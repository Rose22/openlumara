# AI Written: Claude Opus 5.5, reviewed by Claude Fable 5.2
import pytest

from core.http_sse import SSEParser

STREAM = (
    ": keepalive\r\n"
    "\r\n"
    'data: {"text": "h\xe9llo \U0001f600"}\r\n'
    "\r\n"
    "event: delta\n"
    "id: 7\n"
    'data: {"a":\n'
    "data: 1}\n"
    "\n"
    "data: [DONE]\n"
    "\n"
    'data: {"after": "done"}\n'
    "\n"
).encode()

EXPECTED = [
    {"text": "h\xe9llo \U0001f600"},
    {"a": 1, "event": "delta", "id": "7"},
]


def parse(chunks):
    parser = SSEParser()
    events = []
    for chunk in chunks:
        events += parser.feed(chunk)
        if parser.done:
            return events, parser
    return events + parser.finish(), parser


def split_every(data, n):
    return [data[i:i + n] for i in range(0, len(data), n)]


@pytest.mark.parametrize("size", [len(STREAM), 1, 3])
def test_stream_survives_any_chunking(size):
    events, parser = parse(split_every(STREAM, size))
    assert events == EXPECTED
    assert parser.done


def test_split_at_every_position():
    for i in range(len(STREAM)):
        events, _ = parse([STREAM[:i], STREAM[i:]])
        assert events == EXPECTED, f"split at byte {i}"


@pytest.mark.parametrize("chunks", [
    [b'data: {"n": 1}\r\rdata: {"n": 2}\r\r'],
    [b'data: {"n": 1}\r', b'\n\r', b'\ndata: {"n": 2}\r\n\r\n'],  # CRLF split across chunks
    [b'data: {"n": 1}\n\ndata: {"n": 2}\r'],  # lone CR at the very end of the stream
    [b'data: {"n":\r\ndata: 1}\r\n\r\ndata: {"n": 2}\r\n\r\n'],  # multi-line data with CRLF
])
def test_line_terminators(chunks):
    events, _ = parse(chunks)
    assert events == [{"n": 1}, {"n": 2}]


def test_event_without_blank_line_flushed_on_finish():
    parser = SSEParser()
    assert parser.feed(b'data: {"n": 1}\n') == []
    assert parser.finish() == [{"n": 1}]
    assert SSEParser().finish() == []


def test_only_one_leading_space_is_stripped():
    events, _ = parse([b'id:  7\ndata: {}\n\nid:8\ndata: {}\n\n'])
    assert events == [{"id": " 7"}, {"id": "8"}]


def test_json_fields_win_over_sse_fields():
    events, _ = parse([b'event: e\nid: 1\ndata: {"event": "mine", "id": 2}\n\n'])
    assert events == [{"event": "mine", "id": 2}]


def test_non_json_and_empty_events_are_dropped():
    events, _ = parse([b"data: not json\n\nretry: 10\n\n\n\ndata: [1]\n\n"])
    assert events == [{"content": [1]}]


def test_invalid_utf8_raises():
    with pytest.raises(UnicodeDecodeError):
        parse([b"data: \xff\xfe\n\n"])
