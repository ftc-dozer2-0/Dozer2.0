"""Initializes the bot and deals with the configuration file"""

import json
import os
import sys
import asyncio
import uvloop
import discord
from discord.ext import commands
from typing import Any

from bot import Dozer


def load_config() -> dict[str, Any]:
    config = {
        'prefix': '&', 'developers': [],
        'tba': {
            'key': ''
        },
        'toa': {
            'key': 'Put TOA API key here',
            'app_name': 'Dozer',
            'teamdata_url': ''
        },
        'ftc_events': {
            "user": "Put FTC-Events user here",
            "token": "Put FTC-Events token here",
        },
        'log_level': 'INFO',
        'db_url': 'postgres:///dozer',
        'tz_url': '',
        'discord_token': "Put Discord API Token here.",
        'news': {
            'check_interval': 5.0,
            'twitch': {
                'client_id': "Put Twitch Client ID here",
                'client_secret': "Put Twitch Secret Here"
            },
            'reddit': {
                'client_id': "Put Reddit Client ID here",
                'client_secret': "Put Reddit Secret Here"
            },

        },
        'debug': False,
        'is_backup': False
    }

    config_file = 'config.json'

    if os.path.isfile(config_file):
        with open(config_file) as f:
            config.update(json.load(f))

    with open('config.json', 'w') as f:
        json.dump(config, f, indent='\t')

    if 'discord_token' not in config:
        sys.exit('Discord token must be supplied in configuration - please add one to config.json')

    return config


def load_cogs(bot: Dozer):
    for ext in os.listdir('cogs'):
        if not ext.startswith(('_', '.')):
            await bot.load_extension('cogs.' + ext[:-3])  # Remove '.py' from the end of the filename


async def main():
    # TODO: this version of restart code breaks update functionality. Replace functionality
    #  with a better alternative, like a proper CD pipeline.
    while True:
        config = load_config()
        bot = Dozer(config)
        load_cogs(bot)

        # await orm.connect(dsn = config['db_url'])
        # await orm.Model.create_all_tables()
        await bot.run()

        if not bot.restarting:
            break


if discord.version_info.major < 1:
    v = discord.version_info
    sys.exit(
        f'Your installed discord.py version, {v.major}.{v.minor}.{v.macro}, is too low.'
        'Please upgrade to at least 1.0.0a'
    )

if not hasattr(commands, "Cog"):
    sys.exit(
        'Your installed discord.py rewrite version is too old and lacks discord.ext.commands.Cog,'
        'please reinstall it and try again.'
    )

if sys.version_info < (3, 6):
    v = sys.version_info
    sys.exit(
        f'Dozer requires Python 3.6 or higher to run. This is version {v.major}.{v.minor}.{v.macro}.'
    )

if os.name == 'nt':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
else:
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

asyncio.run(main())
