# -- AI GENERATED CODE (Claude) :: (2026-10-25) harness:openlumara status:unreviewed
"""
core/search.py - tokenization, snippets and BM25 ranking.

intent (from the file's own extensive comments): words are letter-runs or
digit-runs (underscores split, "128gb" splits, decimals like "3.8" stay one
token); BM25 with prefix matching as cheap stemming, a x1.5 verbatim-phrase
boost, diminishing returns on repetition, rarity weighting and a length
handicap.
"""

import pytest

import core


# ---- normalize_words ----------------------------------------------------

def test_normalize_folds_case_and_punctuation():
    assert core.search.normalize_words("Vitamins!") == ["vitamins"]


def test_normalize_splits_underscores():
    # intent: snake_case must be findable by its parts
    assert core.search.normalize_words("about_lumara") == ["about", "lumara"]


def test_normalize_splits_digits_from_letters():
    assert core.search.normalize_words("128gb") == ["128", "gb"]


def test_normalize_keeps_decimals_together():
    assert core.search.normalize_words("qwen 3.8 release") == ["qwen", "3.8", "release"]


def test_normalize_splits_dotted_words_and_sentence_dots():
    assert core.search.normalize_words("file.txt") == ["file", "txt"]
    assert core.search.normalize_words("end. Next") == ["end", "next"]


# ---- make_snippets --------------------------------------------------------

def test_snippet_surrounds_the_match():
    text = "prefix " + "filler " * 30 + "needle in the haystack" + " tail" * 30
    snippets = core.search.make_snippets(text, "needle", max_snippets=1, radius=20)
    assert len(snippets) == 1
    assert "needle" in snippets[0]
    assert snippets[0].startswith("...")  # truncated on the left
    assert snippets[0].endswith("...")    # truncated on the right


def test_snippet_no_ellipsis_when_not_truncated():
    assert core.search.make_snippets("hello world", "world", radius=50) == ["hello world"]


def test_snippet_no_match_returns_empty():
    assert core.search.make_snippets("nothing here", "zebra") == []


def test_snippet_prefers_whole_query_over_single_words():
    text = "the open lumara project is open"
    snippets = core.search.make_snippets(text, "open lumara", radius=10)
    assert snippets and "open lumara" in snippets[0]


# ---- bm25_rank -------------------------------------------------------------

def test_bm25_empty_query_returns_nothing():
    assert core.search.bm25_rank(["anything"], "   ", None, 10) == []


def test_bm25_no_match_returns_nothing():
    assert core.search.bm25_rank(["alpha beta"], "zebra", None, 10) == []


def test_bm25_matches_by_word_prefix():
    # "vitamin" must find "vitamins" (cheap stemming)
    hits = core.search.bm25_rank(["vitamins are good"], "vitamin", None, 10)
    assert [idx for idx, _ in hits] == [0]


def test_bm25_prefix_does_not_match_mid_word():
    # "of" must NOT find "roof" - prefix matching is word-start only
    assert core.search.bm25_rank(["the roof is hot"], "of", None, 10) == []


def test_bm25_rare_term_outranks_common_term():
    entries = ["the cat sat", "the dog ran"]
    cat_score = core.search.bm25_rank(entries, "cat", None, 10)[0][1]
    the_score = core.search.bm25_rank(entries, "the", None, 10)[0][1]
    assert cat_score > the_score


def test_bm25_repetition_saturates():
    entries = ["apple " * 10 + "filler", "apple filler"]
    ranked = dict(core.search.bm25_rank(entries, "apple", None, 10))
    assert ranked[0] > ranked[1]
    # ... but with diminishing returns: 10x the mentions is NOT 10x the score
    assert ranked[0] < 10 * ranked[1]


def test_bm25_verbatim_phrase_boosts():
    # e1 has more raw term hits, but e0 contains the query verbatim and the
    # x1.5 phrase boost is meant to flip the order (documented deviation)
    entries = ["alpha beta", "beta extra extra alpha extra"]
    ranked = core.search.bm25_rank(entries, "alpha beta", None, 10)
    assert ranked[0][0] == 0


def test_bm25_field_weights_scale_scores():
    entry = {"title": "apple pie", "body": "yummy"}
    single = core.search.bm25_rank([entry], "apple", {"title": 1.0, "body": 1.0}, 10)[0][1]
    double = core.search.bm25_rank([entry], "apple", {"title": 2.0, "body": 1.0}, 10)[0][1]
    assert double == pytest.approx(2.0 * single)


def test_bm25_respects_top_n():
    entries = ["apple one", "apple two", "apple three", "apple four"]
    assert len(core.search.bm25_rank(entries, "apple", None, 2)) == 2


def test_bm25_non_string_values_are_ignored_or_joined():
    # dict values are skipped, lists of primitives are joined into text
    entries = [
        {"id": 1, "tags": ["red wagon"], "meta": {"nested": "x"}},
        {"id": 2, "tags": ["blue car"], "meta": {"nested": "wagon"}},
    ]
    ranked = core.search.bm25_rank(entries, "wagon", None, 10)
    # only entry 0 matches: "wagon" inside its tags; the nested dict value of
    # entry 1 must NOT be searchable
    assert [idx for idx, _ in ranked] == [0]


def test_bm25_word_count_cache_is_consistent():
    # the module caches word tallies; a cache hit must equal a fresh count
    entries = ["consistency check entry", "another entry here"]
    first = core.search.bm25_rank(entries, "entry", None, 10)
    second = core.search.bm25_rank(entries, "entry", None, 10)
    assert first == second


# ---- search() wrapper ---------------------------------------------------------

async def test_search_requires_entries_and_query():
    assert await core.search.search([], "x") == []
    assert await core.search.search(["x"], "   ") == []


async def test_search_returns_id_score_entry_dicts():
    entries = [{"id": "m1", "content": "buy milk"}, {"id": "m2", "content": "sell boat"}]
    results = await core.search.search(entries, "milk", id_field="id")

    assert len(results) == 1
    assert results[0]["id"] == "m1"
    assert results[0]["score"] > 0
    assert results[0]["entry"] is entries[0]


async def test_search_falls_back_to_index_when_id_missing():
    results = await core.search.search(["just a string", "another string"], "string")
    assert sorted(r["id"] for r in results) == [0, 1]
