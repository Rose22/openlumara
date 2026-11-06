# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
core/toolcalls.py ToolcallManager.process() - the agentic tool loop.

integration level: real Chat/Messages/Context + real ToolcallManager on
FakeChannel/FakeAPI. The API's recursive responses are scripted streams.

intent under test:
- process() is a no-op without tool_calls.
- happy path: assistant message with tool_calls lands in history, the
  module method executes with repaired JSON args, the tool result is
  appended as a role=tool message, then the loop re-requests the API and
  forwards its tokens until a {"type": "final"} message token arrives.
- every rejection path (unknown tool, disabled tool, unloaded tool, meta
  tool while dynamic loading is off) still produces a tool result message
  so the model can recover, and the chain continues.
- tool exceptions/timeouts become error results, never crash the chain.
- cancel_request stops the chain before executing remaining tools.
- push=True emits the assistant message with defer=False mid-chain.
"""

import asyncio
import json
from types import SimpleNamespace

import pytest

import core
from harness import apply_config


class DemoTools:
    """module stub: catalog entries resolve to methods on this object"""

    name = "demo"

    def __init__(self):
        self.disabled_tools = []
        self.echo_calls = []

    async def echo(self, msg=""):
        self.echo_calls.append(msg)
        return {"status": "success", "content": f"echo:{msg}"}

    async def boom(self):
        raise RuntimeError("tool exploded")

    async def slow(self):
        await asyncio.sleep(5)
        return {"status": "success", "content": "late"}

    def result(self, content, success=True):
        return {"status": "success" if success else "error", "content": content}


def tool_call(id_, name, arguments):
    return {
        "id": id_,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def assistant_with_tools(*calls):
    return {"role": "assistant", "content": None, "tool_calls": list(calls)}


async def make_env(fake_channel, tool_timeout=10.0, dynamic=True, loaded=("demo_echo",)):
    """real Context (owns Chat+Messages) + stub tool_loader wired for process()"""
    apply_config(
        api={"max_context": 16768},
        model={
            "name": "test-model",
            "use_tools": True,
            "dynamic_tool_loading": dynamic,
            "keep_reasoning_in_context": False,
            "only_preserve_reasoning_for_current_agentic_loop": False,
            "automatically_compress_context": False,
            "context_compression_threshold": 0.8,
        },
        modules={"disabled_prompts": []},
        core={"tool_timeout": tool_timeout},
    )

    ctx = core.context.Context(fake_channel)
    fake_channel.context = ctx
    await ctx.chat.autoload()

    demo = DemoTools()
    fake_channel.manager.modules = {"demo": demo}
    fake_channel.manager.tools = [
        {"type": "function", "function": {"name": n}} for n in loaded
    ]

    fake_channel.tool_loader = SimpleNamespace(
        catalog={
            "demo_echo": {"tool": {}, "module": "demo", "method": "echo"},
            "demo_slow": {"tool": {}, "module": "demo", "method": "slow"},
            "demo_boom": {"tool": {}, "module": "demo", "method": "boom"},
        },
        meta_tool_names=["tools_load"],
        get_meta_callable=lambda name: None,
    )

    tc_manager = core.toolcalls.ToolcallManager(fake_channel)
    fake_channel.tc_manager = tc_manager
    return ctx, demo, tc_manager


async def collect(tc_manager, msg, push=False):
    return [token async for token in tc_manager.process(msg, push=push)]


def tool_events(tokens):
    return [t for t in tokens if t.get("type") == "tool"]


def final_msg(tokens):
    finals = [t for t in tokens if t.get("type") == "final"]
    return finals[0]["content"] if finals else None


# ---------------------------------------------------------------------------
# basics
# ---------------------------------------------------------------------------

async def test_process_is_noop_without_tool_calls(fake_channel):
    _ctx, _demo, tc = await make_env(fake_channel)

    tokens = await collect(tc, {"role": "assistant", "content": "no tools here"})

    assert tokens == []
    assert fake_channel.manager.API.sent == []


async def test_happy_path_full_round_trip(fake_channel):
    ctx, demo, tc = await make_env(fake_channel)
    fake_channel.manager.API.queue_stream(
        [
            {"type": "content", "content": "all "},
            {"type": "content", "content": "done"},
        ]
    )

    msg = assistant_with_tools(tool_call("call_1", "demo_echo", '{"msg": "hi"}'))
    tokens = await collect(tc, msg)

    # the tool ran with parsed args
    assert demo.echo_calls == ["hi"]

    # tool result event yielded, content is the module result json
    events = tool_events(tokens)
    assert len(events) == 1
    assert events[0]["tool_call_id"] == "call_1"
    assert json.loads(events[0]["content"]) == {
        "status": "success", "content": "echo:hi"
    }

    # history: assistant(tool_calls) then tool result
    history = await ctx.chat.messages.get()
    assert [m["role"] for m in history] == ["assistant", "tool"]
    assert history[1]["tool_call_id"] == "call_1"

    # the recursive request saw the tool result in context
    sent_ctx = fake_channel.manager.API.sent[-1]["context"]
    assert any(m.get("role") == "tool" for m in sent_ctx)

    # final message token with the joined content
    final = final_msg(tokens)
    assert final == {"role": "assistant", "content": "all done"}


async def test_malformed_json_arguments_are_repaired(fake_channel):
    _ctx, demo, tc = await make_env(fake_channel)
    fake_channel.manager.API.queue_stream([{"type": "content", "content": "ok"}])

    msg = assistant_with_tools(tool_call("c1", "demo_echo", '{"msg": "hi",}'))
    await collect(tc, msg)

    assert demo.echo_calls == ["hi"]


async def test_api_usage_reported_during_recursion_is_recorded(fake_channel):
    ctx, _demo, tc = await make_env(fake_channel)
    fake_channel.manager.API.queue_stream(
        [{"type": "content", "content": "x"},
         {"type": "token_usage", "content": 4321, "source": "API"}]
    )

    msg = assistant_with_tools(tool_call("c1", "demo_echo", '{"msg": "hi"}'))
    await collect(tc, msg)

    assert ctx.chat.data[ctx.chat.current]["token_usage"] == 4321


async def test_push_true_emits_assistant_message_without_defer(fake_channel):
    _ctx, _demo, tc = await make_env(fake_channel)
    fake_channel.manager.API.queue_stream([{"type": "content", "content": "ok"}])

    msg = assistant_with_tools(tool_call("c1", "demo_echo", '{"msg": "hi"}'))
    await collect(tc, msg, push=True)

    assert any(
        m.get("tool_calls") and defer is False
        for m, defer in fake_channel.push_calls
    )


# ---------------------------------------------------------------------------
# rejection paths: every one must still answer the tool call
# ---------------------------------------------------------------------------

async def test_unknown_tool_gets_error_result_and_chain_continues(fake_channel):
    ctx, _demo, tc = await make_env(fake_channel)
    fake_channel.manager.API.queue_stream([{"type": "content", "content": "recovered"}])

    msg = assistant_with_tools(tool_call("c1", "ghost_tool", "{}"))
    tokens = await collect(tc, msg)

    events = tool_events(tokens)
    assert len(events) == 1
    assert "No tool named ghost_tool" in json.loads(events[0]["content"])["content"]

    history = await ctx.chat.messages.get()
    assert history[1]["role"] == "tool"
    assert final_msg(tokens)["content"] == "recovered"


async def test_disabled_tool_is_refused(fake_channel):
    _ctx, demo, tc = await make_env(fake_channel)
    demo.disabled_tools = ["echo"]
    fake_channel.manager.API.queue_stream([{"type": "content", "content": "x"}])

    msg = assistant_with_tools(tool_call("c1", "demo_echo", '{"msg": "hi"}'))
    tokens = await collect(tc, msg)

    assert "disabled by the user" in tool_events(tokens)[0]["content"]
    assert demo.echo_calls == []


async def test_unloaded_tool_prompts_loading_when_dynamic(fake_channel):
    _ctx, demo, tc = await make_env(fake_channel, loaded=())
    fake_channel.manager.API.queue_stream([{"type": "content", "content": "x"}])

    msg = assistant_with_tools(tool_call("c1", "demo_echo", '{"msg": "hi"}'))
    tokens = await collect(tc, msg)

    content = tool_events(tokens)[0]["content"]
    assert "not loaded" in content and "tools_load" in content
    assert demo.echo_calls == []


async def test_meta_tool_refused_when_dynamic_loading_disabled(fake_channel):
    _ctx, _demo, tc = await make_env(fake_channel, dynamic=False)
    fake_channel.manager.API.queue_stream([{"type": "content", "content": "x"}])

    msg = assistant_with_tools(tool_call("c1", "tools_load", '{"module_names": ["demo"]}'))
    tokens = await collect(tc, msg)

    assert "Dynamic tool loading is disabled" in tool_events(tokens)[0]["content"]


# ---------------------------------------------------------------------------
# failures and cancellation
# ---------------------------------------------------------------------------

async def test_tool_exception_becomes_error_result(fake_channel):
    _ctx, _demo, tc = await make_env(fake_channel, loaded=("demo_echo", "demo_boom"))
    fake_channel.manager.API.queue_stream([{"type": "content", "content": "x"}])

    msg = assistant_with_tools(tool_call("c1", "demo_boom", "{}"))
    tokens = await collect(tc, msg)

    result = json.loads(tool_events(tokens)[0]["content"])
    assert result["status"] == "error"
    assert "Error while executing tool" in result["content"]


async def test_tool_timeout_is_enforced(fake_channel):
    _ctx, _demo, tc = await make_env(
        fake_channel, tool_timeout=0.1, loaded=("demo_echo", "demo_slow")
    )
    fake_channel.manager.API.queue_stream([{"type": "content", "content": "x"}])

    msg = assistant_with_tools(tool_call("c1", "demo_slow", "{}"))
    tokens = await collect(tc, msg)

    result = json.loads(tool_events(tokens)[0]["content"])
    assert result["status"] == "error"
    assert "Tool timed out after 0.1s" in result["content"]


async def test_cancel_stops_remaining_tools_in_batch(fake_channel):
    ctx, demo, tc = await make_env(fake_channel)
    fake_channel.manager.API.cancel_request = True

    msg = assistant_with_tools(
        tool_call("c1", "demo_echo", '{"msg": "one"}'),
        tool_call("c2", "demo_echo", '{"msg": "two"}'),
    )
    tokens = await collect(tc, msg)

    assert demo.echo_calls == []  # nothing executed
    assert tokens == []
    assert ("toolcalling chain cancelled", False) in fake_channel.push_calls
    # the assistant message was still recorded before execution started
    history = await ctx.chat.messages.get()
    assert history[-1].get("tool_calls")


async def test_api_failure_during_recursion_is_reported_not_raised(fake_channel):
    ctx, _demo, tc = await make_env(fake_channel)

    async def broken_stream(context, **kwargs):
        raise RuntimeError("api on fire")
        yield  # pragma: no cover

    fake_channel.manager.API.send_stream = broken_stream

    msg = assistant_with_tools(tool_call("c1", "demo_echo", '{"msg": "hi"}'))
    tokens = await collect(tc, msg)  # must not raise

    # the tool itself ran (its result event was yielded before the recursion),
    # but the chain dies gracefully: no final token, error pushed to the user
    assert len(tool_events(tokens)) == 1
    assert final_msg(tokens) is None
    assert any("Error while handling tool calls" in str(m) for m, _d in fake_channel.push_calls)
    assert any("Error while handling tool calls" in m and "api on fire" in m
               for cat, m in fake_channel.logs if cat == "error")


# ---------------------------------------------------------------------------
# recursion
# ---------------------------------------------------------------------------

async def test_second_toolcall_round_recurses(fake_channel):
    ctx, demo, tc = await make_env(fake_channel)
    api = fake_channel.manager.API
    # first recursive round: the model wants ANOTHER tool call...
    api.queue_stream([
        {"type": "tool_calls", "tool_calls": [tool_call("c2", "demo_echo", '{"msg": "again"}')]},
    ])
    # ...which succeeds, and the second round produces the final answer
    api.queue_stream([{"type": "content", "content": "truly done"}])

    msg = assistant_with_tools(tool_call("c1", "demo_echo", '{"msg": "first"}'))
    tokens = await collect(tc, msg)

    assert demo.echo_calls == ["first", "again"]
    assert len(tool_events(tokens)) == 2
    assert final_msg(tokens)["content"] == "truly done"

    history = await ctx.chat.messages.get()
    roles = [m["role"] for m in history]
    assert roles == ["assistant", "tool", "assistant", "tool"]
