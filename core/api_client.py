import core
import openai
import asyncio
import json
import inspect

class APIClient():
    """
    wrapper around the openAI API to make sending/receiving messages easier to work with
    """
    def __init__(self, manager):
        # store a reference to the manager
        self.manager = manager

        self.connected = False
        self._AI = None # replaced later using .connect()

        self._model = None
        self._messages = []

        self.cancel_request = False

        self._connection_error = None
        self._last_connection_attempt = None
        self._connection_attempts = 0

    async def connect(self):
        if self.connected:
            # dont unnecessarily connect
            return True

        self._model = core.config.get("model", {}).get("name")
        self._connection_attempts += 1

        api_config = core.config.get("api", {})

        # initialize connection to the API
        httpx_client = None
        try:
            if self.manager.args.insecure_tls:
                # Allow opting out of TLS validation for self-signed certs or hostname mismatches.
                import httpx
                httpx_client = httpx.AsyncClient(verify=False)
                core.log("API", "WARNING: TLS certificate and hostname verification are disabled")

            self._AI = openai.AsyncOpenAI(
                base_url=api_config.get("url"),
                api_key=api_config.get("key"),
                http_client=httpx_client
            )
            await self._AI.models.list()
        except openai.AuthenticationError as e:
            if self.manager.args.insecure_tls and httpx_client:
                await httpx_client.aclose()

            self._connection_error = "Invalid API key. Please check your configuration."
            core.log("API", f"Authentication failed: {e}")
            return False
        except openai.APIConnectionError as e:
            if self.manager.args.insecure_tls and httpx_client:
                await httpx_client.aclose()

            self._connection_error = f"Could not reach API server at {api_config.get('url')}"
            core.log("API", f"Connection failed: {e}")
            return False
        except Exception as e:
            if self.manager.args.insecure_tls and httpx_client:
                await httpx_client.aclose()

            self._connection_error = f"Connection error: {str(e)}"
            return False

        self.connected = True
        self._connection_error = None
        self._connection_attempts = 0
        core.log("API", "Successfully connected to AI")
        return True

    def get_connection_status(self):
        api_config = core.config.get("api", {})
        model_config = core.config.get("model", {})

        return {
            "connected": self.connected,
            "error": self._connection_error,
            "model": self._model,
            "attempts": self._connection_attempts,
            "url_configured": bool(api_config.get("url")),
            "key_configured": bool(api_config.get("key")),
            "model_configured": bool(model_config.get("name")),
        }

    async def disconnect(self):
        """disconnect from the API"""
        self.connected = False
        self._AI = None
        core.log("API", "Disconnected from API")
        return True

    async def reconnect(self):
        """disconnect and reconnect to the API"""
        await self.disconnect()
        return await self.connect()

    def get_model(self):
        return self._model

    def set_model(self, name: str):
        self._model = name
        return self._model

    def get_last_error(self):
        """returns the last connection error message"""
        return self._connection_error

    async def _request(self, context, tools=None, stream=False):
        """send a request to the LLM and return the response object"""

        if not self.connected:
            # attempt to connect
            connected = await self.connect()
            if not connected:
                return {"error": "not_connected", "message": self._connection_error}

        if not core.config.get("model", {}).get("use_tools"):
            # allow switching tools off globally
            tools = None

        req = {
            "model": self._model,
            "messages": context,
            "tools": tools,
            "stream": stream,
            "temperature": core.config.get("model", {}).get("temperature", 0.2),
            "max_completion_tokens": core.config.get("api", {}).get("max_output_tokens", 8192)
        }

        if stream:
            # request token usage from the API
            req["stream_options"] = {"include_usage": True}

        if core.debug:
            core.log("debug:request", str(req))

        try:
            response = await self._AI.chat.completions.create(**req)
        except openai.AuthenticationError as e:
            core.log_error("Authentication error - disconnecting", e)
            self.connected = False
            self._connection_error = "Authentication failed. Please check your API key."
            return {"error": "auth_failed", "message": str(e)}
        except openai.APIConnectionError as e:
            core.log_error("Connection error - disconnecting", e)
            self.connected = False
            self._connection_error = "Lost connection to API server."
            return {"error": "connection_lost", "message": str(e)}
        except openai.RateLimitError as e:
            core.log_error("Rate limit exceeded", e)
            return {"error": "rate_limit", "message": "Rate limit exceeded. Please wait and try again."}
        except openai.APIStatusError as e:
            core.log_error("API status error", e)
            return {"error": "api_error", "message": f"API error: {e.message}"}
        except Exception as e:
            core.log_error("error while sending request to AI", e)
            self.connected = False
            return {"error": "unknown", "message": str(e)}

        if core.debug:
            core.log("debug:response", str(response))

        return response

    async def send(self, context: list, system_prompt=True, use_tools=True, tools=None, **kwargs):
        """send a message to the LLM. returns a string or error dict"""

        self.cancel_request = False

        # use default tools if not specified. allow overrides
        if not tools:
            tools = self.manager.tools

        response = await self._request(context, tools=(tools if use_tools else None))

        # return errors if applicable
        if isinstance(response, dict) and "error" in response:
            return response

        try:
            result = await self._recv(response)
            return result
        except Exception as e:
            core.log_error("error while processing response from AI", e)
            return {"error": "processing_failed", "message": str(e)}

    async def send_stream(self, context: list, use_tools=True, tools=None):
        """send a message to the LLM. is an iterable async generator"""

        self.cancel_request = False

        # use default tools if not specified. allow overrides
        if not tools:
            tools = self.manager.tools

        response = await self._request(context, tools=(tools if use_tools else None), stream=True)

        # return errors if applicable
        if isinstance(response, dict) and "error" in response:
            yield {"type": "error", "content": response}
            return

        try:
            async for token in self._recv_stream(response):
                if self.cancel_request:
                    # cancel the entire stream
                    break

                # let the channel calling send_stream() handle token processing
                yield token
        except Exception as e:
            core.log_error("error while sending request to AI", e)
            yield {"type": "error", "content": {"error": "stream_failed", "message": str(e)}}

    async def cancel(self):
        """cancel a request that's been sent to the AI"""
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
            return {"error": "invalid_response", "message": str(e)}

        reasoning_content = getattr(response_main.message, "reasoning_content", None) or \
                            getattr(response_main.message, "reasoning", None) or ""

        if reasoning_content and core.debug:
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

        return result

    async def _recv_stream(self, response, use_tools=True):
        """Takes a response object and extracts the message from it, handling tool calls if needed. Streaming version."""
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
                    if hasattr(response, "close"):
                        # support closing
                        await response.close()
                    return

                if chunk.choices:
                    streamed_token = chunk.choices[0].delta

                    # yield the current token in the stream
                    if streamed_token.content:
                        tokens.append(streamed_token.content)
                        yield {"type": "content", "content": streamed_token.content}

                    # handle reasoning content streaming
                    reason_part = getattr(streamed_token, "reasoning_content", None) or \
                                getattr(streamed_token, "reasoning", None)

                    if reason_part:
                        reasoning_tokens.append(reason_part)
                        yield {"type": "reasoning", "content": reason_part}

                    # extract tool calls, if any
                    if streamed_token.tool_calls and use_tools:
                        for tool_call in streamed_token.tool_calls:
                            index = tool_call.index

                            if index not in tool_call_buffer:
                                tool_call_buffer[index] = tool_call
                                # ensure arguments is always a string
                                if tool_call_buffer[index].function.arguments is None:
                                    tool_call_buffer[index].function.arguments = ""
                            else:
                                # the documentation for this was awful, so i had to use AI to figure it out
                                # welcome to the reason i was forced to introduce AI slop to the core framework
                                # (dont worry, i removed it by now)
                                # thanks openAI for ruining your documentation of chat completion requests in favor of your stupid Responses API

                                # it seems these properties will only show up in one chunk,
                                # and the rest of the stream won't have them anymore..
                                # so the AI (GLM-5) decided we should set these if they show up
                                # and then just assume it won't happen again
                                # i guess if it does, it just overwrites it..
                                if tool_call.id:
                                    tool_call_buffer[index].id = tool_call.id
                                if tool_call.function.name:
                                    tool_call_buffer[index].function.name = tool_call.function.name

                                # function arguments seem to be the part that actually gets streamed
                                # and which we must accumulate to get the full toolcall
                                if tool_call.function.arguments:
                                    tool_call_buffer[index].function.arguments += tool_call.function.arguments

                # if response has usage data, save it so we can use it to show to the user and to trim context
                if hasattr(chunk, 'usage') and chunk.usage is not None:
                    token_usage = chunk.usage.prompt_tokens

            if use_tools:
                for index in sorted(tool_call_buffer.keys()):
                    # filter out blank tool calls (rare model glitch)
                    tool_call = tool_call_buffer[index]
                    if not tool_call.function.name:
                        continue

                    final_tool_calls.append(tool_call)

                if final_tool_calls and core.config.get("model").get("use_tools", False):
                    # yield the full toolcall object as a single token to be interpreted by the function that is iterating through _recv_stream()
                    yield {"type": "tool_calls", "content": final_tool_calls}

            # yield token usage as a seperate token
            yield {"type": "token_usage", "content": token_usage}

        except Exception as e:
            core.log_error("error while receiving response from AI", e)

    async def list_models(self):
        if not self.connected:
            return []

        try:
            # get alphabetically sorted model list
            models = await self._AI.models.list()
            models_list = [model.id for model in models.data]
            models_list.sort()

        except Exception as e:
            core.log_error("error while retrieving model list", e)
            return []

        return models_list
