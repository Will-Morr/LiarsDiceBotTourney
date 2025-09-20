import uuid
import argparse
import zmq
import time
import json
import random
from multiprocessing import Process
import os
import importlib.util
from pathlib import Path
import socket

parser = argparse.ArgumentParser()
parser.add_argument("zmq_address", help="Address to start ZMQ on")
parser.add_argument("bot_path", help="Python file containing bot info")
parser.add_argument("-p", "--ping_freq_mS", default=10000, help="How frequently to ping server (default is 10 seconds)")
args = parser.parse_args()

# Import library specified as argument
# We do it this way so players can just copy example bot without duplicating code
module_name = args.bot_path.stem if hasattr(args.bot_path, 'stem') else 'dynamic_module'
spec = importlib.util.spec_from_file_location(module_name, args.bot_path)
bot_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bot_module)

CalculateMove = bot_module.calculateMove
BOT_REGISTRY_DATA = bot_module.BOT_REGISTRY_DATA

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

# Send metadata on boot
def register_bot():
    server_socket.send_multipart([b'', b'RegisterBot', json.dumps(BOT_REGISTRY_DATA).encode('utf-8')])
register_bot()

# Poller to have main loop receive both game states and finished move calculation
poller = zmq.Poller()
poller.register(server_socket, zmq.POLLIN)

# Main loop
print("Handlers started, running main loop")
while True:
    try:
        # Poll for messages with 10 second timeout
        # This timeout is required to make sure the server gets pinged every 10 seconds
        socks = dict(poller.poll(int(args.ping_freq_mS)))

        # Handle incoming client requests
        if server_socket in socks and socks[server_socket] == zmq.POLLIN:
            fulMsg = server_socket.recv_multipart()
            _, messageType, *messageData = fulMsg
            if messageType == b'GameState':
                # Receive game state and get response
                game_uuid = messageData[0]
                game_state = messageData[1]
                response = CalculateMove(json.loads(game_state))
                server_socket.send_multipart([b'', b'Move', game_uuid, json.dumps(response).encode('utf-8')])
            elif messageType == b'Print':
                print(f"Received: {messageData[0].decode('utf-8')}")
            elif messageType == b'Ping':
                server_socket.send_multipart([b'', b'Ping'])
                print('Server pinged, game may start soon   ', end='\r', flush=True)
            else:
                print(f"WARNING: Unhandled message type {messageType}")

        # Ping server if timed out
        elif len(socks) == 0:
            register_bot()
        
        # Something is afoot
        else:
            print(f"Failed to handle {socks}")

    except KeyboardInterrupt:        
        break

print("Shutting down...")
server_socket.close()
