# AI Written: Claude Opus 5.5, reviewed by Claude Fable 5.2
import asyncio
from types import SimpleNamespace

import pytest

import core


async def history(channel):
    return [(m["role"], m["content"]) for m in await channel.context.chat.messages.get()]


async def test_send_stores_user_and_assistant(channel, manager):
    manager.API.replies.append({"role": "assistant", "content": "hi there"})

    reply = await channel.send("hello")

    assert reply["content"] == "hi there"
    assert manager.API.sent[0]["context"][-1] == {"role": "user", "content": "hello"}
    assert await history(channel) == [("user", "hello"), ("assistant", "hi there")]


@pytest.mark.parametrize("message, authorized, expected", [
    ("/ping", True, "pong"),
    ("/ping", False, "not authorized"),
])
async def test_commands_skip_the_api(channel, manager, message, authorized, expected):
    reply = await channel.send(message, commands_authorized=authorized)
    assert expected in reply["content"]
    assert manager.API.sent == []


def hook(fn, is_async):
    if not is_async:
        return SimpleNamespace(on_user_message=fn)

    async def on_user_message(message):
        return fn(message)
    return SimpleNamespace(on_user_message=on_user_message)


@pytest.mark.parametrize("is_async", [False, True])
async def test_user_message_hook_can_rewrite(channel, manager, is_async):
    manager.modules["shout"] = hook(str.upper, is_async)
    manager.API.replies.append({"role": "assistant", "content": "ok"})

    await channel.send("hello")

    assert manager.API.sent[0]["context"][-1]["content"] == "HELLO"
    assert (await history(channel))[0] == ("user", "HELLO")


async def test_user_message_hook_can_intercept(channel, manager):
    manager.modules["eater"] = hook(lambda message: False, is_async=False)

    assert await channel.send("hello") is None
    assert manager.API.sent == []
    assert await history(channel) == [("user", "hello")]


async def test_assistant_message_hook_sees_reply(channel, manager):
    seen = []
    manager.modules["spy"] = SimpleNamespace(on_assistant_message=seen.append)
    manager.API.replies.append({"role": "assistant", "content": "hi"})

    await channel.send("hello")
    assert seen == ["hi"]


async def test_api_error_becomes_assistant_message(channel, manager):
    async def fail(context, **kwargs):
        raise core.api.APIError("Rate limit exceeded")
    manager.API.send = fail

    reply = await channel.send("hello")
    assert reply == {"role": "assistant", "content": "Rate limit exceeded"}


async def test_connect_failure_skips_the_request(channel, manager):
    async def fail():
        raise core.api.APIError("Failed to connect to the API")
    manager.API.attempt_connect = fail

    reply = await channel.send("hello")
    assert "Failed to connect" in reply["content"]
    assert manager.API.sent == []


async def test_stream_assembles_final_message(channel, manager):
    manager.API.replies.append([
        {"type": "reasoning", "content": "let me "},
        {"type": "reasoning", "content": "think"},
        {"type": "content", "content": "Hel"},
        {"type": "content", "content": "lo"},
    ])

    tokens = [t async for t in channel.send_stream("hi")]

    assert tokens[0] == {"type": "user_message", "content": "hi"}
    assert tokens[-1]["type"] == "token_usage"
    last = (await channel.context.chat.messages.get())[-1]
    assert (last["role"], last["content"], last["reasoning_content"]) == ("assistant", "Hello", "let me think")


async def test_stream_error_keeps_partial_reply(channel, manager):
    manager.API.replies.append([
        {"type": "content", "content": "partial"},
        {"type": "error", "content": "connection lost"},
    ])

    tokens = [t async for t in channel.send_stream("hi")]

    assert tokens[-1] == {"type": "error", "content": "connection lost"}
    assert (await history(channel))[1:] == [("assistant", "partial"), ("assistant", "Error: connection lost")]


async def test_stream_command_yields_reply_without_api(channel, manager):
    tokens = [t async for t in channel.send_stream("/ping", commands_authorized=True)]
    assert [t["type"] for t in tokens] == ["user_message", "content"]
    assert "pong" in tokens[1]["content"]
    assert manager.API.sent == []


async def test_deferred_push_lands_after_the_reply(channel, manager):
    await channel._start_push_queue()
    send = manager.API.send

    async def send_and_push(context, **kwargs):
        # a module pushing mid-turn, e.g. from a tool
        await channel.push("deferred note")
        await channel.push("immediate note", defer=False)
        await asyncio.sleep(0.01)
        return await send(context, **kwargs)
    manager.API.send = send_and_push
    manager.API.replies.append({"role": "assistant", "content": "reply"})

    await channel.send("hello")
    await asyncio.wait_for(channel.push_queue.join(), timeout=1)

    assert await history(channel) == [
        ("user", "hello"),
        ("assistant", "immediate note"),
        ("assistant", "reply"),
        ("assistant", "deferred note"),
    ]
    assert sorted(m["content"] for m in channel.pushed) == ["deferred note", "immediate note"]
