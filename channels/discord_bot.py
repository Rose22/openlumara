import core
import discord
import asyncio
import datetime
import json_repair

class Client(discord.Client):
    def __init__(self, channel, **kwargs):
        super(Client, self).__init__(**kwargs)
        self.ai_channel = channel

    def _format_tool_call(self, tool_data):
        """
        Parses raw tool call data into a friendly string.
        Example: 🔧 scheduler_add_job(action="Remind user...", seconds=5)
        """
        try:
            # Handle OpenAI style pydantic objects
            if hasattr(tool_data, 'function'):
                func_name = getattr(tool_data.function, 'name', 'unknown')
                raw_args = getattr(tool_data.function, 'arguments', '{}')
            # Handle dictionary style
            elif isinstance(tool_data, dict) and 'function' in tool_data:
                func_name = tool_data['function'].get('name', 'unknown')
                raw_args = tool_data['function'].get('arguments', '{}')
            else:
                return "🔧 Calling tool..."

            # Parse arguments safely using json_repair
            if isinstance(raw_args, str):
                try:
                    args_dict = json_repair.loads(raw_args)
                except Exception:
                    args_dict = {}
            elif isinstance(raw_args, dict):
                args_dict = raw_args
            else:
                args_dict = {}

            # Build arg string: key="value", key2="value2"
            arg_strs = []
            for k, v in args_dict.items():
                v_str = str(v)
                # Truncate long values
                if len(v_str) > 30:
                    v_str = v_str[:30] + ".."
                # Escape quotes for display
                v_str = v_str.replace('"', "'")
                arg_strs.append(f'{k}="{v_str}"')

            args_display = ", ".join(arg_strs)
            return f"🔧 {func_name}({args_display})"

        except Exception as e:
            core.log("discord", f"Error formatting tool call: {e}")
            return "🔧 Calling tool..."

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
                                current_tool_buffer.append(self._format_tool_call(tool))
                        else:
                            current_tool_buffer.append(self._format_tool_call(content))
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
        "token": "TOKEN_HERE"
    }

    def __init__(self, manager):
        super().__init__(manager)

        intents = discord.Intents.default()
        intents.message_content = True
        self._client = Client(self, intents=intents)

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

        core.log("discord", "logging in..")

        try:
            await self._client.start(token)
        except Exception as e:
            core.log("error", f"error connecting to discord: {e}")
