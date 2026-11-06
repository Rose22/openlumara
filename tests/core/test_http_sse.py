# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
core/http_sse.py - SSE field parsing.

intent (from the module docstring): implement the field-parsing part of the
SSE spec - LF/CRLF/CR line endings, one leading space after the colon belongs
to the separator, multi-data joined with newlines, empty line completes an
event, comments ignored, [DONE] ends the stream, strict incremental decoding.
"""

import pytest

import core

from harness import sse_encode


def feed_all(chunks):
    """feed a list of byte chunks, return (events, parser)."""
    parser = core.http_sse.SSEParser()
    events = []
    for chunk in chunks:
        events.extend(parser.feed(chunk))
    return events, parser


def test_lf_and_crlf_terminate_lines():
    for terminator in (b"\n", b"\r\n"):
        events, _ = feed_all([b"data: {\"a\": 1}" + terminator + terminator])
        assert events == [{"a": 1}], f"terminator {terminator!r}"


def test_lone_cr_terminates_lines_mid_stream():
    # a CR followed by a non-LF character IS a completed line ending:
    # first CR ends the data line, second CR ends the blank line
    events, _ = feed_all([b"data: {\"a\": 1}\r\rdata: {\"b\": 2}\n\n"])
    assert events == [{"a": 1}, {"b": 2}]


def test_crlf_split_across_chunks_is_one_terminator():
    # a CR at the end of the buffer must NOT end the line yet: the next chunk
    # might start with LF, making it a CRLF pair
    events, parser = feed_all([b"data: {\"a\": 1}\r", b"\n\r\n"])
    assert events == [{"a": 1}]


def test_lone_cr_at_end_of_stream_terminates_line():
    parser = core.http_sse.SSEParser()
    assert parser.feed(b"data: {\"a\": 1}\r") == []
    # at end of stream the pending CR is known to be a lone CR line ending;
    # finish() then also flushes the pending event
    assert parser.finish() == [{"a": 1}]


def test_incomplete_event_flushed_by_finish():
    # some servers end the stream right after the last data line, without the
    # closing blank line - finish() must still deliver the event
    events, parser = feed_all([b"data: {\"a\": 1}\n"])
    assert events == []
    assert parser.finish() == [{"a": 1}]


def test_exactly_one_leading_space_stripped_from_value():
    # per the spec, one space after the colon belongs to the separator; a
    # second space is part of the value (visible here via the id field)
    events, _ = feed_all([b"id:  abc\ndata: {\"a\": 1}\n\n"])
    # exactly one space removed; the second one is part of the value
    assert events == [{"a": 1, "id": " abc"}]


def test_multiple_data_lines_joined_with_newline():
    events, _ = feed_all([b"data: {\"a\":\ndata: 1}\n\n"])
    assert events == [{"a": 1}]


def test_comment_lines_are_ignored():
    events, _ = feed_all([b": keep-alive\n\n"])
    assert events == []


def test_event_and_id_fields_merged_unless_already_present():
    events, _ = feed_all([
        b"event: progress\ndata: {\"x\": 1}\n\n",
        b"event: override\ndata: {\"event\": \"mine\"}\n\n",
    ])
    assert events == [
        {"x": 1, "event": "progress"},
        {"event": "mine"},
    ]


def test_non_dict_json_payload_wrapped_in_content():
    events, _ = feed_all([b"data: 42\n\n"])
    assert events == [{"content": 42}]


def test_non_json_payload_dropped():
    events, _ = feed_all([b"data: this is not json\n\n"])
    assert events == []


def test_done_sentinel_sets_flag_and_drops_followers():
    # design intent: feed() returns events completed BEFORE [DONE] and flips
    # parser.done instead of yielding the marker; iter_events() stops on that
    events, parser = feed_all(
        [b"data: {\"n\": 1}\n\ndata: [DONE]\n\ndata: {\"n\": 2}\n\n"]
    )
    assert events == [{"n": 1}]
    assert parser.done is True
    # once done, further data is ignored by iter_events(); the parser itself
    # stays usable but finish() adds nothing meaningful
    assert parser.finish() == []


def test_multibyte_character_split_across_chunks():
    events, parser = feed_all([b"data: {\"a\": \"\xc3", b"\xa9\"}\n\n"])
    assert events == [{"a": "é"}]
    assert parser.finish() == []


def test_invalid_utf8_raises_instead_of_replacing():
    # intent (class docstring): decoding is strict, invalid utf-8 must raise
    # rather than silently corrupt the payload
    parser = core.http_sse.SSEParser()
    with pytest.raises(UnicodeDecodeError):
        parser.feed(b"data: {\"a\": \"\xff\xfe\"}\n\n")


def test_finish_on_fresh_parser_is_empty():
    parser = core.http_sse.SSEParser()
    assert parser.finish() == []
