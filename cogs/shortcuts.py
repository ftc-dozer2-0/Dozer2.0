from typing import Dict, List, Optional, Self

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands import BadArgument
from discord.ext.commands import NotOwner
from discord.ext.commands.core import has_permissions

import db
from context import DozerContext
from ._utils import *


class Shortcuts(commands.Cog):
    MAX_LEN = 20

    def __init__(self, bot):
        """cog init"""
        pass

    """Commands for managing shortcuts/macros."""

    @has_permissions(manage_messages=True)
    @commands.hybrid_group(invoke_without_command=True)
    async def shortcuts(self, ctx: DozerContext):
        """
        Display shortcut information
        """
        setting = await ShortcutSetting.get_unique_by(guild_id=ctx.guild.id)
        if setting is None:
            await ctx.send("This server has no shortcut configuration.", ephemeral=True)
            return

        if not setting.approved:
            await ctx.send("This server is not approved for shortcuts.", ephemeral=True)
            return

        e = discord.Embed()
        e.title = "Server shortcut configuration"
        e.add_field(name="Shortcut prefix", value=setting.prefix or "[unset]")
        await ctx.send(embed=e, ephemeral=True)

    @shortcuts.command()
    @app_commands.describe(prefix="The prefix to use for shortcuts")
    async def approve(self, ctx: DozerContext, prefix: str = "!"):
        """Approve the server to use shortcuts"""
        if ctx.author.id not in ctx.bot.config['developers']:
            raise NotOwner('You are not a developer!')
        setting = await ShortcutSetting.get_unique_by(guild_id=ctx.guild.id)
        if setting is None:
            setting = ShortcutSetting(guild_id=ctx.guild.id, approved=True, prefix=prefix)
            await setting.update_or_add()
        else:
            setting.approved = True
            await setting.update_or_add()
        await ctx.send("Shortcuts approved for this guild", ephemeral=True)

    @shortcuts.command()
    async def revoke(self, ctx: DozerContext):
        """Revoke the server's ability to use shortcuts"""
        if ctx.author.id not in ctx.bot.config['developers']:
            raise NotOwner('You are not a developer!')

        setting = await ShortcutSetting.get_unique_by(guild_id=ctx.guild.id)
        if not setting or not setting.approved:
            await ctx.send("Shortcuts were not enabled on this guild.", ephemeral=True)
            return

        setting.approved = False
        await setting.update_or_add()

        await ctx.send("Shortcuts have been revoked from this guild.", ephemeral=True)

    @has_permissions(manage_messages=True)
    @shortcuts.command()
    @app_commands.describe(cmd_name="shortcut name", cmd_msg="stuff shortcut should display")
    async def add(self, ctx: DozerContext, cmd_name, *, cmd_msg):
        """Add a shortcut to the server."""

        cmd_name = cmd_name.casefold()

        if not cmd_msg:
            raise BadArgument("Command message is null or empty. How?")

        setting = await ShortcutSetting.get_unique_by(guild_id=ctx.guild.id)
        if setting is None or not setting.approved:
            await ctx.send("This feature is not approved yet.", ephemeral=True)
            return

        if len(cmd_name) > self.MAX_LEN:
            await ctx.send(f"Command names can only be up to {self.MAX_LEN} chars long.", ephemeral=True)
            return

        ent = await ShortcutEntry.get_unique_by(guild_id=ctx.guild.id, name=cmd_name)
        if ent:
            ent.value = cmd_msg
            await ent.update_or_add()
        else:
            ent = ShortcutEntry(guild_id=ctx.guild.id, name=cmd_name, value=cmd_msg)
            await ent.update_or_add()

        await ctx.send("Updated command successfully.", ephemeral=True)

    @has_permissions(manage_messages=True)
    @shortcuts.command()
    @app_commands.describe(cmd_name="shortcut name")
    async def remove(self, ctx: DozerContext, cmd_name):
        """Remove a shortcut from the server."""

        cmd_name = cmd_name.casefold()

        setting = await ShortcutSetting.get_unique_by(guild_id=ctx.guild.id)
        if setting is None or not setting.approved:
            await ctx.send("This feature is not approved yet.", ephemeral=True)
            return

        ent = await ShortcutEntry.get_unique_by(guild_id=ctx.guild.id, name=cmd_name)
        if not ent:
            await ctx.send("No such shortcut.", ephemeral=True)
            return

        await ent.delete()
        await ctx.send("Removed command successfully.", ephemeral=True)

    @shortcuts.command()
    async def list(self, ctx: DozerContext):
        """List all shortcuts for this server."""
        setting = await ShortcutSetting.get_unique_by(guild_id=ctx.guild.id)
        if setting is None or not setting.approved:
            await ctx.send("This feature is not approved yet.", ephemeral=True)
            return

        entries: List[ShortcutEntry] = await ShortcutEntry.get_by(guild_id=ctx.guild.id)

        if not entries:
            await ctx.send("There are no shortcuts for this server.", ephemeral=True)
            return

        embed = None
        for i, e in enumerate(entries):
            if i % 20 == 0:
                if embed is not None:
                    await ctx.send(embed=embed)
                embed = discord.Embed()
                embed.title = "Shortcuts for this guild"
            embed.add_field(name=setting.prefix + e.name, value=e.value[:1024])  # Max embed field length is 1024

        if embed.fields:
            await ctx.send(embed=embed, ephemeral=True)

    @Cog.listener()
    async def on_ready(self):
        """reload sheets on_ready"""
        pass

    @Cog.listener()
    async def on_message(self, msg: discord.Message):
        """prefix scanner"""
        if not msg.guild or msg.author.bot:
            return

        setting = await ShortcutSetting.get_unique_by(guild_id=msg.guild.id)
        if not setting:
            return

        if not msg.content.startswith(setting.prefix):
            return

        cmd = msg.content.removeprefix(setting.prefix).casefold()
        shortcut = await ShortcutEntry.get_unique_by(guild_id=msg.guild.id, name=cmd)
        await msg.channel.send(shortcut.value)


class ShortcutSetting(db.DatabaseTable):
    """Provides a DB config to track mutes."""
    __tablename__ = 'shortcut_settings'
    __uniques__ = ("guild_id",)

    @classmethod
    async def initial_create(cls):
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,
            approved boolean NOT NULL,
            prefix text null
            )""")

    def __init__(self, guild_id: int, approved: bool, prefix: str = '!'):
        super().__init__()
        self.guild_id = guild_id
        self.approved = approved
        self.prefix = prefix

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        results_list = []
        for result in results:
            thing = ShortcutSetting(guild_id=result.get('guild_id'), approved=result.get('approved'),
                                    prefix=result.get('prefix'))
            results_list.append(thing)
        return results_list

    @classmethod
    async def get_unique_by(cls, **kwargs) -> Optional[Self]:
        # In the rare case that get_by gives us tons of records this will be very inefficient,
        # but that is never expected to happen, so it should be fine.
        settings = await cls.get_by(**kwargs)
        if not settings:
            return None

        assert len(settings) == 1

        return settings[0]


class ShortcutEntry(db.DatabaseTable):
    """Provides a DB config to track mutes."""
    __tablename__ = 'shortcuts'
    __uniques__ = ("guild_id", "name")

    @classmethod
    async def initial_create(cls):
        async with db.Pool.acquire() as conn:
            query = f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,
            name text NOT NULL,
            value text NOT NULL,
            UNIQUE (guild_id, name)
            )"""
            print(query)
            await conn.execute(query)

    def __init__(self, guild_id: int, name: str, value: str):
        super().__init__()
        self.guild_id = guild_id
        self.name = name
        self.value = value

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        results_list = []
        for result in results:
            thing = ShortcutEntry(guild_id=result.get('guild_id'), name=result.get('name'),
                                  value=result.get('value'))
            results_list.append(thing)
        return results_list

    @classmethod
    async def get_unique_by(cls, **kwargs) -> Optional[Self]:
        # In the rare case that get_by gives us tons of records this will be very inefficient,
        # but that is never expected to happen, so it should be fine.
        settings = await cls.get_by(**kwargs)
        if not settings:
            return None

        assert len(settings) == 1

        return settings[0]


async def setup(bot):
    """Adds the moderation cog to the bot."""
    await bot.add_cog(Shortcuts(bot))
