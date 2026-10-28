# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-25) harness:openlumara status:unreviewed
"""
modules/shell - sandbox container command construction.

Recent dev change (40f1e4a): the Dockerfile is no longer bind-mounted into the
running sandbox container. The Dockerfile may still be used to build the image,
but the `docker run` command must not carry it as a volume.
"""

import pytest

from harness import apply_config
from modules.shell.module import Shell


BASE = {
    "api": {"max_context": 1000},
    "model": {"name": "test-model", "use_tools": False, "dynamic_tool_loading": False},
    "core": {"cmd_prefix": "/"},
}


def configure_shell(**settings):
    apply_config(
        modules={"disabled_prompts": [], "settings": {"shell": settings}},
        **BASE,
    )


@pytest.fixture
def shell(fake_manager, tmp_path):
    configure_shell(
        method="dockerfile",
        dockerfile_path=str(tmp_path / "Dockerfile"),
        image="debian:stable-slim",
        persistent_data=False,
        temporary_filesystem_size_limit="128m",
    )

    mod = Shell(fake_manager)
    mod.runtime = "docker"
    mod.container_name = "openlumara_test_shell"
    mod.host_workspace = str(tmp_path / "workspace")
    mod.host_user_uid = 1000
    mod.host_user_gid = 1000
    mod.use_gvisor = False
    mod.image_hash_path = str(tmp_path / "image_hash")
    return mod


async def test_dockerfile_method_does_not_bind_mount_dockerfile(shell, tmp_path, monkeypatch):
    (tmp_path / "Dockerfile").write_text("FROM debian:stable-slim\n")

    calls = []

    async def fake_build(force=False):
        return "custom:sandbox"

    async def fake_run(cmd, timeout=None, limit=None):
        calls.append(cmd)
        return b"", b"", 0, False

    monkeypatch.setattr(shell, "_build_image", fake_build)
    monkeypatch.setattr(shell, "_run_async_cmd", fake_run)

    await shell._start_container()

    run_cmd = next(cmd for cmd in calls if len(cmd) > 1 and cmd[1] == "run")

    assert run_cmd[-1] == "custom:sandbox"
    assert not any("Dockerfile" in arg for arg in run_cmd)
    assert "-v" not in run_cmd
    assert "--tmpfs" in run_cmd
    assert "/home/lumara:size=128m" in run_cmd
