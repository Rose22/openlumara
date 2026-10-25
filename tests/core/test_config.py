# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
core/config.py - config access and schema/config reconciliation.

intent: the config file keeps everything the user set; the schema provides
defaults for anything missing; keys the user has that the schema does not
know about are PRESERVED (settings for disabled modules must survive);
enabled/disabled lists are reconciled against what is actually on disk.
"""

import pytest

import core


# ---- ConfigManager -----------------------------------------------------

@pytest.fixture
def cm():
    return core.config.ConfigManager(core.config.config, base_path=["modules", "settings", "demo"])


def test_config_manager_get_defaults_on_missing(cm):
    assert cm.get("nope") is None
    assert cm.get("nope", default=7) == 7
    assert cm.get("nope", 7) == 7


def test_config_manager_set_persists_through_storage(cm, tmp_path):
    cm["greeting"] = "hi"
    assert cm.get("greeting") == "hi"
    # ConfigManager.set saves - the value must be on disk, not just in memory
    assert "greeting" in (tmp_path / "config.yml").read_text()


def test_config_manager_nested_get(cm):
    cm["section"] = {"inner": 7}
    assert cm.get("section", "inner") == 7


def test_config_manager_contains_and_getitem(cm):
    cm["known"] = 1
    assert "known" in cm
    assert "unknown" not in cm
    assert cm["known"] == 1
    with pytest.raises(KeyError):
        cm["unknown"]


# ---- _flatten_settings ---------------------------------------------------

def test_flatten_settings_extracts_defaults_recursively():
    schema = {
        "a": {"default": 1, "description": "d"},
        "b": {"c": {"default": {"default": 5}}},
        "d": 3,
    }
    assert core.config._flatten_settings(schema) == {"a": 1, "b": {"c": 5}, "d": 3}


# ---- _merge_core_settings --------------------------------------------------

def test_merge_core_settings_builds_defaults_from_schema():
    # real usage (get_schema): user_config is empty, output is the flattened
    # core defaults
    schema = {
        "url": {"default": "http://default/v1", "description": "u"},
        "max": {"default": 100},
    }
    assert core.config._merge_core_settings({}, schema) == {
        "url": "http://default/v1", "max": 100,
    }

    # sanity: the real core settings schema round-trips through it
    real = core.config._merge_core_settings({}, core.config.core_settings_schema)
    assert real["api"]["max_context"] == 16768


def test_merge_core_settings_is_schema_driven():
    # it iterates schema keys only: user keys the schema does not know are
    # NOT merged here (that is sync_config's job, tested below)
    merged = core.config._merge_core_settings({"a": 1, "extra": 2}, {"a": {"default": 5}})
    assert merged == {"a": 1}


def test_merge_core_settings_node_level_default_sentinel():
    # intent: a stored value that is still an unflattened {default: ...}
    # node gets replaced by the schema default; a real value survives
    assert core.config._merge_core_settings({"default": 99}, {"default": 5}) == 5
    assert core.config._merge_core_settings(None, {"default": 5}) == 5
    assert core.config._merge_core_settings(3, {"default": 5}) == 3


# ---- sync_config -----------------------------------------------------------

def test_sync_config_adds_missing_and_preserves_unknown():
    schema = {"a": 1, "nested": {"x": 1, "y": 2}}
    user = {"a": 99, "nested": {"x": 8}, "custom_key": "keep me"}

    synced = core.config.sync_config(user, schema)
    assert synced["a"] == 99                       # user wins
    assert synced["nested"] == {"x": 8, "y": 2}    # defaults merged in
    assert synced["custom_key"] == "keep me"       # unknown keys preserved


def test_sync_config_keeps_user_values_at_empty_schema_nodes():
    # empty dict/list in the schema means "free-form" - never overwrite it
    assert core.config.sync_config({"a": [1, 2]}, {"a": []})["a"] == [1, 2]
    assert core.config.sync_config({"a": {"k": 1}}, {"a": {}})["a"] == {"k": 1}


def test_sync_config_keeps_scalar_over_dict_schema():
    # user set a scalar where the schema has a dict: user value survives
    assert core.config.sync_config({"a": 5}, {"a": {"x": 1}})["a"] == 5


# ---- reconcile_lists ---------------------------------------------------------

def test_reconcile_new_names_follow_defaults():
    state = core.config.reconcile_lists(["a", "b", "c"], ["a"], {"enabled": ["b"], "disabled": []})
    assert state["enabled"] == ["a", "b"]   # new default module auto-enabled
    assert state["disabled"] == ["c"]       # new non-default auto-disabled


def test_reconcile_prunes_names_no_longer_on_disk():
    state = core.config.reconcile_lists(
        ["a"], ["a"], {"enabled": ["a", "gone"], "disabled": ["deleted"]}
    )
    assert state["enabled"] == ["a"]
    assert state["disabled"] == []


def test_reconcile_respects_explicit_disable_of_default_module():
    # user disabled a default module earlier: it must NOT be re-enabled
    state = core.config.reconcile_lists(["a"], ["a"], {"enabled": [], "disabled": ["a"]})
    assert state["enabled"] == []
    assert state["disabled"] == ["a"]


def test_reconcile_output_is_sorted():
    state = core.config.reconcile_lists(["b", "a"], [], {"enabled": [], "disabled": []})
    assert state["disabled"] == ["a", "b"]


# ---- module-level get() ----------------------------------------------------

def test_config_get_no_args_returns_default():
    assert core.config.get() is None


def test_config_get_reads_loaded_config():
    # the conftest fixture points data_folder at tmp
    assert core.config.get("core", "data_folder").startswith("/")


def test_config_get_positional_default():
    assert core.config.get("does_not_exist", 42) == 42


def test_config_get_falls_back_to_schema_defaults_when_unloaded(monkeypatch):
    # intent: even before any config file is loaded, core settings resolve
    # to their documented defaults
    monkeypatch.setattr(core.config, "config", None)
    assert core.config.get("api", "max_context") == 16768
    assert core.config.get("core", "cmd_prefix") == "/"
