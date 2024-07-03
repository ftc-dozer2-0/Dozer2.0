"""Maintenance commands for bot developers"""

import os

from discord.ext.commands import NotOwner
from discord.ext import commands
from loguru import logger

from context import DozerContext


class Maintenance(commands.Cog):
    """
    Commands for performing maintenance on the bot.
    These commands are restricted to bot developers.
    """
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__()
        self.bot = bot

    def cog_check(self, ctx: DozerContext):  # All of this cog is only available to devs
        if ctx.author.id not in ctx.bot.config['developers']:
            raise NotOwner('You are not a developer!')
        return True

    @commands.hybrid_command()
    async def shutdown(self, ctx: DozerContext):
        """Force-stops the bot."""
        await ctx.send('Shutting down')
        logger.info(f'Shutting down at request of {ctx.author.name}{"#" + ctx.author.discriminator if ctx.author.discriminator != "0" else ""}'
                    f'(in {ctx.guild.name}, #{ctx.channel.name})')
        stephan = ctx.bot.get_user(675726066018680861)
        await stephan.send(f"Shutting down at request of {ctx.author.name}{'#' + ctx.author.discriminator if ctx.author.discriminator != '0' else ''}"
                           f'(in {ctx.guild.name}, #{ctx.channel.name})')
        await self.bot.shutdown()

    shutdown.example_usage = """
    `{prefix}shutdown` - stop the bot
    """

    @commands.hybrid_command(name = "restart", aliases = ["reboot"])
    async def restart(self, ctx: DozerContext):
        """Restarts the bot."""
        await ctx.send('Restarting')
        logger.info(f'Restarting at request of {ctx.author.name}{"#" + ctx.author.discriminator if ctx.author.discriminator != "0" else ""}'
                    f'(in {ctx.guild.name}, #{ctx.channel.name})')
        stephan = ctx.bot.get_user(675726066018680861)
        await stephan.send(f"Restarting at request of {ctx.author.name}{'#' + ctx.author.discriminator if ctx.author.discriminator != '0' else ''}"
                           f'(in {ctx.guild.name}, #{ctx.channel.name})')
        await self.bot.shutdown(restart=True)

    restart.example_usage = """
    `{prefix}restart` - restart the bot
    """

    @commands.hybrid_command(name = "update", aliases = ["pull"])
    async def update(self, ctx: DozerContext):
        """
        Pulls code from GitHub and restarts.
        This pulls from whatever repository `origin` is linked to.
        If there are changes to download, and the download is successful, the bot restarts to apply changes.
        """
        res = os.popen("git pull").read()
        stephan = ctx.bot.get_user(675726066018680861)
        if res.startswith('Already up to date.') or "CONFLICT (content):" in res:
            await ctx.send('```\n' + res + '```')
            await stephan.send(f"Update command run by {ctx.author.name}{'#' + ctx.author.discriminator if ctx.author.discriminator != '0' else ''}")
        else:
            await ctx.send('```\n' + res + '```')
            await stephan.send(f"Update command run by {ctx.author.name}{'#' + ctx.author.discriminator if ctx.author.discriminator != '0' else ''}")
            await ctx.bot.get_command('restart').callback(self, ctx)

    update.example_usage = """
    `{prefix}update` - update to the latest commit and restart
    """


async def setup(bot):
    """Adds the maintenance cog to the bot process."""
    await bot.add_cog(Maintenance(bot))
