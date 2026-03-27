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

        message_content = []

        next_edit_time = datetime.datetime.now()
        message_content_full = []
        max_tokens_per_message = 400
        shown_reasoning_text = False
        shown_tool_use = False

        # Buffers for visual formatting
        tool_calls_display = []
        response_buffer = []

        async with message_obj.channel.typing():
            async for token in token_stream:
                t_type = token.get("type")
                content = token.get("content", "")

                if token.get("type") == "reasoning":
                    # reasoning would be very hard to show on discord lol
                    if not shown_reasoning_text:
                        await message_obj.edit(content="thinking..")
                        shown_reasoning_text = True
                    continue

                # Handle Tool Calls: Format and store
                if t_type == "tool_calls":
                    if content:
                        if isinstance(content, list):
                            for tool in content:
                                tool_calls_display.append(self._format_tool_call(tool))
                        else:
                            tool_calls_display.append(self._format_tool_call(content))
                    if not shown_tool_use:
                        shown_tool_use = True
                    continue

                # Handle Content/Errors: Store text
                if content:
                    response_buffer.append(content)

                # Construct the visual message
                tools_text = "\n".join(tool_calls_display)
                text_part = "".join(response_buffer)

                # Add spacing if we have both tools and text
                if tools_text and text_part:
                    visual_buffer = f"{tools_text}\n\n{text_part}"
                else:
                    visual_buffer = tools_text + text_part

                # if tokens exceed 200, add a new message to target for the edits
                if len(message_content) >= max_tokens_per_message:
                    message_content = []
                    message_obj = await discord_channel.send("...")

                message_content.append(content)
                message_content_full.append(content)

                # edit message every few seconds or if token limit reached
                if datetime.datetime.now() >= next_edit_time or len(message_content) >= max_tokens_per_message:
                    if visual_buffer:
                        await message_obj.edit(content=visual_buffer)
                    next_edit_time = datetime.datetime.now() + datetime.timedelta(seconds=1)

        if message_content:
            await message_obj.edit(content=visual_buffer)
            return "".join(message_content)
        else:
            return "..come again?"

    async def on_ready(self):
        core.log("discord", "logged in.")

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

                        response_obj = self.ai_channel.send_stream({"role": "user", "content": content})
                    except Exception as e:
                        return await message.channel.send(f"error while sending request to AI: {e}")

                try:
                    response_content = await self._stream_to_discord(response_obj, message.channel)
                    core.log("discord", f"<{message.guild.me.name}> {response_content}")
                except Exception as e:
                    return await message.channel.send(f"error while receiving response from AI: {e} | {e.__traceback__.tb_frame.f_code.co_filename}, {e.__traceback__.tb_frame.f_code.co_name}, ln:{e.__traceback__.tb_lineno}")

class Discord(core.channel.Channel):
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
