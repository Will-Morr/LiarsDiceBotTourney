from datetime import datetime
import argparse
import json
import zmq
import threading
import time
import queue
import uuid
import numpy as np


parser = argparse.ArgumentParser()
parser.add_argument("zmq_address", help="Address to start ZMQ on")
parser.add_argument("config_path", help="Path to server config to use")
parser.add_argument("-d", "--debug_info", default=False, help="Print debug info about games")
args = parser.parse_args()

DEBUG_INFO = args.debug_info

timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
print(timestamp)

# Load server configuration
server_config = json.load(open(args.config_path))

def botRegistration(clients, id, data, broadcast_socket = None):
    # If new connection, add
    if id not in clients:
        msg_data = json.loads(data)
        print(f"New connection: {id} : {msg_data['full_title']}")
        clients[id] = {
            'metadata': msg_data,
            'last_ping': time.time()
        }

        # Broadcast bot registration if requested
        if broadcast_socket:
            broadcast_socket.send_multipart([
                b'RegisterBot',
                json.dumps(msg_data).encode('utf-8')
            ])
    # Otherwise track ping
    else:
        clients[id]['last_ping'] = time.time()

def rollNewDice(game_state):
    player_count = len(game_state['dice_counts'])
    new_hands = [[0] * 6 for _ in range(player_count)] # Nested list of zeros
    for botIdx in range(player_count):
        for i in range(game_state['dice_counts'][botIdx]):
            new_hands[botIdx][np.random.randint(0, 6)] += 1
    return new_hands

def goToLegalPlayer(game_state):
    nextPlayer = game_state['bot_index'] % len(game_state["dice_counts"])
    while game_state["dice_counts"][nextPlayer] == 0:
        nextPlayer += 1
        if nextPlayer == game_state['bot_index']:
            print("FATAL ERROR All players have no dice")
            exit()
        if nextPlayer >= len(game_state["dice_counts"]):
            nextPlayer -= len(game_state["dice_counts"])
    game_state['bot_index'] = nextPlayer
    return game_state


def endRound(result, game_state, face_counts, losing_player, calling_player):
    global DEBUG_INFO
    if DEBUG_INFO:
        print(f"\nROUND END: {losing_player} {result} {face_counts}")
        print(f"dice_counts: {game_state['dice_counts']}")
        for foo in game_state['bid_history']:
            print(foo)

    # Losing player loses a die but goes first next round
    game_state["dice_counts"][losing_player] -= 1

    # Get who starts next round (assuming players are out) this 
    game_state = goToLegalPlayer(game_state)

    # Reset ones being wild
    game_state["wild_ones"] = True
    game_state["first_round"] = True

    # Save current round data as history
    round_history = {
        "losing_player": losing_player,
        "calling_player": calling_player,
        "result": result,
        "bid_history": game_state['bid_history'],
        "face_counts": face_counts,
    }
    game_state["round_history"].append(round_history)
    game_state["bid"] = [0, 6]
    game_state["bid_history"] = []
    game_state["round_count"] += 1

    return game_state, rollNewDice(game_state)

def GameEngineThread(context, dice_count, do_drop_wilds, player_uuids, tourney_uuid, timeout_Ms):
    # Init game state
    start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    player_count = len(player_uuids)
    game_uuid = str(uuid.uuid4())
    game_state =  {
        "bid": [0, 6], # Any raise will be a legal bid

        "player_count": len(player_uuids),
        "dice": [0, 0, 0, 0, 0, 0], # Updated on message send
        "dice_counts": [dice_count for _ in range(player_count)],
        "bot_index": 0,
        "wild_ones": True,
        "first_round": True,
        
        "bid_history": [],
        "round_count": 0,

        "round_history": [],

        "game_uuid": game_uuid
    }

    ping_times = [[] for _ in range(len(player_uuids))]

    current_hands = None
    
    # Init socket connection
    gameEngine_socket = context.socket(zmq.DEALER)
    gameEngine_socket.connect(f"inproc://game_engine")
    gameEngine_socket.setsockopt_string(zmq.IDENTITY, game_uuid)

    poller = zmq.Poller()
    poller.register(gameEngine_socket, zmq.POLLIN)
    
    while True:
        # Roll new dice (on start and on new round)
        if current_hands == None:
            current_hands = rollNewDice(game_state)

        # Update current dice counts in state
        game_state['dice'] = current_hands[game_state['bot_index']]

        # Send game state to bot
        gameEngine_socket.send_multipart([
            b'', 
            b'MoveRequest',
            player_uuids[game_state['bot_index']],
            json.dumps(game_state).encode('utf-8')
        ])

        # Ease of reference var
        bot_index = game_state['bot_index']

        # Get response and ping time
        response_ping = time.time()
        socks = dict(poller.poll(timeout_Ms))
        response_ping = time.time() - response_ping
        ping_times[bot_index] = response_ping

        # Handle move
        if gameEngine_socket in socks and socks[gameEngine_socket] == zmq.POLLIN:
            _, response = gameEngine_socket.recv_multipart()
            
            response = json.loads(response)

            # Set last bidder if not first bid
            if len(game_state['bid_history']) > 0:
                last_bidder = game_state['bid_history'][-1][2]
            else:
                last_bidder = bot_index

            # if call, calculate if it is correct
            if response['response_type'] == 'call':
                dice_sums = np.sum(np.array(current_hands), axis=0)
                
                # Add ones if wild
                if game_state['wild_ones']:
                    dice_sums[1:] += dice_sums[0]
                
                bidRealValue = dice_sums[game_state['bid'][1]-1] # subtract 1 for zero indexing

                # actually check if bid was legitimate
                if bidRealValue < game_state['bid'][1]:
                    game_state, current_hands = endRound("bad_call", game_state, current_hands, bot_index, bot_index)
                else:
                    game_state, current_hands = endRound("good_call", game_state, current_hands, last_bidder, bot_index)

            elif response['response_type'] == 'bid':
                # Update wild ones status before we do anything else
                if game_state["first_round"] and response['bid'][1] == 1 and do_drop_wilds:
                    game_state["wild_ones"] = False
                
                # If bids have been place and current bot was first player, first round is over
                if len(game_state["bid_history"]) > 0 and game_state["bid_history"][-1][2] == bot_index:
                    game_state["first_round"] = False

                # Append bot index to end of history
                game_state['bid_history'].append([response['bid'][0], response['bid'][1], bot_index])
                
                # Count cannot ever decrease
                if response['bid'][0] < game_state['bid'][0]:
                    game_state, current_hands = endRound("error_lower_count", game_state, current_hands, bot_index, bot_index)

                # If count is the same, face must increase
                elif response['bid'][0] == game_state['bid'][0] and response['bid'][1] <= game_state['bid'][1]:
                    game_state, current_hands = endRound("error_increase_face", game_state, current_hands, bot_index, bot_index)

                # Cannot bid more dice than exist
                elif response['bid'][0] > sum(game_state['dice_counts']):
                    game_state, current_hands = endRound("error_overflow", game_state, current_hands, bot_index, bot_index)
                
                # Move was successful, update info and pass turn
                else:
                    # Update bid
                    game_state['bid'] = [response['bid'][0], response['bid'][1]]

                    # Pass to next player
                    game_state['bot_index'] += 1
                    game_state = goToLegalPlayer(game_state)

        # Handle bot timeout
        elif len(socks) == 0:
            print(f"Bot timed out")
            game_state, current_hands = endRound("error_timeout", game_state, current_hands, bot_index, bot_index)

        # Break if only one bot remains
        if sum(game_state['dice_counts']) == max(game_state['dice_counts']):
            break

    # Def not the fastest way to do this but it runs once per round so eh
    bot_rankings = []
    for round in game_state['round_history']:
        for playerIdx, counts in enumerate(round['face_counts']):
            if sum(counts) == 0 and playerIdx not in bot_rankings:
                bot_rankings = [playerIdx] + bot_rankings
    
    # Build game log
    game_log = {
        "game_history": [game_state['round_history']],
        "bot_rankings": bot_rankings,

        "bot_count": len(player_uuids),
        "dice_count": dice_count,
        "wild_ones_drop": do_drop_wilds, 

        "bot_uuids": [str(foo) for foo in player_uuids],
        "game_uuid": game_uuid,
        "tourney_uuid": tourney_uuid,

        "start_time": start_time,
        "end_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "ping_averages_mS": [1000*np.average(arr) for arr in ping_times],
        "ping_maximums_mS": [1000*np.max(arr) for arr in ping_times]
    }

    # Send game log
    gameEngine_socket.send_multipart([
        b'', 
        b'GameLog',
        json.dumps(game_log).encode('utf-8')
    ])

    return

def runServer(server_config):
    # Init everything
    
    lastTourneyTime = time.time() # Init time of last tourney to current time


    # Init ZMQ router
    context = zmq.Context.instance()

    # Init communication with bots
    bot_socket = context.socket(zmq.ROUTER)
    bot_socket.bind(f"tcp://*:5555")

    # Init broadcast communications for logs
    broadcast_socket = context.socket(zmq.PUB)
    broadcast_socket.bind(f"tcp://*:5556")

    # Init internal game communication
    gameEngine_socket = context.socket(zmq.ROUTER)
    gameEngine_socket.bind(f"inproc://game_engine")

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
                messageIdentity, _, messageType, *messageData = bot_socket.recv_multipart()

                # Verify that message is legitimate bot metadata
                if messageType == b'RegisterBot':
                    botRegistration(clients, messageIdentity, messageData[0], broadcast_socket)
                elif messageType == b'Move':
                    print(f"Bot {messageIdentity} responded too late, RIP")
                else:
                    print(f"Invalid Message Received: {messageType}")
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
        if len(clients) < 2:
            print(f"Not enough clients to start tourney ({len(clients)})")
            continue

        print(f"Starting tourney with {len(clients)} bots")
        tourney_uuid = str(uuid.uuid4())
        
        # Kick off game engines
        # TODO Don't just put every bot in the same games
        game_threads = []
        game_logs = []
        game_threads_live = True
        print(f"Kicking off {server_config['games_per_tourney']} games")
        for i in range(server_config['games_per_tourney']):
            bot_uuids = list(clients.keys())
            print(f"Starting game {i} with UUIDs {bot_uuids}")
            t = threading.Thread(
                target=GameEngineThread, 
                args=[context, server_config['dice_count'], server_config['do_drop_wilds'], bot_uuids, tourney_uuid, server_config['move_timeout_mS']],
                name=f"GameEngine_{i}",
                daemon=True
            )
            t.start()
            game_threads.append(t)

        # Handle re-routing ZMQ messages to engines
        # Wait for all games to return or hang
        while game_threads_live:
            socks = dict(poller.poll(100)) # 100ms timeout so we will start tournament even if every bot is connected

            # Timeout hit, check to make sure all games threads are still live
            if len(socks) == 0:
                # Check for live game threads
                game_threads_live = False
                for t in game_threads:
                    if t.is_alive():
                        game_threads_live = True
                        break
                if not game_threads_live:
                    print("WARNING All game threads returned without full logs")
                    # We timed out despite all games having returned. This should not happen
                    break
            
            # Handle bot communication
            elif bot_socket in socks and socks[bot_socket] == zmq.POLLIN:                    
                messageIdentity, _, messageType, *messageData = bot_socket.recv_multipart()
                
                # Verify that message is legitimate bot metadata
                if messageType == b'RegisterBot':
                    botRegistration(clients, messageIdentity, messageData[0], broadcast_socket)
                # Handle move response
                elif messageType == b'Move':
                    # Move data is [game_uuid, move_json] so pass those directly to game engines
                    gameEngine_socket.send_multipart([messageData[0], b'', messageData[1]])
                else:
                    print(f"Invalid Message Type Received: {messageType}")
                    continue
            
            # Handle engine communication
            elif gameEngine_socket in socks and socks[gameEngine_socket] == zmq.POLLIN:
                messageIdentity, _, messageType, *messageData = gameEngine_socket.recv_multipart()
                
                # Redirect move requests to the appropriate bot GUID
                if messageType == b'MoveRequest':
                    # Include messageIdentity to trace game
                    bot_socket.send_multipart([messageData[0], b'', b'GameState', messageIdentity, messageData[1]])
                
                # Log game results
                elif messageType == b'GameLog':
                    game_logs.append(messageData[0])
                    broadcast_socket.send_multipart([b'GameLog', messageData[0]])

            # Something is afoot
            else:
                print(f"Failed to handle {socks}")

            # Break if all games have returned
            if len(game_logs) == server_config['games_per_tourney']:
                break

        print(f"TOURNEY COMPLETE\n\n")
        # Send responses to logger

        # Repeat





runServer(server_config)