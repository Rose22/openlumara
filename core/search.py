# AI DISCLAIMER: A lot of this file was generated with the help of
# my local model, Qwen3.8 Flash Next
#
# I vetted it, edited the parts i understand,
# and tested it as much as i could, but
# complex search algorithms are simply beyond my understanding.
#
# If you're reading this code and find a bug or something that's wrong,
# please submit an issue!

import math
import re
from collections import Counter

# -- AI GENERATED CODE (qwen/Qwen3.8-Flash-Next-Q4) :: 2026-10-02
# splitting rules: words are runs of letters OR runs of digits, nothing else.
# - underscores split: "about_lumara" becomes "about" + "lumara", so searching
#   "lumara" finds filenames and snake_case code (the old \w+ pattern glued
#   underscores into single words).
# - digits split from letters: "128gb" becomes "128" + "gb", so both "128"
#   and "gb" find it (previously only "128..." did, as a prefix of "128gb").
# - decimal points are kept: "3.8" and "0.75" stay ONE word, so version
#   numbers and decimals survive searching. a dot only survives when it sits
#   between digits - "file.txt" still splits into "file" + "txt", and a dot
#   at the end of a sentence never glues onto a word.
# hyphens, apostrophes and punctuation act as separators.
_normalize_rx = re.compile(r"\d+(?:\.\d+)?|[^\W\d_]+", re.UNICODE)

def normalize_words(text):
    """splits raw text into lowercase word tokens, so 'Vitamins!' and 'vitamins' match"""
    return _normalize_rx.findall(str(text).lower())

def make_snippets(text, query, max_snippets=1, radius=50):
    """returns up to max_snippets excerpts of text surrounding matches of the query"""
    text = str(text)
    low = text.lower()
    candidates = [query.strip().lower()] + normalize_words(query)
    term = next((c for c in candidates if c and c in low), "")
    if not term:
        return []

    snippets = []
    start = 0
    while len(snippets) < max_snippets:
        pos = low.find(term, start)
        if pos == -1:
            break
        end = min(len(text), pos + len(term) + radius)
        chunk = text[max(0, pos - radius):end].replace("\n", " ").strip()
        snippets.append(("..." if pos > radius else "") + chunk + ("..." if end < len(text) else ""))
        start = end
    return snippets

def _extract(entry, field_weights):
    """normalizes any entry (string, dict, or whatever) into a {field: text} dict"""
    if not isinstance(entry, dict):
        return {"text": str(entry)}

    fields = {}
    for key, value in entry.items():
        if field_weights is not None and key not in field_weights:
            continue
        if isinstance(value, str):
            fields[key] = value
        elif isinstance(value, list):
            parts = [str(v) for v in value if isinstance(v, (str, int, float))]
            if parts:
                fields[key] = " ".join(parts)
    return fields

# -- AI GENERATED CODE (qwen/Qwen3.8-Flash-Next-Q4) :: 2026-10-02
# word-tally cache: counting the words in a big chat is the slowest part of
# searching, but the same text almost never changes between searches. so we
# remember the tally for every text we have ever counted and reuse it.
# identical text always produces identical counts, so this can never go stale.
# memory is kept in check by budgeting the TOTAL number of cached unique
# words (that's what the counters actually grow with), not the number of
# cached texts - one giant chat costs far more than a hundred small notes.
# when the budget is spent we simply empty the cache and start over.
_word_count_cache = {}
_word_count_cache_words = 0  # running total of unique words stored in the cache
_WORD_COUNT_CACHE_BUDGET = 300_000  # ~50 MB worst case

def _count_words(text):
    """returns a {word: count} tally for the text, reusing a cached one if possible"""
    global _word_count_cache_words
    counts = _word_count_cache.get(text)
    if counts is None:
        counts = Counter(normalize_words(text))
        if _word_count_cache_words + len(counts) > _WORD_COUNT_CACHE_BUDGET:
            _word_count_cache.clear()
            _word_count_cache_words = 0
        _word_count_cache[text] = counts
        _word_count_cache_words += len(counts)
    return counts

def bm25_rank(entries, query, field_weights, top_n):
    """
    scores each entry against the query using the BM25 algorithm, returning
    (entry_index, score) tuples sorted from best match to worst.

    BM25 in plain english - three simple ideas:
    1. repetition: an entry that mentions your search word a lot is probably
       relevant... but the 10th mention shouldn't count as much as the 1st.
    2. rarity: a word that appears in only a few entries ("zebra") tells you
       much more than a word that appears everywhere ("the").
    3. length: long entries naturally contain more words, so we give them a
       small handicap so they don't win just by being wordy.

    one deliberate deviation from textbook BM25, so future readers know:
    - matching is by word PREFIX ("vitamin" finds "vitamins"), a cheap
      stand-in for stemming.
    """
    # tuning knobs (these are the classic BM25 defaults, they work well as-is)
    repeat_saturation = 1.5   # how fast extra repeats of a word stop mattering
    length_penalty = 0.75     # how strongly long entries are held back

    # split query into words, removing duplicates but keeping the original order
    query_terms = list(dict.fromkeys(normalize_words(query)))
    if not query_terms:
        return []

    # -- step 1: sort entries into one group per field, remembering each
    # entry's original position so scores always land on the correct entry.
    # fields like "title" and "content" are scored separately, then combined.
    # the actual word-counting happens in step 2, through the cache.
    entries_by_field = {}
    for entry_index, entry in enumerate(entries):
        for field_name, text in _extract(entry, field_weights).items():
            entries_by_field.setdefault(field_name, []).append((entry_index, text))

    # -- step 2: score every entry, field by field
    total_scores = {}  # {entry_index: final score}
    for field_name, field_texts in entries_by_field.items():
        # look up (or compute) the word tally for each entry in this field
        tallies = []
        lengths = []
        for _, text in field_texts:
            counts = _count_words(text)
            tallies.append(counts)
            lengths.append(sum(counts.values()))

        avg_length = sum(lengths) / len(lengths)
        if not avg_length:
            continue  # every entry is empty in this field, nothing to score

        total_entries = len(field_texts)

        # -- one pass over all entries does TWO jobs at once:
        # 1. find out which query words each entry contains, and how often.
        #    a query word matches when a text word STARTS with it, so
        #    "vitamin" still finds "vitamins", but "of" no longer finds "roof".
        # 2. tally the rarity stats: how many entries contain each query word
        #    at least once. an entry counts only once per word, no matter how
        #    many matching variants it contains.
        # entries that match nothing are dropped immediately - they can never
        # earn points anyway, so we skip all their scoring math.
        entries_with_term = dict.fromkeys(query_terms, 0)
        matched = []  # entries that contain at least one query word
        for position, (entry_index, _) in enumerate(field_texts):
            hits = {}
            for word, count in tallies[position].items():
                for term in query_terms:
                    if word.startswith(term):
                        hits[term] = hits.get(term, 0) + count
            if hits:
                matched.append((position, entry_index, hits))
                for term in hits:
                    entries_with_term[term] += 1

        field_weight = (field_weights or {}).get(field_name, 1.0)

        # -- score only the entries that actually matched something
        for position, entry_index, hits in matched:
            entry_score = 0.0

            for term, term_hits in hits.items():
                # rarity bonus: rare terms score higher than common ones.
                # this is the "lucene-style" formula, which stays >= 0 as long
                # as entries_with_term never exceeds total_entries (it can't now).
                num_with_term = entries_with_term[term]
                rarity_bonus = math.log(1 + (total_entries - num_with_term + 0.5) / (num_with_term + 0.5))

                # length handicap: an entry of average size gets 1.0; longer
                # entries get > 1.0 (making it harder to score), shorter < 1.0.
                length_handicap = 1 - length_penalty + length_penalty * lengths[position] / avg_length

                # the diminishing-returns part: term_hits lifts the score, but
                # the denominator makes each extra hit count a bit less.
                term_score = rarity_bonus * term_hits * (repeat_saturation + 1) / (
                    term_hits + repeat_saturation * length_handicap
                )
                entry_score += term_score

            total_scores[entry_index] = total_scores.get(entry_index, 0.0) + entry_score * field_weight

    # -- step 3: sort by score (best first) and keep only the top_n results
    return sorted(total_scores.items(), key=lambda item: item[1], reverse=True)[:top_n]

async def search(entries, query, id_field="id", field_weights=None, top_n=10):
    """
    search that uses BM25 to rank entries
    returns a ranked list of {"id": ..., "score": ..., "entry": ...} dicts.
    """
    if not entries or not query or not str(query).strip():
        return []

    entries = list(entries)
    results = []
    for index, score in bm25_rank(entries, query, field_weights, top_n):
        entry = entries[index]
        entry_id = entry.get(id_field) if isinstance(entry, dict) else None
        # -- AI GENERATED CODE (qwen/Qwen3.8-Flash-Next-Q4) :: 2026-10-02
        # use an explicit None check so a legitimate id of 0 or "" isn't silently replaced by the index.
        results.append({"id": entry_id if entry_id is not None else index, "score": score, "entry": entry})
    return results
