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
    """scores entries using Okapi BM25 with per-field weighting"""
    k1, b = 1.5, 0.75
    raw = str(query).strip().lower()
    qterms = list(dict.fromkeys(normalize_words(query)))
    if not qterms:
        return []

    # tokenize every field once, grouped per field across the whole corpus
    per_field = {}
    for fields in (_extract(entry, field_weights) for entry in entries):
        for fname, text in fields.items():
            per_field.setdefault(fname, []).append((Counter(normalize_words(text)), text))

    totals = {}
    for fname, field_data in per_field.items():
        lengths = [sum(tfs.values()) for tfs, _ in field_data]
        avgdl = sum(lengths) / len(lengths)
        if not avgdl:
            continue

        dfs = Counter()
        for tfs, _ in field_data:
            dfs.update(tfs)

        # query terms match document tokens as substrings ("vitamin" finds "vitamins")
        n = len(field_data)
        df_by_qt = {qt: sum(c for term, c in dfs.items() if qt in term) for qt in qterms}
        weight = (field_weights or {}).get(fname, 1.0)

        for i, (tfs, text) in enumerate(field_data):
            score = 0.0
            for qt in qterms:
                df = df_by_qt[qt]
                tf = sum(c for term, c in tfs.items() if qt in term)
                if df and tf:
                    # Lucene-style IDF, guaranteed non-negative
                    idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                    score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * lengths[i] / avgdl))
            if score > 0 and raw and raw in text.lower():
                score *= 1.5
            if score:
                totals[i] = totals.get(i, 0.0) + score * weight

    return sorted(totals.items(), key=lambda item: item[1], reverse=True)[:top_n]

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
