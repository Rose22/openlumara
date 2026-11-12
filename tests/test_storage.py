# AI Written: Claude Opus 5.5, reviewed by Claude Fable 5.2
import os

import pytest

import core
from core.storage import StorageDict, StorageList, StorageText


def touch_later(path):
    # make sure an external write gets a different mtime than our cached one
    st = os.stat(path)
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))


@pytest.mark.parametrize("type, ext, items", [
    ("json", "json", [1, "two", {"three": [3]}]),
    ("msgpack", "mp", [1, "two", {"three": [3]}]),
    ("text", "txt", ["line one", "line two"]),
])
def test_list_roundtrip(tmp_path, type, ext, items):
    data = StorageList("things", type, path=str(tmp_path))
    data.extend(items)
    data.save()

    assert data.path == str(tmp_path / f"things.{ext}")
    assert list(StorageList("things", type, path=str(tmp_path))) == items


def test_list_get_reloads_external_change(tmp_path):
    data = StorageList("things", "json", path=str(tmp_path))
    data.extend(["old"])
    data.save()

    with open(data.path, "w") as f:
        f.write('["new"]')
    touch_later(data.path)

    assert data.get(0) == "new"


@pytest.mark.parametrize("type", ["json", "yaml", "msgpack"])
def test_dict_roundtrip(tmp_path, type):
    data = StorageDict("stuff", type, path=str(tmp_path))
    data["a"] = {"nested": [1, 2]}
    data["b"] = "text"
    data.save()

    assert dict(StorageDict("stuff", type, path=str(tmp_path))) == {"a": {"nested": [1, 2]}, "b": "text"}


def test_dict_get_reloads_external_change(tmp_path):
    data = StorageDict("stuff", "json", path=str(tmp_path))
    data["key"] = "old"
    data.save()

    with open(data.path, "w") as f:
        f.write('{"key": "new"}')
    touch_later(data.path)

    assert data.get("key") == "new"
    assert data.get("missing", "fallback") == "fallback"


def test_json_folder_one_file_per_key(tmp_path):
    data = StorageDict("chars", "json_folder", path=str(tmp_path))
    data["alice"] = {"age": 30}
    data["bob"] = {"age": 40}
    data.save()

    folder = tmp_path / "chars"
    assert sorted(os.listdir(folder)) == ["alice.json", "bob.json"]
    assert dict(StorageDict("chars", "json_folder", path=str(tmp_path))) == {"alice": {"age": 30}, "bob": {"age": 40}}

    del data["bob"]
    data.save()
    assert os.listdir(folder) == ["alice.json"]


def test_json_folder_sanitizes_filenames(tmp_path):
    data = StorageDict("chars", "json_folder", path=str(tmp_path))
    data["a/b:c"] = 1
    data.save()

    assert os.listdir(tmp_path / "chars") == ["a_b_c.json"]


def test_markdown_nested_keys_become_dirs(tmp_path):
    notes = StorageDict("notes", "markdown", path=str(tmp_path))
    notes["ideas"] = {"openlumara": {"topic": "modules"}}
    notes["todo"] = "buy milk"
    notes.save()

    assert (tmp_path / "notes" / "ideas" / "openlumara" / "topic.md").read_text() == "modules"
    assert (tmp_path / "notes" / "todo.md").read_text() == "buy milk"

    reloaded = StorageDict("notes", "markdown", path=str(tmp_path))
    assert dict(reloaded) == {"ideas": {"openlumara": {"topic": "modules"}}, "todo": "buy milk"}


def test_markdown_slash_key_is_nested_on_reload(tmp_path):
    notes = StorageDict("notes", "markdown", path=str(tmp_path))
    notes["a/b"] = "deep"
    notes.save()

    assert (tmp_path / "notes" / "a" / "b.md").exists()
    assert dict(StorageDict("notes", "markdown", path=str(tmp_path))) == {"a": {"b": "deep"}}


def test_markdown_prunes_stale_files_and_dirs(tmp_path):
    notes = StorageDict("notes", "markdown", path=str(tmp_path))
    notes["keep"] = "x"
    notes["old"] = {"note": "y"}
    notes.save()

    del notes["old"]
    notes.save()

    assert os.listdir(tmp_path / "notes") == ["keep.md"]


def test_markdown_rejects_path_traversal(tmp_path):
    notes = StorageDict("notes", "markdown", path=str(tmp_path))
    notes["../escape"] = "nope"

    with pytest.raises(ValueError):
        notes.save()
    assert not (tmp_path / "escape.md").exists()


def test_text_roundtrip_and_external_change(tmp_path):
    text = StorageText("notes.txt", path=str(tmp_path))
    text.set("hello")

    assert str(StorageText("notes.txt", path=str(tmp_path))) == "hello"

    with open(text.path, "w") as f:
        f.write("changed")
    touch_later(text.path)
    assert text.get() == "changed"


def test_temporary_mode_never_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(core.storage, "TEMPORARY", True)
    store = str(tmp_path / "store")  # tmp_path itself holds the test config

    items = StorageList("list", "json", path=store)
    items.append(1)
    items.save()
    data = StorageDict("dict", "json", path=store)
    data["a"] = 1
    data.save()
    notes = StorageDict("notes", "markdown", path=store)
    notes["a"] = "b"
    notes.save()
    StorageText("text.txt", path=store).set("hi")

    assert os.listdir(store) == []


def test_override_temporary_still_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(core.storage, "TEMPORARY", True)
    store = str(tmp_path / "store")

    data = StorageDict("config", "yaml", path=store, override_temporary=True)
    data["a"] = 1
    data.save()

    monkeypatch.setattr(core.storage, "TEMPORARY", False)
    assert dict(StorageDict("config", "yaml", path=store)) == {"a": 1}
