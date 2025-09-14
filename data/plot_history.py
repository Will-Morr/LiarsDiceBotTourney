
import os
import pandas as pd

import matplotlib.pyplot as plt
plt.style.use('dark_background')

last_read_time = 0

tourney = pd.read_parquet('logs/tourney.parquet')
bot_result = pd.read_parquet('logs/bot_result.parquet')

    # print(bot_result)
    # print(tourney)

print(tourney['tourney_index'])

bot_result = bot_result.merge(tourney[['tourney_uuid','tourney_index','start_time']], on='tourney_uuid', how='outer')
bot_result = bot_result.sort_values('start_time')

bot_result["print_name"] = bot_result['bot_name'] + ' ' + bot_result['bot_player']

for name, subdf in bot_result.groupby('print_name'):
    plt.plot(subdf['tourney_index'], subdf['final_score'].cumsum(), label = name)
    plt.xlabel("Tournies")
    plt.ylabel("Sum Score")

plt.legend()
plt.show()