# AI Written: Claude Opus 5.5, reviewed by Claude Fable 5.2
import importlib
import sys

import pytest

import core
from tests.fixtures import fixtures_pkg

PKG = fixtures_pkg.__name__


@pytest.fixture(autouse=True)
def forget_fixture_imports():
    yield
    for key in [k for k in sys.modules if k.startswith(PKG + ".")]:
        del sys.modules[key]
        if hasattr(fixtures_pkg, key.split(".")[-1]):
            delattr(fixtures_pkg, key.split(".")[-1])


def test_discovery_skips_hidden_and_invalid_folders():
    # .hidden/_underscore are private, nofile has no entry file, initmodule has a forbidden __init__.py
    assert core.modules.discover_module_names(fixtures_pkg) == [
        "baddeps", "bothmodule", "brokenmodule", "channelmod", "demomodule"
    ]


@pytest.mark.parametrize("name, marker", [("bothmodule", "module"), ("channelmod", "channel")])
def test_entry_file(name, marker):
    # module.py wins over channel.py when a folder has both
    assert core.modules.import_entry(fixtures_pkg, name).MARKER == marker


def test_import_entry_supports_relative_imports_and_caches():
    mod = core.modules.import_entry(fixtures_pkg, "demomodule")
    assert mod.GREETING == "hello from helper"
    assert sys.modules[f"{PKG}.demomodule"] is mod
    assert fixtures_pkg.demomodule is mod
    assert core.modules.import_entry(fixtures_pkg, "demomodule") is mod


def test_failed_import_leaves_nothing_behind():
    for _ in range(2):  # a second attempt must fail the same way, not return a half-built module
        with pytest.raises(RuntimeError, match="boom"):
            core.modules.import_entry(fixtures_pkg, "brokenmodule")
        assert f"{PKG}.brokenmodule" not in sys.modules


def test_import_entry_promotes_namespace_package():
    # importing a submodule first leaves a bare namespace package (like channels.webui.api does)
    importlib.import_module(f"{PKG}.demomodule.helper")
    assert not getattr(sys.modules[f"{PKG}.demomodule"], "__file__", None)

    mod = core.modules.import_entry(fixtures_pkg, "demomodule")
    assert mod.__file__.endswith("module.py")
    assert mod.Demo


def test_import_entry_without_entry_file():
    with pytest.raises(ImportError):
        core.modules.import_entry(fixtures_pkg, "nofile")


def test_load_filters_and_skips_broken_and_missing_deps():
    classes = core.modules.load(fixtures_pkg, filter=["demomodule", "brokenmodule", "baddeps"])
    # only classes defined in the folder count, not imported ones like OrderedDict
    assert [c.__name__ for c in classes] == ["Demo"]
    assert f"{PKG}.baddeps" not in sys.modules
    assert f"{PKG}.channelmod" not in sys.modules


def test_load_filters_by_base_class():
    assert core.modules.load(fixtures_pkg, base_class=core.module.Module, filter=["demomodule"]) == ()


def test_dependencies_parsed_without_import():
    deps = core.modules._extract_deps_from_file(core.modules._get_module_file_path(fixtures_pkg, "baddeps"))
    assert deps == ["openlumara-test-missing-package>=1.0", "pytest[testing]==1.0"]
    # version pins and extras are stripped before looking up the installed package
    assert core.modules._check_missing_deps(deps) == ["openlumara-test-missing-package>=1.0"]


@pytest.mark.parametrize("module, name", [
    ("modules.calendar.module", "calendar"),
    ("user_channels.bridge.channel", "bridge"),
    ("channels.webui.api", "webui"),
])
def test_get_name(module, name):
    assert core.modules.get_name(type("X", (), {"__module__": module})) == name


def test_get_name_rejects_classes_outside_module_folders():
    with pytest.raises(ValueError):
        core.modules.get_name(type("X", (), {"__module__": "core.something"}))
