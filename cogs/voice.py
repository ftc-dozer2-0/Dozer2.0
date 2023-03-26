"""Provides commands for voice, currently only voice and text channel access bindings."""
import discord
from discord.ext.commands import has_permissions

from ._utils import *
from asyncdb.orm import orm
from asyncdb import psqlt


class Voice(Cog):
    """Commands interacting with voice."""

    @Cog.listener('on_voice_state_update')
    async def on_voice_state_update(self, member, before, after):
        """Handles voicebinds when members join/leave voice channels"""
        # skip this if we have no perms, or if it's something like a mute/deafen
        if member.guild.me.guild_permissions.manage_roles and before.channel != after.channel:
            # determine if it's a join/leave event as well.
            # before and after are voice states
            if before.channel is not None:
                # leave event, take role
                config = await Voicebinds.select_one(channel_id = before.channel.id)
                if config is not None:
                    await member.remove_roles(member.guild.get_role(config.role_id))

            if after.channel is not None:
                # join event, give role
                config = await Voicebinds.select_one(channel_id = after.channel.id)
                if config is not None:
                    await member.add_roles(member.guild.get_role(config.role_id))

    @command()
    @bot_has_permissions(manage_roles = True)
    @has_permissions(manage_roles = True)
    async def voicebind(self, ctx, voice_channel: discord.VoiceChannel, *, role: discord.Role):
        """Associates a voice channel with a role, so users joining a voice channel will automatically be given a
        specified role or roles."""

        config = await Voicebinds.select_one(channel_id = voice_channel.id)
        if config is not None:
            config.guild_id = ctx.guild.id
            config.role_id = role.id
            await config.update()
        else:
            config = Voicebinds(channel_id = voice_channel.id, role_id = role.id, guild_id = ctx.guild.id)
            await config.insert()

        await ctx.send(
            "Role `{role}` will now be given to users in voice channel `{voice_channel}`!".format(role = role,
                                                                                                  voice_channel = voice_channel))

    voicebind.example_usage = """
    `{prefix}voicebind "General #1" voice-general-1` - sets up Dozer to give users  `voice-general-1` when they join voice channel 
    "General #1", which will be removed when they leave.
    """

    @command()
    @bot_has_permissions(manage_roles = True)
    @has_permissions(manage_roles = True)
    async def voiceunbind(self, ctx, voice_channel: discord.VoiceChannel):
        """Dissasociates a voice channel with a role previously binded with the voicebind command."""
        config = await Voicebinds.select_one(channel_id = voice_channel.id)
        if config is not None:
            role = ctx.guild.get_role(config.role_id)
            await config.delete()
            await ctx.send(
                "Role `{role}` will no longer be given to users in voice channel `{voice_channel}`!".format(
                    role = role, voice_channel = voice_channel))
        else:
            await ctx.send("It appears that `{voice_channel}` is not associated with a role!".format(
                voice_channel = voice_channel))

    voiceunbind.example_usage = """
    `{prefix}voiceunbind "General #1"` - Removes automatic role-giving for users in "General #1".
    """

    @command()
    @bot_has_permissions(manage_roles = True)
    async def voicebindlist(self, ctx):
        """Lists all the voice channel to role bindings for the current server"""
        embed = discord.Embed(title = "List of voice bindings for \"{}\"".format(ctx.guild),
                              color = discord.Color.blue())
        for config in await Voicebinds.select(guild_id = ctx.guild.id):
            channel = discord.utils.get(ctx.guild.voice_channels, id = config.channel_id)
            role = ctx.guild.get_role(config.role_id)
            embed.add_field(name = channel, value = f"`{role}`")
        await ctx.send(embed = embed)

    voicebindlist.example_usage = """
    `{prefix}voicebindlist` - Lists all the voice channel to role bindings for the current server bound with the voicebind command.
    """


class Voicebinds(orm.Model):
    """DB object to keep track of voice to text channel access bindings."""
    __tablename__ = 'voicebinds'
    __primary_key__ = ('channel_id',)

    guild_id: psqlt.bigint
    channel_id: psqlt.bigint
    role_id: psqlt.bigint


# ALTER TABLE voicebinds DROP CONSTRAINT voicebinds_pkey;
# ALTER TABLE voicebinds ADD PRIMARY KEY (channel_id);

async def setup(bot):
    """Add this cog to the main bot."""
    await bot.add_cog(Voice(bot))
