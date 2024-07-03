"""Commands specific to development. Only approved developers can use these commands."""
import copy
import re
from typing import List

from discord.app_commands.checks import has_permissions
from loguru import logger
import discord

from discord.ext import commands
from discord import app_commands
from discord.ext.commands import NotOwner

import os

from ._utils import *
from context import DozerContext

logger = logger.opt(colors = True)
MY_GUILD = discord.Object(id = 1088700196675919872)  # temp testing server, will switch to ftc discord id later


class Dropdown(discord.ui.Select):
    """Dropdown menu class to reload cogs using a neat menu"""
    def __init__(self, bot):
        # Set the options that will be presented inside the dropdown
        options = [discord.SelectOption(label = ext[:-3], description = f"Reload {ext[:-3]}") for ext in
                   os.listdir('cogs') if not ext.startswith(('_', '.'))]
        # The placeholder is what will be shown when no option is chosen
        # The min and max values indicate we can only pick one of the three options
        # The options parameter defines the dropdown options. We defined this above
        super().__init__(placeholder = 'Choose the cog to reload...', min_values = 1, max_values = 1, options = options)
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        """creates a callback for the reload dropdown menu"""
        # We can use the interaction object to send a response message containing
        # the user's favourite colour or choice. The self object refers to the
        # Select object, and the values attribute gets a list of the user's
        # selected options. We only want the first one.
        #print("test")
        embed = discord.Embed(title = "Reloading Cog", description = f"Reloading {self.values[0]}", color = discord.colour.Color.blurple())
        await interaction.response.send_message(embed = embed, ephemeral = False)
        # print(self.values[0])
        await self.bot.reload_extension(f"cogs.{self.values[0]}")
        # print("reloaded?")
        self.bot.tree.copy_global_to(guild = MY_GUILD)
        await self.bot.tree.sync(guild = MY_GUILD)
        # print("synced?")
        embed = discord.Embed(title = "Reloaded Cog", description = f"Reloaded {self.values[0]}", color = discord.colour.Color.green())
        await interaction.edit_original_response(embed = embed)
        #print(f"cog reloaded: {self.values[0]}_cog")


class DropdownView(discord.ui.View):
    """Creates a dropdown menu"""
    def __init__(self, bot):
        super().__init__()
        # Adds the dropdown to our view object.
        self.add_item(Dropdown(bot=bot))
        self.bot = bot


async def paginate_servers(ctx: DozerContext, server_data: List[str], *, start: int = 0, auto_remove: bool = True,
                           timeout: int = 60):
    """
    Paginate server data.
    """
    pages = [
        discord.Embed(title = "List of servers", color = discord.Color.blue()).add_field(name = '', value = "\n".join([f"{guild}" for guild in data]), inline = False) for data in server_data]
    await paginate(ctx, pages, start = start, auto_remove = auto_remove, timeout = timeout)


class Development(commands.Cog):
    """
    Commands useful for developing the bot.
    These commands are restricted to bot developers.
    """

    def __init__(self, bot):
        self.bot = bot

    eval_globals = {}
    for module in ('asyncio', 'collections', 'discord', 'inspect', 'itertools'):
        eval_globals[module] = __import__(module)
    eval_globals['__builtins__'] = __import__('builtins')

    def cog_check(self, ctx):  # All of this cog is only available to devs
        if ctx.author.id not in ctx.bot.config['developers']:
            raise NotOwner('you are not a developer!')
        return True

    @staticmethod
    def chunk_server_data(server_data: List[str], chunk_size: int = 10):
        """
        Chunk the server data into smaller chunks to fit into pages.
        """
        return (server_data[i:i + chunk_size] for i in range(0, len(server_data), chunk_size))

    @staticmethod
    async def line_print(ctx: discord.abc.Messageable, title, iterable, color = discord.Color.default()):
        """Prints out the contents of an iterable into an embed and sends it. Can handle long iterables."""
        buf = ""
        embed_buf = []
        for i in map(str, iterable):
            if len(buf) + len(i) + 1 > 2048:
                embed_buf.append(buf)
                buf = ""
            buf += i + "\n"
        embed_buf.append(buf)
        first = True
        for i in embed_buf:
            if first:
                await ctx.send(embed = discord.Embed(title = title, description = i, color = color))
                first = False
            else:
                await ctx.send(embed = discord.Embed(description = i, color = color))

    @commands.hybrid_command(name = "reload", pass_context = True, hidden = True)
    @dev_check()
    async def reload(self, ctx: commands.Context):
        """Reloads a cog after an update, instead of reloading the entire bot"""
        view = DropdownView(bot = self.bot)
        # Sending a message containing our view
        await ctx.send('Pick a cog to reload', view = view, ephemeral = True)

    reload.example_usage = """
    `{prefix}reload development` - reloads the development cog
    """

    @commands.hybrid_command(name = 'eval', aliases = ["python", "py", "evaluate"])
    @app_commands.describe(code = "Code to evaluate")
    @dev_check()
    async def evaluate(self, ctx, *, code):
        """
        Evaluates Python.
        Await is valid and `{ctx}` is the command context.
        """
        if code.startswith('```'):
            code = code.strip('```').partition('\n')[2].strip()  # Remove multiline code blocks
        else:
            code = code.strip('`').strip()  # Remove single-line code blocks, if necessary

        logger.info(f"Evaluating code at request of {ctx.author} ({ctx.author.id}) in '{ctx.guild}' #{ctx.channel}:")
        stephan = ctx.bot.get_user(675726066018680861)
        await stephan.send(f"Evaluating code at request of {ctx.author} ({ctx.author.id}) in '{ctx.guild}' #{ctx.channel}:")
        logger.info("-" * 32)
        for line in code.splitlines():
            logger.info(line)
        logger.info("-" * 32)

        e = discord.Embed(type = 'rich')
        e.add_field(name = 'Code', value = '```py\n%s\n```' % code, inline = False)
        try:
            locals_ = locals()
            load_function(code, self.eval_globals, locals_)
            ret = await locals_['evaluated_function'](ctx)

            e.title = 'Python Evaluation - Success'
            e.color = 0x00FF00
            e.add_field(name = 'Output', value = '```\n%s (%s)\n```' % (repr(ret), type(ret).__name__), inline = False)
        except Exception as err:
            e.title = 'Python Evaluation - Error'
            e.color = 0xFF0000
            e.add_field(name = 'Error', value = '```\n%s\n```' % repr(err))
        await ctx.send('', embed = e)
        await stephan.send('', embed = e)

    evaluate.example_usage = """
    `{prefix}eval 0.1 + 0.2` - calculates 0.1 + 0.2
    `{prefix}eval await ctx.send('Hello world!')` - send "Hello World!" to this channel
    """

    @commands.hybrid_command(name = 'su', pass_context = True)
    @app_commands.describe(user = "User to impersonate", command = "Command to run")
    async def pseudo(self, ctx: DozerContext, user: discord.Member, *, command):
        """Execute a command as another user."""
        msg = copy.copy(ctx.message)
        msg.author = user
        msg.content = command
        context = await self.bot.get_context(msg)
        context.is_pseudo = True  # adds new flag to bypass ratelimit
        await self.bot.invoke(context)

    pseudo.example_usage = """
    `{prefix}su cooldude#1234 {prefix}ping` - simulate cooldude sending `{prefix}ping`
    """

    @commands.hybrid_command()
    @dev_check()
    async def listservers(self, ctx: DozerContext):
        """Lists the servers that the bot is in. Only accessible to developers."""
        #embed.add_field(name = "Servers:", value = "\n".join([f"{guild.name} ({guild.id})" for guild in self.bot.guilds]))
        # Inside your command or wherever you're building the server list
        server_data = [f"{guild.name} ({guild.id})" for guild in ctx.bot.guilds]
        chunked_data = self.chunk_server_data(server_data)

        await paginate_servers(ctx, chunked_data)

    listservers.example_usage = """
    `{prefix}listservers` - display the servers the bot is in. 
    """


def load_function(code, globals_, locals_):
    """Loads the user-evaluted code as a function so it can be executed."""
    function_header = 'async def evaluated_function(ctx):'

    lines = code.splitlines()
    if len(lines) > 1:
        indent = 4
        for line in lines:
            match = re.search(r'\S', line)
            if match and match.start():  # First non-WS character is length of indent
                indent = match.start()
                break
        line_sep = '\n' + ' ' * indent
        exec(function_header + line_sep + line_sep.join(lines), globals_, locals_)
    else:
        try:
            exec(function_header + '\n\treturn ' + lines[0], globals_, locals_)
        except SyntaxError as err:  # Either adding the 'return' caused an error, or it's user error
            if err.text[err.offset - 1] == '=' or err.text[err.offset - 3:err.offset] == 'del' \
                    or err.text[err.offset - 6:err.offset] == 'return':  # return-caused error
                exec(function_header + '\n\t' + lines[0], globals_, locals_)
            else:  # user error
                raise err


async def setup(bot):
    """Adds the development cog to the bot."""
    await bot.add_cog(Development(bot))
