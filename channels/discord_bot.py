import core
import discord
import asyncio
import time
import datetime
import json_repair

CHUNK_SIZE = 1000

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
            return await message.reply(content)
        else:
            return await self.target_channel.send(content)

    def _make_progress_bar(self, percentage, size=12):
        filled = int(size * percentage / 100)
        if filled <= 0:
            bar = "░" * size
        elif filled >= size:
            bar = "█" * size
        else:
            bar = "█" * (filled - 1) + "▓" + "░" * (size - filled)
        return f"`{bar}` {percentage:.0f}%"

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

        if self._chan.config.get("use_streaming"):
            edit_interval = float(self._chan.config.get("edit_interval"))

            async with self.target_channel.typing():
                # send a message that can be edited
                msg = await self.send_to_main("processing your request..")

                # stream through tokens so we can get the current state including prompt processing,
                # but only actually stream content tokens to discord if it's set in config
                response_content = ""
                chunk_content = ""
                reasoning_content_full = ""
                reasoning_content = ""

                should_stream_text = self._chan.config.get("stream_text")

                # we're using a timer to edit on an interval to avoid hitting rate limits
                timer = time.time()
                async for token in self._chan.send_stream(content, commands_authorized=authorized):
                    try:
                        token_type = token.get("type")
                        token_content = token.get("content")

                        if token_type in ["user_message", "token_usage"]:
                            continue

                        if token_type == "prompt_progress":
                            # show a fancy progress bar

                            total = token_content.get("total")
                            processed = token_content.get("processed")

                            percentage = 0
                            if total:
                                percentage = (processed / total) * 100
                            msg = await msg.edit(content=self._make_progress_bar(percentage))

                            continue

                        if not should_stream_text:
                            # just accumulate
                            if token_type == "reasoning":
                                reasoning_content += token_content

                                if msg.content != "thinking..":
                                    msg = await msg.edit(content="thinking..")
                            if token_type == "content":
                                if msg.content != "writing response..":
                                    msg = await msg.edit(content="writing response..")

                                response_content += token_content

                            continue

                        # edit-streaming logic
                        if token_type == "reasoning":
                            reasoning_content_full += token_content

                            # stream only part of the reasoning
                            reasoning_snippet = reasoning_content_full[-450:]
                            reasoning_snippet = "\n".join([f"> {txt}" for txt in reasoning_snippet.split("\n")])

                            reasoning_content = "## thinking..\n"+reasoning_snippet
                        elif token_type == "content":
                            if reasoning_content:
                                # erase it from display
                                reasoning_content = None

                            chunk_content += token_content
                            response_content += token_content

                            # if response content length exceeds chunk size, start a new chunk message
                            if len(chunk_content) >= CHUNK_SIZE:
                                # finalize current message
                                msg = await msg.edit(content=chunk_content)

                                msg = await self.send_to_main("...")
                                chunk_content = ""

                        # this checks if the timer has elapsed
                        if (time.time() - timer) >= edit_interval:
                            if reasoning_content:
                                if self._chan.config.get("show_reasoning"):
                                    msg = await msg.edit(content=reasoning_content)
                                elif msg.content != "thinking..":
                                    msg = await msg.edit(content="thinking..")
                            else:
                                msg = await msg.edit(content=chunk_content)

                            timer = time.time()
                    except Exception as e:
                        self._chan.log(self._chan.name, f"error: {core.detail_error(e)}")

                response = response_content

                if should_stream_text:
                    # do a final edit at the end
                    msg = await msg.edit(content=chunk_content)
                else:
                    # apply the same logic as non-streaming mode
                    if len(response) < CHUNK_SIZE:
                        msg = await msg.edit(content=response)
                    else:
                        offset = 0
                        while offset < len(response):
                            chunk = response[offset:(offset+CHUNK_SIZE)]
                            if offset == 0:
                                msg = await msg.edit(content=chunk)
                            else:
                                await self.send_to_main(chunk, message=message)

                            offset += CHUNK_SIZE
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
            "description": "Whether to show the model's internal reasoning process within sent messages",
            "default": False
        },
        "use_streaming": {
            "description": "Whether to use token streaming to do things like display a thinking indicator, show prompt processing progress, and so on.. turn this off if you want the bot to strictly only send messages without ever editing them. Note that this does NOT enable text generation streaming",
            "default": True
        },
        "stream_text": {
            "description": "Whether to stream text live as it is generated. If this is off, it will instead accumulate the content until it is ready, then post the finished content",
            "default": False
        },
        "edit_interval": {
            "description": "The rate (in seconds) at which your bot's messages will be edited in streaming mode. Recommend setting this to 1 or above to avoid being rate limited!",
            "default": 1,
            "depends": "use_streaming"
        },
        "stream_tool_calls": {
            "description": "Whether to stream tool call arguments as they are written by the AI. Extremely useful when using toolcalls with long content, such as when using the Coder to write code",
            "default": False,
            "depends": "use_streaming"
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
