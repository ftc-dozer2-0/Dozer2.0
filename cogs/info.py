"""Provides commands for pulling certain information."""
import time
import re
import datetime
from datetime import date, timezone
import math

from bot import DozerContext

import discord
from discord.ext.commands import cooldown, BucketType, guild_only
from discord.ext import commands
from discord import app_commands

from ._utils import *

blurple = discord.Color.blurple()
startup_time = time.time()

try:
    with open("/etc/os-release") as f:
        os_name = re.findall(r'PRETTY_NAME=\"(.+?)\"', f.read())[0]
except Exception:
    os_name = "Windows probably"


class Info(Cog):
    """Commands for getting information about people and things on Discord."""

    def __init__(self, bot):
        super().__init__(bot)
        self.bot = bot

    @commands.hybrid_command(name = "profile", aliases = ['user', 'memberinfo', 'userinfo', 'member'])
    @guild_only()
    @bot_has_permissions(embed_links = True)
    @app_commands.describe(member = "The member to get info about.")
    async def member(self, ctx: DozerContext, *, member: discord.Member = None):
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
        icon_url = member.avatar.replace(static_format = 'png', size = 32) or None

        embed = discord.Embed(title = member.display_name, description = f'{member!s} ({member.id}) | {member.mention}',
                              color = member.color)
        embed.add_field(name = 'Bot Created' if member.bot else 'Account Created',
                        value = discord.utils.format_dt(member.created_at), inline = True)
        embed.add_field(name = 'Member Joined', value = discord.utils.format_dt(member.joined_at), inline = True)
        if member.premium_since is not None:
            embed.add_field(name = 'Member Boosted', value = discord.utils.format_dt(member.premium_since),
                            inline = True)
        if len(member.roles) > 1:
            role_string = ' '.join([r.mention for r in member.roles][1:])
        else:
            role_string = member.roles[0].mention
        s = "s" if len(member.roles) >= 2 else ""
        embed.add_field(name = f"Role{s}: ", value = role_string, inline = False)
        embed.set_thumbnail(url = icon_url or None)
        await ctx.send(embed = embed, ephemeral = True)

    member.example_usage = """
    `{prefix}member`: show your member info
    `{prefix}member {ctx.me}`: show my member info
    """

    @guild_only()
    @cooldown(1, 10, BucketType.channel)
    @commands.hybrid_command(name = "server", aliases = ['guild', 'guildinfo', 'serverinfo'])
    async def guild(self, ctx: DozerContext):
        """Retrieve information about this guild."""
        guild = ctx.guild
        static_emoji = sum(not e.animated for e in ctx.guild.emojis)
        animated_emoji = sum(e.animated for e in ctx.guild.emojis)
        e = discord.Embed(color = blurple)
        e.set_thumbnail(url = guild.icon.url if guild.icon else None)
        e.title = guild.name
        e.description = f"{guild.member_count} members, {len(guild.channels)} channels, {len(guild.roles) - 1} roles"
        e.add_field(name = 'ID', value = guild.id)
        e.add_field(name = 'Created on', value = discord.utils.format_dt(guild.created_at))
        e.add_field(name = 'Owner', value = guild.owner.mention)
        e.add_field(name = 'Emoji', value = f"{static_emoji} static, {animated_emoji} animated")
        e.add_field(name = 'Nitro Boost', value = f'Level {ctx.guild.premium_tier}, '
                                                  f'{ctx.guild.premium_subscription_count} booster(s)\n'
                                                  f'{ctx.guild.filesize_limit // 1024**2}MiB files, '
                                                  f'{ctx.guild.bitrate_limit / 1000:0.1f}kbps voice')
        await ctx.send(embed = e, ephemeral = True)

    guild.example_usage = """
    `{prefix}guild` - get information about this guild
    """

    @commands.hybrid_command()
    async def stats(self, ctx: DozerContext):
        """Get current running internal/host stats for the bot"""
        info = await ctx.bot.application_info()

        frame = "\n".join(
            map(lambda x: f"{str(x[0]):<24}{str(x[1])}", {
                "Users:": len(ctx.bot.users),
                "Channels:": len(list(ctx.bot.get_all_channels())),
                "Servers:": len(ctx.bot.guilds),
                "": "",
                f"{' Host stats ':=^48}": "",
                "Operating system:": os_name,
                "Process uptime": str(datetime.datetime.timedelta(seconds = round(time.time() - startup_time)))
            }.items()))
        embed = discord.Embed(title = f"Stats for {info.name}", description = f"Bot owner: {info.owner.mention}```{frame}```", color = blurple)
        await ctx.send(embed=embed, ephemeral = True)

    stats.example_usage = """
    `{prefix}stats` - get current bot/host stats
    """

    @commands.hybrid_command(aliases = ['roleinfo'])
    @guild_only()
    @cooldown(1, 10, BucketType.channel)
    async def role(self, ctx: DozerContext, role: discord.Role):
        """Retrieve info about a role in this guild"""
        embed = discord.Embed(title = f"Info for role: {role.name}", description = f"{role.mention} ({role.id})",
                              color = role.color)
        embed.add_field(name = "Created on", value = discord.utils.format_dt(role.created_at))
        embed.add_field(name = "Position", value = role.position)
        embed.add_field(name = "Color", value = str(role.color).upper())
        embed.add_field(name = "Assigned members", value = f"{len(role.members)}", inline = False)
        await ctx.send(embed = embed, ephemeral = True)

    @commands.hybrid_command(aliases = ['withrole'])
    @guild_only()
    async def rolemembers(self, ctx: DozerContext, role: discord.Role):
        """Retrieve members who have this role"""
        await ctx.defer(ephemeral = True)
        embeds = []
        for page_num, page in enumerate(chunk(role.members, 10)):
            embed = discord.Embed(title = f"Members for role: {role.name}", color = role.color)
            embed.description = "\n".join(f"{member.mention}({member.id})" for member in page)
            embed.set_footer(text = f"Page {page_num + 1} of {math.ceil(len(role.members) / 10)}")
            embeds.append(embed)
        await paginate(ctx, embeds)


# removed afk, honestly no one uses it

async def setup(bot):
    """Adds the info cog to the bot"""
    await bot.add_cog(Info(bot))
