import core
import discord
import asyncio
import datetime
import json_repair

class Client(discord.Client):
    def __init__(self, channel, **kwargs):
        super(Client, self).__init__(**kwargs)
        self.ai_channel = channel

    async def _stream_to_discord(self, token_stream, discord_channel):
        """streams a message to discord in steps"""
        message_obj = await discord_channel.send("...")

        # Buffers for the CURRENT active discord message
        current_text_buffer = []
        current_tool_buffer = []

        # Buffer for the full response text (for return value)
        full_response_text = []

        next_edit_time = datetime.datetime.now()

        # Discord limit is 2000, leave some room for formatting/newlines
        MAX_CHARS = 1900

        shown_reasoning_text = False

        async with message_obj.channel.typing():
            async for token in token_stream:
                t_type = token.get("type")
                content = token.get("content", "")

                if token.get("type") == "reasoning":
                    if not shown_reasoning_text:
                        await message_obj.edit(content="thinking..")
                        shown_reasoning_text = True
                    continue

                # Handle Tool Calls
                if t_type == "tool_calls":
                    if content:
                        if isinstance(content, list):
                            for tool in content:
                                current_tool_buffer.append(self.ai_channel.tc_manager.display_call(tool))
                        else:
                            current_tool_buffer.append(self.ai_channel.tc_manager.display_call(content))
                    continue

                if t_type != "content":
                    continue

                # Handle Content/Errors
                if content:
                    current_text_buffer.append(content)
                    full_response_text.append(content)

                # Construct the visual message for the CURRENT message
                tools_text = "\n".join(current_tool_buffer)
                text_part = "".join(current_text_buffer)

                if tools_text and text_part:
                    visual_buffer = f"{tools_text}\n\n{text_part}"
                else:
                    visual_buffer = tools_text + text_part

                # Check if we need to split
                # We split if the current buffer exceeds the character limit
                if len(visual_buffer) >= MAX_CHARS:
                    # Finalize current message
                    if visual_buffer:
                        await message_obj.edit(content=visual_buffer)

                    # Start a new message
                    message_obj = await discord_channel.send("...")

                    # CLEAR the buffers for the new message so we don't repeat text
                    current_text_buffer = []
                    current_tool_buffer = []

                    # Reset reasoning state for the new message if needed
                    shown_reasoning_text = False

                    # Update next edit time to avoid rate limits
                    next_edit_time = datetime.datetime.now() + datetime.timedelta(seconds=1)

                # Edit message periodically (throttled)
                if datetime.datetime.now() >= next_edit_time:
                    # Re-calculate visual buffer for the edit (it might be empty after a split)
                    tools_text = "\n".join(current_tool_buffer)
                    text_part = "".join(current_text_buffer)
                    if tools_text and text_part:
                        visual_buffer = f"{tools_text}\n\n{text_part}"
                    else:
                        visual_buffer = tools_text + text_part

                    if visual_buffer:
                        await message_obj.edit(content=visual_buffer)
                    next_edit_time = datetime.datetime.now() + datetime.timedelta(seconds=1)

        # Final edit for the last message
        tools_text = "\n".join(current_tool_buffer)
        text_part = "".join(current_text_buffer)
        if tools_text and text_part:
            visual_buffer = f"{tools_text}\n\n{text_part}"
        else:
            visual_buffer = tools_text + text_part

        if visual_buffer:
            await message_obj.edit(content=visual_buffer)

        return "".join(full_response_text)

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

                        # if group chat is enabled, make the AI aware of who is speaking
                        if self.ai_channel.config.get("enable_group_chat") and not content.startswith(core.config.get("cmd_prefix", "/")):
                            content = f"{message.author.display_name} said: {content}"

                        response_obj = self.ai_channel.send_stream({"role": "user", "content": content})
                    except Exception as e:
                        return await message.channel.send(f"error while sending request to AI: {e}")

                try:
                    response_content = await self._stream_to_discord(response_obj, message.channel)
                    core.log("discord", f"<{message.guild.me.name}> {response_content}")
                except Exception as e:
                    return await message.channel.send(f"error while receiving response from AI: {e} | {e.__traceback__.tb_frame.f_code.co_filename}, {e.__traceback__.tb_frame.f_code.co_name}, ln:{e.__traceback__.tb_lineno}")

class Discord(core.channel.Channel):
    settings =  {
        "token": "TOKEN_HERE",
        "require_mentions": False,
        "enable_group_chat": False,
        "announce_startup": False,
        "announce_shutdown": False
    }

    async def _announce(self, msg: str, type: str = None):
        if not msg:
            return None

        for guild in self._client.guilds:
            for channel in guild.channels:
                if isinstance(channel, discord.TextChannel) and channel.permissions_for(guild.me).view_channel:
                    await channel.send(msg)

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
