# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
core/commands.py - CLI/chat command parsing.

intent: _convert_type turns CLI strings that are MEANT to be typed values
(bools/ints/floats) into Python types for /config, everything else stays a
string. _extract_cmd splits prefixed commands with shell-style quoting.
cmd_library renders /library output purely from the module manager.
"""

import pytest

import core
from core.commands import Commands, _convert_type


# ---- _convert_type ----------------------------------------------------

@pytest.mark.parametrize("value", ["true", "True", "TRUE", "on", "On"])
def test_convert_type_truthy_words(value):
    assert _convert_type(value) is True


@pytest.mark.parametrize("value", ["false", "False", "FALSE", "off", "Off"])
def test_convert_type_falsy_words(value):
    assert _convert_type(value) is False


def test_convert_type_ints():
    assert _convert_type("42") == 42
    assert _convert_type("-7") == -7
    assert _convert_type("0") == 0


def test_convert_type_floats():
    assert _convert_type("3.5") == 3.5
    assert _convert_type("-0.25") == -0.25
    # scientific notation is a number as far as float() is concerned
    assert _convert_type("1e3") == 1000.0


def test_convert_type_leaves_plain_strings_alone():
    for value in ("hello", "0x10", "some/url/v1", ""):
        assert _convert_type(value) == value


# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
# FINDING (2026-10-25): _convert_type lets float()'s acceptance of the magic
# words "nan"/"inf"/"-inf" leak through: /config model temperature nan would
# store float('nan'). The function's purpose is converting strings that are
# *meant* to be numbers; these are not. Intended: stay strings.
@pytest.mark.xfail(
    strict=True,
    reason="suspected bug: float() magic words 'nan'/'inf' are converted to "
           "floats instead of staying strings",
)
@pytest.mark.parametrize("value", ["nan", "NaN", "inf", "-inf"])
def test_convert_type_magic_float_words_stay_strings(value):
    assert _convert_type(value) == value


# ---- _extract_cmd -------------------------------------------------------

async def test_extract_cmd_basic(fake_channel):
    cmd = Commands(fake_channel)
    assert await cmd._extract_cmd("/ping hello world") == ("/", "ping", ["hello", "world"])


async def test_extract_cmd_shell_style_quoting(fake_channel):
    cmd = Commands(fake_channel)
    prefix, name, args = await cmd._extract_cmd('/chat rename "two words" tail')
    assert (prefix, name, args) == ("/", "chat", ["rename", "two words", "tail"])


async def test_extract_cmd_non_command_text(fake_channel):
    cmd = Commands(fake_channel)
    assert await cmd._extract_cmd("just chatting") == (None, None, [])


async def test_extract_cmd_unbalanced_quotes_is_not_a_command(fake_channel):
    # intent: shlex failures must degrade to "normal message", not crash
    cmd = Commands(fake_channel)
    assert await cmd._extract_cmd('/chat rename "broken') == (None, None, [])


async def test_extract_cmd_bare_prefix(fake_channel):
    cmd = Commands(fake_channel)
    assert await cmd._extract_cmd("/") == ("/", "", [])


async def test_extract_cmd_custom_prefix(fake_channel, monkeypatch):
    # rewrite the isolated config the way a user setting it would
    core.config.config.load({
        "core": {
            "data_folder": core.config.config["core"]["data_folder"],
            "cmd_prefix": "!",
        },
    })
    core.config.config.save()

    cmd = Commands(fake_channel)
    assert await cmd._extract_cmd("!ping pong") == ("!", "ping", ["pong"])
    assert await cmd._extract_cmd("/ping pong") == (None, None, [])


# ---- _check_if_temporary -----------------------------------------------

def _set_use_tools(value):
    core.config.config.load({
        "core": {
            "data_folder": core.config.config["core"]["data_folder"],
        },
        "model": {"use_tools": value},
    })
    core.config.config.save()


def test_check_if_temporary_ghost_list(fake_channel):
    _set_use_tools(True)
    cmd = Commands(fake_channel)
    assert cmd._check_if_temporary("help") is True  # in Commands.GHOST
    assert cmd._check_if_temporary("some_module_cmd") is False


def test_check_if_temporary_via_module_registry(fake_channel, monkeypatch):
    def temp_handler(args): pass
    temp_handler._is_temporary = True

    monkeypatch.setattr(core.module, "_command_registry",
                        {"mytemp": [(object, temp_handler)]})

    _set_use_tools(True)
    cmd = Commands(fake_channel)
    assert cmd._check_if_temporary("mytemp") is True


def test_check_if_temporary_all_ghost_when_tools_off(fake_channel):
    # intent: with tools disabled the AI can't see any commands anyway, so
    # every command becomes ghost (invisible to the AI)
    _set_use_tools(False)
    cmd = Commands(fake_channel)
    assert cmd._check_if_temporary("some_module_cmd") is True


# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
# ---- cmd_library ---------------------------------------------------------
#
# intent: /library output is built entirely from three ModuleManager calls
# (list_repos / list_libraries / list_available), so a stub manager pins the
# whole rendering. Two properties of the dev aaddc4d format are load-bearing:
# entries group by kind in a fixed order with installed entries first inside
# each group, and no square brackets appear anywhere - the CLI channel prints
# command results through rich with markup enabled, which swallows [text].

class FakeModuleManager:
    """stand-in for core.module_manager.ModuleManager (only what cmd_library reads)."""

    def __init__(self, repos=(), libraries=None, available=()):
        self._repos = list(repos)
        self._libraries = dict(libraries or {})
        self._available = list(available)

    def list_repos(self):
        return list(self._repos)

    def list_libraries(self):
        return dict(self._libraries)

    def list_available(self):
        return list(self._available)


def _lib_cmd(fake_channel, **kwargs):
    # fake_channel is function-scoped, so a plain assign cannot leak into other tests
    fake_channel.manager.module_manager = FakeModuleManager(**kwargs)
    return Commands(fake_channel)


def _entry(name, library="acme", kind="module", doc="", installed=False):
    return {"library": library, "name": name, "type": kind, "doc": doc,
            "installed": installed}


async def test_library_no_args_lists_repos_and_cloned_libraries(fake_channel):
    cmd = _lib_cmd(
        fake_channel,
        repos=["https://example.com/a.git", "git@github.com:b/c.git"],
        libraries={"a": "/tmp/a", "c": "/tmp/c"},
    )

    out = await cmd.cmd_library([])

    assert out.startswith("== content libraries ==\n")
    assert "configured repos:\n  - https://example.com/a.git\n" \
           "  - git@github.com:b/c.git" in out
    # cloned libraries print as a comma list of names, never their paths
    assert "cloned: a, c" in out
    assert out.endswith("install <name> | update <name> | remove <name>")


async def test_library_no_args_shows_setup_hints_when_empty(fake_channel):
    cmd = _lib_cmd(fake_channel)

    assert await cmd.cmd_library([]) == (
        "== content libraries ==\n"
        "no repos configured - add git urls under core -> module_libraries\n"
        "nothing cloned yet - run /library sync\n"
        "\nsubcommands: sync | list | add <git url> | remove <git url> | "
        "install <name> | update <name> | remove <name>"
    )


async def test_library_list_groups_by_kind_in_kind_order(fake_channel):
    # input order is deliberately scrambled: the output order is the contract
    cmd = _lib_cmd(fake_channel, available=[
        _entry("dark", kind="theme", doc="midnight"),
        _entry("zeta", kind="widget"),
        _entry("alpha", kind="widget"),
        _entry("web_search", doc="search the web", installed=True),
        _entry("coder", doc="edit files"),
        _entry("webui", kind="channel"),
        _entry("pdf", kind="skill"),
    ])

    out = await cmd.cmd_library(["list"])

    assert out == "\n".join([
        "== modules ==",
        "  web_search (acme) (installed) - search the web",
        "  coder (acme) - edit files",
        "",
        "== channels ==",
        "  webui (acme)",
        "",
        "== skills ==",
        "  pdf (acme)",
        "",
        "== themes ==",
        "  dark (acme) - midnight",
        "",
        # kinds outside the known order still render, alphabetically, last
        "== widgets ==",
        "  alpha (acme)",
        "  zeta (acme)",
    ])
    # the blank line closing the final group is stripped, and rich markup
    # characters never reach the output
    assert not out.endswith("\n")
    assert "[" not in out and "]" not in out


async def test_library_list_before_any_sync_is_a_single_hint(fake_channel):
    cmd = _lib_cmd(fake_channel)

    assert await cmd.cmd_library(["list"]) == \
        "no installable modules found - run /library sync first"


# ---------------------------------------------------------------------------
# command dispatch + process_input plumbing
#
# These run the real Commands class on a real Channel subclass (real
# Context/Chat/Messages on tmp storage), mirroring test_channel_pipeline.
# ---------------------------------------------------------------------------

import json
import os
import types

import pytest

import core
from core.channel import Channel
from harness import apply_config


BASE = {
    "api": {"max_context": 16768, "max_messages": 200},
    "model": {
        "name": "test-model",
        "use_tools": True,
        "dynamic_tool_loading": False,
        "automatically_compress_context": False,
    },
    "modules": {"disabled_prompts": []},
    "core": {"cmd_prefix": "/", "tool_timeout": 10.0},
}


class CommandsTestChannel(Channel):
    """minimal concrete channel; __module__ gives get_name() 'cmdtest'"""

    __module__ = "channels.cmdtest"

    async def on_push(self, message):
        pass


@pytest.fixture
async def cmd_channel(fake_manager):
    apply_config(**BASE)
    ch = CommandsTestChannel(fake_manager)
    fake_manager.channel = ch  # makes _set_as_active_channel a no-op
    await ch.init()
    yield ch
    await ch._shutdown()


@pytest.fixture
def commands(cmd_channel):
    return Commands(cmd_channel)


async def history(ch):
    return await ch.context.chat.messages.get()


async def test_process_input_passes_through_normal_text(commands, cmd_channel):
    assert await commands.process_input("just chatting") is False
    assert await history(cmd_channel) == []


async def test_process_input_records_both_sides_as_command_exchange(commands, cmd_channel):
    result = await commands.process_input("/ping", authorized=True)

    assert result == "pong!"
    stored = await history(cmd_channel)
    assert [(m["role"], m["content"]) for m in stored] == [
        ("user", "/ping"),
        ("assistant", "pong!"),
    ]
    # /ping is not in GHOST and tools are on -> visible to the AI
    assert all("_metadata" not in m or not m["_metadata"].get("ghost") for m in stored)


async def test_process_input_ghosts_ghost_commands(commands, cmd_channel):
    # /help is in Commands.GHOST: the exchange must be invisible to the AI
    await commands.process_input("/help nonexistent-topic", authorized=True)

    stored = await history(cmd_channel)
    assert [m["_metadata"]["ghost"] for m in stored] == [True, True]


async def test_process_input_ghosts_everything_when_tools_off(commands, cmd_channel):
    apply_config(**{**BASE, "model": {**BASE["model"], "use_tools": False}})

    # with tools off even admin-ish commands only need... still authorized
    await commands.process_input("/ping", authorized=True)

    stored = await history(cmd_channel)
    assert all(m["_metadata"]["ghost"] for m in stored)


async def test_process_input_requires_authorization_for_admin_commands(commands, fake_api):
    with pytest.raises(core.exceptions.UnauthorizedException):
        await commands.process_input("/restart", authorized=False)

    # Commands.PUBLIC_COMMANDS (new/clear/status/stop) work unauthorized;
    # everything else - even the harmless /ping - requires authorization
    assert "ping" not in Commands.PUBLIC_COMMANDS
    with pytest.raises(core.exceptions.UnauthorizedException):
        await commands.process_input("/ping", authorized=False)

    assert "status" in Commands.PUBLIC_COMMANDS
    assert (await commands.process_input("/status", authorized=False)).startswith(
        "== API Status =="
    )


async def test_process_input_refuses_zero_length_command(commands):
    # a bare prefix would dispatch with no name: abort loudly instead
    with pytest.raises(core.exceptions.UnauthorizedException):
        await commands.process_input("/")


async def test_process_input_unknown_command(commands):
    assert await commands._process_input("/nosuchcommand") == "no such command! check /help"


async def test_process_input_wraps_core_command_exceptions(commands, monkeypatch):
    async def boom(args):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(commands, "cmd_ping", boom)

    # the channel must not die: the error text is returned as the result
    # (and the real exception is logged instead of swallowed)
    assert await commands._process_input("/ping") == "error: kaboom"


async def test_process_input_dispatches_module_commands(commands, cmd_channel):
    class FakeMod:
        pass

    async def handler(self, args):
        return f"got {' '.join(args)}"

    handler._is_command = True
    handler._command_name = "modcmd"
    handler._command_description = "a module command"

    inst = FakeMod()
    original = core.module._command_registry
    try:
        core.module._command_registry = dict(original)
        core.module._command_registry["modcmd"] = [(FakeMod, handler)]
        cmd_channel.manager.modules = {"fake": inst}

        assert await commands._process_input("/modcmd hello there") == "got hello there"
    finally:
        core.module._command_registry = original


async def test_process_input_module_command_exception_is_isolated(commands, cmd_channel):
    class FakeMod:
        pass

    async def handler(self, args):
        raise RuntimeError("mod boom")

    handler._is_command = True
    handler._command_name = "modbad"
    handler._command_description = "explodes"

    original = core.module._command_registry
    try:
        core.module._command_registry = dict(original)
        core.module._command_registry["modbad"] = [(FakeMod, handler)]
        cmd_channel.manager.modules = {"fake": FakeMod()}

        # intent: a raising module command must not take down the pipeline.
        # current contract: the exception is logged and the caller is told
        # "no such command" (the fall-through after the except). Surprising
        # wording, but the load-bearing part is that nothing propagates.
        assert await commands._process_input("/modbad x") == "no such command! check /help"
    finally:
        core.module._command_registry = original


# ---------------------------------------------------------------------------
# chat management commands (real Chat on tmp storage)
# ---------------------------------------------------------------------------

async def test_cmd_ping(commands):
    assert await commands.cmd_ping([]) == "pong!"


async def test_cmd_new_starts_a_fresh_chat(commands, cmd_channel):
    before = cmd_channel.context.chat.get("id")

    assert await commands.cmd_new([]) == "New session started."
    assert cmd_channel.context.chat.get("id") != before


async def test_cmd_clear_wipes_history(commands, cmd_channel):
    await cmd_channel.context.chat.messages.add({"role": "user", "content": "remember me"})

    assert await commands.cmd_clear([]) == "Chat history wiped."
    assert await history(cmd_channel) == []


async def seed_chats(cmd_channel, count):
    """create `count` extra chats with deterministic updated ordering"""
    chat = cmd_channel.context.chat
    for i in range(count):
        await chat.new()
        await chat.set("title", f"seed {i}")
    # make ordering independent of wall-clock collisions
    for i, entry in enumerate(chat.data):
        entry["updated"] = f"2026-01-{i + 1:02d}T00:00:00"
    await chat.save()
    return chat


async def test_cmd_chats_paginates_by_ten(commands, cmd_channel):
    await seed_chats(cmd_channel, 12)  # + the initial chat = 13 entries

    page1 = await commands.cmd_chats([])
    assert "(page 1/2, showing 1-10 of 13)" in page1
    assert page1.count("\n- [") == 10

    page2 = await commands.cmd_chats(["2"])
    assert "(page 2/2, showing 11-13 of 13)" in page2
    # numbering is the global position, not per-page
    assert "- [11]" in page2 and "- [13]" in page2


async def test_cmd_chats_page_number_edge_cases(commands, cmd_channel):
    await seed_chats(cmd_channel, 1)

    # garbage page arg falls back to page 1
    assert "(page 1/" in await commands.cmd_chats(["banana"])
    # zero/negative clamp to page 1
    assert "(page 1/" in await commands.cmd_chats(["0"])
    assert "(page 1/" in await commands.cmd_chats(["-3"])
    # beyond the last page clamps to the last page
    total = len(cmd_channel.context.chat.data)
    pages = (total + 9) // 10
    assert f"(page {pages}/" in await commands.cmd_chats(["999"])


async def test_cmd_chat_info_without_args(commands, cmd_channel):
    chat = cmd_channel.context.chat
    await chat.set("title", "my chat")
    await chat.set("category", "work")

    out = await commands.cmd_chat([])

    assert out.startswith("== chat info ==")
    assert "title: my chat" in out
    assert "category: work" in out
    assert "tags: None" in out


async def test_cmd_chat_rename_and_category(commands, cmd_channel):
    assert await commands.cmd_chat(["rename", "two", "words"]) == "chat renamed to two words"
    assert cmd_channel.context.chat.get("title") == "two words"

    assert await commands.cmd_chat(["category", "deep", "nested"]) == \
        "chat categorised into deep nested"
    assert cmd_channel.context.chat.get("category") == "deep nested"


async def test_cmd_chat_loads_by_position(commands, cmd_channel):
    chat = await seed_chats(cmd_channel, 2)

    # the freshest seeded chat (position 1) is the current chat after seeding,
    # so load position 2 and check it switches to the second-newest entry
    assert await commands.cmd_chat(["2"]) == "chat loaded"
    assert chat.get("id") == chat.get_all()[1]["id"]


async def test_cmd_chat_load_position_out_of_range(commands, cmd_channel):
    assert await commands.cmd_chat(["0"]) == "chat with that position doesn't exist"
    assert await commands.cmd_chat(["9999"]) == "chat with that position doesn't exist"


async def test_cmd_chat_load_unknown_id_surfaces_as_error(commands, cmd_channel):
    # Chat.load() raises on an unknown id rather than returning falsy, so
    # cmd_chat's "failed to load chat" string is dead code; the dispatcher's
    # per-command try/except is what turns this into a user-visible error
    # instead of killing the pipeline.
    out = await commands._process_input("/chat nosuchchatid")

    assert out.startswith("error:") and "nosuchchatid" not in out  # generic load error


async def test_cmd_search_no_results(commands):
    assert await commands.cmd_search(["nothing", "matches"]) == "no results found"


async def test_cmd_search_finds_message_content(commands, cmd_channel):
    chat = cmd_channel.context.chat
    await chat.messages.add({"role": "user", "content": "the passphrase is marmalade3"})

    out = await commands.cmd_search(["marmalade3"])

    assert "Found these chats containing 'marmalade3':" in out
    assert chat.get("id") in out


# ---------------------------------------------------------------------------
# connection + status commands
# ---------------------------------------------------------------------------

async def test_cmd_connect_short_circuits_when_already_connected(commands, fake_api):
    fake_api.connected = True
    assert await commands.cmd_connect([]) == "Already connected."


async def test_cmd_connect_reports_errors_verbatim(commands, fake_api):
    fake_api.connected = False

    async def failing_connect(silent=False):
        return core.api.APIError("boom town")

    fake_api.connect = failing_connect
    out = await commands.cmd_connect([])
    assert out.startswith("Error while connecting:") and "boom town" in out

    fake_api.connect = lambda silent=False: _await(True)
    fake_api.connected = False
    assert await commands.cmd_connect([]) == "Connected!"


async def _await(value):
    return value


async def test_cmd_reconnect_and_disconnect(commands, fake_api):
    assert await commands.cmd_reconnect([]) == "Reconnected"

    assert await commands.cmd_disconnect([]) == "Disconnected from API"
    assert fake_api.connected is False


def test_format_context_size_groups_and_separates(commands):
    size = {
        "total_tokens": 12345,
        "max_context": 128000,
        "percent_full": 9,
        "system_prompt": {"tokens": 1500, "words": 250},
        "tools": {"active": 4, "tokens": 800, "words": 130},
        "message_history": {"tokens": 10000, "words": 1700},
        "end_prompt": {"tokens": 20, "words": 5},
    }

    out = commands._format_context_size(size)

    lines = out.splitlines()
    assert lines[0] == "Total: 12,345 / 128,000 tokens (9% full)"
    assert lines[1] == "System prompt: 1,500 tokens | 250 words"
    assert lines[2] == "Tools: 4 active | 800 tokens | 130 words"
    assert lines[3] == "Message history: 10,000 tokens | 1,700 words"
    assert lines[4] == "End prompt: 20 tokens | 5 words"


async def test_cmd_status_connected_includes_context_size(commands, fake_api):
    fake_api.connected = True

    out = await commands.cmd_status([])

    assert "== API Status ==" in out
    assert "Connected: Yes" in out
    assert "Model: test-model" in out
    assert "== Context Size ==" in out
    assert "Total:" in out


async def test_cmd_status_disconnected_skips_context_size(commands, fake_api):
    fake_api.connected = False

    out = await commands.cmd_status([])

    assert "Connected: No" in out
    assert "== Context Size ==" not in out


# ---------------------------------------------------------------------------
# module/channel toggling commands
# ---------------------------------------------------------------------------

async def test_cmd_modules_lists_sections(commands, cmd_channel):
    apply_config(**{**BASE, "modules": {
        "enabled": ["memory"], "disabled": ["shell"], "disabled_prompts": [],
        "settings": {},
    }})
    cmd_channel.manager.modules = {"memory": object()}

    out = await commands.cmd_modules([])

    assert out == "== loaded ==\nmemory\n\n== disabled ==\nshell\n"


async def test_cmd_module_requires_and_validates_name(commands):
    assert await commands.cmd_module([]) == \
        "please provide a name of the module to toggle"
    assert await commands.cmd_module(["ghostmodule"]) == \
        "module with that name doesn't exist"


async def test_cmd_module_toggles_and_reports_new_state(commands, fake_manager):
    apply_config(**{**BASE, "modules": {
        "enabled": ["memory"], "disabled": ["shell"], "disabled_prompts": [],
        "settings": {},
    }})

    out = await commands.cmd_module(["memory"])
    assert out == "module disabled\nrestart required - run /restart"
    assert fake_manager.toggled_modules == ["memory"]

    out = await commands.cmd_module(["shell"])
    # disabled (not enabled) -> toggling enables it
    assert out == "module enabled\nrestart required - run /restart"
    assert fake_manager.toggled_modules == ["memory", "shell"]


async def test_cmd_channel_toggles_known_channels(commands, fake_manager, monkeypatch):
    assert await commands.cmd_channel([]) == \
        "please provide a name of the channel to toggle"

    monkeypatch.setattr(core.channel, "get_available_channels",
                        lambda: ["webui", "telegram"])

    assert await commands.cmd_channel(["ghostchan"]) == \
        "channel with that name doesn't exist"

    apply_config(**{**BASE, "channels": {"enabled": ["webui"], "settings": {}}})
    out = await commands.cmd_channel(["webui"])
    assert out == "channel disabled\nrestart required - run /restart"
    assert fake_manager.toggled_channels == ["webui"]


# ---------------------------------------------------------------------------
# help + tools
# ---------------------------------------------------------------------------

async def test_cmd_help_lists_topics(commands, cmd_channel):
    out = await commands.cmd_help([])

    assert "/help with one of the following topics" in out
    assert "- core" in out
    assert "/help core" in out  # the example mentions the always-present topic


async def test_cmd_help_unknown_topic(commands):
    assert await commands.cmd_help(["nosuchmodule"]) == \
        "that's not a valid topic! check /help"


async def test_cmd_help_core_renders_command_table(commands):
    out = await commands.cmd_help(["core"])

    assert "/ping" in out
    assert "test command that echoes Pong!" in out
    # subcommand defs expand to full names
    assert "/chat rename <name>" in out


async def test_cmd_help_includes_module_commands(commands, cmd_channel):
    class FakeMod:
        pass

    async def handler(self, args):
        return "x"

    handler._is_command = True
    handler._command_name = "modhelp"
    handler._command_description = "helps in a module way"

    original = core.module._command_registry
    try:
        core.module._command_registry = dict(original)
        core.module._command_registry["modhelp"] = [(FakeMod, handler)]
        cmd_channel.manager.modules = {"mymod": FakeMod()}

        topics = await commands.cmd_help([])
        assert "- mymod" in topics

        out = await commands.cmd_help(["mymod"])
        assert "/modhelp" in out and "helps in a module way" in out
    finally:
        core.module._command_registry = original


async def test_cmd_tools_off_globally(commands):
    apply_config(**{**BASE, "model": {**BASE["model"], "use_tools": False}})

    assert await commands.cmd_tools([]) == "Tools are turned off globally."


async def test_cmd_tools_no_args_shows_active_and_catalog(commands, cmd_channel):
    apply_config(**{**BASE, "model": {
        **BASE["model"], "dynamic_tool_loading": True,
    }})
    cmd_channel.manager.tools = [
        {"function": {"name": "memory_create"}},
        {"function": {"name": "memory_edit"}},
        {"function": {"name": "calendar_add_event"}},
    ]
    cmd_channel.tool_loader = types.SimpleNamespace(
        catalog={"shell_exec": {"module": "shell"}},
        active_names=set(),
        tools_load=None,
    )

    out = await commands.cmd_tools([])

    assert "== Active Tools ==" in out
    # tools are grouped by their name prefix, groups sorted alphabetically
    assert out.index("calendar:") < out.index("memory:")
    assert "• calendar_add_event" in out
    # memory groups both memory tools together
    assert "• memory_create" in out and "• memory_edit" in out
    # unloaded catalog entries show under the not-loaded section
    assert "== Available Tools (Not Loaded) ==" in out
    assert "shell_exec" in out


async def test_cmd_tools_load_requires_dynamic_loading(commands, cmd_channel):
    cmd_channel.tool_loader = types.SimpleNamespace(tools_load=None)

    assert await commands.cmd_tools(["load", "shell"]) == \
        "Dynamic tool loading is disabled. All tools are already loaded at startup."


async def test_cmd_tools_load_reports_per_module_result(commands, cmd_channel):
    apply_config(**{**BASE, "model": {
        **BASE["model"], "dynamic_tool_loading": True,
    }})

    async def tools_load(names):
        return {"status": "success"} if names == ["goodmod"] else {"status": "error"}

    cmd_channel.tool_loader = types.SimpleNamespace(tools_load=tools_load)

    out = await commands.cmd_tools(["load", "goodmod"])
    assert "goodmod tools loaded" in out
    assert "Load result for 1 module(s):" in out

    out = await commands.cmd_tools(["load", "badmod"])
    assert "Failed to load badmod tools!" in out


async def test_cmd_tools_unknown_subcommand(commands, cmd_channel):
    cmd_channel.tool_loader = types.SimpleNamespace(tools_load=None)

    out = await commands.cmd_tools(["frobnicate"])
    assert out.startswith("Unknown subcommand: frobnicate")


# ---------------------------------------------------------------------------
# /config
# ---------------------------------------------------------------------------

async def test_cmd_config_no_args_lists_root_categories(commands):
    out = await commands.cmd_config([])

    assert out.startswith("Available settings: ")
    assert "core" in out and "api" in out and "model" in out


async def test_cmd_config_unknown_category(commands):
    # the arg walk refuses any first token that is not a config section
    assert await commands.cmd_config(["bogus"]) == \
        "setting 'bogus' does not exist at that path."


async def test_cmd_config_category_lists_keys(commands):
    out = await commands.cmd_config(["model"])

    assert out.startswith("Available settings in model:")
    assert "name" in out


async def test_cmd_config_leaf_returns_value(commands):
    assert await commands.cmd_config(["model", "name"]) == "test-model"


async def test_cmd_config_set_writes_and_types_values(commands):
    out = await commands.cmd_config(["model", "name", "gpt-next"])

    assert out == "Config updated: model -> name = gpt-next"
    assert core.config.config["model"]["name"] == "gpt-next"

    # numeric strings become typed values, not strings
    out = await commands.cmd_config(["api", "max_context", "4096"])
    assert out == "Config updated: api -> max_context = 4096"
    assert core.config.config["api"]["max_context"] == 4096

    out = await commands.cmd_config(["model", "use_tools", "off"])
    assert core.config.config["model"]["use_tools"] is False


async def test_cmd_config_set_joins_trailing_words_into_one_value(commands):
    # the first non-dict arg ends the path; everything after it is the value
    out = await commands.cmd_config(["model", "name", "two", "words"])

    assert out == "Config updated: model -> name = two words"
    assert core.config.config["model"]["name"] == "two words"


async def test_cmd_config_cannot_write_through_a_group(commands):
    # settings groups can be explored but not written through: the walk
    # refuses args that do not exist under the group
    apply_config(**{**BASE, "model": {**BASE["model"], "nested": {"a": 1}}})

    assert await commands.cmd_config(["model", "nested", "oops"]) == \
        "setting 'oops' does not exist at that path."

    # reading the group lists its keys instead
    out = await commands.cmd_config(["model", "nested"])
    assert out == "Available settings in nested: a"


async def test_cmd_config_unknown_path_argument(commands):
    assert await commands.cmd_config(["model", "nosuchkey", "1"]) == \
        "setting 'nosuchkey' does not exist at that path."


async def test_cmd_config_modules_shortcut_inserts_settings(commands, fake_manager):
    apply_config(**{**BASE, "modules": {
        "enabled": [], "disabled": [], "disabled_prompts": [],
        "settings": {"memory": {"max_pinned_memories": 5}},
    }})

    # /config modules memory max_pinned_memories 10 == /config modules
    # settings memory max_pinned_memories 10
    out = await commands.cmd_config(["modules", "memory", "max_pinned_memories", "10"])

    assert out == "Config updated: modules -> settings -> memory -> max_pinned_memories = 10"
    assert core.config.config["modules"]["settings"]["memory"]["max_pinned_memories"] == 10
    # module settings reload the owning module so it picks the value up live
    assert fake_manager.reloaded_modules == ["memory"]


async def test_cmd_config_module_reload_failure_still_reports_update(commands, fake_manager):
    apply_config(**{**BASE, "modules": {
        "enabled": [], "disabled": [], "disabled_prompts": [],
        "settings": {"memory": {"max_pinned_memories": 5}},
    }})

    async def broken_reload(name):
        raise RuntimeError("reload exploded")

    fake_manager.reload_module = broken_reload

    out = await commands.cmd_config(["modules", "memory", "max_pinned_memories", "10"])

    assert out.startswith("Config updated: modules -> settings -> memory")
    assert "Warning: Failed to reload module 'memory': reload exploded" in out


# ---------------------------------------------------------------------------
# prompts / history / context / export
# ---------------------------------------------------------------------------

class PromptStub:
    def __init__(self, prompt=None, end=None):
        self._prompt = prompt
        self._end = end

    async def on_system_prompt(self):
        return self._prompt

    async def on_end_prompt(self):
        return self._end


async def test_cmd_prompt_blank_without_modules(commands):
    out = await commands.cmd_prompt([])

    assert out.startswith("=== system prompt ===")
    assert "BLANK" in out


async def test_cmd_prompt_shows_module_prompts_and_disabled(commands, cmd_channel):
    cmd_channel.manager.modules = {"greeter": PromptStub(prompt="be nice")}
    # the chat froze its system prompt at creation; drop the cache the way
    # a freshly created chat would start without one
    cmd_channel.context.chat._cached_system_prompt = None
    apply_config(**{**BASE, "modules": {
        "enabled": [], "disabled": [], "disabled_prompts": ["quietmod"],
        "settings": {},
    }})

    out = await commands.cmd_prompt([])


    assert "be nice" in out
    assert "=== disabled prompts ===" in out
    assert "quietmod" in out


async def test_cmd_prompt_for_specific_module(commands, cmd_channel):
    cmd_channel.manager.modules = {
        "greeter": PromptStub(prompt="be nice"),
        "silent": PromptStub(prompt=None),
    }

    assert await commands.cmd_prompt(["greeter"]) == "be nice"
    assert await commands.cmd_prompt(["silent"]) == "BLANK"
    assert await commands.cmd_prompt(["ghostmod"]) == "module not found"


async def test_cmd_prompts_lists_active_prompt_modules(commands, cmd_channel):
    cmd_channel.manager.modules = {
        "greeter": PromptStub(prompt="be nice"),
        "silent": PromptStub(prompt=None),
    }

    out = await commands.cmd_prompts([])

    assert "== modules with active prompts ==" in out
    assert "greeter" in out
    assert "silent" not in out


async def test_cmd_history_respects_context_window_toggle(commands, cmd_channel):
    await cmd_channel.context.chat.messages.add({"role": "user", "content": "hi there"})

    out = await commands.cmd_history([])
    assert "== user ==" in out and "hi there" in out
    assert "== context size ==" in out

    apply_config(**{**BASE, "api": {**BASE["api"], "context_window": False}})
    assert await commands.cmd_history([]) == "CONTEXT DISABLED"


# FINDING (2026-10-26): /history full can never show the system prompt.
# cmd_history deliberately builds the context with system_prompt=True when
# the arg is "full", but it then renders EVERY message through
# Channel.format_message(), which only fills in content for the user/
# assistant/tool roles - the system message comes back with content "".
# The intended output is the prompt text (that is the whole point of "full").
@pytest.mark.xfail(
    strict=True,
    reason="suspected bug: format_message() blanks the system role, so "
           "/history full always renders an empty == system == section",
)
async def test_cmd_history_full_includes_system_prompt(commands, cmd_channel):
    cmd_channel.manager.modules = {"greeter": PromptStub(prompt="be nice")}
    cmd_channel.context.chat._cached_system_prompt = None

    out = await commands.cmd_history(["full"])

    assert "be nice" in out


async def test_cmd_context_dumps_json(commands, cmd_channel):
    await cmd_channel.context.chat.messages.add({"role": "user", "content": "hi"})

    parsed = json.loads(await commands.cmd_context([]))

    assert isinstance(parsed, list)
    assert any(m.get("content") == "hi" for m in parsed)


async def test_cmd_export_writes_titled_file(commands, cmd_channel, isolate_lumara_paths):
    chat = cmd_channel.context.chat
    await chat.set("title", "my big chat")
    await chat.messages.add({"role": "user", "content": "export me please"})

    out = await commands.cmd_export([])

    assert out.startswith("chat exported to ")
    path = out.removeprefix("chat exported to ")
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as f:
        assert "export me please" in f.read()
    # lives under the (tmp) data dir, named with the sanitized title
    assert str(isolate_lumara_paths) in path
    assert "my_big_chat.txt" in os.path.basename(path)


async def test_cmd_restart_and_stop(commands, cmd_channel, fake_api):
    assert await commands.cmd_restart([]) == "restarting server"
    assert cmd_channel.manager.restarts == 1

    assert await commands.cmd_stop([]) == "stopped!"
    assert fake_api.cancel_request is True
