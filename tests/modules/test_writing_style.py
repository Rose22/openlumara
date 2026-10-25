# -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-26) harness:openlumara status:unreviewed
"""
modules/writing_style - constraint prompt assembly from settings.

integration level: pure config -> prompt snapshots (TEST_PLAN's deferred
Tier-4 item). The module is a giant match over settings values; these tests
pin the assembly rules rather than every option string:

- all-default settings emit no prompt at all (None), so the header never
  appears in a default install;
- style and flair share one constraint line when both are non-default
  (space-joined), each on its own line otherwise;
- custom flair/mood/desire fall back to fixed joke-placeholders when the
  custom field was left empty;
- the forbid_* switches: markdown suppression wins over the tables/headers
  switches (they are inside its else branch);
- output format is one "- " bullet per constraint.
"""

import pytest

import core
from harness import apply_config
from modules.writing_style.module import WritingStyle

BASE = {
    "api": {"max_context": 1000},
    "model": {"name": "test-model", "use_tools": True, "dynamic_tool_loading": False},
    "core": {"cmd_prefix": "/"},
}


def configure(**settings):
    apply_config(
        modules={"disabled_prompts": [], "settings": {"writing_style": settings}},
        **BASE,
    )


async def prompt(**settings):
    configure(**settings)
    return await WritingStyle(None).on_system_prompt()


# ---------------------------------------------------------------------------
# defaults
# ---------------------------------------------------------------------------

async def test_all_defaults_emit_no_prompt(fake_manager):
    # every setting on "default" -> the module contributes nothing at all
    assert await prompt() is None


# ---------------------------------------------------------------------------
# style + flair joining
# ---------------------------------------------------------------------------

async def test_style_alone(fake_manager):
    out = await prompt(writing_style="chat")

    # quirk pinned, not asserted to the byte: writing_flair defaults to
    # None (not "default"), so the joiner fires anyway and leaves a trailing
    # space on the style line. Assert the content, not the whitespace wart.
    assert out.rstrip() == "- Style: Messaging app (Telegram/Discord)."


async def test_flair_alone(fake_manager):
    out = await prompt(writing_flair="robotic")

    assert out == "- Speak in a robotic way."


async def test_style_and_flair_share_one_line(fake_manager):
    out = await prompt(writing_style="chat", writing_flair="robotic")

    # style and flair are one voice description, not two bullets
    assert out == "- Style: Messaging app (Telegram/Discord). Speak in a robotic way."


async def test_flair_alone_has_no_stray_joiner(fake_manager):
    # style stays default -> no joiner space when flair is the only voice
    assert await prompt(writing_flair="pirate") == "- Talk like a pirate!"


async def test_code_output_styles(fake_manager):
    assert (await prompt(writing_style="json")).rstrip() == "- Output ONLY json"
    assert (await prompt(writing_style="python")).rstrip() == "- Output ONLY python code"
    assert (await prompt(writing_style="javascript")).rstrip() == "- Output ONLY javascript code"


async def test_custom_flair_fallbacks(fake_manager):
    # custom selected but the custom field left empty -> the placeholder
    assert await prompt(writing_flair="custom") == "- Not sure"
    assert await prompt(writing_flair="custom", custom_writing_flair="like a pirate") \
        == "- like a pirate"


# ---------------------------------------------------------------------------
# mood / desire / custom fallbacks
# ---------------------------------------------------------------------------

async def test_mood_and_desire_lines(fake_manager):
    out = await prompt(mood="angry", desire="helpful")

    assert out == "- Mood: Angry at user\n- Desire: Help the user"


async def test_comedic_mood_implies_a_desire(fake_manager):
    out = await prompt(mood="comedic")

    assert out == "- Mood: Comedic\n- Desire: Tell jokes"


async def test_custom_mood_placeholder_when_unset(fake_manager):
    out = await prompt(mood="custom")

    assert out == "- Mood: Annoyed at user for not specifying a custom mood"


async def test_custom_desire_lines(fake_manager):
    assert await prompt(desire="custom") == "- Desire: Not sure"
    assert await prompt(desire="custom", custom_desire="write tests") \
        == "- Desire: write tests"


# ---------------------------------------------------------------------------
# length / vocab / emoji / case / lists
# ---------------------------------------------------------------------------

async def test_orthogonal_dimensions_get_their_own_lines(fake_manager):
    out = await prompt(
        writing_length="one sentence",
        vocabulary_level="eli5",
        emoji_style="none",
        capitalization_style="lowercase",
        list_style="none",
    )

    # assembly order is fixed: case, length, vocabulary, emoji, lists
    assert out.splitlines() == [
        "- Case: Lowercase only",
        "- Length: Only one sentence",
        "- Vocabulary: Use simple explain-like-im-five language.",
        "- Emoji: Forbidden.",
        "- No lists",
    ]


# ---------------------------------------------------------------------------
# forbid switches
# ---------------------------------------------------------------------------

async def test_forbid_markdown_supersedes_tables_and_headers(fake_manager):
    out = await prompt(
        forbid_markdown=True, forbid_tables=True, forbid_headers=True
    )

    lines = out.splitlines()
    assert "- Don't use markdown" in lines
    # tables/headers switches live in markdown's else-branch: dead when
    # markdown is already forbidden
    assert "- No tables" not in lines
    assert "- No headers" not in lines


async def test_forbid_tables_and_headers_without_markdown(fake_manager):
    out = await prompt(forbid_tables=True, forbid_headers=True)

    assert "- No tables" in out.splitlines()
    assert "- No headers" in out.splitlines()


async def test_independent_forbid_switches(fake_manager):
    out = await prompt(
        forbid_em_dash=True,
        forbid_negative_parallelism=True,
        forbid_relentless_praise=True,
    )

    lines = out.splitlines()
    assert "- Don't use `—`, use `-` instead" in lines
    assert "- No negative parallelism (e.g., 'Not just X, but Y')." in lines
    assert "- No excessive user praise (e.g., 'You're absolutely right!')." in lines


async def test_full_combination_is_bulleted(fake_manager):
    out = await prompt(
        writing_style="formal",
        writing_flair="pirate",
        writing_length="essay",
        mood="happy",
    )

    assert out == (
        "- Style: Very formal/Business. Talk like a pirate!\n"
        "- You MUST write your response with the length of a scientific essay\n"
        "- Mood: Happy"
    )
