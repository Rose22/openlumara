# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
lightweight fakes for the manager/channel/api objects that core classes expect.

most core classes only use a handful of attributes of their manager or channel,
so these fakes implement exactly what is used - plus recording, so tests can
assert on what happened. they deliberately do NOT implement the rest: if a test
touches an attribute that doesn't exist here, that's useful signal that the
real class has a dependency worth discussing (add it to the fake on purpose).
"""

import json
import os
import pathlib
import types

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def repo_state():
    """
    snapshot of everything the test suite must never modify in a live install:
    the data/ tree, config.yml and .module_cache.json.
    returns {relpath: (mtime_ns, size)}; used by the phase 0 smoke test and
    by the isolation assertions elsewhere.
    """
    manifest = {}

    data_dir = REPO_ROOT / "data"
    if data_dir.exists():
        for dirpath, _dirs, files in os.walk(data_dir):
            for fname in files:
                p = pathlib.Path(dirpath) / fname
                st = p.stat()
                manifest[str(p.relative_to(REPO_ROOT))] = (st.st_mtime_ns, st.st_size)

    for special in ("config.yml", ".module_cache.json"):
        p = REPO_ROOT / special
        if p.exists():
            st = p.stat()
            manifest[special] = (st.st_mtime_ns, st.st_size)

    return manifest


class FakeAPI:
    """
    scripted stand-in for core.api.APIClient.

    core.context.Context.get() reads .connected / .supports_developer_role and
    calls .connect() when not connected, so those exist as plain attributes.
    queue responses/streams, then assert on .sent afterwards.

    also fakes the connection-status and model-switching surface
    (get_status/get_model/list_models/set_model) that core.commands and
    modules/models read, mirroring the real APIClient contract.
    """

    def __init__(self):
        self.connected = True
        self.supports_developer_role = False
        self.cancel_request = False

        self.sent = []          # one dict per send()/send_stream() call
        self._responses = []    # queued send() results (FIFO)
        self._streams = []      # queued send_stream() token lists (FIFO)

        # model-switching surface (read by modules/models)
        self.model_name = "test-model"
        self.available_models = []
        self.list_models_calls = 0

    def queue_response(self, response):
        self._responses.append(response)

    def queue_stream(self, tokens):
        self._streams.append(list(tokens))

    async def connect(self, silent=False):
        return True

    async def attempt_connect(self):
        return True

    async def disconnect(self):
        self.connected = False
        return True

    async def reconnect(self):
        return True

    def get_status(self):
        # mirrors core.api.APIClient.get_status
        return {"connected": self.connected, "url": "http://fake.test/v1", "model": self.model_name}

    def get_model(self):
        return self.model_name

    async def list_models(self):
        self.list_models_calls += 1
        return list(self.available_models)

    def set_model(self, name):
        self.model_name = name

    async def send(self, context, **kwargs):
        self.sent.append({"context": context, **kwargs})
        if self._responses:
            return self._responses.pop(0)
        return {"choices": [{"message": {"content": ""}}]}

    async def send_stream(self, context, **kwargs):
        self.sent.append({"context": context, **kwargs})
        tokens = self._streams.pop(0) if self._streams else []
        for token in tokens:
            yield token

    async def cancel(self):
        self.cancel_request = True


class FakeManager:
    """minimal stand-in for core.manager.Manager (see TEST_PLAN.md section 1.3)."""

    def __init__(self, api=None):
        self.API = api if api is not None else FakeAPI()
        self.modules = {}
        self.channels = {}
        self.tools = []

        # read by core.chat.Chat.get_system_prompt()
        self.pure_mode = False
        self.broken_modules = []

        # read by core.api.APIClient._connect_setup
        self.args = types.SimpleNamespace(insecure_tls=False)

        self.logs = []    # (category, message) tuples from log()
        self.errors = []  # (message, exception) tuples from log_error()

        self.toggled_modules = []
        self.toggled_channels = []
        self.reloaded_modules = []
        self.restarts = 0

        # Module._start() registers background tasks on these
        self._async_tasks = set()

    @property
    def tool_names(self):
        return [t["function"]["name"] for t in self.tools]

    def log(self, category, message):
        self.logs.append((category, message))

    def log_error(self, message, e):
        self.errors.append((message, e))

    def _remove_async_task(self, task):
        self._async_tasks.discard(task)

    # lifecycle surface used by core.commands (/module, /channel, /restart,
    # /config module reloads) - recorded so tests can assert on it
    async def toggle_module(self, module_name):
        self.toggled_modules.append(module_name)
        return True

    async def toggle_channel(self, channel_name):
        self.toggled_channels.append(channel_name)
        return True

    async def reload_module(self, module_name):
        self.reloaded_modules.append(module_name)

    async def restart(self):
        self.restarts += 1


class FakeChannel:
    """
    minimal stand-in for core.channel.Channel.

    exposes exactly what core.context / core.toolcalls read today:
    manager, agentic_loop_start, push(), log()/log_error(), _extract_content().
    """

    def __init__(self, manager=None):
        self.manager = manager if manager is not None else FakeManager()
        self.name = "fake"
        self.agentic_loop_start = 0

        self.logs = []    # (category, message) tuples
        self.pushes = []  # everything passed to push()
        self.push_calls = []  # (message, defer) tuples

        # core.messages.Messages.add() and core.chat.Chat.new() go through
        # channel.context; default to a stub, tests replace it with a real
        # core.context.Context when they want the real thing.
        self.context = FakeContext()

        # export() uses these; tests assign real core.turns/core.toolcalls
        # objects when they exercise export.
        self.turncollector = None
        self.tc_manager = None

    def log(self, category, message):
        self.logs.append((category, message))

    def log_error(self, message, e):
        self.logs.append(("error", f"{message}: {e}"))

    async def push(self, message, defer=True):
        self.pushes.append(message)
        self.push_calls.append((message, defer))

    async def push_stream(self, stream, **kwargs):
        """
        consume an async token stream and return a finalized response dict,
        mirroring what core.channel.Channel.push_stream returns to callers
        like core.context.Context.compress().
        """
        content = ""
        reasoning = ""
        async for token in stream:
            if isinstance(token, dict):
                content += token.get("content") or ""
                reasoning += token.get("reasoning_content") or ""
            else:
                content += str(token)
        return {"role": "assistant", "content": content, "reasoning_content": reasoning}

    def _extract_content(self, message_dict):
        """mirrors core.channel.Channel._extract_content - keep in sync!"""
        content = message_dict.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    return item.get("text")
        return ""


def sse_encode(events):
    """join a list of payload dicts / raw strings into one raw SSE byte stream."""
    parts = []
    for ev in events:
        payload = ev if isinstance(ev, str) else json.dumps(ev)
        parts.append(f"data: {payload}\n\n".encode("utf-8"))
    return b"".join(parts)


def sse_chunks(events, split_at=None):
    """
    encode events as raw SSE bytes, optionally cut into chunks at byte offsets.

    split_at lets tests place chunk boundaries anywhere - including inside a
    multibyte character - to exercise core.http_sse.SSEParser's incremental
    decoder. pass e.g. list(range(1, len(sse_encode(events)), 3)) to chunk
    aggressively.
    """
    raw = sse_encode(events)
    if not split_at or not raw:
        return [raw] if raw else []

    cuts = sorted({c for c in split_at if 0 < c < len(raw)})
    chunks = []
    prev = 0
    for c in cuts:
        chunks.append(raw[prev:c])
        prev = c
    chunks.append(raw[prev:])
    return chunks


class FakeContext:
    """
    stub for core.context.Context, used by Chat/Messages code paths that
    call channel.context.get_total_tokens()/is_over_threshold()/compress().
    tests flip the knobs; nothing here talks to the API.
    """

    def __init__(self):
        self.total_tokens = 0
        self.over_threshold = False
        self.compress_calls = 0
        self.compress_result = {"content": "compressed"}

    async def get_total_tokens(self):
        return self.total_tokens

    async def is_over_threshold(self):
        return self.over_threshold

    async def compress(self):
        self.compress_calls += 1
        return self.compress_result


def apply_config(**sections):
    """
    rewrite the isolated test config (installed by conftest) with the given
    top-level sections, keeping core.data_folder intact.

    note: core.config.get() returns the raw user config once one is loaded -
    schema defaults are NOT merged in - so tests that need e.g. api.max_context
    must set it explicitly.

    the merged dict is deep-copied before loading: StorageDict stores the very
    objects it is given, and code like /config's setter mutates the live
    config in place - without a copy, shared test constants (BASE dicts)
    would slowly corrupt across tests.
    """
    import copy

    import core

    cfg = core.config.config
    data_folder = cfg.get("core", {}).get("data_folder")
    merged = {"core": {"data_folder": data_folder}}
    for key, value in sections.items():
        if key == "core":
            merged["core"].update(value)
        else:
            merged[key] = value
    cfg.load(copy.deepcopy(merged))
    cfg.save()
    return merged
