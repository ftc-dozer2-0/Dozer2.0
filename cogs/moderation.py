"""Provides moderation commands for Dozer."""
import asyncio
import re
import datetime
import time
from typing import Union
from logging import getLogger

import discord
from discord.ext.commands import BadArgument, has_permissions, RoleConverter, guild_only
from discord import app_commands
from discord.ext import commands
from discord.utils import escape_markdown
from loguru import logger

from Components.CustomJoinLeaveMessages import send_log, CustomJoinLeaveMessages
from ._utils import *
from context import DozerContext
import db
from .profile_menus import member_avatar_url
from Components.TeamNumbers import TeamNumbers

blurple = discord.Color.blurple()


class SafeRoleConverter(RoleConverter):
    """Allows for @everyone to be specified without pinging everyone"""

    async def convert(self, ctx: DozerContext, argument):
        try:
            return await super().convert(ctx, argument)
        except BadArgument:
            if argument.casefold() in (
                    'everyone', '@everyone', '@/everyone', '@.everyone', '@ everyone', '@\N{ZERO WIDTH SPACE}everyone'):
                return ctx.guild.default_role
            else:
                raise


# pylint: disable=too-many-public-methods
class Moderation(Cog):
    """A cog to handle moderation tasks."""

    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot
        self.links_config = db.ConfigCache(GuildMessageLinks)
        self.punishment_timer_tasks = []

    """=== Helper functions ==="""

    # todo: clean this up
    async def mod_log(self, actor: discord.Member, action: str, target: Union[discord.User, discord.Member, None],
                      reason, orig_channel=None,
                      embed_color=discord.Color.red(), global_modlog: bool = True, duration: bool = None,
                      dm: bool = True, guild_override: int = None, extra_fields=None, updated_by: discord.Member = None):
        """Generates a modlog embed"""
        modlog_embed = discord.Embed(
            color = embed_color,
            title = f"User {action}!"

        )
        if target is not None:
            modlog_embed.add_field(name = f"{action.capitalize()} user",
                                   value = f"{target.mention} ({target} | {target.id})", inline = False)
        modlog_embed.add_field(name = "Performed by", value = f"{actor.mention} ({actor} | {actor.id})", inline = False)
        if updated_by is not None:
            modlog_embed.add_field(name = "Updated by",
                                   value = f"{updated_by.mention} ({updated_by} | {updated_by.id})", inline = False)
        modlog_embed.add_field(name = "Reason", value = reason or "No reason specified", inline = False)
        modlog_embed.timestamp = datetime.datetime.utcnow()
        if extra_fields is not None:
            for field in extra_fields:
                modlog_embed.add_field(name = field['name'], value = field['value'], inline = field['inline'])
        if duration:
            modlog_embed.add_field(name = "Duration", value = duration)
            modlog_embed.add_field(name = "Expiration",
                                   value = f"<t:{round((datetime.datetime.now() + duration).timestamp())}:R>")
        if target is not None and dm:
            try:
                # Add source guild after Preformed by to embed if the modlog is being sent to a DM
                modlog_embed.insert_field_at(2, name = "Source Guild",
                                             value = f"**{actor.guild.name}** ({actor.guild.id})")
                await target.send(embed = modlog_embed)
                # Remove the source guild line from the embed
            except discord.Forbidden:
                await orig_channel.send("Failed to DM modlog to user")
            finally:
                modlog_embed.remove_field(2)
        modlog_channel = await GuildModLog.get_by(guild_id = actor.guild.id) if guild_override is None else \
            await GuildModLog.get_by(guild_id = guild_override)
        if orig_channel is not None:
            await orig_channel.send(embed = modlog_embed)
        if len(modlog_channel) != 0:
            if global_modlog:
                channel = self.bot.get_guild(actor.guild.id if guild_override is None else guild_override). \
                    get_channel(modlog_channel[0].modlog_channel)
                if channel is not None and channel != orig_channel:  # prevent duplicate embeds
                    try:
                        await channel.send(embed = modlog_embed)
                    except discord.Forbidden as e:
                        logger.warning(
                            f"Unable to send modlog in guild \"{channel.guild}\" ({channel.guild.id}) reason {e}")
        else:
            if orig_channel is not None:
                await orig_channel.send("Please configure modlog channel to enable modlog functionality", ephemeral = True)

    async def perm_override(self, member, **overwrites):
        """Applies the given overrides to the given member in their guild."""
        coros = []
        for channel in member.guild.channels:
            overwrite = channel.overwrites_for(member)
            perms = channel.permissions_for(member.guild.me)
            if perms.manage_roles and perms.manage_channels:
                overwrite.update(**overwrites)
                coros.append(
                    channel.set_permissions(target = member, overwrite = None if overwrite.is_empty() else overwrite))
        try:
            await asyncio.gather(*coros)
        except discord.Forbidden as e:
            getLogger("dozer").error(f"Failed to catch missing permissions: Error ({e}")

    # the below regex and updated hm_to_seconds were borrowed from the frc dozer as well (skhynix#1554)
    hm_regex = re.compile(
        r"((?P<years>\d+)y)?((?P<months>\d+)M)?((?P<weeks>\d+)w)?((?P<days>\d+)d)?((?P<hours>\d+)h)?((?P<minutes>\d+)m)?(("
        r"?P<seconds>\d+)s)?")

    def hm_to_seconds(self, hm_str: str):
        """Converts an hour-minute string to seconds. For example, '1h15m' returns 4500"""
        matches = re.match(self.hm_regex, hm_str).groupdict()
        years = int(matches.get('years') or 0)
        months = int(matches.get('months') or 0)
        weeks = int(matches.get('weeks') or 0)
        days = int(matches.get('days') or 0)
        hours = int(matches.get('hours') or 0)
        minutes = int(matches.get('minutes') or 0)
        seconds = int(matches.get('seconds') or 0)
        val = int((years * 3.154e+7) + (months * 2.628e+6) + (weeks * 604800) + (days * 86400) + (hours * 3600) + (
                minutes * 60) + seconds)
        # Make sure it is a positive number, and it doesn't exceed the max 32-bit int
        return max(0, min(2147483647, val))

    async def punishment_timer(self, seconds, target: discord.Member, punishment, reason, actor: discord.Member,
                               orig_channel = None,
                               global_modlog = True):
        """Asynchronous task that sleeps for a set time to unmute/undeafen a member for a set period of time."""
        if seconds == 0:
            return

        # register the timer
        ent = PunishmentTimerRecords(
            guild_id = target.guild.id,
            actor_id = actor.id,
            target_id = target.id,
            orig_channel_id = orig_channel.id if orig_channel else 0,
            type = punishment.type,
            reason = reason,
            target_ts = int(seconds + time.time()),
            send_modlog = global_modlog
        )
        ent_id = await ent.insert()

        await asyncio.sleep(seconds)

        user = await punishment.select_one(member_id = target.id, guild_id = target.guild.id)
        if user is not None:
            await self.mod_log(actor,
                               "un" + punishment.past_participle,
                               target,
                               reason,
                               orig_channel,
                               embed_color = discord.Color.green(),
                               global_modlog = global_modlog)
            self.bot.loop.create_task(punishment.finished_callback(self, target))
        ent = await PunishmentTimerRecords.select_one(id = ent_id)
        if ent:
            await ent.delete()

    async def _check_links_warn(self, msg, role):
        """Warns a user that they can't send links."""
        await msg.channel.send(f"{msg.author.mention}, you need the `{role.name}` role to post links!", ephemeral = True)

    async def check_links(self, msg):
        """Checks messages for the links role if necessary, then checks if the author is allowed to send links in the
        server"""
        if msg.guild is None or not isinstance(msg.author,
                                               discord.Member) or not msg.guild.me.guild_permissions.manage_messages:
            return

        # this is a dirty hack
        # (let people post links in #robotics-help, #media, #robot-showcase)
        if msg.channel.id in [676583549561995274, 771188718198456321, 761068471252680704]:
            return

        if msg.guild is None or not isinstance(msg.author,
                                               discord.Member) or not msg.guild.me.guild_permissions.manage_messages:
            return
        config = await self.links_config.query_one(guild_id=msg.guild.id)
        if config is None:
            return
        role = msg.guild.get_role(config.role_id)
        if role is None:
            return
        if role not in msg.author.roles and re.search("https?://", msg.content):
            await msg.delete()
            self.bot.loop.create_task(self._check_links_warn(msg, role))
            return True
        return False

    async def check_talking_showcase(self, msg):
        """Checks for messages sent in #robot-showcase without attachments or embeds and automatically deletes them."""
        if (
                msg.channel.id == 771188718198456321 or msg.channel.id == 676583549561995274) and not msg.attachments and not msg.embeds and not re.search(
            "https?://", msg.content):
            await msg.delete()

    """=== context-free backend functions ==="""

    async def _mute(self, member: discord.Member, reason: str = "No reason provided", seconds = 0, actor = None,
                    orig_channel = None):
        """Mutes a user.
        member: the member to be muted
        reason: a reason string without a time specifier
        seconds: a duration of time for the mute to be applied. If 0, then the mute is indefinite. Do not set negative durations.
        actor: the acting user who requested the mute
        orig_channel: the channel of the request origin
        """
        results = await Mute.get_by(guild_id = member.guild.id, member_id = member.id)
        if results:
            await PunishmentTimerRecords.delete(target_id = member.id, guild_id = member.guild.id,
                                                type_of_punishment = Mute.type)
            await self.restart_all_timers()
            self.bot.loop.create_task(
                self.punishment_timer(seconds, member, Mute, reason, actor or member.guild.me,
                                      orig_channel = orig_channel))
            return False  # member already muted, edit preexisting record
        else:
            user = Mute(member_id = member.id, guild_id = member.guild.id)
            await user.update_or_add()
            await self.perm_override(member, send_messages = False, add_reactions = False, speak = False,
                                     stream = False,
                                     create_public_threads = False, create_private_threads = False)

            self.bot.loop.create_task(
                self.punishment_timer(seconds, member, Mute, reason, actor or member.guild.me,
                                      orig_channel = orig_channel))
            return True

    async def _unmute(self, member: discord.Member):
        """Unmutes a user."""
        results = await Mute.get_by(guild_id = member.guild.id, member_id = member.id)
        if results:
            await Mute.delete(member_id = member.id, guild_id = member.guild.id)
            await PunishmentTimerRecords.delete(target_id = member.id, guild_id = member.guild.id,
                                                type_of_punishment = Mute.type)
            await self.perm_override(member, send_messages = None, add_reactions = None, speak = None, stream = None,
                                     create_public_threads = None, create_private_threads = None)
            await self.restart_all_timers()
            return True
        else:
            return False  # member not muted

    async def _deafen(self, member: discord.Member, reason: str = "No reason provided", seconds: int = 0,
                      self_inflicted: bool = False, actor = None,
                      orig_channel = None):
        """Deafens a user.
        member: the member to be deafened
        reason: a reason string without a time specifier
        seconds: a duration of time for the mute to be applied. If 0, then the mute is indefinite. Do not set negative durations.
        self_inflicted: specifies if the deafen is a self-deafen
        actor: the acting user who requested the mute
        orig_channel: the channel of the request origin
        """
        results = await Deafen.get_by(guild_id = member.guild.id, member_id = member.id)
        if results:
            await PunishmentTimerRecords.delete(target_id = member.id, guild_id = member.guild.id,
                                                type_of_punishment = Deafen.type)

            await self.restart_all_timers()
            self.bot.loop.create_task(
                self.punishment_timer(seconds, member,
                                      Deafen,
                                      reason,
                                      actor or member.guild.me,
                                      orig_channel = orig_channel,
                                      global_modlog = not self_inflicted))
            return False
        else:
            user = Deafen(member_id = member.id, guild_id = member.guild.id, self_inflicted = self_inflicted)
            await user.update_or_add()
            await self.perm_override(member, read_messages = False)

            if self_inflicted and seconds == 0:
                seconds = 30  # prevent lockout in case of bad argument
            self.bot.loop.create_task(
                self.punishment_timer(seconds, member,
                                      punishment = Deafen,
                                      reason = reason,
                                      actor = actor or member.guild.me,
                                      orig_channel = orig_channel,
                                      global_modlog = not self_inflicted))
            return True

    async def _undeafen(self, member: discord.Member):
        """Undeafens a user."""
        results = await Deafen.get_by(guild_id = member.guild.id, member_id = member.id)
        if results:
            await self.perm_override(member = member, read_messages = None)
            await PunishmentTimerRecords.delete(target_id = member.id, guild_id = member.guild.id,
                                                type_of_punishment = Deafen.type)
            await self.restart_all_timers()
            await Deafen.delete(member_id = member.id, guild_id = member.guild.id)
            truths = [True, results[0].self_inflicted]
            return truths
        else:
            return [False]

    """=== Event handlers ==="""

    @Cog.listener('on_ready')
    async def on_ready(self):
        """Restore punishment timers on bot startup and trigger the nm purge cycle"""
        await self.start_punishment_timers()

    async def start_punishment_timers(self):
        """Starts all punishment timers"""
        q = await PunishmentTimerRecords.get_by()  # no filters: all
        for r in q:
            guild = self.bot.get_guild(r.guild_id)
            actor = guild.get_member(r.actor_id)
            target = guild.get_member(r.target_id)
            orig_channel = self.bot.get_channel(r.orig_channel_id)
            punishment_type = r.type_of_punishment
            reason = r.reason or ""
            seconds = max(int(r.target_ts - time.time()), 0.01)
            await PunishmentTimerRecords.delete(id = r.id)
            self.bot.loop.create_task(
                self.punishment_timer(seconds, target, PunishmentTimerRecords.type_map[punishment_type], reason, actor,
                                      orig_channel))
            logger.info(
                f"Restarted {PunishmentTimerRecords.type_map[punishment_type].__name__} of {target} in {guild}")

    async def restart_all_timers(self):
        """Restarts all timers"""
        logger.info("Restarting all timers")
        for timer in self.punishment_timer_tasks:
            # timer: asyncio.Task
            logger.info(f"Stopping \"{timer.get_name()}\"")
        for timer in self.punishment_timer_tasks:
            timer.cancel()
        self.punishment_timer_tasks = []
        await self.start_punishment_timers()

    async def punishment_timer(self, seconds: int, target: discord.Member, punishment, reason: str,
                               actor: discord.Member, orig_channel = None,
                               global_modlog: bool = True):
        """Asynchronous task that sleeps for a set time to unmute/undeafen a member for a set period of time."""

        # Add this task to the list of active timer tasks
        asyncio.current_task().set_name(f"PunishmentTimer for {target}")
        self.punishment_timer_tasks.append(asyncio.current_task())

        logger.info(
            f"Starting{' self' if not global_modlog else ''} {punishment.__name__} timer of \"{target}\" in \"{target.guild}\" will "
            f"expire in {seconds} seconds")

        if seconds == 0:
            return

        # register the timer
        ent = PunishmentTimerRecords(
            guild_id = target.guild.id,
            actor_id = actor.id,
            target_id = target.id,
            orig_channel_id = orig_channel.id if orig_channel else 0,
            type_of_punishment = punishment.type,
            reason = reason,
            target_ts = int(seconds + time.time()),
            self_inflicted = not global_modlog
        )
        await ent.update_or_add()

        await asyncio.sleep(seconds)

        user = await punishment.get_by(member_id = target.id)
        if len(user) != 0:
            await self.mod_log(actor = actor,
                               action = "un" + punishment.past_participle,
                               target = target,
                               reason = reason,
                               orig_channel = orig_channel,
                               embed_color = discord.Color.green(),
                               global_modlog = global_modlog)

            self.punishment_timer_tasks.remove(asyncio.current_task())
            self.bot.loop.create_task(coro = punishment.finished_callback(self, target))
        if ent:
            await PunishmentTimerRecords.delete(guild_id = target.guild.id, target_id = target.id,
                                                type_of_punishment = punishment.type)

    @Cog.listener('on_member_join')
    async def on_member_join(self, member: discord.Member):
        """Logs that a member joined."""
        users = await Mute.get_by(guild_id = member.guild.id, member_id = member.id)
        if users:
            await self.perm_override(member, add_reactions = False, send_messages = False)
        users = await Deafen.get_by(guild_id = member.guild.id, member_id = member.id)
        if users:
            await self.perm_override(member, read_messages = False)

    @Cog.listener()
    async def on_member_remove(self, member):
        """Logs that a member left."""
        leave = discord.Embed(type = 'rich', color = 0xFF0000)
        leave.set_author(name = 'Member Left', icon_url = member_avatar_url(member))
        leave.description = "{0.mention}\n{0} ({0.id})".format(member)
        leave.set_footer(text = "{} | {} members".format(member.guild.name, member.guild.member_count))

        config = await self.guild_config.query_one(guild_id = member.guild.id)
        if config is not None and config.member_log_channel_id is not None:
            channel = member.guild.get_channel(config.member_log_channel_id)
            await channel.send(embed = leave)

    @Cog.listener('on_message')
    async def on_message(self, message: discord.Message):
        """Check things when messages come in."""
        if message.author.bot or message.guild is None or not message.guild.me.guild_permissions.manage_roles:
            return
        if await self.check_links(message):
            return
        config = await GuildNewMember.get_by(guild_id = message.guild.id)
        ctx = await self.bot.get_context(message)
        if len(config) != 0:
            config = config[0]
            string = config.message
            content = message.content.casefold()
            if string not in content:
                return
            channel = config.channel_id
            role_id = config.role_id
            if message.channel.id != channel:
                return
            if config.require_team:
                teams = await TeamNumbers.get_by(user_id = message.author.id)
                if len(teams) == 0:
                    if ctx.prefix is None:
                        ctx.prefix = self.bot.config['prefix']
                    await message.reply(f"You must set a team number first. ex: `{ctx.prefix}setteam frc 0`")
                    return

            custom_log_config = await CustomJoinLeaveMessages.get_by(guild_id = message.guild.id)

            await message.author.add_roles(message.guild.get_role(role_id))
            if custom_log_config[0].send_on_verify:
                await send_log(member = message.author)

    @Cog.listener()
    async def on_message_delete(self, message):
        """When a message is deleted, log it."""
        if self.bot.user == message.author or not message.guild:
            return
        e = discord.Embed(type = 'rich', title = 'Message Deleted', color = 0xff0000)
        e.timestamp = datetime.datetime.utcnow()
        e.set_author(name = f"{message.author} in #{message.channel}", icon_url = member_avatar_url(message.author))
        e.add_field(name = 'Channel link', value = message.channel.mention)
        e.add_field(name = 'Author pingable', value = message.author.mention)

        if len(message.content) > 0:
            e.description = message.content
        elif len(message.content) == 0:
            for i in message.embeds:
                e.add_field(name = "Title", value = i.title)
                e.add_field(name = "Description", value = i.description)
                e.add_field(name = "Timestamp", value = i.timestamp)
                for x in i.fields:
                    e.add_field(name = x.name, value = x.value)
                e.add_field(name = "Footer", value = i.footer)
        if message.attachments:
            e.add_field(name = "Attachments", value = ", ".join([i.url for i in message.attachments]))

        config = await self.guild_config.query_one(guild_id = message.guild.id)
        if config is not None and config.message_log_channel_id is not None:
            channel = message.guild.get_channel(config.message_log_channel_id)
            if channel is not None:
                await channel.send(embed = e)

    @Cog.listener()
    async def on_message_edit(self, before, after):
        """Logs message edits."""
        await self.check_links(after)
        if before.author.bot or not before.guild:
            return
        if after.edited_at is not None or before.edited_at is not None:
            # There is a reason for this. That reason is that otherwise, an infinite spam loop occurs
            e = discord.Embed(type = 'rich', title = 'Message Edited', color = 0xffc400)
            e.timestamp = after.edited_at
            e.set_author(name = f"{before.author} in #{before.channel}", icon_url = member_avatar_url(before.author))

            if 1024 > len(before.content) > 0:
                e.add_field(name = "Old message", value = before.content)
            elif len(before.content) != 0:
                e.add_field(name = "Old message", value = before.content[0:1023])
                e.add_field(name = "Old message continued", value = before.content[1024:2000])
            elif len(before.content) == 0 and before.edited_at is not None:
                for i in before.embeds:
                    e.add_field(name = "Title", value = i.title)
                    e.add_field(name = "Description", value = i.description)
                    e.add_field(name = "Timestamp", value = i.timestamp)
                    for x in i.fields:
                        e.add_field(name = x.name, value = x.value)
                    e.add_field(name = "Footer", value = i.footer)
            if before.attachments:
                e.add_field(name = "Attachments", value = ", ".join([i.url for i in before.attachments]))
            if 0 < len(after.content) < 1024:
                e.add_field(name = "New message", value = after.content)
            elif len(after.content) != 0:
                e.add_field(name = "New message", value = after.content[0:1023])
                e.add_field(name = "New message continued", value = after.content[1024:2000])
            elif len(after.content) == 0 and after.edited_at is not None:
                for i in after.embeds:
                    e.add_field(name = "Title", value = i.title)
                    e.add_field(name = "Description", value = i.description)
                    e.add_field(name = "Timestamp", value = i.timestamp)
                    for x in i.fields:
                        e.add_field(name = x.name, value = x.value)
            if after.attachments:
                e.add_field(name = "Attachments", value = ", ".join([i.url for i in before.attachments]))
            e.add_field(name = 'Channel link', value = before.channel.mention)
            e.add_field(name = 'Author pingable', value = before.author.mention)

            config = await self.guild_config.query_one(guild_id = before.guild.id)
            if config is not None and config.message_log_channel_id is not None:
                channel = before.guild.get_channel(config.message_log_channel_id)
                if channel is not None:
                    await channel.send(embed = e)

    """=== Direct moderation commands ==="""

    @commands.hybrid_command(aliases = ["warning"])
    @has_permissions(kick_members = True)
    @app_commands.describe(member = "The member to warn", reason = "The reason for the warning")
    async def warn(self, ctx, member: discord.Member, *, reason):
        """Sends a message to the mod log specifying the member has been warned without punishment."""
        await self.mod_log(actor = ctx.author, action = "warned", target = member, orig_channel = ctx.channel,
                           reason = reason)

    warn.example_usage = """
    `{prefix}warn @user reason` - warns a user for "reason"
    """

    @commands.hybrid_command(aliases = ["purge", "clear"])
    @has_permissions(manage_messages = True)
    @bot_has_permissions(manage_messages = True, read_message_history = True)
    @app_commands.describe(num_to_delete = "The amount of messages to delete")
    async def prune(self, ctx, num_to_delete: int):
        """Bulk delete a set number of messages from the current channel."""
        if num_to_delete > 100:
            await ctx.send("Cannot purge more than 100 messages!")
            return

        await ctx.message.channel.purge(limit = num_to_delete + 1)
        await ctx.send(
            "Deleted {n} messages under request of {user}".format(n = num_to_delete, user = ctx.message.author.mention),
            delete_after = 5)

    prune.example_usage = """
    `{prefix}prune 10` - Delete the last 10 messages in the current channel.
    """

    @command(aliases = ["clearreacts"])
    @has_permissions(manage_messages = True)
    @bot_has_permissions(manage_messages = True)
    @app_commands.describe(message_id = "The message to clear reactions from",
                           channel = "(optional) The channel the message is in")
    async def clearreactions(self, ctx, message_id: int, channel: discord.TextChannel = None):
        """Clear the reactions from a message, given its id and optionally a channel."""
        chn = channel or ctx.channel
        try:
            message = await chn.fetch_message(message_id)
        except discord.NotFound:
            await ctx.send(f"Message {message_id} not found in channel {chn.mention}!")
            return
        await message.clear_reactions()
        await ctx.send(f"Cleared reactions from message {message_id}")

    clearreactions.example_usage = """
    `{prefix}clearreactions 481021088046907392 #general` - clear all reactions from messageid 481021088046907392 in #general
    """

    @commands.hybrid_command(aliases = ["bulkclearreacts"])
    @has_permissions(manage_messages = True)
    @bot_has_permissions(manage_messages = True)
    @app_commands.describe(num_to_clear = "The number of messages to clear reactions from",
                           channel = "(optional) The channel to clear reactions from")
    async def bulkclearreactions(self, ctx, num_to_clear: int, channel: discord.TextChannel = None):
        """Clears the reactions of the last x messages in a channel"""
        chn = channel or ctx.channel
        async for message in chn.history(limit = num_to_clear):
            await message.clear_reactions()
        await ctx.send(f"Cleared reactions on {num_to_clear} messages in {chn.mention}")

    bulkclearreactions.example_usage = """
    `{prefix}bulkclearreactions 50 #general` - clear all reactions from the last 50 messages in #general
    """

    # this is all already underneath the class, moderation

    @commands.hybrid_group(name = "channel", invoke_without_command = True, case_insensitive = True)
    async def channel_group(self, ctx):
        """Manages channel settings."""
        await ctx.send_help(ctx.command)

    @channel_group.command(name = "slowmode")
    @has_permissions(manage_roles = True)
    @bot_has_permissions(manage_channels = True)
    async def slowmode(self, ctx, slowmode_delay: int):
        """Set the slowmode message delay for the current channel. Passing 0 disables slowmode."""
        await ctx.channel.edit(slowmode_delay = slowmode_delay,
                               reason = f"Adjusted slowmode at request of {ctx.author}")

    slowmode.example_usage = """
    `{prefix}slowmode 20` - set slowmode to 20 seconds per message per user
    """

    @channel_group.command(name = "timeout")
    @has_permissions(manage_roles = True)
    @bot_has_permissions(manage_roles = True)
    @app_commands.describe(duration = "The duration of the timeout in seconds")
    async def timeout(self, ctx: DozerContext, duration: float):
        """Set a timeout (no sending messages or adding reactions) on the current channel."""
        settings = await MemberRole.get_by(guild_id = ctx.guild.id)
        if len(settings) == 0:
            settings = MemberRole(guild_id = ctx.guild.id, member_role = MemberRole.nullify)
            await settings.update_or_add()
        else:
            settings = settings[0]
        # None-safe - nonexistent or non-configured role return None
        member_role = ctx.guild.get_role(settings.member_role)
        if member_role is not None:
            targets = {member_role}
        else:
            await ctx.send(
                f'{ctx.author.mention}, the members role has not been configured. This may not work as expected. Use '
                f'`{ctx.prefix}help memberconfig` to see how to set this up.')
            targets = set(sorted(ctx.guild.roles)[:ctx.author.top_role.position])

        to_restore = [(target, ctx.channel.overwrites_for(target)) for target in targets]
        for target, overwrite in to_restore:
            new_overwrite = discord.PermissionOverwrite.from_pair(*overwrite.pair())
            new_overwrite.update(send_messages = False, add_reactions = False)
            await ctx.channel.set_permissions(target, overwrite = new_overwrite)

        for allow_target in (ctx.me, ctx.author):
            overwrite = ctx.channel.overwrites_for(allow_target)
            new_overwrite = discord.PermissionOverwrite.from_pair(*overwrite.pair())
            new_overwrite.update(send_messages = True)
            await ctx.channel.set_permissions(allow_target, overwrite = new_overwrite)
            to_restore.append((allow_target, overwrite))

        e = discord.Embed(title = f'Timeout - {duration}s', description = 'This channel has been timed out.',
                          color = discord.Color.blue())
        e.set_author(name = escape_markdown(ctx.author.display_name),
                     icon_url = ctx.author.display_avatar.replace(format = 'png', size = 32))
        msg = await ctx.send(embed = e)

        await asyncio.sleep(duration)

        for target, overwrite in to_restore:
            if all(permission is None for _, permission in overwrite):
                await ctx.channel.set_permissions(target, overwrite = None)
            else:
                await ctx.channel.set_permissions(target, overwrite = overwrite)

        e.description = 'The timeout has ended.'
        await msg.edit(embed = e)

    timeout.example_usage = """
           `{prefix}timeout 60` - prevents sending messages in this channel for 1 minute (60s)
           """

    @command(aliases = ["eject"])
    @guild_only()
    @has_permissions(ban_members = True)
    @bot_has_permissions(ban_members = True)
    @app_commands.describe(user_mention = "The user to ban", reason = "(optional) The reason for the ban")
    async def ban(self, ctx, user_mention: discord.User, *, reason = "No reason provided"):
        """Bans the user mentioned."""
        member = ctx.guild.get_member(user_mention.id)
        if member and member.top_role >= ctx.guild.me.top_role:
            await ctx.send(f"{ctx.author.mention}, this user's top role is the same as or higher than mine!")
            return
        await self.mod_log(actor = ctx.author, action = "banned", target = user_mention, reason = reason,
                           orig_channel = ctx.channel)
        await ctx.guild.ban(user_mention, reason = reason, delete_message_days = 0)

    ban.example_usage = """
    `{prefix}ban @user reason` - ban @user for a given (optional) reason
    """

    @commands.hybrid_command()
    @has_permissions(ban_members = True)
    @bot_has_permissions(ban_members = True)
    @app_commands.describe(user_mention = "The user to unban", reason = "(optional) The reason for the unban")
    async def unban(self, ctx, user_mention: discord.User, *, reason = "No reason provided"):
        """Unbans the user mentioned."""
        await ctx.guild.unban(user_mention, reason = reason)
        await self.mod_log(actor = ctx.author, action = "unbanned", target = user_mention, reason = reason,
                           orig_channel = ctx.channel, embed_color = discord.Color.green())

    unban.example_usage = """
    `{prefix}unban user_id reason` - unban the user corresponding to the ID for a given (optional) reason
    """

    @commands.hybrid_command(aliases = ["dropkick", "boot"])
    @has_permissions(kick_members = True)
    @bot_has_permissions(kick_members = True)
    @app_commands.describe(user_mention = "The user to kick", reason = "(optional) The reason for the kick")
    async def kick(self, ctx, user_mention: discord.User, *, reason = "No reason provided"):
        """Kicks the user mentioned."""
        member = ctx.guild.get_member(user_mention.id)
        if member and member.top_role >= ctx.guild.me.top_role:
            await ctx.send(f"{ctx.author.mention}, this user's top role is the same as or higher than mine!")
            return
        await self.mod_log(actor = ctx.author, action = "kicked", target = user_mention, reason = reason,
                           orig_channel = ctx.channel)
        await ctx.guild.kick(user_mention, reason = reason)

    kick.example_usage = """
    `{prefix}kick @user reason` - kick @user for a given (optional) reason
    """

    @commands.hybrid_command(aliases = ["muteuser", "silence"])
    @has_permissions(manage_roles = True)
    @bot_has_permissions(manage_roles = True)
    @app_commands.describe(member_mentions = "The user to mute", reason = "(optional) The reason for the mute")
    async def mute(self, ctx, member_mentions: discord.Member, *, reason = "No reason provided"):
        """Mute a user to prevent them from sending messages"""
        async with ctx.typing():
            seconds = self.hm_to_seconds(reason)
            reason = self.hm_regex.sub(reason, "") or "No reason provided"
            if await self._mute(member_mentions, reason = reason, seconds = seconds, actor = ctx.author,
                                orig_channel = ctx.channel):
                await self.mod_log(ctx.author, "muted", member_mentions, reason, ctx.channel, discord.Color.red())
            else:
                await ctx.send("Member is already muted!")

    mute.example_usage = """
    `{prefix}mute @user 1h reason` - mute @user for 1 hour for a given reason, the timing component (1h) and reason is optional.
    """

    @commands.hybrid_command(aliases = ["unmuteuser", "unsilence"])
    @has_permissions(manage_roles = True)
    @bot_has_permissions(manage_roles = True)
    @app_commands.describe(member_mentions = "The user to unmute", reason = "(optional) The reason for the unmute")
    async def unmute(self, ctx, member_mentions: discord.Member, reason = "No reason provided"):
        """Unmute a user to allow them to send messages again."""
        async with ctx.typing():
            if await self._unmute(member_mentions):
                await self.mod_log(actor = ctx.author, action = "unmuted", target = member_mentions, reason = reason,
                                   orig_channel = ctx.channel, embed_color = discord.Color.green())
            else:
                await ctx.send("Member is not muted!")

    unmute.example_usage = """
    `{prefix}unmute @user reason` - unmute @user for a given (optional) reason
    """

    @commands.hybrid_command()
    @has_permissions(manage_roles = True)
    @bot_has_permissions(manage_roles = True)
    @app_commands.describe(member_mentions = "User to deafen", reason = "(optional) The reason for the deafen")
    async def deafen(self, ctx, member_mentions: discord.Member, *, reason = "No reason provided"):
        """Deafen a user to prevent them from both sending messages but also reading messages."""
        async with ctx.typing():
            seconds = self.hm_to_seconds(reason)
            reason = self.hm_regex.sub(reason, "") or "No reason provided"
            if await self._deafen(member_mentions, reason, seconds = seconds, self_inflicted = False,
                                  actor = ctx.author, orig_channel = ctx.channel):
                await self.mod_log(ctx.author, "deafened", member_mentions, reason, ctx.channel, discord.Color.red())
            else:
                await ctx.send("Member is already deafened!")

    deafen.example_usage = """
    `{prefix}deafen @user 1h reason` - deafen @user for 1 hour for a given reason, the timing component (1h) is optional.
    """

    @commands.hybrid_command()
    @bot_has_permissions(manage_roles = True)
    @app_commands.describe(reason = "(optional) The reason for deafening yourself")
    async def selfdeafen(self, ctx, *, reason = "No reason provided"):
        """Prevent yourself from both sending and reading messages; Useful as a study tool"""
        async with ctx.typing():
            seconds = self.hm_to_seconds(reason)

            if seconds == 0:
                await ctx.send("You need to specify a duration!")
                return

            reason = self.hm_regex.sub(reason, "") or "No reason provided"
            if await self._deafen(ctx.author, reason, seconds = seconds, self_inflicted = True, actor = ctx.author,
                                  orig_channel = ctx.channel):
                await self.mod_log(ctx.author, "deafened", ctx.author, reason, ctx.channel, discord.Color.red(),
                                   global_modlog = False)
            else:
                await ctx.send("You are already deafened!", ephemeral = True)

    selfdeafen.example_usage = """
    `{prefix}selfdeafen time (1h5m, both optional) reason` - deafens you if you need to get work done
    """

    @commands.hybrid_command()
    @has_permissions(manage_roles = True)
    @bot_has_permissions(manage_roles = True)
    @app_commands.describe(member_mentions = "User to undeafen", reason = "(optional) The reason for undeafening")
    async def undeafen(self, ctx, member_mentions: discord.Member, reason = "No reason provided"):
        """Undeafen a user to allow them to see message and send message again."""
        async with ctx.typing():
            if await self._undeafen(member_mentions):
                await self.mod_log(actor = ctx.author, action = "undeafened", target = member_mentions, reason = reason,
                                   orig_channel = ctx.channel, embed_color = discord.Color.green())
            else:
                await ctx.send("Member is not deafened!")

    undeafen.example_usage = """
    `{prefix}undeafen @user reason` - undeafen @user for a given (optional) reason
    """

    @commands.hybrid_command()
    @has_permissions(manage_roles = True)
    @bot_has_permissions(manage_roles = True)
    @app_commands.describe(member_mentions = "User to undeafen", reason = "(optional) The reason for silent undeafen")
    async def silentundeafen(self, ctx, member_mentions: discord.Member, reason = "No reason provided"):
        """Undeafen a user to allow them to see message and send message again, without modlog post"""
        async with ctx.typing():
            if await self._undeafen(member_mentions):
                await self.mod_log(actor = ctx.author, action = "undeafened", target = member_mentions, reason = reason,
                                   orig_channel = ctx.channel, embed_color = discord.Color.green(),
                                   global_modlog = False)
            else:
                await ctx.send("Member is not deafened!", ephemeral = True)

    silentundeafen.example_usage = """
    `{prefix}silentundeafen @user reason` - undeafen @user for a given (optional) reason, without sending it to global modlogs
    """

    @commands.hybrid_command()
    @has_permissions(manage_roles = True)
    @bot_has_permissions(manage_roles = True)
    @app_commands.describe(member = "User to kick", reason = "(optional) The reason for kicking")
    async def voicekick(self, ctx, member: discord.Member, reason = "No reason provided"):
        """Kick a user from voice chat. This is most useful if their perms to rejoin have already been removed."""
        async with ctx.typing():
            if member.voice is None:
                await ctx.send("User is not in a voice channel!")
                return
            if not member.voice.channel.permissions_for(ctx.author).move_members:
                await ctx.send("You do not have permission to do this!")
                return
            if not member.voice.channel.permissions_for(ctx.me).move_members:
                await ctx.send("I do not have permission to do this!")
                return
            await member.edit(voice_channel = None, reason = reason)
            await ctx.send(f"{member} has been kicked from voice chat.")

    voicekick.example_usage = """
    `{prefix}voicekick @user reason` - kick @user out of voice
    """

    @commands.hybrid_command()
    @guild_only()
    @has_permissions(manage_roles = True)
    async def punishments(self, ctx: DozerContext):
        """List currently active mutes and deafens in a guild"""
        punishments = await PunishmentTimerRecords.get_by(guild_id = ctx.guild.id)
        deafen_records = await Deafen.get_by(guild_id = ctx.guild.id)
        self_inflicted = [record.member_id for record in deafen_records if record.self_inflicted]
        deafens = [punishment for punishment in punishments if
                   punishment.type_of_punishment == 2 and punishment.target_id not in self_inflicted]
        self_deafens = [punishment for punishment in punishments if
                        punishment.type_of_punishment == 2 and punishment.target_id in self_inflicted]
        mutes = [punishment for punishment in punishments if punishment.type_of_punishment == 1]
        embed = discord.Embed(title = f"Active punishments in {ctx.guild}", color = blurple)
        embed.set_footer(text = 'Triggered by ' + ctx.author.display_name)

        def get_mention(target_id):
            member = ctx.guild.get_member(target_id)
            if member:
                return member.mention
            else:
                return "**Member left**"

        def get_name(target_id):
            user = ctx.bot.get_user(target_id)
            if user:
                return user
            else:
                return "**Unknown#NONE**"

        for field_number, punishments in enumerate(chunk(deafens, 3)):
            embed.add_field(name = f"Deafens - {len(deafens)}", value = '\n-\n'.join(
                f"{get_mention(punishment.target_id)} ({get_name(punishment.target_id)} | {punishment.target_id}) "
                f"\nExpires: <t:{round(punishment.target_ts)}:R> Reason: {punishment.reason}"
                for punishment in punishments) or 'None', inline = False)

        for field_number, punishments in enumerate(chunk(mutes, 3)):
            embed.add_field(name = f"Mutes - {len(mutes)}", value = '\n-\n'.join(
                f"{get_mention(punishment.target_id)} ({get_name(punishment.target_id)} | {punishment.target_id}) "
                f"\nExpires: <t:{round(punishment.target_ts)}:R> Reason: {punishment.reason}"
                for punishment in punishments) or 'None', inline = False)

        for field_number, punishments in enumerate(chunk(self_deafens, 3)):
            embed.add_field(name = f"Self Deafens - {len(self_deafens)}", value = '\n-\n'.join(
                f"{get_mention(punishment.target_id)} ({get_name(punishment.target_id)} | {punishment.target_id}) "
                f"\nExpires: <t:{round(punishment.target_ts)}:R> Reason: {punishment.reason}"
                for punishment in punishments) or 'None', inline = False)

        await ctx.send(embed = embed)

    punishments.example_usage = """
       `{prefix}punishments:` Lists currently active punishments in current guild
       """

    """=== Configuration commands ==="""

    @has_permissions(manage_guild = True)
    @commands.hybrid_group(invoke_without_command = True, aliases = ("GuildModLog",), case_insensitive = True)
    async def serverconfig(self, ctx):
        """Display server configuration information"""
        guild = ctx.guild
        e = discord.Embed()
        e.color = discord.Color.blurple()
        e.title = f"Server-specific bot settings for {guild.name}"
        e.description = f"To change these settings, see `{ctx.prefix}help serverconfig` for details."
        e.set_thumbnail(url = ctx.guild.icon.url)
        config = await self.guild_config.query_one(guild_id = guild.id)
        if not config:
            config = GuildModLog.make_defaults(guild)
            await config.insert()
        if not config.guild_name:
            config.guild_name = guild.name
            await config.update()
        self.guild_config.invalidate_entry(guild_id = ctx.guild.id)

        def role_ent(rid):
            if not rid:
                return "Unset"
            if rid == ctx.guild.id:
                return "@everyone"
            return f"<@&{rid}>"

        def channel_ent(cid):
            if not cid:
                return "Unset"
            return f"<#{cid}>"

        e.add_field(name = "New members channel", value = channel_ent(config.new_members_channel_id))
        e.add_field(name = "New members given role", value = role_ent(config.new_members_role_id))
        e.add_field(name = "New members entry message", value = config.new_members_message or "Unset")

        e.add_field(name = "Mod log", value = channel_ent(config.mod_log_channel_id))
        e.add_field(name = "Member log", value = channel_ent(config.member_log_channel_id))
        e.add_field(name = "Edit/delete log", value = channel_ent(config.message_log_channel_id))

        e.add_field(name = "Invite welcome channel", value = channel_ent(config.welcome_channel_id))
        e.add_field(name = "Member role", value = role_ent(config.member_role_id))
        e.add_field(name = "Links role", value = role_ent(config.links_role_id))
        await ctx.send(embed = e)

    serverconfig.example_usage = """
    `{prefix}serverconfig` - display server configuration information
    `{prefix}serverconfig unset modlog` - unset the modlog channel
    """

    @serverconfig.command()
    @has_permissions(administrator = True)
    @app_commands.describe(setting = "The setting to remove")
    async def unset(self, ctx, setting):
        """Unsets various server config settings."""
        fields = {
            "links": ("links_role_id",),
            "memberlog": ("member_log_channel_id",),
            "memberrole": ("member_role_id",),
            "messagelog": ("message_log_channel_id",),
            "modlog": ("mod_log_channel_id",),
            "newmem": ("new_members_channel_id", "new_members_role_id", "new_members_message"),
        }.get(setting, None)
        if fields is None:
            raise BadArgument("that guild-specific bot setting does not exist!")
        config = await self.guild_config.query_one(guild_id = ctx.guild.id)
        if config:
            for field in fields:
                setattr(config, field, None)
            if setting == "memberrole":
                config.member_role_id = ctx.guild.id
            await config.update()
        self.guild_config.invalidate_entry(guild_id = ctx.guild.id)
        await ctx.send(f"Unset configuration for setting `{setting}`")

    unset.example_usage = """
    `{prefix}serverconfig unset newmem` - disable new member message verification
    `{prefix}serverconfig unset memberlog` - disable member join/leave logs
    `{prefix}serverconfig unset messagelog` - disable edit/delete logs
    `{prefix}serverconfig unset modlog` - clear mod log settings
    `{prefix}serverconfig unset memberrole` - reset the member role back to @everyone
    `{prefix}serverconfig unset links` - clear links role settings
    """

    @serverconfig.command(name = "modlog")
    @has_permissions(administrator = True)
    @app_commands.describe(channel_mentions = "The channel to log moderation actions to")
    async def modlogconfig(self, ctx, channel_mentions: discord.TextChannel):
        """Set the modlog channel for a server by passing the channel id"""
        config = await GuildModLog.get_by(guild_id=ctx.guild.id)
        if len(config) != 0:
            config = config[0]
            config.name = ctx.guild.name
            config.modlog_channel = channel_mentions.id
        else:
            config = GuildModLog(guild_id=ctx.guild.id, modlog_channel=channel_mentions.id, name=ctx.guild.name)
        await config.update_or_add()
        await ctx.send(ctx.message.author.mention + ', modlog settings configured!', ephemeral=True)

    modlogconfig.example_usage = """
    `{prefix}serverconfig modlog #mod-log` - set a channel named #mod-log to log moderation actions
    `{prefix}serverconfig unset modlog` - clear the modlog settings
    """

    @serverconfig.command(name = "newmem")
    @has_permissions(administrator = True)
    @app_commands.describe(channel_mention = "The channel to send new member verification messages to",
                           role = "role to give when a user verifies", message = "The message to send to new members")
    async def nmconfig(self, ctx, channel_mention: discord.TextChannel, role: discord.Role, *, message):
        """Sets the config for the new members channel"""

        await GuildModLog.update_guild(ctx.guild, new_members_channel_id = channel_mention.id,
                                       new_members_role_id = role.id, new_members_message = message.casefold())

        role_name = role.name
        await ctx.send(
            "New Member Channel configured as: {channel}. Role configured as: {role}. Message: {message}".format(
                channel = channel_mention.name, role = role_name, message = message))

    nmconfig.example_usage = """
    `{prefix}serverconfig newmem #new_members Member I have read the rules and regulations`""" + \
                             """ - Configures the #new_members channel so if someone types "I have read the rules and regulations" it assigns them the Member role.
    `{prefix}serverconfig unset newmem` - Clear any settings back to default
    """

    @serverconfig.command(name = "memberrole")
    @has_permissions(administrator = True)
    @app_commands.describe(member_role = "The role to assign to members")
    async def memberconfig(self, ctx, *, member_role: SafeRoleConverter):
        """
        Set the member role for the guild.
        The member role is the role used for the timeout and pttlimit commands. It should be a role that all members of the server have.
        """
        if member_role >= ctx.author.top_role:
            raise BadArgument('member role cannot be higher than your top role!')

        await GuildModLog.update_guild(ctx.guild, member_role_id = member_role.id)
        await ctx.send('Member role set as `{}`.'.format(member_role.name))

    memberconfig.example_usage = """
    `{prefix}serverconfig memberrole Members` - set a role called "Members" as the member role
    `{prefix}serverconfig memberrole @everyone` - set the default role as the member role
    `{prefix}serverconfig memberrole everyone` - set the default role as the member role (ping-safe)
    `{prefix}serverconfig memberrole @ everyone` - set the default role as the member role (ping-safe)
    `{prefix}serverconfig memberrole @.everyone` - set the default role as the member role (ping-safe)
    `{prefix}serverconfig memberrole @/everyone` - set the default role as the member role (ping-safe)
    `{prefix}serverconfig unset memberrole` - equivalent to `{prefix}serverconfig memberrole everyone`
    """

    @serverconfig.command(name = "links")
    @has_permissions(administrator = True)
    @bot_has_permissions(manage_messages = True)
    @app_commands.describe(link_role = "The role that lets users post links")
    async def linkscrubconfig(self, ctx, *, link_role: SafeRoleConverter):
        """
        Set a role that users must have in order to post links.
        This accepts the safe default role conventions that serverconfig memberrole does.
        """
        if link_role >= ctx.author.top_role:
            raise BadArgument('Link role cannot be higher than your top role!')

        await GuildModLog.update_guild(ctx.guild, links_role_id = link_role.id)
        await ctx.send(f'Link role set as `{link_role.name}`.')

    linkscrubconfig.example_usage = """
    `{prefix}serverconfig links Links` - set a role called "Links" as the link role
    `{prefix}serverconfig links @everyone` - set the default role as the link role
    `{prefix}serverconfig links everyone` - set the default role as the link role (ping-safe)
    `{prefix}serverconfig links @ everyone` - set the default role as the link role (ping-safe)
    `{prefix}serverconfig links @.everyone` - set the default role as the link role (ping-safe)
    `{prefix}serverconfig links @/everyone` - set the default role as the link role (ping-safe)
    `{prefix}serverconfig unset links` - equivalent to `{prefix}serverconfig links everyone`
    """

    @serverconfig.command(name = "memberlog")
    @has_permissions(administrator = True)
    @app_commands.describe(channel_mentions = "The channel to log member join/leave events to")
    async def memberlogconfig(self, ctx, channel_mentions: discord.TextChannel):
        """Set the join/leave channel for a server by passing a channel mention"""
        await GuildModLog.update_guild(ctx.guild, member_log_channel_id = channel_mentions.id)
        await ctx.send(ctx.message.author.mention + ', memberlog settings configured!')

    memberlogconfig.example_usage = """
    `{prefix}serverconfig memberlog #join-leave-logs` - set a channel named #join-leave-logs to log joins/leaves 
    `{prefix}serverconfig unset memberlog` - disable this behavior
    """

    @serverconfig.command(name = "messagelog")
    @has_permissions(administrator = True)
    @app_commands.describe(channel_mentions = "The channel to log message edits/deletes to")
    async def messagelogconfig(self, ctx: DozerContext, channel_mentions: discord.TextChannel):
        """Set the modlog channel for a server by passing the channel id"""
        await GuildModLog.get_by(guild_id = ctx.guild.id, message_log_channel_id = channel_mentions.id)
        await ctx.send(ctx.message.author.mention + ', messagelog settings configured!')

    messagelogconfig.example_usage = """
    `{prefix}serverconfig messagelog #edit-delete-logs` - set a channel named #edit-delete-logs to log message edits/deletions
    `{prefix}serverconfig unset messagelog` - disable this behavior
    """

    @serverconfig.command(name = "welcome")
    @has_permissions(administrator = True)
    @app_commands.describe(welcome_channel = "The channel to send welcome messages to")
    async def welcomeconfig(self, ctx: DozerContext, *, welcome_channel: discord.TextChannel):
        """
        Sets the new member channel for this guild.
        """
        if welcome_channel.guild != ctx.guild:
            await ctx.send("That channel is not in this guild.")
            return

        await GuildModLog.get_by(guild_id = ctx.guild.id, welcome_channel_id = welcome_channel.id)
        await ctx.send("Welcome channel set to {}".format(welcome_channel.mention))

    welcomeconfig.example_usage = """
    `{prefix}serverconfig welcome #new-members` - Sets the invite channel to #new-members.
    """


class GuildModLog(db.DatabaseTable):
    """Holds modlog info"""
    __tablename__ = 'modlogconfig'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,
            modlog_channel bigint null,
            name varchar NOT NULL
            )""")

    def __init__(self, guild_id: int, modlog_channel: int, name: str):
        super().__init__()
        self.guild_id = guild_id
        self.modlog_channel = modlog_channel
        self.name = name

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = GuildModLog(guild_id=result.get("guild_id"), modlog_channel=result.get("modlog_channel"),
                              name=result.get("name"))
            result_list.append(obj)
        return result_list


class Mute(db.DatabaseTable):
    """Holds mute info"""
    type = 1
    past_participle = "muted"
    finished_callback = Moderation._unmute
    __tablename__ = 'mutes'
    __uniques__ = 'guild_id, member_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            member_id bigint NOT NULL,
            guild_id bigint NOT NULL,
            PRIMARY KEY (member_id, guild_id)
            )""")

    def __init__(self, member_id: int, guild_id: int):
        super().__init__()
        self.member_id = member_id
        self.guild_id = guild_id

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = Mute(member_id = result.get("member_id"), guild_id = result.get("guild_id"))
            result_list.append(obj)
        return result_list

    async def update_or_add(self):
        """Assign the attribute to this object, then call this method to either insert the object if it doesn't exist in
        the DB or update it if it does exist. It will update every column not specified in __uniques__."""
        # This is its own functions because all columns must be unique, which breaks the syntax of the other one
        keys = []
        values = []
        for var, value in self.__dict__.items():
            # Done so that the two are guaranteed to be in the same order, which isn't true of keys() and values()
            if value is not None:
                keys.append(var)
                values.append(value)
        async with db.Pool.acquire() as conn:
            statement = f"""
            INSERT INTO {self.__tablename__} ({", ".join(keys)})
            VALUES({','.join(f'${i + 1}' for i in range(len(values)))}) 
            """
            await conn.execute(statement, *values)


class Deafen(db.DatabaseTable):
    """Holds deafens"""
    type = 2
    __tablename__ = 'deafens'
    __uniques__ = 'member_id, guild_id'
    past_participle = "deafened"
    finished_callback = Moderation._undeafen

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            member_id bigint NOT NULL,
            guild_id bigint NOT NULL,
            self_inflicted boolean NOT NULL,
            PRIMARY KEY (member_id, guild_id)
            )""")

    def __init__(self, member_id: int, guild_id: int, self_inflicted: bool):
        super().__init__()
        self.member_id = member_id
        self.guild_id = guild_id
        self.self_inflicted = self_inflicted

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = Deafen(member_id = result.get("member_id"), guild_id = result.get("guild_id"),
                         self_inflicted = result.get("self_inflicted"))
            result_list.append(obj)
        return result_list


class MemberRole(db.DatabaseTable):
    """Holds info on member roles used for timeouts"""
    __tablename__ = 'member_roles'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,
            member_role bigint null
            )""")

    def __init__(self, guild_id: int, member_role: int = None):
        super().__init__()
        self.guild_id = guild_id
        self.member_role = member_role

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = MemberRole(member_role = result.get("member_role"), guild_id = result.get("guild_id"))
            result_list.append(obj)
        return result_list


class NewMemPurgeConfig(db.DatabaseTable):
    """Holds info on member purge routines"""
    __tablename__ = 'member_purge_configs'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,
            member_role bigint not null,
            days int not null
            )""")

    def __init__(self, guild_id: int, member_role: int, days: int):
        super().__init__()
        self.guild_id = guild_id
        self.member_role = member_role
        self.days = days

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = NewMemPurgeConfig(member_role = result.get("member_role"),
                                    guild_id = result.get("guild_id"),
                                    days = result.get("days"))
            result_list.append(obj)
        return result_list


class GuildNewMember(db.DatabaseTable):
    """Holds new member info"""
    __tablename__ = 'new_members'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY,
            channel_id bigint NOT NULL,
            role_id bigint NOT NULL,
            message varchar NOT NULL
            )""")

    def __init__(self, guild_id: int, channel_id: int, role_id: int, message: str, require_team: bool):
        super().__init__()
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.role_id = role_id
        self.message = message
        self.require_team = require_team

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = GuildNewMember(guild_id = result.get("guild_id"), channel_id = result.get("channel_id"),
                                 role_id = result.get("role_id"), message = result.get("message"),
                                 require_team = result.get("require_team"))
            result_list.append(obj)
        return result_list

    async def version_1(self):
        """DB migration v1"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            ALTER TABLE {self.__tablename__} ADD require_team bool NOT NULL DEFAULT false;
            """)

    __versions__ = [version_1]


class GuildMessageLinks(db.DatabaseTable):
    """Contains information for link scrubbing"""
    __tablename__ = 'guild_msg_links'
    __uniques__ = 'guild_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,
            role_id bigint null
            )""")

    def __init__(self, guild_id: int, role_id: int = None):
        super().__init__()
        self.guild_id = guild_id
        self.role_id = role_id

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = GuildMessageLinks(guild_id = result.get("guild_id"), role_id = result.get("role_id"))
            result_list.append(obj)
        return result_list


class PunishmentTimerRecords(db.DatabaseTable):
    """Punishment Timer Records"""
    type_map = {p.type: p for p in (Mute, Deafen)}
    __tablename__ = 'punishment_timers'
    __uniques__ = 'id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            id serial PRIMARY KEY NOT NULL,
            guild_id bigint NOT NULL,
            actor_id bigint NOT NULL,
            target_id bigint NOT NULL,
            orig_channel_id bigint null,
            type_of_punishment bigint NOT NULL,
            reason varchar null,
            target_ts bigint NOT NULL
            )""")

    def __init__(self, guild_id: int, actor_id: int, target_id: int, type_of_punishment: int, target_ts: int,
                 orig_channel_id: int = None, reason: str = None, input_id: int = None, self_inflicted: bool = False):
        super().__init__()
        self.id = input_id
        self.guild_id = guild_id
        self.actor_id = actor_id
        self.target_id = target_id
        self.type_of_punishment = type_of_punishment
        self.target_ts = target_ts
        self.orig_channel_id = orig_channel_id
        self.reason = reason
        self.self_inflicted = self_inflicted

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = PunishmentTimerRecords(guild_id = result.get("guild_id"), actor_id = result.get("actor_id"),
                                         target_id = result.get("target_id"),
                                         type_of_punishment = result.get("type_of_punishment"),
                                         target_ts = result.get("target_ts"),
                                         orig_channel_id = result.get("orig_channel_id"), reason = result.get("reason"),
                                         input_id = result.get('id'), self_inflicted = result.get("self_inflicted"))
            result_list.append(obj)
        return result_list

    async def version_1(self):
        """DB migration v1"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            ALTER TABLE {self.__tablename__} ADD self_inflicted bool NOT NULL DEFAULT false;
            """)

    __versions__ = [version_1]


async def setup(bot):
    """Adds the moderation cog to the bot."""
    await bot.add_cog(Moderation(bot))
