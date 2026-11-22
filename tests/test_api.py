# AI Written: Claude Opus 5.5, reviewed by Claude Fable 5.2
"""APIClient against a real local HTTP server on 127.0.0.1."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from aiohttp import web

import core
from core.api import APIError

USER = [{"role": "user", "content": "hi"}]
TOOL = {"type": "function", "function": {"name": "demo_echo", "parameters": {}}}


def sse(*events):
    body = "".join(f"data: {json.dumps(e)}\n\n" for e in events) + "data: [DONE]\n\n"
    return web.Response(body=body.encode(), content_type="text/event-stream")


def delta(**fields):
    return {"choices": [{"delta": fields}]}


class Server:
    """answers GET /models, and POSTs from a queue of responses (or handlers)"""

    def __init__(self):
        self.posts = []
        self.replies = []

    async def handle(self, request):
        if request.method == "GET":
            return web.json_response({"data": []})
        self.posts.append({"json": await request.json(), "headers": dict(request.headers)})
        reply = self.replies.pop(0) if self.replies else web.json_response({"choices": [{"message": {"content": "ok"}}]})
        return await reply(request) if callable(reply) else reply


@pytest.fixture
async def server(set_config):
    srv = Server()
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", srv.handle)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "127.0.0.1", 0).start()
    port = runner.addresses[0][1]
    set_config(api={"url": f"http://127.0.0.1:{port}/v1"}, model={"name": "test-model", "use_tools": True})
    yield srv
    await runner.cleanup()


@pytest.fixture
async def client(manager, server):
    manager.args = SimpleNamespace(insecure_tls=False)
    api = core.api.APIClient(manager)
    api.RETRY_BASE_DELAY = 0
    yield api
    await api.disconnect()


async def drain(gen):
    return [token async for token in gen]


async def test_connect_applies_key_and_developer_role(client, server, set_config):
    set_config(api={"key": "secret", "use_developer_role": True})
    assert await client.connect() is True
    assert client.supports_developer_role is True

    await client.send(USER)
    assert server.posts[0]["headers"]["Authorization"] == "Bearer secret"


async def test_placeholder_url_is_an_error(client, set_config):
    set_config(api={"url": "http://API_URL_HERE/v1"})
    with pytest.raises(APIError, match="not been set up"):
        await client.connect()


@pytest.mark.parametrize("use_tools", [True, False])
async def test_request_payload(client, server, set_config, use_tools):
    set_config(model={"use_tools": use_tools}, api={"custom_fields": {"top_k": 5}})
    await client.send(USER, tools=[TOOL])

    payload = server.posts[0]["json"]
    assert payload["model"] == "test-model"
    assert payload["messages"] == USER
    assert payload["stream"] is False
    assert payload["top_k"] == 5
    assert ("tools" in payload) is use_tools


async def test_send_returns_assistant_message(client, server):
    tool_call = {"id": "c1", "type": "function", "function": {"name": "demo_echo", "arguments": "{}"}}
    server.replies.append(web.json_response({"choices": [{"message": {
        "content": "hello", "reasoning_content": "thinking", "tool_calls": [tool_call],
    }}]}))

    result = await client.send(USER)
    assert result == {"role": "assistant", "content": "hello", "reasoning_content": "thinking", "tool_calls": [tool_call]}


@pytest.mark.parametrize("status, body, expected", [
    (401, "nope", "Authentication failed"),
    (403, "nope", "Authentication failed"),
    (404, "", "does not exist"),
    (400, "model 'x' not found", "does not exist"),
    (400, "bad field", "Bad request"),
])
async def test_http_errors_become_api_errors(client, server, status, body, expected):
    server.replies.append(web.Response(status=status, text=body))
    with pytest.raises(APIError, match=expected):
        await client.send(USER)
    assert len(server.posts) == 1  # not retried


async def test_server_errors_are_retried(client, server):
    server.replies += [web.Response(status=503), web.Response(status=502)]
    result = await client.send(USER)
    assert result["content"] == "ok"
    assert len(server.posts) == 3


async def test_retries_give_up_with_an_error(client, server):
    server.replies += [web.Response(status=503) for _ in range(3)]
    with pytest.raises(APIError, match="HTTP 503"):
        await client.send(USER)
    assert len(server.posts) == 3


async def test_stream_tokens(client, server):
    server.replies.append(sse(
        delta(reasoning_content="hmm"),
        delta(content="Hel"),
        delta(content="lo"),
        delta(tool_calls=[{"index": 0, "id": "c1", "function": {"name": "demo_echo"}}]),
        delta(tool_calls=[{"index": 0, "function": {"arguments": '{"msg": '}}]),
        delta(tool_calls=[{"index": 0, "function": {"arguments": '"hi"}'}}]),
        {"choices": [], "usage": {"prompt_tokens": 42, "completion_tokens": 3}},
    ))
    tokens = await drain(client.send_stream(USER, tools=[TOOL]))

    assert server.posts[0]["json"]["stream"] is True
    assert [t["content"] for t in tokens if t["type"] == "reasoning"] == ["hmm"]
    assert "".join(t["content"] for t in tokens if t["type"] == "content") == "Hello"
    assert {"type": "token_usage", "content": 42, "source": "API"} in tokens

    final = [t for t in tokens if t["type"] == "tool_calls"]
    assert len(final) == 1
    call = final[0]["tool_calls"][0]
    assert (call["id"], call["function"]["name"], call["function"]["arguments"]) == ("c1", "demo_echo", '{"msg": "hi"}')


async def test_stream_tool_calls_dropped_when_tools_disabled(client, server, set_config):
    set_config(model={"use_tools": False})
    server.replies.append(sse(delta(tool_calls=[{"index": 0, "id": "c1", "function": {"name": "demo_echo", "arguments": "{}"}}])))
    tokens = await drain(client.send_stream(USER))
    assert not any(t["type"] == "tool_calls" for t in tokens)


@pytest.mark.parametrize("reply", [
    lambda: sse(delta(content="par"), {"error": {"message": "out of memory"}}),
    lambda: web.Response(status=401, text="nope"),
    lambda: web.Response(body=b"", content_type="text/event-stream"),  # blank stream
])
async def test_stream_errors_become_error_tokens(client, server, reply):
    server.replies.append(reply())
    tokens = await drain(client.send_stream(USER))
    assert tokens[-1]["type"] == "error"


async def test_cancel_mid_stream(client, server):
    async def endless(request):
        resp = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await resp.prepare(request)
        await resp.write(f"data: {json.dumps(delta(content='first'))}\n\n".encode())
        try:
            for _ in range(100):
                await asyncio.sleep(0.02)
                await resp.write(b": keepalive\n\n")
        except Exception:
            pass
        return resp

    server.replies.append(endless)
    tokens = []

    async def consume():
        async for token in client.send_stream(USER):
            tokens.append(token)

    consumer = asyncio.create_task(consume())
    for _ in range(100):
        if tokens:
            break
        await asyncio.sleep(0.01)
    assert tokens

    assert await client.cancel() is True
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(consumer, timeout=1)
    assert client.cancel_request is False

    # the client is still usable afterwards
    assert (await client.send(USER))["content"] == "ok"


async def test_cancel_when_idle_is_a_noop(client):
    assert await client.cancel() is False
    assert client.cancel_request is False
