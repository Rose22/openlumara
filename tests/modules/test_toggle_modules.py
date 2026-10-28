# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-26) harness:openlumara status:unreviewed
"""
modules/modules + modules/channel - the module toggler and the channel
instructions prompt.

integration level: real module classes on FakeManager/FakeChannel, plus one
real Channel subclass (core.modules.get_name() demands a class defined in a
channels.* folder).

intent under test:
- Modules.toggle is gated by the unsafe allow_ai_to_toggle setting, can
  never toggle its own module, and reports the manager's verdict.
- its system prompt duplicates the module list only when dynamic tool
  loading is off (otherwise the tool prompt already carries it).
- Channel module prompt: friendly channel names, the no-markdown warning
  for cli/matrix, the available-channels line, tutorial instructions only
  when enabled, and full silence while a character is active.
"""

import types

import pytest

import core
from harness import apply_config
from modules.channel.module import Channel as ChannelPromptModule
from modules.modules.module import Modules as ModulesModule

BASE = {
    "api": {"max_context": 1000},
    "model": {"name": "test-model", "use_tools": True, "dynamic_tool_loading": False},
    "core": {"cmd_prefix": "/"},
}


def configure(module, **settings):
    apply_config(
        modules={"disabled_prompts": [], "settings": {module: settings}}, **BASE
    )


# ---------------------------------------------------------------------------
# modules/modules
# ---------------------------------------------------------------------------

async def make_modules_mod(fake_manager, **settings):
    configure("modules", **settings)
    mod = ModulesModule(fake_manager)
    await mod.on_ready()
    return mod


async def test_toggle_tool_gated_by_unsafe_setting(fake_manager):
    mod = await make_modules_mod(fake_manager)  # allow_ai_to_toggle default False

    assert "toggle" in mod.disabled_tools
    res = await mod.toggle("shell")
    assert res["status"] == "success"
    assert "disabled for security" in res["content"]
    assert fake_manager.toggled_modules == []


async def test_toggle_refuses_to_toggle_itself(fake_manager):
    mod = await make_modules_mod(fake_manager, allow_ai_to_toggle=True)

    out = await mod.toggle("modules")

    assert "user needs to know what you're doing" in out
    assert fake_manager.toggled_modules == []


async def test_toggle_reports_manager_verdict(fake_manager):
    mod = await make_modules_mod(fake_manager, allow_ai_to_toggle=True)

    res = await mod.toggle("calendar")
    assert res["status"] == "success"
    assert "/restart" in res["content"]
    assert fake_manager.toggled_modules == ["calendar"]

    async def unknown(name):
        return False

    fake_manager.toggle_module = unknown
    res = await mod.toggle("ghost")
    assert res["status"] == "error"


async def test_system_prompt_suppressed_under_dynamic_tool_loading(fake_manager):
    mod = await make_modules_mod(fake_manager)

    # dynamic loading sends the module list via the tool prompt already
    apply_config(**{**BASE, "model": {**BASE["model"], "dynamic_tool_loading": True}})
    assert await mod.on_system_prompt() is None

    apply_config(**{**BASE, "model": {**BASE["model"], "dynamic_tool_loading": False},
                    "modules": {"disabled_prompts": [], "enabled": ["memory"],
                                "disabled": ["shell"], "settings": {"modules": {}}}})
    out = await mod.on_system_prompt()
    assert "memory" in out and "shell" in out


async def test_get_help_reads_the_module_structure(fake_manager, monkeypatch):
    mod = await make_modules_mod(fake_manager)

    structure = {"calendar": {"settings": {"x": {}}}}
    monkeypatch.setattr(core.config, "get_module_structure", lambda: structure)

    assert await mod.get_help("calendar") == {"settings": {"x": {}}}

    res = await mod.get_help("ghostmod")
    assert res["status"] == "error"
    assert res["content"] == "That module does not exist"


# ---------------------------------------------------------------------------
# modules/channel
# ---------------------------------------------------------------------------

def make_probe(channel_folder, metadata=None):
    """
    stand-in channel whose class lives in channels.<folder> so that
    core.modules.get_name() resolves it, carrying just the chat metadata
    the module reads.
    """
    chat = types.SimpleNamespace(get=lambda key, default=None: metadata or {})
    cls = type(
        "ProbeChannel",
        (),
        {
            "__module__": f"channels.{channel_folder}",
            "context": types.SimpleNamespace(chat=chat),
        },
    )
    return cls()


@pytest.fixture
async def chanmod(fake_manager):
    configure("channel")
    return ChannelPromptModule(fake_manager)


async def test_channel_prompt_translates_names_and_lists_channels(chanmod):
    apply_config(**{**BASE, "channels": {"enabled": ["webui", "telegram"], "settings": {}}})
    chanmod.channel = make_probe("webui")

    out = await chanmod.on_system_prompt()

    assert "Current channel: WebUI" in out
    assert "Available channels: webui, telegram" in out
    # markdown is fine on the webui
    assert "DO NOT USE MARKDOWN" not in out


async def test_cli_channel_forbids_markdown(chanmod):
    chanmod.channel = make_probe("cli")

    out = await chanmod.on_system_prompt()

    assert "Current channel: Command Line Interface (CLI)" in out
    assert "DO NOT USE MARKDOWN" in out


async def test_unknown_channel_name_passes_through(chanmod):
    chanmod.channel = make_probe("ntfy")

    out = await chanmod.on_system_prompt()

    # no friendly translation exists -> the raw name is used
    assert "Current channel: ntfy" in out


async def test_tutorial_instructions_are_gated(chanmod):
    chanmod.channel = make_probe("webui")

    assert "Instructions for the user" not in (await chanmod.on_system_prompt() or "")

    configure("channel", enable_tutorial_prompts=True)
    out = await chanmod.on_system_prompt()

    assert "Instructions for the user" in out
    assert "Input bar" in out  # the webui instruction block


async def test_silent_while_character_active(chanmod):
    chanmod.channel = make_probe("webui", metadata={"character": "someone"})

    assert await chanmod.on_system_prompt() is None
