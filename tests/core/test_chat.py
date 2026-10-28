# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
core/chat.py: the Chat class (index management, resume, system prompt,
export, search, migration).

integration level: real Chat + real Messages on top of FakeChannel, with
all files landing in the conftest tmp data dir. FakeContext stands in for
core.context.Context so nothing hits an API.

intent under test:
- autoload() is the async constructor: resume the last chat when
  core.auto_resume_chats is on and a current file exists, otherwise create
  a fresh chat.
- index entries carry id/title/category/tags/token_usage/metadata/created/updated.
- current-chat bookkeeping survives deletes (shift / clamp / auto-create).
- unknown keys raise on set(), return default on get().
- system prompt: module prompts joined with headers, top/middle/bottom
  ordering, cached per chat, broken modules quarantined, pure_mode blanks.
- old single-file chat format migrates with a backup; an un-backupable
  file aborts startup (sys.exit) rather than destroying data.
"""

import json
import os
import shutil
import sys
import time

import pytest

import core
from harness import apply_config


class StubModule:
    """minimal module stub for system/end prompt assembly"""

    def __init__(self, name, prompt=None, end=None, error=False, header=None):
        self.name = name
        self._prompt = prompt
        self._end = end
        self._error = error
        if header is not None:
            self.header = header

    async def on_system_prompt(self):
        if self._error:
            raise RuntimeError("kaboom")
        return self._prompt

    async def on_end_prompt(self):
        return self._end


@pytest.fixture
def chat_channel(fake_channel):
    # fake_channel already carries a FakeContext + FakeManager
    return fake_channel


@pytest.fixture
async def chat(chat_channel):
    ch = core.chat.Chat(chat_channel)
    await ch.autoload()
    return ch


def data_dir_files(data_dir):
    return sorted(
        os.path.relpath(os.path.join(root, f), data_dir)
        for root, _dirs, files in os.walk(data_dir)
        for f in files
    )


# ---------------------------------------------------------------------------
# autoload / new
# ---------------------------------------------------------------------------

async def test_autoload_creates_chat_and_persists_index(chat_channel, isolate_lumara_paths):
    ch = core.chat.Chat(chat_channel)
    await ch.autoload()

    assert ch.current == 0
    assert len(ch.data) == 1

    entry = ch.data[0]
    assert isinstance(entry["id"], str) and len(entry["id"]) == 8
    assert entry["title"] == "New chat"
    assert entry["category"] == "general"
    assert entry["tags"] == []
    assert entry["metadata"] == {}
    assert entry["created"] == entry["updated"]

    files = data_dir_files(isolate_lumara_paths)
    assert os.path.join("chats", "fake", "index.mp") in files
    assert os.path.join("chats", "fake", "current") in files

    with open(ch.current_save_path) as f:
        assert f.read() == "0"

    assert isinstance(ch.messages, core.messages.Messages)


async def test_autoload_resumes_last_chat_when_enabled(chat_channel):
    apply_config(core={"auto_resume_chats": True})

    ch = core.chat.Chat(chat_channel)
    await ch.autoload()
    await ch.new(title="second chat")

    ch2 = core.chat.Chat(chat_channel)
    await ch2.autoload()

    assert ch2.current == 1
    assert ch2.get("title") == "second chat"
    # resuming must not spawn another chat
    assert len(ch2.data) == 2


async def test_autoload_creates_new_when_resume_disabled(chat_channel):
    ch = core.chat.Chat(chat_channel)
    await ch.autoload()
    assert os.path.exists(ch.current_save_path)

    ch2 = core.chat.Chat(chat_channel)
    await ch2.autoload()

    assert len(ch2.data) == 2


async def test_autoload_with_unreadable_current_file_logs_and_recovers(chat_channel):
    apply_config(core={"auto_resume_chats": True})

    ch = core.chat.Chat(chat_channel)
    await ch.autoload()
    with open(ch.current_save_path, "w") as f:
        f.write("not-a-number")

    ch2 = core.chat.Chat(chat_channel)
    await ch2.autoload()

    assert ch2.current == 1  # a fresh chat was created
    assert any("autoresume" in msg for _cat, msg in chat_channel.logs)


async def test_new_assigns_unique_ids_and_advances_current(chat):
    first_id = chat.get("id")
    first_current = chat.current

    second_id = await chat.new(category="work", title="second", metadata={"k": 1})

    assert second_id != first_id
    assert chat.current == first_current + 1
    assert chat.get("category") == "work"
    assert chat.get("metadata") == {"k": 1}
    # the old chat is still in the index
    assert chat.data[0]["id"] == first_id


# ---------------------------------------------------------------------------
# load / delete
# ---------------------------------------------------------------------------

async def test_find_index_is_case_insensitive(chat):
    chat_id = chat.get("id")
    assert chat._find_index(chat_id.lower()) == 0
    assert chat._find_index(chat_id.upper()) == 0
    assert chat._find_index("deadbeef") is None


async def test_load_switches_silently_allows_same_and_raises_on_unknown(chat):
    other = await chat.new(title="other")
    first = chat.data[0]["id"]

    assert await chat.load(first) is True
    assert chat.current == 0
    assert await chat.load(first) is False  # already loaded

    with pytest.raises(Exception, match="blank chat id"):
        await chat.load("nosuchid")


async def test_delete_current_chat_clamps_and_removes_history(chat, isolate_lumara_paths):
    await chat.new(title="second")
    await chat.new(title="third")
    await chat.messages.add({"role": "user", "content": "bye"})
    victim_id = chat.get("id")
    history_file = os.path.join(isolate_lumara_paths, "chats", "fake", "history", f"{victim_id}.json")
    assert os.path.exists(history_file)

    current = await chat.delete(victim_id)

    assert not os.path.exists(history_file)
    assert len(chat.data) == 2
    # current was 2, deleted 2 -> min(2, len-1) = 1
    assert current == 1
    assert chat.get("title") == "second"


async def test_delete_earlier_chat_shifts_current_down(chat):
    await chat.new(title="second")
    await chat.new(title="third")
    first_id = chat.data[0]["id"]
    assert chat.current == 2

    current = await chat.delete(first_id)

    # current must keep pointing at the same chat ("third"), now at index 1
    assert current == 1
    assert chat.get("title") == "third"


async def test_deleting_everything_autocreates_a_fresh_chat(chat):
    victim = chat.get("id")

    current = await chat.delete(victim)

    assert len(chat.data) == 1
    assert current == 0
    assert chat.get("id") != victim
    assert chat.get("title") == "New chat"


async def test_delete_unknown_id_returns_false(chat):
    assert await chat.delete("nosuchid") is False


# ---------------------------------------------------------------------------
# get / set / clear / timestamps
# ---------------------------------------------------------------------------

async def test_get_set_contract(chat):
    assert chat.get()["title"] == "New chat"
    assert chat.get("title") == "New chat"
    assert chat.get("nonexistent", default="fallback") == "fallback"

    assert await chat.set("title", "renamed") is True
    assert chat.get("title") == "renamed"

    with pytest.raises(Exception, match="not a valid chat property"):
        await chat.set("nonexistent", 1)


async def test_operations_without_loaded_chat_raise(chat_channel):
    ch = core.chat.Chat(chat_channel)  # no autoload

    with pytest.raises(Exception, match="No chat is currently loaded"):
        ch.get()
    with pytest.raises(Exception, match="No chat is currently loaded"):
        await ch.set("title", "x")
    with pytest.raises(Exception, match="No chat is currently loaded"):
        await ch.clear()
    with pytest.raises(Exception, match="No chat is currently loaded"):
        await ch.update_timestamp()
    with pytest.raises(Exception, match="No chat is currently loaded"):
        await ch.export()


async def test_clear_empties_messages_and_resets_usage(chat):
    await chat.messages.add({"role": "user", "content": "hi"})
    await chat.set("token_usage", 500)
    chat.data[chat.current]["token_usage_mark"] = 5

    assert await chat.clear() is True

    assert len(await chat.messages.get()) == 0
    assert chat.get("token_usage") == 0
    assert chat.data[chat.current]["token_usage_mark"] == 0


async def test_update_timestamp_refreshes_and_persists(chat):
    chat.data[chat.current]["updated"] = "2000-01-01T00:00:00"
    chat.data.save()

    await chat.update_timestamp()

    # re-read from disk to prove persistence
    fresh = core.storage.StorageList(
        os.path.join("chats", "fake", "index"), "msgpack"
    )
    assert fresh[0]["updated"] > "2000-01-01T00:00:00"


async def test_get_all_sorted_by_updated_desc(chat):
    await chat.new(title="old")
    await chat.new(title="newest")
    chat.data[1]["updated"] = "1999-01-01T00:00:00"

    ordered = chat.get_all()

    assert ordered[0]["title"] == "newest"
    assert ordered[-1]["title"] == "old"


async def test_get_categories_unique_in_encounter_order(chat):
    await chat.new(category="alpha")
    await chat.new(category="beta")
    await chat.new(category="alpha")

    assert chat.get_categories() == ["general", "alpha", "beta"]


# ---------------------------------------------------------------------------
# system prompt assembly
# ---------------------------------------------------------------------------

async def test_system_prompt_orders_top_middle_bottom_with_headers(chat_channel):
    apply_config(model={"use_tools": True}, modules={"disabled_prompts": []})
    chat_channel.manager.modules = {
        "calendar": StubModule("calendar", prompt="middle bit"),
        "identity": StubModule("identity", prompt="top bit"),
        "time": StubModule("time", prompt="bottom bit"),
    }

    ch = core.chat.Chat(chat_channel)
    await ch.autoload()
    prompt = await ch.get_system_prompt()

    assert "# Identity\ntop bit" in prompt
    assert "# Calendar\nmiddle bit" in prompt
    assert "# Time\nbottom bit" in prompt
    assert prompt.index("# Identity") < prompt.index("# Calendar") < prompt.index("# Time")


async def test_system_prompt_custom_header(chat_channel):
    apply_config(model={"use_tools": True}, modules={"disabled_prompts": []})
    chat_channel.manager.modules = {
        "calendar": StubModule("calendar", prompt="dates", header="My Dates"),
    }

    ch = core.chat.Chat(chat_channel)
    await ch.autoload()

    assert "# My Dates\ndates" in await ch.get_system_prompt()


async def test_system_prompt_is_cached_until_invalidated(chat_channel):
    apply_config(model={"use_tools": True}, modules={"disabled_prompts": []})
    mod = StubModule("identity", prompt="v1")
    chat_channel.manager.modules = {"identity": mod}

    ch = core.chat.Chat(chat_channel)
    await ch.autoload()
    first = await ch.get_system_prompt()

    mod._prompt = "v2"
    assert await ch.get_system_prompt() == first  # frozen

    ch._cached_system_prompt = None
    second = await ch.get_system_prompt()
    assert "v2" in second


async def test_system_prompt_blank_in_pure_mode(chat_channel):
    apply_config(model={"use_tools": True}, modules={"disabled_prompts": []})
    chat_channel.manager.modules = {"identity": StubModule("identity", prompt="nope")}
    chat_channel.manager.pure_mode = True

    ch = core.chat.Chat(chat_channel)
    await ch.autoload()

    assert await ch.get_system_prompt() == ""


async def test_broken_module_is_quarantined_and_logged(chat_channel):
    apply_config(model={"use_tools": True}, modules={"disabled_prompts": []})
    chat_channel.manager.modules = {
        "memory": StubModule("memory", error=True),
        "identity": StubModule("identity", prompt="fine"),
    }

    ch = core.chat.Chat(chat_channel)
    await ch.autoload()
    prompt = await ch.get_system_prompt()

    assert "fine" in prompt
    assert "memory" in chat_channel.manager.broken_modules
    assert any("on_system_prompt" in msg for _cat, msg in chat_channel.logs)


async def test_disabled_prompts_are_excluded(chat_channel):
    apply_config(
        model={"use_tools": True},
        modules={"disabled_prompts": ["calendar"]},
    )
    chat_channel.manager.modules = {
        "calendar": StubModule("calendar", prompt="hidden"),
        "identity": StubModule("identity", prompt="shown"),
    }

    ch = core.chat.Chat(chat_channel)
    await ch.autoload()
    prompt = await ch.get_system_prompt()

    assert "hidden" not in prompt
    assert "shown" in prompt


async def test_tools_off_keeps_only_nonagentic_prompts(chat_channel):
    apply_config(model={"use_tools": False}, modules={"disabled_prompts": []})
    chat_channel.manager.modules = {
        "calendar": StubModule("calendar", prompt="needs-tools"),
        "time": StubModule("time", prompt="always-on"),
    }

    ch = core.chat.Chat(chat_channel)
    await ch.autoload()
    prompt = await ch.get_system_prompt()

    assert "needs-tools" not in prompt
    assert "always-on" in prompt


# ---------------------------------------------------------------------------
# export / search
# ---------------------------------------------------------------------------

async def test_export_groups_turns_by_role(chat):
    chat.channel.turncollector = core.turns.TurnCollector(chat.channel)
    chat.channel.tc_manager = core.toolcalls.ToolcallManager(chat.channel)

    await chat.messages.add({"role": "user", "content": "hi there"})
    await chat.messages.add({"role": "assistant", "content": "hello!"})
    await chat.messages.add(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "1",
                    "type": "function",
                    "function": {"name": "demo_tool", "arguments": "{}"},
                }
            ],
        }
    )
    await chat.messages.add(
        {"role": "tool", "tool_call_id": "1", "content": "tool output"}
    )
    await chat.messages.add({"role": "assistant", "content": "all done"})

    exported = await chat.export()

    assert "--- user ---" in exported
    assert "hi there" in exported
    assert "hello!" in exported
    assert "all done" in exported
    assert "demo_tool" in exported


async def test_search_matches_titles(chat):
    await chat.set("title", "quantum brewing")
    chat.data.save()
    await chat.new(title="plain chat")
    chat.data.save()

    results = await chat.search("quantum")

    assert len(results) == 1
    assert results[0]["id"] == chat.data[0]["id"]
    assert results[0]["title_match"] is True


async def test_search_matches_message_content(chat):
    target = chat.get("id")
    await chat.messages.add(
        {"role": "user", "content": "the sourdough starter needs feeding"}
    )
    await chat.messages.add({"role": "assistant", "content": "noted"})

    results = await chat.search("sourdough")

    assert results and results[0]["id"] == target
    assert results[0]["message_snippets"]


async def test_search_blank_query_returns_nothing(chat):
    assert await chat.search("   ") == []


# ---------------------------------------------------------------------------
# old-format migration
# ---------------------------------------------------------------------------

def _write_old_format(data_dir, channel_name, chats):
    path = os.path.join(data_dir, f"{channel_name}_chats.json")
    with open(path, "w") as f:
        json.dump(chats, f)
    return path


async def test_migration_moves_messages_and_backs_up(fake_channel, isolate_lumara_paths):
    old_file = _write_old_format(
        str(isolate_lumara_paths),
        "fake",
        [
            {
                "id": "abc12345",
                "title": "Old chat",
                "category": "misc",
                "messages": [{"role": "user", "content": "ancient"}],
                "custom_data": {"x": 1},
                "created": "2020-01-01T00:00:00",
                "updated": "2020-01-02T00:00:00",
            }
        ],
    )
    with open(os.path.join(str(isolate_lumara_paths), "fake_current_chat"), "w") as f:
        f.write("0")

    ch = core.chat.Chat(fake_channel)

    assert not os.path.exists(old_file)  # consumed
    backup = os.path.join(
        str(isolate_lumara_paths), "chat_migration_backups", "fake_chats.json.bak"
    )
    assert os.path.exists(backup)

    assert len(ch.data) == 1
    assert ch.data[0]["title"] == "Old chat"
    assert ch.data[0]["category"] == "misc"
    assert ch.data[0]["metadata"] == {"x": 1}  # custom_data -> metadata

    history = os.path.join(
        str(isolate_lumara_paths), "chats", "fake", "history", "abc12345.json"
    )
    assert json.load(open(history)) == [{"role": "user", "content": "ancient"}]

    with open(os.path.join(str(isolate_lumara_paths), "chats", "fake", "current")) as f:
        assert f.read() == "0"


async def test_migration_of_invalid_old_file_keeps_it_in_place(fake_channel, isolate_lumara_paths):
    old_file = _write_old_format(str(isolate_lumara_paths), "fake", {"not": "a list"})

    ch = core.chat.Chat(fake_channel)  # must not raise

    assert os.path.exists(old_file)
    assert len(ch.data) == 0


async def test_migration_aborts_when_backup_fails(fake_channel, isolate_lumara_paths, monkeypatch):
    _write_old_format(str(isolate_lumara_paths), "fake", [])

    def boom(*args, **kwargs):
        raise OSError("disk on fire")

    monkeypatch.setattr(shutil, "copy2", boom)
    monkeypatch.setattr(sys, "exit", lambda code=0: (_ for _ in ()).throw(SystemExit(code)))

    with pytest.raises(SystemExit):
        core.chat.Chat(fake_channel)

    assert any("FATAL" in msg for _cat, msg in fake_channel.logs)
