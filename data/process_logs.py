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

def file_ingestor_thread(folder_path, output_path, process_func, save_func):
    last_read_time = time.time()
    data_object = None

    # Initial object loads
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            file_path = os.path.join(root, file)
            data_object = process_func(file_path, data_object)
            print(f"Initial Injestion: {file_path}")
    save_func(data_object, output_path)

    # Loop reloading objects
    while True:
        new_max_read_time = last_read_time
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                file_mtime = os.path.getmtime(file_path)
                if file_mtime > last_read_time:
                    data_object = process_func(file_path, data_object)
                    print(f"New File: {file_path}")
                    if file_mtime > new_max_read_time:
                        new_max_read_time = file_mtime
        if new_max_read_time > last_read_time:
            save_func(data_object, output_path)
            last_read_time = new_max_read_time
        time.sleep(0.5)

def update_client_json(file_path, data_object):
    new_data = pd.DataFrame([json.load(open(file_path, 'r'))])
    if data_object is not None:
        # Return merged dataframes if none
        return pd.merge(data_object, new_data, 'outer')
    else:
        # Return raw data if new
        return new_data

def save_jsons_to_parquet(data_object, output_path):
    if data_object is not None:
        data_object.to_parquet(output_path+'.tmp')
        shutil.move(output_path+'.tmp', output_path)


# file_ingestor_thread('logs/json/clients', 'logs/client.parquet', update_client_json, save_jsons_to_parquet)
print(f"Starting client_logger_thread")
client_logger_thread = threading.Thread(
            target=file_ingestor_thread, 
            args=['logs/json/clients', 'logs/client.parquet', update_client_json, save_jsons_to_parquet],
            name=f"client_logger_thread",
            daemon=True
        )
client_logger_thread.start()

while True:
    time.sleep(3)
    data = pd.read_parquet('logs/client.parquet')
    # data = pd.read_parquet(open('logs/client.parquet', 'rb'))
    print(data)
    del data

