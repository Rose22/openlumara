# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-26) harness:openlumara status:unreviewed
"""
modules/host_shell + modules/file_manager - the two unsafe filesystem/shell
tool modules, exercised directly (never through the module installer).

integration level: real subprocesses for host_shell, but only with trivial
POSIX commands (printf/exit) against tmp_path; file_manager tools run
against tmp_path trees only.

intent under test:
- host_shell.exec returns stdout/stderr/exit_code with whitespace trimmed,
  never raising on nonzero exit; the command wrapper flattens that into
  display text and shows BLANK for no output at all.
- file_manager tools refuse operations on missing/wrong-typed paths with an
  error envelope instead of raising, and write/append/move/copy/remove
  behave like the tool descriptions promise.
- the system-info end prompt is gated by put_system_info_in_prompt.
"""

import pytest

import core
from harness import apply_config
from modules.file_manager.module import FileManager
from modules.host_shell.module import HostShell

BASE = {
    "api": {"max_context": 1000},
    "model": {"name": "test-model", "use_tools": True, "dynamic_tool_loading": False},
    "core": {"cmd_prefix": "/"},
}


def configure(module, **settings):
    apply_config(
        modules={"disabled_prompts": [], "settings": {module: settings}}, **BASE
    )


# ---------------------------------------------------------------------------
# host_shell
# ---------------------------------------------------------------------------

async def test_host_shell_exec_captures_streams_and_exit_code(fake_manager):
    configure("host_shell")
    mod = HostShell(fake_manager)

    res = await mod.exec("printf out; printf err 1>&2; exit 3")

    assert res["status"] == "success"
    assert res["content"] == {"stdout": "out", "stderr": "err", "exit_code": 3}


async def test_host_shell_exec_does_not_raise_on_failure(fake_manager):
    configure("host_shell")
    mod = HostShell(fake_manager)

    res = await mod.exec("exit 1")

    # nonzero exit is data, not an exception
    assert res["status"] == "success"
    assert res["content"]["exit_code"] == 1


async def test_host_shell_command_flattens_output(fake_manager):
    configure("host_shell")
    mod = HostShell(fake_manager)

    assert await mod.cmd_exec(["echo", "hello", "world"]) == "hello world"

    # stdout first, stderr appended on its own line
    both = await mod.cmd_exec(["printf", "out; printf e 1>&2"])
    assert both == "out\ne"

    assert await mod.cmd_exec(["true"]) == "BLANK"


# ---------------------------------------------------------------------------
# file_manager
# ---------------------------------------------------------------------------

@pytest.fixture
async def fm(fake_manager):
    configure("file_manager")
    return FileManager(fake_manager)


async def test_list_directory_and_errors(fm, tmp_path):
    folder = tmp_path / "files"
    folder.mkdir()
    (folder / "alpha.txt").write_text("a")

    res = await fm.list(str(folder))
    # success path returns the bare listing, not an envelope
    assert set(res) == {"alpha.txt"}

    missing = await fm.list(str(folder / "ghost"))
    assert missing == {"status": "error", "content": "path does not exist"}

    notdir = await fm.list(str(folder / "alpha.txt"))
    assert notdir["content"] == "target path is not a directory"


async def test_read_text_and_binary(fm, tmp_path):
    text = tmp_path / "note.txt"
    text.write_text("hello world")
    blob = tmp_path / "bin.dat"
    blob.write_bytes(b"\x00\xff\x01")

    assert await fm.read(str(text)) == {"status": "success", "content": "hello world"}
    assert await fm.read_binary(str(blob)) == {"status": "success", "content": b"\x00\xff\x01"}

    # binary content is refused by the text reader with guidance
    res = await fm.read(str(blob))
    assert res["status"] == "error"
    assert "read_binary" in res["content"]

    assert (await fm.read(str(tmp_path / "ghost")))["content"] == "path does not exist"
    assert (await fm.read(str(tmp_path)))["content"] == "target path is not a file"


async def test_write_creates_parents_then_append(fm, tmp_path):
    target = tmp_path / "deep" / "nested" / "file.txt"

    res = await fm.write(str(target), "line1\n")
    assert res["status"] == "success"
    assert target.read_text() == "line1\n"

    await fm.append(str(target), "line2\n")
    assert target.read_text() == "line1\nline2\n"

    # write overwrites instead of appending
    await fm.write(str(target), "fresh")
    assert target.read_text() == "fresh"


async def test_mkdir_remove_roundtrip(fm, tmp_path):
    newdir = tmp_path / "a" / "b" / "c"

    assert (await fm.mkdir(str(newdir)))["status"] == "success"
    assert newdir.is_dir()

    assert (await fm.remove(str(newdir)))["status"] == "success"
    assert not newdir.exists()

    assert (await fm.remove(str(tmp_path / "ghost"))) == {
        "status": "error", "content": "path does not exist",
    }


async def test_move_and_copy_files_and_dirs(fm, tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "inner.txt").write_text("data")

    moved = tmp_path / "moved" / "src"
    assert (await fm.move(str(src), str(moved)))["status"] == "success"
    assert not src.exists()
    assert (moved / "inner.txt").read_text() == "data"

    copied = tmp_path / "copy"
    assert (await fm.copy(str(moved), str(copied)))["status"] == "success"
    assert (copied / "inner.txt").read_text() == "data"
    assert moved.exists()  # copy leaves the source alone


async def test_get_info_reports_path_facts(fm, tmp_path):
    f = tmp_path / "info.txt"
    f.write_text("12345")

    res = await fm.get_info(str(f))

    assert res["status"] == "success"
    info = res["content"]
    assert info["name"] == "info.txt"
    assert info["absolute_path"] == str(f.absolute())
    assert info["size_bytes"] == 5
    assert info["is_file"] is True and info["is_dir"] is False

    assert (await fm.get_info(str(tmp_path / "ghost")))["content"] == "path does not exist"


async def test_system_info_end_prompt_is_gated(fm, fake_manager, fake_channel):
    fm.channel = fake_channel

    # the setting is a bare bool: unset reads return None, so the default
    # install shows no system info prompt at all (TEST_PLAN section 4 note)
    configure("file_manager")
    assert await fm.on_end_prompt() is None

    configure("file_manager", put_system_info_in_prompt=True)
    out = await fm.on_end_prompt()

    assert "OS:" in out and "home dir:" in out and "architecture:" in out
