# AI Written: Claude Opus 5.5, reviewed by Claude Fable 5.2
import json
import os

import pytest

import core


def on_disk(chat):
    with open(chat.messages.data.path) as f:
        return json.load(f)


async def test_new_chat_becomes_current(channel):
    chat = channel.context.chat
    first = chat.get("id")
    second = await chat.new(category="work")

    assert second != first
    assert chat.get("id") == second
    assert chat.get("category") == "work"
    assert len(chat.data) == 2
    assert await chat.messages.get() == []


async def test_load_switches_chat(channel):
    chat = channel.context.chat
    first = chat.get("id")
    await chat.messages.add({"role": "user", "content": "in first"})
    await chat.new()

    assert await chat.load(first) is True
    assert chat.get("id") == first
    assert (await chat.messages.get())[0]["content"] == "in first"
    assert await chat.load(first) is False  # already loaded

    with pytest.raises(Exception, match="blank chat id"):
        await chat.load("nope")


async def test_chats_survive_restart(channel):
    chat = channel.context.chat
    await chat.messages.add({"role": "user", "content": "remember me"})
    other = await chat.new()
    await chat.messages.add({"role": "user", "content": "latest"})

    fresh = core.chat.Chat(channel)
    await fresh.autoload()

    assert len(fresh.data) == 2
    assert fresh.get("id") == other
    assert (await fresh.messages.get())[0]["content"] == "latest"


async def test_delete_current_chat(channel):
    chat = channel.context.chat
    first = chat.get("id")
    await chat.messages.add({"role": "user", "content": "bye"})
    history = chat.messages.data.path
    second = await chat.new()
    await chat.load(first)

    await chat.delete(first)

    assert not os.path.exists(history)
    assert [c["id"] for c in chat.data] == [second]
    assert chat.get("id") == second


async def test_delete_earlier_chat_keeps_current(channel):
    chat = channel.context.chat
    first = chat.get("id")
    second = await chat.new()

    await chat.delete(first)
    assert chat.get("id") == second
    assert await chat.delete("missing") is False


async def test_deleting_last_chat_creates_a_new_one(channel):
    chat = channel.context.chat
    only = chat.get("id")

    await chat.delete(only)

    assert len(chat.data) == 1
    assert chat.get("id") != only


async def test_message_changes_are_persisted(channel):
    chat = channel.context.chat
    for text in ["one", "two", "three", "four"]:
        await chat.messages.add({"role": "user", "content": text})

    await chat.messages.edit(1, {"role": "user", "content": "TWO"})
    await chat.messages.delete(0)
    assert [m["content"] for m in on_disk(chat)] == ["TWO", "three", "four"]

    await chat.messages.delete_from(1)
    assert [m["content"] for m in on_disk(chat)] == ["TWO"]

    with pytest.raises(Exception, match="Invalid message index"):
        await chat.messages.delete_from(5)


async def test_add_stores_metadata_without_touching_input(channel):
    messages = channel.context.chat.messages
    original = {"role": "user", "content": "hi"}

    await messages.add(original, cmd=True, ghost=True)

    assert original == {"role": "user", "content": "hi"}
    meta = (await messages.get(0))["_metadata"]
    assert meta["is_cmd"] and meta["ghost"]
    assert isinstance(meta["timestamp"], int)


async def test_first_user_message_sets_title(channel):
    chat = channel.context.chat
    await chat.messages.add({"role": "assistant", "content": "welcome"})
    assert chat.get("title") == "New chat"

    await chat.messages.add({"role": "user", "content": [{"type": "text", "text": "plan a trip"}]})
    await chat.messages.add({"role": "user", "content": "something else"})
    assert chat.get("title") == "plan a trip"


async def test_long_title_is_truncated(channel):
    chat = channel.context.chat
    await chat.messages.add({"role": "user", "content": "x" * 150})
    assert chat.get("title") == "x" * 100 + ".."


async def test_commands_do_not_set_title(channel):
    chat = channel.context.chat
    await chat.messages.add({"role": "user", "content": "/help"}, cmd=True)
    assert chat.get("title") == "New chat"


async def test_last_message_with_role(channel):
    messages = channel.context.chat.messages
    assert await messages.get_last_message_with_role("user") == -1

    for role in ["user", "assistant", "user", "assistant"]:
        await messages.add({"role": role, "content": "x"})

    assert await messages.get_last_message_with_role("user") == 2
    assert await messages.get_last_message_with_role("user", cutoff_index=1) == 0
    assert await messages.get_last_message_with_role("user", cutoff_index=99) == 2
    assert await messages.get_last_message_with_role("tool") == -1
