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

def file_ingestor_thread(folder_path, output_path, process_func, save_func):
    last_read_time = time.time()
    data_object = None

    ingested_files = []
    # Initial object loads
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            file_path = os.path.join(root, file)
            print(f"Initial Injestion: {file_path}")
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
                    print(f"New File: {file_path}")
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
    new_data = pd.DataFrame([json.load(open(file_path, 'r'))])

    if data_object is not None:
        # Return merged dataframes if none
        return pd.merge(data_object, new_data, how='outer')
    else:
        # Return raw data if new
        return new_data

def save_jsons_to_parquet(data_object, output_path):
    if data_object is not None:
        data_object.to_parquet(output_path+'.tmp')
        shutil.move(output_path+'.tmp', output_path)

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
    bot_data = []
    for i, (bot_uuid, scores) in enumerate(data['results_by_bot'].items()):
        bot_data.append({
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
    bot_data = pd.DataFrame(bot_data)

    # Game data
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

    # Build move table TODO


    # Make new set of dataframes to log
    # The filename is set by this arg
    new_dataframes = {
        'tourney': tourney_data,
        'bot_result': bot_data,
        'game': game_data,
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
def main():
    print(f"Starting client_logger_thread")
    client_logger_thread = threading.Thread(
                target=file_ingestor_thread, 
                args=['logs/json/clients', 'logs/client.parquet', load_client_json, save_jsons_to_parquet],
                name=f"client_logger_thread",
                daemon=True
            )
    client_logger_thread.start()

    print(f"Starting tourney_logger_thread")
    tourney_logger_thread = threading.Thread(
                target=file_ingestor_thread, 
                args=['logs/json/tournies', 'logs', load_tourney_json, save_tourney_parquets],
                name=f"tourney_logger_thread",
                daemon=True
            )
    tourney_logger_thread.start()

    # Main thread sleeps forever
    while True: time.sleep(10)

if __name__ == '__main__':
    main()