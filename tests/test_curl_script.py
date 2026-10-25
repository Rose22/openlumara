# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-26) harness:openlumara status:unreviewed
"""
curl.sh - the one-line installer added upstream in dev 90610b1.

integration level: the real script is executed with `sh` in a subprocess,
with every external command it can reach (git, curl, wget, sudo, the six
package managers) replaced by recording stubs on PATH. Python candidates
resolve to the real interpreter running under test, so py_ok()'s version
gate is exercised for real. Nothing touches the network.

intent under test (per the script header):
- defaults: clone the Rose22 repo's dev branch into ~/openlumara, but every
  knob is an env override (REPO_URL / BRANCH / INSTALL_DIR / MIN_PY).
- a fresh INSTALL_DIR is cloned with --depth 1 --branch; an existing git
  checkout is updated with pull --ff-only instead; a non-git INSTALL_DIR is
  a hard error rather than a silent overwrite.
- a failed ff-only pull only warns: the install still completes.
- the script hands over to the repo's own run.sh via exec, forwarding args.
- python too old for MIN_PY -> package manager attempt -> uv fallback; if uv
  cannot be installed either, die with a clear message instead of installing
  an unusable interpreter.
- fetch() prefers curl, falls back to wget.
- output is plain text when stdout is not a tty (no ANSI leaks into logs).
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

CURL_SH = Path(__file__).resolve().parent.parent / "curl.sh"

STUB_GIT = """#!/bin/sh
echo "git $*" >> "$STUB_LOG"
case "$1" in
    clone)
        # git clone --depth 1 --branch BRANCH URL DEST
        dest=""
        for a in "$@"; do dest="$a"; done
        mkdir -p "$dest/.git"
        printf '#!/bin/sh\\necho "RUNSH $*"\\n' > "$dest/run.sh"
        exit 0
        ;;
esac
if [ "$1" = "-C" ]; then
    exit "${GIT_PULL_EXIT:-0}"
fi
exit 0
"""

STUB_LOGGER = """#!/bin/sh
echo "{name} $*" >> "$STUB_LOG"
exit 0
"""

STUB_FALSE = """#!/bin/sh
echo "{name} $*" >> "$STUB_LOG"
exit 1
"""

STUB_SUDO = """#!/bin/sh
exec "$@"
"""


def sh_run(curl_args=(), env_extra=None, env=None):
    """run curl.sh with the given argv tail and env overrides over `env`."""
    run_env = dict(env if env is not None else make_env())
    run_env.update(env_extra or {})
    return subprocess.run(
        ["sh", str(CURL_SH), *curl_args],
        env=run_env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def make_env(tmp_root=None, *, with_curl=True, with_wget=True, install_dir=None):
    """
    build a subprocess env whose PATH starts with a directory of command
    stubs. git clones into fake repos on disk; python3 is a wrapper around
    the interpreter running pytest, so py_ok()'s real version check applies.
    """
    root = Path(tmp_root) / f"curlsh-{os.getpid()}-{id(object())}"
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    home = root / "home"
    home.mkdir()

    # PATH deliberately does NOT include the real system PATH: the only
    # escape hatches are the handful of coreutils the script legitimately
    # needs, so tests can never reach a real curl/git/package manager.
    sys_dir = root / "sys"
    sys_dir.mkdir()
    for tool in ("sh", "id", "mkdir"):
        real = shutil.which(tool)
        assert real, f"host is missing {tool}"
        os.symlink(real, sys_dir / tool)

    (bin_dir / "git").write_text(STUB_GIT)
    (bin_dir / "python3").write_text(f'#!/bin/sh\nexec {sys.executable} "$@"\n')
    (bin_dir / "sudo").write_text(STUB_SUDO)
    for pm in ("apt-get", "dnf", "pacman", "zypper", "apk"):
        (bin_dir / pm).write_text(STUB_FALSE.format(name=pm))
    if with_curl:
        (bin_dir / "curl").write_text(STUB_LOGGER.format(name="curl"))
    if with_wget:
        (bin_dir / "wget").write_text(STUB_LOGGER.format(name="wget"))

    for f in bin_dir.iterdir():
        f.chmod(0o755)

    env = {
        "PATH": f"{bin_dir}{os.pathsep}{sys_dir}",
        "HOME": str(home),
        "STUB_LOG": str(root / "calls.log"),
        "INSTALL_DIR": str(install_dir or (root / "openlumara")),
    }
    env["_ROOT"] = str(root)
    return env


def calls(env):
    log = Path(env["STUB_LOG"])
    return log.read_text().splitlines() if log.exists() else []


# ---------------------------------------------------------------------------
# static contract
# ---------------------------------------------------------------------------

def test_curl_sh_passes_posix_syntax_check():
    # the script is piped through plain `sh` on wildly different systems, so
    # it must stay POSIX-compatible - bashisms are a hard failure
    result = subprocess.run(
        ["sh", "-n", str(CURL_SH)], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


# ---------------------------------------------------------------------------
# happy paths
# ---------------------------------------------------------------------------

def test_fresh_install_clones_defaults_and_executes_run_sh(tmp_path):
    env = make_env(tmp_path)

    result = sh_run(env=env)

    assert result.returncode == 0, result.stderr
    clone_calls = [c for c in calls(env) if c.startswith("git clone")]
    assert clone_calls == [
        "git clone --depth 1 --branch dev https://github.com/Rose22/openlumara "
        + env["INSTALL_DIR"]
    ]
    # the repo's own run.sh takes over and the installer banner is shown
    assert "RUNSH" in result.stdout
    assert "setup complete" in result.stdout


def test_env_overrides_reach_the_clone_command(tmp_path):
    env = make_env(tmp_path)

    result = sh_run(
        env=env,
        env_extra={
            "REPO_URL": "https://example.com/fork/openlumara",
            "BRANCH": "my-branch",
        },
    )

    assert result.returncode == 0, result.stderr
    assert any(
        c.startswith(
            "git clone --depth 1 --branch my-branch "
            "https://example.com/fork/openlumara "
        )
        for c in calls(env)
    )


def test_extra_args_are_forwarded_to_run_sh(tmp_path):
    env = make_env(tmp_path)

    result = sh_run(("--help",), env=env)

    assert result.returncode == 0, result.stderr
    assert 'RUNSH --help' in result.stdout


def test_existing_checkout_is_pulled_not_cloned(tmp_path):
    env = make_env(tmp_path)
    install = Path(env["INSTALL_DIR"])
    (install / ".git").mkdir(parents=True)
    (install / "run.sh").write_text('#!/bin/sh\necho "RUNSH $*"\n')

    result = sh_run(env=env)

    assert result.returncode == 0, result.stderr
    assert f"git -C {install} pull --ff-only" in calls(env)
    assert not any(c.startswith("git clone") for c in calls(env))
    assert "updating" in result.stdout


def test_failed_ff_only_pull_warns_but_completes(tmp_path):
    env = make_env(tmp_path)
    install = Path(env["INSTALL_DIR"])
    (install / ".git").mkdir(parents=True)
    (install / "run.sh").write_text('#!/bin/sh\necho "RUNSH $*"\n')

    result = sh_run(env=env, env_extra={"GIT_PULL_EXIT": "1"})

    assert result.returncode == 0, result.stderr
    assert "could not fast-forward" in result.stderr
    assert "RUNSH" in result.stdout


# ---------------------------------------------------------------------------
# failure paths
# ---------------------------------------------------------------------------

def test_existing_non_git_dir_is_fatal(tmp_path):
    env = make_env(tmp_path)
    Path(env["INSTALL_DIR"]).mkdir(parents=True)
    (Path(env["INSTALL_DIR"]) / "important.txt").write_text("do not delete me")

    result = sh_run(env=env)

    assert result.returncode == 1
    assert "exists but is not a git checkout" in result.stderr
    # the user's directory must survive untouched, and no clone attempted
    assert (Path(env["INSTALL_DIR"]) / "important.txt").exists()
    assert not any(c.startswith("git clone") for c in calls(env))


def test_python_too_old_goes_through_pkg_manager_then_uv_then_dies(tmp_path):
    env = make_env(tmp_path)

    result = sh_run(env=env, env_extra={"MIN_PY": "99.99"})

    assert result.returncode == 1
    assert "uv install failed" in result.stderr
    # the package manager was tried first (apt-get stub always fails)...
    assert any(c.startswith("apt-get update") for c in calls(env))
    # ...then the uv bootstrap was fetched over the network - via curl
    assert any(c.startswith("curl ") and "astral.sh/uv" in c for c in calls(env))
    # and no clone ever happened with an unusable interpreter
    assert not any(c.startswith("git clone") for c in calls(env))


def test_fetch_falls_back_to_wget_when_curl_is_absent(tmp_path):
    env = make_env(tmp_path, with_curl=False)

    result = sh_run(env=env, env_extra={"MIN_PY": "99.99"})

    assert result.returncode == 1
    assert any(c.startswith("wget ") and "astral.sh/uv" in c for c in calls(env))
    assert not any(c.startswith("curl ") for c in calls(env))


# ---------------------------------------------------------------------------
# output hygiene
# ---------------------------------------------------------------------------

def test_no_ansi_escapes_when_stdout_is_not_a_tty(tmp_path):
    # curl | sh pipes stdout, so the tty probe must keep colours off there
    env = make_env(tmp_path)

    result = sh_run(env=env)

    assert result.returncode == 0, result.stderr
    assert "\x1b[" not in result.stdout
