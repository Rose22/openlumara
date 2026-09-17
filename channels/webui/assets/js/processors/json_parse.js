// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
/* deterministic partial-JSON parser for streamed tool call arguments.

   the old implementation tried to "repair" incomplete JSON with brace and
   quote counting, and fell back to `{ _raw: ... }` whenever the heuristic
   choked. mid-stream that flipped the rendered rows between real keys and
   a single `_raw` row every few tokens, which is the jank users saw.

   this walks the string once with a recursive descent parser that
   understands incomplete input: unterminated strings, numbers and
   containers simply truncate the parse at that point. the parsed object
   only ever grows while tokens stream in, so the x-for rows stay stable.
   a small last-good-parse cache (keyed by tool call id) guards against
   rows ever disappearing if a token arrives that parses to less than what
   is already on screen.
*/

function _skipWs(str, i) {
    while (i < str.length && (str[i] === ' ' || str[i] === '\n' || str[i] === '\t' || str[i] === '\r')) i++;
    return i;
}

function _parseStringAt(str, i) {
    // i must point at the opening quote.
    // returns { value, next, terminated } - partial strings come back with
    // terminated=false so the caller can decide whether to keep them.
    if (str[i] !== '"') return null;
    let out = '';
    i++;
    while (i < str.length) {
        const c = str[i];
        if (c === '\\') {
            if (i + 1 >= str.length) return { value: out, next: i, terminated: false };
            const esc = str[i + 1];
            switch (esc) {
                case 'n': out += '\n'; break;
                case 'r': out += '\r'; break;
                case 't': out += '\t'; break;
                case 'b': out += '\b'; break;
                case 'f': out += '\f'; break;
                case 'u': {
                    const hex = str.slice(i + 2, i + 6);
                    if (hex.length < 4) return { value: out, next: i, terminated: false };
                    const code = parseInt(hex, 16);
                    if (Number.isNaN(code)) return { value: out, next: i, terminated: false };
                    out += String.fromCharCode(code);
                    i += 6;
                    continue;
                }
                default: out += esc;
            }
            i += 2;
            continue;
        }
        if (c === '"') return { value: out, next: i + 1, terminated: true };
        out += c;
        i++;
    }
    return { value: out, next: i, terminated: false };
}

function _parseValue(ctx) {
    const str = ctx.str;
    ctx.i = _skipWs(str, ctx.i);
    if (ctx.i >= str.length) { ctx.done = true; return null; }

    const c = str[ctx.i];
    if (c === '{') return _parseObject(ctx);
    if (c === '[') return _parseArray(ctx);
    if (c === '"') {
        const s = _parseStringAt(str, ctx.i);
        ctx.i = s.next;
        if (!s.terminated) ctx.done = true;
        return s.value;
    }
    if (str.startsWith('true', ctx.i)) { ctx.i += 4; return true; }
    if (str.startsWith('false', ctx.i)) { ctx.i += 5; return false; }
    if (str.startsWith('null', ctx.i)) { ctx.i += 4; return null; }

    const rest = str.slice(ctx.i);
    // partially streamed literal (e.g. "tru") - stop here, keep it out
    if (rest.length < 5 && ('true'.startsWith(rest) || 'false'.startsWith(rest) || 'null'.startsWith(rest))) {
        ctx.done = true;
        return null;
    }

    const numMatch = /^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/.exec(rest);
    if (numMatch) {
        ctx.i += numMatch[0].length;
        if (ctx.i >= str.length) ctx.done = true;
        return Number(numMatch[0]);
    }

    // lone '-' or anything we can't make sense of: treat as incomplete
    ctx.done = true;
    return null;
}

function _parseObject(ctx) {
    const str = ctx.str;
    const obj = {};
    ctx.i++; // consume '{'
    while (true) {
        ctx.i = _skipWs(str, ctx.i);
        if (ctx.i >= str.length) { ctx.done = true; return obj; }
        if (str[ctx.i] === '}') { ctx.i++; return obj; }
        if (str[ctx.i] !== '"') { ctx.done = true; return obj; }

        const key = _parseStringAt(str, ctx.i);
        if (!key.terminated) { ctx.done = true; return obj; }

        ctx.i = _skipWs(str, key.next);
        if (str[ctx.i] !== ':') { ctx.done = true; return obj; }
        ctx.i++;

        obj[key.value] = _parseValue(ctx);
        if (ctx.done) return obj;

        ctx.i = _skipWs(str, ctx.i);
        if (ctx.i >= str.length) { ctx.done = true; return obj; }
        if (str[ctx.i] === ',') { ctx.i++; continue; }
        if (str[ctx.i] === '}') { ctx.i++; return obj; }
        ctx.done = true;
        return obj;
    }
}

function _parseArray(ctx) {
    const str = ctx.str;
    const arr = [];
    ctx.i++; // consume '['
    while (true) {
        ctx.i = _skipWs(str, ctx.i);
        if (ctx.i >= str.length) { ctx.done = true; return arr; }
        if (str[ctx.i] === ']') { ctx.i++; return arr; }

        arr.push(_parseValue(ctx));
        if (ctx.done) return arr;

        ctx.i = _skipWs(str, ctx.i);
        if (ctx.i >= str.length) { ctx.done = true; return arr; }
        if (str[ctx.i] === ',') { ctx.i++; continue; }
        if (str[ctx.i] === ']') { ctx.i++; return arr; }
        ctx.done = true;
        return arr;
    }
}

function parsePartialJSON(str) {
    const ctx = { str, i: 0, done: false };
    ctx.i = _skipWs(str, ctx.i);
    if (ctx.i >= str.length) return {};
    const c = str[ctx.i];
    if (c === '{' || c === '[') return _parseValue(ctx);
    return null; // not json-ish at all
}

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
// last-good-parse cache, keyed by tool call id, so a mid-stream hiccup can
// never blank out rows that already streamed in.
const _PARSE_CACHE = new Map();
const _PARSE_CACHE_MAX = 64;

function _entryCount(parsed) {
    if (Array.isArray(parsed)) return parsed.length;
    if (parsed && typeof parsed === 'object') return Object.keys(parsed).length;
    return 0;
}

function partialJsonParse(str, cacheKey) {
    if (!str || !str.trim()) return {};

    try {
        const full = JSON.parse(str);
        if (cacheKey) _PARSE_CACHE.set(cacheKey, { raw: str, parsed: full });
        return full;
    } catch (e) {}

    const partial = parsePartialJSON(str);

    if (partial !== null && typeof partial === 'object') {
        if (!cacheKey) return partial;
        const cached = _PARSE_CACHE.get(cacheKey);
        const result = (cached && _entryCount(cached.parsed) > _entryCount(partial)) ? cached.parsed : partial;
        _PARSE_CACHE.set(cacheKey, { raw: str, parsed: result });
        while (_PARSE_CACHE.size > _PARSE_CACHE_MAX) _PARSE_CACHE.delete(_PARSE_CACHE.keys().next().value);
        return result;
    }

    if (cacheKey) {
        const cached = _PARSE_CACHE.get(cacheKey);
        if (cached && str.startsWith(cached.raw)) return cached.parsed;
    }
    return { _raw: formatRawString(str) };
}

/**
 * Converts JSON escape sequences in a raw (unparseable) string into their
 * actual characters so the webui can display them properly.
 *
 * The single-pass regex ensures `\\n` (escaped backslash + 'n') still
 * displays as the literal text `\n` instead of being treated as a newline.
 */
function formatRawString(str) {
    return str.replace(/\\(n|r|t|b|f|u[0-9a-fA-F]{4}|["'\/\\])/g, (match, esc) => {
        switch (esc[0]) {
            case 'n': return '\n';
            case 'r': return '\r';
            case 't': return '\t';
            case 'b': return '\b';
            case 'f': return '\f';
            case 'u': return String.fromCharCode(parseInt(esc.slice(1), 16));
            default: return esc[0]; // ", ', /, \
        }
    });
}
