# AI Written: Claude Opus 5.5, reviewed by Claude Fable 5.2
"""The sandbox container's run command, built without touching docker."""

import pytest

from modules.shell.module import Shell


@pytest.mark.parametrize("persistent", [True, False])
async def test_container_is_locked_down(manager, tmp_path, monkeypatch, set_config, persistent):
    set_config(modules={"settings": {"shell": {
        "method": "dockerfile",
        "dockerfile_path": str(tmp_path / "Dockerfile"),
        "persistent_data": persistent,
        "temporary_filesystem_size_limit": "128m",
    }}})
    shell = Shell(manager)
    # what on_ready would detect
    shell.runtime = "docker"
    shell.container_name = "openlumara_test_shell"
    shell.host_workspace = str(tmp_path / "workspace")
    shell.host_user_uid = shell.host_user_gid = 1000
    shell.use_gvisor = False

    calls = []

    async def fake_build(force=False):
        return "custom:sandbox"

    async def fake_run(cmd, timeout=None, limit=None):
        calls.append(cmd)
        return b"", b"", 0, False

    monkeypatch.setattr(shell, "_build_image", fake_build)
    monkeypatch.setattr(shell, "_run_async_cmd", fake_run)

    await shell._start_container()

    run = next(cmd for cmd in calls if cmd[1] == "run")
    assert run[-1] == "custom:sandbox"
    assert ["--network", "none"] == run[run.index("--network"):run.index("--network") + 2]
    assert ["--cap-drop", "ALL"] == run[run.index("--cap-drop"):run.index("--cap-drop") + 2]
    assert "--read-only" in run
    # only the workspace may be mounted, never the Dockerfile
    assert not any("Dockerfile" in arg for arg in run)
    mounts = [run[i + 1] for i, arg in enumerate(run) if arg == "-v"]
    if persistent:
        assert len(mounts) == 1 and mounts[0].startswith(shell.host_workspace + ":/home/lumara")
    else:
        assert mounts == []
        assert "/home/lumara:size=128m" in run
