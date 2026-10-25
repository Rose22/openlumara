# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
modules/memory - CRUD by ULID, pinned-memory system prompt, search.

integration level: real Memory module on FakeManager, real tmp-dir msgpack
+ json StorageLists (conftest isolation).

intent under test:
- create/edit/pin/unpin/delete round-trip through storage; delete moves
  the record into the deleted_memories list.
- id lookup is whitespace-tolerant.
- the system prompt contains pinned memories, newest first, capped by
  max_pinned_memories; the feature can be switched off entirely.
- list_unpinned excludes pinned entries and filters tags case-insensitively.
- search ranks via the shared core.search engine.
"""

import pytest

import core
from harness import apply_config
from modules.memory.module import Memory


def mem_config(**settings):
    apply_config(
        api={"max_context": 16768},
        model={"name": "test-model", "use_tools": False, "dynamic_tool_loading": False},
        modules={"disabled_prompts": [], "settings": {"memory": settings}},
        core={"cmd_prefix": "/"},
    )


@pytest.fixture
async def mem(fake_manager):
    mem_config()
    mod = Memory(fake_manager)
    await mod.on_ready()
    return mod


async def create(mem, content, tags=("tag",), pinned=False):
    res = await mem.create(content, list(tags), pinned)
    assert res["status"] == "success"
    return mem._mem[-1]["id"]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def test_create_stores_full_record_and_persists(mem):
    mid = await create(mem, "steven likes dark roast", tags=("coffee", "user"))

    stored = mem._mem[0]
    assert stored["id"] == mid
    assert stored["content"] == "steven likes dark roast"
    assert stored["tags"] == ["coffee", "user"]
    assert stored["pinned"] is False
    assert stored["date_created"]

    # survives a reload (msgpack round-trip)
    reloaded = core.storage.StorageList("memory", type="msgpack")
    assert reloaded[0]["content"] == "steven likes dark roast"


def test_get_index_is_whitespace_tolerant(mem):
    mem._mem.append({"id": "abc"})
    assert mem._get_index(" abc ") == 0
    assert mem._get_index("ghost") == -1


async def test_edit_updates_content_and_tags(mem):
    mid = await create(mem, "old", tags=("a",))

    res = await mem.edit(mid, content="new", tags=["b"])

    assert res["status"] == "success"
    assert mem._mem[0]["content"] == "new"
    assert mem._mem[0]["tags"] == ["b"]


async def test_edit_unknown_id_reports_not_found(mem):
    res = await mem.edit("ghost", content="x")
    assert "not found" in res["content"]


@pytest.mark.xfail(
    strict=True,
    reason="suspected bug: not-found results are wrapped in a SUCCESS "
    "envelope (self.result default); the module's own webui update route "
    "uses success=False for the very same message, so the tool methods "
    "just forgot the flag",
)
async def test_edit_unknown_id_is_an_error_envelope(mem):
    res = await mem.edit("ghost", content="x")
    assert res["status"] == "error"


async def test_pin_and_unpin_toggle_flag(mem):
    mid = await create(mem, "important")

    assert (await mem.pin(mid))["status"] == "success"
    assert mem._mem[0]["pinned"] is True

    assert (await mem.unpin(mid))["status"] == "success"
    assert mem._mem[0]["pinned"] is False

    assert "not found" in (await mem.pin("ghost"))["content"]
    assert "not found" in (await mem.unpin("ghost"))["content"]


async def test_delete_moves_record_to_deleted_list(mem):
    mid = await create(mem, "obsolete", tags=("x",))

    res = await mem.delete(mid)

    assert res["status"] == "success"
    assert list(mem._mem) == []
    assert len(mem._mem_deleted) == 1
    assert mem._mem_deleted[0]["id"] == mid
    assert mem._mem_deleted[0]["tags"] == ["x"]

    assert "not found" in (await mem.delete(mid))["content"]


# ---------------------------------------------------------------------------
# system prompt
# ---------------------------------------------------------------------------

async def test_system_prompt_contains_pinned_memories(mem):
    await create(mem, "unpinned thought")
    await create(mem, "pinned identity fact", pinned=True)

    prompt = await mem.on_system_prompt()

    assert "pinned identity fact" in prompt
    assert "unpinned thought" not in prompt


async def test_system_prompt_pinned_cap_newest_first(mem):
    mem_config(max_pinned_memories=2)

    ids = []
    for i in range(4):
        ids.append(await create(mem, f"pinned {i}", pinned=True))

    prompt = await mem.on_system_prompt()

    # exactly the 2 newest pinned memories, oldest dropped
    assert ids[3] in prompt and ids[2] in prompt
    assert ids[1] not in prompt and ids[0] not in prompt


async def test_system_prompt_no_pinned_placeholder(mem):
    await create(mem, "just a memory")
    prompt = await mem.on_system_prompt()
    assert "no pinned memories" in prompt


async def test_system_prompt_feature_can_be_disabled(mem):
    mem_config(put_pinned_memories_in_system_prompt=False)
    await create(mem, "pinned but hidden", pinned=True)
    assert await mem.on_system_prompt() is None


async def test_end_prompt_nudge_opt_in(mem):
    assert await mem.on_end_prompt() is None
    mem_config(insert_nudge_prompt=True)
    prompt = await mem.on_end_prompt()
    assert "long-term memory" in prompt


# ---------------------------------------------------------------------------
# listing and search
# ---------------------------------------------------------------------------

async def test_list_unpinned_filters_pinned_and_tags(mem):
    await create(mem, "keep visible", tags=("Work",))
    await create(mem, "hidden by pin", tags=("work",), pinned=True)
    await create(mem, "other topic", tags=("fun",))

    all_unpinned = await mem.list_unpinned()
    assert "keep visible" in all_unpinned["content"]
    assert "hidden by pin" not in all_unpinned["content"]

    tagged = await mem.list_unpinned(tag="work")  # case-insensitive
    assert tagged["content"].count("keep visible") == 1
    assert "other topic" not in tagged["content"]

    none = await mem.list_unpinned(tag="nothing")
    assert "No unpinned memories found" in none["content"] and "nothing" in none["content"]


async def test_search_finds_by_content_and_reports_misses(mem):
    id_a = await create(mem, "the user loves kettle coffee", tags=("drink",))
    id_b = await create(mem, "the user drives a blue car", tags=("car",))

    res = await mem.search("kettle")

    assert res["status"] == "success"
    assert id_a in res["content"]
    assert id_b not in res["content"]

    miss = await mem.search("zzzqqq")
    assert "No memories found" in miss["content"]