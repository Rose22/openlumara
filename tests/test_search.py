# AI Written: Claude Opus 5.5, reviewed by Claude Fable 5.2
import core

NOTES = [
    {"id": "groceries", "title": "shopping list", "content": "milk, eggs and vitamins"},
    {"id": "health", "title": "vitamin schedule", "content": "take vitamin d every morning"},
    {"id": "roof", "title": "house", "content": "fix the roof before winter"},
]


async def test_best_match_first():
    results = await core.search.search(NOTES, "vitamin")
    assert [r["id"] for r in results] == ["health", "groceries"]
    assert results[0]["entry"] is NOTES[1]
    assert results[0]["score"] > results[1]["score"] > 0


async def test_prefix_matching_does_not_match_mid_word():
    # "of" must not find "roof"
    assert await core.search.search(NOTES, "of") == []


async def test_field_weights_change_ranking():
    entries = [
        {"id": "in_title", "title": "winter coat", "content": "warm"},
        {"id": "in_content", "title": "coat", "content": "for winter"},
    ]
    weights = {"title": 5.0, "content": 1.0}
    assert (await core.search.search(entries, "winter", field_weights=weights))[0]["id"] == "in_title"
    weights = {"title": 1.0, "content": 5.0}
    assert (await core.search.search(entries, "winter", field_weights=weights))[0]["id"] == "in_content"
    # fields left out of the weights are not searched
    assert await core.search.search(entries, "warm", field_weights={"title": 1.0}) == []


async def test_empty_results():
    assert await core.search.search(NOTES, "zebra") == []
    assert await core.search.search(NOTES, "   ") == []
    assert await core.search.search([], "milk") == []


async def test_plain_strings_use_index_as_id():
    results = await core.search.search(["apples", "pears and apples", "pears"], "pears", top_n=1)
    assert len(results) == 1
    assert results[0]["id"] in (1, 2)
