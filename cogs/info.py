"""Provides commands for pulling certain information."""
import time
import re
import datetime
# import resource

import discord
from discord.ext.commands import cooldown, BucketType, guild_only
from discord.ext import commands
from discord import app_commands

from ._utils import *
from asyncdb.orm import orm
from asyncdb import psqlt

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
        self.afk_map = {}
        self.bot = bot

    @commands.hybrid_command(name = "profile", aliases=['user', 'memberinfo', 'userinfo', 'member'])
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

        embed = discord.Embed(title=member.display_name, description=f'{member!s} ({member.id}) | {member.mention}', color=member.color)
        embed.add_field(name='Bot Created' if member.bot else 'Account Created',
                        value=discord.utils.format_dt(member.created_at), inline=True)
        embed.add_field(name='Member Joined', value=discord.utils.format_dt(member.joined_at), inline=True)
        if member.premium_since is not None:
            embed.add_field(name='Member Boosted', value=discord.utils.format_dt(member.premium_since), inline=True)
        if len(member.roles) > 1:
            role_string = ' '.join([r.mention for r in member.roles][1:])
        else:
            role_string = member.roles[0].mention
        s = "s" if len(member.roles) >= 2 else ""
        embed.add_field(name = f"Role{s}: ", value = role_string, inline = False)
        embed.set_thumbnail(url=icon_url or None)
        await ctx.send(embed=embed, ephemeral=True)

    member.example_usage = """
    `{prefix}member`: show your member info
    `{prefix}member {ctx.me}`: show my member info
    """

    @guild_only()
    @cooldown(1, 10, BucketType.channel)
    @commands.hybrid_command(name= "server", aliases=['guild', 'guildinfo', 'serverinfo'])
    async def guild(self, ctx):
        """Retrieve information about this guild."""
        guild = ctx.guild
        static_emoji = sum(not e.animated for e in ctx.guild.emojis)
        animated_emoji = sum(e.animated for e in ctx.guild.emojis)
        e = discord.Embed(color=blurple)
        e.set_thumbnail(url=guild.icon.url if guild.icon else None)
        e.title = guild.name
        e.description = f"{guild.member_count} members, {len(guild.channels)} channels, {len(guild.roles) - 1} roles"
        e.add_field(name='ID', value=guild.id)
        e.add_field(name='Created at', value=discord.utils.format_dt(guild.created_at))
        e.add_field(name='Owner', value=guild.owner.mention)
        e.add_field(name='Emoji', value=f"{static_emoji} static, {animated_emoji} animated")
        e.add_field(name='Nitro Boost', value=f'Level {ctx.guild.premium_tier}, '
                                              f'{ctx.guild.premium_subscription_count} booster(s)\n'
                                              f'{ctx.guild.filesize_limit // 1024**2}MiB files, '
                                              f'{ctx.guild.bitrate_limit / 1000:0.1f}kbps voice')
        await ctx.send(embed=e, ephemeral=True)

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
        await ctx.send(f"```\n{frame}\n```", ephemeral = True)#embed=e)

    stats.example_usage = """
    `{prefix}stats` - get current bot/host stats
    """

    @commands.hybrid_command()
    @app_commands.describe(reason = "Reason you want others to see when you're afk")
    async def afk(self, ctx, *, reason: str = "Not specified"):
        """Set yourself to AFK so that if you are pinged, the bot can explain your absence."""
        if len(ctx.message.mentions):
            await ctx.send("Please don't mention anyone in your AFK message!", ephemeral=True)
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
            await ctx.send(f"**{ctx.author.name}** is no longer AFK!", ephemeral=True)
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
