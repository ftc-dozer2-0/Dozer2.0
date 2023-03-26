import discord
from discord.ext import commands
from discord import app_commands


class MessageMenus(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.ctx_menu = app_commands.ContextMenu(name = 'Report Message',
                                                 callback = self.report_message,
                                                 # sets the callback the view_profile function
                                                 )
        self.bot.tree.add_command(self.ctx_menu)  # add the context menu to the tree

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.ctx_menu.name, type = self.ctx_menu.type)

    async def report_message(self, interaction: discord.Interaction, message: discord.Message):
        # We're sending this response message with ephemeral=True, so only the command executor can see it
        await interaction.response.send_message(
            f'Thanks for reporting this message by {message.author.mention}! The mod team will be looking into this. ',
            ephemeral = False
        )

        # Handle report by sending it into a log channel
        log_channel = interaction.guild.get_channel(1089027854047658054)  # todo: replace with your channel id

        embed = discord.Embed(title = 'Reported Message')
        if message.content:
            embed.description = message.content

        embed.set_author(name = message.author.display_name, icon_url = message.author.display_avatar.url)
        embed.timestamp = message.created_at
        embed.add_field(name = "Reported by",
                        value = f"{interaction.user.display_name} | {interaction.user.id}")  # optional to add reporting person's info
        # also optional, can add message id to db to prevent multiple reports of same message
        url_view = discord.ui.View()
        url_view.add_item(
            discord.ui.Button(label = 'Go to Message', style = discord.ButtonStyle.url, url = message.jump_url))
        await log_channel.send(embed = embed, view = url_view)


async def setup(bot):
    """Adds the message context menus cog to the bot."""
    await bot.add_cog(MessageMenus(bot))
