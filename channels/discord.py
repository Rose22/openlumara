import core
import discord
import asyncio
import datetime
import json_repair

MAX_CHARS = 1900

class Client(discord.Client):
    def __init__(self, channel, **kwargs):
        super(Client, self).__init__(**kwargs)
        self.ai_channel = channel

    async def _stream_to_discord(self, token_stream, discord_channel):
        """streams a message to discord in steps"""
        edit_interval = self.ai_channel.config.get("edit_interval", 1)
        message_obj = await discord_channel.send("processing your request...")
        edit_lock = asyncio.Lock()

        class StreamState:
            def __init__(self, initial_msg):
                self.message_obj = initial_msg
                self.full_content = ""
                self.pending_content = ""
                self.is_running = True

        state = StreamState(message_obj)

        async def periodic_editor():
            while state.is_running:
                await asyncio.sleep(edit_interval)
                async with edit_lock:
                    if state.pending_content:
                        try:
                            chunk = state.pending_content
                            state.pending_content = ""
                            state.full_content += chunk
                            await state.message_obj.edit(content=state.full_content)
                        except Exception:
                            pass

        editor_task = asyncio.create_task(periodic_editor())

        try:
            async with message_obj.channel.typing():
                async for token in token_stream:
                    if token.get("type") == "new_chunk":
                        async with edit_lock:
                            if state.pending_content:
                                state.full_content += state.pending_content
                                state.pending_content = ""
                                try:
                                    await state.message_obj.edit(content=state.full_content)
                                    self.ai_channel.log(self.ai_channel.name, state.full_content)
                                except:
                                    pass
                            
                            state.message_obj = await discord_channel.send("...")
                            state.full_content = ""
                        continue

                    word = token.get("content")
                    if not word or not isinstance(word, str):
                        continue
                    state.pending_content += word
        finally:
            state.is_running = False
            editor_task.cancel()
            try:
                await editor_task
            except asyncio.CancelledError:
                pass
            
            async with edit_lock:
                if state.pending_content:
                    state.full_content += state.pending_content
                    state.pending_content = ""
                
                if state.full_content:
                    self.ai_channel.log(self.ai_channel.name, state.full_content)
                    try:
                        await state.message_obj.edit(content=state.full_content)
                    except Exception:
                        try:
                            await discord_channel.send(state.full_content)
                        except:
                            pass

    async def on_ready(self):
        self.ai_channel.log("discord", "logged in.")
        startup_message = self.ai_channel.config.get("startup_message")
        if startup_message:
            await self.ai_channel.push(startup_message)

    async def on_message(self, message):
        if message.author == self.user:
            return

        if message.channel.id != int(self.ai_channel.config.get("target_channel_id")):
            return

        commands_authorized = False
        authorized_id = self.ai_channel.config.get("authorized_user_id")
        if authorized_id and message.author.id == int(authorized_id):
            commands_authorized = True

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
                self.ai_channel.log("discord", f"<{message.author.name}> {message.clean_content}")

                async with message.channel.typing():
                    try:
                        # remove mentions from message before sending
                        content = message.content.strip()
                        for mention in message.raw_mentions:
                            content = content.replace(str(mention), "")
                            content = content.replace("<@>", "")
                            content = content.strip()

                        is_cmd = False
                        cmd_prefix, cmd, args = await self.ai_channel.commands._extract_cmd(content)
                        if cmd:
                            is_cmd = content.lower().strip().startswith(cmd_prefix.lower())

                        if is_cmd:
                            # send the pure command to the AI
                            # command authorization checks were moved to the core framework
                            # so that it's much more secure
                            content = f"{cmd_prefix}{' '.join(cmd)}"
                        else:
                            orig_content = str(content)
                            content = ""

                            group_chat = self.ai_channel.config.get("enable_group_chat")

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
                                cmd_prefix_temp = str(core.config.get("core", "cmd_prefix", default="/"))
                                author_name = str(message.author.name).lstrip(cmd_prefix_temp)
                                del(cmd_prefix_temp)

                                content += f"{author_name} said: {orig_content}"
                            else:
                                content += orig_content

                    except Exception as e:
                        return await message.channel.send(f"error while processing your request: {e}")

                    try:
                        if self.ai_channel.config.get("use_message_streaming"):
                            response_obj = self.ai_channel.format_stream_for_text(
                                self.ai_channel.send_stream(
                                    {"role": "user", "content": content},
                                    commands_authorized=commands_authorized
                                ),
                                chunk_size=MAX_CHARS
                            )
                            await self._stream_to_discord(response_obj, message.channel)
                        else:
                            response_obj = await self.ai_channel.send({"role": "user", "content": content}, commands_authorized=commands_authorized)

                            if response_obj:
                                response_content = response_obj.get("content")

                                chunks = [response_content[i:i + MAX_CHARS] for i in range(0, len(response_content), MAX_CHARS)]

                                for chunk in chunks:
                                    await message.channel.send(chunk, mention_author=self.ai_channel.config.get("use_replies"))
                                    self.ai_channel.log("discord", f"<{message.guild.me.name}> {chunk}")
                                    await asyncio.sleep(0.5)
                    except Exception as e:
                        err_msg = core.detail_error(e) if core.debug else str(e)
                        return await message.channel.send(f"error while sending request to AI: {err_msg}")

class Discord(core.channel.Channel):
    """Talk to your AI over Discord"""

    dependencies = ["discord.py"]

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
        "use_message_streaming": {
            "description": "Whether to stream messages by periodically editing them. Use this together with *show reasoning* and *stream tool calls* for an experience very similar to the WebUI!",
            "default": False
        },
        "edit_interval": {
            "description": "The rate (in seconds) at which your bot's messages will be edited in streaming mode. Recommend setting this to 1 or above to avoid being rate limited!",
            "default": 1
        },
        "show_reasoning": {
            "description": "Whether to show the model's internal reasoning process within sent messages. Works in both streaming mode and non-streaming mode",
            "default": False
        },
        "stream_tool_calls": {
            "description": "Whether to stream tool call arguments as they are written by the AI. Extremely useful when using toolcalls with long content, such as when using the Coder to write code",
            "default": False
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

    async def on_push(self, message: dict):
        if not message:
            return None

        if message.get("role") != "assistant":
            return None

        target_channel_id = self.config.get("target_channel_id")
        if not target_channel_id:
            self.log(self.name, "Error while sending push message: No target channel ID set. Could not send message! Please configure your target channel.")
            return

        # split the content into chunk sizes that discord accepts
        content = message.get("content")
        self.log(f"{self.name} push", content)
        chunks = [content[i:i + MAX_CHARS] for i in range(0, len(content), MAX_CHARS)]

        # send into the channel if we have the permissions to
        channel = await self._client.fetch_channel(target_channel_id)
        for guild in self._client.guilds:
            if isinstance(channel, discord.TextChannel):
                if (
                    channel.permissions_for(guild.me).view_channel and
                    channel.permissions_for(guild.me).send_messages
                ):
                    for chunk in chunks:
                        await channel.send(chunk)
                        await asyncio.sleep(0.5)
                else:
                    self.log(self.name, "Error while sending push message: Discord bot does not have the required permissions to send messages into the target channel. Please give it the needed permissions!")
                    return

    async def run(self):
        token = core.config.config.get("channels").get("settings").get("discord").get("token")

        if not token:
            self.log("error", "Discord token not set! Set it up in the webui or by editing the config")
            return False

        intents = discord.Intents.default()
        intents.message_content = True
        self._client = Client(self, intents=intents)

        # discordpy really likes to throw useless exceptions. shut up already.
        discord.utils.setup_logging(level=50, root=False)

        self.log("discord", "logging in..")

        try:
            await self._client.start(token)
        except asyncio.CancelledError:
            # shut up no one cares about this stupid error
            pass
        except Exception as e:
            self.log("error", f"error connecting to discord: {e}")

    async def on_shutdown(self):
        shutdown_message = self.config.get("shutdown_message")
        if shutdown_message:
            await self.push(shutdown_message)

        await self._client.close()
