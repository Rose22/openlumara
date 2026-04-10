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
        self.name = core.module.get_name(self)
        self.manager = manager
        self.commands = core.commands.Commands(self)
        self._last_cmd_was_temporary = False
        self.context = core.context.Context(self) # each channel has its own context window

        self.tc_manager = core.toolcalls.ToolcallManager(self)

    async def _set_as_active_channel(self):
        self.manager.channel = self

        # give all modules a way to access this channel
        for module_name, module in self.manager.modules.items():
            module.channel = self

    def _get_disconnection_message(self):
        """Generate a user-friendly disconnection message."""
        status = self.manager.get_api_status()
        error = status.get("error", "Unknown error")

        message_parts = ["Not connected to API."]

        if error:
            message_parts.append(f"Error: {error}")

        # Provide actionable guidance
        if not status.get("url_configured"):
            message_parts.append("Please configure your API URL in config/config.yml")
        elif not status.get("key_configured"):
            message_parts.append("Please configure your API key in config/config.yml")
        else:
            message_parts.append("Use /connect to retry connection, or check your settings.")

        return "\n".join(message_parts)

    async def send(self, message: dict):
        """sends a message to the AI from within the current channel"""

        # as soon as user sends a message in this channel, set current channel (tracked in the manager) to this one
        await self._set_as_active_channel()

        cmd_response = None
        if message.get("role", "user") == "user":
            cmd_response = await self.commands.process_input(message)

        if cmd_response:
            return {"role": "assistant", "content": cmd_response}
        else:
            # if not a command, send the message to the AI and return it's response

            # Check connection status
            if not self.manager.API.connected:
                # Try to reconnect automatically once
                reconnected = await self.manager.API.connect()
                if not reconnected:
                    return {"role": "assistant", "content": self._get_disconnection_message()}

            # add sent message to context
            await self.context.chat.add(message)

            context = await self.context.get(system_prompt=True, end_prompt=True)

            # Check if context generation failed (can happen if disconnected)
            if context is None:
                return {"role": "assistant", "content": self._get_disconnection_message()}

            # then request AI response and add it to context
            response = await self.manager.API.send(context)

            # Handle error responses
            if isinstance(response, dict) and "error" in response:
                await self.context.chat.pop()  # Remove the user message we just added
                error_msg = response.get("message", "Unknown error occurred")
                return {"role": "assistant", "content": f"API Error: {error_msg}\n\nUse /connect to retry."}

            tool_calls = response.get("tool_calls")
            if tool_calls:
                toolcall_text = []
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

            return response

    async def send_stream(self, message: dict):
        """sends a message to the AI from within the current channel, streaming version"""

        # as soon as user sends a message in this channel, set current channel (tracked in the manager) to this one
        await self._set_as_active_channel()

        cmd_response = None
        if message.get("role", "user") == "user":
            cmd_response = await self.commands.process_input(message)

        if cmd_response:
            # insert and return the command response without sending it to the AI
            for word in cmd_response:
                yield {"type": "content", "content": word}
        else:
            # Check connection status
            if not self.manager.API.connected:
                # Try to reconnect automatically once
                reconnected = await self.manager.API.connect()
                if not reconnected:
                    yield {"type": "content", "content": self._get_disconnection_message()}
                    return

            # add to context
            await self.context.chat.add(message)

            # and stream the response to the caller of this method
            context = await self.context.get(system_prompt=True, end_prompt=True)

            # Check if context generation failed
            if context is None:
                yield {"type": "content", "content": self._get_disconnection_message()}
                return

            final_content = []
            final_reasoning = []
            tc_response = None
            tool_calls_occurred = False

            async for token in self.manager.API.send_stream(context):
                token_type = token.get("type")

                # Handle error tokens
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
                elif token_type == "tool_calls":
                    yield token

                    tool_calls_occurred = True
                    # Pass accumulated content to be included in tool_calls message

                    async for sub_token in self.tc_manager.process(
                        token.get("content"),
                        initial_content="".join(final_content)
                    ):
                        yield sub_token
                    # tc_manager.process() will loop until the AI no longer deems tool calls necessary
                elif token_type == "usage":
                    # this is the final token usage count, also emitted at the end of the stream
                    pass

            # add AI's response to context as well
            if not tool_calls_occurred:
                new_message = {
                    "role": "assistant",
                    "content": "".join(final_content)
                }

                if final_reasoning:
                    new_message["reasoning_content"] = "".join(final_reasoning)

                await self.context.chat.add(new_message)

    async def announce(self, message: str, type=None):
        """called externally to announce things in this channel, such as a reminder sent by the AI"""
        if not type:
            type = "info"

        # insert announced message into context
        await self.context.chat.add({"role": "assistant", "content": f"[System {type}]: {message}"})

        # Subclass hook
        await self._announce(message, type=type)

    async def _announce(self, message: str, type=None):
        """override this one in subclasses"""
        raise NotImplementedError

    async def announce_all(self, message: str, type=None):
        """announces a message across all channels. useful for very important notifications!"""
        if not type:
            type = "info"

        count = 0
        for channel_name, channel in self.manager.channels.items():
            insert = True if count < 1 else False
            await channel.announce(message, type, insert_message=insert)
            count += 1
        return

    async def ask(self, message: str):
        """sends a message in the channel and then intercepts communication for one message so that user can be asked for input without that input being sent to the LLM. useful for menus."""
        pass
