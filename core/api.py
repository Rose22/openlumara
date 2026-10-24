import core
import core.http_sse as http_sse
import aiohttp
import asyncio
import copy
import json
import ssl
import time
import urllib.parse

class APIError:
    """Simple class that holds an error message, used for passing on to channels"""
    def __init__(self, message: str = None, exc = None):
        self.message = message
        
        # store exception if relevant
        self.exc = None
        if exc:
            self.exc = exc

    def __str__(self):
        err_str = ""
        if self.message:
            err_str += self.message
        if self.exc:
            if self.message:
                err_str += ": "
            err_str += core.detail_error(self.exc)

        return err_str

class APIHTTPError(Exception):
    """a HTTP response with a non-200 status"""
    def __init__(self, status: int, body: str = ""):
        self.status = status
        self.body = body or ""
        super().__init__(f"HTTP {status}: {self.body[:500]}")

class APIClient():
    """
    wrapper around an OpenAI-compatible chat completions API
    """

    MAX_API_ATTEMPTS = 3
    RETRY_BASE_DELAY = 0.5
    RETRYABLE_STATUS_CODES = (408, 409, 425, 429, 500, 502, 503, 504)

    def __init__(self, manager):
        # store a reference to the manager
        self.manager = manager

        self.connected = False
        self.is_streaming = False

        self._messages = []

        self.cancel_request = False

        # active low-level HTTP request task, used for reliable cancellation
        self._request_task = None

        # guards session lifecycle against concurrent connect/disconnect calls
        self._connect_lock = asyncio.Lock()

        # active streamed HTTP response, so cancel() can sever the SSE
        # connection immediately instead of waiting for the next token
        self._stream_response = None

        # the aiohttp session is the one HTTP client for everything
        self._session = None
        self._ssl_ctx = None # only set when TLS verification is disabled

        self.supports_developer_role = False

        # origin of the API when it's a llama.cpp router. enables the model load progress feed.
        self._router_origin = None

    # -------------------
    # HTTP plumbing
    # -------------------
    def _api_headers(self):
        """auth headers for calls to the API"""
        key = core.config.get("api", "key")
        if key:
            return {"Authorization": f"Bearer {key}"}
        return {}

    def _json_headers(self):
        headers = self._api_headers()
        headers["Content-Type"] = "application/json"
        return headers

    def _make_session(self):
        """create the shared aiohttp session"""
        # infinite read timeout (long generations and model loads must not be cut off)
        timeout = aiohttp.ClientTimeout(total=None, connect=5.0)
        return aiohttp.ClientSession(timeout=timeout)

    async def _http_get(self, url, timeout_total=None):
        """GET a url and return (status, body_text)"""
        kwargs = {"headers": self._api_headers()}
        if self._ssl_ctx is not None:
            kwargs["ssl"] = self._ssl_ctx
        if timeout_total is not None:
            kwargs["timeout"] = aiohttp.ClientTimeout(total=timeout_total)

        async with self._session.get(url, **kwargs) as resp:
            return resp.status, await resp.text()

    async def _probe_chat_completions(self):
        """validate the API with a minimal chat completion request"""
        api_config = core.config.get("api", {})
        
        probe_body = {
            "messages": [{"role": "user", "content": "ping"}],
            "stream": False,
            "max_completion_tokens": 1,
        }
        model_name = core.config.get("model", "name")
        if model_name:
            probe_body["model"] = model_name

        kwargs = {"headers": self._json_headers(), "json": probe_body}
        if self._ssl_ctx is not None:
            kwargs["ssl"] = self._ssl_ctx

        async with self._session.post(
            f"{api_config.get('url')}/chat/completions",
            timeout=aiohttp.ClientTimeout(total=60, connect=15),
            **kwargs,
        ) as resp:
            return resp.status, await resp.text()

    def _error_for_status(self, status, body, prefix=""):
        """maps an HTTP error response onto a APIError"""
        e = APIHTTPError(status, body)
        error_str = (body or "").lower()

        if status == 400:
            # check if the error message specifically mentions the model is not found
            if "model" in error_str and ("not found" in error_str or "missing" in error_str):
                return APIError("Model with that name does not exist!", e)
            return APIError("Bad request", e)

        if status in (401, 403):
            return APIError("Authentication failed. Check whether your API key is valid!", e)

        if status == 404:
            return APIError("Model with that name does not exist!", e)

        if status == 429:
            return APIError("Rate limit exceeded", e)

        return APIError("API Status Error", e)

    # -------------------
    # Connection management
    # -------------------
    async def connect(self, silent=False):
        if self.connected:
            return True

        async with self._connect_lock:
            # dont allow concurrent connect() calls
            if self.connected:
                return True

            return await self._connect_setup(silent=silent)

    async def _connect_setup(self, silent=False):
        api_config = core.config.get("api", {})

        if api_config.get("url") == "http://API_URL_HERE/v1":
            return APIError("The API connection has not been set up yet! Please set up your API connection by either using the WebUI, the /config command, or editing the config file")

        # close any session left over from a previous failed connect attempt
        await self._close_session()

        use_secure_connection = not self.manager.args.insecure_tls
        if not use_secure_connection:
            self.manager.log("API", "WARNING: TLS certificate and hostname verification are disabled")

        try:
            self._session = self._make_session()

            if not use_secure_connection:
                self._ssl_ctx = ssl.create_default_context()
                self._ssl_ctx.check_hostname = False
                self._ssl_ctx.verify_mode = ssl.CERT_NONE

            # validate the connection with a minimal chat-completions request
            status, body = await self._probe_chat_completions()
            connection_error = None

            if status in (400, 404):
                error_str = body.lower()
                if "model" in error_str and ("not found" in error_str or "missing" in error_str):
                    connection_error = APIError("Model not found.")
                elif status != 400:
                    connection_error = APIError("The URL does not look like a chat-completions API.", APIHTTPError(status, body))
                # status 400 without a model complaint: accept the connection

            elif status in (401, 403):
                connection_error = APIError("Authentication failed. Check if your API key is valid.", APIHTTPError(status, body))

            elif status == 405:
                connection_error = APIError("The URL does not look like a chat-completions API.", APIHTTPError(status, body))

            elif status != 200:
                connection_error = APIError("Failed to connect to the API", APIHTTPError(status, body))

            if connection_error is not None:
                await self._close_session()
                return connection_error

        except aiohttp.ClientError as e:
            await self._close_session()
            return APIError("Failed to connect to the API", e)

        except Exception as e:
            await self._close_session()
            import traceback
            if core.debug:
                traceback.print_exc()
            return APIError(None, e)

        self.connected = True
        self.supports_developer_role = core.config.get("api", "use_developer_role", default=False)

        # probe for a llama.cpp router so we can stream model-load progress
        await self._detect_router()

        if not silent:
            self.manager.log("API", "Successfully connected to AI")

        return True
    
    async def attempt_connect(self):
        """connect if disconnected, else just return True"""
        if not self.connected:
            return await self.connect()
        
        return True

    def get_status(self):
        api_config = core.config.get("api", {})
        model_config = core.config.get("model", {})

        return {
            "connected": self.connected,
            "url": api_config.get("url"),
            "model": core.config.get("model", "name")
        }

    async def _close_session(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def disconnect(self):
        """disconnect from the API"""
        # dont allow concurrent disconnect() calls
        async with self._connect_lock:
            await self._close_session()

            # clear per-session state
            self._ssl_ctx = None
            self._router_origin = None

            self.connected = False

        return True

    async def reconnect(self):
        """disconnect and reconnect to the API"""
        await self.disconnect()
        return await self.connect()

    # -------------------
    # llama.cpp router support
    # -------------------
    async def _detect_router(self):
        """
        probe the API to detect if it's a llamacpp instance that's in router mode
        (to support features exclusive to llamacpp, such as
        model loading progress bars, prompt progress, and so on)
        """
        self._router_origin = None

        try:
            api_url = core.config.get("api", "url") or ""
            parsed = urllib.parse.urlsplit(api_url)

            if not parsed.scheme or not parsed.netloc:
                return

            origin = f"{parsed.scheme}://{parsed.netloc}"
            status, body = await self._http_get(f"{origin}/models", timeout_total=5.0)

            if status != 200:
                return

            body = json.loads(body)
            entries = body.get("data")

            if isinstance(entries, list) and any(isinstance(e, dict) and "status" in e for e in entries):
                self._router_origin = origin

        except Exception as e:
            pass

    async def _watch_model_load(self, model_name, queue):
        """reads the llamacpp router's /models/sse feed while a model loads"""
        try:
            url = f"{self._router_origin}/models/sse"
            kwargs = {"headers": self._api_headers()}
            if self._ssl_ctx is not None:
                kwargs["ssl"] = self._ssl_ctx

            async with self._session.get(url, **kwargs) as feed:
                async for event in http_sse.iter_events(feed):
                    # the SSE parser merges the event/id fields into the
                    # parsed data payload
                    if event.get("event") not in ("status_change", "model_status"):
                        continue

                    # the payload IS the event data (status/model/progress live
                    # at the top level of the parsed JSON)
                    data = event
                    status = data.get("status") or ""
                    name = data.get("model") or ""

                    if status in ("loaded", "unloaded"):
                        # let the prompt/content tokens take over the progress indicator
                        if name == model_name:
                            return
                        continue

                    if status not in ("loading", "queued", "downloading"):
                        continue

                    progress = data.get("progress") or {}
                    value = progress.get("value")

                    await queue.put({
                        "model": name,
                        "status": status,
                        "stage": progress.get("current") or "",
                        "percent": round(value * 100) if isinstance(value, (int, float)) else None,
                    })

        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    # -------------------
    # Model config
    # -------------------
    def get_model(self):
        return core.config.get("model", "name")

    def set_model(self, name: str):
        core.config.config["model"]["name"] = name
        core.config.config.save()

        return True

    # -------------------
    # Requests
    # -------------------
    async def _post_chat_completion(self, payload, stream=False):
        """
        sends the chat completions request over HTTP.
        returns a parsed JSON dict when not streaming,
        or an open aiohttp ClientResponse (to be consumed by _recv_stream) when streaming.
        """
        url = f"{core.config.get('api', 'url')}/chat/completions"

        kwargs = {"json": payload, "headers": self._json_headers()}
        if self._ssl_ctx is not None:
            kwargs["ssl"] = self._ssl_ctx

        if stream:
            resp = await self._session.post(url, **kwargs)

            if resp.status != 200:
                body = await resp.text()
                await resp.release()
                raise APIHTTPError(resp.status, body)

            return resp

        async with self._session.post(url, **kwargs) as resp:
            body = await resp.text()

            if resp.status != 200:
                raise APIHTTPError(resp.status, body)

            return json.loads(body)

    # -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-24) harness:openlumara status:reviewed
	# ROSE22: i mean, this is just an exception parser.
    def _is_retryable_error(self, exc):
        """whether a failed request may be retried"""
        if isinstance(exc, APIHTTPError):
            return exc.status in self.RETRYABLE_STATUS_CODES
        if isinstance(exc, aiohttp.ClientSSLError):
            return False
        if isinstance(exc, aiohttp.ClientConnectionError):
            return True
        if isinstance(exc, asyncio.TimeoutError):
            return True
        return False

    async def _request(self, context, tools=None, stream=False, use_thinking=True, **kwargs):
        """send a request to the LLM and return the response (dict, or an open SSE response when streaming)"""

        if not context:
            # this should never happen..
            # so if it does, always print a traceback, since it's bad news!
            import traceback
            traceback.print_stack()

            return APIError("Tried to send a blank request for some reason! This should NEVER happen. Notify the developer.")

        connected = await self.attempt_connect()
        if connected is not True:
            # thats an error
            return connected

        if not core.config.get("model", {}).get("use_tools"):
            # allow switching tools off globally
            tools = None

        req = {
            "model": core.config.get("model", "name"),
            "messages": context,
            "stream": stream,
            "temperature": core.config.get("model", {}).get("temperature", 0.7),
            "max_completion_tokens": core.config.get("api", {}).get("max_output_tokens", 8192),
            
            # llamacpp-specific extras
            "chat_template_kwargs": {
                "enable_thinking": core.config.get("model", "enable_thinking", default=use_thinking)
            },
            "return_progress": True
        }

        if tools:
            req["tools"] = tools

        # add kwargs to the request
        for key, value in kwargs.items():
            if key in ("tools", "stream", "use_thinking"): continue
            req[key] = value

        reasoning_effort = core.config.get("model", {}).get("reasoning_effort")
        if reasoning_effort and reasoning_effort != "none":
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

#             self.manager.log(
#                 "debug:request",
#                 json.dumps({
#                     "base_url": api_config.get("url"),
#                     "model": core.config.get("model", "name"),
#                     "stream": stream,
#                     "use_thinking": use_thinking,
#                     "message_count": len(context),
#                     "tool_count": tool_count,
#                     "max_completion_tokens": req.get("max_completion_tokens"),
#                     "temperature": req.get("temperature"),
#                     "reasoning_effort": req.get("reasoning_effort"),
#                     "custom_field_keys": custom_field_keys,
#                     "messages": message_summary,
#                 }, ensure_ascii=True, sort_keys=True)
#             )

        response = None
        attempt = 1
        try:
            # retry loop
            while True:
                try:
                    # if at this point a cancel was already requested,
                    # it was likely from a toolcalling chain, so abort EVERYTHING
                    if self.cancel_request:
                        raise asyncio.CancelledError("Request cancelled")

                    request_task = asyncio.create_task(self._post_chat_completion(req, stream=stream))
                    # keep a reference so cancel() can abort a request that
                    # is still in-flight (before streaming started)
                    self._request_task = request_task

                    # wrap the request in a task that we can poll for cancellation,
                    # so a cancel aborts no matter what
                    try:
                        while not request_task.done():
                            if self.cancel_request:
                                request_task.cancel()
                            await asyncio.sleep(0.1)

                        response = await request_task
                    except asyncio.CancelledError:
                        if not request_task.done():
                            request_task.cancel()
                        raise
                    finally:
                        self._request_task = None

                    break

                except (APIHTTPError, aiohttp.ClientError, asyncio.TimeoutError) as e:
                    if attempt >= self.MAX_API_ATTEMPTS or not self._is_retryable_error(e) or self.cancel_request:
                        raise

                    delay = self.RETRY_BASE_DELAY * attempt
                    self.manager.log(
                        "API",
                        f"request failed ({type(e).__name__}), retrying in {delay:.1f}s "
                        f"(attempt {attempt + 1}/{self.MAX_API_ATTEMPTS})"
                    )

                    # wait with backoff, while staying responsive to cancellation
                    waited = 0.0
                    while waited < delay:
                        if self.cancel_request:
                            raise asyncio.CancelledError("Request cancelled")
                        await asyncio.sleep(0.1)
                        waited += 0.1
                    attempt += 1

        except asyncio.CancelledError as e:
            self.cancel_request = False

            # and propagate it up for any other stuff to handle
            raise

        except APIHTTPError as e:
            return self._error_for_status(e.status, e.body)

        except aiohttp.ClientError as e:
            return APIError("Failed to connect to API", e)

        except Exception as e:
            return APIError(None, e)

        finally:
            self.cancel_request = False
            self._request_task = None

#         if core.debug:
#             self.manager.log("debug:response", str(response))

        return response

    async def send(self, context: list, system_prompt=True, use_tools=True, tools=None, use_thinking=True, **kwargs):
        """send a message to the LLM. returns a dict or APIError"""

        self.cancel_request = False

        # attempt auto-reconnect once
        connected = await self.attempt_connect()
        if connected is not True:
            # thats an error!
            return connected

        # use default tools if not specified. allow overrides
        if not tools:
            tools = self.manager.tools

        response = await self._request(context, tools=(tools if use_tools else None), use_thinking=use_thinking, **kwargs)

        # return errors if applicable
        if isinstance(response, APIError):
            return response

        try:
            result = await self._recv(response)
            return result
        except Exception as e:
            return APIError("While processing response from AI", e)

    async def send_stream(self, context: list, use_tools=True, tools=None, use_thinking=True, **kwargs):
        """send a message to the LLM. is an iterable async generator"""

        self.cancel_request = False

        # attempt auto-reconnect once
        connected = await self.attempt_connect()
        if connected is not True:
            # that's an error
            yield {"type": "error", "content": str(connected)}
            return

        # use default tools if not specified. allow overrides
        if not tools:
            tools = self.manager.tools

        # against a llama.cpp router, the request below blocks while a model
        # is swapped in. run the SSE load watcher alongside it and yield
        # model_load_progress tokens until the request resolves.
        load_task = None
        load_queue = None

        if self._router_origin:
            load_queue = asyncio.Queue()
            load_task = asyncio.create_task(self._watch_model_load(core.config.get("model", "name"), load_queue))

        request_task = asyncio.create_task(self._request(context, tools=(tools if use_tools else None), stream=True, use_thinking=use_thinking, **kwargs))

        response = None
        try:
            while True:
                while load_queue and not load_queue.empty():
                    yield {"type": "model_load_progress", "content": load_queue.get_nowait()}

                if request_task.done():
                    break

                await asyncio.wait([request_task], timeout=0.25)

            response = await request_task

        finally:
            if load_task and not load_task.done():
                load_task.cancel()

            # if we bailed out before the request resolved (cancel, generator
            # closed early, etc.), make sure the request itself is aborted too
            if response is None and not request_task.done():
                request_task.cancel()

        # return errors if applicable
        if isinstance(response, APIError):
            yield {"type": "error", "content": str(response)}
            return

        try:
            self.is_streaming = True
            # expose the live SSE response so cancel() can abort the blocked
            # read immediately (per-event flag checks alone only notice a
            # cancel when the next token arrives)
            self._stream_response = response

            async for token in self._recv_stream(response):
                if self.cancel_request:
                    # cancel the entire stream
                    raise asyncio.CancelledError("Request cancelled")

                if core.debug_stream:
                    self.manager.log("debug:stream", json.dumps(token, ensure_ascii=True))

                # let the channel calling send_stream() handle token processing
                yield token
        except asyncio.CancelledError:
            self.cancel_request = False
            raise  # let callers handle cancellation
        except Exception as e:
            if self.cancel_request:
                # this is almost certainly the read aborting because cancel()
                # force-closed the response: that IS the requested cancellation,
                # not an error - surface it as such instead of an error bubble
                self.cancel_request = False
                raise asyncio.CancelledError("Request cancelled")
            yield {"type": "error", "content": f"While sending request to AI: {core.detail_error(e)}"}
        finally:
            self.is_streaming = False
            self._stream_response = None

            # make sure the SSE connection is always released
            if response is not None and not isinstance(response, APIError) and hasattr(response, "close"):
                response.close()

    async def cancel(self):
        """
        cancel a request that's been sent to the AI.
        safe to call at any time, also when nothing is active.
        """
        self.cancel_request = True

        request_task = self._request_task
        if request_task and not request_task.done():
            # request is in-flight but not streaming yet
            request_task.cancel()

        if self._stream_response is not None:
            # streaming: the per-event checks in send_stream/_recv_stream only
            # run when the next SSE event arrives, so during a token gap a stop
            # could hang until generation resumes. sever the connection now -
            # the blocked read wakes with a connection error, which send_stream
            # translates back into a clean cancellation while cancel_request
            # is still set.
            try:
                self._stream_response.close()
            except Exception:
                pass

        if not self.is_streaming and not (request_task and not request_task.done()):
            # nothing was active, so clear the flag
            self.cancel_request = False
            return False

        # wait for the cancellation to complete
        while self.cancel_request:
            await asyncio.sleep(0.05)

        return True

    async def _recv(self, response, use_tools=True):
        """takes a response dict and extracts the message from it, handling tool calls if needed"""

        try:
            # normal non-streaming mode
            response_main = response["choices"][0]
        except Exception as e:
            raise e # raise it so send() can catch it

        message = response_main.get("message") or {}

        reasoning_content = message.get("reasoning_content") or message.get("reasoning") or ""

        if reasoning_content and core.debug:
            self.manager.log("debug:reasoning", reasoning_content)

        # extract message content
        final_content = message.get("content") or ""

        # handle tool calls, if any
        tool_calls = None
        if use_tools and core.config.get("model").get("use_tools", False) and message.get("tool_calls"):
            tool_calls = [copy.deepcopy(tc) for tc in message.get("tool_calls")]

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
        """
        Takes a HTTP SSE response object and yields tokens from it,
        handling tool calls if needed. Streaming version.
        """
        final_tool_calls = []
        tool_call_buffer = {}

        token_usage = None
        total_prompt_tokens = 0
        total_completion_tokens = 0
        last_token_time = 0

        if not response:
            return

        response_started = False
        try:
            async for chunk in http_sse.iter_events(response):
                if not response_started:
                    # mark it as started so that we can detect if the API has returned a blank message
                    # (for example due to an error the inference server, i.e. llamacpp, failed to send)
                    response_started = True

                if self.cancel_request:
                    # closing the response severs the HTTP connection immediately
                    response.close()
                    raise asyncio.CancelledError("Request cancelled")

                if chunk.get("error") is not None or chunk.get("event") == "error":
					# surface errors if they appear
                    err = chunk.get("error")
                    message = None
                    if isinstance(err, dict):
                        inner = err.get("error")
                        message = err.get("message")
                        if message is None and isinstance(inner, dict):
                            message = inner.get("message")
                        elif message is None and isinstance(inner, str):
                            message = inner
                        if message is None:
                            message = json.dumps(err)
                    elif err is not None:
                        message = str(err)
                    if not message:
                        message = "The API reported an error while streaming the response."

                    yield {"type": "error", "content": str(message)}
                    return

                # uncomment if trying to see token stream chunks
                #print(chunk)

                if chunk.get("prompt_progress") is not None:
                    yield {
                        "type": "prompt_progress",
                        "content": chunk.get("prompt_progress")
                    }

                # Calculate time delta for real-time stats
                current_time = time.time()
                delta_ms = (current_time - last_token_time) * 1000
                last_token_time = current_time

                if chunk.get("choices"):
                    streamed_token = chunk["choices"][0].get("delta") or {}

                    content_yield = None

                    # handle content token streaming
                    if streamed_token.get("content"):
                        content_yield = {"type": "content", "content": streamed_token["content"]}

                    # handle reasoning content streaming
                    reason_part = streamed_token.get("reasoning_content") or streamed_token.get("reasoning")

                    if reason_part:
                        content_yield = {"type": "reasoning", "content": reason_part}

                    # add timing data to the yielded token
                    if streamed_token.get("content") or reason_part:
                        # Send timing data: Use native if available, otherwise calculate
                        native_timings = chunk.get("timings")
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
                    if streamed_token.get("tool_calls") and use_tools:
                        for tool_call in streamed_token["tool_calls"]:
                            index = tool_call.get("index", 0)

                            if index not in tool_call_buffer:
                                tool_call_buffer[index] = copy.deepcopy(tool_call)
                                # ensure arguments is always a string
                                if tool_call_buffer[index].get("function", {}).get("arguments") is None:
                                    tool_call_buffer[index].setdefault("function", {})["arguments"] = ""

                                yield {
                                    "type": "tool_call_delta",
                                    "tool_calls": [copy.deepcopy(tool_call_buffer[index])]
                                }
                            else:
                                # it seems these properties will only show up in one chunk,
                                # and the rest of the stream won't have them anymore..
                                # so the AI decided we should set these if they show up
                                # and then just assume it won't happen again
                                # i guess if it does, it just overwrites it..
                                if tool_call.get("id"):
                                    tool_call_buffer[index]["id"] = tool_call["id"]

                                incoming_fn = tool_call.get("function") or {}
                                buffer_fn = tool_call_buffer[index].setdefault("function", {})

                                if incoming_fn.get("name"):
                                    buffer_fn["name"] = incoming_fn["name"]

                                # function arguments seem to be the part that actually gets streamed
                                # and which we must accumulate to get the full toolcall
                                if incoming_fn.get("arguments"):
                                    buffer_fn["arguments"] = buffer_fn.get("arguments", "") + incoming_fn["arguments"]

                                    # the magic sauce that allows streaming toolcall arguments
                                    yield {
                                        "type": "tool_call_delta",
                                        "tool_calls": [copy.deepcopy(tool_call_buffer[index])]
                                    }

                # if response has usage data, save it so we can use it to show to the user and to trim context
                if chunk.get("usage") is not None:
                    usage = chunk["usage"]

                    if usage.get("prompt_tokens") is not None:
                        total_prompt_tokens = usage["prompt_tokens"]
                    if usage.get("completion_tokens") is not None:
                        total_completion_tokens = usage["completion_tokens"]

                    token_usage = 0
                    if total_prompt_tokens > 0:
                        token_usage = total_prompt_tokens
                    elif total_completion_tokens > 0:
                        # API gave us no prompt count, fall back to what we have
                        token_usage = total_completion_tokens

                    if token_usage > 0:
                        yield {"type": "token_usage", "content": token_usage, "source": "API"}

                if chunk.get("timings") is not None:
                    yield {"type": "timings", "content": chunk["timings"]}

            if use_tools:
                for index in sorted(tool_call_buffer.keys()):
                    # filter out blank tool calls (rare model glitch)
                    tool_call = tool_call_buffer[index]
                    if not (tool_call.get("function") or {}).get("name"):
                        continue

                    final_tool_calls.append(tool_call)

                if final_tool_calls and core.config.get("model").get("use_tools", False):
                    # yield the full toolcall object as a single token to be interpreted by the function that is iterating through _recv_stream()
                    tool_call_dicts = [copy.deepcopy(tc) for tc in final_tool_calls]
                    yield {"type": "tool_calls", "tool_calls": tool_call_dicts}

        except Exception as e:
            raise e # Re-raise so send_stream can catch it and yield the error type

        finally:
            # release the connection back to the pool (or close it if the stream ended early)
            if hasattr(response, "close"):
                response.close()

        if not response_started:
            # this means the inference server (such as llamacpp) failed to report an error
            # for user friendliness, we just display a message that explains what happened
            raise Exception("The API returned a blank response. This likely means an error happened on the API end, but that API failed to report the error. Check your AI server's logs if you're using local AI, or if not, contact your cloud AI service. Also, try turning off `Use Developer Role` in the api settings, as some models don't support it.")

    async def list_models(self):
        if not self.connected:
            result = await self.attempt_connect()
            if result is not True:
                return result

        try:
            # get alphabetically sorted model list
            status, body = await self._http_get(f"{core.config.get('api', 'url')}/models")

            if status != 200:
                raise APIHTTPError(status, body)

            body = json.loads(body)

            model_list = [model["id"] for model in body.get("data", []) if isinstance(model, dict) and model.get("id")]
            model_list.sort()

        except Exception as e:
            self.manager.log_error("error while retrieving model list", e)
            return []

        return model_list
