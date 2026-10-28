# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
core/storage.py: StorageList / StorageDict / StorageText.

intent under test:
- every storage type round-trips its content through disk (json, yaml,
  msgpack, text, json_folder, markdown).
- reads see external changes (get()/load() reload when the file's mtime
  moved), while direct in-memory access uses the cache on purpose.
- load(data) replaces the in-memory content only; persisting is the
  caller's job (save()).
- json_folder mode: one file per key, sanitized filenames, stale files
  pruned, unreadable files skipped instead of fatal.
- markdown mode: "a/b" keys become nested directories, invalid keys raise
  ValueError listing them (and are dropped from memory), stale .md files
  and empty dirs are pruned.
- TEMPORARY mode means "never touch disk"; override_temporary re-enables
  writes for that one instance (config uses this).
"""

import json
import os
import time

import pytest

import core


# ---------------------------------------------------------------------------
# StorageList
# ---------------------------------------------------------------------------

def test_list_json_roundtrip_and_extension(tmp_path):
    sl = core.storage.StorageList("things", "json", path=str(tmp_path))
    sl.append({"a": 1})
    sl.append("two")
    sl.save()

    assert (tmp_path / "things.json").exists()

    sl2 = core.storage.StorageList("things", "json", path=str(tmp_path))
    assert list(sl2) == [{"a": 1}, "two"]


@pytest.mark.xfail(
    strict=True,
    reason="suspected bug: StorageList.save() passes the StorageList subclass "
    "itself to yaml.safe_dump, which cannot represent list subclasses, so "
    "every yaml StorageList write raises RepresenterError - even the "
    "empty-file init save. StorageDict works because it dumps dict(self). "
    "Latent: no caller currently uses yaml StorageLists. "
    "(TEST_PLAN.md section 5, finding 5)",
)
def test_list_yaml_roundtrip_and_extension(tmp_path):
    sl = core.storage.StorageList("things", "yaml", path=str(tmp_path))
    sl.append({"naïve": "wörth"})
    sl.save()

    assert (tmp_path / "things.yml").exists()

    sl2 = core.storage.StorageList("things", "yaml", path=str(tmp_path))
    assert list(sl2) == [{"naïve": "wörth"}]


def test_list_msgpack_roundtrip_is_binary(tmp_path):
    sl = core.storage.StorageList("things", "msgpack", path=str(tmp_path))
    sl.append({"bin": b"\x00\x01"})
    sl.save()

    raw = (tmp_path / "things.mp").read_bytes()
    assert isinstance(raw, bytes)

    sl2 = core.storage.StorageList("things", "msgpack", path=str(tmp_path))
    assert list(sl2) == [{"bin": b"\x00\x01"}]


def test_list_text_roundtrip_joins_with_newline(tmp_path):
    sl = core.storage.StorageList("lines", "text", path=str(tmp_path))
    sl.extend(["one", "two"])
    sl.save()

    assert (tmp_path / "lines.txt").read_text() == "one\ntwo"

    sl2 = core.storage.StorageList("lines", "text", path=str(tmp_path))
    assert list(sl2) == ["one", "two"]


def test_list_init_creates_missing_file_for_structured_types(tmp_path):
    # yaml omitted: its save() is broken for StorageList (see the xfail above)
    for type_name, ext in (("json", "json"), ("msgpack", "mp")):
        sl = core.storage.StorageList(f"fresh_{type_name}", type_name, path=str(tmp_path))
        assert (tmp_path / f"fresh_{type_name}.{ext}").exists()
        assert list(sl) == []


def test_list_load_data_replaces_in_memory_without_saving(tmp_path):
    sl = core.storage.StorageList("things", "json", path=str(tmp_path))
    sl.append({"disk": True})
    sl.save()

    result = sl.load([{"memory": True}])

    assert result is sl
    assert list(sl) == [{"memory": True}]
    # disk untouched until save()
    on_disk = json.loads((tmp_path / "things.json").read_text())
    assert on_disk == [{"disk": True}]


def test_list_get_reflects_external_change(tmp_path):
    sl = core.storage.StorageList("things", "json", path=str(tmp_path))
    sl.append("mine")
    sl.save()

    external = tmp_path / "things.json"
    external.write_text(json.dumps(["external"]))
    # force a different mtime so change detection can't miss a fast rewrite
    os.utime(external, (time.time() + 5, time.time() + 5))

    assert sl.get(0) == "external"


def test_list_direct_indexing_deliberately_uses_cache(tmp_path):
    sl = core.storage.StorageList("things", "json", path=str(tmp_path))
    sl.append("mine")
    sl.save()

    external = tmp_path / "things.json"
    external.write_text(json.dumps(["external"]))
    os.utime(external, (time.time() + 5, time.time() + 5))

    # __getitem__ does not reload - that is what get() is for
    assert sl[0] == "mine"


def test_list_two_instances_last_save_wins_and_stays_parseable(tmp_path):
    a = core.storage.StorageList("things", "json", path=str(tmp_path))
    b = core.storage.StorageList("things", "json", path=str(tmp_path))

    a.append("from-a")
    a.save()
    b.append("from-b")
    b.save()

    winner = core.storage.StorageList("things", "json", path=str(tmp_path))
    assert list(winner) == ["from-b"]


@pytest.mark.xfail(
    strict=True,
    reason="suspected bug: text-type save() skips the write when the list is "
    "empty, so clearing or creating an empty text list never reaches disk "
    "(TEST_PLAN.md section 5, finding 4)",
)
def test_list_emptying_text_list_clears_the_file(tmp_path):
    sl = core.storage.StorageList("lines", "text", path=str(tmp_path))
    sl.extend(["stale"])
    sl.save()

    sl.load([])
    sl.save()

    fresh = core.storage.StorageList("lines", "text", path=str(tmp_path))
    assert list(fresh) == []


# ---------------------------------------------------------------------------
# StorageDict
# ---------------------------------------------------------------------------

def test_dict_json_roundtrip_and_get_reloads(tmp_path):
    sd = core.storage.StorageDict("conf", "json", path=str(tmp_path))
    sd["keep"] = 1
    sd.save()

    assert (tmp_path / "conf.json").exists()
    assert sd.get("keep") == 1

    external = tmp_path / "conf.json"
    external.write_text(json.dumps({"keep": 99, "added": True}))
    os.utime(external, (time.time() + 5, time.time() + 5))

    assert sd.get("keep") == 99
    assert sd.get("added") is True


def test_dict_load_data_returns_true_and_does_not_save(tmp_path):
    sd = core.storage.StorageDict("conf", "json", path=str(tmp_path))
    sd["disk"] = True
    sd.save()

    result = sd.load({"memory": True})

    assert result is True
    assert dict(sd) == {"memory": True}
    on_disk = json.loads((tmp_path / "conf.json").read_text())
    assert on_disk == {"disk": True}


def test_dict_yaml_roundtrip(tmp_path):
    sd = core.storage.StorageDict("conf", "yaml", path=str(tmp_path))
    sd["nested"] = {"list": [1, 2, {"k": "v"}]}
    sd.save()

    sd2 = core.storage.StorageDict("conf", "yaml", path=str(tmp_path))
    assert sd2["nested"]["list"][2] == {"k": "v"}


# ---- json_folder mode ----

def test_json_folder_one_file_per_key_and_reload(tmp_path):
    folder = tmp_path / "entries"
    sd = core.storage.StorageDict("entries", "json_folder", path=str(tmp_path))
    sd["alpha"] = {"body": "first"}
    sd["beta"] = {"body": "second"}
    sd.save()

    assert (folder / "alpha.json").exists()
    assert (folder / "beta.json").exists()
    assert json.loads((folder / "alpha.json").read_text()) == {"body": "first"}

    sd2 = core.storage.StorageDict("entries", "json_folder", path=str(tmp_path))
    assert sd2.get("beta") == {"body": "second"}


def test_json_folder_sanitizes_key_into_safe_filename(tmp_path):
    sd = core.storage.StorageDict("entries", "json_folder", path=str(tmp_path))
    sd["a/b:c*"] = 1
    sd.save()

    assert (tmp_path / "entries" / "a_b_c_.json").exists()


def test_json_folder_prunes_files_of_removed_keys(tmp_path):
    sd = core.storage.StorageDict("entries", "json_folder", path=str(tmp_path))
    sd["keep"] = 1
    sd["drop"] = 2
    sd.save()

    sd2 = core.storage.StorageDict("entries", "json_folder", path=str(tmp_path))
    del sd2["drop"]
    sd2.save()

    assert (tmp_path / "entries" / "keep.json").exists()
    assert not (tmp_path / "entries" / "drop.json").exists()


def test_json_folder_skips_unreadable_files(tmp_path):
    sd = core.storage.StorageDict("entries", "json_folder", path=str(tmp_path))
    sd["good"] = {"ok": True}
    sd.save()

    (tmp_path / "entries" / "broken.json").write_text("{not json")

    sd2 = core.storage.StorageDict("entries", "json_folder", path=str(tmp_path))
    # a single corrupt file must not take down the whole folder
    assert sd2.get("good") == {"ok": True}


def test_json_folder_disk_mtime_is_newest_json(tmp_path):
    sd = core.storage.StorageDict("entries", "json_folder", path=str(tmp_path))
    sd["one"] = 1
    sd.save()

    old, new = time.time() - 100, time.time() + 10
    os.utime(tmp_path / "entries" / "one.json", (old, old))
    (tmp_path / "entries" / "two.json").write_text("2")
    os.utime(tmp_path / "entries" / "two.json", (new, new))

    fresh = core.storage.StorageDict("entries", "json_folder", path=str(tmp_path))
    assert fresh._last_modified == pytest.approx(new)


# ---- markdown mode ----

def test_markdown_nested_key_becomes_directory_tree(tmp_path):
    sd = core.storage.StorageDict("notes", "markdown", path=str(tmp_path))
    sd["ideas/openlumara/topic"] = "the content"
    sd.save()

    written = tmp_path / "notes" / "ideas" / "openlumara" / "topic.md"
    assert written.exists()
    assert written.read_text() == "the content"

    sd2 = core.storage.StorageDict("notes", "markdown", path=str(tmp_path))
    assert sd2["ideas"]["openlumara"]["topic"] == "the content"


def test_markdown_invalid_key_raises_listing_failed_keys(tmp_path):
    sd = core.storage.StorageDict("notes", "markdown", path=str(tmp_path))
    sd["ok"] = "fine"
    sd["../escape"] = "traversal"

    with pytest.raises(ValueError) as excinfo:
        sd.save()

    # the raise must name the offending key so callers can fix it
    assert "../escape" in str(excinfo.value)
    # valid keys still made it to disk before the raise
    assert (tmp_path / "notes" / "ok.md").read_text() == "fine"


@pytest.mark.xfail(
    strict=True,
    reason="suspected bug: markdown save() prunes failed keys with "
    "_delete_nested_key(), which re-splits the flat key by '/'; it only "
    "removes the key when every failed segment is a full path component, "
    "so keys with embedded slashes (like '../escape') survive in memory "
    "even though the code comment promises failed keys are deleted "
    "(TEST_PLAN.md section 5, finding 6)",
)
def test_markdown_invalid_flat_key_is_dropped_from_memory(tmp_path):
    sd = core.storage.StorageDict("notes", "markdown", path=str(tmp_path))
    sd["ok"] = "fine"
    sd["../escape"] = "traversal"

    with pytest.raises(ValueError):
        sd.save()

    assert "../escape" not in sd
    assert "ok" in sd


def test_markdown_prunes_stale_files_and_empty_dirs(tmp_path):
    sd = core.storage.StorageDict("notes", "markdown", path=str(tmp_path))
    sd["ideas/sub/page"] = "old"
    sd.save()
    stale = tmp_path / "notes" / "ideas" / "sub" / "page.md"
    assert stale.exists()

    # a fresh instance loads the old page, so removal is modeled as
    # clearing the key before saving again
    sd2 = core.storage.StorageDict("notes", "markdown", path=str(tmp_path))
    sd2.clear()
    sd2["elsewhere"] = "new"
    sd2.save()

    assert not stale.exists()
    assert not (tmp_path / "notes" / "ideas").exists()
    assert (tmp_path / "notes" / "elsewhere.md").exists()


# ---- search ----

async def test_dict_search_returns_key_score_pairs(tmp_path):
    sd = core.storage.StorageDict("conf", "json", path=str(tmp_path))
    sd["recipe_apple"] = "apple pie is a nice dessert"
    sd["other"] = "banana split"
    sd.save()

    results = await sd.search("apple")

    assert results, "search should find the apple recipe"
    assert isinstance(results[0], tuple)
    assert results[0][0] == "recipe_apple"


# ---- TEMPORARY / override_temporary ----

def test_temporary_mode_never_touches_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(core.storage, "TEMPORARY", True)

    existing = tmp_path / "conf.json"
    existing.write_text(json.dumps({"disk": "value"}))

    sd = core.storage.StorageDict("conf", "json", path=str(tmp_path))
    # TEMPORARY skips the initial load too
    assert dict(sd) == {}

    sd["memory"] = 1
    sd.save()
    assert json.loads(existing.read_text()) == {"disk": "value"}


def test_override_temporary_writes_despite_temporary(tmp_path, monkeypatch):
    monkeypatch.setattr(core.storage, "TEMPORARY", True)

    sd = core.storage.StorageDict(
        "conf", "json", path=str(tmp_path), override_temporary=True
    )
    sd["written"] = True
    sd.save()

    assert json.loads((tmp_path / "conf.json").read_text()) == {"written": True}

    # with override, get() skips disk reloads too (in-memory wins)
    external = tmp_path / "conf.json"
    external.write_text(json.dumps({"written": True, "external": 1}))
    os.utime(external, (time.time() + 5, time.time() + 5))
    assert sd.get("external") is None


# ---------------------------------------------------------------------------
# StorageText
# ---------------------------------------------------------------------------

def test_text_set_get_roundtrip_and_str(tmp_path):
    st = core.storage.StorageText("note", path=str(tmp_path))
    assert (tmp_path / "note").exists()
    assert st.get() == ""

    st.set("hello text")
    assert (tmp_path / "note").read_text() == "hello text"

    st2 = core.storage.StorageText("note", path=str(tmp_path))
    assert st2.get() == "hello text"
    assert str(st2) == "hello text"


def test_text_get_reflects_external_change(tmp_path):
    st = core.storage.StorageText("note", path=str(tmp_path))
    st.set("mine")

    external = tmp_path / "note"
    external.write_text("external")
    os.utime(external, (time.time() + 5, time.time() + 5))

    assert st.get() == "external"


def test_text_search_returns_snippet_or_none(tmp_path):
    st = core.storage.StorageText("note", path=str(tmp_path))
    st.set("the quick brown fox jumps over the lazy dog")

    snippet = st.search("brown")
    assert snippet is not None
    assert "brown" in snippet.lower()

    assert st.search("zebra") is None
