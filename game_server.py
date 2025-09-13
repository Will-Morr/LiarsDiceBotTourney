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

def botRegistration(clients, id, data):
    # If new connection, add
    if id not in clients:
        msg_data = json.loads(data)
        print(f"New connection: {id} : {msg_data['full_title']}")
        clients[id] = {
            'metadata': msg_data,
            'last_ping': time.time()
        }
    # Otherwise track ping
    else:
        clients[id]['last_ping'] = time.time()

def runServer(server_config):
    # Init everything
    
    lastTourneyTime = time.time() # Init time of last tourney to current time


    # Init ZMQ router
    context = zmq.Context()
    bot_socket = context.socket(zmq.ROUTER)
    bot_socket.bind(f"tcp://*:5555")
    bot_socket.setsockopt(zmq.RCVTIMEO, int(2*server_config['move_timeout_S'])) # Set timeout to double move timeout

    # Init internal game communication
    gameEngine_socket = context.socket(zmq.ROUTER)
    gameEngine_socket.bind(f"inproc://games")
    gameEngine_socket.setsockopt(zmq.RCVTIMEO, int(2*server_config['move_timeout_S'])) # Set timeout to double move timeout

    # Poller to handle both network comms and game comms
    poller = zmq.Poller()
    poller.register(bot_socket, zmq.POLLIN)
    poller.register(gameEngine_socket, zmq.POLLIN)

    # Poll for ZMQ clients and wait until tourney interval to start 

    # List of clients that are active
    clients = {}
    
    # Giant loop to run tourneys repeatedly
    while True:
        # Loop receiving new connections until new tourney starts
        while time.time() < lastTourneyTime + server_config['tourney_freq_S']:
            socks = dict(poller.poll(100)) # 100ms timeout so we will start tournament even if every bot is connected

            # Timeout happened, ignore
            if len(socks) == 0:
                continue
            # Handle incoming registrations from bots
            elif bot_socket in socks and socks[bot_socket] == zmq.POLLIN:                    
                full_message = bot_socket.recv_multipart()
                messageIdentity = full_message[0]
                messageType = full_message[2]
                messageData = full_message[3:]

                # Verify that message is legitimate bot metadata
                if messageType == b'RegisterBot':
                    botRegistration(clients, messageIdentity, messageData[0])
                elif messageType == b'Move':
                    print(f"Bot {messageIdentity} responded too late, RIP")
                else:
                    print(f"Invalid Message Received: {full_message}")
                    continue
            
            # We should not have engine communication here but just in case
            elif gameEngine_socket in socks and socks[gameEngine_socket] == zmq.POLLIN:
                bad_message = gameEngine_socket.recv_multipart()
                print(f"Received what should be an impossible message from gameEngine_socket : {bad_message}")
            # Something is afoot
            else:
                print(f"Failed to handle {socks}")

        # Delete all bots that have been inactive for 30 seconds
        currentTime = time.time()
        for id in list(clients.keys()):
            data = clients[id]
            if 30 < currentTime - data['last_ping']:
                print(f"Deleting timed out bot {id} : {data['metadata']['full_title']}")
                del clients[id]            

        # Update last tourney time even if we don't have enough connections to run a game
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
            for ii in range(3):
                bot_socket.send_multipart([client_id, b'', json.dumps(EXAMPLE_GAME_STATE).encode('utf-8')])
        
        # Split bots into games

        # Init queues for game engines

        # Kick off game engines

        # Handle re-routing ZMQ messages to engines
        # Wait for games to return or hang

        # Send responses to logger

        # Repeat





runServer(server_config)