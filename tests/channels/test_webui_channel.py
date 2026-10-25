# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-25) harness:openlumara status:unreviewed
"""
channels/webui - Python-side channel helpers touched by recent dev deslop.

These tests cover the behavior that remains testable without starting a server:
websocket origin checks, module extension discovery, session-secret bootstrap,
and the backend-side live turn buffer used by the step stream.
"""

import os
import types

import pytest

import core
from harness import apply_config

# the webui was split into focused modules by the dev refactor (0b7aa12);
# pull each symbol from the module that owns it now
webui_mod = pytest.importorskip("channels.webui.channel")
ws_mod = pytest.importorskip("channels.webui.ws_manager")
server_mod = pytest.importorskip("channels.webui.server")
ext_mod = pytest.importorskip("channels.webui.ui_extensions")
Webui = webui_mod.Webui
WebSocketManager = ws_mod.WebSocketManager


BASE = {
    "api": {"max_context": 1000, "max_messages": 200, "max_output_tokens": 100},
    "model": {
        "name": "test-model",
        "use_tools": False,
        "dynamic_tool_loading": False,
        "automatically_compress_context": False,
    },
    "core": {"cmd_prefix": "/"},
}


class FakeConfig:
    def __init__(self, value):
        self.value = value

    def get(self, key):
        return self.value


class FakeModule:
    def __init__(self, enabled, settings=None):
        self.config = FakeConfig(enabled)
        self.settings = settings or {}


@pytest.fixture
def webui_channel(fake_manager):
    apply_config(
        channels={"settings": {"webui": {"network_mode": "local", "port": 3000}}},
        **BASE,
    )
    return Webui(fake_manager)


def bind(channel, host="127.0.0.1", port=3000):
    channel.host = host
    channel.port = port
    return channel


def test_default_ws_stream_index_is_minus_one(webui_channel):
    assert Webui._ws_stream_index == -1
    assert webui_channel._ws_stream_index == -1


def test_origin_allowed_matches_bound_host(webui_channel):
    channel = bind(webui_channel)

    assert channel._origin_allowed("http://localhost:3000")
    assert channel._origin_allowed("http://127.0.0.1:3000")
    assert not channel._origin_allowed("http://localhost:3001")
    assert not channel._origin_allowed("http://evil.example:3000")


def test_origin_allowed_extra_origin_is_schemeless_by_default(webui_channel):
    channel = bind(webui_channel)
    channel.config.set("extra_allowed_origins", ["crystal-ai:8006"])

    assert channel._origin_allowed("https://crystal-ai:8006")
    assert channel._origin_allowed("http://crystal-ai:8006")
    assert not channel._origin_allowed("https://crystal-ai:9000")
    assert not channel._origin_allowed("https://evil.example:8006")


def test_origin_allowed_extra_origin_can_require_scheme(webui_channel):
    channel = bind(webui_channel)
    channel.config.set("extra_allowed_origins", ["http://crystal-ai:8006"])

    assert channel._origin_allowed("http://crystal-ai:8006")
    assert not channel._origin_allowed("https://crystal-ai:8006")


def test_origin_allowed_wildcard_bind_uses_host_header(webui_channel):
    channel = bind(webui_channel, host="0.0.0.0")

    assert channel._origin_allowed(
        "http://example.com:3000", host_header="example.com:3000"
    )
    assert not channel._origin_allowed(
        "http://evil.example:3000", host_header="example.com:3000"
    )


def test_ui_extension_enabled_ignores_schema_default(webui_channel):
    # Recent dev change: the live config value is the only gate. A module that
    # declares enable_webui_extension=False but has no persisted value yet is
    # still enabled until the user saves the setting.
    mod = FakeModule(None, settings={"enable_webui_extension": {"default": False}})

    assert webui_channel._ui_extension_enabled(mod) is True
    assert webui_channel._ui_extension_enabled(FakeModule(True)) is True
    assert webui_channel._ui_extension_enabled(FakeModule(False)) is False


def test_ext_module_config_exposes_declared_settings(webui_channel):
    mod = types.SimpleNamespace(
        settings={"greeting": {}, "port": {}},
        config=types.SimpleNamespace(get=lambda key: f"v-{key}"),
    )

    assert webui_channel._ext_module_config(mod) == {
        "greeting": "v-greeting",
        "port": "v-port",
    }


def test_ui_extension_dirs_uses_package_path_and_extension_gate(
    webui_channel, tmp_path, monkeypatch
):
    template_dir = tmp_path / "demo" / "webui" / "templates"
    template_dir.mkdir(parents=True)

    pkg = types.SimpleNamespace(__path__=[str(tmp_path)])

    def fake_import(name):
        if name == "modules":
            return pkg
        raise ImportError

    monkeypatch.setattr(ext_mod.importlib, "import_module", fake_import)
    apply_config(
        channels={"settings": {"webui": {"network_mode": "local", "port": 3000}}},
        modules={"enabled": ["demo"]},
        **BASE,
    )

    webui_channel.manager.modules = {"demo": FakeModule(True)}
    assert webui_channel._ui_extension_dirs() == {"demo": str(template_dir)}

    webui_channel.manager.modules = {"demo": FakeModule(False)}
    assert webui_channel._ui_extension_dirs() == {}


async def test_on_ready_generates_persists_and_reuses_session_secret(
    webui_channel, monkeypatch
):
    async def fake_create_fastapi(channel):
        return types.SimpleNamespace()

    monkeypatch.setattr(server_mod, "create_fastapi", fake_create_fastapi)

    # The current bootstrap intentionally does not read the old config value.
    # It only uses the data-folder secret file, creating it when missing.
    webui_channel.config.set("session_secret", "legacy-secret")

    await webui_channel.on_ready()

    secret_file = core.get_data_path("webui_session_secret")
    assert os.path.exists(secret_file)

    with open(secret_file, "r", encoding="utf-8") as f:
        persisted = f.read()

    assert persisted == webui_channel.session_secret_value
    assert persisted != "legacy-secret"
    assert oct(os.stat(secret_file).st_mode & 0o777) == "0o600"

    await webui_channel.on_ready()
    assert webui_channel.session_secret_value == persisted


def test_websocket_manager_records_step_and_final_snapshots():
    ws = WebSocketManager(None)

    step = {"step": 2, "content": "partial"}
    ws.record_step_snapshot(step)
    assert ws.turn_steps == {2: step}

    final = [{"step": 2, "content": "final"}]
    ws.record_final_snapshot(final)
    assert ws.turn_final == final


async def test_websocket_manager_clears_turn_buffer_on_stream_boundaries():
    ws = WebSocketManager(None)

    ws.turn_steps = {1: {"step": 1}}
    ws.turn_final = [{"step": 1}]
    await ws.set_stream_state("message_sending")
    assert ws.turn_steps == {}
    assert ws.turn_final == []

    ws.turn_steps = {1: {"step": 1}}
    ws.turn_final = [{"step": 1}]
    await ws.set_stream_state("idle")
    assert ws.turn_steps == {}
    assert ws.turn_final == []
