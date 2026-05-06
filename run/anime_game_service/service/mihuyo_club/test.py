from run.anime_game_service.service.mihuyo_club.command import *
import asyncio

from framework_common.database_util.ManShuoDrawCompatibleDataBase import cache_init

if __name__ == '__main__':
    #asyncio.run(cache_init())
    asyncio.run(mys_game_sign(1270858640,target = 'daily_sign'))
    #asyncio.run(mys_game_sign(1270858640))