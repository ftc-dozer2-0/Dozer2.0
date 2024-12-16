"""Adds fun commands to the bot"""
import random
from asyncio import sleep

import discord
from discord import app_commands
from discord.ext.commands import cooldown, BucketType, guild_only
from discord.ext import commands

from cogs._utils import dev_check
from context import DozerContext

blurple = discord.Color.blurple()


class Fun(commands.Cog):
    """Fun commands"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @guild_only()
    @cooldown(1, 20, BucketType.user)
    @commands.hybrid_command(name = "fight", aliases = ["duel"], pass_context = True)
    @app_commands.describe(opponent = "The user you want to fight")
    async def fight(self, ctx: DozerContext, opponent: discord.Member):
        """Start a fight with another user."""
        attacks = [
            # These were edited by FTC members to be more FTC-specific.
            "**{opponent}** was hit on the head by **{attacker}** ",
            "**{opponent}** was kicked by **{attacker}** ",
            "**{opponent}** was slammed into a wall by **{attacker}** ",
            "**{opponent}** was dropkicked by **{attacker}** ",
            "**{opponent}** was DDoSed by **{attacker}** ",
            "**{opponent}** was run over with a robot by **{attacker}** ",
            "**{opponent}** had their IQ dropped 15 points by **{attacker}**",
            "**{opponent}** had a heavy object dropped on them by **{attacker}**",
            "**{opponent}** was beat up by **{attacker}** ",
            "**{opponent}** was told to read the manual by **{attacker}** ",
            "**{opponent}** was told to use Android Studio by **{attacker}**",
            "**{opponent}** was hit by a snowplow driven by **{attacker}**",
            "**{opponent}** had their api token leaked by **{attacker}**",
            "**{opponent}** had a satellite dropped on them by **{attacker}**",
            "**{opponent}** lost connection to the field courtesy of **{attacker}**",
            "**{opponent}** had the scale dropped on them by **{attacker}**",
            "**{opponent}** had `git rm --force` executed on them by **{attacker}**",
            # this and the following messages up to the next comment are custom by @transorsmth#7483
            "**{opponent}** had their autonomous broken by **{attacker}**",
            "**{opponent}** was voted out by **{attacker}**",
            "**{opponent}** was called sus by **{attacker}**",
            "**{opponent}** had a conflicting autonomous with **{attacker}**",
            "**{opponent}** was hit with a stapler by **{attacker}**",
            "**{opponent}** had their battery fall out out thanks to **{attacker}**",
            "**{opponent}** had their season ended by **{attacker}**",
            "**{opponent}** had their control hub bricked by **{attacker}**",
            # this and the following messages are thanks to J-Man from the CHS discord server, who expended their
            # creative powers on these statements.
            "**{opponent}** extended too far outside their field perimeter in front of **{attacker}**",
            "**{opponent}** lost a coffee-drinking competition against **{attacker}**",
            "**{opponent}** was a no-show against **{attacker}**",
            "**{opponent}** fell asleep before a match against **{attacker}**",
            "**{opponent}** yelled ROBOT! too loudly at **{attacker}**",
            "**{opponent}** got caught running in the pits by **{attacker}**",
            "**{opponent}** had their robot disabled by **{attacker}**",
            "**{opponent}** got a red card from **{attacker}**",
            "**{opponent}** got a yellow card from **{attacker}**",
            "**{opponent}** failed their robot's inspection by **{attacker}**",
            "**{opponent}** had their drill battery stolen by **{attacker}**",
            "**{opponent}** had their website hacked by **{attacker}**",
            "**{opponent}** lost their sponsorship to **{attacker}**",
            "**{opponent}** took an arrow in the knee from **{attacker}**",
            "**{opponent}** was given a tech foul by **{attacker}**",
            "**{opponent}** had their code corrupted by **{attacker}**",
            "**{opponent}** was found without adequate eye protection by **{attacker}**",
        ]

        damages = [50, 69, 100, 150, 200, 250, 300, 420]
        players = [ctx.author, opponent]
        hps = [1500, 1500]
        turn = random.randint(0, 1)

        messages = []
        while hps[0] > 0 and hps[1] > 0:
            opp_idx = (turn + 1) % 2
            damage = random.choice(damages)
            if players[turn].id in ctx.bot.config['developers'] or players[turn] == ctx.bot.user:
                damage = damage * 2
            if players[turn].id == 787125089434730537: #olivia gets minor power boost for no reason whatsoever now
                damage = damage * 2.2
            hps[opp_idx] = max(hps[opp_idx] - damage, 0)
            messages.append(
                await ctx.send(
                    f"{random.choice(attacks).format(opponent = players[opp_idx].name, attacker = players[turn].name)} *[-{damage} hp]"
                    f" [{hps[opp_idx]} HP remaining]*"))
            await sleep(1.5)
            turn = opp_idx
        win_embed = discord.Embed(description = f"{players[(turn + 1) % 2].mention} won! GG {players[turn].mention}!",
                                  color = blurple)
        await ctx.send(embed = win_embed)
        await sleep(5)
        # bulk delete if we have the manage messages permission
        if ctx.channel.permissions_for(ctx.guild.get_member(ctx.bot.user.id)).manage_messages:
            await ctx.channel.delete_messages(messages)
        else:
            # otherwise delete manually
            for msg in messages:
                await msg.delete()

        return players[turn], players[(turn + 1) % 2]

    fight.example_usage = """
    `{prefix}fight @user2#2322 - Initiates a fight with @user2#2322`
    """


async def setup(bot):
    """Adds the fun cog to Dozer"""
    await bot.add_cog(Fun(bot))
