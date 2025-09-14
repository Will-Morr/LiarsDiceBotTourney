import matplotlib.pyplot as plt
import matplotlib.animation as animation
from matplotlib import style
import os
import pandas as pd

import matplotlib.pyplot as plt
plt.style.use('dark_background')

fig, ax = plt.subplots(2, sharex=True)
ax1, ax2 = ax

last_read_time = 0
file_path = 'logs/tourney.parquet'

def animate(i):
    tourney = pd.read_parquet('logs/tourney.parquet')
    bot_result = pd.read_parquet(
        'logs/bot_result.parquet', 
        columns=['tourney_uuid','bot_uuid','bot_fullname', 'bot_name', 'bot_player', 'final_score']
    )

    bot_result = bot_result.merge(tourney[['tourney_uuid','tourney_index','start_time']], on='tourney_uuid', how='outer')

    bot_result = bot_result.sort_values('start_time')

    bot_result["print_name"] = bot_result['bot_name'] + ' ' + bot_result['bot_player']

    if True:
        bot_result = bot_result[bot_result['tourney_index'] >= bot_result['tourney_index'].max()-10]

    ax1.cla()
    ax2.cla()
    for name, subdf in bot_result.groupby('print_name'):
        ax1.plot(subdf['tourney_index'], subdf['final_score'], label = name)
        # ax1.scatter(subdf['tourney_index'], subdf['final_score'])

        ax2.plot(subdf['tourney_index'], subdf['final_score'].cumsum(), label = name)
        # ax1.scatter(subdf['tourney_index'], subdf['final_score'])

    ax2.legend()
    ax1.set_ylabel("Score")
    ax2.set_ylabel("Cum Score")
    ax2.set_xlabel("Tourney Index")

ani = animation.FuncAnimation(fig, animate, interval=1000)
plt.show()