# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
core/channel.py Channel - the send/send_stream pipeline.

integration level: real Channel subclass + real Context (owns Chat+Messages)
on FakeManager/FakeAPI. The APIClient is scripted; ToolcallManager.process is
stubbed where the channel only needs to orchestrate it (its own behaviour is
covered by test_toolcalls_pipeline.py).

intent under test:
- send(): preprocess (commands -> module hooks -> add user msg -> connect ->
  build context), request, postprocess (hooks + add assistant msg), then
  format_message for display.
- commands short-circuit the AI; module hooks can transform or fully
  intercept a user message; connect failures surface as an assistant
  message without ever calling the API.
- APIError results become a plain assistant message.
- send_stream(): user_message token, estimation token_usage, streamed
  tokens, final token_usage; error tokens persist the partial message and
  append an "Error: ..." message; tool_calls tokens hand over to the
  toolcall manager whose final message is added to context.
- the push queue: deferred pushes wait for the chain-idle gate (so they
  land after the assistant's final message), immediate pushes do not;
  _shutdown() stops the consumer.
- format_message renders tool results, tool call displays and (optionally)
  reasoning blocks.
"""

import asyncio
from types import SimpleNamespace

import pytest

import core
from core.channel import Channel
from harness import apply_config


class PipelineTestChannel(Channel):
    """minimal concrete channel; __module__ gives get_name() 'pipeline_test'"""

    __module__ = "channels.pipeline_test"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.received = []  # what on_push() displayed

    async def on_push(self, message):
        self.received.append(message)


class FakeSave(dict):
    """stand-in for manager.savedata (StorageDict)"""

    def __init__(self):
        super().__init__()
        self.saved = 0

    def save(self):
        self.saved += 1


def make_hook_module(on_user_message=None, on_assistant_message=None):
    return SimpleNamespace(
        **{k: v for k, v in (("on_user_message", on_user_message),
                             ("on_assistant_message", on_assistant_message)) if v}
    )


@pytest.fixture
async def channel(fake_manager):
    """real Channel with real Context, isolated config, active-channel no-op"""
    apply_config(
        api={"max_context": 16768},
        model={
            "name": "test-model",
            "use_tools": True,
            "dynamic_tool_loading": True,
            "keep_reasoning_in_context": False,
            "only_preserve_reasoning_for_current_agentic_loop": False,
            "automatically_compress_context": False,
            "context_compression_threshold": 0.8,
        },
        modules={"disabled_prompts": []},
        core={"cmd_prefix": "/", "tool_timeout": 10.0},
    )
    ch = PipelineTestChannel(fake_manager)
    fake_manager.channel = ch  # makes _set_as_active_channel a no-op
    await ch.init()
    yield ch
    await ch._shutdown()


async def collect(stream):
    return [token async for token in stream]


async def history(ch):
    return await ch.context.chat.messages.get()


# ---------------------------------------------------------------------------
# send() happy paths
# ---------------------------------------------------------------------------

async def test_send_happy_path(channel):
    channel.manager.API.queue_response({"role": "assistant", "content": "hello"})

    result = await channel.send("hi")

    assert result == {"role": "assistant", "content": "hello"}
    # the API saw a context ending with the user message
    sent_ctx = channel.manager.API.sent[-1]["context"]
    assert sent_ctx[-1] == {"role": "user", "content": "hi"}
    # both sides of the exchange are in history
    assert [(m["role"], m["content"]) for m in await history(channel)] == [
        ("user", "hi"),
        ("assistant", "hello"),
    ]
    # the agentic loop marker points at the user message
    assert channel.agentic_loop_start == 0


async def test_send_passes_kwargs_to_api(channel):
    channel.manager.API.queue_response({"role": "assistant", "content": "ok"})
    await channel.send("hi", temperature=0.1)
    assert channel.manager.API.sent[-1]["temperature"] == 0.1


async def test_send_add_to_context_false_skips_assistant_only(channel):
    channel.manager.API.queue_response({"role": "assistant", "content": "hello"})

    await channel.send("hi", add_to_context=False)

    assert [m["role"] for m in await history(channel)] == ["user"]


async def test_send_closes_chain_idle_gate_during_request(channel):
    api = channel.manager.API
    gate_states = []
    original_send = api.send

    async def spy(context, **kwargs):
        gate_states.append(channel._chain_idle.is_set())
        return await original_send(context, **kwargs)

    api.send = spy
    api.queue_response({"role": "assistant", "content": "ok"})

    await channel.send("hi")

    # deferred pushes must wait for the turn to complete
    assert gate_states == [False]
    assert channel._chain_idle.is_set()


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

async def test_command_response_short_circuits_the_api(channel):
    calls = []

    async def fake_process_input(cmd, authorized=False):
        calls.append((cmd, authorized))
        return "cmd output"

    channel.commands.process_input = fake_process_input

    result = await channel.send("/test", commands_authorized=True)

    assert calls == [("/test", True)]
    assert result["content"] == "cmd output"
    assert channel.manager.API.sent == []  # never reached the AI


async def test_command_without_response_returns_none(channel):
    async def fake_process_input(cmd, authorized=False):
        return None

    channel.commands.process_input = fake_process_input

    assert await channel.send("/nocmdoutput") is None
    assert channel.manager.API.sent == []


async def test_command_exception_becomes_error_message(channel):
    async def broken(cmd, authorized=False):
        raise RuntimeError("cmd exploded")

    channel.commands.process_input = broken

    result = await channel.send("/boom")

    assert result["role"] == "assistant"
    assert "cmd exploded" in result["content"]


# ---------------------------------------------------------------------------
# module hooks
# ---------------------------------------------------------------------------

async def test_user_message_hook_can_transform_message(channel):
    channel.manager.modules["hook"] = make_hook_module(
        on_user_message=lambda msg: msg.upper()
    )
    channel.manager.API.queue_response({"role": "assistant", "content": "ok"})

    await channel.send("hello")

    sent_ctx = channel.manager.API.sent[-1]["context"]
    assert sent_ctx[-1] == {"role": "user", "content": "HELLO"}


async def test_user_message_hook_can_intercept(channel):
    channel.manager.modules["hook"] = make_hook_module(
        on_user_message=lambda msg: False
    )

    result = await channel.send("secret")

    assert result is None
    assert channel.manager.API.sent == []
    # the intercepted message was still recorded in context
    assert [m["role"] for m in await history(channel)] == ["user"]


async def test_assistant_message_hook_receives_content(channel):
    seen = []
    channel.manager.modules["hook"] = make_hook_module(
        on_assistant_message=lambda content: seen.append(content)
    )
    channel.manager.API.queue_response({"role": "assistant", "content": "answer"})

    await channel.send("q")

    assert seen == ["answer"]


async def test_assistant_message_hook_exception_does_not_break_send(channel):
    def boom(content):
        raise RuntimeError("hook exploded")

    channel.manager.modules["hook"] = make_hook_module(on_assistant_message=boom)
    channel.manager.API.queue_response({"role": "assistant", "content": "answer"})

    result = await channel.send("q")

    assert result["content"] == "answer"
    assert any("module error" in cat for cat, _m in channel.manager.logs)


@pytest.mark.xfail(
    strict=True,
    reason="suspected bug: if on_user_message() raises, usr_msg_result is "
    "never assigned; the subsequent 'if usr_msg_result is False' then dies "
    "with UnboundLocalError instead of the intended per-module isolation",
)
async def test_user_message_hook_exception_is_isolated(channel):
    def boom(msg):
        raise RuntimeError("hook exploded")

    channel.manager.modules["hook"] = make_hook_module(on_user_message=boom)
    channel.manager.API.queue_response({"role": "assistant", "content": "answer"})

    result = await channel.send("q")

    # intent: the error is logged and the message proceeds unmodified
    assert result["content"] == "answer"
    assert any("module error" in cat for cat, _m in channel.logs)


# ---------------------------------------------------------------------------
# api failures
# ---------------------------------------------------------------------------

async def test_connect_failure_short_circuits(channel):
    async def failing_attempt_connect():
        return "connection refused"

    channel.manager.API.attempt_connect = failing_attempt_connect

    result = await channel.send("hi")

    assert result == {"role": "assistant", "content": "connection refused"}
    assert channel.manager.API.sent == []


async def test_api_error_result_becomes_assistant_message(channel):
    channel.manager.API.queue_response(core.api.APIError("model is grumpy"))

    result = await channel.send("hi")

    assert result == {"role": "assistant", "content": "model is grumpy"}


# ---------------------------------------------------------------------------
# toolcalls delegation (channel side only)
# ---------------------------------------------------------------------------

async def test_send_with_tool_calls_delegates_to_tc_manager(channel):
    seen = {}

    async def fake_process(assistant_message, push=False):
        seen["msg"] = assistant_message
        seen["push"] = push
        yield {
            "type": "final",
            "content": {"role": "assistant", "content": "after the tools"},
        }

    channel.tc_manager.process = fake_process
    channel.manager.API.queue_response(
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "demo_echo", "arguments": "{}"}}]}
    )

    result = await channel.send("use a tool")

    assert seen["push"] is True
    assert seen["msg"]["tool_calls"]
    assert result["content"] == "after the tools"
    # the final message went through postprocess (added to context)
    assert (await history(channel))[-1]["content"] == "after the tools"


async def test_send_with_tool_calls_but_no_final_returns_none(channel):
    async def fake_process(assistant_message, push=False):
        return
        yield  # pragma: no cover

    channel.tc_manager.process = fake_process
    channel.manager.API.queue_response(
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "x", "arguments": "{}"}}]}
    )

    assert await channel.send("use a tool") is None


# ---------------------------------------------------------------------------
# send_stream()
# ---------------------------------------------------------------------------

async def test_stream_happy_path_token_sequence(channel):
    channel.manager.API.queue_stream(
        [
            {"type": "content", "content": "he"},
            {"type": "content", "content": "llo"},
            {"type": "token_usage", "content": 123, "source": "API"},
        ]
    )

    tokens = await collect(channel.send_stream("hi"))

    kinds = [t["type"] for t in tokens]
    assert kinds == [
        "user_message", "token_usage", "content", "content",
        "token_usage", "token_usage",
    ]
    assert tokens[0]["content"] == "hi"
    assert tokens[1]["source"] == "estimation"
    # the API-reported usage is forwarded as-is and cached...
    assert tokens[4] == {"type": "token_usage", "content": 123, "source": "API"}
    # ...so the channel's final count is reported with source "API"
    assert tokens[-1]["type"] == "token_usage" and tokens[-1]["source"] == "API"

    assert [(m["role"], m["content"]) for m in await history(channel)] == [
        ("user", "hi"),
        ("assistant", "hello"),
    ]


async def test_stream_reasoning_is_persisted_with_content(channel):
    channel.manager.API.queue_stream(
        [
            {"type": "reasoning", "content": "thinking.."},
            {"type": "content", "content": "answer"},
        ]
    )

    await collect(channel.send_stream("q"))

    assistant = (await history(channel))[-1]
    assert assistant["content"] == "answer"
    assert assistant["reasoning_content"] == "thinking.."


async def test_stream_error_token_persists_partial_then_error(channel):
    channel.manager.API.queue_stream(
        [
            {"type": "content", "content": "partial ans"},
            {"type": "error", "content": "kaboom"},
        ]
    )

    tokens = await collect(channel.send_stream("q"))

    assert tokens[-1] == {"type": "error", "content": "kaboom"}
    roles = [(m["role"], m["content"]) for m in await history(channel)]
    # partial content is not lost, and the error itself lands in context
    assert roles == [
        ("user", "q"),
        ("assistant", "partial ans"),
        ("assistant", "Error: kaboom"),
    ]


async def test_stream_tool_calls_hand_over_to_manager(channel):
    seen = {}

    async def fake_process(toolcall_request):
        seen["req"] = toolcall_request
        yield {"type": "tool", "tool_call_id": "c1", "content": "{}"}
        yield {"type": "final", "content": {"role": "assistant", "content": "done"}}

    channel.tc_manager.process = fake_process
    channel.manager.API.queue_stream(
        [{"type": "tool_calls",
          "tool_calls": [{"id": "c1", "type": "function",
                          "function": {"name": "demo_echo",
                                       "arguments": '{"msg": "hi"}'}}]}]
    )

    tokens = await collect(channel.send_stream("use a tool"))

    # the channel built the recursive request from the stream content
    assert seen["req"]["tool_calls"][0]["id"] == "c1"
    # sub-tokens are forwarded, final token_usage closes the stream
    kinds = [t["type"] for t in tokens]
    assert kinds == [
        "user_message", "token_usage", "tool_calls", "tool", "final",
        "token_usage",
    ]
    assert tokens[-1]["type"] == "token_usage"
    # the toolcall final message was added to context by the channel
    # (the stubbed process() itself does not write to context)
    assert (await history(channel))[-1]["content"] == "done"


async def test_stream_command_yields_user_and_response_tokens(channel):
    async def fake_process_input(cmd, authorized=False):
        return "cmd output"

    channel.commands.process_input = fake_process_input

    tokens = await collect(channel.send_stream("/test"))

    assert tokens == [
        {"type": "user_message", "content": "/test", "is_cmd": True},
        {"type": "content", "content": "cmd output", "is_cmd": True},
    ]
    assert channel.manager.API.sent == []


async def test_stream_module_intercept_yields_nothing(channel):
    channel.manager.modules["hook"] = make_hook_module(
        on_user_message=lambda msg: False
    )

    assert await collect(channel.send_stream("secret")) == []
    assert channel.manager.API.sent == []


async def test_stream_connect_failure_yields_error_token(channel):
    async def failing_attempt_connect():
        return "connection refused"

    channel.manager.API.attempt_connect = failing_attempt_connect

    tokens = await collect(channel.send_stream("hi"))

    assert tokens[-1] == {"type": "error", "content": "connection refused"}
    assert (await history(channel))[-1]["content"] == "Error: connection refused"


async def test_stream_reopens_chain_idle_gate_after_completion(channel):
    channel.manager.API.queue_stream([{"type": "content", "content": "ok"}])

    await collect(channel.send_stream("hi"))

    assert channel._chain_idle.is_set()


# ---------------------------------------------------------------------------
# push queue
# ---------------------------------------------------------------------------

async def test_deferred_push_waits_for_chain_idle(channel):
    await channel._start_push_queue()
    channel._chain_idle.clear()

    await channel.push("later", defer=True)
    await asyncio.sleep(0.05)

    # gate closed: nothing displayed, nothing in context yet
    assert channel.received == []
    assert await history(channel) == []

    channel._chain_idle.set()
    await asyncio.wait_for(channel.push_queue.join(), timeout=2)

    assert channel.received == [{"role": "assistant", "content": "later"}]
    assert [m["content"] for m in await history(channel)] == ["later"]


async def test_immediate_push_bypasses_the_gate(channel):
    await channel._start_push_queue()
    channel._chain_idle.clear()

    await channel.push("now", defer=False)
    await asyncio.wait_for(channel.push_queue.join(), timeout=2)

    assert channel.received == [{"role": "assistant", "content": "now"}]
    assert [m["content"] for m in await history(channel)] == ["now"]


async def test_push_string_is_wrapped_as_assistant_message(channel):
    await channel._start_push_queue()

    await channel.push("hello", defer=False)
    await asyncio.wait_for(channel.push_queue.join(), timeout=2)

    assert channel.received == [{"role": "assistant", "content": "hello"}]


async def test_shutdown_cancels_push_consumer(channel):
    await channel._start_push_queue()
    task = channel._queue_task
    assert not task.done()

    await channel._shutdown()

    assert task.done()


# ---------------------------------------------------------------------------
# formatting helpers
# ---------------------------------------------------------------------------

def test_format_message_tool_role_is_summarized(channel):
    out = channel.format_message({"role": "tool", "content": "{\"big\": \"json\"}"})
    assert out["content"] == "processing results.."


def test_format_message_renders_tool_calls(channel):
    out = channel.format_message(
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "demo_echo",
                                      "arguments": '{"msg": "hi"}'}}]}
    )
    assert "demo_echo" in out["content"]
    assert 'msg="hi"' in out["content"]


def test_format_message_reasoning_hidden_by_default(channel):
    out = channel.format_message(
        {"role": "assistant", "content": "answer", "reasoning_content": "secret thoughts"}
    )
    assert out["content"] == "answer"


def test_format_message_reasoning_shown_when_configured(channel, fake_manager):
    apply_config(
        api={"max_context": 16768},
        model={"name": "test-model", "use_tools": True, "dynamic_tool_loading": True},
        modules={"disabled_prompts": []},
        core={"cmd_prefix": "/", "tool_timeout": 10.0},
        channels={"settings": {"pipeline_test": {"show_reasoning": True}}},
    )
    ch = PipelineTestChannel(fake_manager)

    out = ch.format_message(
        {"role": "assistant", "content": "answer", "reasoning_content": "because"}
    )

    assert "**Reasoning:**" in out["content"]
    assert "**Conclusion**:" in out["content"]
    assert "because" in out["content"]


def test_extract_content_variants(channel):
    assert channel._extract_content({"content": "plain"}) == "plain"
    assert channel._extract_content(
        {"content": [{"type": "text", "text": "mm"}, {"type": "image_url"}]}
    ) == "mm"
    assert channel._extract_content({"content": None}) == ""


# ---------------------------------------------------------------------------
# active channel bookkeeping
# ---------------------------------------------------------------------------

async def test_set_as_active_channel_updates_manager(channel, fake_manager):
    class Other:
        pass

    fake_manager.channel = Other()
    fake_manager.savedata = FakeSave()
    mod = SimpleNamespace()
    fake_manager.modules["m"] = mod

    await channel._set_as_active_channel()

    assert fake_manager.channel is channel
    assert fake_manager.savedata["last_channel"] == "pipeline_test"
    assert fake_manager.savedata.saved == 1
    assert mod.channel is channel


def test_channel_wires_itself_into_the_turn_collector(channel):
    # dev a4b6d50: TurnCollector takes the channel so it can ask the owning
    # module for one-line tool result summaries
    assert isinstance(channel.turncollector, core.turns.TurnCollector)
    assert channel.turncollector.channel is channel


async def test_set_as_active_channel_is_noop_when_already_active(channel, fake_manager):
    fake_manager.savedata = FakeSave()

    await channel._set_as_active_channel()

    assert fake_manager.savedata.saved == 0
