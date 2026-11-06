# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-26) harness:openlumara status:unreviewed
"""
modules/identity - AI personality prompt + self-editing tools.

integration level: real Identity module on FakeManager with a real Chat on
tmp storage (the module checks chat metadata for an active character).

intent under test:
- the identity text is inserted as the system prompt, unless it is empty or
  a character is active (characters module owns the prompt then).
- the AI may edit/clear its identity through the tool/command unless the
  allow_ai_to_change_identity setting is off, which also unregisters the
  set tool.
"""

import pytest

import core
from harness import apply_config
from modules.identity.module import Identity

BASE = {
    "api": {"max_context": 1000},
    "model": {"name": "test-model", "use_tools": True, "dynamic_tool_loading": False},
    "core": {"cmd_prefix": "/"},
}


def configure(**settings):
    apply_config(
        modules={"disabled_prompts": [], "settings": {"identity": settings}},
        **BASE,
    )


@pytest.fixture
async def chat_ctx(fake_channel):
    """real Chat on the fake channel (tmp storage via conftest)"""
    chat = core.chat.Chat(fake_channel)
    await chat.autoload()
    fake_channel.context.chat = chat
    return chat


async def make_identity(fake_manager, fake_channel, **settings):
    configure(**settings)
    mod = Identity(fake_manager, channel=fake_channel)
    await mod.on_ready()
    return mod


# ---------------------------------------------------------------------------
# system prompt
# ---------------------------------------------------------------------------

async def test_prompt_returns_identity_text(fake_manager, fake_channel, chat_ctx):
    mod = await make_identity(
        fake_manager, fake_channel, identity="You are Lumy, a helpful AI."
    )

    assert await mod.on_system_prompt() == "You are Lumy, a helpful AI."


async def test_prompt_none_when_identity_empty(fake_manager, fake_channel, chat_ctx):
    mod = await make_identity(fake_manager, fake_channel, identity="")

    assert await mod.on_system_prompt() is None


async def test_prompt_none_while_a_character_is_active(fake_manager, fake_channel, chat_ctx):
    mod = await make_identity(
        fake_manager, fake_channel, identity="You are Lumy, a helpful AI."
    )
    await chat_ctx.set("metadata", {"character": "somechar"})

    # the characters module takes over the system prompt entirely
    assert await mod.on_system_prompt() is None


# ---------------------------------------------------------------------------
# editing tools
# ---------------------------------------------------------------------------

async def test_set_tool_writes_identity_config(fake_manager, fake_channel, chat_ctx):
    mod = await make_identity(fake_manager, fake_channel, identity="")

    res = await mod.set("You are Nova.")

    assert res == {"status": "success", "content": True}
    assert mod.config.get("identity") == "You are Nova."
    assert await mod.on_system_prompt() == "You are Nova."


async def test_clear_tool_blanks_identity(fake_manager, fake_channel, chat_ctx):
    mod = await make_identity(fake_manager, fake_channel, identity="You are Nova.")

    res = await mod.clear()

    assert res["status"] == "success"
    assert mod.config.get("identity") == ""
    assert await mod.on_system_prompt() is None


async def test_config_set_is_a_silent_noop_for_unknown_keys(fake_manager, fake_channel, chat_ctx):
    # ModuleConfig.set() refuses to create keys that do not exist in the
    # module's settings section yet. A live install always has them written
    # by the settings system, but the contract is pinned here because the
    # tool still reports success when the write is skipped.
    apply_config(
        modules={"disabled_prompts": [], "settings": {"identity": {}}}, **BASE
    )
    mod = Identity(fake_manager, channel=fake_channel)

    res = await mod.set("You are Ghost.")

    assert res["status"] == "success"
    # nothing was stored: get() falls back to the schema default ""
    assert mod.config.get("identity") == ""


# ---------------------------------------------------------------------------
# command surface
# ---------------------------------------------------------------------------

async def test_cmd_identity_show_set_and_invalid(fake_manager, fake_channel, chat_ctx):
    mod = await make_identity(fake_manager, fake_channel, identity="")

    assert await mod.cmd_set([]) == "You have not yet set up an identity."

    assert await mod.cmd_set(["set", "You", "are", "Sunny."]) == "identity set!"
    assert mod.config.get("identity") == "You are Sunny."
    assert await mod.cmd_set([]) == "You are Sunny."

    assert await mod.cmd_set(["banana"]) == "invalid argument"


# FINDING (2026-10-26): `/identity clear` can never work.
# cmd_set's clear branch does `await self.config.set("identity", "")`, but
# ModuleConfig.set is a plain sync function returning None - awaiting it
# raises TypeError. Via the command dispatcher the user sees "error: object
# NoneType can't be used in 'await' expression" instead of the identity
# being cleared. Fix candidate: drop the await (the tool clear() already
# does it right).
@pytest.mark.xfail(
    strict=True,
    reason="suspected bug: cmd_set awaits the sync ModuleConfig.set, so "
           "'/identity clear' dies with TypeError instead of clearing",
)
async def test_cmd_identity_clear(fake_manager, fake_channel, chat_ctx):
    mod = await make_identity(fake_manager, fake_channel, identity="You are Sunny.")

    assert await mod.cmd_set(["clear"]) == "identity cleared."
    assert mod.config.get("identity") == ""


# ---------------------------------------------------------------------------
# tool gating
# ---------------------------------------------------------------------------

async def test_set_tool_disabled_when_ai_may_not_change_identity(
    fake_manager, fake_channel, chat_ctx
):
    mod = await make_identity(
        fake_manager, fake_channel,
        identity="x", allow_ai_to_change_identity=False,
    )

    assert "set" in mod.disabled_tools

    mod2 = await make_identity(
        fake_manager, fake_channel,
        identity="x", allow_ai_to_change_identity=True,
    )
    assert "set" not in mod2.disabled_tools
