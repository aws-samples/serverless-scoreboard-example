# Serverless Scoreboard Example.

## Introduction.
This example is to show how to implement a Scoreboard with the Serverless Stack and DynamoDB. The data model for Scoreboards is described well in the DynamoDB Documentation for how to use Global Secondary Indexes https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GSI.html#GSI.scenario. That Documentation only covers half of this example. The part that is not covered is how to efficiently query the access pattern "What rank does player X have". Usually a game scorboard will show the top 100 players and the rank fo my player, which could be 137862. In DynamoDB you can do a query "where score above X" and ask DynamoDB to return count on it but if the number of players is high then that query will end up being very exensive and slow as it needs to find all players. 

This implementation aggregates players into tiers of score ranges. This is done using a scheuduled lambda that goes through the score intervals defined as size of each tier and queries them between 0 and current max score. This in it self is a relativly expensive operation but its done once every X min and not for each request.

When the user requests the score the lambda function first queries all tiers with higher score then the players and sums up number of players within those tiers. Then that value is added to the number of players with higher score then the player within the players tier. All these queries are on predictable sized data sets and will scale as long as the tier size is optimized to the games score range and player numbers.

The size of the tiers can be changed and tiers recalculated on the fly to optimize the queries.

For the highest tier the accouracy of the "What rank does player X have" query is 100% accurate. The further down the ranks and the lower the recalculation frequency of the tiers the less accurate the score is over time. The drift in accuracy occures when player Y from a lower tier then player X passes player X, then that wount be detected until next recalculation of the tiers. If player X moves tiers then the implementation is still accurate.

## Data Model.
The data model in this example expands on the examples in https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/GSI.html#GSI.scenario.

The supported access patterns are.

Customer facing Queries.
Query list of players sorted by score for a game.
Query the score of a player.

Supporting Queries.
Distinct games.
Count players for a game within a score range.
Number of players in each score range (tier).

The table has Hashkey toplist_pk, Rangekey toplist_sk and two GSI´s.
GSI 1. game-scores-index with keys toplist_pk and score.
GSI 2. game-tiers-index with keys toplist_pk and from_score.
````
|toplist_pk|toplist_sk|score|nr_players|from_score|to_score|
|games     |unicorns  |     |          |          |        |
|games     |dragons   |     |          |          |        |
|unicorns  |player1   | 2422|          |          |        |
|unicorns  |player2   |  122|          |          |        |
|unicorns  |player3   |   30|          |          |        |
|unicorns  |tier#0    |     |         1|         0|     999|
|unicorns  |tier#1000 |     |         1|      1000|    1999|
|unicorns  |tier#2000 |     |         1|      2000|    2999|
|dragons   |player1   | 3240|          |          |        |
|dragons   |player2   | 2122|          |          |        |
|dragons   |player3   | 2032|          |          |        |
|dragons   |player4   |  302|          |          |        |
|dragons   |tier#0    |     |         1|         0|     999|
|dragons   |tier#1000 |     |         1|      1000|    1999|
|dragons   |tier#2000 |     |         2|      2000|    2999|
|dragons   |tier#3000 |     |         1|      3000|    3999|
````
## Setup 

### Deploying 

To deploy this application into a AWS account you can use the `simple-deploy.sh` script provided. 

````bash 
./simple-deploy.sh --profile your_aws_profile
````
The profile `your_aws_profile` needs to have enough privilages to deploy the application.

````yml
      Policies:
        - PolicyName: root
          PolicyDocument:
            Version: 2012-10-17
            Statement:
              - Effect: Allow
                Action:
                - apigateway:*
                - cloudformation:*
                - dynamodb:*
                - events:*
                - lambda:*
                - iam:*
                - s3:*
                Resource:
                - "*"
````

You will be promted on the IAM changes that the deployment will make in your account. Choose `y` if you are ok with the changes.

The application now deploys with CDK to your account.


## Testing

There is a lambda function provided to generate test data for a game called 'unicorn-hunters' and with players that have ids `u${index}`. To generate the test data run the following cli command using the same profile as during deployment.

````bash 
aws lambda invoke --profile your_aws_profile --function-name scoreboard-example-generate-test-data-function /dev/stdout
````

Tiers are calculated every minuite so either wait a min or if you are eager to get going run `scoreboard-example-calculate-nr-players-per-tier-function`.

````bash 
aws lambda invoke --profile your_aws_profile --function-name scoreboard-example-generate-test-data-function /dev/stdout
````

````bash 
aws lambda invoke --profile your_aws_profile --function-name scoreboard-example-calculate-nr-players-per-tier-function /dev/stdout
````

To get the score for player u123.
````bash 
curl https://<YOUR_API_ID>.execute-api.eu-west-1.amazonaws.com/prod/game/unicorn-hunters/player/u123/score
````

To find YOUR_API_ID go to the API Gateway in the console and select the `scoreboard-example-api`

To update the score for a player
````
curl --header "Content-Type: application/json" \
  --request POST \
  --data '{"game": "unicorn-hunters", "score": 6450}' \
  https://<YOUR_API_ID>.execute-api.eu-west-1.amazonaws.com/prod/game/unicorn-hunters/player/u123/score

curl https://<YOUR_API_ID>.execute-api.eu-west-1.amazonaws.com/prod/game/unicorn-hunters/player/u123/score
````

To get the scoreboard for the 100 first players.
````
curl https://<YOUR_API_ID>.execute-api.eu-west-1.amazonaws.com/prod/game/unicorn-hunters/scoreboard
````

To paginate the result for the next 100 players use the next_page key provided in the result as a query parameter to get the next page and provide the last_rank to offset the ranking of the next page.
````
curl https://<YOUR_API_ID>.execute-api.eu-west-1.amazonaws.com/prod/game/unicorn-hunters/scoreboard?last_rank=100&next_page=%7B%22game%22%3A%20%22unicorn-hunters%22%2C%20%22player%22%3A%20%22u9%22%2C%20%22score%22%3A%2022428.0%7D
````

## License

This library is licensed under the MIT-0 License. See the LICENSE file.

