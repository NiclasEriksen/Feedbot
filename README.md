# Feedbot

This is a simple bot running on Discord's "interactions" API, which allows users to add and retrieve links to streams and camera feeds, and other convenience functions.
It uses a fuzzy search algorithm to match titles, and has autocomplete listing available streams.

## Requirements

- python >= 3.9
- `discord-py-interactions`
- `aiohttp`
- `SQLAlchemy` + `aiosqlite`
- `numpy` *(for fuzzy search)*
- `youtube_dl` *(optional, for better online check)*

## Commands

These are the available commands as of writing:
|Command    |Arguments		|Function                          |
|-----------|-------------------------------|---------------|
|`/stream`|`search_string`           |Search for stream and post it in channel            |
|`/addstream`          |            |Shows a modal to enter name and url            |
|`/removestream`          |`url`|Removes the stream from the database, given an url|
|`/factcheck`          |`search_string`|Search online fact checking databases for claims|
