# pylint: skip-file
"""incomplete cog, should've been stuck on another branch"""
import discord
import aiohttp
import async_timeout
from bs4 import BeautifulSoup
from discord.ext import commands


class VendorSearcher:
    base_url = ""

    def __init__(self, bot: commands.Bot, http_session = None) -> None:
        if not http_session:
            http_session = aiohttp.ClientSession()
        self.http = http_session
        self.bot = bot

    async def get_soup(self, url):
        async with self.http.get(url) as response, async_timeout.timeout(5) as _:
            return BeautifulSoup(response.text(), 'html.parser')

    async def search(self, query: str) -> dict:
        pass


async def setup(bot):
    pass
