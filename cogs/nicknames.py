"""A cog that handles keeping nicknames persistent between member join/leave, as a substitute for setting nicknames by teams."""
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import guild_only

import db
from context import DozerContext
from ._utils import *


class Nicknames(commands.Cog):
    """Preserves nicknames upon member join/leave, similar to roles."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.hybrid_command()
    @guild_only()
    @app_commands.describe(save = "Do you want to save your nickname?")
    async def savenick(self, ctx: DozerContext, save: bool = None):
        """Sets whether a user wants their nickname upon server leave to be saved upon server rejoin or not."""
        nick = await NicknameTable.get_by(user_id = ctx.author.id, guild_id = ctx.guild.id)
        if nick is None:
            nick = NicknameTable(user_id = ctx.author.id, guild_id = ctx.guild.id, nickname = ctx.author.nick,
                                 enabled = save is None or save)
            await nick.update_or_add()
        else:
            if save is not None:
                nick = NicknameTable(user_id = ctx.author.id, guild_id = ctx.guild.id, nickname = ctx.author.nick,
                                     enabled = save)
                await nick.update_or_add()
        await ctx.send(f"Nickname saving is {'enabled' if nick.enabled else 'disabled'}!", ephemeral = True)

    savenick.example_usage = """
    `{prefix}savenick False` - disables saving nicknames upon server leave.
    """

    @Cog.listener()
    async def on_member_join(self, member):
        """Handles adding the nickname back on server join."""
        nick = await NicknameTable.get_by(user_id = member.id, guild_id = member.guild.id)
        if not nick or not nick[0].enabled or not member.guild.me.guild_permissions.manage_nicknames or member.top_role >= member.guild.me.top_role:
            return
        await member.edit(nick = nick[0].nickname)

    @Cog.listener()
    async def on_member_remove(self, member):
        """Handles saving the nickname on server leave."""
        nick = await NicknameTable.get_by(user_id = member.id, guild_id = member.guild.id)
        if nick is None:
            nick = NicknameTable(user_id = member.id, guild_id = member.guild.id, nickname = member.nick,
                                 enabled = True)
            await nick.update_or_add()
        else:
            if not nick[0].enabled:
                return
            nick[0].nickname = member.nick
            await nick[0].update_or_add()


class NicknameTable(db.DatabaseTable):
    """Maintains a record of saved nicknames for various users."""
    __tablename__ = 'nicknames'
    __uniques__ = ('user_id', 'guild_id',)
    __defaults__ = {'enabled': True}

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            user_id bigint PRIMARY KEY NOT NULL,
            guild_id bigint NOT NULL,
            nickname text NOT NULL,
            enabled bool NOT NULL,
            unique (user_id, guild_id)
            )""")

    def __init__(self, user_id: int, guild_id: int, nickname: str, enabled: bool):
        super().__init__()
        self.user_id = user_id
        self.guild_id = guild_id
        self.nickname = nickname
        self.enabled = enabled

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = NicknameTable(
                user_id = result.get('user_id'),
                guild_id = result.get('guild_id'),
                nickname = result.get('nickname'),
                enabled = result.get('enabled'))
            result_list.append(obj)
        return result_list

    async def version_1(self):
        """DB migration v1"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            ALTER TABLE {self.__tablename__} ADD self_inflicted bool NOT NULL DEFAULT false;
            """)

    __versions__ = (version_1,)


async def setup(bot):
    """cog setup boilerplate"""
    await bot.add_cog(Nicknames(bot))
