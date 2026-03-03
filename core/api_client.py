import core
import openai
import asyncio
import json
import inspect

class APIClient():
    """
    wrapper around the openAI API to make sending/receiving messages easier to work with
    """
    def __init__(self, manager, model: str, *args, **kwargs):
        # store a reference to the manager
        self.manager = manager

        # initialize connection to the API
        self._AI = openai.OpenAI(*args, **kwargs)

        self._model = model
        self._turns = []

        self.cancel_request = False

    async def insert_turn(self, role: str, content: str):
        """inserts a turn (message with role and content) into context, trimming when needed"""

        await self.trim_turns()
        return self._turns.append({"role": role, "content": content})

    async def trim_turns(self, max_turns: int = None, max_tokens: int = None):
        """trims context to keep token consumption low"""

        if not max_turns:
            max_turns = core.config.get("max_turns", 20)
        if not max_tokens:
            # TODO: find a way to get max tokens. also count tokens instead of words
            max_tokens = core.config.get("max_input_tokens", 16384)

        while len(self._turns) > max_turns or len(str(self._turns)) > max_tokens:
            self._turns.pop(0)
        if len(str(self._turns)) > max_tokens and self.manager.channel:
                await self.manager.channel.announce("input was too large! context size trimmed.", "error")
        return len(self._turns) <= max_turns

    def _request(self, context, debug=False, **kwargs):
        """send a request to the LLM and return the response object"""

        req = {
            "model": self._model,
            "messages": context,
            "tools": kwargs.get("tools", None),
            "stream": kwargs.get("stream", False)
        }

        if debug:
            core.log("debug:request", str(req))
        response = self._AI.chat.completions.create(**req)
        if debug:
            core.log("debug:response", str(response))

        #core.log("request", f"CONTEXT\n{context}\n\nKWARGS\n{kwargs}")

        return response

    async def build_context(self, system_prompt=True):
        # context = system prompt + turn history
        context = []

        # always insert system prompt at start of context
        if system_prompt:
            context = context+[{"role": "system", "content": await self.manager.get_system_prompt()}]

        # insert turn history
        context = context+self._turns

        return context

    async def get_context_size(self):
        turn_history = await self.build_context(system_prompt=False)
        sysprompt = await self.manager.get_system_prompt()
        turn_hist_size_chars = len(str(turn_history))
        turn_hist_size_words = len(str(turn_history).split())
        sysprompt_size_chars = len(str(sysprompt))
        sysprompt_size_words = len(str(sysprompt).split())

        combined_size_chars = turn_hist_size_chars+sysprompt_size_chars
        combined_size_words = turn_hist_size_words+sysprompt_size_words

        return {
            "system prompt size": f"{sysprompt_size_chars} characters | {sysprompt_size_words} words",
            "turn history size": f"{turn_hist_size_chars} characters | {sysprompt_size_words} words",
            "total size": f"{combined_size_chars} characters | {combined_size_words} words"
        }

    async def send(self, role: str, content: str, system_prompt=True, channel=None, use_context=None, use_tools=True, tools=None, add_turn=True, debug=False, **kwargs):
        """send a message to the LLM. returns a string"""

        self.cancel_request = False

        if channel:
            self.manager.channel = channel

        if use_context == None and use_context != False:
            use_context = core.config.get("context_window", True)

        context = []
        if use_context:
            if add_turn:
                await self.insert_turn(role, content)
            context = await self.build_context(system_prompt=system_prompt)
        else:
            context = [{"role": role, "content": content}]

        # use default tools if not specified. allow overrides
        if not tools:
            tools = self.manager.tools

        try:
            return await self._recv(self._request(context, tools=(tools if use_tools else None), system_prompt=system_prompt, use_context=use_context, use_tools=use_tools, add_turn=add_turn, debug=debug, **kwargs))
        except Exception as e:
            core.log_error("error while sending request to AI", e)
            if self.manager.channel:
                await self.manager.channel.announce(f"error while sending request to AI: {e}", "error")
            return None

    async def send_stream(self, role: str, content: str, system_prompt=True, channel=None, use_context=None, use_tools=True, tools=None, add_turn=True, debug=False, **kwargs):
        """send a message to the LLM. is an iterable async generator"""

        self.cancel_request = False

        if channel:
            self.manager.channel = channel

        if use_context == None and use_context != False:
            use_context = core.config.get("context_window", True)

        context = []
        if use_context:
            if add_turn:
                await self.insert_turn(role, content)
            context = await self.build_context(system_prompt=system_prompt)
        else:
            context = [{"role": role, "content": content}]

        # use default tools if not specified. allow overrides
        if not tools:
            tools = self.manager.tools
            
        try:
            async for token in self._recv_stream(self._request(context, tools=(tools if use_tools else None), stream=True, debug=debug, **kwargs), **kwargs, debug=debug):
                yield token
        except Exception as e:
            core.log_error("error while sending request to AI", e)
            if self.manager.channel:
                await self.manager.channel.announce(f"error while sending request to AI: {e}", "error")

    async def _recv(self, response, debug=False, **kwargs):
        """takes a response object and extracts the message from it, handling tool calls if needed"""

        final_content = None

        try:
            # normal non-streaming mode
            response_main = response.choices[0]
        except Exception as e:
            core.log_error("error while receiving response from AI", e)
            if self.manager.channel:
                await self.manager.channel.announce(f"error while receiving response from AI: {e}", "error")
            return None

        # extract message content
        final_content = response_main.message.content or ""

        # handle tool calls, if any
        if response_main.message.tool_calls:
            tool_results = await self.manager.handle_tool_calls(response_main.message.tool_calls)
            if tool_results:
                final_content += str(tool_results)

        # add it to context
        if kwargs.get("add_turn"):
            await self.insert_turn("assistant", final_content)

        return final_content

    async def _recv_stream(self, response, use_tools=True, add_turn=True, debug=False, **kwargs):
        """takes a response object and extracts the message from it, handling tool calls if needed. streaming version"""
        final_tool_calls = []
        tool_call_buffer = {}
        tokens = []

        if not response:
            return

        try:
            for chunk in response:
                if self.cancel_request:
                    # allow cancelling the stream
                    if hasattr(response, "close"):
                        response.close()
                    return

                streamed_token = chunk.choices[0].delta
                if debug:
                    core.log("debug:stream_chunk", chunk.choices[0].delta)

                # yield the current token in the stream
                if streamed_token.content:
                    tokens.append(streamed_token.content)
                    yield streamed_token.content

                # extract tool calls, if any
                if streamed_token.tool_calls and use_tools:
                    # take the streamed tool call bits and mesh them together into a completed tool call array
                    for tool_call in streamed_token.tool_calls:
                        index = tool_call.index

                        if index not in tool_call_buffer:
                            tool_call_buffer[index] = tool_call

                        tool_call_buffer[index].function.arguments += tool_call.function.arguments

            if use_tools:
                for index, tool_call in tool_call_buffer.items():
                    final_tool_calls.append(tool_call)

                # handle tool calls, if any
                if final_tool_calls:
                    try:
                        tokens.append("\n")
                        toolcall_results = await self.manager.handle_tool_calls(final_tool_calls)
                        if toolcall_results:
                            for word in toolcall_results:
                                tokens.append(word)
                                yield word
                    except Exception as e:
                        core.log_error(f"error while handling tool calls", e)

            # add it to context
            if add_turn:
                final_content = "".join(tokens)
                await self.insert_turn("assistant", final_content)
        except Exception as e:
            core.log_error("error while receiving response from AI", e)
            if self.manager.channel:
                await self.manager.channel.announce(f"error while receiving response from AI: {e}", "error")

    async def cancel(self):
        self.cancel_request = True
        return True
