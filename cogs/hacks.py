# pylint: skip-file
from typing import Union

import pytz
from discord.ext.commands import has_permissions, bot_has_permissions, BucketType, cooldown
from ._utils import *
import discord
from discord.ext import commands
from discord import app_commands
from loguru import logger
from context import DozerContext
import datetime
from ._utils import not_dev
global count
# as the name implies, this cog is hilariously hacky code.
# it's very ftc server specific code, made specifically for its own needs.
# i stuck it in git for maintenance purposes.
# this should be deleted from the plowie tree if found.

FTC_DISCORD_ID = 225450307654647808
VERIFY_CHANNEL_ID = 333612583409942530
JOINED_LOGS_ID = 350482751335432202
FEEDS_CHANNEL_ID = 320719178132881408
VOTE_CHANNEL_IDS = [674081079761829898, 674026943691358229]
MEDIA_CHANNEL_ID = 676583549561995274
# feeds, media, robot-showcase
PUBLIC_CHANNEL_IDS = [320719178132881408, 676583549561995274, 771188718198456321]
DOOC_DISCORD_ID = 884664360486703125
DOOC_MODS = [748927855219703959, 538729840698982409, 761385417068642305]
FTC_GUILDS = [884664360486703125, 225450307654647808]


class Hacks(Cog):
    def __init__(self, bot: commands.Bot) -> None:
        super().__init__(bot)
        self.bot = bot
        self.config = self.bot.config

    @Cog.listener()
    async def on_guild_join(self, guild):
        activity = discord.Game(name = f"'{self.config['prefix']}' in {len(self.guilds)} guilds")
        await self.bot.change_presence(activity = activity)

    @Cog.listener()
    async def on_member_join(self, member):
        if member.guild.id == FTC_DISCORD_ID:
            try:
                await member.send(
                    """Welcome to the FTC Discord! Please read through #server-rules-info for information on how to access the rest of the server!""")
            except discord.Forbidden:
                logger.info(f"@{member} has blocked me?")
        else:
            return
        logs = self.bot.get_channel(JOINED_LOGS_ID)
        res = f"```New user {member} ({member.id})\nInvite summary:\n"
        for i in await member.guild.invites():
            res += f"{i.code}, {i.uses}\n"
        res += "```"
        await logs.send(res)

    @Cog.listener()
    async def on_message(self, message):
        member = message.author
        global count
        if message.guild is None:
            return
        if message.channel.id == VERIFY_CHANNEL_ID and message.content.lower().startswith(
                "i have read the rules and regulations"):
            await member.add_roles(discord.utils.get(message.guild.roles, name = "Member"))
            await member.send("""Thank you for reading the rules and regulations. We would like to welcome you to the 
            FIRST® Tech Challenge Discord Server! Please follow the server rules and have fun! Don't hesitate to ping 
            a member of the moderation team if you have any questions!
            
            _Please set your nickname with `%nick NAME - TEAM#` in #bot-spam to reflect your team number, or your role in 
            FIRST Robotics if you are not affiliated with a team. If you are not a part of or affiliated directly with a 
            FIRST® Tech Challenge team or the program itself, please contact an administrator for further details._""")
            await member.edit(nick = (message.author.display_name[:20] + " | SET TEAM#"))
            return
        if message.guild and message.guild.id == FTC_DISCORD_ID and "🐢" in message.content and message.author.id != self.bot.user.id:
            pass  # why does this exist here?
            # await message.add_reaction("🐢")
            # await message.delete()

        if message.channel.id in PUBLIC_CHANNEL_IDS:
            await message.publish()

        if (message.channel.id in VOTE_CHANNEL_IDS) & message.type != discord.MessageType.thread_created:
            await message.add_reaction('👍')
            await message.add_reaction('👎')

        if message.guild.id == 884664360486703125:
            if message.author.id in DOOC_MODS: # this is self-explanatory as per rule 4 of the dooc server
                await message.add_reaction("<:modaboos:927346308551954443>")
            if message.author.id == 787125089434730537: #olivia/viamarkable
                if "hi " in message.content:
                    await message.delete()
                    return
                count+=1
                if count >4:
                    await message.add_reaction("👶")
                    count =0
            if "i'm" in message.content.lower():
                if not message.author.bot and message.author.id not in self.config["developers"]:
                    text = message.content.lower()
                    person = text.split("i'm ")[1].strip()
                    await message.reply(f"Hi {person}, I'm Dozer!")
            if message.author.id == 1018237375433953430 and "stephanie" in message.content.lower(): #meheretE
                await message.reply("*Stephan*")

    @Cog.listener()
    async def on_message_edit(self, before, after):
        message = after
        if message.guild and message.guild.id == FTC_DISCORD_ID and "🐢" in message.content and message.author.id != self.bot.user.id:
            pass  # is this like a testing thing?
            # await message.add_reaction("🐢")
            # await message.delete()

    async def clear_reactions(self, reaction):
        async for user in reaction.users():
            await reaction.message.remove_reaction(reaction, user)

    @Cog.listener()
    async def on_reaction_add(self, reaction, user):
        # return
        message = reaction.message
        if message.guild and message.guild.id == FTC_DISCORD_ID and message.channel.id == 771188718198456321 and reaction.emoji == "🍞":
            await reaction.message.remove_reaction(reaction, user)
            # await self.clear_reactions(reaction)
        if message.guild and message.guild.id in FTC_GUILDS and message.content.lower().startswith(
                "no u") and message.author.id != self.bot.user.id and discord.utils.compute_timedelta(message.created_at)<(60):
            await message.channel.send("no u", delete_after=300)  # ok to be funny I uncommented this

    # deleted mkteamrole, no longer used

    @has_permissions(manage_roles = True)
    @bot_has_permissions(manage_roles = True)
    @commands.hybrid_command()
    @app_commands.describe(member = "The member to force undeafen")
    @commands.guild_only()
    async def forceundeafen(self, ctx, member: discord.Member):
        async with ctx.typing():
            await ctx.bot.cogs["Moderation"].perm_override(member, read_messages = None)
        await ctx.send("Overwrote perms for {member}")

    @has_permissions(manage_roles = True) if not dev_check() else has_permissions(send_messages = True)
    @bot_has_permissions(manage_roles = True)
    @commands.hybrid_command(name = "takeemotes", aliases = ["takeemote", "Lemotes", "bread", "🍞"])
    @app_commands.describe(member = "The member to take emotes from")
    @commands.guild_only()
    async def takeemotes(self, ctx, member: discord.Member):
        async with ctx.typing():
            await ctx.bot.cogs["Moderation"].perm_override(member, external_emojis = False)
        await ctx.send(f"took away external emote perms for {member}", ephemeral = True)

    @has_permissions(manage_roles = True)
    @bot_has_permissions(manage_roles = True)
    @commands.hybrid_command(name = "giveemotes", aliases = ["giveemote", "Gemotes"])
    @app_commands.describe(member = "The member to give emote perms")
    async def giveemotes(self, ctx, member: discord.Member):
        async with ctx.typing():
            await ctx.bot.cogs["Moderation"].perm_override(member, external_emojis = None)
        await ctx.send(f"reset external emote perms for {member}", ephemeral = True)

    @has_permissions(add_reactions = True)
    @bot_has_permissions(add_reactions = True)
    @commands.command()
    async def vote(self, ctx: DozerContext, options: Union[int, str] = None, text: str = None):
        if isinstance(options, str):
            try:
                options = int(options)
            except ValueError:
                options = None
        if options == 2 or options is None or not isinstance(options, int):
            await ctx.message.add_reaction('👍')
            await ctx.message.add_reaction('👎')
            await ctx.message.add_reaction('💀')
        else:
            numbers = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            for number in numbers[:options]:
                await ctx.message.add_reaction(number)

    @cooldown(1, 150, BucketType.user) if not dev_check() else cooldown(10, 0, BucketType.user)
    @bot_has_permissions(embed_links = True)
    @commands.hybrid_command(name = "sleep", aliases = ["💀", "bed", "🛏️", "goSleep", "goToBed", "goToSleep"])
    @app_commands.describe(member = "The member to send the sleep message to")
    # ok at this point I'm just adding a ton of random aliases for fun
    async def sleep(self, ctx, member: discord.Member = None):
        IMG_URL = "https://i.imgur.com/ctzynlC.png"
        await ctx.send(IMG_URL)
        if member and member.id not in ctx.bot.config['developers'] and "Mod" not in member.roles:  # updated number of E's to send
            await member.send("🛌 **GO TO SLEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEP** 🛌", delete_after = 60*60*24)

    @commands.command()
    @dev_check()
    async def echo(self, ctx: DozerContext, *, message: str):
        await ctx.send(message)
        await ctx.message.delete()


async def setup(bot):
    await bot.add_cog(Hacks(bot))
