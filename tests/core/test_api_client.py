# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
core/api.py APIClient against a real local aiohttp server.

no network beyond 127.0.0.1; every test gets a fresh scripted server on a
random port and a fresh APIClient whose config points at it.

intent under test (TEST_PLAN.md Tier 3):
- connect() validates with a cheap GET /models probe, falling back to a
  minimal chat-completions probe on servers without /models (dev 7cc1f7b);
  HTTP statuses map to friendly APIErrors, connection state only flips on
  success.
- _request() builds the exact payload contract (max_completion_tokens,
  chat_template_kwargs.enable_thinking, return_progress, stream_options
  on streams, reasoning_effort omitted when falsy/none, custom_fields
  merged last-wins, tools gated by config) and refuses blank contexts
  without touching the network.
- retry loop: MAX_API_ATTEMPTS=3 with linear backoff for retryable
  failures, immediate raise for non-retryable ones, errors are RETURNED
  as APIError, never raised.
- _recv / _recv_stream: message extraction, role forcing, SSE content/
  reasoning deltas, streamed tool-call assembly, in-band error chunks,
  usage chunks surfaced as token_usage, blank-stream detection.
- cancel(): aborts mid-stream, safe no-op when idle.
"""

import asyncio
import json

import aiohttp

import pytest
from aiohttp import web

import core
from harness import apply_config, sse_encode


# ---------------------------------------------------------------------------
# scripted local API server
# ---------------------------------------------------------------------------

class ScriptedServer:
    def __init__(self):
        self.base_url = None
        self.requests = []  # {method, path, headers, json}
        self._script = []   # queued (status, body_bytes, content_type)
        self._path_scripts = {}  # exact path -> list of queued responses

    def queue(self, status=200, body=b"", content_type="application/json"):
        self._script.append((status, body, content_type))

    def queue_json(self, payload, status=200):
        self.queue(status, json.dumps(payload).encode())

    def queue_sse(self, events, status=200):
        self.queue(status, sse_encode(events), "text/event-stream")

    def queue_handler(self, handler):
        """queue an arbitrary coroutine handler(request) -> Response"""
        self._script.append(handler)

    def queue_for(self, path, status=200, body=b"", content_type="application/json"):
        """queue a response reserved for one exact path (checked first)"""
        self._path_scripts.setdefault(path, []).append(
            (status, body, content_type)
        )

    def queue_json_for(self, path, payload, status=200):
        self.queue_for(path, status, json.dumps(payload).encode())

    def chat_calls(self, exclude_probe=True):
        """recorded POSTs to chat/completions, minus the connect probe"""
        calls = [
            r for r in self.requests
            if r["method"] == "POST" and r["path"].endswith("/chat/completions")
        ]
        if exclude_probe:
            calls = [
                r for r in calls
                if not (
                    r["json"]
                    and r["json"].get("messages", [{}])[0].get("content") == "ping"
                )
            ]
        return calls

    async def handle(self, request):
        raw = await request.text()
        try:
            parsed = json.loads(raw) if raw else None
        except ValueError:
            parsed = None
        self.requests.append(
            {"method": request.method, "path": request.path,
             "headers": dict(request.headers), "json": parsed}
        )

        if self._path_scripts.get(request.path):
            status, body, ctype = self._path_scripts[request.path].pop(0)
            return web.Response(status=status, body=body, content_type=ctype)

        if not self._script:
            return web.Response(
                status=200,
                body=json.dumps(
                    {"choices": [{"message": {"role": "assistant", "content": "ok"}}]}
                ).encode(),
                content_type="application/json",
            )

        entry = self._script.pop(0)
        if callable(entry):
            return await entry(request)
        status, body, ctype = entry
        return web.Response(status=status, body=body, content_type=ctype)


@pytest.fixture
async def api_server():
    server = ScriptedServer()
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", server.handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="127.0.0.1", port=0)
    await site.start()
    port = runner.addresses[0][1]
    server.base_url = f"http://127.0.0.1:{port}/v1"
    yield server
    await runner.cleanup()


def configure_api(server, api=None, model=None):
    cfg_api = {"url": server.base_url, "max_context": 16768, "max_output_tokens": 512}
    cfg_model = {"name": "test-model", "use_tools": True, "temperature": 0.5}
    cfg_api.update(api or {})
    cfg_model.update(model or {})
    apply_config(api=cfg_api, model=cfg_model, modules={"disabled_prompts": []})


@pytest.fixture
async def client(fake_manager, api_server):
    configure_api(api_server)
    api = core.api.APIClient(fake_manager)
    yield api
    await api.disconnect()


@pytest.fixture
async def live_client(client):
    """
    pre-connected client: the connect probe already consumed the server's
    default response in the fixture, so anything a test queues maps 1:1 to
    the request(s) it makes itself.
    """
    assert await client.connect() is True
    return client


async def drain(gen):
    return [token async for token in gen]


# ---------------------------------------------------------------------------
# connect
# ---------------------------------------------------------------------------

async def test_connect_primary_probe_is_get_models(fake_manager, api_server):
    configure_api(api_server, api={"key": "secret", "use_developer_role": True})
    api = core.api.APIClient(fake_manager)

    assert await api.connect() is True
    assert api.connected is True
    assert api.supports_developer_role is True

    # dev 7cc1f7b: startup validates with a cheap GET /models instead of a
    # chat-completions round trip (that made llama.cpp load the model just to
    # check connectivity)
    probe = api_server.requests[0]
    assert probe["method"] == "GET"
    assert probe["path"] == "/v1/models"
    assert probe["headers"]["Authorization"] == "Bearer secret"
    # /models answered: the chat-completions fallback probe must not run
    assert api_server.chat_calls(exclude_probe=False) == []


async def test_connect_falls_back_to_chat_probe_without_models_endpoint(fake_manager, api_server):
    configure_api(api_server, api={"key": "secret"})
    api_server.queue_for("/v1/models", 404, b"no route")
    api = core.api.APIClient(fake_manager)

    # default handler accepts the fallback POST with a plain completion
    assert await api.connect() is True

    probe = api_server.chat_calls(exclude_probe=False)[0]
    assert probe["json"]["messages"] == [{"role": "user", "content": "ping"}]
    assert probe["json"]["max_completion_tokens"] == 1
    assert probe["json"]["model"] == "test-model"
    assert probe["headers"]["Authorization"] == "Bearer secret"


async def test_connect_http_error_mapping(fake_manager, api_server):
    # (GET /models reply, chat-probe fallback reply or None, expected error)
    cases = [
        ((401, b"nope"), None, "Authentication failed"),
        ((403, b"nope"), None, "Authentication failed"),
        # a hard error on /models is final: no fallback attempt
        ((500, b""), None, "Failed to connect to the API"),
        ((404, b"no route"), (400, b"model 'x' not found"), "Model not found."),
        ((404, b"no route"), (404, b"model 'x' is missing"), "Model not found."),
        ((404, b"no route"), (404, b"still no route"), "Unknown error"),
        ((405, b""), (405, b""), "does not look like a chat-completions API"),
        ((405, b""), (401, b"nope"), "Authentication failed"),
        ((405, b""), (500, b""), "Failed to connect to the API"),
    ]
    for models_reply, fallback, expected in cases:
        configure_api(api_server)
        api_server.queue_for("/v1/models", *models_reply)
        if fallback is not None:
            api_server.queue(*fallback)
        api = core.api.APIClient(fake_manager)
        result = await api.connect()
        assert isinstance(result, core.api.APIError), (models_reply, fallback)
        assert expected in str(result), (models_reply, fallback)
        assert api.connected is False
        await api.disconnect()


async def test_connect_accepts_chat_probe_400_without_model_complaint(client, api_server):
    # a server without /models that rejects the ping for a benign reason
    # (bad temperature and the like) is still a live chat-completions API
    api_server.queue_for("/v1/models", 404, b"no route")
    api_server.queue(400, b"temperature out of range")

    result = await client.connect()

    assert result is True


async def test_connect_placeholder_url_short_circuits(fake_manager, api_server):
    configure_api(api_server, api={"url": "http://API_URL_HERE/v1"})
    api = core.api.APIClient(fake_manager)

    result = await api.connect()

    assert isinstance(result, core.api.APIError)
    assert "not been set up" in str(result)
    assert api_server.requests == []  # never touched the network


async def test_connect_refused_connection(fake_manager, api_server):
    configure_api(api_server, api={"url": "http://127.0.0.1:9/v1"})
    api = core.api.APIClient(fake_manager)

    result = await api.connect()

    assert isinstance(result, core.api.APIError)
    assert "Failed to connect" in str(result)


async def test_router_detection(fake_manager, api_server, client):
    # router mode: /models entries carry a status field
    api_server.queue_json_for("/models", {"data": [{"id": "m", "status": "loading"}]})
    await client.connect()
    assert client._router_origin == api_server.base_url.removesuffix("/v1")

    # plain openai server: no status fields
    configure_api(api_server)
    api_server.queue_json_for("/models", {"data": [{"id": "m"}]})
    api2 = core.api.APIClient(fake_manager)
    await api2.connect()
    assert api2._router_origin is None


# ---------------------------------------------------------------------------
# _request payload contract
# ---------------------------------------------------------------------------

async def test_request_payload_fields(fake_manager, api_server, live_client):
    api_server.queue_json({"choices": [{"message": {"content": "pong"}}]})

    await live_client.send(
        [{"role": "user", "content": "hello"}],
        tools=[{"function": {"name": "demo"}}],
    )

    payload = api_server.chat_calls()[-1]["json"]
    assert payload["model"] == "test-model"
    assert payload["messages"] == [{"role": "user", "content": "hello"}]
    assert payload["stream"] is False
    assert payload["temperature"] == 0.5
    assert payload["max_completion_tokens"] == 512
    assert payload["chat_template_kwargs"] == {"enable_thinking": True}
    assert payload["return_progress"] is True
    assert payload["tools"] == [{"function": {"name": "demo"}}]
    assert "stream_options" not in payload


async def test_tools_gated_by_model_config(fake_manager, api_server, live_client):
    configure_api(api_server, model={"name": "t", "use_tools": False})

    await live_client.send(
        [{"role": "user", "content": "x"}],
        tools=[{"function": {"name": "demo"}}],
    )

    assert "tools" not in api_server.chat_calls()[-1]["json"]


async def test_reasoning_effort_omitted_when_falsy_or_none(fake_manager, api_server, live_client):
    for effort, present in (("high", True), ("none", False), ("", False)):
        configure_api(api_server, model={"name": "t", "use_tools": True,
                                         "reasoning_effort": effort})
        api_server.queue_json({"choices": [{"message": {"content": "x"}}]})

        await live_client.send([{"role": "user", "content": "x"}])

        payload = api_server.chat_calls()[-1]["json"]
        assert ("reasoning_effort" in payload) is present, effort


async def test_custom_fields_merge_last_wins(fake_manager, api_server, live_client):
    configure_api(api_server, api={
        "url": api_server.base_url, "max_context": 16768,
        "custom_fields": {"temperature": 0.9, "user": "u1"},
    })

    await live_client.send([{"role": "user", "content": "x"}])

    payload = api_server.chat_calls()[-1]["json"]
    assert payload["temperature"] == 0.9  # overrides the model setting
    assert payload["user"] == "u1"


async def test_stream_requests_usage_and_passes_kwargs(fake_manager, api_server, live_client):
    api_server.queue_sse([{"choices": [{"delta": {"content": "hi"}}]}])

    await drain(live_client.send_stream(
        [{"role": "user", "content": "x"}], foo="bar", use_thinking=False,
    ))

    payload = api_server.chat_calls()[-1]["json"]
    assert payload["stream"] is True
    assert payload["stream_options"] == {"include_usage": True}
    assert payload["foo"] == "bar"  # kwargs passthrough
    assert "use_thinking" not in payload  # internal kwarg excluded
    assert payload["chat_template_kwargs"] == {"enable_thinking": False}


async def test_blank_context_never_hits_the_network(client, api_server):
    # _request is the layer that guards blank contexts: no network at all
    result = await client._request([])

    assert isinstance(result, core.api.APIError)
    assert "blank request" in str(result)
    assert api_server.requests == []

    # through send(), the guard still surfaces as an APIError
    result = await client.send([])
    assert isinstance(result, core.api.APIError)
    assert "blank request" in str(result)


# ---------------------------------------------------------------------------
# retries
# ---------------------------------------------------------------------------

async def test_retryable_failures_retried_with_linear_backoff(fake_manager, api_server, live_client):
    api_server.queue(503, b"busy")
    api_server.queue(500, b"bad")
    api_server.queue_json({"choices": [{"message": {"content": "finally"}}]})
    live_client.RETRY_BASE_DELAY = 0.05  # keep the test fast; delays still logged

    result = await live_client.send([{"role": "user", "content": "x"}])

    assert result["content"] == "finally"
    assert len(api_server.chat_calls()) == 3
    retry_logs = [msg for cat, msg in fake_manager.logs if "retrying" in msg]
    assert len(retry_logs) == 2
    assert "attempt 2/3" in retry_logs[0] and "attempt 3/3" in retry_logs[1]


async def test_retry_exhaustion_returns_error_not_exception(fake_manager, api_server, live_client):
    for _ in range(5):
        api_server.queue(503, b"still busy")
    live_client.RETRY_BASE_DELAY = 0.05

    result = await live_client.send([{"role": "user", "content": "x"}])

    assert isinstance(result, core.api.APIError)
    assert "API Status Error" in str(result)
    assert len(api_server.chat_calls()) == core.api.APIClient.MAX_API_ATTEMPTS


async def test_non_retryable_raises_immediately(fake_manager, api_server, live_client):
    api_server.queue(400, b"bad request nonsense")

    result = await live_client.send([{"role": "user", "content": "x"}])

    assert isinstance(result, core.api.APIError)
    assert "Bad request" in str(result)
    assert len(api_server.chat_calls()) == 1


def test_is_retryable_error_matrix(live_client):
    ok = core.api.APIHTTPError
    assert live_client._is_retryable_error(ok(503)) is True
    assert live_client._is_retryable_error(ok(400)) is False
    assert live_client._is_retryable_error(
        aiohttp.ClientSSLError(None, OSError(22, "ssl"))
    ) is False
    assert live_client._is_retryable_error(aiohttp.ClientConnectionError()) is True
    assert live_client._is_retryable_error(asyncio.TimeoutError()) is True
    assert live_client._is_retryable_error(ValueError("?")) is False


# ---------------------------------------------------------------------------
# send() response mapping
# ---------------------------------------------------------------------------

async def test_send_extracts_message_and_forces_role(fake_manager, api_server, live_client):
    api_server.queue_json({"choices": [{"message": {
        "role": "assistant", "content": "pong", "reasoning": "hmm",
    }}]})

    result = await live_client.send([{"role": "user", "content": "ping"}])

    assert result == {"content": "pong", "reasoning_content": "hmm",
                      "role": "assistant"}


async def test_send_malformed_body_returns_apierror(fake_manager, api_server, live_client):
    api_server.queue_json({"nonsense": True})

    result = await live_client.send([{"role": "user", "content": "x"}])

    assert isinstance(result, core.api.APIError)
    assert "While processing response" in str(result)


async def test_send_tool_calls_extracted_only_when_enabled(fake_manager, api_server, live_client):
    body = {"choices": [{"message": {
        "role": "assistant", "content": None,
        "tool_calls": [{"id": "1", "function": {"name": "x", "arguments": "{}"}}],
    }}]}
    api_server.queue_json(body)
    result = await live_client.send([{"role": "user", "content": "x"}])
    assert result["tool_calls"] == body["choices"][0]["message"]["tool_calls"]

    configure_api(api_server, model={"name": "t", "use_tools": False})
    api_server.queue_json(body)
    result = await live_client.send([{"role": "user", "content": "x"}])
    assert "tool_calls" not in result


# ---------------------------------------------------------------------------
# streaming
# ---------------------------------------------------------------------------

async def test_stream_content_and_usage_tokens(fake_manager, api_server, live_client):
    api_server.queue_sse([
        {"choices": [{"delta": {"content": "he"}}]},
        {"choices": [{"delta": {"reasoning_content": "think"}}]},
        {"choices": [{"delta": {"content": "llo"}}]},
        {"usage": {"prompt_tokens": 42, "completion_tokens": 7}},
    ])

    tokens = await drain(live_client.send_stream([{"role": "user", "content": "x"}]))

    kinds = [(t["type"], t.get("content")) for t in tokens]
    assert ("content", "he") in kinds
    assert ("reasoning", "think") in kinds
    assert ("content", "llo") in kinds
    assert ("token_usage", 42) in kinds
    assert tokens[-1]["source"] == "API"


async def test_stream_inband_error_stops_stream(fake_manager, api_server, live_client):
    api_server.queue_sse([
        {"error": {"message": "overloaded"}},
        {"choices": [{"delta": {"content": "never seen"}}]},
    ])

    tokens = await drain(live_client.send_stream([{"role": "user", "content": "x"}]))

    assert tokens == [{"type": "error", "content": "overloaded"}]


async def test_stream_blank_response_surfaces_error(fake_manager, api_server, live_client):
    api_server.queue_sse([])  # 200, no events at all

    tokens = await drain(live_client.send_stream([{"role": "user", "content": "x"}]))

    assert len(tokens) == 1
    assert tokens[0]["type"] == "error"
    assert "blank response" in tokens[0]["content"]


async def test_stream_tool_call_arguments_assembled_across_chunks(fake_manager, api_server, live_client):
    api_server.queue_sse([
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "id": "call_9",
            "function": {"name": "demo_echo", "arguments": ""},
        }]}}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "function": {"arguments": '{"msg": '},
        }]}}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "function": {"arguments": '"hi"}'},
        }]}}]},
    ])

    tokens = await drain(live_client.send_stream([{"role": "user", "content": "x"}]))

    final = [t for t in tokens if t["type"] == "tool_calls"]
    assert len(final) == 1
    tc = final[0]["tool_calls"][0]
    assert tc["id"] == "call_9"
    assert tc["function"]["name"] == "demo_echo"
    assert tc["function"]["arguments"] == '{"msg": "hi"}'
    # deltas were streamed along the way
    assert any(t["type"] == "tool_call_delta" for t in tokens)


async def test_cancel_mid_stream_severs_connection(fake_manager, api_server, live_client):
    async def slow_stream(request):
        resp = web.StreamResponse(
            status=200, headers={"Content-Type": "text/event-stream"}
        )
        await resp.prepare(request)
        await resp.write(sse_encode(
            [{"choices": [{"delta": {"content": "first"}}]}]
        ))
        try:
            # hold the stream open with SSE keepalives (parser-ignored
            # comments); writing to the closed transport ends the handler
            for _ in range(600):
                await asyncio.sleep(0.05)
                await resp.write(b": keepalive\n\n")
        except (asyncio.CancelledError, ConnectionResetError, Exception):
            pass
        return resp

    api_server.queue_handler(slow_stream)
    tokens, cancelled = [], False

    async def consume():
        nonlocal cancelled
        try:
            async for token in live_client.send_stream([{"role": "user", "content": "x"}]):
                tokens.append(token)
        except asyncio.CancelledError:
            cancelled = True

    consumer = asyncio.create_task(consume())
    while not tokens:
        await asyncio.sleep(0.01)

    assert await live_client.cancel() is True
    await asyncio.wait_for(consumer, timeout=5)

    assert cancelled is True
    assert tokens[0]["content"] == "first"
    assert live_client.cancel_request is False


async def test_cancel_when_idle_is_a_noop(client):
    assert await client.cancel() is False
    assert client.cancel_request is False


# ---------------------------------------------------------------------------
# list_models
# ---------------------------------------------------------------------------

async def test_list_models_sorted(fake_manager, api_server, live_client):
    api_server.queue_json({"data": [{"id": "beta"}, {"id": "alpha"}]})

    models = await live_client.list_models()

    assert models == ["alpha", "beta"]


async def test_list_models_failure_returns_empty(fake_manager, api_server, live_client):
    api_server.queue(500, b"boom")

    assert await live_client.list_models() == []
    assert fake_manager.errors, "failure must be logged"
