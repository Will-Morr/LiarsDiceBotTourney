import json
import argparse
import numpy as np
import pandas as pd
import zmq
from copy import deepcopy

parser = argparse.ArgumentParser()
parser.add_argument("-a", "--broadcast_address", help="Address connect to to export game logs")
parser.add_argument("-f", "--file_path", help="File to process")
parser.add_argument("-p", "--player", help="Player to filter for")
parser.add_argument("-b", "--bot", help="Bot to filter for")
parser.add_argument("-e", "--export_path", help="File to export to")
args = parser.parse_args()

def filter_indices(index_list, search_list, search_val):
    idx = 0
    while idx > len(index_list):
        if search_list[index_list[idx]] != search_val:
            del index_list[idx]
        else:
            idx += 1
    return index_list


def makeReadableGameLog(tourney_data, filter_player = None, filter_bot = None, export_path = None):
    # Filter to only specifies bots
    keep_bot_indices = [i for i in range(tourney_data['bot_count'])]
    if filter_player:
        keep_bot_indices = filter_indices(keep_bot_indices, tourney_data['bot_player'], filter_player       )
    if filter_bot:
        keep_bot_indices = filter_indices(keep_bot_indices, tourney_data['bot_name'], filter_bot)
    keep_bot_uuids = [tourney_data['bot_uuids'][i] for i in keep_bot_indices]

    full_names_match = dict(zip(tourney_data['bot_uuids'], tourney_data['bot_fullnames']))

    def print_helper(line):
        print(line)
        if export_path:
            export_path.write(line+'\n')


    for log in tourney_data['game_logs']:
        # Skip if none of our target filtered values are in the logs
        if set(log['bot_uuids']).isdisjoint(keep_bot_uuids):
            continue

        # Get full names for each bot
        full_names = [full_names_match[uuid] for uuid in log['bot_uuids']]
        max_name_len = 0
        for foo in full_names:
            if len(foo) > max_name_len:
                max_name_len = len(foo)
        max_name_len += 1

        print_helper(f"\n\n{'='*75}\n\nGame Summary:")
        print(f"Place| {'Name'.ljust(max_name_len, ' ')} | Max Ping |")
        for idx in np.argsort(log['bot_rankings']):
            print_helper(f"{log['bot_rankings'][idx]: 4d} | {full_names[idx].ljust(max_name_len)} | {log['ping_maximums_mS'][idx]: 3.1f} | ")
        
        # Iterate through games
        for round in log['game_history']:
            print_helper(f"\n{'========== New Hands:'.ljust(max_name_len)}     {'  '.join([str(i) for i in range(1, 7)])}")

            # Print hands in order
            for idx in np.argsort(log['bot_rankings']):
                faceString = ""
                for foo in round['face_counts'][idx]:
                    if foo > 0:
                        faceString += str(foo).rjust(3, ' ')
                    else:
                        faceString += '   '

                print_helper(f"{full_names[idx].ljust(max_name_len)} : {faceString}")
            print(f"========== Moves: ")
            # Print bids in order
            for count, face, idx in round['bid_history']:
                print_helper(f"Bid {count: 2d} {face} {full_names[idx].ljust(max_name_len)}")

            print_helper(f"{round['result']} {full_names[round['calling_player']].ljust(max_name_len)}")

    # Consolidate logs to print some big stats
    response_counts = dict(zip(log['bot_uuids'], [{'bid':0} for i in tourney_data['bot_uuids']]))
    df = pd.DataFrame({
        # 'bot_uuids': tourney_data['bot_uuids'],
        'full_names': tourney_data['bot_fullnames'],
        'scores': tourney_data['bot_scores'],
        'bid': [0 for i in tourney_data['bot_uuids']],
        'good_call': [0 for i in tourney_data['bot_uuids']],
        'bad_call': [0 for i in tourney_data['bot_uuids']],
    })

    for log in tourney_data['game_logs']:
        call_indices = np.array([foo['calling_player'] for foo in log['game_history']])
        call_result = np.array([foo['result'] for foo in log['game_history']])
        bids = np.concatenate([foo['bid_history'] for foo in log['game_history'] if foo['bid_history'] != []])
        
        for idx, uuid in enumerate(log['bot_uuids']):
            df_idx = np.where(np.array(tourney_data['bot_uuids']) == uuid)[0]
            # Count number of bids
            df.loc[df_idx, 'bid'] += len(np.where(bids[:, 2] == idx)[0])

            subset_result = call_result[call_indices == idx]
            for val, count in zip(*np.unique(subset_result, return_counts=True)):
                if val not in df:
                    df[val] = 0
                df.loc[df_idx, val] += count
    print(f"\n\nAggregate bot move results by frequency")
    df = df.sort_values(by=['scores'], ascending=False)
    print(df)





        # for round in log['game_history']:
        #     for count, face, idx in round['bid_history']:
                
    

        
        # if filter_player and filter_player not in log[] 


if args.export_path:
    export_file = open(args.export_path, 'w')
else:
    export_file = None

if args.file_path:
    tourney_log = json.load(open(args.file_path, 'r'))
    makeReadableGameLog(tourney_log, args.player, args.bot, export_file)

if args.broadcast_address:
# Init receiving communications for logs
    context = zmq.Context.instance()
    log_socket = context.socket(zmq.SUB)
    log_socket_path = f"tcp://{args.broadcast_address}"
    log_socket.connect(log_socket_path)
    log_socket.setsockopt(zmq.SUBSCRIBE, b"")

    poller = zmq.Poller()
    poller.register(log_socket, zmq.POLLIN)

    while True:
        socks = dict(poller.poll(1000)) # 100ms timeout so we will start tournament even if every bot is connected

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
                continue
                msg_data = json.loads(messageData[0])
                json.dump(msg_data, open(log_path / "json" / "clients" / f"{msg_data['session_uuid']}.json", 'w'), indent='\t')
            elif messageType == b'TourneyLog':
                tourney_log = json.loads(messageData[0].decode('utf-8'))
                makeReadableGameLog(tourney_log, args.player, args.bot, export_file)
            elif messageType == b'GameLog':
                # We are only logging tourney logs now
                pass
                # msg_data = json.loads(messageData[0])
                # json.dump(msg_data, open(log_path / "json" / "games" / f"{msg_data['tourney_uuid']}_{msg_data['game_uuid']}.json", 'w'), indent='\t')
            else:
                print(f"Invalid Message Type Received: {messageType}")
                continue