"""General, basic commands that are common for Discord bots"""

import inspect
import discord
from discord.ext.commands import BadArgument, cooldown, BucketType, Group, has_permissions
from discord.ext import commands
from ._utils import *
from discord import app_commands


class General(Cog):
    """General commands common to all Discord bots."""

    def __init__(self, bot) -> None:
        super().__init__(bot)
        self.name = 'Dozer'
        self.bot = bot

    @Cog.listener()
    async def on_ready(self):
        """Queries the name of the bot on connection to Discord"""
        self.name = (await self.bot.application_info()).name

    @commands.hybrid_command()
    async def ping(self, ctx):
        """Check the bot is online, and calculate its response time."""
        if ctx.guild is None:
            location = 'DMs'
        else:
            location = 'the **%s** server' % ctx.guild.name
        response = await ctx.send(f'Pong! We\'re in {location}.', ephemeral=True)
        delay = response.created_at - ctx.message.created_at
        await response.edit(
            content=response.content + f'\nTook {delay.seconds * 1000 + delay.microseconds // 1000} ms to respond.')

    ping.example_usage = """
    `{prefix}ping` - Calculate and display the bot's response time
    """

    @cooldown(1, 10, BucketType.channel)
    @commands.command(name='help', aliases=['about', 'plowie', 'yikes', 'commands', 'command', 'info'])
    @bot_has_permissions(add_reactions=True, embed_links=True,
                         read_message_history=True)  # Message history is for internals of paginate()
    async def base_help(self, ctx, *target):
        """Show this message."""
        if not target:  # No commands - general help
            await self._help_all(ctx)
        elif len(target) == 1:  # Cog or command
            target_name = target[0]
            if target_name in ctx.bot.cogs:
                await self._help_cog(ctx, ctx.bot.cogs[target_name])
            else:
                command = ctx.bot.get_command(target_name)
                if command is None:
                    raise BadArgument('that command/cog does not exist!')
                else:
                    await self._help_command(ctx, command)
        else:  # Command with subcommand
            command = ctx.bot.get_command(' '.join(target))
            if command is None:
                raise BadArgument('that command does not exist!')
            else:
                await self._help_command(ctx, command)

    base_help.example_usage = """
    `{prefix}help` - General help message
    `{prefix}help help` - Help about the help command
    `{prefix}help General` - Help about the General category
    """

    async def _help_all(self, ctx):
        """Gets the help message for all commands."""
        info = discord.Embed(title=f'{self.name}: Info',
                             description='The guild management bot for the FTC server' if self.name == "FTC Server Dozer" else
                             'A guild management bot for FIRST Discord servers',
                             color=discord.Color.blue())
        info.set_thumbnail(url=self.bot.user.avatar.url)
        info.add_field(name='About',
                       value=f"{self.name}: A collaborative bot for the FIRST Discord community, rebuilt by the FTC "
                             "Dozer 2.0 Project Team.")
        info.add_field(name=f'About `{ctx.prefix}{ctx.invoked_with}`', value=inspect.cleandoc(f"""
        This command can show info for all commands, a specific command, or a category of commands.
        Use `{ctx.prefix}{ctx.invoked_with} {ctx.invoked_with}` for more information.
        """), inline=False)
        info.add_field(name='Differences from Upstream Dozer', value="[These WERE documented in detail here]"
                                                                     "(https://github.com/guineawheek/Dozer/blob/development/EXTRA_FEATURES.md)")
        info.add_field(name='Support',
                       value="Join our development server at haha funny or ping @skhynix#1554 for "
                             "support, to help with development, or if you have any questions or comments!")
        info.add_field(name="Open Source",
                       value=f"{self.name} is open source! Feel free to view and contribute to our Python code "
                             "[on Github](https://github.com/ftc-dozer2-0/Dozer2.0) | Unfortunately, while we're "
                             "rebuilding the bot, the repo is private.")
        info.set_footer(text=f'{self.name} Help | all commands | Info page')
        await self._show_help(ctx, info, f'{self.name}: Commands', '', 'all commands', ctx.bot.commands)

    async def _help_command(self, ctx, command):
        """Gets the help message for one command."""
        if command.aliases:
            fqn = f"{command.full_parent_name}[{'|'.join([command.name] + list(command.aliases))}]"
        else:
            fqn = command.qualified_name
        info = discord.Embed(title=f'Command: {ctx.prefix}{fqn} {command.signature}',
                             description=command.help or (
                                 None if command.example_usage else 'No information provided.'),
                             color=discord.Color.blue())
        usage = command.example_usage
        if usage is not None:
            info.add_field(name='Usage', value=usage.format(prefix=ctx.prefix, name=ctx.invoked_with),
                           inline=False)
        info.set_footer(text=f'{self.name} Help | {command.qualified_name} command | Info')

        # need to figure out how to walk command.commands correctly
        def all_subcommands(cmd):
            if not isinstance(cmd, Group):
                return set()
            return cmd.commands | set.union(*[all_subcommands(c) for c in cmd.commands])

        await self._show_help(ctx, info, 'Subcommands: {prefix}{name} {signature}', '',
                              '{command.qualified_name!r} command',
                              all_subcommands(command), command=command, name=command.qualified_name,
                              signature=command.signature)

    async def _help_cog(self, ctx, cog):
        """Gets the help message for one cog."""
        await self._show_help(ctx, None, 'Category: {cog_name}', inspect.cleandoc(cog.__doc__ or ''),
                              '{cog_name!r} category',
                              (command for command in ctx.bot.commands if command.cog is cog),
                              cog_name=type(cog).__name__)

    async def _show_help(self, ctx, start_page, title, description, footer, commands, **format_args):
        """Creates and sends a template help message, with arguments filled in."""
        format_args['prefix'] = ctx.prefix
        footer = f'{self.name} Help | {footer} | Page {"{page_num} of {len_pages}"}'
        # Page info is inserted as a parameter so page_num and len_pages aren't evaluated now
        if commands:
            command_chunks = list(chunk(sorted(commands, key=lambda cmd: cmd.qualified_name), 4))
            format_args['len_pages'] = len(command_chunks)
            pages = []
            for page_num, page_commands in enumerate(command_chunks):
                format_args['page_num'] = page_num + 1
                page = discord.Embed(title=title.format(**format_args),
                                     description=description.format(**format_args), color=discord.Color.blue())
                for command in page_commands:
                    if command.short_doc:
                        embed_value = command.short_doc
                    elif command.example_usage:  # Usage provided - show the user the command to see it
                        embed_value = f'Use `{ctx.prefix}{ctx.invoked_with} {command.qualified_name}` for more information.'
                    else:
                        embed_value = 'No information provided.'
                    if command.aliases:
                        cmd_names = "|".join([command.name] + list(command.aliases))
                        page.add_field(
                            name=f"{ctx.prefix}{command.full_parent_name}[{cmd_names}] {command.signature}",
                            value=embed_value,
                            inline=False)
                    else:
                        page.add_field(name=f"{ctx.prefix}{command.qualified_name} {command.signature}",
                                       value=embed_value, inline=False)

                page.set_footer(text=footer.format(**format_args))
                pages.append(page)

            if start_page is not None:
                pages.append({'info': start_page})

            if len(pages) == 1:
                await ctx.send(embed=pages[0])
            elif start_page is not None:
                info_emoji = '\N{INFORMATION SOURCE}'
                p = Paginator(ctx, (info_emoji, ...), pages, start='info',
                              auto_remove=ctx.channel.permissions_for(ctx.me))
                async for reaction in p:
                    if reaction == info_emoji:
                        p.go_to_page('info')
            else:
                await paginate(ctx, pages, auto_remove=ctx.channel.permissions_for(ctx.me))
        elif start_page:  # No commands - command without subcommands or empty cog - but a usable info page
            await ctx.send(embed=start_page)
        else:  # No commands and no info page
            format_args['len_pages'] = 1
            format_args['page_num'] = 1
            embed = discord.Embed(title=title.format(**format_args), description=description.format(**format_args),
                                  color=discord.Color.blue())
            embed.set_footer(text=footer.format(**format_args))
            await ctx.send(embed=embed)

    @has_permissions(change_nickname=True)
    @commands.hybrid_command(name='nick', aliases=['nickname', 'setnick', 'setnickname', 'changename', 'changenick',
                                                   'changenickname'])
    @app_commands.describe(nicktochangeto='Your new nickname')
    async def nick(self, ctx, *, nicktochangeto):
        """Allows a member to change their nickname."""
        if ctx.author.top_role >= ctx.guild.me.top_role:
            await ctx.send(f"{ctx.author.mention}, your top role is the same as or higher than mine!")
        await ctx.author.edit(nick=nicktochangeto[:32])
        await ctx.send("Nick successfully changed to " + nicktochangeto[:32])
        if len(nicktochangeto) > 32:
            await ctx.send("Warning: truncated nickname to 32 characters")

    nick.example_usage = """
    `{prefix}nick cool nickname` - set your nickname to "cool nickname" 
    """

    @commands.hybrid_command(name='invite', aliases=['botinvite', 'botinviteurl', 'botinvitelink'])
    async def invite(self, ctx):
        """
        Display the bot's invite link.
        The generated link gives all permissions the bot requires. If permissions are removed, some commands will be unusable.
        """
        perms = 1073081847
        for cmd in ctx.bot.walk_commands():
            perms |= cmd.required_permissions.value

        if self.name == "FTC Server Dozer":
            await ctx.send("Here's an invite link for the public version of this bot, "
                           "[Plowie](https://discordapp.com/oauth2/authorize?client_id=474456308813266945"
                           "&scope=bot&permissions=1073081847)")
        else:
            await ctx.send(f'<{(discord.utils.oauth_url(ctx.me.id, discord.Permissions(perms)))}>')

    invite.example_usage = """
    `{prefix}invite` - display the bot's invite link. 
    """

    @has_permissions(create_instant_invite=True)
    @bot_has_permissions(create_instant_invite=True)
    @app_commands.describe(num='The number of invites to create',
                           hours='The number of hours the invite should last')
    @commands.hybrid_command(name='serverinvite', aliases=['serverinvitelink', 'serverinviteurl', 'serverinv'])
    async def invites(self, ctx, num, hours=24):
        """
        Generates a set number of single use invites.
        """
        # settings = session.query(WelcomeChannel).filter_by(id=ctx.guild.id).one_or_none()
        config = await self.bot.cogs['Moderation'].guild_config.query_one(guild_id=ctx.guild.id)
        if config is None or not config.welcome_channel_id:
            await ctx.send(
                f"There is no welcome channel set. Please set one using `{ctx.prefix}serverconfig welcome channel` and try again.")
            return
        else:
            invitechannel = ctx.bot.get_channel(config.welcome_channel_id)
            if invitechannel is None:
                await ctx.send(
                    f"There was an issue getting your welcome channel Please set it again using `{ctx.prefix}serverconfig welcome channel`.")
                return
            text = ""
            for i in range(int(num)):
                invite = await invitechannel.create_invite(max_age=hours * 3600, max_uses=1, unique=True,
                                                           reason=f"Autogenerated by {ctx.author}")
                text += f"Invite {i + 1}: <{invite.url}>\n"
            await ctx.send(text)

    invites.example_usage = """
    `{prefix}invtes 5` - Generates 5 single use invites.
    `{prefix}invites 2 12` Generates 2 single use invites that last for 12 hours.
    """


async def setup(bot):
    """Adds the general cog to the bot"""
    bot.remove_command('help')
    await bot.add_cog(General(bot))
