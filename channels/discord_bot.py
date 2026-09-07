import core
import discord
import asyncio
import datetime
import json_repair

CHUNK_SIZE = 1800

# we have to create a special class here so that we can override methods and make methods like on_message work
class DiscordClient(discord.Client):
    def __init__(self, channel, **kwargs):
        super().__init__(**kwargs)
        self._chan = channel

    async def on_ready(self):
        # startup flow
        self._chan.log(self._chan.name, "Logged in")

        try:
            self.target_channel = await self.fetch_channel(self._chan.config.get("target_channel_id"))
        except Exception as e:
            self._chan.log(self._chan.name, f"failed to retrieve target channel: {core.detail_error(e)}")

        startup_message = self._chan.config.get("startup_message")
        if startup_message:
            await self.send_to_main(startup_message)

    async def send_to_main(self, content: str, message=None):
        if self._chan.config.get("use_replies") and message is not None:
            await message.reply(content)
        else:
            await self.target_channel.send(content)

    async def on_message(self, message):
        # dont reply to its own messages
        if message.author == self.user:
            return

        # and dont spam channels that arent the target channel
        if message.channel.id != int(self._chan.config.get("target_channel_id")):
            return

        # if mentions are required, only reply if mentioned
        if self._chan.config.get("require_mentions"):
            mentioned = False
            # go through normal mentions first
            for member in message.mentions:
                if member.id == self.user.id:
                    mentioned = True

            # then check for mention keywords
            mention_keywords = self._chan.config.get("mention_keywords")
            for keyword in mention_keywords:
                if keyword.lower() in message.content.lower():
                    mentioned = True

            if not mentioned:
                return

        # determine whether non-public commands may be ran by the user
        authorized = (message.author.id == int(self._chan.config.get("authorized_user_id")))

        content = message.content

        # remove mentions from message before sending
        content = content.strip()
        for mention in message.raw_mentions:
            content = content.replace(str(mention), "")
            content = content.replace("<@>", "")
            content = content.strip()

        is_cmd = False
        cmd_prefix, cmd, args = await self._chan.commands._extract_cmd(content)
        if cmd:
            is_cmd = content.lower().strip().startswith(cmd_prefix.lower())

        if is_cmd:
            # send the pure command to the AI
            # command authorization checks were moved to the core framework
            # so that it's much more secure
            pass
        else:
            orig_content = str(content)
            content = ""

            group_chat = self._chan.config.get("enable_group_chat")

            # check if the message is a reply
            if message.reference:
                # this gets the actual message object being replied to
                replied_message = await message.channel.fetch_message(message.reference.message_id)

                # format it like a reply
                replied_content = replied_message.content or ""
                replied_message_formatted = "> "+"\n> ".join(replied_content.split("\n"))
                content += f"in reply to:\n{replied_message_formatted}\n\n"

            # if group chat is enabled, make the AI aware of who is speaking
            if group_chat:
                # strip cmd prefix from author name for safety
                # extra layer of security on top of the fix further below in the code
                author_name = str(message.author.name).lstrip(cmd_prefix)
                content += f"{author_name} said: {orig_content}"
            else:
                content += orig_content

        if self._chan.config.get("use_message_streaming"):
            # TODO: message streaming
            pass
        else:
            async with self.target_channel.typing():
                response_obj = await self._chan.send(content, commands_authorized=authorized)
                response = response_obj.get("content")

        if len(response) < CHUNK_SIZE:
            await self.send_to_main(response, message=message)
        else:
            offset = 0
            while offset < len(response):
                chunk = response[offset:(offset+CHUNK_SIZE)]
                await self.send_to_main(chunk, message=message)
                offset += CHUNK_SIZE

# the openlumara channel that sends to/from the actual discord client
class DiscordBot(core.channel.Channel):
    """Talk to your AI over Discord"""

    dependencies = ["aiohttp", "discord.py"]

    settings =  {
        "token": {
            "description": "Your discord token. Get it in the [Discord Developer Portal](https://discord.com/developers/applications)",
            "default": None
        },
        "authorized_user_id": {
            "description": "Your personal user ID. Get it by enabling *Developer Mode* in Discord (open Settings, then go to Developer, then toggle on Developer Mode), then right clicking your name and clicking/tapping *Copy ID*",
            "default": None
        },
        "target_channel_id": {
            "description": "The channel to target for communication with your discord bot. Get this by right clicking your channel and clicking/tapping *Copy ID*",
            "default": None
        },
        "require_mentions": {
            "description": "Whether to require people to mention the bot or reply to one of its messages in order to trigger a response",
            "default": True
        },
        "mention_keywords": {
            "description": "An optional list of keywords that, when present in a user's message, should trigger the discord bot to respond to the message. As an alternative to @mentions. For example, \"hey lumara\"",
            "default": [],
            "type": "list",
            "depends": "require_mentions"
        },
        "show_reasoning": {
            "description": "Whether to show the model's internal reasoning process within sent messages. Works in both streaming mode and non-streaming mode",
            "default": False
        },
        "use_message_streaming": {
            "description": "Whether to stream messages by periodically editing them. Use this together with *show reasoning* and *stream tool calls* for an experience very similar to the WebUI!",
            "default": False
        },
        "edit_interval": {
            "description": "The rate (in seconds) at which your bot's messages will be edited in streaming mode. Recommend setting this to 1 or above to avoid being rate limited!",
            "default": 1,
            "depends": "use_message_streaming"
        },
        "stream_tool_calls": {
            "description": "Whether to stream tool call arguments as they are written by the AI. Extremely useful when using toolcalls with long content, such as when using the Coder to write code",
            "default": False,
            "depends": "use_message_streaming"
        },
        "use_replies": {
            "description": "Whether the bot should reply to your messages using discord's reply feature",
            "default": False
        },
        "enable_group_chat": {
            "description": "Will make the bot aware of who is talking to it by injecting the name of the person into messages sent to the AI",
            "default": True
        },
        "startup_message": {
            "description": "The message your bot will send when it's started up. Leave this blank to disable",
            "default": None
        },
        "shutdown_message": {
            "description": "The message your bot will send when it shuts down. Leave this blank to disable",
            "default": None
        }
    }

    async def run(self):
        # set up discord intents (ugh)
        intents = discord.Intents.default()
        intents.message_content = True

        self.bot = DiscordClient(self, intents=intents)
        await self.bot.start(self.config.get("token"))

    async def on_shutdown(self):
        shutdown_msg = self.config.get("shutdown_message")

        if shutdown_msg:
            await self.bot.send_to_main(shutdown_msg)

    async def on_push(self, message: dict):
        content = message.get("content")

        if len(content) < CHUNK_SIZE:
            await self.bot.send_to_main(content)
        else:
            offset = 0
            while offset < len(content):
                chunk = content[offset:(offset+CHUNK_SIZE)]
                await self.bot.send_to_main(chunk)
                offset += CHUNK_SIZE
