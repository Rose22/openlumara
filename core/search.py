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

_normalize_rx = re.compile(r"\w+", re.UNICODE)

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
    """
    # tuning knobs (these are the classic BM25 defaults, they work well as-is)
    repeat_saturation = 1.5   # how fast extra repeats of a word stop mattering
    length_penalty = 0.75     # how strongly long entries are held back

    full_query = str(query).strip().lower()
    # split query into words, removing duplicates but keeping the original order
    query_terms = list(dict.fromkeys(normalize_words(query)))
    if not query_terms:
        return []

    # -- step 1: count the words in every entry.
    # for each entry we build a tally of which words appear and how often,
    # like {"cat": 2, "dog": 1}. we also keep the entry's original position
    # in the list, so when scores are handed out later they always land on
    # the correct entry.
    # the entries are grouped by field name, because fields like "title" and
    # "content" are scored separately and then combined.
    entries_by_field = {}
    for entry_index, entry in enumerate(entries):
        for field_name, text in _extract(entry, field_weights).items():
            word_counts = Counter(normalize_words(text))
            entries_by_field.setdefault(field_name, []).append((entry_index, word_counts, text))

    # -- step 2: score every entry, field by field
    total_scores = {}  # {entry_index: final score}
    for field_name, field_data in entries_by_field.items():
        lengths = [sum(counts.values()) for _, counts, _ in field_data]
        avg_length = sum(lengths) / len(lengths)
        if not avg_length:
            continue  # every entry is empty in this field, nothing to score

        total_entries = len(field_data)

        # for each query term: how many entries contain it AT LEAST ONCE.
        # matching is done as "inside a word", so "vitamin" also finds "vitamins".
        # an entry counts only once even if it contains several matching words.
        entries_with_term = {}
        for term in query_terms:
            entries_with_term[term] = sum(
                1 for _, counts, _ in field_data if any(term in word for word in counts)
            )

        field_weight = (field_weights or {}).get(field_name, 1.0)

        for position, (entry_index, word_counts, text) in enumerate(field_data):
            entry_score = 0.0
            entry_length = lengths[position]

            for term in query_terms:
                # how many times this term appears inside THIS entry's words
                term_hits = sum(count for word, count in word_counts.items() if term in word)
                if not term_hits:
                    continue

                # rarity bonus: rare terms score higher than common ones.
                # this is the "lucene-style" formula, which stays >= 0 as long
                # as entries_with_term never exceeds total_entries (it can't now).
                num_with_term = entries_with_term[term]
                rarity_bonus = math.log(1 + (total_entries - num_with_term + 0.5) / (num_with_term + 0.5))

                # length handicap: an entry of average size gets 1.0; longer
                # entries get > 1.0 (making it harder to score), shorter < 1.0.
                length_handicap = 1 - length_penalty + length_penalty * entry_length / avg_length

                # the diminishing-returns part: term_hits lifts the score, but
                # the denominator makes each extra hit count a bit less.
                term_score = rarity_bonus * term_hits * (repeat_saturation + 1) / (
                    term_hits + repeat_saturation * length_handicap
                )
                entry_score += term_score

            # small bonus when the whole query appears verbatim in the entry
            if entry_score > 0 and full_query and full_query in text.lower():
                entry_score *= 1.5

            if entry_score:
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
        results.append({"id": entry_id or index, "score": score, "entry": entry})
    return results
