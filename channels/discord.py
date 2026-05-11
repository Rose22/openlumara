import core
import discord
import asyncio
import datetime
import json_repair

MAX_CHARS = 1900
CHUNK_SIZE = 400

class Client(discord.Client):
    def __init__(self, channel, **kwargs):
        super(Client, self).__init__(**kwargs)
        self.ai_channel = channel

    async def _stream_to_discord(self, token_stream, discord_channel):
        """streams a message to discord in steps"""
        message_obj = await discord_channel.send("processing your request...")

        message_content = []

        next_edit_time = datetime.datetime.now()
        message_content_full = []
        shown_reasoning_text = False
        char_counter = 0

        async with message_obj.channel.typing():
            async for token in token_stream:
                word = token.get("content")

                if not word:
                    # wtf
                    continue

                message_content.append(word)
                message_content_full.append(word)
                message_content_str = "".join(message_content)
                char_limit_exceeded = len(message_content_str) > MAX_CHARS

                # if tokens exceed limit, add a new message to target for the edits
                if len(message_content) >= CHUNK_SIZE:
                    core.log("discord", f"<{message_obj.guild.me.name}> {message_content_str}")
                    message_obj = await discord_channel.send("...")
                    message_content = [word]

                # edit message every few seconds
                if datetime.datetime.now() >= next_edit_time or len(message_content) >= CHUNK_SIZE:
                    try:
                        await message_obj.edit(content=message_content_str)
                        next_edit_time = datetime.datetime.now() + datetime.timedelta(seconds=1)
                    except:
                        # fuck off
                        core.log("discord", f"<{message_obj.guild.me.name}> {message_content_str}")
                        message_obj = await discord_channel.send("...")
                        await message_obj.edit(content=message_content_str)

                if len(message_content) >= CHUNK_SIZE or char_limit_exceeded:
                    message_content = [word]
                    message_obj = await discord_channel.send("...")

        if message_content:
            await message_obj.edit(content="".join(message_content))
            return "".join(message_content)
        else:
            return "..come again?"

    async def on_ready(self):
        core.log("discord", "logged in.")
        if self.ai_channel.config.get("announce_startup"):
            await self.ai_channel.announce("i'm back up!", type="status")

    async def on_message(self, message):
        if message.author == self.user:
            return

        self._channel = message.channel

        if message.content:
            # only reply if mentioned
            mentioned = False
            for member in message.mentions:
                if member.id == self.user.id:
                    mentioned = True

            # or if we dont want to require mentions
            if not self.ai_channel.config.get("require_mentions"):
                mentioned = True

            if mentioned:
                core.log("discord", f"<{message.author.name}> {message.clean_content}")

                async with message.channel.typing():
                    try:
                        content = message.content.strip()
                        # remove mentions from message before sending
                        for mention in message.raw_mentions:
                           content = content.replace(str(mention), "")
                           content = content.replace("<@>", "")
                           content = content.strip()

                        cmd_prefix = core.config.get("core").get("cmd_prefix", "/")
                        is_cmd = content.lower().startswith(cmd_prefix.lower())

                        if is_cmd:
                            # only allow authorised user to use commands
                            authorised_id = int(self.ai_channel.config.get("authorised_user_id"))

                            if message.author.id != authorised_id:
                                return await message.channel.send("Only the bot owner is allowed to use commands!")
                        else:
                            orig_content = str(content)
                            content = ""

                            group_chat = self.ai_channel.config.get("enable_group_chat")

                            # check if the message is a reply
                            if message.reference:
                                # this gets the actual message object being replied to
                                replied_message = await message.channel.fetch_message(message.reference.message_id)

                                # format it like a reply
                                replied_message_formatted = "> "+"\n> ".join(replied_message.content.split("\n"))
                                content += f"in reply to:\n{replied_message_formatted}\n\n"

                            # if group chat is enabled, make the AI aware of who is speaking
                            if group_chat:
                                content += f"{message.author.display_name} said: {orig_content}"
                            else:
                                content += orig_content

                    except Exception as e:
                        return await message.channel.send(f"error while processing your request: {e}")

                    try:
                        if self.ai_channel.config.get("use_message_streaming"):
                            response_obj = self.ai_channel.format_stream_for_text(
                                self.ai_channel.send_stream({"role": "user", "content": content}),
                                chunk_size=CHUNK_SIZE
                            )
                            response_content = await self._stream_to_discord(response_obj, message.channel)
                        else:
                            response_obj = await self.ai_channel.send({"role": "user", "content": content})

                            if response_obj:
                                response_content = response_obj.get("content")

                                chunks = [response_content[i:i + CHUNK_SIZE] for i in range(0, len(response_content), CHUNK_SIZE)]

                                for chunk in chunks:
                                    await message.channel.send(chunk, mention_author=self.ai_channel.config.get("use_replies"))
                                    core.log("discord", f"<{message.guild.me.name}> {chunk}")
                                    await asyncio.sleep(0.5)
                    except Exception as e:
                        err_msg = core.detail_error(e) if core.debug else str(e)
                        return await message.channel.send(f"error while sending request to AI: {err_msg}")

class Discord(core.channel.Channel):
    settings =  {
        "token": "TOKEN_HERE",
        "authorised_user_id": "USER_ID_HERE",
        "require_mentions": False,
        "use_message_streaming": False,
        "show_reasoning": False,
        "stream_tool_calls": False,
        "use_replies": True,
        "enable_group_chat": False,
        "announce_startup": False,
        "announce_shutdown": False
    }

    async def on_push(self, message: dict):
        if not message:
            return None

        if message.get("role") != "assistant":
            return None

        content = message.get("content")

        # split the content into chunk sizes that discord accepts
        chunks = [content[i:i + CHUNK_SIZE] for i in range(0, len(content), CHUNK_SIZE)]

        for guild in self._client.guilds:
            for channel in guild.channels:
                if isinstance(channel, discord.TextChannel) and channel.permissions_for(guild.me).view_channel:
                    for chunk in chunks:
                        await channel.send(chunk)
                        await asyncio.sleep(0.5)

    async def run(self):
        token = core.config.config.get("channels").get("settings").get("discord").get("token")

        if not token:
            core.log("error", "discord token not set! set it in config.yaml as discord_token")
            return False

        intents = discord.Intents.default()
        intents.message_content = True
        self._client = Client(self, intents=intents)

        # discordpy really likes to throw useless exceptions. shut up already.
        discord.utils.setup_logging(level=50, root=False)

        core.log("discord", "logging in..")

        try:
            await self._client.start(token)
        except asyncio.CancelledError:
            # shut up no one cares about this stupid error
            pass
        except Exception as e:
            core.log("error", f"error connecting to discord: {e}")

    async def on_shutdown(self):
        if self.config.get("announce_shutdown"):
            await self.announce("i'm shutting down!")
        await self._client.close()
