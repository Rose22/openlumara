# AI Written: Claude Opus 5.5, reviewed by Claude Fable 5.2
import pytest


def history(channel, *messages):
    """put raw messages straight into the current chat's history"""
    channel.context.chat.messages.data.extend(messages)


def call(id):
    return {"id": id, "type": "function", "function": {"name": "time_now", "arguments": "{}"}}


async def test_only_api_fields_are_sent(channel):
    history(
        channel,
        {"role": "user", "content": "hi", "_metadata": {"timestamp": 1}, "old_style_field": True},
        {"role": "assistant", "content": None, "tool_calls": [{**call("c1"), "_metadata": {"shown": True}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "12:00"},
    )

    assert await channel.context.get() == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "tool_calls": [call("c1")]},
        {"role": "tool", "tool_call_id": "c1", "content": "12:00"},
    ]


async def test_empty_assistant_messages_are_dropped(channel):
    history(
        channel,
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": ""},
        {"role": "assistant", "content": None},
        {"role": "assistant", "content": "hello"},
    )

    assert await channel.context.get() == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


async def test_ghost_messages_are_hidden(channel):
    messages = channel.context.chat.messages
    await messages.add({"role": "user", "content": "visible"})
    await messages.add({"role": "assistant", "content": "secret"}, ghost=True)

    assert await channel.context.get() == [{"role": "user", "content": "visible"}]


async def test_module_injections_are_appended_to_user_messages(channel, manager):
    class Clock:
        name = "clock"

        async def on_message_inject(self, content):
            return "[time: 12:00]"

    manager.modules["clock"] = Clock()
    await channel.context.chat.messages.add({"role": "user", "content": "what time is it?"})
    await channel.context.chat.messages.add({"role": "assistant", "content": "noon"})

    context = await channel.context.get()
    assert context[0]["content"] == "what time is it?\n\n[time: 12:00]"
    assert context[1]["content"] == "noon"
    # stored history stays clean
    assert (await channel.context.chat.messages.get(0))["content"] == "what time is it?"


@pytest.mark.parametrize("roles, expected", [
    (["user", "user"], ["user", "assistant", "user"]),
    (["user", "assistant", "assistant"], ["user", "assistant", "user", "assistant"]),
    (["user", "tool"], ["user", "assistant", "tool"]),
    (["user", "assistant", "tool", "user"], ["user", "assistant", "tool", "assistant", "user"]),
    (["user", "assistant", "tool", "tool", "assistant"], ["user", "assistant", "tool", "tool", "assistant"]),
])
async def test_turn_order_is_enforced(channel, roles, expected):
    history(channel, *[{"role": role, "content": "x"} for role in roles])

    assert [m["role"] for m in await channel.context.get()] == expected


async def test_reasoning_removed_when_not_kept(channel, set_config):
    set_config(model={"keep_reasoning_in_context": False})
    history(
        channel,
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello", "reasoning_content": "thinking"},
    )

    assert "reasoning_content" not in (await channel.context.get())[1]


async def test_reasoning_only_kept_for_current_agentic_loop(channel, set_config):
    set_config(model={"keep_reasoning_in_context": True, "only_preserve_reasoning_for_current_agentic_loop": True})
    history(
        channel,
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "", "tool_calls": [call("a")], "reasoning_content": "old loop"},
        {"role": "tool", "tool_call_id": "a", "content": "ok"},
        {"role": "assistant", "content": "done", "reasoning_content": "old answer"},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "", "tool_calls": [call("b")], "reasoning_content": "new loop"},
    )
    channel.agentic_loop_start = 4

    context = await channel.context.get()
    assert "reasoning_content" not in context[1]
    assert context[3]["reasoning_content"] == "old answer"  # plain replies keep theirs
    assert context[5]["reasoning_content"] == "new loop"

    set_config(model={"only_preserve_reasoning_for_current_agentic_loop": False})
    assert (await channel.context.get())[1]["reasoning_content"] == "old loop"


async def test_max_messages_evicts_in_blocks(channel, set_config):
    set_config(api={"max_messages": 4, "evict_block": 2})
    history(channel, *[{"role": "user" if i % 2 == 0 else "assistant", "content": str(i)} for i in range(7)])

    # 3 over the limit rounds up to 4 dropped
    assert [m["content"] for m in await channel.context.get()] == ["4", "5", "6"]


async def test_max_messages_never_starts_on_a_tool_result(channel, set_config):
    set_config(api={"max_messages": 3, "evict_block": 1})
    history(
        channel,
        {"role": "user", "content": "0"},
        {"role": "assistant", "content": "", "tool_calls": [call("a"), call("b")]},
        {"role": "tool", "tool_call_id": "a", "content": "2"},
        {"role": "tool", "tool_call_id": "b", "content": "2"},
        {"role": "assistant", "content": "3"},
    )

    assert [m["content"] for m in await channel.context.get()] == ["3"]


async def test_summary_replaces_older_history(channel, set_config):
    set_config(api={"max_messages": 2, "evict_block": 1})
    history(
        channel,
        {"role": "user", "content": "ancient"},
        {"role": "assistant", "content": "history"},
        channel.context.SUMMARIZATION_CUTOFF,
        {"role": "assistant", "content": "SUMMARY"},
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
    )

    # the summary is pinned even when max_messages trims after it
    assert await channel.context.get() == [
        {"role": "user", "content": "SUMMARY"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "c"},
    ]
