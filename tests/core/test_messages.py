# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
core/messages.py: the Messages class (per-chat history).

integration level: real Chat + Messages on FakeChannel/FakeContext; disk
files land in the conftest tmp data dir.

intent under test:
- add() never mutates the caller's dict; it stamps _metadata (timestamp,
  ghost/is_cmd flags, module injections) and persists.
- the first plain user message auto-titles the chat (truncated at 100
  chars); media uploads must not become the title.
- module on_message_inject() output is joined into _metadata.injection and
  a failing module must not block the message.
- auto-compression fires for plain user messages only, when the context
  stub says we are over threshold.
- edit/delete/delete_from/get/get_last_message_with_role index semantics.
"""

import os
import time

import pytest

import core
from harness import apply_config


class InjectModule:
    def __init__(self, name, result=None, error=False):
        self.name = name
        self._result = result
        self._error = error

    async def on_message_inject(self, content):
        if self._error:
            raise RuntimeError("inject boom")
        return self._result


@pytest.fixture
async def chat(fake_channel):
    ch = core.chat.Chat(fake_channel)
    await ch.autoload()
    return ch


@pytest.fixture
def messages(chat):
    return chat.messages


def history_path(chat):
    return os.path.join(
        core.get_data_path(), "chats", "fake", "history", f"{chat.get('id')}.json"
    )


# ---------------------------------------------------------------------------
# add()
# ---------------------------------------------------------------------------

async def test_add_does_not_mutate_the_callers_dict(messages):
    original = {"role": "user", "content": "x"}

    await messages.add(original)

    assert original == {"role": "user", "content": "x"}


async def test_add_stamps_int_timestamp(messages):
    await messages.add({"role": "user", "content": "x"})

    msg = (await messages.get(0))
    assert isinstance(msg["_metadata"]["timestamp"], int)


async def test_add_sets_ghost_and_cmd_flags(messages):
    await messages.add({"role": "user", "content": "boo"}, ghost=True)
    await messages.add({"role": "assistant", "content": "cmd output"}, cmd=True)

    assert (await messages.get(0))["_metadata"]["ghost"] is True
    assert (await messages.get(1))["_metadata"]["is_cmd"] is True
    # flags must not leak between messages
    assert "ghost" not in (await messages.get(1))["_metadata"]


async def test_first_user_message_sets_title(chat, messages):
    await messages.add({"role": "user", "content": "plan my garden"})

    assert chat.get("title") == "plan my garden"


async def test_later_messages_do_not_rename_the_chat(chat, messages):
    await messages.add({"role": "user", "content": "first topic"})
    await messages.add({"role": "user", "content": "second topic"})

    assert chat.get("title") == "first topic"


async def test_long_first_message_title_is_truncated(chat, messages):
    long_text = "x" * 150

    await messages.add({"role": "user", "content": long_text})

    assert chat.get("title") == "x" * 100 + ".."


async def test_command_messages_never_title_the_chat(chat, messages):
    await messages.add({"role": "user", "content": "/help is cmd"}, cmd=True)

    assert chat.get("title") == "New chat"


@pytest.mark.xfail(
    strict=True,
    reason="suspected bug: the code comment says a media upload must not "
    "become the title, but _extract_content() returns '' (a str) for "
    "media-only content, so the title gets overwritten with the empty "
    "string instead of staying 'New chat' (TEST_PLAN.md section 5, finding 7)",
)
async def test_media_upload_leaves_title_alone(chat, messages):
    await messages.add(
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "x"}}]}
    )

    assert chat.get("title") == "New chat"


async def test_injections_from_modules_are_joined(chat, messages):
    chat.channel.manager.modules = {
        "a": InjectModule("a", result="first injection"),
        "quiet": InjectModule("quiet", result=None),
        "b": InjectModule("b", result="second injection"),
    }

    await messages.add({"role": "user", "content": "hello"})

    msg = await messages.get(0)
    assert msg["_metadata"]["injection"] == "first injection\n\nsecond injection"


async def test_failing_injection_is_logged_not_fatal(chat, messages):
    chat.channel.manager.modules = {"bad": InjectModule("bad", error=True)}

    await messages.add({"role": "user", "content": "hello"})

    assert len(await messages.get()) == 1
    assert any("on_message_inject" in msg for _cat, msg in chat.channel.logs)
    msg = await messages.get(0)
    assert "injection" not in msg["_metadata"]


async def test_injections_only_apply_to_user_messages(messages):
    messages.channel.manager.modules = {"a": InjectModule("a", result="stamp")}

    await messages.add({"role": "assistant", "content": "reply"})

    assert "injection" not in (await messages.get(0))["_metadata"]


async def test_compress_triggered_only_for_plain_user_messages(messages):
    messages.channel.context.over_threshold = True

    await messages.add({"role": "user", "content": "hi"})
    assert messages.channel.context.compress_calls == 1

    await messages.add({"role": "user", "content": "/cmd"}, cmd=True)
    await messages.add({"role": "assistant", "content": "reply"})
    assert messages.channel.context.compress_calls == 1


async def test_no_compress_when_under_threshold(messages):
    await messages.add({"role": "user", "content": "hi"})

    assert messages.channel.context.compress_calls == 0


async def test_add_persists_history_to_disk(chat, messages):
    await messages.add({"role": "user", "content": "durable"})

    reloaded = core.messages.Messages(chat.channel, chat)
    assert (await reloaded.get(0))["content"] == "durable"


# ---------------------------------------------------------------------------
# get / edit / delete
# ---------------------------------------------------------------------------

async def test_get_whole_history_or_indexed_message(messages):
    await messages.add({"role": "user", "content": "one"})
    await messages.add({"role": "assistant", "content": "two"})

    whole = await messages.get()
    assert [m["content"] for m in whole] == ["one", "two"]
    assert (await messages.get(1))["content"] == "two"

    with pytest.raises(Exception, match="Invalid message index"):
        await messages.get(99)


async def test_edit_replaces_and_persists(chat, messages):
    await messages.add({"role": "user", "content": "before"})

    assert await messages.edit(0, {"role": "user", "content": "after"}) is None
    assert (await messages.get(0))["content"] == "after"

    reloaded = core.messages.Messages(chat.channel, chat)
    assert (await reloaded.get(0))["content"] == "after"


async def test_edit_out_of_range_returns_false(messages):
    assert await messages.edit(5, {"role": "user", "content": "x"}) is False


async def test_delete_returns_new_last_index(messages):
    await messages.add({"role": "user", "content": "a"})
    await messages.add({"role": "assistant", "content": "b"})
    await messages.add({"role": "user", "content": "c"})

    assert await messages.delete(1) == 1
    assert [m["content"] for m in await messages.get()] == ["a", "c"]


async def test_delete_from_truncates_from_index_onward(chat, messages):
    for i in range(4):
        await messages.add({"role": "user", "content": f"m{i}"})

    assert await messages.delete_from(2) is True
    assert [m["content"] for m in await messages.get()] == ["m0", "m1"]

    reloaded = core.messages.Messages(chat.channel, chat)
    assert len(await reloaded.get()) == 2


async def test_delete_from_invalid_index_raises(messages):
    with pytest.raises(Exception, match="Invalid message index"):
        await messages.delete_from(3)


@pytest.mark.xfail(
    strict=True,
    reason="suspected bug: Messages.clear() empties the in-memory list but "
    "never calls save() (unlike edit/delete/delete_from), and Chat.clear() "
    "only saves the chat *index* - so a cleared chat comes back with its "
    "old history after a reload/restart (TEST_PLAN.md section 5, finding 8)",
)
async def test_clear_empties_history_persistently(chat, messages):
    await messages.add({"role": "user", "content": "gone soon"})

    await messages.clear()

    # a reload from disk must see the cleared history, otherwise /clear
    # only works until the app restarts
    reloaded = core.messages.Messages(chat.channel, chat)
    assert len(await reloaded.get()) == 0


# ---------------------------------------------------------------------------
# get_last_message_with_role
# ---------------------------------------------------------------------------

async def test_last_message_with_role_semantics(messages):
    assert await messages.get_last_message_with_role("user") == -1

    await messages.add({"role": "user", "content": "a"})
    assert await messages.get_last_message_with_role("user") == 0
    assert await messages.get_last_message_with_role("assistant") == -1

    await messages.add({"role": "assistant", "content": "b"})
    await messages.add({"role": "user", "content": "c"})
    await messages.add({"role": "assistant", "content": "d"})

    assert await messages.get_last_message_with_role("user") == 2
    assert await messages.get_last_message_with_role("assistant") == 3

    # cutoff: search backwards from that index
    assert await messages.get_last_message_with_role("user", cutoff_index=2) == 2
    # cutoff is clamped, not rejected
    assert await messages.get_last_message_with_role("user", cutoff_index=99) == 2
    # cutoff excludes newer matches
    assert await messages.get_last_message_with_role("assistant", cutoff_index=1) == 1
    assert await messages.get_last_message_with_role("assistant", cutoff_index=0) == -1


# ---------------------------------------------------------------------------
# misc
# ---------------------------------------------------------------------------

async def test_save_refreshes_chat_timestamp(chat, messages):
    chat.data[chat.current]["updated"] = "2000-01-01T00:00:00"
    chat.data.save()

    await messages.save()

    assert chat.data[chat.current]["updated"] > "2000-01-01T00:00:00"


async def test_messages_reject_non_string_chat_id(fake_channel, chat):
    chat.data[chat.current]["id"] = 12345

    with pytest.raises(Exception, match="Chat ID must be a string"):
        core.messages.Messages(fake_channel, chat)
