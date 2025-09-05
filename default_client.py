import uuid
import argparse
import zmq
import time
import json
from concurrent.futures import ThreadPoolExecutor
import random
import threading

parser = argparse.ArgumentParser()
parser.add_argument("zmq_address", help="Address to start ZMQ on")
args = parser.parse_args()

# Hardcoded bot metadata
BOT_REGISTRY_DATA = {
    "message_type": "BotRegistry",
    "player": "ExampleHuman",
    "name": "DefaultBot",
    "version": "1.0",
    "stateless": True,
    "software_engineer": False,
    "machine_learning": False,
    "internet": False,
}

def CalculateMove(game_state):
    # DO YOUR MOVE LOGIC HERE
    randVal = random.randint(0, 100)
    
    return {
        "response_type": "bid",
        "bid": [randVal,4]
    }
    
def MoveHandlerThread(context):
    # Socket to get game states
    receiver = context.socket(zmq.PULL)
    receiver.connect("inproc://game-states")

    # Socket to send responses
    sender = context.socket(zmq.PUB)
    sender.connect(f"inproc://moves")

    while True:
        try:
            # Receive game state and get response
            game_state = receiver.recv_json()
            respose = CalculateMove(game_state)

            # Add required metadata
            respose["message_type"] = "BotMove",
            respose["game_uuid"] = game_state["game_uuid"],

            sender.send_json(respose)
        except zmq.ZMQError as e:
            print(f"MoveHandlerThread error: {e}")
            break



# Generate metadata
SESSION_GUID = str(uuid.uuid4())
print(f"SESSION_GUID:{SESSION_GUID}")
BOT_REGISTRY_DATA["session_uuid"] = SESSION_GUID
BOT_REGISTRY_DATA["full_title"] = "_".join([BOT_REGISTRY_DATA['name'], BOT_REGISTRY_DATA['version'], BOT_REGISTRY_DATA['player']])

# Set up ZMQ connection
context = zmq.Context.instance()
server_socket = context.socket(zmq.DEALER)
server_socket.setsockopt_string(zmq.IDENTITY, SESSION_GUID) # Set ID

# Server socket to get game state and send metadata/moves
server_url = f"tcp://{args.zmq_address}:5555"
server_socket.connect(server_url)

# Backend socket for thread communication
backend_socket = context.socket(zmq.SUB)
backend_socket.bind(f"inproc://moves")
backend_socket.setsockopt(zmq.SUBSCRIBE, b"")

# Backend socket to send 
gameState_socket = context.socket(zmq.PUSH)
gameState_socket.bind("inproc://game-states")

# Send metadata on boot
server_socket.send_multipart([b'', json.dumps(BOT_REGISTRY_DATA).encode('utf-8')]) # DEALER sends: [empty_frame, message]

# Poller to have main loop receive both game states and finished move calculation
poller = zmq.Poller()
poller.register(server_socket, zmq.POLLIN)
poller.register(backend_socket, zmq.POLLIN)


# Kick off threads to convert game states into moves
for i in range(10):
    t = threading.Thread(target=MoveHandlerThread, args=[context])
    t.start()

# Main loop
while True:
    try:
        # Poll for messages with 10 second timeout
        socks = dict(poller.poll(5000))
        # Handle incoming client requests
        if server_socket in socks and socks[server_socket] == zmq.POLLIN:
            _, message = server_socket.recv_multipart()
            message = json.loads(message.decode('utf-8'))
            if 'message_type' in message and message['message_type'] == 'GameState':
                gameState_socket.send_json(message)
            else:
                print(f"WARNING: Unknown message type {message}")

        # Handle responses from backend socket
        elif backend_socket in socks and socks[backend_socket] == zmq.POLLIN:
            message = backend_socket.recv_string()
            server_socket.send_multipart([b'', message.encode('utf-8')])
            print(message)
            print(type(message))

        # Ping server if timed out
        elif len(socks) == 0:
            print(f"Poller timed out, sending metadata")
            server_socket.send_multipart([b'', json.dumps(BOT_REGISTRY_DATA).encode('utf-8')])
            print(BOT_REGISTRY_DATA)
            print(type(BOT_REGISTRY_DATA))
        
        # Something is afoot
        else:
            print(f"Failed to handle {socks}")
    except KeyboardInterrupt:
        print("Shutting down...")
        break
