# AI Written: Claude Opus 5.5, reviewed by Claude Fable 5.2
import json
import os
import shutil
import sys
import types

import pytest
import yaml

import core


@pytest.fixture
def user_modules(tmp_path, monkeypatch):
    """swap the module/channel packages for empty ones, with user_modules backed by tmp_path"""
    root = tmp_path / "user_modules"
    root.mkdir()
    for name in core.config.CACHE_SECTIONS:
        pkg = types.ModuleType(name)
        pkg.__path__ = [str(root)] if name == "user_modules" else []
        monkeypatch.setitem(sys.modules, name, pkg)
        monkeypatch.setattr(core.config, name, pkg)
    yield root
    forget_imports()


def forget_imports():
    """drop imported fixture modules, like a restart would"""
    for key in [k for k in sys.modules if k.startswith("user_modules.cfgdemo")]:
        del sys.modules[key]


def write_module(root, body, name="cfgdemo"):
    (root / name).mkdir(exist_ok=True)
    (root / name / "module.py").write_text(
        f'import core\n\nclass Demo(core.module.Module):\n    """demo doc"""\n    category = "life"\n    {body}\n'
    )


def read_cache():
    with open(core.config.SCHEMA_CACHE_FILE) as f:
        return json.load(f)


def test_get_nested_with_defaults(set_config):
    set_config(model={"use_tools": True})
    assert core.config.get("model", "use_tools") is True
    # a non-string last argument is the default, a string is just another key
    assert core.config.get("model", "nope", 5) == 5
    assert core.config.get("model", "nope", "deeper") is None
    assert core.config.get("nope", default=[]) == []
    assert core.config.get() is None


def test_config_manager_scopes_to_base_path():
    cm = core.config.ConfigManager(core.config.config, base_path=["modules", "settings", "demo"])
    assert cm.get("missing", 0) == 0

    cm.set("volume", 7)
    assert core.config.config["modules"]["settings"]["demo"] == {"volume": 7}
    assert "volume" in cm and cm["volume"] == 7

    # get() reloads from disk, so a value saved by someone else shows up
    with open(core.config.config.path) as f:
        data = yaml.safe_load(f)
    data["modules"]["settings"]["demo"]["volume"] = 9
    with open(core.config.config.path, "w") as f:
        yaml.safe_dump(data, f)
    st = os.stat(core.config.config.path)  # reload is keyed on mtime, so make sure it moved
    os.utime(core.config.config.path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))
    assert cm.get("volume") == 9


def test_sync_config_adds_missing_keys_and_keeps_user_values():
    schema = {"api": {"url": "default", "timeout": 30}, "modules": {"settings": {}}}
    user = {"api": {"url": "mine"}, "modules": {"settings": {"x": {"a": 1}}}, "extra": True}
    assert core.config.sync_config(user, schema) == {
        "api": {"url": "mine", "timeout": 30},
        "modules": {"settings": {"x": {"a": 1}}},
        "extra": True,
    }


def test_reconcile_lists():
    result = core.config.reconcile_lists(
        available_names=["a", "b", "new_default", "new_other"],
        default_names=["a", "new_default"],
        section_config={"enabled": ["b", "gone"], "disabled": ["a"]},
    )
    # user choices win, new modules follow the defaults, deleted ones are pruned
    assert result == {"enabled": ["b", "new_default"], "disabled": ["a", "new_other"]}


def test_merge_module_settings():
    defaults = {
        "volume": {"default": 3},
        "voice": {"default": "calm"},
        "nested": {"depth": {"default": 1}},
    }
    current = {"volume": 10, "old_key": "x", "nested": {"depth": 4}}
    assert core.config._merge_module_settings(current, defaults) == {
        "volume": 10, "voice": "calm", "nested": {"depth": 4}
    }


def test_merge_core_settings_keeps_falsy_user_values():
    schema = {"stream": {"default": True}, "retries": {"default": 3}}
    assert core.config._merge_core_settings({"stream": False, "retries": 0}, schema) == {"stream": False, "retries": 0}


def test_sync_module_settings_prunes_removed_and_keeps_disabled():
    enabled = type("Demo", (), {"__module__": "modules.demo.module", "settings": {"a": {"default": 1}}})
    config = {"modules": {"settings": {"demo": {}, "disabled_one": {"keep": True}, "deleted": {"x": 1}}}}
    core.config.sync_module_settings(config, [enabled], "modules", ["demo", "disabled_one"])
    assert config["modules"]["settings"] == {"demo": {"a": 1}, "disabled_one": {"keep": True}}


def test_static_metadata_reads_without_importing(tmp_path):
    path = tmp_path / "module.py"
    path.write_text(
        "import package_that_does_not_exist\n\n"
        "class Helper:\n    pass\n\n"
        "class Mine:\n    '''does things'''\n    unsafe = True\n    category = 'tools'\n    settings = {}\n"
    )
    assert core.config._extract_class_metadata_from_file(str(path)) == {
        "docstring": "does things", "unsafe": True, "category": "tools"
    }


def test_static_metadata_inherits_category_from_other_module(tmp_path):
    # category comes from modules/memory/module.py, resolved through the import alias
    from modules.memory.module import Memory

    path = tmp_path / "module.py"
    path.write_text("from modules.memory import Memory as M\n\nclass Mine(M):\n    settings = {}\n")
    assert core.config._extract_class_metadata_from_file(str(path))["category"] == Memory.category


def test_schema_cache_written_and_trusted_while_unchanged(user_modules):
    write_module(user_modules, 'settings = {"greeting": {"default": "hi"}}')
    assert core.config.get_schema()["user_modules"]["settings"]["cfgdemo"] == {"greeting": "hi"}
    meta = core.config.get_module_structure()["cfgdemo"]["metadata"]
    assert (meta["doc"], meta["category"], meta["type"]) == ("demo doc", "life", "user_module")

    cache = read_cache()
    assert cache["_version"] == core.config.SCHEMA_CACHE_VERSION
    cache["user_modules"]["cfgdemo"]["schema"] = {"greeting": {"default": "from cache"}}
    with open(core.config.SCHEMA_CACHE_FILE, "w") as f:
        json.dump(cache, f)
    assert core.config.get_schema()["user_modules"]["settings"]["cfgdemo"] == {"greeting": "from cache"}

    # a cache from another version is rebuilt from the source
    cache["_version"] = -1
    with open(core.config.SCHEMA_CACHE_FILE, "w") as f:
        json.dump(cache, f)
    forget_imports()
    assert core.config.get_schema()["user_modules"]["settings"]["cfgdemo"] == {"greeting": "hi"}


def test_schema_cache_follows_file_changes(user_modules):
    write_module(user_modules, 'settings = {"greeting": {"default": "hi"}}')
    core.config.get_schema()

    forget_imports()
    write_module(user_modules, 'settings = {"greeting": {"default": "hello"}}')
    assert core.config.get_schema()["user_modules"]["settings"]["cfgdemo"] == {"greeting": "hello"}

    shutil.rmtree(user_modules / "cfgdemo")
    assert "cfgdemo" not in core.config.get_schema()["user_modules"]["settings"]
    assert "cfgdemo" not in read_cache()["user_modules"]


def test_load_merges_existing_config_with_schema(user_modules, tmp_path):
    write_module(user_modules, 'settings = {"greeting": {"default": "hi"}, "volume": {"default": 3}}')
    path = tmp_path / "cfg.yml"
    path.write_text(yaml.safe_dump({
        "model": {"use_tools": False},
        "user_modules": {
            "enabled": ["cfgdemo", "gone"],
            "settings": {"cfgdemo": {"greeting": "yo"}, "gone": {"x": 1}},
        },
    }))

    core.config.load(str(path))

    assert core.config.get("model", "use_tools") is False
    assert core.config.get("core", "data_folder") == core.config.default_config["core"]["data_folder"]
    section = core.config.get("user_modules")
    assert section["enabled"] == ["cfgdemo"]
    assert section["settings"] == {"cfgdemo": {"greeting": "yo", "volume": 3}}
