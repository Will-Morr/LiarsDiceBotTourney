# Liars Dice Bot Tourney

WORK IN PROGRESS

This repo contains a system for running a liars dice bot tournament. A central computer continuously runs games (`game_server.py`) and each player runs a bot locally on their computer (`client_example.py`). 

We want to run as many games as quickly as possible, so both the server and client are multi-threaded to run many games in parallel. This also lets us run a higher time per turn while still getting a large number of games per minute.

The current example client plays randomly but is functional, if very bad and occasionally tanking penalties for illegal moves. 

## TODO
 - Matchmaking, probably random but we need to make sure bots don't play themselves
 - Logging, likely just dumping all bot, game, and tourney jsons into folders
 - Database, ingesting all of this into a queryable table
 - Leaderboard, pull and visualize data from database
 - Example bots, we need a few bare-bones bots to test the system
 - Other languages? If anyone wants to use any tool other than python feel free to re-implement default_client in a language of your choice and make a PR. 

## Schemas

This section is all the info you really need to make a bot. You update the existing metadata array in the example, write something to process game state, and then return a bot response. 

### Bot Metadata
On startup, the client sends the server session data. 

The first section is hardcoded metadata for this specific bot. `player` should just be your full name and is how we track score. Naming your bots and tracking updates would be appreciated to make poking around in the data more clear. 

Please also specify the other tags (which are somewhat TBD right now). Having flags for substantial advantages (like being a full time software engineer or using machine learning instead of pure logic) would open up the playing field to more players. Even if there is a clear dominant strategy using a more sophisticated tool it would be fun to have a best manual bot or best amateur bot category. 

`session_uuid` is the randomly generated uuid used to track this bot. It is regenerated every time you restart the bot. 

`full_title` is just all the identifier as one string for easy display. 

```
{
    "player": "JaneDoe",
    "name": "CleverBot",
    "version": "1.0",
    
    "stateless": true,
    "software_engineer": false,
    "machine_learning": false,
    "internet": false,

    "session_uuid": "c13ca266-51b5-4ab2-9b4f-75e24e131975",
    "full_title": "CleverBot_1.0_JaneDoe"
}
```

### Game State

`bid` is the current bid, where you must either increase the face value at the same count or increase the count. It is encoded as [count, face]

`dice` is the current counts of your dice.

These two pieces of data are the only data you need to make an rudimentary bot.

`player_count` is the number of players.

`dice_counts` is how many dice each player has remaining. Players with 0 are out of the game and skipped.

`bot_index` is where you are in the turn order.

`wild_ones` is indicating that ones are still considered wild cards. There is an special rule that if a player bids some number of ones during the first round ones stop being wild. We may or may not drop this rule for simplicity. 

`first_round` is if all players have made a move. wild_ones is locked once this goes false

This should be all the data required for a statistically perfect bot, assuming random play. Unless you want to get fancy (which admittedly you probably do) you can ignore the following.

`round_history` a list of the bids made during this round. This includes the bidder so each item is [count, face, bot index]

`round_count` specifies the number of rounds completed so far.

This should be all of the data to estimate the other player's dice. 

`game_history` is an list of data for every previous round. Index 0 is the first round. Each row contains the following items:

`calling_player` is the player who called the bluff. This is recorded separately value for if players were skipped. If the bot made an illegial move `calling_player` will be same as `last_bidder`.

`losing_player` is the player who lost this round, losing a die

`result` is the end state of the round. "good_call" is a successfully called bluff by the next player after the loser. "bad_call" is an unsuccessful bluff. Bots responding incorrectly are also logged here. "error_bid" indicates a bid that did not increment, "error_overflow" occurs if more dice than exist are bid (safety catch to prevent infinitely long games). "error_bad_message" indicates a communication failure. "error_timeout" indicates a lack of response in time. 

`bid_history` is the same in both contexts.

`face_counts` is the actual hand of each player. In normal gameplay this is revealed when a round ends to check the call, so bots also have access to this after the round ends.

`game_uuid` is metadata to track what game this turn is for, ignore. 

```
{
    "bid": [4,5],
    "dice": [1,2,0,0,1,1],

    "player_count": 4,
    "dice_counts": [2,4,3,5],
    "bot_index": 3,
    "wild_ones": true,
    "first_round": true,
    
    "bid_history": [[1,4,0],[2,2,1],[4,5,2]],
    "round_count": 6,

    "round_history": [
        ...
        {
            "losing_player": 0,
            "calling_player": 1,
            "result": "good_call",
            "bid_history": [[1,2,0],[2,2,1],[2,3,2],[3,3,3],[20,2,0]],
            "face_counts": [
                [0,3,0,0,0,0],
                [1,0,2,0,1,0],
                [0,0,0,3,0,0],
                [2,1,1,1,1,0]
            ]
        }
    ],

    "game_uuid": "97e698f3-6dbe-4b06-8165-91b79373592b"
}
```

### Bot Response

```
{
    "response_type": "bid",
    "bid": [3,4]
    "game_uuid": "97e698f3-6dbe-4b06-8165-91b79373592b",
}
```

`response_type` Either "bid" or "call"

`bid` If response is bid, then bid value

`game_uuid` Which game this response goes to



#### Example Game State Explained

You would have [1, 2, 2, 5, 6] as the actual faces under the dice. You are deciding rather to raise a bid of 4 fives. You can bid a higher face at the same count (IE 4 fives) or a higher count (IE 5 twos as you have 2 twos and 1 one).

This is a four player game (player count may be varied TBD). Player zero has 2 dice remaining, one has 4, and so on. You have 5 dice remaining and are going last in order. 

In the previous round, player 1 called player 0s call of 20 twos. This was a good call, as there were only 7 twos (technically 3 ones and 4 twos). 

### Logs

#### Game Log

```
{
    "game_history": [ ... ],
    "bot_count": 4,
    "dice_count": 5,
    "wild_ones_drop": false, 
    "bot_uuids": ['c13ca266-51b5-4ab2-9b4f-75e24e131975', ...],
    "game_uuid": "c7bc8469-dc7f-4019-9add-b742209559c0",
    "tourney_uuid": "fd439123-02fc-4a2f-88ab-cec335643bf5",
    "bot_rankings": [3,1,2,0],
    "tourney_index": 1,
    "match_index": 1,
    "start_time": "2025-09-04 12:44:57",
    "end_time": "2025-09-04 12:45:15",
    "ping_averages": [0.110, 0.03, 0.042, 0.052],
    "ping_maximums": [0.312, 0.123, 0.244, 0.251] 
}
```

`game_history` is the same as defined in previous sections. 

`bot_count` the number of bots in the game

`dice_count` the number of dice you start with

`wild_ones_drop` whether or not ones get dropped 

`bot_uuids` list of bot uuids

`bot_titles` list of bot titles

`game_uuid` unique tracker for game

`tourney_uuid` unique tracker for what tourney this game was a part of

`bot_rankings` bot indices in reverse order of loss

`start_time` when match started

`end_time` when match ended

`ping_averages` average response time of each bot

`ping_maximums` max response time of each bot

#### Tourney Log

```
{
    "tourney_tag": "default",
    "tourney_games": 10,
    "scoring_method": "531",
    "score_multiplier": 1.0,
    "start_time": "2025-09-04 12:44:57",
    "end_time": "2025-09-04 12:45:15",
    "tourney_uuid": "fd439123-02fc-4a2f-88ab-cec335643bf5",
    "tourney_index": 1,
    "bot_scores": [11, ...]
    "bot_uuids": ["c13ca266-51b5-4ab2-9b4f-75e24e131975", ...],
    "game_uuids": ["c7bc8469-dc7f-4019-9add-b742209559c0", ...],
}
```

`tourney_tag` arbitrary identifier for what this tourney is a part of. Useful to separate test matches from real gameplay

`tourney_games` how many games in this tourney

`scoring_method` how score is rewarded based on performance. 531 is first place gets 5 points, second gets 3, and third gets 1.

`score_multiplier` how much this game should be weighted in case we need this

`start_time` start timestamp of game

`end_time` end timestamp of game

`tourney_uuid` unique ID of tourney

`tourney_index` index of tourney, start counting from 0 on server boot

`bot_scores` points scored by each bot during this tourney

`bot_uuids` list of uuids of bots included

`game_uuids` list of uuids of games played

### Notes on why things are like that

Encoding hands as counts rather than a list of faces makes it much easier to parse game data, as dice only exist as sums. Also this is hopefully the only 1 indexed array I will ever use.

Extra info is included in a few places to make it easier to process. We specify calling player and include the index of each bot to make it easier to handle bots being skipped as they go out. 
