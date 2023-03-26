"""Maintenance commands for bot developers"""

import os
import sys

from discord.ext.commands import NotOwner
from bot import dozer_logger
from cogs._utils import *
from discord.ext import commands


class Maintenance(Cog):
    """
    Commands for performing maintenance on the bot.
    These commands are restricted to bot developers.
    """
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)
        self.bot = bot

    def cog_check(self, ctx):  # All of this cog is only available to devs
        if ctx.author.id not in ctx.bot.config['developers']:
            raise NotOwner('You are not a developer!')
        return True

    @commands.hybrid_command()
    async def shutdown(self, ctx):
        """Force-stops the bot."""
        await ctx.send('Shutting down', ephemeral=True)
        dozer_logger.info('Shutting down at request of {}#{} (in {}, #{})'.format(ctx.author.name,
                                                                                  ctx.author.discriminator,
                                                                                  ctx.guild.name,
                                                                                  ctx.channel.name))
        await self.bot.shutdown()

    shutdown.example_usage = """
    `{prefix}shutdown` - stop the bot
    """

    @commands.hybrid_command(name = "restart", aliases = ["reboot"])
    async def restart(self, ctx):
        """Restarts the bot."""
        await ctx.send('Restarting', ephemeral=True)
        await self.bot.shutdown(restart=True)

    restart.example_usage = """
    `{prefix}restart` - restart the bot
    """

    @commands.hybrid_command(name = "update", aliases = ["pull"])
    async def update(self, ctx):
        """
        Pulls code from GitHub and restarts.
        This pulls from whatever repository `origin` is linked to.
        If there are changes to download, and the download is successful, the bot restarts to apply changes.
        """
        res = os.popen("git pull").read()
        if res.startswith('Already up-to-date.'):
            await ctx.send('```\n' + res + '```', ephemeral=True)
        else:
            await ctx.send('```\n' + res + '```', ephemeral=True)
            await ctx.bot.get_command('restart').callback(self, ctx)

    update.example_usage = """
    `{prefix}update` - update to the latest commit and restart
    """


async def setup(bot):
    """Adds the maintenance cog to the bot process."""
    await bot.add_cog(Maintenance(bot))
