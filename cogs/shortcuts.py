import collections
import asyncio
import csv
import io
import logging
from typing import Dict, List
import aiohttp
import discord
from discord.ext.commands import BadArgument, guild_only
from discord.ext.commands import NotOwner
from discord.ext.commands.core import has_permissions
from discord import app_commands
from discord.ext import commands

from ._utils import *
from asyncdb.orm import orm
from asyncdb import psqlt, configcache


class Shortcuts(commands.Cog):
    MAX_LEN = 20

    def __init__(self, bot):
        """cog init"""
        self.settings_cache = configcache.AsyncConfigCache(ShortcutSetting)
        self.cache = configcache.AsyncConfigCache(ShortcutEntry)
        self.guild_table: Dict[int, Dict[str, str]] = {}
        self.bot = bot

    """Commands for managing shortcuts/macros."""

    @has_permissions(manage_messages = True)
    @commands.hybrid_group(invoke_without_command = True)
    async def shortcuts(self, ctx):
        """
        Display shortcut information
        """
        settings: ShortcutSetting = await self.settings_cache.query_one(guild_id = ctx.guild.id)
        if settings is None:
            raise BadArgument("This server has no shortcut configuration.")
        if not settings.approved:
            await ctx.send("This server is not approved for shortcuts.", ephemeral = True)
            return
        e = discord.Embed()
        e.title = "Server shortcut configuration"
        # e.add_field("Shortcut spreadsheet", settings.spreadsheet or "Unset")
        e.add_field(name = "Shortcut prefix", value = settings.prefix or "[unset]")
        await ctx.send(embed = e, ephemeral = True)

    @shortcuts.command()
    async def approve(self, ctx):
        """Approve the server to use shortcuts"""
        if ctx.author.id not in ctx.bot.config['developers']:
            raise NotOwner('you are not a developer!')
        settings: ShortcutSetting = await self.settings_cache.query_one(guild_id = ctx.guild.id)
        if settings is None:
            settings = ShortcutSetting()
            settings.guild_id = ctx.guild.id
            # settings.spreadsheet = ""
            settings.prefix = "!"
            settings.approved = True
            await settings.insert()
        else:
            settings.approved = True
            await settings.update()
        self.settings_cache.invalidate_entry(guild_id = ctx.guild.id)
        await ctx.send("shortcuts approved for this guild", ephemeral = True)

    @shortcuts.command()
    async def revoke(self, ctx):
        """Revoke the server's ability to use shortcuts"""
        if ctx.author.id not in ctx.bot.config['developers']:
            raise NotOwner('you are not a developer!')
        settings: ShortcutSetting = await self.settings_cache.query_one(guild_id = ctx.guild.id)
        if settings is not None:
            settings.approved = False
            await settings.update()
            self.settings_cache.invalidate_entry(guild_id = ctx.guild.id)
        await ctx.send("Shortcuts have been revoked from this guild.", ephemeral = True)

    @has_permissions(manage_messages = True)
    @shortcuts.command()
    @app_commands.describe(cmd_name = "shortcut name", cmd_msg = "stuff shortcut should display")
    async def add(self, ctx, cmd_name, *, cmd_msg):
        """Add a shortcut to the server."""
        settings: ShortcutSetting = await self.settings_cache.query_one(guild_id = ctx.guild.id)
        if settings is None or not settings.approved:
            raise BadArgument("this feature is not approved yet")
        if not cmd_name.startswith(settings.prefix):
            raise BadArgument("command must start with the prefix " + settings.prefix)
        if len(cmd_name) > self.MAX_LEN:
            raise BadArgument(f"command names can only be up to {self.MAX_LEN} chars long")
        if not cmd_msg:
            raise BadArgument("can't have null message")

        ent: ShortcutEntry = await self.cache.query_one(guild_id = ctx.guild.id, name = cmd_name)
        if ent:
            ent.value = cmd_msg
            await ent.update()
        else:
            ent = ShortcutEntry()
            ent.guild_id = ctx.guild.id
            ent.name = cmd_name
            ent.value = cmd_msg
            await ent.insert()
        self.cache.invalidate_entry(guild_id = ctx.guild.id, name = cmd_name)

        await ctx.send("Updated command successfully.", ephemeral = True)

    @has_permissions(manage_messages = True)
    @shortcuts.command()
    @app_commands.describe(cmd_name = "shortcut name")
    async def remove(self, ctx, cmd_name):
        """Remove a shortcut from the server."""
        settings: ShortcutSetting = await self.settings_cache.query_one(guild_id = ctx.guild.id)
        if settings is None or not settings.approved:
            raise BadArgument("this feature is not approved yet")

        ent: ShortcutEntry = await self.cache.query_one(guild_id = ctx.guild.id, name = cmd_name)
        if ent:
            await ent.delete()
        self.cache.invalidate_entry(guild_id = ctx.guild.id, name = cmd_name)

        await ctx.send("Removed command successfully.", ephemeral = True)

    @shortcuts.command()
    async def list(self, ctx):
        """List all shortcuts for this server."""
        settings: ShortcutSetting = await self.settings_cache.query_one(guild_id = ctx.guild.id)
        if settings is None or not settings.approved:
            raise BadArgument("this feature is not approved yet")

        ents: List[ShortcutEntry] = await ShortcutEntry.select(guild_id = ctx.guild.id)
        embed = None
        for i, e in enumerate(ents):
            if i % 20 == 0:
                if embed is not None:
                    await ctx.send(embed = embed)
                embed = discord.Embed()
                embed.title = "shortcuts for this guild"
            embed.add_field(name = e.name, value = e.value[:1024])

        if embed.fields:
            await ctx.send(embed = embed, ephemeral = True)

    add.example_usage = """
    `{prefix}shortcuts add hello Hello, World!!!!` - adds !hello to the server
    """

    remove.example_usage = """
    `{prefix}shortcuts remove hello  - removes !hello
    """
    list.example_usage = """
    `{prefix}shortcuts list - lists all shortcuts
    """

    @Cog.listener()
    async def on_ready(self):
        """reload sheets on_ready"""
        pass

    @Cog.listener()
    async def on_message(self, msg):
        """prefix scanner"""
        if not msg.guild or msg.author.bot:
            return
        setting = await self.settings_cache.query_one(guild_id = msg.guild.id)
        if setting is None or not setting.approved:
            return

        c = msg.content
        if len(c) < len(setting.prefix):
            return

        if not c.startswith(setting.prefix):
            return

        shortcuts = await ShortcutEntry.select(guild_id = msg.guild.id)
        if not shortcuts:
            return

        for shortcut in shortcuts:
            if c.lower() == shortcut.name.lower():
                await msg.channel.send(shortcut.value)
                return


class ShortcutSetting(orm.Model):
    """Provides a DB config to track mutes."""
    __tablename__ = 'shortcut_settings'
    __primary_key__ = ("guild_id",)
    guild_id: psqlt.bigint  # guild id
    approved: psqlt.boolean  # whether the guild is approved for the feature or not
    spreadsheet: psqlt.text  # the url of the spreadsheet
    prefix: psqlt.text  # the prefix of the commands


class ShortcutEntry(orm.Model):
    """Provides a DB config to track shortcuts."""
    __tablename__ = 'shortcuts'
    __primary_key__ = ("guild_id", "name")
    guild_id: psqlt.bigint
    name: psqlt.varchar(Shortcuts.MAX_LEN)
    value: psqlt.text


async def setup(bot):
    """Adds the moderation cog to the bot."""
    await bot.add_cog(Shortcuts(bot))
