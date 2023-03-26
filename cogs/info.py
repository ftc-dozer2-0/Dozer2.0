"""Provides commands for pulling certain information."""
import time
import re
import datetime
# import resource

from difflib import SequenceMatcher
import typing
import discord
from discord.ext.commands import cooldown, BucketType, guild_only
from discord.ext import commands
from discord import app_commands

from ._utils import *
from asyncdb.orm import orm
from asyncdb import psqlt

blurple = discord.Color.blurple()
datetime_format = '%Y-%m-%d %I:%M %p'
startup_time = time.time()

try:
    with open("/etc/os-release") as f:
        os_name = re.findall(r'PRETTY_NAME=\"(.+?)\"', f.read())[0]
except Exception:
    os_name = "Windows probably"


class Info(Cog):
    """Commands for getting information about people and things on Discord."""
    datetime_format = '%Y-%m-%d %H:%M:%S UTC'

    def __init__(self, bot):
        super().__init__(bot)
        self.afk_map = {}
        self.bot = bot

    @commands.hybrid_command(aliases=['user', 'memberinfo', 'userinfo', 'profile'])
    @guild_only()
    @bot_has_permissions(embed_links=True)
    @app_commands.describe(member = "The member to get info about.")
    async def member(self, ctx, *, member: discord.Member = None):
        """Retrieve information about a member of the guild.
         If no arguments are passed, information about the author is used.
         **This command works without mentions.** Remove the '@' before your mention so you don't ping the person unnecessarily.
         You can pick a member by:
         - Username (`cooldude`)
         - Username and discriminator (`cooldude#1234`)
         - ID (`326749693969301506`)
         - Nickname - must be exact and is case-sensitive (`"Mr. Cool Dude III | Team 1234"`)
         - Mention (not recommended) (`@Mr Cool Dude III | Team 1234`)
         """
        if member is None:
            member = ctx.author

        icon_url = member_avatar_url(member)

        embed = discord.Embed(title=member.display_name, description=f'{member!s} ({member.id})', color=member.color)
        embed.add_field(name='Bot Created' if member.bot else 'Account Created',
                        value=member.created_at.strftime(self.datetime_format), inline=True)
        embed.add_field(name='Member Joined', value=member.joined_at.strftime(self.datetime_format), inline=True)
        if member.premium_since is not None:
            embed.add_field(name='Member Boosted', value=member.premium_since.strftime(self.datetime_format), inline=True)
        embed.add_field(name='Color', value=str(member.color).upper(), inline=True)

        status = 'DND' if member.status is discord.Status.dnd else member.status.name.title()
        if member.status is not discord.Status.offline:
            platforms = self.pluralize([platform for platform in ('web', 'desktop', 'mobile') if
                                        getattr(member, f'{platform}_status') is not discord.Status.offline])
            status = f'{status} on {platforms}'
        activities = ', '.join(self._format_activities(member.activities))
        embed.add_field(name='Status and Activity', value=f'{status}, {activities}', inline=True)

        embed.add_field(name='Roles', value=', '.join(role.name for role in member.roles[:0:-1]) or 'None', inline=False)
        embed.add_field(name='Icon URL', value=icon_url, inline=False)
        embed.set_thumbnail(url=icon_url)
        await ctx.send(embed=embed)

    member.example_usage = """
    `{prefix}member`: show your member info
    `{prefix}member {ctx.me}`: show my member info
    """

    @staticmethod
    def _format_activities(activities: typing.Sequence[discord.Activity]) -> typing.List[str]:
        if not activities:
            return []

        def format_activity(activity: discord.Activity) -> str:
            if isinstance(activity, discord.CustomActivity):
                return f"{activity.emoji} {activity.name}"
            elif isinstance(activity, discord.Spotify):
                return f'listening to {activity.title} by {activity.artist} on Spotify'
            elif activity.type is discord.ActivityType.listening:
                return f'listening to {activity.name}'  # Special-cased to insert " to"
            else:
                return f'{activity.type.name} {activity.name}'

        # Some games show up twice in the list (e.g. "Rainbow Six Siege" and "Tom Clancy's Rainbow Six Siege") so we
        # need to dedup them by string similarity before displaying them
        matcher = SequenceMatcher(lambda c: not c.isalnum(), autojunk=False)
        filtered = [activities[0]]
        for activity in activities[1:]:
            matcher.set_seq2(activity.name)  # Expensive metadata is computed about seq2, so change it less frequently
            for filtered_activity in filtered:
                matcher.set_seq1(filtered_activity.name)
                if matcher.quick_ratio() < 0.6 and matcher.ratio() < 0.6:  # Use quick_ratio if we can as ratio is slow
                    filtered.append(activity)
                    break

        return [format_activity(activity) for activity in filtered]

    @staticmethod
    def pluralize(values: typing.List[str]) -> str:
        """Inserts commas and "and"s in the right places to create a grammatically correct list."""
        if len(values) == 0:
            return ''
        elif len(values) == 1:
            return values[0]
        elif len(values) == 2:
            return f'{values[0]} and {values[1]}'
        else:
            return f'{", ".join(values[:-1])}, and {values[-1]}'

    @guild_only()
    @cooldown(1, 10, BucketType.channel)
    @commands.hybrid_command(aliases=['server', 'guildinfo', 'serverinfo'])
    async def guild(self, ctx):
        """Retrieve information about this guild."""
        guild = ctx.guild
        static_emoji = sum(not e.animated for e in ctx.guild.emojis)
        animated_emoji = sum(e.animated for e in ctx.guild.emojis)
        e = discord.Embed(color=blurple)
        e.set_thumbnail(url=guild.icon.url)
        e.title = guild.name
        e.description = f"{guild.member_count} members, {len(guild.channels)} channels, {len(guild.roles) - 1} roles"
        #e.add_field(name='Name', value=guild.name)
        e.add_field(name='ID', value=guild.id)
        e.add_field(name='Created at', value=guild.created_at.strftime(datetime_format))
        e.add_field(name='Owner', value=guild.owner.mention)
        e.add_field(name='Emoji', value="{} static, {} animated".format(static_emoji, animated_emoji))
        e.add_field(name='Region', value=guild.region.name)
        e.add_field(name='Nitro Boost', value=f'Level {ctx.guild.premium_tier}, '
                                              f'{ctx.guild.premium_subscription_count} booster(s)\n'
                                              f'{ctx.guild.filesize_limit // 1024**2}MiB files, '
                                              f'{ctx.guild.bitrate_limit / 1000:0.1f}kbps voice')
        e.add_field(name='Icon URL', value=guild.icon.url or 'This guild has no icon.', inline=False)

        await ctx.send(embed=e)

    guild.example_usage = """
    `{prefix}guild` - get information about this guild
    """

    @commands.hybrid_command()
    async def stats(self, ctx):
        """Get current running internal/hosts stats for the bot"""
        info = await ctx.bot.application_info()

        #e = discord.Embed(title=info.name + " Stats", color=discord.Color.blue())
        frame = "\n".join(map(lambda x: f"{str(x[0]):<24}{str(x[1])}", { #e.add_field(name=x[0], value=x[1], inline=False), {
            "{:=^48}".format(f" Stats for {info.name} "): "",
            "Bot owner:": info.owner,
            "Users:": len(ctx.bot.users),
            "Channels:": len(list(ctx.bot.get_all_channels())),
            "Servers:": len(ctx.bot.guilds),
            "":"",
            f"{' Host stats ':=^48}": "",
            "Operating system:": os_name,
            #"Process memory usage:": f"{resource.getrusage(resource.RUSAGE_SELF).ru_maxrss}K",
            "Process uptime": str(datetime.timedelta(seconds=round(time.time() - startup_time)))
        }.items()))
        await ctx.send(f"```\n{frame}\n```")#embed=e)

    stats.example_usage = """
    `{prefix}stats` - get current bot/host stats
    """

    @commands.hybrid_command()
    @app_commands.describe(reason = "Reason you want others to see when you're afk")
    async def afk(self, ctx, *, reason: str = "Not specified"):
        """Set yourself to AFK so that if you are pinged, the bot can explain your absence."""
        if len(ctx.message.mentions):
            await ctx.send("Please don't mention anyone in your AFK message!")
            return

        afk_status = self.afk_map.get(ctx.author.id)
        if not afk_status is None:
            afk_status.reason = reason
        else:
            afk_status = AFKStatus(user_id=ctx.author.id, reason=reason)
            self.afk_map[ctx.author.id] = afk_status

        await ctx.send(embed=discord.Embed(description=f"**{ctx.author.name}** is AFK: **{reason}**"))
    afk.example_usage = """
    `{prefix}afk robot building` - set yourself to AFK for reason "reason"
    """

    @Cog.listener()
    async def on_message(self, message):
        """Primarily handles AFK"""
        ctx = await self.bot.get_context(message)
        if message.content.strip().startswith(f"{ctx.prefix}afk"):
            return

        for member in message.mentions:
            if member.id in self.afk_map:
                await ctx.send(embed=discord.Embed(description=f"**{member.name}** is AFK: **{self.afk_map[member.id].reason}**"))

        afk_status = self.afk_map.get(ctx.author.id)
        if afk_status is not None:
            await ctx.send(f"**{ctx.author.name}** is no longer AFK!")
            del self.afk_map[ctx.author.id]


class AFKStatus(orm.Model):
    """Holds AFK data."""
    __tablename__ = "afk_status"
    __primary_key__ = ("user_id",)
    user_id: psqlt.bigint
    reason: psqlt.text


async def setup(bot):
    """Adds the info cog to the bot"""
    await bot.add_cog(Info(bot))
