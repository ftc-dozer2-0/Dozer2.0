import discord
from discord.ext import commands
from discord import app_commands
import typing

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
        # await interaction.response.send_message(f'{member} joined at {discord.utils.format_dt(member.joined_at)}',
        # ephemeral = False)  # temp false for testing
        if member is None:
            member = interaction.user

        icon_url = member_avatar_url(member)

        embed = discord.Embed(title = member.display_name, description = f'{member!s} ({member.id})',
                              color = member.color)
        embed.add_field(name = 'Bot Created' if member.bot else 'Account Created',
                        value = discord.utils.format_dt(member.created_at), inline = True)
        embed.add_field(name = 'Member Joined', value = discord.utils.format_dt(member.joined_at), inline = True)
        if member.premium_since is not None:
            embed.add_field(name = 'Member Boosted', value = discord.utils.format_dt(member.premium_since),
                            inline = True)
        embed.add_field(name = 'Color', value = str(member.color).upper(), inline = True)

        status = 'DND' if member.status is discord.Status.dnd else member.status.name.title()
        if member.status is not discord.Status.offline:
            platforms = self.pluralize([platform for platform in ('web', 'desktop', 'mobile') if
                                        getattr(member, f'{platform}_status') is not discord.Status.offline])
            status = f'{status} on {platforms}'
        activities = ', '.join(self._format_activities(member.activities))
        embed.add_field(name = 'Status and Activity', value = f'{status}, {activities}', inline = True)

        embed.add_field(name = 'Roles', value = ', '.join(role.name for role in member.roles[:0:-1]) or 'None',
                        inline = False)
        embed.add_field(name = 'Icon URL', value = icon_url, inline = False)
        embed.set_thumbnail(url = icon_url)
        await interaction.response.send_message(embed = embed)

    @staticmethod
    def _format_activities(activities: typing.Sequence[discord.Activity]) -> typing.List[str]:
        if not activities:
            return []

        def format_activity(activity: discord.Activity) -> str:
            if isinstance(activity, discord.CustomActivity):
                return f"{activity.emoji} {activity.name}"
            elif isinstance(activity, discord.Spotify):
                return f'listening to {activity.title} by {activity.artist} on Spotify'
            elif activity.type is discord.ActivityType.listening:
                return f'listening to {activity.name}'  # Special-cased to insert " to"
            else:
                return f'{activity.type.name} {activity.name}'

        # Some games show up twice in the list (e.g. "Rainbow Six Siege" and "Tom Clancy's Rainbow Six Siege") so we
        # need to dedup them by string similarity before displaying them
        matcher = SequenceMatcher(lambda c: not c.isalnum(), autojunk=False)
        filtered = [activities[0]]
        for activity in activities[1:]:
            matcher.set_seq2(activity.name)  # Expensive metadata is computed about seq2, so change it less frequently
            for filtered_activity in filtered:
                matcher.set_seq1(filtered_activity.name)
                if matcher.quick_ratio() < 0.6 and matcher.ratio() < 0.6:  # Use quick_ratio if we can as ratio is slow
                    filtered.append(activity)
                    break

        return [format_activity(activity) for activity in filtered]

    @staticmethod
    def pluralize(values: typing.List[str]) -> str:
        """Inserts commas and "and"s in the right places to create a grammatically correct list."""
        if len(values) == 0:
            return ''
        elif len(values) == 1:
            return values[0]
        elif len(values) == 2:
            return f'{values[0]} and {values[1]}'
        else:
            return f'{", ".join(values[:-1])}, and {values[-1]}'


async def setup(bot):
    """Adds the profile context menus cog to the bot."""
    await bot.add_cog(ProfileMenus(bot))


def member_avatar_url(m: discord.Member, static_format = 'png', size = 32):
    """return avatar url"""
    if m.avatar is not None:
        return m.avatar.replace(static_format = static_format, size = size)
    else:
        return None
