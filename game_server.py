from datetime import datetime
import argparse
import json
import zmq
import threading
import time
import queue
import uuid


parser = argparse.ArgumentParser()
parser.add_argument("zmq_address", help="Address to start ZMQ on")
parser.add_argument("config_path", help="Path to server config to use")
args = parser.parse_args()

timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
print(timestamp)

# Load server configuration
server_config = json.load(open(args.config_path))

def runServer(server_config):
    # Init everything
    
    lastTourneyTime = time.time() # Init time of last tourney to current time


    # Init ZMQ router
    context = zmq.Context()
    socket = context.socket(zmq.ROUTER)
    socket.bind(f"tcp://*:5555")
    socket.setsockopt(zmq.RCVTIMEO, int(2*server_config['move_timeout_S'])) # Set timeout to double move timeout

    # Poll for ZMQ clients and wait until tourney interval to start 

    # List of clients that are active
    clients = {}
    
    # Giant loop to run tourneys repeatedly
    while True:
        # Loop receiving new connections until new tourney starts
        while time.time() < lastTourneyTime + server_config['tourney_freq_S']:
            # Get message
            try:
                identity, _, message = socket.recv_multipart()
            except zmq.Again:
                continue
            msg_data = json.loads(message.decode())

            print(f"{identity} : {message}")

            # Verify that message is legitimate bot metadata
            if 'message_type' not in msg_data or msg_data['message_type'] != 'BotRegistry':
                print(f"Invalid Message Received: {msg_data}")
                continue
            
            # If new connection, add
            if identity not in clients:
                print(f"New connection: {msg_data['full_title']} ({identity})")
                clients[identity] = msg_data

        lastTourneyTime = time.time()

        # Make sure we have enough bots
        if len(clients) < 1:
            print(f"Not enough clients to start tourney ({len(clients)})")
            continue

        print(f"Starting tourney with {len(clients)} bots")
        

        # TESTING NETWORKING

        # Example game state
        EXAMPLE_GAME_STATE =  {
            "message_type": "GameState",

            "bid": [4,5],
            "dice": [1,2,0,0,1,1],

            "player_count": 4,
            "face_counts": [2,4,3,5],
            "bot_index": 3,
            "wild_ones": True,
            
            "bid_history": [[1,4,0],[2,2,1],[4,5,2]],
            "round_count": 6,

            "round_history": [
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

            "game_uuid": str(uuid.uuid4())
        }
        
        # Spam client with data to make sure it responds nicely
        for client_id in clients:
            for ii in range(100):
                socket.send_multipart([client_id, b'', json.dumps(EXAMPLE_GAME_STATE).encode('utf-8')])
        
        # Split bots into games

        # Init queues for game engines

        # Kick off game engines

        # Handle re-routing ZMQ messages to engines
        # Wait for games to return or hang

        # Send responses to logger

        # Repeat





runServer(server_config)