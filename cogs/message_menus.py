import discord
from discord.ext import commands
from discord import app_commands

import db


class MessageMenus(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.ctx_menu = app_commands.ContextMenu(name='Report Message',
                                                 callback=self.report_message,
                                                 # sets the callback the view_profile function
                                                 )
        self.bot.tree.add_command(self.ctx_menu)  # add the context menu to the tree

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.ctx_menu.name, type=self.ctx_menu.type)

    async def report_message(self, interaction: discord.Interaction, message: discord.Message):
        # We're sending this response message with ephemeral=True, so only the command executor can see it
        await interaction.response.send_message(
            f'Thanks for reporting this message by {message.author.mention}! The mod team will be looking into this. ',
            ephemeral=True
        )

        # Handle report by sending it into a log channel
        log_channel = ReportModLog.get_by(guild_id = interaction.guild.id, message_id = interaction.message.id)

        embed = discord.Embed(title='Reported Message')
        if message.content:
            embed.description = message.content

        embed.set_author(name=message.author.display_name, icon_url=message.author.display_avatar.url)
        embed.timestamp = message.created_at
        embed.add_field(name="Reported by",
                        value=f"{interaction.user.display_name} | {interaction.user.id}")  # optional to add reporting person's info
        # also optional, can add message id to db to prevent multiple reports of same message
        url_view = discord.ui.View()
        url_view.add_item(
            discord.ui.Button(label='Go to Message', style=discord.ButtonStyle.url, url=message.jump_url))
        await log_channel[0].send(embed=embed, view=url_view)


class ReportModLog(db.DatabaseTable):
    __tablename__ = "report_table"
    __uniques__ = ("guild_id",)

    @classmethod
    async def initial_create(cls):
        async with db.Pool.acquire() as conn:
            await conn.execute(f"""
            CREATE TABLE {cls.__tablename__} (
            guild_id bigint PRIMARY KEY NOT NULL,
            report_channel bigint null,
            message_id bigint NOT NULL
            )""")

    def __init__(self, guild_id: int, report_channel: int, message_id: int):
        super().__init__()
        self.guild_id = guild_id
        self.report_channel = report_channel
        self.message_id = message_id

    @classmethod
    async def get_by(cls, **kwargs):
        results = await super().get_by(**kwargs)
        result_list = []
        for result in results:
            obj = ReportModLog(guild_id=result.get("guild_id"), report_channel=result.get("report_channel"),
                               message_id=result.get("message_id"))
            result_list.append(obj)
        return result_list


async def setup(bot):
    """Adds the message context menus cog to the bot."""
    await bot.add_cog(MessageMenus(bot))
