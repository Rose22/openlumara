# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
core/modules.py: module discovery and folder-import machinery.

uses tests/fixtures/fixtures_pkg, a real package whose subfolders mimic
the repo's module layout (entry files, no __init__.py in module folders).

intent under test:
- discover_module_names lists folders that contain an entry file
  (module.py/channel.py), skipping dot/underscore folders, folders without
  an entry file, and folders with a forbidden __init__.py; result is
  sorted and deduplicated across multiple __path__ entries.
- import_entry execs the folder's entry file under <package>.<name>, so
  relative imports inside the module work, caches in sys.modules, and
  never leaves a half-initialized module behind when exec fails.
- dependencies are extractable by AST without importing the file, and
  _check_missing_deps maps PEP-ish requirement strings to installed
  distribution names.
- get_name derives the canonical name from the defining package.
"""

import pathlib
import sys
import types

import pytest

import core.modules as modules_mod

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures"
if str(FIXTURES) not in sys.path:
    sys.path.insert(0, str(FIXTURES))

import fixtures_pkg  # noqa: E402

ALL_FIXTURE_MODULES = [
    "baddeps",
    "bothmodule",
    "brokenmodule",
    "channelmod",
    "demomodule",
    "depfile",
]


@pytest.fixture(autouse=True)
def clean_loaded_fixtures():
    """
    keep fixture-module imports from leaking between tests.
    ONLY touch fixtures_pkg.* entries: the diff of sys.modules also
    contains stdlib modules first imported by fixture code, and deleting
    those breaks the interpreter for the rest of the session.
    """
    prefix = "fixtures_pkg."
    before = {k: sys.modules[k] for k in sys.modules if k.startswith(prefix)}
    yield
    for name in [k for k in sys.modules if k.startswith(prefix) and k not in before]:
        del sys.modules[name]
    sys.modules.update(before)


@pytest.fixture(autouse=True)
def clean_reported_init():
    # reported_init dedupes the "__init__.py not allowed" warning globally
    saved = list(modules_mod.reported_init)
    modules_mod.reported_init.clear()
    yield
    modules_mod.reported_init.extend(saved)


# ---------------------------------------------------------------------------
# discovery
# ---------------------------------------------------------------------------

def test_discover_lists_entry_file_folders_only():
    names = modules_mod.discover_module_names(fixtures_pkg)

    # nofile (no entry), initmodule (__init__.py), _underscore and .hidden
    # are all invisible
    assert names == ALL_FIXTURE_MODULES


def test_discover_returns_empty_for_non_package():
    assert modules_mod.discover_module_names(sys) == []


def test_discover_dedupes_and_sorts_across_paths(tmp_path):
    for pkg_dir, mod, entry in (
        ("a", "shared", "module.py"),
        ("b", "shared", "module.py"),
        ("b", "zeta", "channel.py"),
    ):
        d = tmp_path / pkg_dir / mod
        d.mkdir(parents=True)
        (d / entry).write_text("MARKER = 1\n")

    pkg = types.SimpleNamespace(
        __name__="multi_path_pkg",
        __path__=[str(tmp_path / "a"), str(tmp_path / "b")],
    )

    assert modules_mod.discover_module_names(pkg) == ["shared", "zeta"]


def test_module_py_wins_over_channel_py():
    path = modules_mod._get_module_file_path(fixtures_pkg, "bothmodule")
    assert path.endswith("bothmodule/module.py")


def test_folder_with_init_py_is_skipped_and_reported_once():
    assert modules_mod._get_module_file_path(fixtures_pkg, "initmodule") is None
    # second call must not add a second report
    modules_mod._get_module_file_path(fixtures_pkg, "initmodule")

    assert modules_mod.reported_init.count("fixtures_pkg.initmodule") == 1


def test_missing_module_file_returns_none():
    assert modules_mod._get_module_file_path(fixtures_pkg, "nosuchmodule") is None


# ---------------------------------------------------------------------------
# import_entry
# ---------------------------------------------------------------------------

def test_import_entry_executes_entry_file_with_relative_imports():
    mod = modules_mod.import_entry(fixtures_pkg, "demomodule")

    # relative import inside the module folder resolved
    assert mod.GREETING == "hello from helper"
    assert mod.DemoModule.header == "Demo"
    # registered under the canonical dotted name and as a package attribute
    assert sys.modules["fixtures_pkg.demomodule"] is mod
    assert fixtures_pkg.demomodule is mod


def test_import_entry_is_cached():
    mod = modules_mod.import_entry(fixtures_pkg, "demomodule")
    assert mod.LOAD_COUNT == 1

    # cached: same object, code not re-executed
    assert modules_mod.import_entry(fixtures_pkg, "demomodule") is mod
    assert mod.LOAD_COUNT == 1


@pytest.mark.xfail(
    strict=True,
    reason="suspected bug (latent): import_entry(reload=True) delegates to "
    "importlib.reload, which re-resolves the spec via PathFinder; an "
    "__init__.py-less module folder only resolves to a loaderless namespace "
    "spec there, so the FIRST reload silently skips execution (and clobbers "
    "__spec__ with the namespace spec) - only a second reload re-executes. "
    "Latent because the only reload=True caller is manager startup, where "
    "the module cache is always empty. (TEST_PLAN.md section 5, finding 10)",
)
def test_import_entry_reload_reexecutes_on_first_request():
    mod = modules_mod.import_entry(fixtures_pkg, "demomodule")
    assert mod.LOAD_COUNT == 1

    reloaded = modules_mod.import_entry(fixtures_pkg, "demomodule", reload=True)

    assert reloaded is mod
    assert mod.LOAD_COUNT == 2


def test_import_entry_channel_entry_file():
    mod = modules_mod.import_entry(fixtures_pkg, "channelmod")
    assert mod.MARKER == "channel-entry"


def test_failed_import_leaves_no_half_initialized_module():
    with pytest.raises(RuntimeError, match="boom during import"):
        modules_mod.import_entry(fixtures_pkg, "brokenmodule")

    assert "fixtures_pkg.brokenmodule" not in sys.modules
    # a later attempt retries cleanly rather than seeing a stale module
    with pytest.raises(RuntimeError):
        modules_mod.import_entry(fixtures_pkg, "brokenmodule")


def test_import_entry_without_entry_file_raises_import_error():
    with pytest.raises(ImportError, match="no entry file"):
        modules_mod.import_entry(fixtures_pkg, "nosuchmodule")


# ---------------------------------------------------------------------------
# dependency extraction / checking
# ---------------------------------------------------------------------------

def test_extract_deps_from_file_without_importing(tmp_path):
    deps = modules_mod._extract_deps_from_file(
        str(FIXTURES / "fixtures_pkg" / "depfile" / "module.py")
    )

    assert deps == ["python-telegram-bot>=1.0", "rich[pretty]==13.0", "plain-dep"]


def test_extract_deps_from_unparseable_file_returns_empty():
    path = str(FIXTURES / "fixtures_pkg" / "baddeps" / "module.py")
    assert modules_mod._extract_deps_from_file(path) == []


def test_extract_deps_when_no_dependencies_declared():
    path = str(FIXTURES / "fixtures_pkg" / "demomodule" / "module.py")
    assert modules_mod._extract_deps_from_file(path) == []


def test_check_missing_deps_resolves_distribution_names():
    assert modules_mod._check_missing_deps(["pytest"]) == []
    # extras and version specifiers must be stripped before lookup
    assert modules_mod._check_missing_deps(["pytest[e2e]>=1.0"]) == []

    missing = modules_mod._check_missing_deps(
        ["totally-not-installed-pkg-9999>=1.0", "pytest"]
    )
    assert missing == ["totally-not-installed-pkg-9999>=1.0"]


# ---------------------------------------------------------------------------
# get_name
# ---------------------------------------------------------------------------

def test_get_name_from_module_and_submodule():
    class A:
        pass

    A.__module__ = "modules.calendar.module"
    assert modules_mod.get_name(A) == "calendar"

    A.__module__ = "channels.webui.api"
    assert modules_mod.get_name(A) == "webui"


def test_get_name_rejects_outside_classes():
    class A:
        pass

    A.__module__ = "core.chat"
    with pytest.raises(ValueError, match="not defined inside a module/channel folder"):
        modules_mod.get_name(A)
