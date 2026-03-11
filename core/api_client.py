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
    def set_model(self, name: str):
        self._model = name
        return self._model

    async def _request(self, context, tools=None, stream=False):
        """send a request to the LLM and return the response object"""

        if not core.config.get("model").get("use_tools"):
            # allow switching tools off globally
            tools = None

        req = {
            "model": self._model,
            "messages": context,
            "tools": tools,
            "stream": stream,
            "temperature": core.config.get("model").get("temperature", 0.2)
        }

        if stream:
            req["stream_options"] = {"include_usage": True}

        if core.config.get("channels").get("debug"):
            core.log("debug:request", str(req))

        response = await self._AI.chat.completions.create(**req)
        if core.config.get("channels").get("debug"):
            core.log("debug:response", str(response))

        return response

    async def send(self, context: list, system_prompt=True, use_tools=True, tools=None, **kwargs):
        """send a message to the LLM. returns a string"""

        self.cancel_request = False

        # use default tools if not specified. allow overrides
        if not tools:
            tools = self.manager.tools

        try:
            return await self._recv(await self._request(context, tools=(tools if use_tools else None)))
        except Exception as e:
            core.log_error("error while sending request to AI", e)
            return None

    async def send_stream(self, context: list, use_tools=True, tools=None):
        """send a message to the LLM. is an iterable async generator"""

        self.cancel_request = False

        # use default tools if not specified. allow overrides
        if not tools:
            tools = self.manager.tools

        try:
            async for token in self._recv_stream(await self._request(context, tools=(tools if use_tools else None), stream=True)):
                yield token
        except Exception as e:
            core.log_error("error while sending request to AI", e)

    async def cancel(self):
        self.cancel_request = True
        return True

    async def _recv(self, response, use_tools=True):
        """takes a response object and extracts the message from it, handling tool calls if needed"""

        final_content = None

        try:
            # normal non-streaming mode
            response_main = response.choices[0]
        except Exception as e:
            core.log_error("error while receiving response from AI", e)
            return None

        # Extract reasoning content if available
        reasoning_content = getattr(response_main.message, "reasoning_content", None) or \
                            getattr(response_main.message, "reasoning", None) or ""

        # Log reasoning if needed
        if reasoning_content:
            core.log("debug:reasoning", reasoning_content)

        # extract message content
        # replace with reasoning if message was blank
        final_content = response_main.message.content or reasoning_content or ""

        # handle tool calls, if any
        tool_calls = None
        if use_tools and core.config.get("model").get("use_tools", False) and response_main.message.tool_calls:
            tool_calls = response_main.message.tool_calls

        result = {}

        if final_content:
            result["content"] = final_content
        if reasoning_content:
            result["reasoning"] = reasoning_content
        if tool_calls:
            result["tool_calls"] = tool_calls

        # Return content (reasoning is stored in context but not returned to caller)
        return result

    async def _recv_stream(self, response, use_tools=True):
        """takes a response object and extracts the message from it, handling tool calls if needed. streaming version"""
        final_tool_calls = []
        tool_call_buffer = {}
        tokens = []
        reasoning_tokens = []

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

                    # yield the current token in the stream
                    if streamed_token.content:
                        tokens.append(streamed_token.content)
                        yield {"type": "content", "content": streamed_token.content}

                    # Handle reasoning content streaming
                    reason_part = getattr(streamed_token, "reasoning_content", None) or \
                                  getattr(streamed_token, "reasoning", None)

                    if reason_part:
                        reasoning_tokens.append(reason_part)
                        yield {"type": "reasoning", "content": reason_part}

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
                if final_tool_calls and use_tools and core.config.get("model").get("use_tools", False):
                    yield {"type": "tool_calls", "content": final_tool_calls}

            yield {"type": "token_usage", "content": token_usage}

        except Exception as e:
            core.log_error("error while receiving response from AI", e)
