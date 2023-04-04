"""Initializes the bot and deals with the configuration file"""

import json
import os
import sys

import discord
import sentry_sdk
from loguru import logger

if sys.version_info < (3, 11):
    sys.exit('Due to certain features only found in Python 3.11 and up, Dozer requires Python 3.11 or higher to run. '
             'This is version ' + '.'.join(sys.version_info[:3]) + '.')

config = {
    'prefix': '&', 'developers': [],
    'cache_size': 20000,
    'tba': {
        'key': 'Put TBA API key here'
    },
    'toa': {
        'app_name': 'Dozer',
    },
    'db_url': 'postgres://dozer_user:simplepass@postgres',
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
    'lavalink': {
        'enabled': False,
        'host': 'lavalink',
        'port': 2333,
        'password': 'youshallnotpass',
        'identifier': 'MAIN',
        'region': 'us_central'
    },
    'debug': False,
    'presences_intents': True,
    'is_backup': False,
    'invite_override': "",
    "sentry_url": "",
    "disabled_cogs": []
}
config_file = 'config.json'

if os.path.isfile(config_file):
    with open(config_file) as f:
        config.update(json.load(f))

with open('config.json', 'w') as f:
    json.dump(config, f, indent = '\t')

if config['sentry_url'] != "":
    sentry_sdk.init(  # pylint: disable=abstract-class-instantiated  # noqa: E0110
        str(config['sentry_url']),
        traces_sample_rate=1.0,
    )
logger_format = "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{" \
                "name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{" \
                "message}</level> "
logger.remove()
logger.add(sys.stdout, format=logger_format, level="DEBUG" if config['debug'] else "INFO", enqueue=True, colorize=True)
if 'discord_token' not in config:
    sys.exit('Discord token must be supplied in configuration')

from bot import Dozer

bot = Dozer(config)

intents = discord.Intents.default()
intents.members = True
intents.presences = True
intents.message_content = True

bot.run()


# restart the bot if the bot flagged itself to do so
if bot._restarting:
    script = sys.argv[0]
    if script.startswith(os.getcwd()):
        script = script[len(os.getcwd()):].lstrip(os.sep)

    if script.endswith('__main__'):
        args = [sys.executable, '-m', script[:-len('__main__')].rstrip(os.sep).replace(os.sep, '.')]
    else:
        args = [sys.executable, script]
    os.execv(sys.executable, args + sys.argv[1:])
