# pylint: skip-file
from discord.ext.commands import has_permissions, bot_has_permissions, BucketType, cooldown
from ._utils import *
import discord
from discord.ext import commands
from discord import app_commands

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


class Hacks(Cog):

    @Cog.listener()
    async def on_member_join(self, member):
        if member.guild.id == FTC_DISCORD_ID:
            try:
                await member.send(
                    """Welcome to the FTC Discord! Please read through #server-rules-info for information on how to access the rest of the server!""")
            except discord.Forbidden:
                self.bot.logger.info(f"@{member} has blocked me?")
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
            pass # why does this exist here?
            # await message.add_reaction("🐢")
            # await message.delete()

        if message.channel.id in PUBLIC_CHANNEL_IDS:
            await message.publish()

        if message.channel.id in VOTE_CHANNEL_IDS:
            await message.add_reaction('👍')
            await message.add_reaction('👎')

    @Cog.listener()
    async def on_message_edit(self, before, after):
        message = after
        if message.guild and message.guild.id == FTC_DISCORD_ID and "🐢" in message.content and message.author.id != self.bot.user.id:
            pass # is this like a testing thing?
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
        if message.guild and message.guild.id == FTC_DISCORD_ID and message.content.lower().startswith("no u") and message.author.id != self.bot.user.id:
            await message.channel.send("no u") # ok to be funny I uncommented this

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

    @has_permissions(manage_roles = True)
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
    async def vote(self, ctx):
        await ctx.message.add_reaction('👍')
        await ctx.message.add_reaction('👎')
        await ctx.message.add_reaction('💀')

    @cooldown(1, 60, BucketType.user)
    @bot_has_permissions(embed_links = True)
    @commands.hybrid_command(name = "sleep", aliases = ["💀", "bed", "🛏️", "goSleep", "goToBed", "goToSleep"])
    @app_commands.describe(member = "The member to send the sleep message to")
    # ok at this point I'm just adding a ton of random aliases for fun
    async def sleep(self, ctx, member: discord.Member = None):
        IMG_URL = "https://i.imgur.com/ctzynlC.png"
        await ctx.send(IMG_URL)
        if member: # updated number of E's to send
            await member.send("🛌 **GO TO SLEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEEP** 🛌")


async def setup(bot):
    await bot.add_cog(Hacks(bot))
