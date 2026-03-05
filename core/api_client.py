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
        self._AI = openai.AsyncOpenAI(*args, **kwargs)

        self._model = model
        self._messages = []

        self.cancel_request = False

    def get_model(self):
        return self._model

    def _count_tokens_local(self, messages: list) -> int:
        """
        Counts tokens locally using tiktoken. 
        Used as a fallback if the API doesn't return usage data.
        """
        import tiktoken
        try:
            # Try to get the specific tokenizer for the model (e.g. gpt-4)
            encoding = tiktoken.encoding_for_model(self._model)
        except KeyError:
            # Fallback to a standard encoding for unknown/custom models
            encoding = tiktoken.get_encoding("cl100k_base")

        num_tokens = 0
        for message in messages:
            # OpenAI message format overhead is ~4 tokens per message
            # <im_start>{role/name}\n{content}<im_end>\n
            num_tokens += 4
            for key, value in message.items():
                if value:
                    num_tokens += len(encoding.encode(str(value)))

        # Add 2-3 tokens for the assistant priming at the end
        num_tokens += 2
        return num_tokens

    def get_messages(self):
        return self._messages
    def set_messages(self, messages: list):
        self._messages = messages

    async def insert_message(self, role: str, content: str, num_tokens=None):
        """inserts a message (dict with role and content) into context, trimming when needed"""

        await self.trim_messages(num_tokens=num_tokens)
        return self._messages.append({"role": role, "content": content})

    async def trim_messages(self, max_messages: int = None, max_tokens: int = None, num_tokens: int = None):
        """trims context to keep token consumption low"""

        if not max_messages:
            max_messages = core.config.get("max_messages", 20)
        if not max_tokens:
            # TODO: find a way to get max tokens. also count tokens instead of words
            max_tokens = core.config.get("max_context", 8192)

        if not num_tokens:
            # default to character length if we couldn't get the token amount
            num_tokens = len(str(self._messages))

        request_too_big = False
        context_trimmed = False
        while len(self._messages) > max_messages or num_tokens > max_tokens:
            context_trimmed = True
            if not self._messages:
                request_too_big = True
                # we've exhausted all messages. handle it later in this function
                break
            self._messages.pop(0)

        if self.manager.channel:
            if request_too_big:
                # the entire thing was too big including user's input! inform them
                await self.manager.channel.announce("Your request exceeds the max amount of tokens allowed. Please send a smaller request!", "error")
            elif context_trimmed:
                await self.manager.channel.announce("Input was too large! context size trimmed.", "error")
        return len(self._messages) <= max_messages

    async def _request(self, context, debug=False, tools=None, stream=False):
        """send a request to the LLM and return the response object"""

        req = {
            "model": self._model,
            "messages": context,
            "tools": tools,
            "stream": stream,
            "temperature": core.config.get("model_temperature", 0.2)
        }

        if stream:
            req["stream_options"] = {"include_usage": True}

        if debug:
            core.log("debug:request", str(req))

        response = await self._AI.chat.completions.create(**req)
        if debug:
            core.log("debug:response", str(response))

        #core.log("request", f"CONTEXT\n{context}\n\nKWARGS\n{kwargs}")

        return response

    async def build_context(self, system_prompt=True):
        # context = system prompt + message history
        context = []

        # always insert system prompt at start of context
        if system_prompt:
            context = context+[{"role": "system", "content": await self.manager.get_system_prompt()}]

        # insert message history
        context = context+self._messages

        if system_prompt:
            histend = await self.manager.get_end_prompt()
            # for some reason, it won't accept a 2nd system prompt. so we add it as user
            # maybe theres a better way to do this..
            context = context+[{"role": "user", "content": histend}]

        return context

    async def get_context_size(self):
        message_history = await self.build_context(system_prompt=False)
        sysprompt = await self.manager.get_system_prompt()
        histend = await self.manager.get_end_prompt()
        sysprompt_size_chars = len(str(sysprompt))
        sysprompt_size_words = len(str(sysprompt).split())
        message_hist_size_chars = len(str(message_history))
        message_hist_size_words = len(str(message_history).split())
        histend_size_chars = len(str(histend))
        histend_size_words = len(str(histend).split())

        combined_size_chars = message_hist_size_chars+sysprompt_size_chars+histend_size_chars
        combined_size_words = message_hist_size_words+sysprompt_size_words+histend_size_words

        return {
            "system prompt size": f"{sysprompt_size_chars} characters | {sysprompt_size_words} words",
            "message history size": f"{message_hist_size_chars} characters | {message_hist_size_words} words",
            "end prompt size": f"{histend_size_chars} characters | {histend_size_words} words",
            "total size": f"{combined_size_chars} characters | {combined_size_words} words"
        }

    async def send(self, role: str, content: str, system_prompt=True, channel=None, use_context=None, use_tools=True, tools=None, add_message=True, debug=False, **kwargs):
        """send a message to the LLM. returns a string"""

        self.cancel_request = False

        if channel:
            self.manager.channel = channel
            # save name of last channel used for restoring from save later
            self.manager.savedata["last_channel"] = core.module.get_name(channel)
            self.manager.savedata.save()

        if use_context is None:
            use_context = core.config.get("context_window", True)

        context = []
        if use_context:
            if add_message:
                # try to check how big (in tokens) the request content is
                # num_tokens = self._count_tokens_local({"role": role, "content": content})
                # if num_tokens > core.config.get("max_tokens", 8192):
                #     if self.manager.channel:
                #         self.manager.channel.announce("error: request was too big!", False)
                #     core.log("error", "request was too big!")
                await self.insert_message(role, content)
            context = await self.build_context(system_prompt=system_prompt)
        else:
            context = [{"role": role, "content": content}]

        # use default tools if not specified. allow overrides
        if not tools:
            tools = self.manager.tools

        try:
            return await self._recv(await self._request(context, tools=(tools if use_tools else None)), system_prompt=system_prompt, use_context=use_context, context=context, use_tools=use_tools, add_message=add_message, debug=debug, **kwargs)
        except Exception as e:
            core.log_error("error while sending request to AI", e)
            if self.manager.channel:
                await self.manager.channel.announce(f"error while sending request to AI: {e}", "error")
            return None

    async def send_stream(self, role: str, content: str, system_prompt=True, channel=None, use_context=None, use_tools=True, tools=None, add_message=True, debug=False, **kwargs):
        """send a message to the LLM. is an iterable async generator"""

        self.cancel_request = False

        if channel:
            self.manager.channel = channel
            # save name of last channel used for restoring from save later
            self.manager.savedata["last_channel"] = core.module.get_name(channel)
            self.manager.savedata.save()

        if use_context is None:
            use_context = core.config.get("context_window", True)

        context = []
        if use_context:
            if add_message:
                await self.insert_message(role, content)
            context = await self.build_context(system_prompt=system_prompt)
        else:
            context = [{"role": role, "content": content}]

        # use default tools if not specified. allow overrides
        if not tools:
            tools = self.manager.tools

        try:
            async for token in self._recv_stream(await self._request(context, tools=(tools if use_tools else None), stream=True, debug=debug, **kwargs), context=context, **kwargs, debug=debug):
                yield token
        except Exception as e:
            core.log_error("error while sending request to AI", e)
            if self.manager.channel:
                await self.manager.channel.announce(f"error while sending request to AI: {e}", "error")

    async def _recv(self, response, context=None, debug=False, **kwargs):
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
        token_usage = None
        if kwargs.get("add_message"):
            if hasattr(response, 'usage') and response.usage:
                token_usage = response.usage.prompt_tokens
            else:
                # fall back to tokenizer counting if api didn't provide a token count
                token_usage = self._count_tokens_local(context)

            await self.insert_message("assistant", final_content, num_tokens=token_usage)

        return final_content

    async def _recv_stream(self, response, use_tools=True, add_message=True, context=None, debug=False, **kwargs):
        """takes a response object and extracts the message from it, handling tool calls if needed. streaming version"""
        final_tool_calls = []
        tool_call_buffer = {}
        tokens = []

        token_usage = None

        if not response:
            return

        try:
            async for chunk in response:
                if self.cancel_request:
                    # allow cancelling the stream
                    if hasattr(response, "close"):
                        await response.close()
                    return

                if chunk.choices:
                    streamed_token = chunk.choices[0].delta
                    # if debug:
                    #     core.log("debug:stream_chunk", chunk.choices[0].delta)

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

                # if response has usage data, save it so we can use it to trim context!
                if hasattr(chunk, 'usage') and chunk.usage is not None:
                    token_usage = chunk.usage.prompt_tokens

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

            if token_usage is None:
                # fall back to tokenizer for context length counting
                token_usage = self._count_tokens_local(context)

            # add it to context
            if add_message:
                final_content = "".join(tokens)
                await self.insert_message("assistant", final_content, num_tokens=token_usage)
        except Exception as e:
            core.log_error("error while receiving response from AI", e)
            if self.manager.channel:
                await self.manager.channel.announce(f"error while receiving response from AI: {e}", "error")

    async def cancel(self):
        self.cancel_request = True
        return True
