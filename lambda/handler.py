import decimal
import json
import os
from random import randint

import boto3
from boto3.dynamodb.conditions import Key


class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return float(o)
        return super(DecimalEncoder, self).default(o)


GAME = 'toplist_pk'
PLAYER = 'toplist_sk'
SCORE = 'score'
TIER = 'toplist_sk'
GAMES = 'toplist_pk'
GAME_IN_GAMES = 'toplist_sk'
FROM_SCORE = 'from_score'

TABLE_NAME = os.environ['TABLE_NAME']
AWS_DEFAULT_REGION = os.environ['AWS_DEFAULT_REGION']

dynamodb_resource = boto3.resource('dynamodb', AWS_DEFAULT_REGION)
table = dynamodb_resource.Table(TABLE_NAME)


def add_player_score(event, context):
    """ 
    Adds a players score to the dynamodb table and updates the games lookup list as well. 

    Called by the api endpoint /game/{game}/player/{player}/score expecting the payload {"score": 123}.
    """
    game = event['pathParameters']['game']
    player = event['pathParameters']['player']
    body = json.loads(event['body'])

    if 'score' in body:
        table.put_item(Item={GAME: game, PLAYER: player, SCORE: body['score']},)
        table.put_item(Item={GAMES: 'games', GAME_IN_GAMES: game},)
        status = 200
    else:
        status = 400

    return {'statusCode': status}


def get_scoreboard(event, context):
    """ 
    Get the scoreboard for a game. Supports pagination and expects the next_page and last_rank to be sent back.
    It converts the names of the dyanmodb collumns to not expose internal structure, this is converted back if the 
    next_page is sent back as it was recieved.

    Called by the api endpoint /game/{game}/scoreboard optional query parameters last_key and next_page.
    """
    game = event['pathParameters']['game']
    query_parameters = event.get('queryStringParameters', {}) or {}
    page_size = query_parameters.get('page_size', 100) or 100
    next_page = query_parameters.get('next_page')
    last_rank = int(query_parameters.get('last_rank', 0) or 0)
    if next_page and next_page.startswith('{'):
        next_page = json.loads(next_page, parse_float=decimal.Decimal)
        next_page = {
            GAME: next_page['game'],
            PLAYER: next_page['player'],
            SCORE: next_page['score'],
        }
    else:
        next_page = dict()

    if bool(next_page):
        game_score = table.query(
            IndexName='game-score-index',
            ScanIndexForward=False,
            Limit=page_size,
            KeyConditionExpression=Key(GAME).eq(game),
            ExclusiveStartKey=next_page,
        )
    else:
        game_score = table.query(
            IndexName='game-score-index',
            ScanIndexForward=False,
            Limit=page_size,
            KeyConditionExpression=Key(GAME).eq(game),
        )

    score_board = {'game': game, 'toplist': []}

    if game_score.get('LastEvaluatedKey'):
        score_board['next_page'] = {
            'game': game_score['LastEvaluatedKey'][GAME],
            'player': game_score['LastEvaluatedKey'][PLAYER],
            'score': game_score['LastEvaluatedKey'][SCORE],
        }

    for rank, score in enumerate(game_score['Items'], start=(1 + last_rank)):
        score_board['toplist'].append(
            {'rank': rank, 'player': score[PLAYER], 'score': int(score[SCORE])}
        )
        score_board['last_rank'] = rank

    return {
        'statusCode': 200,
        'body': json.dumps(score_board, cls=DecimalEncoder),
    }


def get_player_score(event, context):
    """ 
    Get the score for a player by first querying for the score of the player. 

    Then calculate the rank of the player by selecting all tiers that with a higher score then the players.
    Summing the number of players in each of these tiers and then adding the position within the players own tier.

    Called by the api endpoint /game/{game}/player/{player}/score.
    """
    game = event['pathParameters']['game']
    player = event['pathParameters']['player']
    player_score_response = table.query(
        KeyConditionExpression=Key(GAME).eq(game) & Key(PLAYER).eq(player),
    )
    player_score = player_score_response['Items'][0]['score']

    tiers_above = table.query(
        IndexName='game-tier-index',
        KeyConditionExpression=Key(GAME).eq(game) & Key(FROM_SCORE).gt(player_score),
    )

    player_ranking = 1

    for tier in tiers_above['Items']:
        player_ranking += tier['count']

    if len(tiers_above['Items']) > 0:
        next_tier_from_score = tiers_above['Items'][0]['from_score']
        my_tier = table.query(
            IndexName='game-score-index',
            KeyConditionExpression=Key(GAME).eq(game)
            & Key(SCORE).between(player_score, next_tier_from_score - 1),
            Select='COUNT',
            ScanIndexForward=False,
        )
        player_ranking += my_tier['Count']

    return {
        'statusCode': 200,
        'body': json.dumps({'score': int(player_score), 'rank': int(player_ranking)}),
    }


def delete_tier_aggregates(event, context):
    """ 
    Delete the tier aggregates. This should be done when resizing the tiers.

    Called by the api endpoint /game/{game}/tiers.
    """
    game = event['pathParameters']['game']
    games_query = table.query(
        KeyConditionExpression=Key(GAME).eq(game) & Key(TIER).begins_with('tier'),
        ScanIndexForward=False,
    )
    for item in games_query['Items']:
        with table.batch_writer() as batch:
            batch.delete_item(Key={GAME: game, PLAYER: item[PLAYER]})
    return {
        'statusCode': 200,
    }


def calculate_nr_players_per_tier(event, context):
    """ 
    Calculate the number of players within each tier.

    This is done by first selecting all existing games and looping over those. Then for each game the max score is queried. 
    Then using the default tier size of 1000 points create a range of X number of tiers where X depends on what the max score is. 
    Do count queries for each tier range to get number of players with that range.

    Called by a scheduled event.
    """
    games_query = table.query(
        KeyConditionExpression=Key(GAME).eq('games'), ScanIndexForward=False
    )

    for game_entry in games_query['Items']:
        game = game_entry[GAME_IN_GAMES]
        top_score_query = table.query(
            IndexName='game-score-index',
            KeyConditionExpression=Key(GAME).eq(game),
            Limit=1,
            ScanIndexForward=False,
        )

        max_score = top_score_query['Items'][0]['score']

        tier_size = 1000
        nr_tiers, rest = divmod(max_score, tier_size)
        if rest > 0:
            nr_tiers += 1

        for i in range(1, int(nr_tiers + 1)):

            from_score = (i - 1) * tier_size
            to_score = i * tier_size - 1

            tier_player_count_query = table.query(
                IndexName='game-score-index',
                KeyConditionExpression=Key(GAME).eq(game)
                & Key(SCORE).between(from_score, to_score),
                Select='COUNT',
                ScanIndexForward=False,
            )

            count = tier_player_count_query['Count']

            table.put_item(
                Item={
                    GAME: game,
                    TIER: 'tier#{}'.format(from_score),
                    'from_score': from_score,
                    'to_score': to_score,
                    'count': count,
                }
            )
            print('{}-{}: {}'.format(from_score, to_score, count))


def generate_test_data(event, context):
    """ 
    Generate testa data for a game called unicorn-hunters. Generates 200 players with scores betwene 0 and 50000, naming the players 'u{}'.format(i).

    Manually triggered.
    """
    max_score = 50000
    with table.batch_writer() as batch:
        batch.put_item(Item={GAMES: 'games', GAME_IN_GAMES: 'unicorn-hunters'},)
        for i in range(0, 200):
            score = randint(0, max_score)
            batch.put_item(
                Item={GAMES: 'unicorn-hunters', PLAYER: 'u{}'.format(i), SCORE: score},
            )

            if i % 100 == 0:
                print(i)
