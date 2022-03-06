import logging
import asyncio
import aiohttp
import interactions
import os
from .helpers import levenshtein_ratio_and_distance

from .db import StreamDAL, Session, StreamLink

SERVER_ID = os.environ.get("SERVER_ID")
try:
    SERVER_ID = int(SERVER_ID)
except TypeError:
    SERVER_ID = 0

MAX_STREAM_LINKS = 5
log = logging.getLogger("feedbot.discord")

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
        ),
    ],
)
async def stream_command(context, search_string: str):
    streams = await get_streams()
    if len(streams):
        matches = match_names(search_string, streams)
        stream_info = [{"name": s.name, "lr": matches[s.id], "url": s.url} for s in streams]
        stream_info.sort(key=lambda x: x["lr"], reverse=True)
        best = max([m["lr"] for m in stream_info])

        if best > 0.0:
            txt = ""
            over_treshold = [s for s in stream_info[:MAX_STREAM_LINKS] if s["lr"] >= best * 0.85]
            if len(over_treshold) > 1 and best < 1.0:
                txt = f"Found these matching streams:"
                for s in over_treshold:
                    online = await check_online(s["url"])
                    txt += f"\n**{s['name']}:** "
                    if online:
                        txt += f"<{s['url']}>"
                    else:
                        txt += f"~~<{s['url']}>~~"
            else:
                s = over_treshold[0]
                online = await check_online(s["url"])
                if online:
                    txt = f"**{s['name']}:**\n{s['url']}"
                else:
                    txt = f"**{s['name']}:**\n~~{s['url']}~~ URL not responding."

            return await context.send(txt)

        else:
            return await context.send("Could not find a good matching stream for that search term.")
    


    else:
        return await context.send("Did not find any streams containing that text.")

@client.command(
    name="add",
    description="Add a stream, given a url and name.",
    scope=SERVER_ID,
    options=[
        interactions.Option(
            name="url",
            description="The stream URL.",
            type=interactions.OptionType.STRING,
            required=True
        ),
        interactions.Option(
            name="title",
            description="What it should be called",
            type=interactions.OptionType.STRING,
            required=True
        )
    ]
)
async def add_command(context, url: str, title: str):
    if len(url.split()) > 1 or not any(x in url for x in ["http", "https"]):
        return await context.send("That URL doesn't look right.")

    online = await check_online(url)
    if not online:
        return await context.send("That URL had a bad respond code, are you sure it's online?")

    streams = await get_streams()
    
    async with Session() as session:
        async with session.begin():
            stream_dal = StreamDAL(session)
        
            for s in streams:
                if s.url == url:
                    await stream_dal.update_stream_name(s.id, title)
                    return await context.send("Stream was already in the database, updated the title instead.")
            else:
                s = await stream_dal.create_streamlink(title, context.author.nick, url)
                return await context.send("Stream has been added to the database.")


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



@client.event
async def on_ready():
    log.info("We have logged in!")

def run_bot():
    client.start()
