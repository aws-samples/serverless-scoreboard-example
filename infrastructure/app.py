#!/usr/bin/env python3
import os

from aws_cdk import (
    core as _core,
    aws_dynamodb as _dynamodb,
    aws_events as _events,
)
from serverless import Serverless

STR = _dynamodb.AttributeType.STRING
NUM = _dynamodb.AttributeType.NUMBER

GAME = 'toplist_pk'
PLAYER = 'toplist_sk'
SCORE = 'score'
FROM_SCORE = 'from_score'


class AppStack(_core.Stack):
    def __init__(self, scope: _core.Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)
        serverless = Serverless(self)
        serverless.create_application(
            id=id,
            resource_handlers=[
                {
                    'path': '/game/{game}/scoreboard',
                    'methods': ['GET'],
                    'handler': 'handler.get_scoreboard',
                    'size': 1024,
                },
                {
                    'path': '/game/{game}/tiers',
                    'methods': ['DELETE'],
                    'handler': 'handler.delete_tier_aggregates',
                    'size': 1024,
                },
                {
                    'path': '/game/{game}/player/{player}/score',
                    'methods': ['PUT', 'POST'],
                    'handler': 'handler.add_player_score',
                    'size': 1024,
                },
                {
                    'path': '/game/{game}/player/{player}/score',
                    'methods': ['GET'],
                    'handler': 'handler.get_player_score',
                    'size': 1024,
                },
                {
                    'schedule': _events.Schedule.rate(
                        duration=_core.Duration.minutes(1)
                    ),
                    'handler': 'handler.calculate_nr_players_per_tier',
                    'size': 1024,
                },
                {   
                    'handler': 'handler.generate_test_data', 
                    'size': 1024
                },
            ],
            dynamo_table={
                'table_name': '{}-table'.format(id),
                'partition_key': {'name': GAME, 'type': STR},
                'sort_key': {'name': PLAYER, 'type': STR},
                'indexes': [
                    {
                        'index_name': 'game-score-index',
                        'partition_key': {'name': GAME, 'type': STR},
                        'sort_key': {'name': SCORE, 'type': NUM},
                    },
                    {
                        'index_name': 'game-tier-index',
                        'partition_key': {'name': GAME, 'type': STR},
                        'sort_key': {'name': FROM_SCORE, 'type': NUM},
                    },
                ],
            },
        )


if __name__ == '__main__':
    app = _core.App()
    AppStack(app, 'scoreboard-example')
    app.synth()
