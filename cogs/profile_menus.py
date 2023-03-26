import discord
from discord.ext import commands
from discord import app_commands


class ProfileMenus(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.ctx_menu = app_commands.ContextMenu(
            name = 'View Profile',
            callback = self.profile,  # sets the callback the view_profile function
        )
        self.bot.tree.add_command(self.ctx_menu)  # add the context menu to the tree

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.ctx_menu.name, type = self.ctx_menu.type)

    async def profile(self, interaction: discord.Interaction, member: discord.Member):
        await interaction.response.send_message(f'{member} joined at {discord.utils.format_dt(member.joined_at)}',
                                                ephemeral = False)  # temp false for testing
        # todo: make this a nice embed with all profile info


async def setup(bot):
    """Adds the profile context menus cog to the bot."""
    await bot.add_cog(ProfileMenus(bot))
