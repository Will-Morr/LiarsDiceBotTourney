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

plot_path = Path('plots')
os.makedirs(plot_path, exist_ok=True)

def game_game_matchups(df):
    # Get matrix of which bots played which the most
    just_bot_ranks = df[['bot_uuid', 'game_uuid', 'bot_ranking']] # Just get the two rows we care about
    just_bot_ranks = just_bot_ranks.merge(client[['full_title', 'bot_uuid']], 'left', on='bot_uuid') # Join on real name
    just_bot_ranks = just_bot_ranks[['full_title', 'game_uuid', 'bot_ranking']] # Drop uuid
    bots_by_placement = just_bot_ranks.groupby('full_title')['bot_ranking'].mean().sort_values() # Get rank
    bot_order = np.array(bots_by_placement.index) # Get array of strings
    bot_counts = pd.Series(bot_order).map(dict(zip(*np.unique(just_bot_ranks['full_title'], return_counts=True))))

    match_counts = np.zeros([len(bot_order), len(bot_order)], dtype=np.uint16)
    win_counts = np.zeros([len(bot_order), len(bot_order)], dtype=np.uint16)

    for idx, bot_name in enumerate(bot_order):
        # Get dataframe of games we were in vs games we were not
        bot_ranks = just_bot_ranks[just_bot_ranks['full_title'] == bot_name]
        other_ranks = just_bot_ranks[just_bot_ranks['full_title'] != bot_name]
        comparisons = bot_ranks.merge(other_ranks, 'left', on='game_uuid', suffixes=['', '_match'])
        # Get count of total matchups and games were bot placed higher
        games = comparisons.groupby('full_title_match').count()
        wins = comparisons[comparisons['bot_ranking'] < comparisons['bot_ranking_match']].groupby('full_title_match').count()
        # Map so that values are in same order as bot_order to add to matrix, where empty rows are 0
        game_counts = pd.Series(bot_order).map(games['bot_ranking_match'].to_dict()).fillna(0).astype(int)
        game_wins = pd.Series(bot_order).map(wins['bot_ranking_match'].to_dict()).fillna(0).astype(int)
        # Save row to matrix
        match_counts[idx] = game_counts
        win_counts[idx] = game_wins

    # Get win ratio
    dummy_match_counts = match_counts
    dummy_match_counts[dummy_match_counts == 0] = 1
    win_ratio = win_counts / dummy_match_counts
    # Set middle values to Nan
    win_ratio[np.arange(win_ratio.shape[0]), np.arange(win_ratio.shape[0])] = np.nan
    win_ratio *= 100

    return win_ratio, bot_order

def plotHeatMap(data, xlabel, ylabel, title='', rot=-90):
    fig = plt.figure(figsize=(12, 8))
    plt.title(title)
    # fig.tight_layout(rect=[0.0, 0.1, 1, 0.95])
    # plt.subplot(1, 2, 1)
    im = plt.imshow(data, cmap='inferno', aspect='auto') #, vmin=np.nanmin(data)-0.2, vmax=np.nanmax(data))

    # Add text labels
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            if np.isnan(data[i, j]):
                continue
            text = plt.text(
                j, i,
                # f'{np.int32(data[i, j])}',
                f'{np.round(data[i, j],1): 2.1F}',
                ha="center", va="center", 
                color='black' if data[i, j] > np.nanmin(data) + 10 else 'white',
                fontsize=8,
                # fontweight='bold',
            )
    plt.colorbar(im)
    plt.xticks(range(len(xlabel)), xlabel, rotation=rot)
    plt.yticks(range(len(ylabel)), ylabel)
    plt.tight_layout()



def score_by_column(df, sort_column, title='', rot=0):
    bot_names_ordered = np.array(df.groupby('full_title')['score'].mean().sort_values().index)
    bot_names_ordered = np.flip(bot_names_ordered)
    sort_values = np.array(df.groupby(sort_column)[sort_column].mean().sort_values().index)

    score_array = np.zeros([len(bot_names_ordered), len(sort_values)], dtype=np.float32)
    for idx, bot_name in enumerate(bot_names_ordered):
        bot_scores = df[df['full_title'] == bot_name]
        scores_by_count = bot_scores[[sort_column, 'score']].groupby(sort_column).mean()
        game_counts = pd.Series(sort_values).map(scores_by_count['score'].to_dict()).fillna(0.0)
        score_array[idx] = game_counts

    score_array = np.round(100*score_array, 1)

    plotHeatMap(score_array, sort_values, bot_names_ordered, title, rot)



just_bot_ranks = game_results[['bot_uuid', 'game_uuid', 'bot_ranking', 'turn_placement']] # Just get the two rows we care about
just_bot_ranks = just_bot_ranks.merge(client[['full_title', 'bot_uuid']], 'left', on='bot_uuid') # Join on real name
just_bot_ranks = just_bot_ranks.merge(game[['game_uuid', 'bot_count']], 'left', on='game_uuid') # Join game data
just_bot_ranks['score'] = 1.0 - (just_bot_ranks['bot_ranking'] / (just_bot_ranks['bot_count']-1))

score_by_column(just_bot_ranks, 'bot_count', f"Average score by number of bots in game (100 is first, 0 is last)", rot=0)
plt.savefig(plot_path / 'average_scores_by_game_size.png')

for player_count in np.unique(just_bot_ranks['bot_count']):
    score_by_column(just_bot_ranks[just_bot_ranks['bot_count'] == player_count], 'turn_placement', f"Average score by turn index in {player_count} player games (100 is perfect, 0 is last every time)", rot=0)
    plt.savefig(plot_path / f"Score_by_starting_position_for_{player_count}_players.png")

# Heat map of matchups
win_ratio, bot_order = game_game_matchups(game_results)
plotHeatMap(win_ratio, bot_order, bot_order, f"Matchup Win Rates")
plt.savefig(plot_path / 'Matchups_overall.png')

# Match-ups by game size
game_results = game_results.merge(game[['game_uuid', 'bot_count']], on='game_uuid')
for idx in range(6, 2, -1):
    game_subset = game_results[game_results['bot_count'] == idx]
    win_ratio, bot_order = game_game_matchups(game_subset)
    plotHeatMap(win_ratio, bot_order, bot_order, f"Matchup Win Rates for games with {idx} bots")
    plt.savefig(plot_path / f"Matchups_size_{idx}.png")
