import os
import logging
import asyncio
import aiohttp
import interactions
import python_weather
from .helpers import levenshtein_ratio_and_distance
from .db import StreamDAL, Session, StreamLink
from .google import create_factchect_service, GoogleError


log = logging.getLogger("feedbot.discord")

SERVER_ID = os.environ.get("SERVER_ID")
try:
    SERVER_ID = int(SERVER_ID)
except TypeError:
    log.error("No server id supplied, will not be able to use scoped content.")
    SERVER_ID = 0

POST_URL = os.environ.get("POST_URL")

GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
try:
    fact_check = create_factchect_service(GOOGLE_API_KEY)
except GoogleError:
    log.error("No google api connection has been made (GOOGLE_API_KEY), fact checking disabled.")
    fact_check = None


MAX_STREAM_LINKS = 6
MAX_CLAIMS = 6

client = interactions.Client(os.environ.get("DISCORD_TOKEN"))


def match_names(name: str, streams: list) -> {}:
    result = {}
    for s in streams:
        sn = s.name.lower().strip()
        n = name.lower().strip()
        result[s.id] = levenshtein_ratio_and_distance(n, sn, ratio_calc=True)
    return result


async def check_online(url) -> bool:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                return resp.status >= 200 and resp.status < 400
    except Exception as e:
        log.error(e)
        return False
    return False


async def get_streams() -> str:
    async with Session() as session:
        stream_dal = StreamDAL(session)
        streams = await stream_dal.get_all_streams()
        return streams


@client.command(
    name="stream",
    description="Search for streams by title.",
    scope=SERVER_ID,
    options=[
        interactions.Option(
            type=interactions.OptionType.STRING,
            name="search_string",
            description="What to search for",
            required=True,
            autocomplete=True
        ),
    ],
)
async def stream_command(context, search_string: str = ""):
    streams = await get_streams()

    if not len(streams):
        return await context.send("Could not find any streams...", ephemeral=True)

    if len(search_string):
        log.info(f"Search sting is: {search_string}")

        matches = match_names(search_string, streams)
        stream_info = [{"name": s.name, "lr": matches[s.id], "url": s.url} for s in streams]
        stream_info.sort(key=lambda x: x["lr"], reverse=True)
        best = max([m["lr"] for m in stream_info])
        if best >= 1.0:
            over_treshold = [stream_info[0]]
        elif best == 0.0:
            over_treshold = []
        else:
            over_treshold = [s for s in stream_info[:MAX_STREAM_LINKS] if s["lr"] >= best * 0.25]
    else:
        log.info("Blank search string given.")
        over_treshold = [{"name": s.name, "url": s.url} for s in streams[:MAX_STREAM_LINKS]]

    if not len(over_treshold):
        return await context.send("Could not find a good enough match...", ephemeral=True)

    log.info("Generating message to send.")

    message = ""
    several = len(over_treshold) > 1
    for s in over_treshold:
        online = await check_online(s["url"])
        url = s["url"]
        if several:
            url = f"<{url}>"
        message += f"{'~~' if not online else ''}**{s['name']}:** {url}{'~~' if not online else ''}"
        message += "\n" if several else ""

    log.info("Sending message....")
    log.info(message)
    return await context.send(message)


@client.command(
    name="removestream",
    description="Remove stream based on url.",
    scope=SERVER_ID,
    options=[
        interactions.Option(
            name="url",
            description="What URL to delete from database",
            type=interactions.OptionType.STRING,
            required=True
        )
    ]
)
async def remove_command(context, url: str):
    async with Session() as session:
        async with session.begin():
            stream_dal = StreamDAL(session)
            result = await stream_dal.remove_streamlink(url)
            if result:
                return await context.send("Removed stream from database.")

    return await context.send("Did not find any streams with that url to remove.")


@client.command(
    name="addstream",
    description="Add a new stream",
    scope=SERVER_ID,
    options=[]
)
async def stream_enter_modal(context):
    modal = interactions.Modal(
        title="Add new stream",
        custom_id="stream_enter_form",
        components=[
            interactions.TextInput(
                style=interactions.TextStyleType.SHORT,
                label="Short descriptive name for the stream",
                custom_id="stream_input_name",
                min_length=2,
                max_length=64
            ),
            interactions.TextInput(
                style=interactions.TextStyleType.PARAGRAPH,
                label="URL",
                custom_id="stream_input_url",
                min_length=10,
                max_length=2048
            )
        ]
    )
    await context.popup(modal)


@client.modal("stream_enter_form")
async def stream_enter_response(context, name: str, url: str):
    if len(url.split()) > 1 or not any(x in url for x in ["http", "https"]):
        return await context.send("That URL doesn't look right.", ephemeral=True)

    online = await check_online(url)
    if not online:
        return await context.send("That URL had a bad respond code, are you sure it's online?", ephemeral=True)

    streams = await get_streams()
    
    async with Session() as session:
        async with session.begin():
            stream_dal = StreamDAL(session)
        
            for s in streams:
                if s.url == url:
                    await stream_dal.update_stream_name(s.id, name)
                    return await context.send(f"Stream \"{name}\" was already in the database, updated the title instead.")
            else:
                s = await stream_dal.create_streamlink(name, context.author.nick, url)
                return await context.send(f"Stream \"{name}\" has been added to the database.")


@client.autocomplete(
    command="stream", name="search_string"
)
async def do_autocomplete(context, *args):
    streams = await get_streams()
    choices = [
        interactions.Choice(name=s.name, value=s.name) for s in streams
    ]
    await context.populate(choices)

if fact_check:
    @client.command(
        name="factcheck",
        description="Search multiple sources for fact checks",
        scope=SERVER_ID,
        options=[
            interactions.Option(
                name="search_string",
                description="Keywords or phrase to search for",
                type=interactions.OptionType.STRING,
                required=True
            )
        ]
    )
    async def fact_check_select(context, search_string):
        query = fact_check.search(query=search_string)
        try:
            results = query.execute()
        except Exception as e:
            raise e
            return await context.send("Unknown error during fact-checking...", ephemeral=True)

        if "claims" not in results:
            return await context.send("Could not find any claims matching that text...", ephemeral=True)

        if not len(results["claims"]):
            return await context.send("Could not find any claims matching that text...", ephemeral=True)

        claims = results["claims"][:MAX_CLAIMS]

        confirm_button = interactions.Button(
            style=interactions.ButtonStyle.DANGER,
            label="Post this result?",
            custom_id="factcheck_confirm_button"
        )

        claim_text = claims[0]["text"]

        if "claimReview" in claims[0]:
            claim_url = claims[0]["claimReview"][0]["url"]
            claim_title = claims[0]["claimReview"][0]["title"]
            claim_rating = claims[0]["claimReview"][0]["textualRating"]
        else:
            return await context.send("Something weird about the results...", ephemeral=True)


        msg = f"Fact check: ***{claim_rating}***\n\n**{claim_title}**\n*{claim_text}*\n<{claim_url}>"


        await context.send(msg, components=[confirm_button], ephemeral=True)


@client.component("factcheck_confirm_button")
async def post_factcheck(context):
    await context.send(context.message.content)


@client.command(
    name="kyivweather",
    description="Post current weather",
    scope=SERVER_ID,
    options=[]
)
async def kyiv_weather_command(context):
    return await weather_command(context, "Kyiv")

@client.command(
    name="weather",
    description="Post current weather for location",
    options=[
        interactions.Option(
            name="location",
            description="A location to search for.",
            type=interactions.OptionType.STRING,
            required=True
        )    
    ]
)
async def weather_command(context, location: str):
    wclient = python_weather.Client(format=python_weather.METRIC)
    try:
        weather = await wclient.find(location)
    except:
        return await context.send("Couldn't find a location matching that text.", ephemeral=True)

    wind = weather.current.wind_display
    c = weather.current.temperature
    sky = weather.current.sky_text
    op = weather.current.observation_point
    txt = f"**{op}**\n{sky}\nTemp: **{c}**℃/**{round((c * 9/5) + 32)}**F\nWind: *{wind}*"

    await wclient.close()
    await context.send(txt)


@client.command(
    name="posterity",
    description="Sends this link to a service that downloads videos for posterity",
    options=[]
)
async def open_posterity_modal(context):
    modal = interactions.Modal(
        title="Save video for posterity",
        custom_id="posterity_enter_form",
        components=[
            interactions.TextInput(
                style=interactions.TextStyleType.SHORT,
                label="A descriptive title of this video",
                custom_id="posterity_input_title",
                min_length=4,
                max_length=256
            ),
            interactions.TextInput(
                style=interactions.TextStyleType.PARAGRAPH,
                label="URL",
                custom_id="posterity_input_url",
                min_length=10,
                max_length=1024
            ),
            interactions.TextInput(
                style=interactions.TextStyleType.SHORT,
                label="Content warning",
                custom_id="posterity_input_cw",
                min_length=0,
                max_length=128
            )
        ]
    )
    await context.popup(modal)


@client.modal("posterity_enter_form")
async def posterity_enter_response(context, title: str, url: str, cw: str):
    if len(url.split()) > 1 or not any(x in url for x in ["http", "https"]):
        return await context.send("That URL doesn't look right.", ephemeral=True)

    online = await check_online(url)
    if not online:
        return await context.send("That URL had a bad respond code, are you sure it's valid?", ephemeral=True)


    data = {
        "url": url,
        "title": title,
        "content_warning": cw,
        "source": "Discord"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(POST_URL, json=data) as resp:
                if resp.status >= 200 and resp.status < 400:
                    return await context.send(f"Video was sent to ras.putin.no for downloading...", ephemeral=True)
    except Exception as e:
        log.error(e)

    return await context.send(f"We got a bad reply from the server, video was **not** saved.", ephemeral=True)


@client.event
async def on_ready():
    log.info("We have logged in!")

def run_bot():
    client.start()
