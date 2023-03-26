"""A cog that handles keeping nicknames persistent between member join/leave, as a substitute for setting nicknames by teams."""
import discord
from discord.ext.commands import BadArgument, guild_only
from discord import app_commands
from discord.ext import commands
from ._utils import *
from asyncdb.orm import orm
from asyncdb import psqlt


class Nicknames(commands.Cog):
    """Preserves nicknames upon member join/leave, similar to roles."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command()
    @guild_only()
    @app_commands.describe(save = "Do you want to save your nickname?")
    async def savenick(self, ctx, save: bool = None):
        """Sets whether or not a user wants their nickname upon server leave to be saved upon server rejoin."""
        nick = await NicknameTable.select_one(user_id=ctx.author.id, guild_id=ctx.guild.id)
        if nick is None:
            nick = NicknameTable(user_id=ctx.author.id, guild_id=ctx.guild.id, nickname=ctx.author.nick, enabled=save is None or save)
            await nick.insert()
        else:
            if save is not None:
                nick.enabled = save
                await nick.update()
        await ctx.send(f"Nickname saving is {'enabled' if nick.enabled else 'disabled'}!")
    savenick.example_usage = """
    `{prefix}savenick False` - disables saving nicknames upon server leave.
    """

    @Cog.listener()
    async def on_member_join(self, member):
        """Handles adding the nickname back on server join."""
        if 'silent' in self.bot.config and self.bot.config['silent']:
            return
        nick = await NicknameTable.select_one(user_id=member.id, guild_id=member.guild.id)
        if not nick or not nick.enabled or not member.guild.me.guild_permissions.manage_nicknames or member.top_role >= member.guild.me.top_role:
            return
        await member.edit(nick=nick.nickname)

    @Cog.listener()
    async def on_member_remove(self, member):
        """Handles saving the nickname on server leave."""
        nick = await NicknameTable.select_one(user_id=member.id, guild_id=member.guild.id)
        if nick is None:
            nick = NicknameTable(user_id=member.id, guild_id=member.guild.id, nickname=member.nick, enabled=True)
            await nick.insert()
        else:
            if not nick.enabled:
                return
            nick.nickname = member.nick
            await nick.update()


class NicknameTable(orm.Model):
    """Maintains a record of saved nicknames for various users."""
    __tablename__ = "nicknames"
    __primary_key__ = ('user_id', 'guild_id')
    user_id: psqlt.bigint
    guild_id: psqlt.bigint
    nickname: psqlt.text
    enabled: psqlt.boolean


async def setup(bot):
    """cog setup boilerplate"""
    await bot.add_cog(Nicknames(bot))
