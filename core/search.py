import core
import math
import re
import hashlib
import httpx

# maps (embedding url, sha1 of text) to (vector norm, vector) so each text is only embedded once
_vector_cache = {}

# matches runs of unicode word characters; drops punctuation and number-only tokens
_token_rx = re.compile(r"\w+", re.UNICODE)


def tokenize(text):
    """splits raw text into lowercase word tokens, so 'Vitamins!' and 'vitamins' match"""
    return _token_rx.findall(str(text).lower())


def make_snippet(text, query, radius=50):
    """returns a short excerpt of text centered on where the query best matches, or None if no match"""
    text = str(text)
    low = text.lower()

    candidates = []
    stripped = query.strip().lower()
    if stripped:
        candidates.append(stripped)
    candidates.extend(tokenize(query))

    best_pos = -1
    for cand in candidates:
        if not cand:
            continue
        pos = low.find(cand)
        if pos != -1:
            best_pos = pos
            break

    if best_pos == -1:
        return None

    start = max(0, best_pos - radius)
    end = min(len(text), best_pos + len(query) + radius)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


def _extract(entry, field_weights):
    """normalizes any entry (string, dict, or whatever) into a {field: text} dict"""
    if isinstance(entry, str):
        return {"text": entry}

    if isinstance(entry, dict):
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

    return {"text": str(entry)}


def _bm25(entries, query, field_weights, top_n):
    """scores entries on-the-fly using Okapi BM25 with per-field weighting and a verbatim-substring bonus"""
    k1 = 1.5
    b = 0.75

    raw = query.strip().lower()

    qterms = []
    seen = set()
    for term in tokenize(query):
        if term not in seen:
            seen.add(term)
            qterms.append(term)
    if not qterms:
        return []

    fielded = [_extract(entry, field_weights) for entry in entries]

    field_names = set()
    for fields in fielded:
        field_names.update(fields.keys())

    # per-field corpus stats (document frequency per field, average field length)
    stats = {}
    for fname in field_names:
        dfs = {}
        total_len = 0
        count = 0
        for fields in fielded:
            if fname not in fields:
                continue
            count += 1
            tokens = tokenize(fields[fname])
            total_len += len(tokens)
            for term in set(tokens):
                dfs[term] = dfs.get(term, 0) + 1
        stats[fname] = {"df": dfs, "avgdl": (total_len / count) if count else 0, "n": count}

    # search within each word using substrings
    substr_df = {}
    for fname in field_names:
        vocab = stats[fname]["df"]
        substr_df[fname] = {}
        for qt in qterms:
            substr_df[fname][qt] = sum(c for term, c in vocab.items() if qt in term)

    scored = []
    for index, fields in enumerate(fielded):
        total = 0.0
        for fname, text in fields.items():
            st = stats[fname]
            if not st["avgdl"]:
                continue

            tokens = tokenize(text)
            if not tokens:
                continue

            tfs = {}
            for term in tokens:
                tfs[term] = tfs.get(term, 0) + 1

            field_score = 0.0
            for qt in qterms:
                df = substr_df[fname][qt]
                # tf summed over all document tokens that contain the query term
                tf = 0
                for term, c in tfs.items():
                    if qt in term:
                        tf += c
                if df == 0 or tf == 0:
                    continue
                # Lucene-style IDF, guaranteed non-negative
                idf = math.log(1 + (st["n"] - df + 0.5) / (df + 0.5))
                field_score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * len(tokens) / st["avgdl"]))

            if field_score > 0 and raw and raw in text.lower():
                field_score *= 1.5

            weight = 1.0
            if field_weights and fname in field_weights:
                weight = field_weights[fname]
            total += field_score * weight

        if total > 0:
            scored.append((index, total))

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_n]


async def _embed_texts(texts, url, key, model):
    """POSTs texts to an OpenAI-compatible /embeddings endpoint and returns the vectors"""
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"

    vectors = []
    async with httpx.AsyncClient(timeout=60) as client:
        for start in range(0, len(texts), 32):
            batch = texts[start:start + 32]
            resp = await client.post(url, headers=headers, json={"model": model, "input": batch})
            if resp.status_code != 200:
                raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")
            data = resp.json().get("data", [])
            if len(data) != len(batch):
                raise Exception("embedding response did not contain one vector per input")
            vectors.extend(item["embedding"] for item in data)
    return vectors


def _cache_vector(url, text, vector):
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    _vector_cache[(url, hashlib.sha1(text.encode("utf-8")).hexdigest())] = (norm, vector)


def _get_cached_vector(url, text):
    return _vector_cache.get((url, hashlib.sha1(text.encode("utf-8")).hexdigest()))


async def _embed_search(entries, query, field_weights, top_n):
    """embeds entries (cached) and the query, then ranks by cosine similarity"""
    api_url = core.config.get("task_models", "embeddings_url") or ""
    if not api_url:
        return "search error: no embeddings URL is configured. Set 'embeddings_url' in the core settings, or clear it to use keyword search instead."

    url = api_url.rstrip("/") + "/embeddings"
    key = core.config.get("api", "key") or ""
    model = core.config.get("task_models", "embeddings_model_name") or "embeddings"

    texts = [" ".join(_extract(entry, field_weights).values()) for entry in entries]

    try:
        missing = [t for t in texts if t.strip() and _get_cached_vector(url, t) is None]
        if missing:
            new_vectors = await _embed_texts(missing, url, key, model)
            for text, vector in zip(missing, new_vectors):
                _cache_vector(url, text, vector)

        if _get_cached_vector(url, query) is None:
            qv = (await _embed_texts([query], url, key, model))[0]
            _cache_vector(url, query, qv)
    except Exception as e:
        return (
            f"search error: could not get embeddings from {url} ({core.detail_error(e)}). "
            "Make sure the server at 'embeddings_url' serves an embedding model named "
            f"'{model}', or clear 'embeddings_url' in the core settings to use keyword search instead."
        )

    qnorm, qvec = _get_cached_vector(url, query)

    scored = []
    for index, text in enumerate(texts):
        if not text.strip():
            continue
        cached = _get_cached_vector(url, text)
        if not cached:
            continue
        norm, vec = cached
        if len(vec) != len(qvec):
            continue
        sim = sum(a * b for a, b in zip(qvec, vec)) / (qnorm * norm)
        if sim > 0:
            scored.append((index, sim))

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_n]


async def search(entries, query, id_field="id", field_weights=None, top_n=10):
    """Ranks entries against a query.

    Entries can be anything: strings, dicts, or other objects (converted via str()).
    Dicts are searched field-by-field; field_weights (e.g. {"tags": 2.0, "content": 1.0})
    restricts which fields are searched and how heavily they count (BM25 mode only;
    in embed mode the selected fields are simply joined into one text).

    Uses embeddings when the core setting 'embeddings_url' is set,
    otherwise ranks with BM25 (computed fresh per call, always local).

    Returns a ranked list of {"id": ..., "score": ..., "entry": ...} dicts,
    or a single error-message string if embedding failed."""
    if not entries or not query or not str(query).strip():
        return []

    if core.config.get("task_models", "embeddings_url"):
        scored = await _embed_search(entries, query, field_weights, top_n)
    else:
        scored = _bm25(entries, query, field_weights, top_n)

    if isinstance(scored, str):
        return scored

    results = []
    for index, score in scored:
        entry = entries[index]
        if isinstance(entry, dict) and entry.get(id_field):
            doc_id = entry.get(id_field)
        else:
            doc_id = index
        results.append({"id": doc_id, "score": score, "entry": entry})
    return results
