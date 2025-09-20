import os
import pandas as pd
from pathlib import Path
import numpy as np

import matplotlib.pyplot as plt
plt.style.use('dark_background')

# Load all log tables
log_path = Path('logs')

tourney = pd.read_parquet(log_path / 'tourney.parquet')
game = pd.read_parquet(log_path / 'game.parquet')
tourney_results = pd.read_parquet(log_path / 'tourney_results.parquet')
game_results = pd.read_parquet(log_path / 'game_results.parquet')
move_results = pd.read_parquet(log_path / 'move_results.parquet')
hands = pd.read_parquet(log_path / 'hands.parquet')
client = pd.read_parquet(log_path / 'client.parquet')

# Print all columns in each dataframe
dataframes = {'tourney':tourney, 'game':game, 'tourney_results':tourney_results, 'game_results':game_results, 'move_results':move_results, 'hands':hands, 'client':client}
for name, df in dataframes.items():
    print(f"\n{name} columns:")
    for col in df.columns:
        print(f"   {col.ljust(18, ' ')} : {type(df[col].dtype)}")




# Print the count of each move result for every bot

# Get just UUID and result
just_results = move_results[['bot_uuid', 'result']]
# Merge with client to get full names
just_results = just_results.merge(client[['full_title', 'bot_uuid']], 'left', on='bot_uuid')
# Crosstab makes an array that pure results
move_results_by_bot = pd.crosstab(just_results['full_title'], just_results['result'])

# Overthinking a table plotter there's definitely a one liner for this
rows = ['uncalled_bid', 'good_bid', 'bad_bid', 'good_call', 'bad_call', 'error_bad_response', 'error_lower_count', 'error_increase_count', 'error_overflow', 'error_timeout', ]
for foo in rows:
    if foo not in move_results_by_bot:
        move_results_by_bot[foo] = 0
top_cols = [' ', '|', 'bid', ' ', ' ', '|', 'call', ' ', '|', 'error', ' ', ' ', ' ', ' ', '|   ']
second_cols = [' ', '|', 'uncalled', 'good', 'bad', '|', 'good', 'bad', '|',  'bad_response', 'lower_count', 'increase_face', 'overflow', 'timeout', '|']
print_table_rows = [top_cols, second_cols]
for name, row in move_results_by_bot.iterrows():
    print_table_rows.append([
        name,
        '|',
        row['uncalled_bid'],
        row['good_bid'],
        row['bad_bid'],
        '|',
        row['good_call'],
        row['bad_call'],
        '|',
        row['error_bad_response'],
        row['error_lower_count'],
        row['error_increase_count'],
        row['error_overflow'],
        row['error_timeout'],
        '|',
    ])

# Align columns
swapped_table = np.swapaxes(print_table_rows, 0, 1)
result = np.empty_like(swapped_table)
for i, max_len in enumerate(np.max(np.char.str_len(swapped_table), axis=1)):
    result[i] = np.char.rjust(swapped_table[i], max_len)

# Print
for foo in np.swapaxes(result, 0, 1):
    print(' '.join(foo))
