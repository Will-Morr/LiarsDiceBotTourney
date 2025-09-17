# Log aggregator
# Injests client and tourney jsons converts them to parquet files

import json
import argparse
import numpy as np
import pandas as pd
from copy import deepcopy
from pathlib import Path
import os
import time
import threading
import shutil
from datetime import datetime
import subprocess

def file_ingestor_thread(folder_path, output_path, process_func, save_func, silence):
    last_read_time = time.time()
    data_object = None

    ingested_files = []
    # Initial object loads
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            file_path = os.path.join(root, file)
            if not silence: print(f"Initial Injestion: {file_path}")
            ingested_files.append(file_path)
            data_object = process_func(file_path, data_object)
    save_func(data_object, output_path)

    # Loop reloading objects
    while True:
        newFiles = False
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                if file_path not in ingested_files and not is_file_open_lsof(file_path):
                    if not silence: print(f"New File: {file_path}")
                    data_object = process_func(file_path, data_object)
                    ingested_files.append(file_path)
                    newFiles = True
        if newFiles:
            save_func(data_object, output_path)
        time.sleep(0.5)


def is_file_open_lsof(filepath):
    """Check if file is open using lsof command"""
    result = subprocess.run(['lsof', filepath], 
                            capture_output=True, 
                            text=True, 
                            check=False)
    return len(result.stdout.strip()) > 0
    
def load_client_json(file_path, data_object):
    # Rename session uuid
    # This is a quick hack to avoid a refactor that would touch players existing bots
    new_client = json.load(open(file_path, 'r'))
    new_client['bot_uuid'] = new_client['session_uuid']
    del new_client['session_uuid']

    new_data = pd.DataFrame([new_client])

    if data_object is not None:
        # Return merged dataframes if none
        return pd.merge(data_object, new_data, how='outer')
    else:
        # Return raw data if new
        return new_data

def save_jsons_to_parquet(data_object, output_path):
    if data_object is not None:
        data_object.to_parquet(str(output_path)+'.tmp')
        shutil.move(str(output_path)+'.tmp', output_path)

def get_timestamp(timestamp):
    return datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')

def load_tourney_json(file_path, data_object):
    data = json.load(open(file_path, 'r'))
    # Build tourney table
    tourney_data = {
        'tourney_tag': [data['tourney_tag']],
        'tourney_game_count': [data['tourney_game_count']],
        'scoring_method': [data['scoring_method']],
        'score_multiplier': [data['score_multiplier']],
        'start_time': [get_timestamp(data['start_time'])],
        'end_time': [get_timestamp(data['end_time'])],
        'tourney_uuid': [data['tourney_uuid']],
        'tourney_index': [data['tourney_index']],
        'tourney_bot_count': [data['bot_count']]
    }
    tourney_data = pd.DataFrame(tourney_data)

    # Bot data
    tourney_results = []
    for i, (bot_uuid, scores) in enumerate(data['results_by_bot'].items()):
        tourney_results.append({
            'tourney_uuid': data['tourney_uuid'],
            'bot_uuid': bot_uuid,
            'bot_fullname': data['bot_fullnames'][i],
            'bot_player': data['bot_player'][i],
            'bot_name': data['bot_name'][i],
            'bot_version': data['bot_version'][i],
            'final_score': data['bot_scores'][i],
            'game_scores': scores[0],  # First array is game scores
            'game_rankings': scores[1]  # Second array is rankings
        })
    tourney_results = pd.DataFrame(tourney_results)

    # Log game metadata
    game_data = []
    for i, game_log in enumerate(data['game_logs']):
        game_data.append({
            'tourney_uuid': data['tourney_uuid'],
            'game_uuid': data['game_uuids'][i],
            'game_index': i,
            'bot_count': game_log['bot_count'],
            'dice_count': game_log['dice_count'],
            'wild_ones_drop': game_log['wild_ones_drop'],
            'start_time': get_timestamp (game_log['start_time']),
            'end_time': get_timestamp   (game_log['end_time']),
            'total_rounds': len(game_log['game_history']),
            'final_rankings': str(game_log['bot_rankings'])  # Store as string for now
        })
    game_data = pd.DataFrame(game_data)

    # Every move's results and each bot's game logs by tourney
    move_results = []
    game_results = []
    game_hands = []
    for i, game_log in enumerate(data['game_logs']):
        # Iterate through rounds in game
        for roundIdx, roundLog in enumerate(game_log['game_history']):
            # Save each hand played
            for botIdx, uuid in enumerate(game_log['bot_uuids']):
                handDict = {
                    'bot_uuid': uuid,
                    'game_uuid': game_log['game_uuid'],
                    'round_index': roundIdx,
                }
                handDict |= {str(i): j for i, j in zip(range(1,7), roundLog['face_counts'][botIdx])}
                game_hands.append(handDict)
            
            # Iterate through all bids except for final bid
            wild_ones = True
            is_first_go_around = True
            first_bot_index = 0
            if len(roundLog['bid_history']) > 0: first_bot_index = roundLog['bid_history'][0][2]
            for bidIdx, bid in enumerate(roundLog['bid_history'][:-1]):
                if bidIdx == 0:
                    first_bot_index = bid[2]
                elif is_first_go_around:
                    if bid[1] == 1:
                        wild_ones = False
                    if bid[2] == first_bot_index:
                        is_first_go_around = False

                move_results.append({
                        'game_uuid': game_log['game_uuid'],
                        'round_index': roundIdx,
                        'bid_index': bidIdx,
                        'bot_uuid': game_log['bot_uuids'][bid[2]],
                        'result': "uncalled_bid",
                        'bid_count': bid[0],
                        'bid_face': bid[1],
                        'wild_ones': wild_ones,
                })

            # Save final move
            move_results.append({
                'game_uuid': game_log['game_uuid'],
                'round_index': roundIdx,
                'bid_index': len(roundLog['bid_history']), # Index is number of bids + 1
                'bot_uuid': game_log['bot_uuids'][roundLog['calling_player']],
                'result': roundLog['result'],
                'bid_count': None,
                'bid_face': None,
                'wild_ones': wild_ones,
            })

            finalBidIdx = len(roundLog['bid_history'])-1

            # Do not log final bid if the game was called instantly
            if finalBidIdx < 0:
                continue

            # Set final bid's result by if it was called and if it was true
            final_bid_result = 'uncalled_bid'
            if roundLog['result'] == 'good_call': final_bid_result = 'bad_bid'
            if roundLog['result'] == 'bad_call': final_bid_result = 'good_bid'

            # Save final bid result
            finalBid = roundLog['bid_history'][-1]
            move_results.append({
                'game_uuid': game_log['game_uuid'],
                'round_index': roundIdx,
                'bid_index': finalBidIdx,
                'bot_uuid': game_log['bot_uuids'][finalBid[2]],
                'result': final_bid_result,
                'bid_count': finalBid[0],
                'bid_face': finalBid[1],
                'wild_ones': wild_ones,
            })


        for botIdx, uuid in enumerate(game_log['bot_uuids']):
            game_results.append({
                'bot_uuid': uuid,
                'game_uuid': game_log['game_uuid'],
                'turn_placement': botIdx,
                'bot_ranking': game_log['bot_rankings'][botIdx],
                'ping_average_mS': game_log['ping_averages_mS'][botIdx],
                'ping_maximum_mS': game_log['ping_maximums_mS'][botIdx],
            })
    game_results = pd.DataFrame(game_results)
    move_results = pd.DataFrame(move_results)
    game_hands = pd.DataFrame(game_hands)

    # Make new set of dataframes to log
    # The filename is set by this arg
    new_dataframes = {
        'tourney': tourney_data,
        'game': game_data,
        'tourney_results': tourney_results,
        'game_results': game_results,
        'move_results': move_results,
        'hands': game_hands,
    }

    if data_object is not None:
        # Return merged dataframes if none
        for col in data_object:
            data_object[col] = pd.concat([data_object[col], new_dataframes[col]])
        return data_object
    else:
        # Return raw data if new
        return new_dataframes

def save_tourney_parquets(data_object, output_path):
    if data_object is None:
        return
    # Save dataframe to temp file
    for key, val in data_object.items():
        val.to_parquet(os.path.join(output_path, key+'.parquet')+'.tmp')
    # Move all at once to keep in sync
    for key, val in data_object.items():
        filepath = os.path.join(output_path, key+'.parquet')
        shutil.move(filepath+'.tmp', filepath)

# # Test tourney thread
# file_ingestor_thread('logs/json/tournies', 'logs', load_tourney_json, save_tourney_parquets)
# exit()
def log_ingestor_threads(output_path = Path('logs'), silence = True):
    if not silence: print(f"Starting client_logger_thread")
    client_logger_thread = threading.Thread(
                target=file_ingestor_thread, 
                args=['logs/json/clients', output_path / 'client.parquet', load_client_json, save_jsons_to_parquet, silence],
                name=f"client_logger_thread",
                daemon=True
            )
    client_logger_thread.start()

    if not silence: print(f"Starting tourney_logger_thread")
    tourney_logger_thread = threading.Thread(
                target=file_ingestor_thread, 
                args=['logs/json/tournies', output_path, load_tourney_json, save_tourney_parquets, silence],
                name=f"tourney_logger_thread",
                daemon=True
            )
    tourney_logger_thread.start()

if __name__ == '__main__':
    # Test client handler
    if False:
        file_ingestor_thread('logs/json/clients', Path('logs') / 'client.parquet', load_client_json, save_jsons_to_parquet, False)
    
    # Test tourney handler
    if False:
        file_ingestor_thread('logs/json/tournies', Path('logs'), load_tourney_json, save_tourney_parquets, False)



    log_ingestor_threads(silence = False)

    # Main thread sleeps forever
    while True: time.sleep(10)