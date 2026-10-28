# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
core/turns.py - lenient JSON, turn hashing and turn grouping.

key intent (explicitly commented in the code): turns must NEVER mutate the
stored chat messages - annotations live on copies and under `_metadata`, so
re-rendering history can't invalidate the provider-side prompt cache.
"""

import copy
from types import SimpleNamespace

import pytest

import core

from core.turns import TurnCollector, parse_lenient_json, turn_hash
from harness import FakeChannel


# ---- parse_lenient_json ----------------------------------------------------

def test_lenient_json_empty_inputs_give_empty_dict():
    assert parse_lenient_json("") == {}
    assert parse_lenient_json("   ") == {}
    assert parse_lenient_json(None) == {}
    assert parse_lenient_json(42) == {}


def test_lenient_json_valid_and_partial():
    assert parse_lenient_json('{"a": 1}') == {"a": 1}
    assert parse_lenient_json('{"a": 1, "b": "un') == {"a": 1, "b": "un"}


def test_lenient_json_non_object_becomes_raw():
    # intent (docstring): falls back to {'_raw': text} for non-JSON input -
    # and JSON that is not an object can't be used as tool args either
    assert parse_lenient_json("plain text") == {"_raw": "plain text"}
    assert parse_lenient_json("[1, 2]") == {"_raw": "[1, 2]"}
    assert parse_lenient_json("123") == {"_raw": "123"}


# ---- turn_hash ---------------------------------------------------------------

def _turn(content="hi", role="assistant", extra=None):
    msg = {"index": 0, "role": role, "content": content}
    if extra:
        msg.update(extra)
    return {"role": "assistant", "messages": [msg]}


def test_turn_hash_is_stable_and_content_sensitive():
    assert turn_hash(_turn("hi")) == turn_hash(_turn("hi"))
    assert turn_hash(_turn("hi")) != turn_hash(_turn("hi there"))


def test_turn_hash_changes_with_tool_response_metadata():
    a = _turn("", extra={"tool_calls": [{"id": "1", "_metadata": {"response": "ok"}}]})
    b = _turn("", extra={"tool_calls": [{"id": "1", "_metadata": {"response": "different"}}]})
    assert turn_hash(a) != turn_hash(b)


def test_turn_hash_changes_with_cmd_flag():
    a = _turn("x", extra={"_metadata": {"is_cmd": True}})
    b = _turn("x", extra={"_metadata": {"is_cmd": False}})
    assert turn_hash(a) != turn_hash(b)


# ---- group_history -----------------------------------------------------------

def _sample_history():
    return [
        {"role": "user", "content": "do the thing"},
        {
            "role": "assistant",
            "content": None,
            "reasoning_content": "thinking hard",
            "tool_calls": [
                {"id": "call1", "type": "function",
                 "function": {"name": "demo_tool", "arguments": '{"path": "a/b/c.txt"}'}},
            ],
        },
        {"role": "tool", "tool_call_id": "call1",
         "content": '{"status": "error", "content": "boom"}'},
        {"role": "assistant", "content": "it failed, sorry"},
        {"role": "user", "content": "ok thanks"},
    ]


async def test_group_history_groups_turns_and_indices():
    turns = await TurnCollector().group_history(_sample_history())

    assert [t["role"] for t in turns] == ["user", "assistant", "user"]
    assert turns[0]["first_message_index"] == 0
    assert turns[0]["messages"][0]["index"] == 0
    assert turns[1]["first_message_index"] == 1
    assert turns[1]["last_message_index"] == 3
    assert len(turns[1]["messages"]) == 3
    assert turns[2]["messages"][0]["content"] == "ok thanks"


async def test_group_history_never_mutates_the_input_history():
    # intent (2026-10-13 comments): turns hold COPIES; annotating in place
    # used to rewrite chat storage and bust the provider prompt cache
    history = _sample_history()
    original = copy.deepcopy(history)
    await TurnCollector().group_history(history)
    assert history == original


async def test_group_history_merges_tool_responses_into_calls():
    turns = await TurnCollector().group_history(_sample_history())
    tool = turns[1]["messages"][0]["tool_calls"][0]

    meta = tool["_metadata"]
    assert meta["response"] == '{"status": "error", "content": "boom"}'
    assert meta["failed"] is True
    assert meta["args_parsed"] == {"path": "a/b/c.txt"}
    assert meta["summary"] == "(a/b/c.txt)"
    assert "bridge" not in meta


async def test_group_history_failed_flag_only_for_error_status():
    history = [
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "function": {"name": "t", "arguments": "{}"}},
            {"id": "c2", "function": {"name": "t", "arguments": "{}"}},
            {"id": "c3", "function": {"name": "t", "arguments": "{}"}},
        ]},
        {"role": "tool", "tool_call_id": "c1", "content": '{"status": "success", "content": 1}'},
        {"role": "tool", "tool_call_id": "c2", "content": "not json at all"},
        # c3 has no response at all
    ]
    turns = await TurnCollector().group_history(history)
    tools = turns[1]["messages"][0]["tool_calls"]

    assert tools[0]["_metadata"]["failed"] is False
    assert tools[1]["_metadata"]["failed"] is False  # unparseable -> not failed
    assert tools[2]["_metadata"]["failed"] is False  # no response -> not failed
    assert "response" not in tools[2]["_metadata"]


async def test_group_history_unwraps_bridge_calls():
    history = [
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "function": {"name": "tools_call",
                                      "arguments": '{"name": "some_tool", "params": {"query": "x"}}'}},
        ]},
        {"role": "tool", "tool_call_id": "c1", "content": '{"status": "success"}'},
    ]
    turns = await TurnCollector().group_history(history)
    meta = turns[1]["messages"][0]["tool_calls"][0]["_metadata"]

    assert meta["bridge"] is True
    assert meta["display_name"] == "some_tool"
    assert meta["args_parsed"] == {"query": "x"}
    assert meta["summary"] == "(x)"


async def test_group_history_stamps_hash_and_steps():
    turns = await TurnCollector().group_history(_sample_history())

    for turn in turns:
        assert turn["hash"] == turn_hash(turn)

    assistant = turns[1]
    assert "steps" in assistant and "final_messages" in assistant
    # the tool call is a step; the trailing text answer is final content
    assert len(assistant["steps"]) == 1
    assert assistant["steps"][0]["status"] == "failed"  # its only call failed
    assert [m["content"] for m in assistant["final_messages"]] == ["it failed, sorry"]
    # user turns carry no step data
    assert "steps" not in turns[0]


async def test_group_history_empty_history():
    assert await TurnCollector().group_history([]) == []


# ---- step status ----------------------------------------------------------------

def test_step_status_variants():
    def tool(response=None, failed=False):
        meta = {}
        if response is not None:
            meta["response"] = response
        if failed:
            meta["response"] = '{"status": "error"}'
        return {"_metadata": meta}

    assert TurnCollector._step_status([]) == "thoughts"
    assert TurnCollector._step_status([tool()]) == "running"
    assert TurnCollector._step_status([tool(response="ok")]) == "done"
    assert TurnCollector._step_status([tool(failed=True)]) == "failed"
    assert TurnCollector._step_status([tool(failed=True), tool(response="ok")]) == "done"


# ---- arg formatting helpers ------------------------------------------------------

def test_truncate_arg_short_unchanged():
    assert TurnCollector._truncate_arg("short/path.txt") == "short/path.txt"


def test_truncate_arg_long_path_keeps_tail():
    long_path = "/very/long/" + "x" * 100
    result = TurnCollector._truncate_arg(long_path)
    assert result == ".." + long_path[-68:]


def test_truncate_arg_long_plain_text_keeps_head():
    text = "y" * 100
    assert TurnCollector._truncate_arg(text) == "y" * 69 + ".."


def test_arg_to_string_json_style_booleans_and_nulls():
    assert TurnCollector._arg_to_string("s") == "s"
    assert TurnCollector._arg_to_string(None) == "null"
    assert TurnCollector._arg_to_string(True) == "true"
    assert TurnCollector._arg_to_string(False) == "false"
    assert TurnCollector._arg_to_string({"a": 1}) == '{"a": 1}'
    assert TurnCollector._arg_to_string(7) == "7"


def test_summary_prefers_informative_keys():
    # path beats query beats anything else
    assert TurnCollector._summary_from_args({"query": "q", "path": "/p/f.txt"}) == "(/p/f.txt)"
    assert TurnCollector._summary_from_args({"query": "q", "extra": "e"}) == "(q)"
    # no priority key: first string value wins
    assert TurnCollector._summary_from_args({"zzz": "zval", "aaa": 1}) == "(zval)"
    # empty or raw args render no summary
    assert TurnCollector._summary_from_args({}) == ""
    assert TurnCollector._summary_from_args({"_raw": "junk"}) == ""


# ---- module-owned result summaries ------------------------------------------
#
# on_result_summary asks the module that owns a tool for a one-line result
# hint via its on_tool_summary(name, args, response) hook. Both were private
# _-prefixed names until dev aaddc4d renamed them onto the on_* module-hook
# convention (on_ready / on_user_message / ...), which is also how modules
# document them now. Contract: only consulted once a response exists, bridged
# calls summarize as the wrapped tool, output is flattened to one line capped
# at 120 chars, and any module misbehaviour (crash, garbage) degrades to no
# summary - never a crash.

class SummaryModule:
    def __init__(self, ret="fired!"):
        self.ret = ret
        self.calls = []

    def on_tool_summary(self, name, args, response):
        self.calls.append((name, args, response))
        if isinstance(self.ret, Exception):
            raise self.ret
        return self.ret


def _summary_collector(module, catalog):
    ch = FakeChannel()
    ch.manager.modules["demo"] = module
    ch.tool_loader = SimpleNamespace(catalog=catalog)
    return TurnCollector(ch)


def _rs_tool(name="demo_ping"):
    return {"id": "1", "type": "function", "function": {"name": name}}


def _rs_meta(**extra):
    meta = {"response": '{"status": "success"}', "args_parsed": {"a": 1}}
    meta.update(extra)
    return meta


def test_on_result_summary_needs_a_response():
    mod = SummaryModule()
    tc = _summary_collector(mod, {"demo_ping": {"module": "demo"}})

    assert tc.on_result_summary(_rs_tool(), {"args_parsed": {}}) == ""
    assert mod.calls == []  # hook cost stays out of the streaming path


def test_on_result_summary_happy_path_parses_response_and_passes_args():
    mod = SummaryModule()
    tc = _summary_collector(mod, {"demo_ping": {"module": "demo"}})

    out = tc.on_result_summary(_rs_tool(), _rs_meta())

    assert out == "fired!"
    assert mod.calls == [("demo_ping", {"a": 1}, {"status": "success"})]


def test_on_result_summary_bridged_calls_use_display_name():
    mod = SummaryModule()
    tc = _summary_collector(
        mod, {"tools_call": {"module": "demo"}, "wrapped_tool": {"module": "demo"}}
    )

    out = tc.on_result_summary(
        _rs_tool("tools_call"), _rs_meta(display_name="wrapped_tool")
    )

    assert out == "fired!"
    assert mod.calls[0][0] == "wrapped_tool"


def test_on_result_summary_flattens_and_caps():
    mod = SummaryModule(ret="first line\nsecond line")
    tc = _summary_collector(mod, {"demo_ping": {"module": "demo"}})
    assert tc.on_result_summary(_rs_tool(), _rs_meta()) == "first line"

    long_mod = SummaryModule(ret="x" * 300)
    tc2 = _summary_collector(long_mod, {"demo_ping": {"module": "demo"}})
    assert tc2.on_result_summary(_rs_tool(), _rs_meta()) == "x" * 120


def test_on_result_summary_crashing_module_degrades_to_empty():
    mod = SummaryModule(ret=RuntimeError("hook exploded"))
    tc = _summary_collector(mod, {"demo_ping": {"module": "demo"}})
    assert tc.on_result_summary(_rs_tool(), _rs_meta()) == ""


def test_on_result_summary_empty_hook_answer_is_empty():
    mod = SummaryModule(ret="   ")
    tc = _summary_collector(mod, {"demo_ping": {"module": "demo"}})
    assert tc.on_result_summary(_rs_tool(), _rs_meta()) == ""


def test_on_result_summary_non_json_response_is_passed_raw():
    mod = SummaryModule()
    tc = _summary_collector(mod, {"demo_ping": {"module": "demo"}})

    tc.on_result_summary(_rs_tool(), {"response": "plain text", "args_parsed": {}})

    assert mod.calls[0][2] == "plain text"


def test_on_result_summary_missing_pieces_are_silent():
    # no channel at all (bare collector)
    assert TurnCollector().on_result_summary(_rs_tool(), _rs_meta()) == ""

    # unknown tool name
    mod = SummaryModule()
    tc = _summary_collector(mod, {})
    assert tc.on_result_summary(_rs_tool(), _rs_meta()) == ""
    assert mod.calls == []

    # owning module has no hook
    class NoHook: pass
    tc = _summary_collector(NoHook(), {"demo_ping": {"module": "demo"}})
    assert tc.on_result_summary(_rs_tool(), _rs_meta()) == ""


async def test_group_history_stamps_result_summary():
    mod = SummaryModule(ret="job queued")
    ch = FakeChannel()
    ch.manager.modules["demo"] = mod
    ch.tool_loader = SimpleNamespace(catalog={"demo_ping": {"module": "demo"}})

    history = [
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "function": {"name": "demo_ping", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": '{"status": "success"}'},
    ]
    turns = await TurnCollector(ch).group_history(history)

    meta = turns[1]["messages"][0]["tool_calls"][0]["_metadata"]
    assert meta["result_summary"] == "job queued"
    assert mod.calls == [("demo_ping", {}, {"status": "success"})]


async def test_group_history_running_tool_gets_empty_summary():
    mod = SummaryModule()
    ch = FakeChannel()
    ch.manager.modules["demo"] = mod
    ch.tool_loader = SimpleNamespace(catalog={"demo_ping": {"module": "demo"}})

    history = [
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": "c1", "function": {"name": "demo_ping", "arguments": "{}"}}]},
        # no tool response message yet: the call is still running
    ]
    turns = await TurnCollector(ch).group_history(history)

    meta = turns[1]["messages"][0]["tool_calls"][0]["_metadata"]
    assert meta["result_summary"] == ""
    assert mod.calls == []
