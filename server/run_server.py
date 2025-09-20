from datetime import datetime
import argparse
import json
import zmq
import threading
import time
import uuid
import numpy as np
import os
from pathlib import Path
import random
from copy import deepcopy

import process_logs # Load log processor to run as independent thread

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
    player_count = game_state['player_count']
    new_hands = [[0] * 6 for _ in range(player_count)] # Nested list of zeros
    for botIdx in range(player_count):
        for i in range(game_state['dice_counts'][botIdx]):
            new_hands[botIdx][np.random.randint(0, 6)] += 1
    return new_hands

def goToLegalPlayer(game_state):
    nextPlayer = game_state['bot_index']
    for i in range(game_state["player_count"]*2): # Loop through twice as to never hang
        if nextPlayer >= game_state["player_count"]:
            nextPlayer -= game_state["player_count"]

        if game_state["dice_counts"][nextPlayer] > 0:
            break

        nextPlayer += 1

        if nextPlayer == game_state['bot_index']:
            print(f"FATAL ERROR All players have no dice \n{game_state['dice_counts']}\n\n{json.dumps(game_state, indent=4)}")
            exit()
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

    # Record if any player went out
    if game_state["dice_counts"][losing_player] == 0:
        game_state["bot_rankings"].append(losing_player)

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
    start_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    start_time = time.time()
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
        "bot_rankings": [],

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
        ping_times[bot_index].append(response_ping)

        # Handle move
        if gameEngine_socket in socks and socks[gameEngine_socket] == zmq.POLLIN:
            _, response = gameEngine_socket.recv_multipart()
            
            # Set last bidder if not first bid
            if len(game_state['bid_history']) > 0:
                last_bidder = game_state['bid_history'][-1][2]
            else:
                last_bidder = bot_index

            # Sanitize response input
            okayResponse = True
            try:
                response = json.loads(response)
                if 'response_type' not in response: okayResponse = False
                elif response['response_type'] not in ['call', 'bid'] : okayResponse = False
                elif response['response_type'] == 'bid':
                    if 'bid' not in response: okayResponse = False
                    elif response['bid'][0] <= 0: okayResponse = False
                    elif response['bid'][1] > 6: okayResponse = False
            except:
                okayResponse = False

            # Current bot loses if the response is bad
            if not okayResponse:
                game_state, current_hands = endRound("error_bad_response", game_state, current_hands, bot_index, bot_index)
                gameEngine_socket.send_multipart([
                    b'', 
                    b'PrintToBot',
                    player_uuids[game_state['bot_index']],
                    f"Bad response: {json.dumps(response)}".encode('utf-8')
                ])

            # if call, calculate if it is correct
            elif response['response_type'] == 'call':
                dice_sums = np.sum(np.array(current_hands), axis=0)
                
                # Add ones if wild
                if game_state['wild_ones']:
                    dice_sums[1:] += dice_sums[0]
                
                bidRealValue = dice_sums[game_state['bid'][1]-1] # subtract 1 for zero indexing
                # actually check if bid was legitimate
                if bidRealValue >= game_state['bid'][0]:
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
            game_state, current_hands = endRound("error_timeout", game_state, current_hands, bot_index, bot_index)

        # Break if only one bot remains
        if sum(game_state['dice_counts']) == max(game_state['dice_counts']):
            break
        
        # Timeout if exceeded tourney timeout
        if (time.time() - start_time)*1000 > server_config['game_timeout_mS']:
            print(f"CRITICAL: GAME ENGINE EXCEEDED TIMEOUT. Game state:{game_state}")
            return

    # Add winner to rankings
    game_state["bot_rankings"].append(game_state['bot_index'])
    game_state["bot_rankings"].reverse() # Index 0 is winner and so on

    # Build game log
    game_log = {
        "game_history": game_state['round_history'],
        "bot_rankings": game_state["bot_rankings"],

        "bot_count": len(player_uuids),
        "dice_count": dice_count,
        "wild_ones_drop": do_drop_wilds, 

        "bot_uuids": [str(foo.decode()) for foo in player_uuids],
        "game_uuid": game_uuid,
        "tourney_uuid": tourney_uuid,

        "start_time": start_timestamp,
        "end_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "ping_averages_mS": [1000*np.average(arr) if len(arr) > 0 else 0 for arr in ping_times],
        "ping_maximums_mS": [1000*np.max(arr) if len(arr) > 0 else 0 for arr in ping_times]
    }

    # Send game log
    gameEngine_socket.send_multipart([
        b'', 
        b'GameLog',
        json.dumps(game_log).encode('utf-8')
    ])

    return

def tourneyLogsThread(context, server_config):
    # Init receiving communications for logs
    log_socket = context.socket(zmq.SUB)
    log_socket_path = f"tcp://localhost:{server_config['logs_port']}"
    log_socket.connect(log_socket_path)
    log_socket.setsockopt(zmq.SUBSCRIBE, b"")

    poller = zmq.Poller()
    poller.register(log_socket, zmq.POLLIN)

    log_path = Path(server_config['logs_path'])
    os.makedirs(log_path / "json" / "clients", exist_ok=True)
    os.makedirs(log_path / "json" / "tournies", exist_ok=True)
    
    while True:
        socks = dict(poller.poll(100)) # 100ms timeout so we will start tournament even if every bot is connected

        # Timeout happened, ignore
        if len(socks) == 0:
            continue
        # Handle bad messages
        elif log_socket not in socks and socks[log_socket] != zmq.POLLIN:
            print(f"Failed to handle {socks}")
        # Log message
        else:
            messageType, *messageData = log_socket.recv_multipart()

            if messageType == b'RegisterBot':
                msg_data = json.loads(messageData[0])
                json.dump(msg_data, open(log_path / "json" / "clients" / f"{msg_data['session_uuid']}.json", 'w'), indent='\t')
            elif messageType == b'TourneyLog':
                msg_data = json.loads(messageData[0])
                json.dump(msg_data, open(log_path / "json" / "tournies" / f"{str(msg_data['tourney_index']).rjust(8, '0')}_{msg_data['tourney_uuid']}.json", 'w'), indent='\t')
            elif messageType == b'GameLog':
                # We are only logging tourney logs now
                pass
                # msg_data = json.loads(messageData[0])
                # json.dump(msg_data, open(log_path / "json" / "games" / f"{msg_data['tourney_uuid']}_{msg_data['game_uuid']}.json", 'w'), indent='\t')
            else:
                print(f"Invalid message type received on log_socket: {messageType}")
                continue

def runServer(server_config):
    # Init everything
    
    lastTourneyTime = time.time() # Init time of last tourney to current time


    # Init ZMQ router
    context = zmq.Context.instance()

    # Init communication with bots
    bot_socket = context.socket(zmq.ROUTER)
    bot_socket.bind(f"tcp://*:{server_config['game_port']}")

    # Init broadcast communications for logs
    broadcast_socket = context.socket(zmq.PUB)
    broadcast_socket.bind(f"tcp://*:{server_config['logs_port']}")

    # Init internal game communication
    gameEngine_socket = context.socket(zmq.ROUTER)
    gameEngine_socket.bind(f"inproc://game_engine")

    # Poller to handle both network comms and game comms
    poller = zmq.Poller()
    poller.register(bot_socket, zmq.POLLIN)
    poller.register(gameEngine_socket, zmq.POLLIN)

    # Kick off logger thread
    print(f"Starting log broadcaster")
    log_broadcaster = threading.Thread(
                target=tourneyLogsThread, 
                args=[context, server_config],
                name=f"log_broadcaster",
                daemon=True
            )
    log_broadcaster.start()
    
    print(f"Starting log ingestor")
    log_ingestor = threading.Thread(
                target=process_logs.log_ingestor_threads(), 
                args=["fjaksdlfjskadlf"],
                name=f"log_ingestor",
                daemon=True,
            )
    log_ingestor.start()

    # List of clients that are active
    clients = {}
    tourney_idx = -1
    last_ping_time = time.time()
    
    # Giant loop to run tourneys repeatedly
    while True:
        # Set minimum time gap between tourneys
        if time.time() > lastTourneyTime + server_config['tourney_freq_S'] - server_config['tourney_min_gap_S']:
            print(f"Tourney ran over time, setting mandatory {server_config['tourney_min_gap_S']} second gap")
            lastTourneyTime = time.time() + server_config['tourney_min_gap_S']

        # Loop receiving new connections until new tourney starts
        pings_sent = False
        while time.time() < lastTourneyTime + server_config['tourney_freq_S'] or not pings_sent:
            socks = dict(poller.poll(100)) # 100ms timeout so we will start tournament even if every bot is connected

            # Ping all bots 1 second before tourney starts
            # Because we only time out when the server starts, 
            if not pings_sent and time.time() > lastTourneyTime + server_config['tourney_freq_S'] - 1.0:
                pings_sent = True
                last_ping_time = time.time()
                for id in list(clients.keys()):
                    bot_socket.send_multipart([id, b'', b'Ping'])


            # Timeout happened, ignore
            if len(socks) == 0:
                continue
            # Handle incoming registrations from bots
            elif bot_socket in socks and socks[bot_socket] == zmq.POLLIN:                    
                messageIdentity, _, messageType, *messageData = bot_socket.recv_multipart()

                if messageType == b'RegisterBot':
                    botRegistration(clients, messageIdentity, messageData[0], broadcast_socket)
                elif messageType == b'Ping':
                    # Ping message is to just make sure bot is still online
                    clients[messageIdentity]['last_ping'] = time.time()
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
        for id in list(clients.keys()):
            data = clients[id]
            if data['last_ping'] < last_ping_time:
                print(f"Deleting timed out bot {id} : {data['metadata']['full_title']}")
                del clients[id]            

        # Update last tourney time even if we don't have enough connections to run a game
        lastTourneyTime = time.time()

        # Make sure we have enough bots
        if len(clients) < server_config['player_count'][0]:
            print(f"Not enough clients to start tourney ({len(clients)})")
            continue
        
        tourney_idx += 1
        tourney_client_uuids = list(clients.keys())
        tourney_uuid = str(uuid.uuid4())
        tourney_start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n\nStarting tourney {tourney_idx} with {len(clients)} bots")

        
        # Kick off game engines
        game_threads = []
        game_logs = []
        # Calculate how many games to start
        game_sizes = server_config['player_count']
        min_players = game_sizes[0]
        max_players = max(game_sizes[0], game_sizes[1])
        players_per_game = np.average(np.array(np.arange(min_players, max_players+1), dtype=np.float16))
        game_count = int(np.ceil(server_config['games_per_tourney_per_bot'] * len(clients) / players_per_game))
        print(f"Kicking off {game_count} games")
        bot_uuids = list(clients.keys())
        game_processes_live = game_count
        for i in range(game_count):
            # Get new set of bots
            nextGameCount = random.randint(server_config['player_count'][0], min(len(clients), server_config['player_count'][1]))
            game_bot_uuids = random.sample(bot_uuids, nextGameCount)
            game_bot_uuids = deepcopy(game_bot_uuids)
            random.shuffle(game_bot_uuids)
            t = threading.Thread(
                target=GameEngineThread, 
                args=[context, server_config['dice_count'], server_config['do_drop_wilds'], game_bot_uuids, tourney_uuid, server_config['move_timeout_mS']],
                name=f"GameEngine_{i}",
                daemon=True
            )
            t.start()
            game_threads.append(t)

        # Handle re-routing ZMQ messages to engines
        # Wait for all games to return or hang
        while game_threads_live > 0:
            socks = dict(poller.poll(100)) # 100ms timeout so we will start tournament even if every bot is connected

            # Timeout hit, check to make sure all games threads are still live
            if len(socks) == 0:
                # Check for live game threads
                game_threads_live = 0
                for t in game_threads:
                    if t.is_alive():
                        game_threads_live += 1
                if game_threads_live == 0:
                    print("WARNING All game threads returned without full logs")
                    # We timed out despite all games having returned. This should not happen
                    break
                else:
                    print(f"{game_threads_live} live threads")
            
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
                    print(f"Invalid message type received on gameEngine_socket: {messageType}")
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

                elif messageType == b'PrintToBot':
                    bot_socket.send_multipart([messageData[0], b'', b'Print', messageData[1]])
                else:
                    print(f"Invalid message type received on broadcast_socket: {messageType}")
                    continue

            # Something is afoot
            else:
                print(f"Failed to handle {socks}")

            # Break if all games have returned
            if len(game_logs) == game_count:
                break

        print(f"Tourney complete")

        # Parse game logs
        game_logs = [json.loads(log) for log in game_logs] # Load game logs as json
        bot_uuid_str = [foo.decode() for foo in tourney_client_uuids]
        
        results_by_bot = {foo:[[], []] for foo in bot_uuid_str}
        for log in game_logs:
            for botIdx, fooUuid in enumerate(log['bot_uuids']):
                results_by_bot[fooUuid][0].append(log['bot_rankings'][botIdx])
                results_by_bot[fooUuid][1].append(log['bot_count'])
        full_names = [clients[fooUuid]['metadata']['full_title'] for fooUuid in bot_uuids]

        # Score games
        tourney_score = [0.0 for _ in bot_uuids]
        if server_config['scoring_method'] == '531':
            # 531 scoring is first gets 5 points, second 3, and third 1
            for botIdx, fooUuid in enumerate(bot_uuid_str):
                rankings = np.array(results_by_bot[fooUuid][0])
                tourney_score[botIdx] += 5*len(np.where(rankings == 0)[0])
                tourney_score[botIdx] += 3*len(np.where(rankings == 1)[0])
                tourney_score[botIdx] += 1*len(np.where(rankings == 2)[0])
        elif server_config['scoring_method'] == 'even':
            for botIdx, fooUuid in enumerate(bot_uuid_str):
                rankings = np.array(results_by_bot[fooUuid])
                # Flip so first gets 1 point, last gets 0, and the spread is even between them
                rankings[1] -= 1 # 
                tourney_score[botIdx] = np.sum((rankings[1] - rankings[0]) / rankings[1])
        else:
            print(f"ERROR: Scoring method {server_config['scoring_method']} does not exist")
        
        # Add score mult
        tourney_score = [score * server_config['score_mult'] for score in tourney_score]

        # Get score for each player
        player_name_match = np.array([clients[fooUuid]['metadata']['player'] for fooUuid in tourney_client_uuids])
        player_scores = {}
        for name, count in zip(*np.unique(player_name_match, return_counts=True)):
            if count > server_config['max_bots_per_player']:
                print(f"HEADS UP: Player {name} is running {count} bots. No points awarded")
                warning_message = f"YOU ARE RUNNING {count} BOTS AND THUS SCORING NO POINTS. MAX BOTS IS {server_config['max_bots_per_player']}"
                for bot in np.array(bot_uuids)[np.where(player_name_match == name)[0]]:
                    bot_socket.send_multipart([
                        bot,
                        b'',
                        b'Print',
                        warning_message.encode('utf-8'),
                    ])
                player_scores[name] = 0
            else:
                scores = np.array(tourney_score)[player_name_match == name]
                player_scores[name] = np.max(scores)
                print(f"{name} score {scores}")

        # Generate tourney logs
        tourney_logs = {
            "tourney_tag": server_config['tourney_tag'],
            "tourney_game_count": game_count,
            "scoring_method": server_config['scoring_method'],
            "score_multiplier": server_config['score_mult'],

            "results_by_bot": results_by_bot,
            "bot_fullnames": full_names,
            "bot_player": [clients[fooUuid]['metadata']['player'] for fooUuid in bot_uuids],
            "bot_name": [clients[fooUuid]['metadata']['name'] for fooUuid in bot_uuids],
            "bot_version": [clients[fooUuid]['metadata']['version'] for fooUuid in bot_uuids],
            "bot_scores": tourney_score,
            "bot_count": len(bot_uuids),

            "start_time": tourney_start_time,
            "end_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "tourney_uuid": tourney_uuid,
            "tourney_index": tourney_idx,
            "bot_uuids": bot_uuid_str,
            "game_uuids": [log['game_uuid'] for log in game_logs],
            "game_logs": game_logs,
        }           

        # Send responses to logger
        broadcast_socket.send_multipart([
            b'TourneyLog',
            json.dumps(tourney_logs).encode('utf-8')
        ])

        # Send summary to client
        scoreRanking = np.argsort(tourney_score)[::-1]
        for idx, fooUuid in enumerate(bot_uuids):
            player_score = player_scores[player_name_match[idx]]
            bot_rank = np.where(scoreRanking == idx)[0][0]
            
            addComplement = ""
            if bot_rank == 0: addComplement = " (nice!)"
            printStatement = f"Placed {bot_rank+1}/{len(tourney_client_uuids)}{addComplement}, scoring {tourney_score[idx]: 3.3f} points"
            bot_socket.send_multipart([
                fooUuid,
                b'',
                b'Print',
                printStatement.encode('utf-8'),
            ])

        # Repeat

runServer(server_config)