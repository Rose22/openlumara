# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-26) harness:openlumara status:unreviewed
"""
modules/models - model awareness in the prompt + model switching.

integration level: real Models module on FakeManager (its FakeAPI fakes the
get_model/list_models/set_model surface of the real APIClient).

intent under test:
- current model line on/off via insert_current_model_into_system_prompt;
  with the available-models insert off, the prompt is just the bare model
  name under the "current model" header.
- the available-models list is fetched once and cached; APIError/empty
  results degrade gracefully (no listing, no crash).
- switch() matches case-insensitively, persists to config and tells the
  API; unknown names are refused without touching config.
- /model and /models commands render from the same data.
"""

import pytest

import core
from harness import apply_config
from modules.models.module import Models

BASE = {
    "api": {"max_context": 1000},
    "model": {"name": "test-model", "use_tools": True, "dynamic_tool_loading": False},
    "core": {"cmd_prefix": "/"},
}


def configure(**settings):
    apply_config(
        modules={"disabled_prompts": [], "settings": {"models": settings}}, **BASE
    )


async def make_models(fake_manager, **settings):
    configure(**settings)
    mod = Models(fake_manager)
    await mod.on_ready()
    return mod


# ---------------------------------------------------------------------------
# system prompt
# ---------------------------------------------------------------------------

async def test_prompt_current_model_only_is_bare_name(fake_manager):
    fake_manager.API.model_name = "qwen-3.8"
    mod = await make_models(fake_manager)

    # with available-models off the whole prompt is the model name, under a
    # "current model" header (no "Current model:" label duplication)
    assert await mod.on_system_prompt() == "qwen-3.8"
    assert mod.header == "current model"


async def test_prompt_current_model_line_when_available_list_on(fake_manager):
    fake_manager.API.available_models = ["a-model", "b-model"]
    mod = await make_models(
        fake_manager,
        insert_current_model_into_system_prompt=True,
        insert_available_models_into_system_prompt=True,
    )

    out = await mod.on_system_prompt()

    assert out.startswith("Current model: test-model")
    assert "a-model, b-model" in out
    assert "models_switch()" in out


async def test_prompt_single_available_model_is_not_listed(fake_manager):
    fake_manager.API.available_models = ["only-one"]
    mod = await make_models(
        fake_manager, insert_available_models_into_system_prompt=True,
    )

    # listing one option you cannot switch away from is pointless
    assert "only-one" not in (await mod.on_system_prompt() or "")


async def test_prompt_survives_model_list_failure(fake_manager):
    mod = await make_models(
        fake_manager,
        insert_current_model_into_system_prompt=True,
        insert_available_models_into_system_prompt=True,
    )

    async def broken_list():
        return core.api.APIError("offline")

    fake_manager.API.list_models = broken_list

    # APIError must degrade to "no listing", never crash or cache garbage
    assert await mod.on_system_prompt() == "Current model: test-model"
    assert mod.models is None


# ---------------------------------------------------------------------------
# get_available tool
# ---------------------------------------------------------------------------

async def test_get_available_caches_the_model_list(fake_manager):
    fake_manager.API.available_models = ["a", "b"]
    mod = await make_models(fake_manager)

    first = await mod.get_available()
    second = await mod.get_available()

    assert first == {"status": "success", "content": ["a", "b"]}
    assert second == first
    assert fake_manager.API.list_models_calls == 1


async def test_on_ready_hides_get_available_when_list_is_in_prompt(fake_manager):
    # if the model list is already in the system prompt the tool is noise
    mod = await make_models(
        fake_manager, insert_available_models_into_system_prompt=True,
    )
    assert "get_available" in mod.disabled_tools

    mod2 = await make_models(fake_manager)
    assert "get_available" not in mod2.disabled_tools


# ---------------------------------------------------------------------------
# switching
# ---------------------------------------------------------------------------

async def test_switch_matches_case_insensitively_and_persists(fake_manager):
    fake_manager.API.available_models = ["Qwen3-14B", "llama-3.3"]
    mod = await make_models(fake_manager)

    out = await mod.switch("qwen3-14b")

    assert out == "model has been switched to Qwen3-14B"
    # canonical name from the server list, not the user's casing
    assert core.config.config["model"]["name"] == "Qwen3-14B"
    assert fake_manager.API.model_name == "Qwen3-14B"


async def test_switch_unknown_model_refuses_without_side_effects(fake_manager):
    fake_manager.API.available_models = ["Qwen3-14B"]
    mod = await make_models(fake_manager)

    out = await mod.switch("gpt-whatever")

    assert out == "model does not exist. use models_get_available() first"
    assert core.config.config["model"]["name"] == "test-model"
    assert fake_manager.API.model_name == "test-model"


async def test_switch_survives_unreachable_model_list(fake_manager):
    mod = await make_models(fake_manager)

    async def broken_list():
        return core.api.APIError("offline")

    fake_manager.API.list_models = broken_list

    assert await mod.switch("anything") is None


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

async def test_cmd_model_shows_current_or_switches(fake_manager):
    fake_manager.API.model_name = "qwen-3.8"
    fake_manager.API.available_models = ["qwen-3.8", "llama-3.3"]
    mod = await make_models(fake_manager)

    assert await mod.model([]) == "Current model: qwen-3.8"
    assert await mod.model(["llama-3.3"]) == "model has been switched to llama-3.3"


async def test_cmd_models_lists_with_usage_hint(fake_manager):
    fake_manager.API.available_models = ["alpha", "beta"]
    mod = await make_models(fake_manager)

    # on_ready() sets the instance attribute self.models, shadowing the
    # models() command method on the instance - the dispatcher is unaffected
    # because it binds the class-level function from the command registry,
    # so tests must go through the class too.
    out = await Models.models(mod, [])

    assert out.startswith("alpha\nbeta")
    assert "/model <name>" in out
