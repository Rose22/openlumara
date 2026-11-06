# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
tests for the test harness itself: the fakes must behave like the real things
they stand in for, so later phases can trust them.
"""

import core

from harness import FakeAPI, FakeChannel, sse_chunks, sse_encode


# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
class _DemoModule(core.module.Module):
    """demo module used to prove the harness can host real core.module classes"""

    # core.modules.get_name() derives the module name from the package the
    # class lives in; classes defined in test files would resolve to None,
    # so pretend we live in a module folder (no import of that name happens)
    __module__ = "modules.demo"

    category = "test"
    settings = {"greeting": {"default": "hi", "description": "test setting"}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ready_ran = False

    async def on_ready(self):
        self.ready_ran = True

    async def greet(self, name: str):
        """greet someone by name"""
        return self.result(f"{self.config.get('greeting')} {name}")


def test_sse_chunks_round_trip_through_real_parser():
    events = [{"a": 1}, {"b": "tëst ✓"}, {"c": [1, 2, 3]}]
    parser = core.http_sse.SSEParser()

    out = []
    # 3-byte chunks guarantee splits inside multibyte characters
    for chunk in sse_chunks(events, split_at=range(1, len(sse_encode(events)), 3)):
        out.extend(parser.feed(chunk))
    out.extend(parser.finish())

    assert out == events
    assert parser.done is False


def test_sse_done_sentinel_ends_the_stream():
    # design intent: feed() returns the events completed before [DONE] and
    # flips parser.done instead of yielding the marker - that is exactly how
    # core.http_sse.iter_events() stops consuming. anything after [DONE] is
    # dropped, since the server said the stream is over.
    parser = core.http_sse.SSEParser()
    out = parser.feed(sse_encode([{"x": 1}, "[DONE]", {"never": "sent"}]))

    assert out == [{"x": 1}]
    assert parser.done is True
    assert parser.feed(b"data: after\n\n") == []
    assert parser.finish() == []


async def test_fake_api_records_calls_and_replays_script():
    api = FakeAPI()
    api.queue_response({"choices": [{"message": {"content": "pong"}}]})
    api.queue_stream([{"content": "hello "}, {"content": "world"}])

    result = await api.send([{"role": "user", "content": "ping"}])
    assert result["choices"][0]["message"]["content"] == "pong"

    tokens = [t async for t in api.send_stream([{"role": "user", "content": "x"}])]
    assert tokens == [{"content": "hello "}, {"content": "world"}]

    assert len(api.sent) == 2
    assert api.sent[0]["context"] == [{"role": "user", "content": "ping"}]


def test_fake_channel_extract_content_mirrors_real_channel():
    channel = FakeChannel()
    assert channel._extract_content({"content": "plain"}) == "plain"
    assert channel._extract_content({"content": [
        {"type": "image_url", "image_url": {"url": "x"}},
        {"type": "text", "text": "caption"},
    ]}) == "caption"
    assert channel._extract_content({"content": None}) == ""
    assert channel._extract_content({}) == ""


async def test_demo_module_runs_on_fake_manager(fake_manager):
    demo = _DemoModule(fake_manager)

    # the isolation fixture's StorageDict config must satisfy ModuleConfig
    assert demo.name == "demo"
    assert demo.config.get("greeting") == "hi"  # schema default fallback

    # _start() runs on_ready, and must NOT spawn a background task because
    # the inherited on_background is an empty coroutine
    started = await demo._start()
    assert started is True
    assert demo.ready_ran is True
    assert fake_manager._async_tasks == set()

    result = await demo.greet("bob")
    assert result == {"status": "success", "content": "hi bob"}


def test_module_config_set_persists_declared_settings(fake_manager, tmp_path, isolate_lumara_paths):
    # intent: a module can change its declared settings at runtime and the change
    # persists to the config file; keys the module never declared are rejected
    # instead of written. production config.load() merges module defaults into the
    # file, so seed the declared key the same way here.
    core.config.config.load({
        "core": {"data_folder": str(isolate_lumara_paths)},
        "modules": {"settings": {"demo": {"greeting": "hi"}}},
    })
    core.config.config.save()

    demo = _DemoModule(fake_manager)
    assert demo.config.get("greeting") == "hi"

    demo.config.set("greeting", "yo")
    assert demo.config.get("greeting") == "yo"
    assert "yo" in (tmp_path / "config.yml").read_text()

    # undeclared keys must never end up in the config file
    demo.config.set("not_a_setting", "x")
    assert "not_a_setting" not in demo.config.config.to_dict()
    assert "not_a_setting" not in (tmp_path / "config.yml").read_text()
