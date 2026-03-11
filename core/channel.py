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

    async def send(self, message: dict):
        """sends a message to the AI from within the current channel"""

        # as soon as user sends a message in this channel, set current channel (tracked in the manager) to this one
        await self._set_as_active_channel()

        cmd_response = None
        if message.get("role", "user") == "user":
            cmd_response = await self.commands.process_input(message)

        if cmd_response:
            # set temporary flag on temporary commands so that they disappear upon the next user message
            use_temporary = True if message.get("content") in self.commands.TEMPORARY else False

            # insert /command into context so that it gets properly tracked and displayed
            await self.context.chat.add({"role": "user", "content": message.get("content")}, temporary=use_temporary)

            # insert and return the command response without sending it to the AI
            await self.context.chat.add({"role": "assistant", "content": f"[Command Output]: {''.join(cmd_response)}"},  temporary=use_temporary)
            return cmd_response
        else:
            # if not a command, send the message to the AI and return it's response

            # add sent message to context
            await self.context.chat.add(message)

            context = await self.context.get(system_prompt=True)

            # then request AI response and add it to context
            response = await self.manager.API.send(context)
            await self.context.chat.add({"role": "assistant", "content": response})
            return response

    async def send_stream(self, message: dict):
        """sends a message to the AI from within the current channel, streaming version"""

        # as soon as user sends a message in this channel, set current channel (tracked in the manager) to this one
        await self._set_as_active_channel()

        cmd = None
        if message.get("role", "user") == "user":
            cmd = await self.commands.process_input(message)

        if cmd:
            # set temporary flag on temporary commands so that they disappear upon the next user message
            use_temporary = True if cmd in self.commands.TEMPORARY else False

            # insert /command into context so that it gets properly tracked and displayed
            await self.context.chat.add({"role": "user", "content": message.get("content")}, temporary=use_temporary)

            # insert and return the command response without sending it to the AI
            cmd_response = []
            for word in cmd:
                cmd_response.append(word)
                token_data = {"type": "content", "content": word}
                yield token_data
            await self.context.chat.add({"role": "assistant", "content": f"[Command Output]: {''.join(cmd_response)}"},  temporary=use_temporary)
            return
        else:
            # add to context
            await self.context.chat.add(message)

            # and stream the response to the caller of this method
            context = await self.context.get(system_prompt=True)
            final_content = []
            final_reasoning = []
            tc_response = None
            tool_calls_occurred = False

            async for token in self.manager.API.send_stream(context):
                token_type = token.get("type")
                if token_type == "content":
                    # this is a normal piece of streamed text
                    final_content.append(token.get("content"))
                    yield token
                elif token_type == "reasoning":
                    final_reasoning.append(token.get("content"))
                    yield token
                elif token_type == "tool_calls":
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
