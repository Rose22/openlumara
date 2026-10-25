# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
shared test fixtures.

the important one is `isolate_lumara_paths` (autouse): it guarantees the test
suite never writes to a live install's real data/, config.yml, or
.module_cache.json.

background: importing core is side-effect-light (it creates user_modules/,
user_channels/ and the data/firstrun marker if missing - all already present
in any install that has been started at least once). the real danger is what
happens AFTER import:
  - core.get_data_path() resolves the data folder at CALL time from
    core.config.get("core", "data_folder"), falling back to ./data when no
    config is loaded.
  - core.config._get_module_schema_cache() writes SCHEMA_CACHE_FILE to the
    project root.
both are redirected to tmp_path below. note that core.config.config must be a
StorageDict (or something with .load()/.save()), because ConfigManager.get()
reloads from disk on every call - a plain dict would blow up.
"""

import pathlib
import sys

import pytest

# make the repo root importable even when pytest is invoked from a subdir
# (pytest.ini also sets pythonpath, this is just belt & suspenders)
REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import core  # noqa: E402  (import on purpose at conftest import time)

from harness import FakeAPI, FakeChannel, FakeManager, repo_state  # noqa: E402


@pytest.fixture(autouse=True)
def isolate_lumara_paths(tmp_path, monkeypatch):
    """
    redirect the data folder, the global config file and the module schema
    cache into tmp_path for every test. yields the tmp data directory.
    """
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # a real StorageDict in tmp, so ConfigManager's load()/save() round-trips
    # behave exactly like production - just pointed at a throwaway file.
    test_config = core.storage.StorageDict(
        "config", "yaml", path=str(tmp_path), override_temporary=True
    )
    test_config.load({"core": {"data_folder": str(data_dir)}})

    monkeypatch.setattr(core.config, "config", test_config)

    # get_path() returns absolute paths unchanged, so this keeps the module
    # schema cache out of the repo root.
    monkeypatch.setattr(
        core.config, "SCHEMA_CACHE_FILE", str(tmp_path / "module_cache.json")
    )

    # make sure global runtime state can't leak between tests
    monkeypatch.setattr(core.config, "_registry_cache", None)
    monkeypatch.setattr(core.storage, "TEMPORARY", False)
    monkeypatch.setattr(core.manager, "global_instance", None)

    yield data_dir


@pytest.fixture
def repo_snapshot():
    """state of the real data/, config.yml and .module_cache.json, pre-test."""
    return repo_state()


@pytest.fixture
def fake_api():
    return FakeAPI()


@pytest.fixture
def fake_manager(fake_api):
    return FakeManager(api=fake_api)


@pytest.fixture
def fake_channel(fake_manager):
    return FakeChannel(manager=fake_manager)
