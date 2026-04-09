import core
import openai
import asyncio
import json
import inspect
import httpx

class APIClient():
    """
    wrapper around the openAI API to make sending/receiving messages easier to work with
    """
    def __init__(self, manager):
        # store a reference to the manager
        self.manager = manager

        self.connected = False
        self._AI = None # replaced later using .connect()
        self._http_client = None

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

        # validate config
        validation_result = self._validate_config()
        if not validation_result["valid"]:
            self._connection_error = validation_result["error"]
            core.log("API", f"Configuration invalid: {validation_result['error']}")
            return False

        self._model = core.config.get("model").get("name")
        self._connection_attempts += 1

        api_config = core.config.get("api")
        insecure_skip_tls_verify = api_config.get("insecure_skip_tls_verify", False)

        # initialize connection to the API
        try:
            # Allow opting out of TLS validation for self-signed certs or hostname mismatches.
            self._http_client = httpx.AsyncClient(verify=(not insecure_skip_tls_verify))
            if insecure_skip_tls_verify:
                core.log("API", "WARNING: TLS certificate and hostname verification are disabled")
            self._AI = openai.AsyncOpenAI(
                base_url=api_config.get("url"),
                api_key=api_config.get("key"),
                http_client=self._http_client
            )
            await self._AI.models.list()
        except openai.AuthenticationError as e:
            if self._http_client:
                await self._http_client.aclose()
                self._http_client = None
            self._connection_error = "Invalid API key. Please check your configuration."
            core.log("API", f"Authentication failed: {e}")
            return False
        except openai.APIConnectionError as e:
            if self._http_client:
                await self._http_client.aclose()
                self._http_client = None
            self._connection_error = f"Could not reach API server at {api_config.get('url')}"
            core.log("API", f"Connection failed: {e}")
            return False
        except Exception as e:
            if self._http_client:
                await self._http_client.aclose()
                self._http_client = None
            self._connection_error = f"Connection error: {str(e)}"
            return False

        self.connected = True
        self._connection_error = None
        self._connection_attempts = 0
        core.log("API", "Successfully connected to API")
        return True

    def _validate_config(self):
        """Validate that API configuration is present and valid."""
        result = {"valid": False, "error": None}

        api_config = core.config.get("api")
        if not api_config:
            result["error"] = "API configuration not found in config file"
            return result

        url = api_config.get("url")
        key = api_config.get("key")

        if not url:
            result["error"] = "API URL not configured. Please set 'url' in config."
            return result

        if not key:
            result["error"] = "API key not configured. Please set 'key' in config."
            return result

        model_config = core.config.get("model")
        if not model_config or not model_config.get("name"):
            result["error"] = "Model name not configured. Please set model name in config."
            return result

        result["valid"] = True
        return result

    def get_connection_status(self):
        """Returns a dictionary with connection status info for UI display."""
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
        """Properly disconnect from the API."""
        self.connected = False
        self._AI = None
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        core.log("API", "Disconnected from API")
        return True

    async def reconnect(self):
        """Disconnect and reconnect to the API."""
        await self.disconnect()
        return await self.connect()

    def get_model(self):
        return self._model

    def set_model(self, name: str):
        self._model = name
        return self._model

    def get_last_error(self):
        """Get the last connection error message."""
        return self._connection_error

    async def _request(self, context, tools=None, stream=False):
        """send a request to the LLM and return the response object"""

        if not self.connected:
            # attempt to connect
            connected = await self.connect()
            if not connected:
                return {"error": "not_connected", "message": self._connection_error}

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

        if core.config.get("channels").get("debug"):
            core.log("debug:response", str(response))

        return response

    async def send(self, context: list, system_prompt=True, use_tools=True, tools=None, **kwargs):
        """send a message to the LLM. returns a string or error dict"""

        self.cancel_request = False

        # use default tools if not specified. allow overrides
        if not tools:
            tools = self.manager.tools

        response = await self._request(context, tools=(tools if use_tools else None))

        # Check for error response
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

        # Check for error response
        if isinstance(response, dict) and "error" in response:
            yield {"type": "error", "content": response}
            return

        try:
            async for token in self._recv_stream(response):
                if self.cancel_request:
                    break

                yield token
        except Exception as e:
            core.log_error("error while sending request to AI", e)
            yield {"type": "error", "content": {"error": "stream_failed", "message": str(e)}}

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
            return {"error": "invalid_response", "message": str(e)}

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
                                # ensure arguments is a string, not None
                                if tool_call_buffer[index].function.arguments is None:
                                    tool_call_buffer[index].function.arguments = ""
                            else:
                                # Continuation chunk — merge fields into the buffer
                                # The id and function.name are typically only on the first chunk,
                                # but merge them defensively in case they appear later
                                if tool_call.id:
                                    tool_call_buffer[index].id = tool_call.id
                                if tool_call.function.name:
                                    tool_call_buffer[index].function.name = tool_call.function.name
                                # Append argument fragments
                                if tool_call.function.arguments:
                                    tool_call_buffer[index].function.arguments += tool_call.function.arguments

                # if response has usage data, save it so we can use it to trim context
                if hasattr(chunk, 'usage') and chunk.usage is not None:
                    token_usage = chunk.usage.prompt_tokens

            if use_tools:
                for index in sorted(tool_call_buffer.keys()):
                    final_tool_calls.append(tool_call_buffer[index])

                if final_tool_calls and core.config.get("model").get("use_tools", False):
                    yield {"type": "tool_calls", "content": final_tool_calls}

            yield {"type": "token_usage", "content": token_usage}

        except Exception as e:
            core.log_error("error while receiving response from AI", e)

    async def list_models(self):
        if not self.connected:
            return []

        try:
            models = await self._AI.models.list()
        except Exception as e:
            core.log_error("error while retrieving model list", e)
            return []

        return models
