import core
import httpx
import openai
import asyncio
import json
import time
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
        self.prompt_warming_up = False
        self.cancel_prompt_warmup = False
        self._warmup_task = None
        self._warmup_queue = asyncio.Queue()
        self._warmup_done = asyncio.Event()

        self._connection_error = None
        self._last_connection_attempt = None
        self._connection_attempts = 0

        # used for insecure SSL connections
        self._httpx_client = None

        self.supports_developer_role = False

    def _get_user_friendly_message(self, error_type, exception=None):
        """
        Maps technical error types to polite, actionable messages for end-users.
        Returns a dict with both a friendly message and the raw error details.
        """

        model_msg = f"Model {self._model} not found" if self._model else "You have no model set"
        messages = {
            "auth_failed": "Your API key is invalid or expired. Please check your configuration settings.",
            "connection_lost": "Lost connection to the AI server.",
            "rate_limit": "You are sending requests too quickly. Please wait a moment before trying again.",
            "api_error": "The AI server returned an unknown error. Please try again in a few minutes.",
            "model_not_found": f"{model_msg}. Please select a model by using `/models` or the Settings in the WebUI",
            "cancelled": "The request was cancelled.",
            "blank_request": "The request was empty. Please try typing your message again.",
            "processing_failed": "Failed to process the response from the AI. Please try sending your message again.",
            "invalid_response": "The AI returned an unexpected format. Please try again.",
            "unknown": "An unexpected error occurred.",
            "not_connected": "You are not connected to the AI server."
        }

        # Fallback to a generic message if the key isn't found
        base_msg = messages.get(error_type, messages["unknown"])

        result = {"message": base_msg}

        # Always include raw error details if available - the frontend can decide how to display
        if exception:
            result["raw_error"] = str(exception)

        return result

    async def connect(self, silent=False):
        if self.connected:
            return True

        self._model = core.config.get("model", "name")
        self._connection_attempts += 1
        api_config = core.config.get("api", {})

        # infinite timeout
        httpx_timeout = httpx.Timeout(
            connect=5.0,
            read=None,
            write=None,
            pool=None
        )

        use_secure_connection = not self.manager.args.insecure_tls
        if not use_secure_connection:
            self.manager.log("API", "WARNING: TLS certificate and hostname verification are disabled")

        try:
            self._httpx_client = httpx.AsyncClient(
                verify=use_secure_connection,
                timeout=httpx_timeout
            )

            self._AI = openai.AsyncOpenAI(
                base_url=api_config.get("url"),
                api_key=api_config.get("key"),
                http_client=self._httpx_client
            )
            await self._AI.models.list()

        except openai.BadRequestError as e:
            # Check if the error message specifically mentions the model is not found
            error_str = str(e).lower()
            if "model" in error_str and ("not found" in error_str or "missing" in error_str):
                self.manager.log_error("Model not found (400)", e)
                return {"error": "model_not_found", **self._get_user_friendly_message("model_not_found", e)}
            else:
                # It's a different kind of 400 error (e.g., invalid parameters)
                self.manager.log_error("Bad request (400)", e)
                return {"error": "api_error", **self._get_user_friendly_message("api_error", e)}

        except openai.AuthenticationError as e:
            await self.disconnect()
            error_info = self._get_user_friendly_message("auth_failed", e)
            self._connection_error = error_info["message"]
            self.manager.log("API", f"Authentication failed: {e}")
            return False

        except openai.APIConnectionError as e:
            await self.disconnect()
            error_info = self._get_user_friendly_message("connection_lost", e)
            self._connection_error = error_info["message"]
            self.manager.log("API", f"Connection failed: {e}")
            return False
        except Exception as e:
            await self.disconnect()
            error_info = self._get_user_friendly_message("unknown", e)
            self._connection_error = error_info["message"]
            self.manager.log("API", f"Unexpected connection error: {e}")
            return False

        self.connected = True
        self._connection_error = None
        self._connection_attempts = 0
        self.supports_developer_role = core.config.get("api", "use_developer_role", default=False)

        if not silent:
            self.manager.log("API", "Successfully connected to AI")

        # send the system prompt in the background,
        # so that the AI is ready to respond right away when the user has finished
        # typing their message
        # (thanks to https://www.reddit.com/r/LocalLLaMA/comments/1uskb1g/speculative_cache_warming_warms_your_cache_while/ for the idea)
        await self.start_prompt_warmup(context=[{"role": "system", "content": await self.manager.get_system_prompt()}], notify=False)

        return True

    def get_connection_status(self):
        api_config = core.config.get("api", {})
        model_config = core.config.get("model", {})

        return {
            "connected": self.connected,
            "error": self._connection_error,
            "url": api_config.get("url"),
            "model": self._model,
            "attempts": self._connection_attempts,
            "url_configured": bool(api_config.get("url")),
            "key_configured": bool(api_config.get("key")),
            "model_configured": bool(model_config.get("name")),
        }

    async def disconnect(self):
        """disconnect from the API"""
        if self._httpx_client:
            await self._httpx_client.aclose()
            self._httpx_client = None

        self.connected = False
        self._AI = None
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

    async def _request(self, context, tools=None, stream=False, use_thinking=True, **kwargs):
        """send a request to the LLM and return the response object"""

        if not context:
            # wtf just swallow it
            return {"error": "blank_request", "message": "tried to send a blank request for some reason"}

        if not self.connected:
            # attempt to connect
            connected = await self.connect(silent=True)
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
            "max_completion_tokens": core.config.get("api", {}).get("max_output_tokens", 8192),
            "extra_body": {
                "chat_template_kwargs": {
                    "enable_thinking": core.config.get("model", "enable_thinking", default=use_thinking)
                },
                "return_progress": True
            }
        }

        # add kwargs to the request
        for key, value in kwargs.items():
            if key in ("tools", "stream", "use_thinking"): continue
            req[key] = value

        reasoning_effort = core.config.get("model", {}).get("reasoning_effort")
        if reasoning_effort:
            req["reasoning_effort"] = reasoning_effort

        # allow inserting custom request fields
        custom_fields = core.config.get("api", {}).get("custom_fields", {})
        if isinstance(custom_fields, dict):
            for key, value in custom_fields.items():
                req[key] = value

        if stream:
            # request token usage from the API
            req["stream_options"] = {"include_usage": True}

        if core.debug:
            message_summary = []
            api_config = core.config.get("api", {})

            for message in context:
                summary = {
                    "role": message.get("role")
                }

                content = message.get("content")
                if isinstance(content, str):
                    summary["content_chars"] = len(content)
                elif isinstance(content, list):
                    summary["content_items"] = len(content)

                if message.get("tool_calls"):
                    summary["tool_calls"] = len(message.get("tool_calls") or [])

                message_summary.append(summary)

            tool_count = len(tools or [])
            custom_field_keys = sorted(list(custom_fields.keys())) if isinstance(custom_fields, dict) else []

            self.manager.log(
                "debug:request",
                json.dumps({
                    "base_url": api_config.get("url"),
                    "model": self._model,
                    "stream": stream,
                    "use_thinking": use_thinking,
                    "message_count": len(context),
                    "tool_count": tool_count,
                    "max_completion_tokens": req.get("max_completion_tokens"),
                    "temperature": req.get("temperature"),
                    "reasoning_effort": req.get("reasoning_effort"),
                    "custom_field_keys": custom_field_keys,
                    "messages": message_summary,
                }, ensure_ascii=True, sort_keys=True)
            )

        response = None
        try:
            # if at this point a cancel was already requested,
            # it was likely from a toolcalling chain, so abort EVERYTHING
            if self.cancel_request and not self.prompt_warming_up:
                raise asyncio.CancelledError("Request cancelled")

            request_task = asyncio.create_task(self._AI.chat.completions.create(**req))

            # wrap the request in a way that we can check for cancellation
            # since openai's async client doesn't natively support an abort signal
            # easily through the high-level chat.completions.create, we use a task
            # so we can actually cancel the task itself.

            # monitor the task and the cancel_request flag
            while not request_task.done():
                if self.cancel_request or self.cancel_prompt_warmup:
                    request_task.cancel()
                    raise asyncio.CancelledError("Request cancelled")

                await asyncio.sleep(0.1)

            response = await request_task

        except asyncio.CancelledError as e:
            # fully kill the connection because ive been debuggging this for like 5 hours and im tired
            # make it stop
            #self.manager.log("api", "Force closing HTTP connection due to unclean state..")
            await self.disconnect()

            self.cancel_request = False

            # and propagate it up for any other stuff to handle
            raise

        except openai.BadRequestError as e:
            # Check if the error message specifically mentions the model is not found
            error_str = str(e).lower()
            if "model" in error_str and ("not found" in error_str or "missing" in error_str):
                self.manager.log_error("Model not found (400)", e)
                return {"error": "model_not_found", **self._get_user_friendly_message("model_not_found", e)}
            else:
                # It's a different kind of 400 error (e.g., invalid parameters)
                self.manager.log_error("Bad request (400)", e)
                return {"error": "api_error", **self._get_user_friendly_message("api_error", e)}

        except openai.AuthenticationError as e:
            self.manager.log_error("Authentication error", e)
            self.connected = False
            error_info = self._get_user_friendly_message("auth_failed", e)
            self._connection_error = error_info["message"]
            return {"error": "auth_failed", **error_info}

        except openai.APIConnectionError as e:
            self.manager.log_error("Connection error", e)
            self.connected = False
            error_info = self._get_user_friendly_message("connection_lost", e)
            self._connection_error = error_info["message"]
            return {"error": "connection_lost", **error_info}

        except openai.NotFoundError as e:
            self.manager.log_error("Model not found", e)
            return {"error": "model_not_found", **self._get_user_friendly_message("model_not_found", e)}

        except openai.RateLimitError as e:
            self.manager.log_error("Rate limit exceeded", e)
            return {"error": "rate_limit", **self._get_user_friendly_message("rate_limit", e)}

        except openai.APIStatusError as e:
            self.manager.log_error("API status error", e)
            return {"error": "api_error", **self._get_user_friendly_message("api_error", e)}

        except Exception as e:
            self.manager.log_error("error while sending request to AI", e)
            self.connected = False
            return {"error": "unknown", **self._get_user_friendly_message("unknown", e)}

        finally:
            self.cancel_request = False

        if core.debug:
            self.manager.log("debug:response", str(response))

        return response

    async def stop_prompt_warmup(self):
        if self._warmup_task and not self._warmup_task.done():
            self.cancel_prompt_warmup = True
            self._warmup_task.cancel()
            try:
                await self._warmup_task
            except asyncio.CancelledError:
                return
            except Exception as e:
                self.manager.log_error("Warmup task failed", e)
            finally:
                self.cancel_prompt_warmup = False

        # clear the queue completely
        while not self._warmup_queue.empty():
            try:
                self._warmup_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        self._warmup_task = None
        self.prompt_warming_up = False

    async def start_prompt_warmup(self, context=None, notify=True):
        # cancel existing warmup task if there's already one running
        # (for example if the warmup is running for one chat,
        # and the user switches to a different one)
        await self.stop_prompt_warmup()
        self._warmup_done.clear()

        self._warmup_task = asyncio.create_task(self._run_warmup(context=context, notify=notify))
        if notify:
            self.manager.log("API", "Sending prompt in advance to make AI response instant.. (prompt warmup)")

    async def _run_warmup(self, context=None, notify=True):
        self._warmup_done.clear()
        self.prompt_warming_up = True

        try:
            if not context:
                prompt = await self.manager.get_system_prompt()
                context = [{"role": "system", "content": prompt}]

            response = await self._request(context, stream=True, tools=self.manager.tools, use_thinking=False, max_completion_tokens=1)

            if isinstance(response, dict):
                # thats an error
                return

        except Exception as e:
            self.manager.log("api", f"Failure while sending prompt warmup request to AI: {core.detail_error(e)}")

        try:
            async for token in self._recv_stream(response):
                if self.cancel_request:
                    raise asyncio.CancelledError("Warmup task cancelled")

                if token.get("type") == "prompt_progress":
                    await self._warmup_queue.put(token)
            if notify:
                self.manager.log("API", "Prompt warmup complete")

        except asyncio.CancelledError:
            # fully kill the connection because ive been debuggging this for like 5 hours and im tired
            # make it stop
            #self.manager.log("api", "Force closing HTTP connection due to unclean state..")
            await self.disconnect()
        except Exception as e:
            if notify:
                self.manager.log("api", f"Warmup request failed: {core.detail_error(e)}")
        finally:
            self.prompt_warming_up = False
            self._warmup_done.set()

    async def send(self, context: list, system_prompt=True, use_tools=True, tools=None, use_thinking=True, **kwargs):
        """send a message to the LLM. returns a string or error dict"""

        self.cancel_request = False

        # wait for the system prompt warmup to finish if it's still running
        if self._warmup_task and not self._warmup_task.done():
            if core.debug:
                self.manager.log("API", "Waiting for prompt warmup to complete..")
            await self._warmup_task

        # use default tools if not specified. allow overrides
        if not tools:
            tools = self.manager.tools

        response = await self._request(context, tools=(tools if use_tools else None), use_thinking=use_thinking, **kwargs)

        # return errors if applicable
        if isinstance(response, dict) and "error" in response:
            return response

        try:
            result = await self._recv(response)
            return result
        except Exception as e:
            self.manager.log_error("error while processing response from AI", e)
            return {"error": "processing_failed", **self._get_user_friendly_message("processing_failed", e)}

    async def send_stream(self, context: list, use_tools=True, tools=None, use_thinking=True, **kwargs):
        """send a message to the LLM. is an iterable async generator"""

        self.cancel_request = False

        # drain progress tokens while waiting for warmup to finish
        # so that warmup progress can be shown in channels
        if self._warmup_task and not self._warmup_task.done():
            while not self._warmup_done.is_set():
                try:
                    token = self._warmup_queue.get_nowait()
                    yield token
                except asyncio.QueueEmpty:
                    await asyncio.sleep(0.01)

        # drain any remaining tokens that arrived while we were yielding
        while not self._warmup_queue.empty():
            yield await self._warmup_queue.get()

        # wait for the prompt warmup to actually finish
        if self._warmup_task and not self._warmup_task.done():
            await self._warmup_task

        # use default tools if not specified. allow overrides
        if not tools:
            tools = self.manager.tools

        response = await self._request(context, tools=(tools if use_tools else None), stream=True, use_thinking=use_thinking, **kwargs)

        # return errors if applicable
        if isinstance(response, dict):
            yield response
            return

        try:
            async for token in self._recv_stream(response):
                if self.cancel_request:
                    # cancel the entire stream
                    break

                if core.debug_stream:
                    self.manager.log("debug:stream", json.dumps(token, ensure_ascii=True))

                # let the channel calling send_stream() handle token processing
                yield token
        except Exception as e:
            self.manager.log_error("error while sending request to AI", e)
            yield {"type": "error", "content": {"error": "stream_failed", **self._get_user_friendly_message("processing_failed", e)}}

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
            #self.manager.log_error("error while receiving response from AI", e)
            return {"error": "invalid_response", "message": self._get_user_friendly_message("invalid_response", e)}

        reasoning_content = getattr(response_main.message, "reasoning_content", None) or \
                            getattr(response_main.message, "reasoning", None) or ""

        if reasoning_content and core.debug:
            self.manager.log("debug:reasoning", reasoning_content)

        # extract message content
        final_content = response_main.message.content or ""

        # handle tool calls, if any
        tool_calls = None
        if use_tools and core.config.get("model").get("use_tools", False) and response_main.message.tool_calls:
            tool_calls = [tc.model_dump(warnings=False) for tc in response_main.message.tool_calls]

        result = {}

        if final_content:
            result["content"] = final_content
        if reasoning_content:
            result["reasoning_content"] = reasoning_content
        if tool_calls:
            result["tool_calls"] = tool_calls

            # role is always assistant, so we force it if for some reason its not present
            result["role"] = "assistant"

        return result

    async def _recv_stream(self, response, use_tools=True):
        """Takes a response object and extracts the message from it, handling tool calls if needed. Streaming version."""
        final_tool_calls = []
        tool_call_buffer = {}
        tokens = []
        reasoning_tokens = []

        token_usage = None
        total_prompt_tokens = 0
        total_completion_tokens = 0
        has_usage_data = False
        last_token_time = 0

        if not response:
            return

        try:
            async for chunk in response:
                if self.cancel_request:
                    if hasattr(response, "close"):
                        # support closing
                        await response.close()
                    return

                # uncomment if trying to see token stream chunks
                # print(chunk)

                if hasattr(chunk, 'prompt_progress') and chunk.prompt_progress is not None:
                    yield {
                        "type": "prompt_progress",
                        "content": chunk.prompt_progress
                    }

                # Calculate time delta for real-time stats
                current_time = time.time()
                delta_ms = (current_time - last_token_time) * 1000
                last_token_time = current_time


                if chunk.choices:
                    streamed_token = chunk.choices[0].delta

                    content_yield = None

                    # handle content token streaming
                    if streamed_token.content:
                        tokens.append(streamed_token.content)
                        content_yield = {"type": "content", "content": streamed_token.content}

                    # handle reasoning content streaming
                    reason_part = getattr(streamed_token, "reasoning_content", None) or \
                                getattr(streamed_token, "reasoning", None)

                    if reason_part:
                        reasoning_tokens.append(reason_part)
                        content_yield = {"type": "reasoning", "content": reason_part}

                    # add timing data to the yielded token
                    if streamed_token.content or reason_part:
                        # Send timing data: Use native if available, otherwise calculate
                        native_timings = getattr(chunk, 'timings', None)
                        if native_timings:
                            content_yield["timings"] = native_timings

                        else:
                            # Fallback: Calculate tokens/s based on time between chunks
                            if delta_ms > 1: # Only yield if significant time passed
                                content_yield["timings"] = {
                                    "predicted_ms": delta_ms,
                                    "predicted_n": 1
                                }

                    # and finally, yield the content token
                    if content_yield:
                        yield content_yield

                    # extract tool calls, if any
                    if streamed_token.tool_calls and use_tools:
                        for tool_call in streamed_token.tool_calls:
                            index = tool_call.index

                            if index not in tool_call_buffer:
                                tool_call_buffer[index] = tool_call
                                # ensure arguments is always a string
                                if tool_call_buffer[index].function.arguments is None:
                                    tool_call_buffer[index].function.arguments = ""

                                yield {
                                    "type": "tool_call_delta",
                                    "tool_calls": [tool_call_buffer[index]]
                                }
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

                                    # the magic sauce that allows streaming toolcall arguments
                                    yield {
                                        "type": "tool_call_delta",
                                        "tool_calls": [tool_call_buffer[index]]
                                    }

                # if response has usage data, save it so we can use it to show to the user and to trim context
                if hasattr(chunk, 'usage') and chunk.usage is not None:
                    if hasattr(chunk.usage, 'prompt_tokens'):
                        total_prompt_tokens = chunk.usage.prompt_tokens
                    if hasattr(chunk.usage, 'completion_tokens'):
                        total_completion_tokens = chunk.usage.completion_tokens
                    if hasattr(chunk.usage, 'total_tokens'):
                        token_usage = chunk.usage.total_tokens
                    elif total_prompt_tokens > 0 or total_completion_tokens > 0:
                        # Calculate total if not provided
                        token_usage = total_prompt_tokens + total_completion_tokens

                    yield {"type": "token_usage", "content": token_usage, "source": "API"}

                if hasattr(chunk, 'timings'):
                    yield {"type": "timings", "content": chunk.timings}

            if use_tools:
                for index in sorted(tool_call_buffer.keys()):
                    # filter out blank tool calls (rare model glitch)
                    tool_call = tool_call_buffer[index]
                    if not tool_call.function.name:
                        continue

                    final_tool_calls.append(tool_call)

                if final_tool_calls and core.config.get("model").get("use_tools", False):
                    # yield the full toolcall object as a single token to be interpreted by the function that is iterating through _recv_stream()
                    tool_call_dicts = [tc.model_dump(warnings=False) for tc in final_tool_calls]
                    yield {"type": "tool_calls", "tool_calls": tool_call_dicts}

        except Exception as e:
            #self.manager.log_error("error while receiving response from AI", e)
            raise e # Re-raise so send_stream can catch it and yield the error type

    async def list_models(self):
        if not self.connected:
            await self.connect()

        try:
            # get alphabetically sorted model list
            models = await self._AI.models.list()
            models_list = [model.id for model in models.data]
            models_list.sort()

        except Exception as e:
            self.manager.log_error("error while retrieving model list", e)
            return []

        return models_list
