import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib import style
import os
import pandas as pd

import matplotlib.pyplot as plt
# plt.style.use('dark_background')

from copy import deepcopy

# fig, ax = plt.subplots(2, sharex=True)
fig, ax = plt.subplots(2)
ax1, ax2 = ax

last_read_time = 0
file_path = 'logs/tourney.parquet'


import pandas as pd
import matplotlib.pyplot as plt
import numpy as np

def plot_last_ten_tournaments(df, ax):
    """
    Plot the sum of scores from the last 10 tournaments for each player
    as a horizontal bar plot. Extrapolates for players with < 10 games.
    
    Parameters:
    -----------
    df : pandas.DataFrame
        DataFrame with columns 'bot_fullname', 'tourney_index', 'final_score'
    ax : matplotlib.axes.Axes
        Matplotlib axis object to plot on
    """
    # Get the last 10 unique tournament indices
    last_ten_tourneys = sorted(df['tourney_index'].unique())[-10:]
    
    # Filter dataframe for last 10 tournaments
    # df_last_ten = df[df['tourney_index'].isin(last_ten_tourneys)]
    
    df_last_ten = df

    # Calculate actual scores and game counts for each player
    player_stats = df_last_ten.groupby('bot_fullname').agg({
        'final_score': 'sum',
        'tourney_index': 'count'
    }).rename(columns={'tourney_index': 'games_played'})
    
    # Calculate extrapolated scores for players with < 10 games
    player_stats['extrapolated_score'] = player_stats.apply(
        lambda row: (row['final_score'] / row['games_played'] * 10) 
        if row['games_played'] < 10 else row['final_score'], 
        axis=1
    )
    
    # Sort by extrapolated score for consistent ordering
    player_stats = player_stats.sort_values('extrapolated_score')
    
    # Separate players into two groups
    full_players = player_stats[player_stats['games_played'] >= 10]
    partial_players = player_stats[player_stats['games_played'] < 10]
    
    # Plot actual scores for all players
    y_positions = np.arange(len(player_stats))
    bars_actual = ax.barh(y_positions, 
                          player_stats['final_score'].values,
                          color='steelblue', 
                        #   label='Actual Score'
                          )
    
    # Plot extrapolated portions for players with < 10 games
    if len(partial_players) > 0:
        partial_indices = [i for i, name in enumerate(player_stats.index) 
                          if name in partial_players.index]
        extrapolated_additions = [
            player_stats.loc[name, 'extrapolated_score'] - player_stats.loc[name, 'final_score']
            for name in partial_players.index
        ]
        
        bars_extrapolated = ax.barh(
            partial_indices,
            extrapolated_additions,
            left=partial_players['final_score'].values,
            color='lightgreen',
            alpha=0.7,
            # label='Extrapolated (< 10 games)'
        )
    
    # Customize the plot
    ax.set_yticks(y_positions)
    ax.set_yticklabels(player_stats.index)
    ax.set_xlabel('Total Score (Last 10 Tournaments)')
    ax.set_ylabel('Player')
    # ax.set_title('Sum of Last 10 Tournament Scores by Player')
    
    # Add value labels on the bars
    for i, (name, row) in enumerate(player_stats.iterrows()):
        # Label for actual score
        ax.text(row['final_score'], i, 
                f"{row['final_score']:.1f} ({row['games_played']}g)", 
                ha='left', va='center', fontsize=8)
        
        # Label for extrapolated score if different
        if row['games_played'] < 10:
            ax.text(row['extrapolated_score'], i, 
                    f"{row['extrapolated_score']:.1f}*", 
                    ha='left', va='center', fontsize=8, 
                    color='darkred', weight='bold')
    
    # Add legend
    # ax.legend(loc='lower right')
    
    # Adjust layout to prevent label cutoff
    ax.margins(x=0.15)
    
    return ax

def animate(i):
    tourney = pd.read_parquet('logs/tourney.parquet')
    bot_result = pd.read_parquet(
        'logs/bot_result.parquet', 
        columns=['tourney_uuid','bot_uuid','bot_fullname', 'bot_name', 'bot_player', 'final_score']
    )

    bot_result = bot_result.merge(tourney[['tourney_uuid','tourney_index','start_time']], on='tourney_uuid', how='outer')

    bot_result = bot_result.sort_values('start_time')


    ax1.cla()
    ax2.cla()

    recent_bots = bot_result[bot_result['tourney_index'] >= bot_result['tourney_index'].max()-10]
    # for name, subdf in recent_bots.groupby('print_name'):
    #     ax1.plot(subdf['tourney_index'], subdf['final_score'], label = name)

    recent_tourney_idx = bot_result['tourney_index'].max()

    print(recent_tourney_idx)

    botPlots = deepcopy(bot_result.groupby(['bot_fullname', 'tourney_index'])['final_score'].max().reset_index())
    botPlots = botPlots.sort_values('tourney_index')
    plot_last_ten_tournaments(botPlots, ax1)

    playerPlots = bot_result.groupby(['bot_player', 'tourney_index'])['final_score'].max().reset_index()
    playerPlots = playerPlots.sort_values('tourney_index')


    print(playerPlots)
    for name, subdf in playerPlots.groupby('bot_player'):
        if not recent_bots['bot_player'].isin([name]).any():
            continue

        # recent_sub_df =  subdf[subdf['tourney_index'] > recent_tourney_idx-10]
        # ax1.plot(subdf['tourney_index'], subdf['final_score'], label = name)

        ax2.plot(subdf['tourney_index'], subdf['final_score'].cumsum(), label = name)
        # ax1.scatter(subdf['tourney_index'], subdf['final_score'])

    ax1.legend(loc='upper left')
    
    # ax1.set_xlabel("Tourney Index")
    # ax1.set_ylabel("Score")

    ax2.set_ylabel("Cum Score")
    ax2.legend(loc='upper left')


ani = animation.FuncAnimation(fig, animate, interval=1000)
plt.show()