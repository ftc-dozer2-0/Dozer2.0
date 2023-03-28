"""Bot object for Dozer"""

import logging
import re
import sys
import traceback
import discord
import aiohttp
from discord.ext import commands

import utils

# from asyncdb.orm import orm #this is for the database that dozer uses

# why on earth should logging objects be capitalized? (I'm not gonna question whoever made this comment)
dozer_logger = logging.getLogger('dozer')
dozer_logger.level = logging.DEBUG
discord_logger = logging.getLogger('discord')
discord_logger.level = logging.DEBUG

dozer_log_handler = logging.StreamHandler(stream=sys.stdout)
dozer_log_handler.level = logging.INFO
dozer_logger.addHandler(dozer_log_handler)
discord_logger.addHandler(dozer_log_handler)
dozer_log_handler.setFormatter(fmt=logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s'))

MY_GUILD = discord.Object(id=1088700196675919872)  # temp testing server, will switch to ftc discord id later
intents = discord.Intents.default()
intents.members = True
intents.message_content = True


class InvalidContext(commands.CheckFailure):
    """
    Check failure raised by the global check for an invalid command context - executed by a bot, exceeding global rate-limit, etc.
    The message will be ignored.
    """


class DozerContext(commands.Context):
    """Cleans all messages before sending"""

    async def send(self, content=None, **kwargs):  # pylint: disable=arguments-differ
        if content is not None:
            content = utils.clean(self, content, mass=True, member=False, role=False, channel=False)

        if "embed" in kwargs and isinstance(kwargs["embed"], discord.Embed):
            for field in kwargs["embed"].fields:
                if not field.name and field.value:
                    dozer_logger.error(f"Invalid embed values {field.name!r}: {field.value!r}")
        return await super().send(content, **kwargs)


class Dozer(commands.Bot):
    """Botty things that are critical to Dozer working"""

    def __init__(self, config):
        super().__init__(command_prefix=config['prefix'], intents=intents, case_insensitive=True)
        self.config = config
        self.logger = dozer_logger
        self.restarting = False
        self.add_check(self.global_checks)
        self.http_session = None
        if 'log_level' in config:
            dozer_log_handler.setLevel(config['log_level'])

    @staticmethod
    def global_checks(ctx):
        """Checks that should be executed before passed to the command"""
        if ctx.author.bot:
            raise InvalidContext('Bots cannot run commands!')
        retry_after = False  # self._global_cooldown.update_rate_limit()
        if retry_after and not hasattr(ctx, "is_pseudo"):  # bypass ratelimit for su'ed commands
            raise InvalidContext('Global rate-limit exceeded!')
        return True

    async def setup_hook(self):
        self.http_session = aiohttp.ClientSession(loop=self.loop)
        # these 2 lines rely on MY_GUILD, which by default is set to be the FTC discord
        # (faster command syncing when it's specified)
        self.tree.copy_global_to(guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)

    async def update_status(self):
        """Dynamically update the bot's status."""
        dozer_logger.info('Signed in as {}#{} ({})'.format(self.user.name, self.user.discriminator, self.user.id))
        if self.config['is_backup']:
            status = discord.Status.dnd
        else:
            status = discord.Status.online
        game = discord.Game(name=f"{self.config['prefix']}help | {len(self.guilds)} guilds")
        try:
            await self.change_presence(activity=game, status=status)
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

    async def get_context(self, message, *, cls=DozerContext):
        return await super().get_context(message, cls=cls)

    async def on_command_error(self, ctx, exception):
        if isinstance(exception, (commands.CommandNotFound, InvalidContext)):
            return  # Silent ignore

        if isinstance(exception, commands.NoPrivateMessage):
            await ctx.send(f'{ctx.author.mention}, This command cannot be used in DMs.')
        elif isinstance(exception, commands.UserInputError):
            await ctx.send(f'{ctx.author.mention}, {utils.format_error(ctx, exception)}')
        elif isinstance(exception, commands.NotOwner):
            await ctx.send(f'{ctx.author.mention}, {exception.args[0]}')
        elif isinstance(exception, commands.MissingPermissions):
            permission_names = [name.replace('guild', 'server').replace('_', ' ').title() for name in
                                exception.missing_permissions]
            perm_str = utils.pretty_concat(permission_names)
            await ctx.send(f'{ctx.author.mention}, you need {perm_str} permissions to run this command!')
        elif isinstance(exception, commands.BotMissingPermissions):
            permission_names = [name.replace('guild', 'server').replace('_', ' ').title() for name in
                                exception.missing_permissions]
            perm_str = utils.pretty_concat(permission_names)
            await ctx.send(f'{ctx.author.mention}, I need {perm_str} permissions to run this command!')
        elif isinstance(exception, commands.CommandOnCooldown):
            await ctx.send(
                f'{ctx.author.mention}, That command is on cooldown!'
                f'Try again in {exception.retry_after:.2f}s!'
            )
        else:
            user_exception = ''.join(traceback.format_exception_only(type(exception), exception)).strip()
            await ctx.send(f'```\n${user_exception}\n```')

            if isinstance(ctx.channel, discord.TextChannel):
                dozer_logger.error('Error in command <{0}> ({1.name!r}:({1.id}) {2}:({2.id}) {3}:({3.id}) {4})',
                                   ctx.command, ctx.guild, ctx.channel, ctx.author, ctx.message.content)
            else:
                dozer_logger.error('Error in command <{0}> (DM {1}:({1}.id) {2})',
                                   ctx.command, ctx.channel.recipient, ctx.message.content)

            logging_exception = ''.join(traceback.format_exception(type(exception), exception, exception.__traceback__))
            dozer_logger.error(logging_exception)

    async def run(self, *args, **kwargs):
        token = self.config['discord_token']
        del self.config['discord_token']  # Prevent token dumping
        await super().start(token)

    async def shutdown(self, restart=False):
        """Shuts down the bot"""
        self.restarting = restart
        # await self.logout()
        await self.close()
        await orm.close()
        await self.http_session.close()
        self.loop.stop()


'''    @bot.tree.context_menu(name = "Report message to mods")
    async def report_message(interaction: discord.Interaction, message: discord.Message):
        # We're sending this response message with ephemeral=True, so only the command executor can see it
        await interaction.response.send_message(
            f'Thanks for reporting this message by {message.author.mention}! The mod team will be looking into this. ',
            ephemeral=True
        )

        # Handle report by sending it into a log channel
        log_channel = interaction.guild.get_channel(1065146798152372295)  # todo: replace with your channel id

        embed = discord.Embed(title='Reported Message')
        if message.content:
            embed.description = message.content

        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        embed.timestamp = message.created_at
        embed.add_field(name="Reported by",
                        value=f"{interaction.user.display_name} | {interaction.user.name}")  # optional to add reporting person's info
        # also optional, can add message id to db to prevent multiple reports of same message
        url_view = discord.ui.View()
        url_view.add_item(
            discord.ui.Button(label='Go to Message', style=discord.ButtonStyle.url, url=message.jump_url))

'''
