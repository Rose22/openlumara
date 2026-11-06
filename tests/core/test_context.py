# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
core/context.py: Context.get() assembly, trimming, compression, token math.

integration level: real Context (which owns a real Chat + Messages) on
FakeChannel/FakeAPI. FakeAPI records every context that was "sent".

intent under test (per the docstring in Context.get):
- the sent context is system -> history -> end prompt, with roles adapted
  to API.supports_developer_role.
- a SUMMARIZATION_CUTOFF pins the summary as the first history message and
  drops everything before it; a cutoff without a usable summary is ignored
  (and logged), not fatal.
- ghost/signal messages never reach the API; empty assistant messages are
  dropped; only API-approved keys survive.
- history is evicted in EVICT_BLOCK chunks, never inside a
  assistant(tool_calls)->tool group.
- token order is enforced with " " spacer messages.
- trimming is a binary search to 95% of max_context; if even an empty
  history does not fit, get() warns once and returns None.
- token accounting: API-reported usage is the source of truth, estimates
  only cover messages added after the measurement.
- compress() appends cutoff+summary non-destructively, merges the previous
  summary, pins the active request, and guards against recursion.
"""

import json

import pytest

import core
from harness import apply_config


class PromptModule:
    def __init__(self, prompt=None, end=None):
        self._prompt = prompt
        self._end = end

    async def on_system_prompt(self):
        return self._prompt

    async def on_end_prompt(self):
        return self._end


def setup_context(fake_channel, api=None, model=None, modules=None):
    """
    real Context on the fake channel, with an explicit config (core.config
    does not merge schema defaults once a config file exists).
    """
    cfg = {
        "api": {"max_messages": 200, "max_context": 16768, "evict_block": 32},
        "model": {
            "use_tools": True,
            "keep_reasoning_in_context": False,
            "only_preserve_reasoning_for_current_agentic_loop": False,
            "automatically_compress_context": False,
            "context_compression_threshold": 0.8,
        },
        "modules": {"disabled_prompts": []},
    }
    for section, override in (("api", api), ("model", model), ("modules", modules)):
        if override:
            cfg[section].update(override)
    apply_config(**cfg)

    ctx = core.context.Context(fake_channel)
    fake_channel.context = ctx
    return ctx


async def seed(ctx, msgs):
    """append raw messages, bypassing Messages.add() side effects"""
    for m in msgs:
        ctx.chat.messages.data.append(m)
    ctx.chat.messages.data.save()  # StorageList.save is sync


def cutoff():
    return {"_metadata": {"signal": "SUMMARIZATION_CUTOFF"}}


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------

async def test_connect_failure_short_circuits(fake_channel):
    ctx = setup_context(fake_channel)

    async def failing_connect(silent=False):
        return "no route to host"

    fake_channel.manager.API.connected = False
    fake_channel.manager.API.connect = failing_connect

    result = await ctx.get()

    assert result == "no route to host"
    assert ("api", "no route to host") in fake_channel.logs


async def test_prompts_wrap_history_with_role_flags(fake_channel):
    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()
    fake_channel.manager.modules = {
        "identity": PromptModule(prompt="be nice", end="think hard"),
    }
    await seed(ctx, [{"role": "user", "content": "hi"}])

    built = await ctx.get()

    assert built[0] == {"role": "system", "content": "# Identity\nbe nice"}
    assert built[1]["content"] == "hi"
    assert built[-1]["role"] == "user"  # dev_role falls back to user
    assert "think hard" in built[-1]["content"]

    # with developer-role APIs, both wrapper messages use the developer role
    fake_channel.manager.API.supports_developer_role = True
    ctx.chat._cached_system_prompt = None
    built = await ctx.get()
    assert built[0]["role"] == "developer"
    assert built[-1]["role"] == "developer"


async def test_history_only_mode(fake_channel):
    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()
    fake_channel.manager.modules = {
        "identity": PromptModule(prompt="be nice", end="think hard"),
    }
    await seed(ctx, [{"role": "user", "content": "hi"}])

    built = await ctx.get(system_prompt=False, end_prompt=False)

    assert [m["content"] for m in built] == ["hi"]


async def test_ghost_signal_and_empty_assistant_filtered(fake_channel):
    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()
    await seed(
        ctx,
        [
            {"role": "user", "content": "kept"},
            {"role": "user", "content": "secret", "_metadata": {"ghost": True}},
            {"role": "user", "content": "", "_metadata": {"signal": "SOMETHING"}},
            {"role": "assistant", "content": None},  # empty assistant
            {"role": "assistant", "content": "reply", "tool_calls": [{"id": "1"}]},
        ],
    )

    built = await ctx.get()

    contents = [m.get("content") for m in built]
    assert "secret" not in contents
    assert all(m["role"] != "user" or m["content"] != "" for m in built)
    assert [m["role"] for m in built] == ["user", "assistant"]


async def test_cutoff_pins_summary_and_drops_older(fake_channel):
    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()
    await seed(
        ctx,
        [
            {"role": "user", "content": "ancient question"},
            {"role": "assistant", "content": "ancient answer"},
            cutoff(),
            {"role": "assistant", "content": "THE SUMMARY"},
            {"role": "user", "content": "newest question"},
        ],
    )

    built = await ctx.get()

    assert built[0] == {"role": "user", "content": "THE SUMMARY"}
    assert built[-1]["content"] == "newest question"
    assert "ancient question" not in json.dumps(built)
    # two consecutive user messages (summary + question) need a spacer
    assert built[1] == {"role": "assistant", "content": " "}


async def test_cutoff_without_summary_is_ignored_and_logged(fake_channel):
    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()
    # a cutoff with no usable summary after it (here: nothing at all)
    await seed(
        ctx,
        [
            {"role": "user", "content": "before cutoff"},
            cutoff(),
        ],
    )

    built = await ctx.get()

    assert any(
        "Broken summarization cutoff" in msg for _cat, msg in fake_channel.logs
    )
    # the broken cutoff is ignored: everything up to and including it is
    # dropped, leaving an empty history rather than a crash
    assert built == []


async def test_injections_appended_to_user_content_only(fake_channel):
    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()
    await seed(
        ctx,
        [
            {
                "role": "user",
                "content": "hello",
                "_metadata": {"injection": "current time: noon"},
            },
            {
                "role": "assistant",
                "content": "hi",
                "_metadata": {"injection": "should not appear"},
            },
        ],
    )

    built = await ctx.get()

    assert built[0]["content"] == "hello\n\ncurrent time: noon"
    assert built[1]["content"] == "hi"


async def test_only_api_approved_keys_survive(fake_channel):
    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()
    await seed(
        ctx,
        [
            {
                "role": "user",
                "content": "hi",
                "timestamp": 123,  # legacy top-level field
                "_metadata": {"timestamp": 123},
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "1",
                        "function": {"name": "x", "arguments": "{}"},
                        "_metadata": {"timestamp": 5},
                    }
                ],
            },
        ],
    )

    built = await ctx.get()

    assert set(built[0].keys()) == {"role", "content"}
    # assistant with tool calls but no content: content key removed entirely
    assert "content" not in built[1]
    assert "_metadata" not in built[1]["tool_calls"][0]


async def test_null_content_normalized(fake_channel):
    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()
    await seed(
        ctx,
        [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "1"}],
            },
        ],
    )

    built = await ctx.get()

    assert "content" not in built[1]


@pytest.mark.xfail(
    strict=True,
    reason="suspected bug: Context.get() null-content normalization has a "
    "misplaced continue - the message is only appended in the assistant "
    "branch, so user/tool messages with content None are dropped from the "
    "context entirely instead of being normalized to content '' like the "
    "comment specifies (TEST_PLAN.md section 5, finding 9)",
)
async def test_null_content_user_message_becomes_empty_string(fake_channel):
    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()
    await seed(ctx, [{"role": "user", "content": None}])

    built = await ctx.get()

    assert built[0]["content"] == ""


async def test_spacers_enforce_turn_order(fake_channel):
    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()
    await seed(
        ctx,
        [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "assistant", "content": "a2"},
            {"role": "user", "content": "u2"},
            {"role": "user", "content": "u3"},
        ],
    )

    built = await ctx.get()

    roles = [m["role"] for m in built]
    assert roles == [
        "user",
        "assistant",
        "user",  # spacer between a1/a2
        "assistant",
        "user",
        "assistant",  # spacer between u2/u3
        "user",
    ]
    assert built[2] == {"role": "user", "content": " "}
    assert built[5] == {"role": "assistant", "content": " "}


async def test_tool_groups_need_assistant_bridge(fake_channel):
    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()
    await seed(
        ctx,
        [
            {"role": "user", "content": "u1"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "1"}],
            },
            {"role": "tool", "tool_call_id": "1", "content": "result"},
            {"role": "user", "content": "u2"},
        ],
    )

    built = await ctx.get()

    roles = [m["role"] for m in built]
    # tool -> user needs an assistant spacer
    assert roles == ["user", "assistant", "tool", "assistant", "user"]


# ---------------------------------------------------------------------------
# eviction / trimming / overflow
# ---------------------------------------------------------------------------

async def test_eviction_rounds_to_evict_block_and_skips_tool_groups(fake_channel):
    ctx = setup_context(
        fake_channel, api={"max_messages": 4, "evict_block": 2, "max_context": 16768}
    )
    await ctx.chat.autoload()
    await seed(
        ctx,
        [
            {"role": "user", "content": "m1"},
            {"role": "assistant", "content": "m2"},
            {"role": "user", "content": "m3"},
            {"role": "assistant", "content": "m4"},
            {"role": "tool", "tool_call_id": "1", "content": "t1"},
            {"role": "tool", "tool_call_id": "2", "content": "t2"},
            {"role": "user", "content": "m7"},
            {"role": "assistant", "content": "m8"},
        ],
    )

    built = await ctx.get()

    # overflow 4 -> drop 4 -> messages[4] is a tool result, so the drop
    # slides forward past the whole tool group
    contents = [m.get("content") for m in built]
    assert "m7" in contents and "m8" in contents
    assert "m1" not in contents and "m4" not in contents and "t1" not in contents


async def test_trim_binary_search_keeps_summary_and_recent(fake_channel):
    ctx = setup_context(fake_channel, api={"max_context": 400})
    await ctx.chat.autoload()
    history = [cutoff(), {"role": "assistant", "content": "THE SUMMARY"}]
    for i in range(10):
        role = "user" if i % 2 == 0 else "assistant"
        history.append({"role": role, "content": f"msg{i} " + "y" * 200})
    await seed(ctx, history)

    built = await ctx.get()

    assert built[0] == {"role": "user", "content": "THE SUMMARY"}
    assert built[-1]["content"].startswith("msg9")
    assert len(built) < 11  # something was trimmed


async def test_overflow_returns_none_and_warns_once(fake_channel):
    ctx = setup_context(fake_channel, api={"max_context": 200})
    await ctx.chat.autoload()
    fake_channel.manager.modules = {"identity": PromptModule(prompt="S" * 4000)}

    assert await ctx.get() is None
    assert len(fake_channel.pushes) == 1
    assert "exceeds the maximum context size" in fake_channel.pushes[0]

    # second call must not spam the user
    assert await ctx.get() is None
    assert len(fake_channel.pushes) == 1


async def test_trim_false_measures_raw_context(fake_channel):
    ctx = setup_context(fake_channel, api={"max_context": 200})
    await ctx.chat.autoload()
    fake_channel.manager.modules = {"identity": PromptModule(prompt="S" * 4000)}

    built = await ctx.get(trim=False)

    assert built is not None
    assert built[0]["content"].startswith("# Identity")


# ---------------------------------------------------------------------------
# reasoning handling
# ---------------------------------------------------------------------------

async def test_reasoning_stripped_by_default_kept_when_enabled(fake_channel):
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "thinking aloud", "reasoning_content": "zzz"},
    ]

    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()
    await seed(ctx, msgs)
    built = await ctx.get()
    assert "reasoning_content" not in built[1]

    ctx2 = setup_context(fake_channel, model={"keep_reasoning_in_context": True})
    await ctx2.chat.autoload()
    await seed(ctx2, [dict(m) for m in msgs])
    built2 = await ctx2.get()
    assert built2[1]["reasoning_content"] == "zzz"


async def test_reasoning_only_kept_for_current_agentic_loop(fake_channel):
    ctx = setup_context(
        fake_channel,
        model={
            "keep_reasoning_in_context": True,
            "only_preserve_reasoning_for_current_agentic_loop": True,
        },
    )
    await ctx.chat.autoload()
    await seed(
        ctx,
        [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "1"}],
                "reasoning_content": "old thoughts",
            },
            {"role": "tool", "tool_call_id": "1", "content": "r"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "2"}],
                "reasoning_content": "fresh thoughts",
            },
        ],
    )
    fake_channel.agentic_loop_start = 2

    built = await ctx.get()

    toolcall_msgs = [m for m in built if m.get("tool_calls")]
    assert "reasoning_content" not in toolcall_msgs[0]
    assert toolcall_msgs[1]["reasoning_content"] == "fresh thoughts"


# ---------------------------------------------------------------------------
# token accounting
# ---------------------------------------------------------------------------

async def test_count_tokens_exempt_multimodal_payload(fake_channel):
    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()

    def payload(url):
        return [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": url}},
                    {"type": "text", "text": "same text"},
                ],
            }
        ]

    small = await ctx.count_tokens(payload("short"))
    huge = await ctx.count_tokens(payload("y" * 4000))
    assert small == huge  # image payloads are exempt

    textier = [{"role": "user", "content": "same text " + "z" * 4000}]
    assert await ctx.count_tokens(textier) > small


async def test_api_usage_is_source_of_truth_plus_delta_estimate(fake_channel):
    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()
    await seed(ctx, [{"role": "user", "content": "measured"}])

    await ctx.record_api_usage(1000)

    assert await ctx.get_total_tokens() == 1000

    # a message added after the measurement is only estimated
    await ctx.chat.messages.add({"role": "user", "content": "added later"})
    stripped = {k: v for k, v in (await ctx.chat.messages.get(1)).items() if k != "_metadata"}
    expected = 1000 + await ctx.count_tokens([stripped])

    assert await ctx.get_total_tokens() == expected


async def test_is_over_threshold(fake_channel):
    ctx = setup_context(
        fake_channel,
        api={"max_context": 1000},
        model={"automatically_compress_context": True, "context_compression_threshold": 0.5},
    )
    await ctx.chat.autoload()
    await seed(ctx, [{"role": "user", "content": "m"}])

    await ctx.record_api_usage(300)
    assert await ctx.is_over_threshold() is False

    await ctx.record_api_usage(600)
    assert await ctx.is_over_threshold() is True

    # feature disabled -> never over threshold
    apply_config(
        api={"max_context": 1000},
        model={
            "use_tools": True,
            "keep_reasoning_in_context": False,
            "only_preserve_reasoning_for_current_agentic_loop": False,
            "automatically_compress_context": False,
            "context_compression_threshold": 0.5,
        },
        modules={"disabled_prompts": []},
    )
    assert await ctx.is_over_threshold() is False


async def test_get_latest_summary(fake_channel):
    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()

    assert await ctx.get_latest_summary() is None

    await seed(
        ctx,
        [
            cutoff(),
            {"role": "assistant", "content": "first summary"},
            cutoff(),
            {"role": "assistant", "content": "second summary"},
        ],
    )
    assert await ctx.get_latest_summary() == "second summary"

    # cutoff with nothing after it has no summary
    await seed(ctx, [cutoff()])
    assert await ctx.get_latest_summary() is None


async def test_get_size_reports_breakdown(fake_channel):
    ctx = setup_context(fake_channel, api={"max_context": 1000})
    await ctx.chat.autoload()
    fake_channel.manager.modules = {"identity": PromptModule(prompt="be nice", end="end")}
    await seed(ctx, [{"role": "user", "content": "hi"}, cutoff()])
    await ctx.record_api_usage(500)

    size = await ctx.get_size()

    assert size["max_context"] == 1000
    assert size["total_tokens"] == 500
    assert size["percent_full"] == 50
    assert size["compaction_count"] == 1
    assert size["system_prompt"]["tokens"] > 0
    assert size["message_history"]["tokens"] >= 0


# ---------------------------------------------------------------------------
# compress
# ---------------------------------------------------------------------------

async def test_compress_appends_cutoff_and_summary(fake_channel, fake_api):
    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()
    await seed(ctx, [{"role": "user", "content": "do the thing"}])
    await ctx.chat.set("token_usage", 999)
    fake_api.queue_stream([{"content": "SUMMARY ONE"}])

    result = await ctx.compress()

    assert result["content"] == "SUMMARY ONE"
    history = await ctx.chat.messages.get()
    assert history[-2]["_metadata"]["signal"] == "SUMMARIZATION_CUTOFF"
    assert history[-1]["content"] == "SUMMARY ONE"
    # the old raw history is still there: compression is non-destructive
    assert history[0]["content"] == "do the thing"
    # stale API measurement invalidated
    assert ctx.chat.data[ctx.chat.current]["token_usage"] == 0

    # the summarization request pins the active user request
    sent_prompt = fake_api.sent[-1]["context"][-1]["content"]
    assert "ACTIVE USER REQUEST" in sent_prompt
    assert "do the thing" in sent_prompt


async def test_compress_merges_previous_summary(fake_channel, fake_api):
    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()
    await seed(
        ctx,
        [
            {"role": "user", "content": "old thing"},
            cutoff(),
            {"role": "assistant", "content": "PREVIOUS SUMMARY BODY"},
            {"role": "user", "content": "new thing"},
        ],
    )
    fake_api.queue_stream([{"content": "MERGED"}])

    result = await ctx.compress()

    assert result["content"] == "MERGED"
    sent_prompt = fake_api.sent[-1]["context"][-1]["content"]
    assert "PREVIOUS HANDOFF SUMMARY" in sent_prompt
    assert "PREVIOUS SUMMARY BODY" in sent_prompt


async def test_compress_falls_back_to_reasoning(fake_channel, fake_api):
    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()
    await seed(ctx, [{"role": "user", "content": "hi"}])
    fake_api.queue_stream([{"content": "", "reasoning_content": "thought summary"}])

    result = await ctx.compress()

    assert result["content"] == "thought summary"
    history = await ctx.chat.messages.get()
    assert history[-1]["content"] == "thought summary"


async def test_compress_without_content_returns_false(fake_channel, fake_api):
    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()
    await seed(ctx, [{"role": "user", "content": "hi"}])
    fake_api.queue_stream([])  # empty stream -> empty response

    assert await ctx.compress() is False
    # no cutoff marker on failure
    history = await ctx.chat.messages.get()
    assert not any(
        m.get("_metadata", {}).get("signal") == "SUMMARIZATION_CUTOFF" for m in history
    )


async def test_compress_guard_blocks_recursion(fake_channel):
    ctx = setup_context(fake_channel)
    await ctx.chat.autoload()

    ctx.compressing = True
    assert await ctx.compress() is False
    assert fake_channel.manager.API.sent == []
