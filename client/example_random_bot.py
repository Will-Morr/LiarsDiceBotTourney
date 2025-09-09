import random

# Hardcoded bot metadata
BOT_REGISTRY_DATA = {
    "player": "ExampleHuman",
    "name": "DefaultBot",
    "version": "1.0",
    "stateless": True,
    "software_engineer": False,
    "machine_learning": False,
    "internet": False,
}

def calculateMove(game_state):
    # 1/20 chance of randomly calling
    if random.randint(0, 20) == 0:
        return {
            "response_type": "call",
        }

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
