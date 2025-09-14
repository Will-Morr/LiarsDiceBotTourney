import random

# Hardcoded bot metadata
BOT_REGISTRY_DATA = {
    "player": "SkillIssue",
    "name": "OnlyBids1s",
    "version": "1.0",
    "stateless": True,
    "software_engineer": True,
    "machine_learning": False,
    "internet": False,
}

# This function is called every move. The complete game history is passed in and a bid or call is returned
def calculateMove(game_state):
    return {
        "response_type": "bid",
        "bid": [game_state['bid'][0]+1, 1]
    }
