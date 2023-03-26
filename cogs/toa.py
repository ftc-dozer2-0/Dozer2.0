"""Provides commands that pull information from The Orange Alliance, an FTC info API."""
from urllib.parse import urljoin
import datetime
import discord
import async_timeout
from discord.ext import commands
import aiotoa.models
from aiotoa import *
from cogs._utils import *
from discord import app_commands

embed_color = discord.Color(0xf89808)


def to_season_key(base_year):
    """converts a start year (2017) to a TOA season key (1718)"""
    if base_year is None:
        return None
    return f"{(base_year) % 100}{(base_year + 1) % 100}"


class TOA(Cog):
    """TOA commands"""
    def __init__(self, bot):
        super().__init__(bot)
        #self.parser = TOASession(bot.config['toa']['key'], bot.config['toa']['app_name'], bot.http_session)

    @staticmethod
    def get_current_season(as_year=False):
        """get the current season code based on the date"""
        today = datetime.datetime.today()
        year = today.year
        # ftc kickoff is always the 2nd saturday of september (except when on 9/11)
        kickoff = [d for d in [datetime.datetime(year=year, month=9, day=i) for i in range(8, 15)] if d.weekday() == 5][0]

        if kickoff > today:
            return year - 1 if as_year else to_season_key(year - 1)
        else:
            return year if as_year else to_season_key(year)

    @staticmethod
    def convert_season(season_key):
        """converts season names to start years"""
        try:
            if season_key.startswith("year"):
                return int(season_key[4:])
            else:
                return 1999 + int(season_key) % 100
        except ValueError:
            pass

        return {
            "quadquandary": 2007,
            "faceoff": 2008,
            "hotshot": 2009,
            "getoverit": 2010,
            "bowledover": 2011,
            "ringitup": 2012,
            "blockparty": 2013,
            "bp": 2013,
            "cascadeeffect": 2014,
            "cascade": 2014,
            "resq": 2015,
            "velocityvortex": 2016,
            "vv": 2016,
            "relicrecovery": 2017,
            "relic": 2017,
            "rr": 2017,
            "roverruckus": 2018,
            "rover": 2018,
            "rr2": 2018,
        }.get(str(season_key).lower().replace("_", "").replace("-", ""), season_key)

    @staticmethod
    def fmt_season_code(s):
        """formats a season key string '1718' as '2017-2018'"""
        return "20" + s[:2] + "-" + "20" + s[2:]

    async def get_teamdata(self, team_num: int):
        """Obtains team data from a separate non-TOA api returning ftc_teams.pickle.gz-like data"""
        if self.bot.config['toa']['teamdata_url']:
            async with self.bot.http_session.get(urljoin(self.bot.config['toa']['teamdata_url'], str(team_num))) as response, \
                    async_timeout.timeout(5) as _:
                return await response.json() if response.status < 400 else {}
        else:
            raise RuntimeError("teamdata not configured")
            try:
                toa_data = await self.parser.team(team_num)
            except AioTOAError:
                return {}
            return {
                "number": team_num,
                "rookie_year": str(toa_data.rookie_year),
                "seasons": [{
                    "city": toa_data.city,
                    "country": toa_data.country,
                    "location": [0, 0],
                    "motto": "",
                    "name": toa_data.team_name_short,
                    "org": toa_data.team_name_long,
                    "postal_code": toa_data.zip_code,
                    "state_prov": toa_data.state_prov,
                    "website": toa_data.website or "",
                    "year": toa_data.rookie_year,
                }]
            }

    @commands.hybrid_group(invoke_without_command=True, case_insensitive=True, aliases=['theorangealliance', 'orangealliance'], name = 'toa')
    async def toa(self, ctx, team_num: int, season: str = None):
        """
        Get FTC-related information from The Orange Alliance.
        If no subcommand is specified, the `team` subcommand is inferred, and the argument is taken as a team number.
        """
        await self.team.callback(self, ctx, team_num, season)  # This works but Pylint throws an error

    toa.example_usage = """
    `{prefix}toa 5667` - show information on team 5667, Robominers
    """

    @toa.command()
    @bot_has_permissions()
    async def disclaimer(self, ctx):
        """
        Display a TOS compliance disclaimer for TOA commands.
        """
        p = ctx.prefix
        e = discord.Embed(color=embed_color, title="TOA Data TOS Compliance Disclaimer")
        e.description = f"The data returned by most `{p}toa` subcommands is in fact downloaded from __The " \
            f"Orange Alliance.__"
        e.add_field(name='However...', value="Under certain configurations of this Dozer-like, " +
                    f"`{p}toa team` may return data that is pulled from " +
                    "a mirror of FIRST's registration data, updated biweekly.", inline=False)
        why = """
Using data that is sourced **_directly from FIRST's servers_** has some benefits.
It allows such a Dozer-like to ensure that it's returned data is both **accurate and up to date.**

""" + "TOA often does not pick up on the registration of new teams for months, and for at least a period of time, " \
        "would return **incorrect data** on older teams."
        e.add_field(name='Why?', value=why, inline=False)

        addn = """TOA will not (and likely never) return registration data for previous seasons,
~~at least intentionally~~. There is often historical and archival values to this, so FIRST data
is used to suppliment the `season` argument of the `team` command, to allow users to look at past names
and locations of teams who may have moved around or renamed over the years. """.replace("\n", " ")
        e.add_field(name="Additionally,", value=addn, inline=False)
        e.add_field(name="This is all intended to improve user experiences!",
                    value="And to represent teams accurately!", inline=False)
        await ctx.send('', embed=e, ephemeral=True)

    @toa.command()
    @bot_has_permissions(embed_links=True)
    @app_commands.describe(team_num="The team number to look up", season="The season you want to see the team's info for")
    async def team(self, ctx, team_num: int, season: str = None):
        """Get information on an FTC team by number."""
        # Fun fact: this no longer actually queries TOA. It queries a server that provides FIRST data.
        team_data = await self.get_teamdata(team_num)  # await self.parser.req("team/" + str(team_num))
        year = int(self.convert_season(season)) if season else None
        if not team_data:
            # rip
            await ctx.send("This team does not have any data on it yet, or it does not exist!", ephemeral=True)
            return

        season_data = None
        for team_season in team_data['seasons']:
            if not year or team_season['year'] == year:
                season_data = team_season
                break
        if not season_data:
            if not self.bot.config['toa']['teamdata_url'] and year is not None:
                await ctx.send("This bot does not have past team registration data available!", ephemeral=True)
            else:
                await ctx.send(f"This team did not compete in the {self.fmt_season_code(to_season_key(int(year)))} season!", ephemeral=True)
            return

        # many team entries lack a valid url
        website = (season_data['website']).strip()
        if website and not (website.startswith("http://") or website.startswith("https://")):
            website = "http://" + website
        e = discord.Embed(color=embed_color,
                          title=f'FIRST® Tech Challenge Team {team_num}',
                          url=f'https://ftc-events.firstinspires.org/{self.get_current_season(as_year=True)}/team/{team_num}')
        e.add_field(name='Name', value=season_data["name"].strip() or "_ _")  # renders as blank on clients
        e.add_field(name='Rookie Year', value=team_data['rookie_year'])
        e.add_field(name='Location', value=', '.join((season_data["city"], season_data["state_prov"], season_data["country"])))
        e.add_field(name='Website', value=website or 'n/a')
        if season_data["motto"].strip():
            e.add_field(name='Motto', value=season_data['motto'])
        # e.add_field(name='Team
        # Info Page', value=f'https://www.theorangealliance.org/teams/{team_num}')
        #e.set_footer(text=f'May contain data from FIRST with TOA data. For more information, see '
        #                  f'{ctx.prefix}toa disclaimer')
        await ctx.send('', embed=e, ephemeral=True)

    team.example_usage = """
    `{prefix}toa team 11115` - show information on team 11115, Gluten Free
    `{prefix}toa team 7486` - show information on team 7486, Suffern Robotics
    `{prefix}toa team 7486 1516` - show information on team 7486, Team Erebor, in Res-Q
    """

    @toa.command()
    @bot_has_permissions(embed_links=True)
    @app_commands.describe(team_num="The team number to look up", season="The season you want to see the team's info for")
    async def events(self, ctx, team_num: int, season=None):
        """Get events for an ftc team defaulting to current year"""
        season = to_season_key(self.convert_season(season)) or self.get_current_season()
        fmt_season = self.fmt_season_code(season)
        try:
            events = await self.parser.team_events(team_num, season)
        except aiotoa.AioTOAError:
            await ctx.send("Couldn't get data!", ephemeral=True)
            return
        e = discord.Embed(color=embed_color,
                          title=f"Events for FTC team {team_num} in {fmt_season}:")
        for event in sorted(map(lambda e: e.event, events), key=lambda e: e.start_date, reverse=True):  # type: aiotoa.models.Event
            # tweak formatting a small bit
            event.region_key = f"[{event.region_key}]" if event.region_key != "CMP" else ""
            date_str = event.start_date.strftime(f"%B {event.start_date.day}, %Y")
            if event.start_date != event.end_date:
                date_str += event.end_date.strftime(f" - %B {event.end_date.day}, %Y")
            e.add_field(name=f"{event.region_key} {event.event_name}",
                        value=f"[[link]](https://theorangealliance.org/events/{event.event_key}) "
                              f"{event.city}, {event.state_prov} {event.country} | {date_str}",
                        inline=False)

        await ctx.send(embed=e, ephemeral=True)

    events.example_usage = """
    `{prefix}toa events 4174 1617` - list 4174 Atomic Theory's events for the 2016-2017 season, Velocity Vortex
    """

    @toa.command()
    @bot_has_permissions(embed_links=True)
    @app_commands.describe(team_num="The team number to look up", season="The season you want to see the team's info for")
    async def awards(self, ctx, team_num: int, season=None):
        """TODO: display awards command"""
        season = to_season_key(self.convert_season(season)) or self.get_current_season()
        fmt_season = self.fmt_season_code(season)
        try:
            events = await self.parser.team_events(team_num, season)
        except aiotoa.AioTOAError:
            await ctx.send("Couldn't get data!", ephemeral=True)
            return
        e = discord.Embed(color=embed_color,
                          title=f"Awards for FTC team {team_num} in {fmt_season}:")
        raise NotImplementedError("toa api is broken so this is a TODO")


async def setup(bot):
    """Adds the TOA cog to the bot."""
    await bot.add_cog(TOA(bot))
