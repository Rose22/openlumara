import core
import core.commands
import os
import sys
import time
import json
import asyncio

class Channel:
    """Base class for channels"""

    def __init__(self, manager):
        self.manager = manager
        self.name = core.modules.get_name(self) # shorthand alias
        self.commands = core.commands.Commands(self)
        self._last_cmd_was_temporary = False
        self.context = core.context.Context(self) # each channel has its own context window

        self.tc_manager = core.toolcalls.ToolcallManager(self)

        # load channel config
        self.config = core.config.ConfigManager(core.config.config, ["channels", "settings", self.name])

    async def _set_as_active_channel(self):
        self.manager.channel = self

        # give all modules a way to access this channel
        for module_name, module in self.manager.modules.items():
            module.channel = self

    def _get_disconnection_message(self):
        status = self.manager.get_api_status()
        error = status.get("error", "Unknown error")

        message_parts = ["Not connected to API."]

        if error:
            message_parts.append(f"Error: {error}")

        if not status.get("url_configured"):
            message_parts.append("Please configure your API URL in config/config.yml")
        elif not status.get("key_configured"):
            message_parts.append("Please configure your API key in config/config.yml")
        else:
            message_parts.append("Use /connect to retry connection, or check your settings.")

        return "\n".join(message_parts)

    def _extract_content(self, message_dict):
        """helper method that makes sure we always get the text content as a string from the messages array, even if it's multimodal"""
        content = message_dict.get("content")

        if isinstance(content, str):
            return content
        elif isinstance(content, list):
            # it's multimodal
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    return item.get("text")

        # fallback
        return ""

    async def get_token_usage(self):
        if not self.token_usage:
            # fall back to manual counting
            return self.context.get_token_usage()

        return self.token_usage

    async def send(self, message: dict):
        """sends a message to the AI from within the current channel"""

        # as soon as user sends a message in this channel, set current channel (tracked in the manager) to this one
        await self._set_as_active_channel()

        # process any /commands
        cmd_response = None
        if message.get("role", "user") == "user":
            try:
                cmd_response = await self.commands.process_input(message)
            except Exception as e:
                core.log_error("error while executing command", e)

            if cmd_response:
                return {"role": "assistant", "content": cmd_response}
            else:
                return {"role": "assistant", "content": "BLANK"}

        # if not a command, send the message to the AI and return it's response

        # attempt auto-reconnect once
        if not self.manager.API.connected:
            reconnected = await self.manager.API.connect()
            if not reconnected:
                return {"role": "assistant", "content": self._get_disconnection_message()}

        # add sent message to context
        await self.context.chat.add(message)

        # run module event hooks
        for module_name, module in self.manager.modules.items():
            if hasattr(module, "on_user_message"):
                try:
                    if asyncio.iscoroutinefunction(module.on_user_message):
                        await module.on_user_message(message.get("content", ""))
                    else:
                        module.on_user_message(message.get("content", ""))
                except Exception as e:
                    core.log(module.name, f"could not run user message hook: {e}")

        # then get the full context window
        context = await self.context.get(system_prompt=True, end_prompt=True)

        # and then request the AI response and add it to context
        response = await self.manager.API.send(context)

        # handle any errors
        if isinstance(response, dict) and "error" in response:
            await self.context.chat.pop()  # remove the user message we just added
            error_msg = response.get("message", "Unknown error occurred")
            return {"role": "assistant", "content": f"API Error: {error_msg}\n\nUse /connect to retry."}

        tool_calls = response.get("tool_calls")
        if tool_calls:
            toolcall_text = []
            # process() does all the toolcalling, but it also returns the raw toolcall stream for our own use
            async for sub_token in self.tc_manager.process(tool_calls):
                toolcall_text.append(sub_token.get("content"))

        # if no content, try the toolcall response text first
        if not response.get("content") and tool_calls:
            response["content"] = "".join(toolcall_text)

        # otherwise fall back to reasoning content
        if not response.get("content"):
            reasoning_content = response.get("reasoning")
            response["content"] = reasoning_content

        # still no content? fuck it, lol
        if not response.get("content"):
            response["content"] = "AI returned a blank response."

        # convert any toolcalls to a dict so that JSON serialization doesnt die
        if tool_calls:
            toolcalls_converted = []

            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    tool_call = tool_call.model_dump(warnings=False)
                toolcalls_converted.append(tool_call)

            response["tool_calls"] = toolcalls_converted

        await self.context.chat.add({"role": "assistant", "content": response.get("content")})

        # run module event hooks
        for module_name, module in self.manager.modules.items():
            if hasattr(module, "on_assistant_message"):
                try:
                    if asyncio.iscoroutinefunction(module.on_assistant_message):
                        await module.on_assistant_message(response.get("content", ""))
                    else:
                        module.on_assistant_message(response.get("content", ""))
                except Exception as e:
                    core.log(module.name, f"could not run assistant message hook: {e}")
        return response

    async def send_stream(self, message: dict):
        """sends a message to the AI from within the current channel, streaming version"""

        # as soon as user sends a message in this channel, set current channel (tracked in the manager) to this one
        await self._set_as_active_channel()

        user_message = message #alias for readability

        cmd_response = None
        if message.get("role", "user") == "user":
            try:
                cmd_response = await self.commands.process_input(user_message)
            except Exception as e:
                core.log_error("error while executing command", e)

        if cmd_response:
            # insert and return the command response without sending it to the AI
            for word in cmd_response:
                yield {"type": "content", "content": word}
            return

        # attempt auto-reconnect once
        if not self.manager.API.connected:
            reconnected = await self.manager.API.connect()
            if not reconnected:
                yield {"type": "content", "content": self._get_disconnection_message()}
                return

        # add user's message to context
        await self.context.chat.add(user_message)

        # run module event hooks
        for module_name, module in self.manager.modules.items():
            if hasattr(module, "on_user_message"):
                try:
                    if asyncio.iscoroutinefunction(module.on_user_message):
                        await module.on_user_message(message.get("content", ""))
                    else:
                        module.on_user_message(message.get("content", ""))
                except Exception as e:
                    core.log(module.name, f"could not run user message hook: {e}")

        # get the new context window with the added message
        context = await self.context.get(system_prompt=True, end_prompt=True)

        final_content = []
        final_reasoning = []
        tc_response = None
        tool_calls_occurred = False

        # and stream the response to the caller of this method
        async for token in self.manager.API.send_stream(context):
            token_type = token.get("type")

            # handle any errors
            if token_type == "error":
                error_data = token.get("content", {})
                error_msg = error_data.get("message", "Unknown error")
                yield {"type": "content", "content": f"API Error: {error_msg}"}
                return

            if token_type == "content":
                # this is a normal piece of streamed text
                final_content.append(token.get("content"))
                yield token
            elif token_type == "reasoning":
                final_reasoning.append(token.get("content"))
                yield token
            elif token_type == "tool_call_delta":
                # yay toolcall arg streaming!
                yield token
            elif token_type == "tool_calls":
                yield token
                tool_calls_occurred = True

                # we add the accumulated content tokens so far to the assistant_content argument
                async for sub_token in self.tc_manager.process(
                    token.get("content"),
                    assistant_content="".join(final_content),
                    assistant_reasoning="".join(final_reasoning)
                ):
                    yield sub_token
                # tc_manager.process() will loop until the AI no longer deems tool calls necessary
            elif token_type == "tool":
                # this is a toolcall response
                yield token
            elif token_type == "token_usage":
                # this is the final token usage count, usually emitted at the end of the stream
                token_usage = token.get("content")
                if isinstance(token_usage, int):
                    self.context.chat.token_usage = token_usage

        if not tool_calls_occurred:
            assistant_message = {
                "role": "assistant",
                "content": "".join(final_content)
            }

            if final_reasoning:
                assistant_message["reasoning_content"] = "".join(final_reasoning)

            await self.context.chat.add(assistant_message)

            # run module event hooks
            for module_name, module in self.manager.modules.items():
                if hasattr(module, "on_assistant_message"):
                    try:
                        if asyncio.iscoroutinefunction(module.on_assistant_message):
                            await module.on_assistant_message(assistant_message.get("content", ""))
                        else:
                            module.on_assistant_message(assistant_message.get("content", ""))
                    except Exception as e:
                        core.log(module.name, f"could not run assistant message hook: {e}")

    async def announce(self, message: str, type=None):
        """called externally to announce things in this channel, such as a reminder sent by the AI"""
        if not type:
            type = "info"

        # insert announced message into context
        await self.context.chat.add({"role": "assistant", "content": f"[System {type}]: {message}"})

        # call the overridable method
        await self._announce(message, type=type)

    async def _announce(self, message: str, type=None):
        """override this one in subclasses"""
        raise NotImplementedError

    async def announce_all(self, message: str, type=None):
        """announces a message across all channels. useful for very important notifications!"""
        if not type:
            type = "info"

        should_insert = True
        for channel_name, channel in self.manager.channels.items():
            await channel.announce(message, type, insert_message=should_insert)

            if should_insert:
                # insert into context only once
                should_insert = False
        return

    async def ask(self, message: str):
        """sends a message in the channel and then intercepts communication for one message so that user can be asked for input without that input being sent to the LLM. useful for menus."""
        raise NotImplementedError
