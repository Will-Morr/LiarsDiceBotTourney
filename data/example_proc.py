
import os
import pandas as pd
from pathlib import Path

import matplotlib.pyplot as plt
plt.style.use('dark_background')

last_read_time = 0

log_path = Path('logs')

tourney = pd.read_parquet(log_path / 'tourney.parquet')
game = pd.read_parquet(log_path / 'game.parquet')
tourney_results = pd.read_parquet(log_path / 'tourney_results.parquet')
game_results = pd.read_parquet(log_path / 'game_results.parquet')
move_results = pd.read_parquet(log_path / 'move_results.parquet')
hands = pd.read_parquet(log_path / 'hands.parquet')
client = pd.read_parquet(log_path / 'client.parquet')

# Print all columns in 
dataframes = {'tourney':tourney, 'game':game, 'tourney_results':tourney_results, 'game_results':game_results, 'move_results':move_results, 'hands':hands, 'client':client}
for name, df in dataframes.items():
    print(f"\n{name} columns:")
    for col in df.columns:
        print(f"   {col.ljust(18, ' ')} : {type(df[col].dtype)}") 

import numpy as np
print(np.unique(move_results['wild_ones'], return_counts=True))

# Get just UUID and result
just_results = move_results[['bot_uuid', 'result']]
# Merge with client to get full names
just_results = just_results.merge(client[['full_title', 'bot_uuid']], 'left', on='bot_uuid')
# Crosstab makes an array that pure results
move_results_by_bot = pd.crosstab(just_results['full_title'], just_results['result'])
print(move_results_by_bot)

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



#     # print(bot_result)
#     # print(tourney)

# print(tourney['tourney_index'])

# bot_result = bot_result.merge(tourney[['tourney_uuid','tourney_index','start_time']], on='tourney_uuid', how='outer')
# bot_result = bot_result.sort_values('start_time')

# bot_result["print_name"] = bot_result['bot_name'] + ' ' + bot_result['bot_player']

# for name, subdf in bot_result.groupby('print_name'):
#     plt.plot(subdf['tourney_index'], subdf['final_score'].cumsum(), label = name)
#     plt.xlabel("Tournies")
#     plt.ylabel("Sum Score")

# plt.legend()
# plt.show()