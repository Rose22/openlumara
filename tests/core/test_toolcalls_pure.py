# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
core/toolcalls.py - tool call JSON repair and display formatting (pure parts).

intent: many backends emit slightly broken JSON in tool arguments (the code
comments explain the frustration in detail); we must repair what json_repair
can fix and degrade to {} - never crash the agentic loop. tool call arguments
are always re-serialized as a JSON object string.
"""

import json

import pytest

import core

WRENCH = "\U0001f527"  # the wrench emoji used in call display strings


@pytest.fixture
def manager(fake_channel):
    return core.toolcalls.ToolcallManager(fake_channel)


def _call(arguments):
    return {"id": "c1", "type": "function",
            "function": {"name": "demo", "arguments": arguments}}


# ---- _repair_tool_calls ----------------------------------------------------

def test_repair_normalizes_valid_json(manager):
    (call,) = manager._repair_tool_calls([_call('{"a":1}')])
    assert json.loads(call["function"]["arguments"]) == {"a": 1}


def test_repair_fixes_broken_json(manager):
    # trailing comma: invalid JSON, but json_repair handles it
    (call,) = manager._repair_tool_calls([_call('{"a": 1,}')])
    assert json.loads(call["function"]["arguments"]) == {"a": 1}


def test_repair_accepts_dict_arguments(manager):
    # some routers hand us parsed dicts already; they pass through and get
    # re-serialized as a string
    (call,) = manager._repair_tool_calls([_call({"a": 1})])
    assert isinstance(call["function"]["arguments"], str)
    assert json.loads(call["function"]["arguments"]) == {"a": 1}


def test_repair_degrades_to_empty_dict_for_non_objects(manager):
    # a repaired value that is not an object is useless as kwargs
    (call,) = manager._repair_tool_calls([_call('"just a string"')])
    assert call["function"]["arguments"] == "{}"

    (call,) = manager._repair_tool_calls([_call(5)])  # unexpected type
    assert call["function"]["arguments"] == "{}"
    assert any("unexpected arguments type" in msg for _cat, msg in manager.channel.logs)


def test_repair_multiple_calls_in_order(manager):
    calls = manager._repair_tool_calls([_call('{"n": 1}'), _call('{"n": 2}')])
    assert [json.loads(c["function"]["arguments"])["n"] for c in calls] == [1, 2]


# ---- display_call -----------------------------------------------------------

def test_display_call_formats_name_and_args(manager):
    out = manager.display_call(_call('{"path": "/x/y.txt"}'))
    assert out == f"{WRENCH} demo(path=\"/x/y.txt\")"


def test_display_call_truncates_long_values(manager):
    out = manager.display_call(_call('{"path": "' + "x" * 40 + '"}'))
    assert "x" * 30 + ".." in out
    assert "x" * 31 not in out


def test_display_call_nests_double_quotes_as_single(manager):
    out = manager.display_call(_call('{"query": "say \\"hi\\""}'))
    assert "say 'hi'" in out


def test_display_call_falls_back_without_function_dict(manager):
    assert manager.display_call({"id": "x"}) == f"{WRENCH} Calling tool..."


def test_display_call_survives_unparseable_args(manager):
    # a broken args payload must degrade to a bare "name()", never raise
    out = manager.display_call(_call(5))
    assert out == f"{WRENCH} demo()"
