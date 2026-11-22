# AI Written: Claude Opus 5.5, reviewed by Claude Fable 5.2
import os

import pytest

import core


@pytest.fixture
def box(tmp_path):
    """sandbox with sub/file.txt, plus symlinks pointing at a folder outside of it"""
    base = tmp_path / "box"
    (base / "sub").mkdir(parents=True)
    (base / "sub" / "file.txt").write_text("inside")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret")
    (base / "link_file").symlink_to(outside / "secret.txt")
    (base / "link_dir").symlink_to(outside)
    return str(base)


def read(box, path):
    with os.fdopen(core.sandbox_open(box, path, os.O_RDONLY)) as f:
        return f.read()


def listdir(box, path):
    return core.sandbox_listdir(box, path)


def path(box, path):
    return core.sandbox_path(box, path)


@pytest.mark.parametrize("func", [path, read, listdir])
@pytest.mark.parametrize("attack", [
    "../outside/secret.txt",
    "sub/../../outside/secret.txt",
    "..\\outside\\secret.txt",
    "%2e%2e/outside/secret.txt",
    "%252e%252e%252foutside/secret.txt",
    "sub/file.txt\x00.png",
])
def test_traversal_rejected(box, func, attack):
    with pytest.raises(ValueError):
        func(box, attack)


@pytest.mark.parametrize("func", [path, read])
def test_symlinked_file_rejected(box, func):
    with pytest.raises(ValueError):
        func(box, "link_file")


def test_symlinked_directory_rejected(box):
    # sandbox_open and sandbox_listdir: see test_known_bugs.py
    with pytest.raises(ValueError):
        path(box, "link_dir/secret.txt")


def test_absolute_path_stays_inside(box):
    os.makedirs(os.path.join(box, "etc"))
    with open(os.path.join(box, "etc", "passwd"), "w") as f:
        f.write("sandboxed")
    assert path(box, "/etc/passwd") == os.path.join(box, "etc", "passwd")
    assert read(box, "/etc/passwd") == "sandboxed"


def test_normal_paths_allowed(box):
    assert path(box, "") == box
    assert path(box, "sub/file.txt") == os.path.join(box, "sub", "file.txt")
    assert path(box, "sub\\file.txt") == os.path.join(box, "sub", "file.txt")
    assert read(box, "sub/file.txt") == "inside"
    assert sorted(listdir(box, "")) == ["link_dir", "link_file", "sub"]
    # callers sometimes include the sandbox folder's own name
    assert listdir(box, "box/sub") == ["file.txt"]
    assert read(box, "box/sub/file.txt") == "inside"


def test_sandbox_open_writes_new_file(box):
    fd = core.sandbox_open(box, "sub/new.txt", os.O_WRONLY | os.O_CREAT)
    with os.fdopen(fd, "w") as f:
        f.write("hello")
    assert read(box, "sub/new.txt") == "hello"


@pytest.mark.parametrize("target", ["", "box"])
def test_sandbox_open_refuses_the_base_itself(box, target):
    with pytest.raises(ValueError):
        core.sandbox_open(box, target, os.O_RDONLY)


def test_get_data_path(isolated):
    assert core.get_data_path() == str(isolated)
    assert os.path.isdir(isolated)
    assert core.get_data_path("chats/a.json") == str(isolated / "chats" / "a.json")
    with pytest.raises(ValueError):
        core.get_data_path("../config.yml")


def test_relative_data_folder_is_inside_the_project(set_config, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # not the working directory
    set_config(core={"data_folder": "data"})
    assert core.get_data_path() == core.get_path("data")
