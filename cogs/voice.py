"""Provides commands for voice, currently only voice and text channel access bindings."""
import discord
from discord.ext.commands import has_permissions

import db
from ._utils import *


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
                config = await Voicebinds.get_by(channel_id = before.channel.id)
                if config is not None:
                    await member.remove_roles(member.guild.get_role(config[0].role_id))

            if after.channel is not None:
                # join event, give role
                config = await Voicebinds.get_by(channel_id = after.channel.id)
                if config is not None:
                    await member.add_roles(member.guild.get_role(config[0].role_id))

    @command()
    @bot_has_permissions(manage_roles = True)
    @has_permissions(manage_roles = True)
    async def voicebind(self, ctx, voice_channel: discord.VoiceChannel, *, role: discord.Role):

        """Associates a voice channel with a role, so that users in vc can have an additional channel"""

        config = await Voicebinds.get_by(channel_id = voice_channel.id)
        if len(config) != 0:
            config[0].guild_id = ctx.guild.id
            config[0].channel_id = voice_channel.id
            config[0].role_id = role.id
            await config[0].update_or_add()
        else:
            await Voicebinds(channel_id = voice_channel.id, role_id = role.id, guild_id = ctx.guild.id).update_or_add()

        await ctx.send(f"Role `{role}` will now be given to users in voice channel `{voice_channel}`!")

    voicebind.example_usage = """
    `{prefix}voicebind "General #1" voice-general-1` - sets up Dozer to give users  `voice-general-1` when they join voice channel 
    "General #1", which will be removed when they leave.
    """

    @command()
    @bot_has_permissions(manage_roles = True)
    @has_permissions(manage_roles = True)
    async def voiceunbind(self, ctx, voice_channel: discord.VoiceChannel):
        """Dissasociates a voice channel with a role previously binded with the voicebind command."""
        config = await Voicebinds.get_by(channel_id = voice_channel.id)
        if config is not None:
            role = ctx.guild.get_role(config[0].role_id)
            await Voicebinds.delete(id = config[0].id)
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
        for config in await Voicebinds.get_by(guild_id = ctx.guild.id):
            channel = discord.utils.get(ctx.guild.voice_channels, id = config.channel_id)
            role = ctx.guild.get_role(config.role_id)
            embed.add_field(name = channel, value = f"`{role}`")
        await ctx.send(embed = embed)

    voicebindlist.example_usage = """
    `{prefix}voicebindlist` - Lists all the voice channel to role bindings for the current server bound with the voicebind command.
    """


class Voicebinds(db.DatabaseTable):
    """DB object to keep track of voice to text channel access bindings."""
    __tablename__ = 'voicebinds'

    __uniques__ = 'id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            id SERIAL PRIMARY KEY NOT NULL,
            guild_id bigint NOT NULL,
            channel_id bigint null,
            role_id bigint null
            )""")

    def __init__(self, guild_id: int, channel_id: int, role_id: int, row_id: int = None):
        super().__init__()
        if row_id is not None:
            self.id = row_id
        self.guild_id = guild_id
        self.channel_id = channel_id
        self.role_id = role_id

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = Voicebinds(row_id = result.get("id"),
                             guild_id = result.get("guild_id"),
                             channel_id = result.get("channel_id"),
                             role_id = result.get("role_id"))
            result_list.append(obj)
        return result_list


class AutoPTT(db.DatabaseTable):
    """DB object to keep track of voice to text channel access bindings."""
    __tablename__ = 'autoptt'
    __uniques__ = 'channel_id'

    @classmethod
    async def initial_create(cls):
        """Create the table in the database"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            channel_id bigint PRIMARY KEY NOT NULL,
            ptt_limit bigint null
            )""")

    def __init__(self, channel_id: int, ptt_limit: int):
        super().__init__()
        self.channel_id = channel_id
        self.ptt_limit = ptt_limit

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = AutoPTT(
                channel_id = result.get("channel_id"),
                ptt_limit = result.get("ptt_limit"))
            result_list.append(obj)
        return result_list

    async def version_1(self):
        """DB migration v1"""
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            ALTER TABLE {self.__tablename__} ADD self_inflicted bool NOT NULL DEFAULT false;
            """)

    __versions__ = (version_1,)


async def setup(bot):
    """Add this cog to the main bot."""
    await bot.add_cog(Voice(bot))
