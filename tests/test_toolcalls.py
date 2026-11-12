# AI Written: Claude Opus 5.5, reviewed by Claude Fable 5.2
import asyncio
import json

import core
import pytest


class Demo(core.module.Module):
    __module__ = "modules.demo"

    def __init__(self, manager):
        super().__init__(manager)
        self.calls = []

    @core.module.tool
    async def echo(self, msg: str):
        self.calls.append(msg)
        return self.result(f"echo:{msg}")

    @core.module.tool
    async def boom(self):
        raise RuntimeError("kaboom")

    @core.module.tool
    async def slow(self):
        await asyncio.sleep(1)


def call(id, name, arguments):
    return {"id": id, "type": "function", "function": {"name": name, "arguments": arguments}}


def assistant(*calls):
    return {"role": "assistant", "content": "", "tool_calls": list(calls)}


def setup(channel, set_config, dynamic=False):
    """register Demo on a fresh tool loader, the way the manager does at startup"""
    set_config(model={"dynamic_tool_loading": dynamic})
    manager = channel.manager
    demo = Demo(manager)
    manager.modules["demo"] = demo
    loader = channel.tool_loader = core.tool_loader.ToolLoader(channel)
    loader.register_module(demo)
    loader.register_meta_tools()
    loader.refresh()
    manager.tools = loader.active_tools
    manager.tool_names = loader.active_names
    return demo


@pytest.fixture
def demo(channel, set_config):
    return setup(channel, set_config)


async def run(channel, message, *followups):
    channel.manager.API.replies.extend(followups or [[{"type": "content", "content": "done"}]])
    return [t async for t in channel.tc_manager.process(message)]


def results(tokens):
    return [json.loads(t["content"]) for t in tokens if t["type"] == "tool"]


async def history(channel):
    return list(await channel.context.chat.messages.get())


async def test_round_trip(channel, demo):
    tokens = await run(channel, assistant(call("c1", "demo_echo", '{"msg": "hi"}')))

    assert demo.calls == ["hi"]
    assert results(tokens) == [{"status": "success", "content": "echo:hi"}]
    msgs = await history(channel)
    assert [m["role"] for m in msgs] == ["assistant", "tool"]
    assert msgs[1]["tool_call_id"] == "c1"
    assert json.loads(msgs[1]["content"])["content"] == "echo:hi"
    # the follow-up request carries the tool result and the tool list
    sent = channel.manager.API.sent[-1]
    assert sent["context"][-1]["role"] == "tool"
    assert sent["tools"] == channel.manager.tools
    assert tokens[-1] == {"type": "final", "content": {"role": "assistant", "content": "done"}}


async def test_malformed_arguments_are_repaired(channel, demo):
    await run(channel, assistant(call("c1", "demo_echo", '{"msg": "hi",')))
    assert demo.calls == ["hi"]
    stored = (await history(channel))[0]["tool_calls"][0]["function"]["arguments"]
    assert json.loads(stored) == {"msg": "hi"}


async def test_unknown_tool_does_not_stop_the_batch(channel, demo):
    tokens = await run(channel, assistant(
        call("c1", "demo_nope", "{}"),
        call("c2", "demo_echo", '{"msg": "still runs"}'),
    ))
    first, second = results(tokens)
    assert first["status"] == "error"
    assert second["status"] == "success"
    assert [m.get("tool_call_id") for m in await history(channel)] == [None, "c1", "c2"]


@pytest.mark.parametrize("tool, error", [("demo_boom", "kaboom"), ("demo_slow", "timed out")])
async def test_failing_tool_becomes_error_result(channel, demo, set_config, tool, error):
    set_config(core={"tool_timeout": 0.05})
    result = results(await run(channel, assistant(call("c1", tool, "{}"))))[0]
    assert result["status"] == "error"
    assert error in result["content"]


async def test_disabled_tool_is_refused(channel, demo):
    demo.disabled_tools.append("echo")
    tokens = await run(channel, assistant(call("c1", "demo_echo", '{"msg": "x"}')))
    assert results(tokens)[0]["status"] == "error"
    assert demo.calls == []


async def test_unloaded_tool_is_refused_with_dynamic_loading(channel, set_config):
    demo = setup(channel, set_config, dynamic=True)
    tokens = await run(channel, assistant(call("c1", "demo_echo", '{"msg": "x"}')))
    assert "tools_load" in results(tokens)[0]["content"]
    assert demo.calls == []


async def test_tools_call_bridge(channel, set_config):
    demo = setup(channel, set_config, dynamic=True)
    args = json.dumps({"name": "demo_echo", "params": '{"msg": "via bridge"}'})
    tokens = await run(channel, assistant(call("c1", "tools_call", args)))
    assert demo.calls == ["via bridge"]
    assert results(tokens) == [{"status": "success", "content": "echo:via bridge"}]


async def test_cancel_stops_remaining_tools(channel, demo):
    channel.manager.API.cancel_request = True
    tokens = await run(channel, assistant(call("c1", "demo_echo", '{"msg": "x"}')))
    assert tokens == []
    assert demo.calls == []
    assert channel.manager.API.sent == []


async def test_model_can_chain_another_tool_call(channel, demo):
    tokens = await run(
        channel,
        assistant(call("c1", "demo_echo", '{"msg": "first"}')),
        [{"type": "tool_calls", "tool_calls": [call("c2", "demo_echo", '{"msg": "again"}')]}],
        [{"type": "content", "content": "all done"}],
    )
    assert demo.calls == ["first", "again"]
    assert tokens[-1]["content"]["content"] == "all done"
    assert [m["role"] for m in await history(channel)] == ["assistant", "tool", "assistant", "tool"]


async def test_api_error_during_followup_is_reported(channel, demo):
    async def broken(context, **kwargs):
        raise RuntimeError("api down")
        yield

    channel.manager.API.send_stream = broken
    tokens = await run(channel, assistant(call("c1", "demo_echo", '{"msg": "x"}')))
    assert [t["type"] for t in tokens] == ["tool"]
    assert "api down" in (await history(channel))[-1]["content"]


async def test_history_groups_into_turns(channel, demo):
    await channel.context.chat.messages.add({"role": "user", "content": "do it"})
    await run(channel, assistant(call("c1", "demo_echo", '{"msg": "a"}'), call("c2", "demo_boom", "{}")))
    await channel.context.chat.messages.add({"role": "assistant", "content": "done"})

    turns = await channel.turncollector.group_history(await history(channel))

    assert [t["role"] for t in turns] == ["user", "assistant"]
    turn = turns[1]
    assert (turn["first_message_index"], turn["last_message_index"]) == (1, 4)
    assert [m["content"] for m in turn["final_messages"]] == ["done"]
    [step] = turn["steps"]
    echo, boom = step["tool_calls"]
    assert json.loads(echo["_metadata"]["response"])["content"] == "echo:a"
    assert echo["_metadata"]["args_parsed"] == {"msg": "a"}
    assert not echo["_metadata"]["failed"]
    assert boom["_metadata"]["failed"]


async def test_stream_groups_into_steps_and_final(channel):
    async def stream():
        yield {"type": "reasoning", "content": "hmm"}
        yield {"type": "content", "content": "let me check"}
        yield {"type": "tool_calls", "tool_calls": [call("c1", "demo_echo", '{"msg": "x"}')]}
        yield {"type": "tool", "tool_call_id": "c1", "content": '{"status": "success", "content": "ok"}'}
        yield {"type": "content", "content": "done"}

    events = [e async for e in channel.turncollector.group_stream(stream())]

    steps = {}
    for e in events:
        if e["type"] == "step":
            steps[e["content"]["step"]] = e["content"]
    finals = [e["content"] for e in events if e["type"] == "final"]

    assert list(steps) == [1]
    step = steps[1]
    # content that was followed by a tool call folds back into the step
    assert (step["reasoning_content"], step["content"]) == ("hmm", "let me check")
    assert step["tool_calls"][0]["_metadata"]["response"]
    assert finals[-1][0]["content"] == "done"
