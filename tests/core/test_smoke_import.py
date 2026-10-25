# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
phase 0 acceptance tests.

1. importing core must not modify a live install. this runs `import core` in a
   fresh subprocess (this process already imported it via conftest) and
   compares data/, config.yml and .module_cache.json before/after.
   NOTE: this assumes the install has been started at least once (so the
   data/firstrun marker exists). on a truly fresh clone, importing core
   legitimately creates data/firstrun, user_modules/ and user_channels/.

2. the conftest isolation fixture must actually isolate: anything that
   resolves the data folder or the schema cache ends up under tmp_path.
"""

import subprocess
import sys

import core

from harness import REPO_ROOT, repo_state


def test_import_core_does_not_touch_live_install(repo_snapshot):
    proc = subprocess.run(
        [sys.executable, "-c", "import core"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, f"import core failed:\n{proc.stderr}"
    assert repo_state() == repo_snapshot, (
        "importing core modified the live install (data/, config.yml or "
        ".module_cache.json changed)"
    )


def test_data_folder_resolves_into_tmp(isolate_lumara_paths):
    resolved = core.get_data_path("probe")
    assert str(resolved).startswith(str(isolate_lumara_paths))


def test_storage_without_explicit_path_writes_to_tmp(isolate_lumara_paths):
    # storage classes resolve core.get_data_path() at construction time;
    # with the isolation fixture active they must land in tmp, not in ./data
    store = core.storage.StorageList("phase0_probe", type="json")
    store.append({"hello": "world"})
    store.save()

    assert (isolate_lumara_paths / "phase0_probe.json").exists()
    assert not (REPO_ROOT / "data" / "phase0_probe.json").exists()


def test_developer_role_flag_defaults_false(fake_manager):
    # core.context reads these attributes off manager.API - the fakes must
    # keep them available (see TEST_PLAN.md section 4)
    assert fake_manager.API.connected is True
    assert fake_manager.API.supports_developer_role is False
    assert fake_manager.API.cancel_request is False
