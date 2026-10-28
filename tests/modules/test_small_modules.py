# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
small utility modules: replacer, time, token_threshold, lists, notes.

integration level: real module classes on FakeManager (+ real Context where
the module reads token usage), real tmp-dir storage (conftest isolation).

intent under test:
- replacer: on_user_message returns the transformed message with whole
  words substituted, word boundaries respected.
- time: frozen-clock snapshots for both injection methods, timezone
  suffix on/off.
- token_threshold: warning injected at/over the threshold, silence below,
  silence without a channel.
- lists: CRUD + item ops with starts-with item matching; pinned lists are
  rendered into the system prompt.
- notes: markdown-backed notebook CRUD, category pruning, search.
"""

import datetime
import types

import pytest

import core
import modules.time.module as time_mod
from harness import apply_config
from modules.lists.module import Lists
from modules.notes.module import Notes
from modules.replacer.module import Replacer
from modules.time.module import Time
from modules.token_threshold.module import TokenThreshold

BASE = {
    "api": {"max_context": 1000},
    "model": {"name": "test-model", "use_tools": False, "dynamic_tool_loading": False},
    "core": {"cmd_prefix": "/"},
}


def configure(**module_settings):
    apply_config(modules={"disabled_prompts": [], "settings": module_settings}, **BASE)


# ---------------------------------------------------------------------------
# replacer
# ---------------------------------------------------------------------------

def make_replacer(fake_manager, **settings):
    configure(replacer=settings)
    return Replacer(fake_manager)


async def test_replacer_substitutes_whole_words(fake_manager):
    mod = make_replacer(fake_manager, replacements={"foo": "bar", "secret": "[redacted]"})

    out = await mod.on_user_message("please foo loudly, the secret stays secret.")

    assert out == "please bar loudly, the [redacted] stays [redacted]."


async def test_replacer_respects_word_boundaries(fake_manager):
    mod = make_replacer(fake_manager, replacements={"foo": "bar"})

    assert await mod.on_user_message("food and foobar stay") == "food and foobar stay"


async def test_replacer_without_replacements_is_identity(fake_manager):
    mod = make_replacer(fake_manager)  # schema default {}
    assert await mod.on_user_message("leave me be") == "leave me be"


# ---------------------------------------------------------------------------
# time
# ---------------------------------------------------------------------------

class FrozenDatetime(datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime.datetime(2026, 1, 1, 12, 0, tzinfo=tz or datetime.timezone.utc)


@pytest.fixture
def frozen_clock(monkeypatch):
    monkeypatch.setattr(
        time_mod, "datetime", types.SimpleNamespace(datetime=FrozenDatetime)
    )


def make_time(fake_manager, **overrides):
    settings = {
        "method": "message injection",
        "add_timezone": True,
        "timezone": "UTC",
        "date_format": "%Y-%m-%d %H:%M",
    }
    settings.update(overrides)
    configure(time=settings)
    return Time(fake_manager)


async def test_time_message_injection_snapshot(fake_manager, frozen_clock):
    mod = make_time(fake_manager)

    assert await mod.on_message_inject("hello") == "sent on 2026-01-01 12:00 UTC"
    # the other method stays silent
    assert await mod.on_end_prompt() is None


async def test_time_end_prompt_method_snapshot(fake_manager, frozen_clock):
    mod = make_time(fake_manager, method="end prompt")

    assert await mod.on_message_inject("hello") is None
    assert await mod.on_end_prompt() == "Current time/date is 2026-01-01 12:00 UTC"


async def test_time_without_timezone_suffix(fake_manager, frozen_clock):
    mod = make_time(fake_manager, add_timezone=False)
    assert await mod.on_message_inject("hello") == "sent on 2026-01-01 12:00"


# ---------------------------------------------------------------------------
# token_threshold
# ---------------------------------------------------------------------------

@pytest.fixture
def tt(fake_manager):
    configure(token_threshold={"warning_threshold": 0.8})
    return TokenThreshold(fake_manager)


async def _wire_channel(fake_channel, token_usage):
    ctx = core.context.Context(fake_channel)
    fake_channel.context = ctx
    await ctx.chat.autoload()
    ctx.chat.data[ctx.chat.current]["token_usage"] = token_usage
    return ctx


async def test_token_warning_at_threshold(tt, fake_channel):
    await _wire_channel(fake_channel, 850)
    tt.channel = fake_channel

    out = await tt.on_end_prompt()

    assert out is not None and "85.0%" in out and "15.0%" in out


async def test_token_silence_below_threshold(tt, fake_channel):
    await _wire_channel(fake_channel, 799)
    tt.channel = fake_channel
    assert await tt.on_end_prompt() is None


async def test_token_silence_without_channel(tt):
    assert await tt.on_end_prompt() is None


# ---------------------------------------------------------------------------
# lists
# ---------------------------------------------------------------------------

@pytest.fixture
async def lists_mod(fake_manager):
    configure(lists={})
    mod = Lists(fake_manager)
    await mod.on_ready()
    return mod


async def test_lists_create_get_delete(lists_mod):
    assert (await lists_mod.create("errands", "shopping", items=["milk"]))["status"] == "success"
    assert (await lists_mod.create("errands", "shopping"))["status"] == "error"  # duplicate

    got = await lists_mod.get("errands", "shopping")
    assert got["content"] == ["milk"]

    assert (await lists_mod.delete("errands", "shopping"))["status"] == "success"
    # category pruned when it becomes empty
    assert "errands" not in lists_mod.data


async def test_lists_add_item_creates_list(lists_mod):
    res = await lists_mod.add_item("fun", "ideas", "paint the fence")
    assert res["status"] == "success"
    assert lists_mod.data["fun"]["ideas"]["items"] == ["paint the fence"]


async def test_lists_item_matching_starts_with(lists_mod):
    await lists_mod.create("errands", "todo", items=["Buy milk", "Book dentist"])

    # case-insensitive prefix match
    res = await lists_mod.edit_item("errands", "todo", "book", "Book dentist friday")
    assert res["status"] == "success"
    assert lists_mod.data["errands"]["todo"]["items"][1] == "Book dentist friday"

    res = await lists_mod.delete_item("errands", "todo", "BUY")
    assert res["status"] == "success"
    assert lists_mod.data["errands"]["todo"]["items"] == ["Book dentist friday"]

    assert (await lists_mod.delete_item("errands", "todo", "ghost"))["status"] == "error"


@pytest.mark.xfail(
    strict=True,
    reason="suspected bug (same envelope family as finding 13): edit_item "
    "returns the not-found message in a SUCCESS envelope for a missing list, "
    "while the very same method uses success=False for a missing item",
)
async def test_lists_edit_unknown_list_is_an_error_envelope(lists_mod):
    res = await lists_mod.edit_item("errands", "ghost", "x", "y")
    assert res["status"] == "error"


async def test_lists_pin_unpin(lists_mod):
    await lists_mod.create("errands", "shopping")
    await lists_mod.pin("errands", "shopping")
    assert lists_mod.data["errands"]["shopping"]["pinned"] is True
    await lists_mod.unpin("errands", "shopping")
    assert lists_mod.data["errands"]["shopping"]["pinned"] is False


async def test_lists_system_prompt_renders_pinned(lists_mod):
    await lists_mod.create("errands", "shopping", items=["milk", "bread"], pinned=True)
    await lists_mod.create("errands", "private")  # empty + unpinned -> not shown

    prompt = await lists_mod.on_system_prompt()

    assert "## errands" in prompt and "### shopping" in prompt
    assert "- milk" in prompt and "- bread" in prompt

    configure(lists={"insert_system_prompt": False})
    assert await lists_mod.on_system_prompt() is None


async def test_lists_search_matches_items(lists_mod):
    await lists_mod.create("kitchen", "pantry", items=["flour", "sugar"])
    await lists_mod.create("kitchen", "tools", items=["whisk"])

    res = await lists_mod.search("sugar")

    assert res["status"] == "success"
    assert "sugar" in res["content"] and "pantry" in res["content"]

    miss = await lists_mod.search("zzzqqq")
    assert miss["status"] == "success" and "no lists" in miss["content"]


# ---------------------------------------------------------------------------
# notes
# ---------------------------------------------------------------------------

@pytest.fixture
async def notes_mod(fake_manager):
    configure(notes={})
    mod = Notes(fake_manager)
    await mod.on_ready()
    return mod


async def test_notes_create_read_roundtrip(notes_mod):
    res = await notes_mod.create(name="recipe", category="cooking", content="mix everything")
    assert res["status"] == "success"

    out = await notes_mod.read(category="cooking", name="recipe")
    assert out["content"] == "mix everything"

    # duplicate create is refused
    assert (await notes_mod.create(name="recipe", category="cooking", content="x"))["status"] == "error"


async def test_notes_unknown_category_and_note(notes_mod):
    assert "category doesn't exist" in (await notes_mod.read(category="ghost", name="x"))["content"]
    await notes_mod.create(name="a", category="c", content="x")
    assert "does not exist" in (await notes_mod.read(category="c", name="ghost"))["content"]


async def test_notes_edit(notes_mod):
    await notes_mod.create(name="n", category="c", content="v1")
    assert (await notes_mod.edit(category="c", name="n", content="v2"))["status"] == "success"
    assert notes_mod.data["c"]["n"] == "v2"


async def test_notes_delete_prunes_empty_category(notes_mod):
    await notes_mod.create(name="only", category="c", content="x")
    assert (await notes_mod.delete(category="c", name="only"))["status"] == "success"
    assert "c" not in notes_mod.data


async def test_notes_categories_and_listing(notes_mod):
    await notes_mod.create(name="n1", category="work", content="a")
    await notes_mod.create(name="n2", category="work", content="b")

    cats = await notes_mod.get_categories()
    assert cats["content"] == ["work"]

    names = await notes_mod.list(category="work")
    assert sorted(names["content"]) == ["n1", "n2"]

    assert (await notes_mod.list(category="ghost"))["status"] == "error"


async def test_notes_search(notes_mod):
    await notes_mod.create(name="dna", category="bio", content="the mitochondria is the powerhouse")
    await notes_mod.create(name="cars", category="auto", content="rotate the tires")

    res = await notes_mod.search("mitochondria")

    assert res["status"] == "success"
    assert "bio/dna" in res["content"]

    miss = await notes_mod.search("zzzqqq")
    assert "no notes found" in miss["content"]
