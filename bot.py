"""Bot object for Dozer"""

import logging
import re
import sys
import traceback
import discord
import aiohttp
from discord.ext import commands
from discord import app_commands
import os

import utils

# from asyncdb.orm import orm #this is for the database that dozer uses

# why on earth should logging objects be capitalized? (I'm not gonna question whoever made this comment)
dozer_logger = logging.getLogger('dozer')
dozer_logger.level = logging.DEBUG
discord_logger = logging.getLogger('discord')
discord_logger.level = logging.DEBUG

dozer_log_handler = logging.StreamHandler(stream = sys.stdout)
dozer_log_handler.level = logging.INFO
dozer_logger.addHandler(dozer_log_handler)
discord_logger.addHandler(dozer_log_handler)
dozer_log_handler.setFormatter(fmt = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'))

if discord.version_info.major < 1:
    dozer_logger.error("Your installed discord.py version is too low "
                       "%d.%d.%d, please upgrade to at least 1.0.0a",
                       discord.version_info.major,
                       discord.version_info.minor,
                       discord.version_info.micro)
    sys.exit(1)

elif not hasattr(commands, "Cog"):
    dozer_logger.error("Your installed discord.py rewrite version is too "
                       "old and lacks discord.ext.commands.Cog, please reinstall it and try again.")
    sys.exit(1)

MY_GUILD = discord.Object(id = 1088700196675919872)  # temp testing server, will switch to ftc discord id later
intents = discord.Intents.all()
intents.members = True
intents.message_content = True
intents.presences = True


class InvalidContext(commands.CheckFailure):
    """
    Check failure raised by the global check for an invalid command context - executed by a bot, exceeding global rate-limit, etc.
    The message will be ignored.
    """


class DozerContext(commands.Context):
    """Cleans all messages before sending"""

    async def send(self, content = None, **kwargs):  # pylint: disable=arguments-differ
        if content is not None:
            content = utils.clean(self, content, mass = True, member = False, role = False, channel = False)

        if "embed" in kwargs and isinstance(kwargs["embed"], discord.Embed):
            for field in kwargs["embed"].fields:
                if not field.name and field.value:
                    dozer_logger.error(f"Invalid embed values {field.name!r}: {field.value!r}")
        return await super().send(content, **kwargs)


class Dozer(commands.Bot):
    """Botty things that are critical to Dozer working"""

    def __init__(self, config):
        super().__init__(command_prefix = config['prefix'], intents = intents, case_insensitive = True)
        self.config = config
        self.logger = dozer_logger
        self._restarting = False
        self.check(self.global_checks)
        self.http_session = None
        if 'log_level' in config:
            dozer_log_handler.setLevel(config['log_level'])

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession(loop = self.loop)
        self.tree.copy_global_to(
            guild = MY_GUILD)  # these 2 lines rely on MY_GUILD, which by default is set to be the FTC discord (
        # faster command syncing when it's specified)
        await self.tree.sync(guild = MY_GUILD)

    async def update_status(self):
        """Dynamically update the bot's status."""
        dozer_logger.info('Signed in as {}#{} ({})'.format(self.user.name, self.user.discriminator, self.user.id))
        if self.config['is_backup']:
            status = discord.Status.dnd
        else:
            status = discord.Status.online
        game = discord.Game(name = f"{self.config['prefix']}help | {len(self.guilds)} guilds")
        try:
            await self.change_presence(activity = game, status = status)
        except TypeError:
            dozer_logger.warning("You are running an older version of the discord.py rewrite (with breaking changes)! "
                                 "To upgrade, run `pip install -r requirements.txt --upgrade`")

    async def on_ready(self):
        """Things to run when the bot has initialized and signed in"""
        await self.update_status()

    async def on_guild_join(self, guild):  # pylint: disable=unused-argument
        """Update bot status to remain accurate."""
        await self.update_status()

    async def on_guild_remove(self, guild):  # pylint: disable=unused-argument
        """Update bot status to remain accurate."""
        await self.update_status()

    async def get_context(self, message, *, cls = DozerContext):
        return await super().get_context(message, cls = cls)

    async def on_command_error(self, context, exception):
        if isinstance(exception, commands.NoPrivateMessage):
            await context.send('{}, This command cannot be used in DMs.'.format(context.author.mention))

        elif isinstance(exception, commands.UserInputError):
            await context.send('{}, {}'.format(context.author.mention, self.format_error(context, exception)))

        elif isinstance(exception, commands.NotOwner):
            await context.send('{}, {}'.format(context.author.mention, exception.args[0]))

        elif isinstance(exception, commands.MissingPermissions):
            permission_names = [name.replace('guild', 'server').replace('_', ' ').title() for name in
                                exception.missing_perms]
            await context.send('{}, you need {} permissions to run this command!'.format(
                context.author.mention, utils.pretty_concat(permission_names)))

        elif isinstance(exception, commands.BotMissingPermissions):
            permission_names = [name.replace('guild', 'server').replace('_', ' ').title() for name in
                                exception.missing_perms]
            await context.send('{}, I need {} permissions to run this command!'.format(
                context.author.mention, utils.pretty_concat(permission_names)))

        elif isinstance(exception, commands.CommandOnCooldown):
            await context.send('{}, That command is on cooldown! Try again in {:.2f}s!'.format(context.author.mention,
                                                                                               exception.retry_after))

        elif isinstance(exception, (commands.CommandNotFound, InvalidContext)):
            pass  # Silent ignore

        else:
            await context.send(
                '```\n%s\n```' % ''.join(traceback.format_exception_only(type(exception), exception)).strip())
            if isinstance(context.channel, discord.TextChannel):
                dozer_logger.error('Error in command <{0}> ({1.name!r}:({1.id}) {2}:({2.id}) {3}:({3.id}) {4})'
                                   ''.format(context.command, context.guild, context.channel, context.author,
                                             context.message.content))
            else:
                dozer_logger.error(
                    'Error in command <{0}> (DM {1}:({1}.id) {2})'.format(context.command, context.channel.recipient,
                                                                          context.message.content))
            dozer_logger.error(''.join(traceback.format_exception(type(exception), exception, exception.__traceback__)))

    @staticmethod
    def format_error(ctx, err, *, word_re = re.compile('[A-Z][a-z]+')):
        """Turns an exception into a user-friendly (or -friendlier, at least) error message."""
        type_words = word_re.findall(type(err).__name__)
        type_msg = ' '.join(map(str.lower, type_words))

        if err.args:
            return '%s: %s' % (type_msg, utils.clean(ctx, err.args[0]))
        else:
            return type_msg

    def global_checks(self, ctx):
        """Checks that should be executed before passed to the command"""
        if ctx.author.bot:
            raise InvalidContext('Bots cannot run commands!')
        retry_after = False  # self._global_cooldown.update_rate_limit()
        if retry_after and not hasattr(ctx, "is_pseudo"):  # bypass ratelimit for su'ed commands
            raise InvalidContext('Global rate-limit exceeded!')
        return True

    async def run(self, *args, **kwargs):
        token = self.config['discord_token']
        del self.config['discord_token']  # Prevent token dumping
        await super().start(token)

    async def shutdown(self, restart = False):
        """Shuts down the bot"""
        self._restarting = restart
        # await self.logout()
        await self.close()
        # await orm.close()
        await self.http_session.close()
        self.loop.stop()
