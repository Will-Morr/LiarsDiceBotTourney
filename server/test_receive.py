import zmq
import json

# Set up ZMQ connection
context = zmq.Context.instance()
server_socket = context.socket(zmq.SUB)

# Server socket to get game state and send metadata/moves
server_url = f"tcp://127.0.0.1:5556"
server_socket.connect(server_url)
server_socket.setsockopt(zmq.SUBSCRIBE, b"")

print(f"Waiting for message")
while True:
    fulMsg = server_socket.recv_multipart()
    print(f"\n\n\n{fulMsg}")