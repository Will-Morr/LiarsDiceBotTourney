import random

# Hardcoded bot metadata
BOT_REGISTRY_DATA = {
    "player": "SimplePlayer",
    "name": "RaiseByOne",
    "version": "1.0",
    "stateless": True,
    "software_engineer": True,
    "machine_learning": False,
    "internet": False,
}

# This function is called every move. The complete game history is passed in and a bid or call is returned
def calculateMove(game_state):
    # Otherwise, raise bid by one
    bid = game_state['bid']
    bid[1] += 1
    
    # If face exceeds six, increment count instead
    if bid[1] > 6:
        bid = [bid[0]+1, 1]
    
    return {
        "response_type": "bid",
        "bid": bid
    }
