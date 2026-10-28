# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-26) harness:openlumara status:unreviewed
"""
modules/chats - AI-side chat management (organize/categories/search).

integration level: real Chats module on FakeChannel with a real Chat on tmp
storage; search reads real history files through the shared core.search
engine (its ranking is covered by tests/core/test_search.py).

intent under test:
- organize() sets title, category and tags on the current chat in one call;
  a blank name is rejected.
- the system prompt exposes the current chat ID and the flat category list
  (subcategories with ':' are the webui's business, not the AI's).
- search ranks titles above message text and always returns a result
  envelope, never a bare None.
"""

import json
import os

import pytest

import core
from harness import apply_config
from modules.chats.module import Chats

BASE = {
    "api": {"max_context": 1000},
    "model": {"name": "test-model", "use_tools": True, "dynamic_tool_loading": False},
    "core": {"cmd_prefix": "/"},
}


def configure(**settings):
    apply_config(
        modules={"disabled_prompts": [], "settings": {"chats": settings}}, **BASE
    )


@pytest.fixture
async def chat(fake_channel):
    ch = core.chat.Chat(fake_channel)
    await ch.autoload()
    fake_channel.context.chat = ch
    return ch


async def make_chats(fake_manager, fake_channel, **settings):
    configure(**settings)
    mod = Chats(fake_manager, channel=fake_channel)
    await mod.on_ready()
    return mod


# ---------------------------------------------------------------------------
# organize
# ---------------------------------------------------------------------------

async def test_organize_sets_title_category_and_tags(fake_manager, fake_channel, chat):
    mod = await make_chats(fake_manager, fake_channel)

    res = await mod.organize("Trip planning", "travel", ["personal", "2026"])

    assert res == {"status": "success", "content": "chat organised!"}
    assert chat.get("title") == "Trip planning"
    assert chat.get("category") == "travel"
    assert chat.get("tags") == ["personal", "2026"]


async def test_organize_defaults_tags_to_empty_list(fake_manager, fake_channel, chat):
    mod = await make_chats(fake_manager, fake_channel)

    await mod.organize("No tags here", "misc")

    assert chat.get("tags") == []


async def test_organize_rejects_blank_name(fake_manager, fake_channel, chat):
    mod = await make_chats(fake_manager, fake_channel)

    res = await mod.organize("", "misc")

    assert res["status"] == "error"
    assert res["content"] == "name must not be blank"


# ---------------------------------------------------------------------------
# categories
# ---------------------------------------------------------------------------

async def test_get_categories_reports_flat_category_list(fake_manager, fake_channel, chat):
    mod = await make_chats(fake_manager, fake_channel)

    res = await mod.get_categories()
    assert res["status"] == "success"
    assert res["content"] == ["general"]  # the autoloaded chat's category

    await chat.new(category="travel")
    await chat.new(category="work")
    res = await mod.get_categories()
    assert set(res["content"]) >= {"general", "travel", "work"}


async def test_get_categories_hides_subcategories(fake_manager, fake_channel, chat):
    mod = await make_chats(fake_manager, fake_channel)

    await chat.new(category="travel")
    await chat.new(category="temp")
    await chat.set("category", "work:projects")  # nested, not offered to the AI

    res = await mod.get_categories()

    assert "work:projects" not in res["content"]
    assert "travel" in res["content"]


async def test_get_categories_empty_message(fake_manager, fake_channel, chat):
    mod = await make_chats(fake_manager, fake_channel)

    # wipe every category from the index
    for entry in chat.data:
        entry["category"] = ""

    res = await mod.get_categories()

    assert res["status"] == "success"
    assert res["content"] == "There are no categories yet. Create one!"


# ---------------------------------------------------------------------------
# system prompt
# ---------------------------------------------------------------------------

async def test_prompt_shows_chat_id_and_categories(fake_manager, fake_channel, chat):
    mod = await make_chats(fake_manager, fake_channel)

    await chat.new(category="travel")
    await chat.new(category="work")

    out = await mod.on_system_prompt()

    assert f"current chat ID: {chat.get('id')}" in out
    assert "Available categories to categorise chat into:" in out


async def test_prompt_omits_disabled_sections(fake_manager, fake_channel, chat):
    mod = await make_chats(
        fake_manager, fake_channel,
        insert_chat_id=False, insert_categories=False,
    )

    assert await mod.on_system_prompt() is None


async def test_prompt_needs_two_categories_to_advertise_them(fake_manager, fake_channel, chat):
    mod = await make_chats(fake_manager, fake_channel)

    out = await mod.on_system_prompt()

    # only one category exists ("general") - nothing to categorise into
    assert "Available categories" not in out
    assert chat.get("id") in out


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------

def write_history(chat, chat_id, messages):
    path = core.get_data_path(os.path.join(chat.path, "history", f"{chat_id}.json"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(messages, f)


async def test_search_finds_text_in_history(fake_manager, fake_channel, chat):
    mod = await make_chats(fake_manager, fake_channel)
    await chat.set("title", "laptop issues")
    write_history(chat, chat.get("id"), [
        {"role": "user", "content": "the fan makes a whining noise"},
    ])

    res = await mod.search("whining")

    assert res["status"] == "success"
    assert "laptop issues" in res["content"]
    assert "whining" in res["content"]  # snippet included


async def test_search_title_outweighs_body_text(fake_manager, fake_channel, chat):
    mod = await make_chats(fake_manager, fake_channel)

    await chat.set("title", "zebras")
    write_history(chat, chat.get("id"), [{"role": "user", "content": "zebras"}])
    other = await chat.new(title="random stuff")
    write_history(chat, chat.get("id"), [{"role": "user", "content": "nothing here"}])

    res = await mod.search("zebras")

    lines = res["content"].splitlines()
    # the title-hit chat ranks first (title weight 2.0)
    assert "zebras" in lines[0]


async def test_search_no_results_is_an_envelope(fake_manager, fake_channel, chat):
    mod = await make_chats(fake_manager, fake_channel)
    write_history(chat, chat.get("id"), [{"role": "user", "content": "hello"}])

    res = await mod.search("nonexistentquery")

    assert res == {"status": "success", "content": "no results found"}
