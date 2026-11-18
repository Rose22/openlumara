// -- AI GENERATED CODE (qwen3.8-flash-next) :: (2026-10-25) harness:openlumara status:reviewed
// shared machinery for the custom tool views, owned by the webui itself:
// the streaming render memo + the generic highlight/line helpers that more
// than one module's views lean on, plus the shared error text helper.
//
// the per-VIEW files (helpers + registerToolDisplay calls) now live with
// their owners: core-meta-tool views in this folder, coder views in
// modules/coder/webui/assets/js/custom_tool_views/, shell in modules/shell/
// ..., scheduler in modules/scheduler/..., web search in modules/
// web_search/... Module JS is auto-globbed onto the page (ext_js_files),
// loads after these core files, and registers on alpine:init - so helper
// globals are always resolved before any view renders.

// -- streaming render memo ----------------------------------------------------

// the backend re-broadcasts the FULL accumulated segment while a tool call
// streams, and alpine re-evaluates every view getter on each of those
// messages (x-fade-html AND x-show read the same html getter). an O(n)
// render (full parse + hljs + diff) over the growing args is therefore
// O(n^2) for large files, with a fresh giant string + DOM subtree per pass -
// the crawl and the RAM blowup. memo caches the last output per view
// instance (keyed by the tool call's cacheKey) and throttles recomputes to
// one per STREAM_MEMO_MIN_MS; a bump timer touches a tiny reactive counter
// that every memo getter reads, so the final tail still lands once the
// throttle window passes.
const STREAM_MEMO_MIN_MS = 100;
const STREAM_MEMO_MAX = 16;
const STREAM_MEMO_MAX_BYTES = 12 * 1024 * 1024;
const _STREAM_MEMOS = new Map();
let _STREAM_MEMO_BYTES = 0;
let _RENDER_TICK = null;

function _memoSize(m) {
    let size = String(m.out || '').length;
    for (const input of m.inputs) {
        if (typeof input === 'string') size += input.length;
        else if (input != null) size += 8;
    }
    return size;
}

function _clearMemo(m) {
    if (m && m.timer) clearTimeout(m.timer);
}

function _evictMemos(bytesToAdd) {
    while (_STREAM_MEMOS.size >= STREAM_MEMO_MAX ||
           (_STREAM_MEMOS.size > 0 && _STREAM_MEMO_BYTES + bytesToAdd > STREAM_MEMO_MAX_BYTES)) {
        const oldestKey = _STREAM_MEMOS.keys().next().value;
        const oldest = _STREAM_MEMOS.get(oldestKey);
        _clearMemo(oldest);
        _STREAM_MEMO_BYTES -= _memoSize(oldest);
        _STREAM_MEMOS.delete(oldestKey);
    }
}

function _renderTick() {
    if (_RENDER_TICK === null) _RENDER_TICK = Alpine.reactive({ v: 0 });
    _RENDER_TICK.v; // tracked read: the bump timer re-fires this getter
    return _RENDER_TICK;
}

// inputs is an array of the (primitive) render inputs; identity comparison
// is enough - streamed strings grow per chunk, so lengths differ and the
// compare short-circuits.
function streamMemo(key, inputs, compute) {
    let m = _STREAM_MEMOS.get(key);
    if (m && m.inputs.length === inputs.length &&
        m.inputs.every((v, i) => v === inputs[i])) {
        _STREAM_MEMOS.delete(key);
        _STREAM_MEMOS.set(key, m);
        return m.out;
    }

    const hadOld = Boolean(m);
    const oldSize = hadOld ? _memoSize(m) : 0;
    if (!m) m = { inputs: [], out: null, at: 0, timer: null };

    const tick = _renderTick();
    const now = performance.now();
    if (m.out !== null && now - m.at < STREAM_MEMO_MIN_MS) {
        _STREAM_MEMOS.delete(key);
        _STREAM_MEMOS.set(key, m);
        if (m.timer === null) {
            m.timer = setTimeout(() => {
                m.timer = null;
                _RENDER_TICK.v++;
            }, STREAM_MEMO_MIN_MS);
        }
        return m.out;
    }

    const nextOut = compute();

    if (hadOld) {
        _STREAM_MEMOS.delete(key);
        _STREAM_MEMO_BYTES -= oldSize;
    }

    m.inputs = inputs;
    m.out = nextOut;
    m.at = now;

    const size = _memoSize(m);
    _evictMemos(size);
    _STREAM_MEMOS.set(key, m);
    _STREAM_MEMO_BYTES += size;

    return m.out;
}

// -- shared: highlighting -------------------------------------------------------

// highlighted html for code. hljs escapes the code itself, so the
// output is safe markup regardless of content. huge dumps skip highlight
// (auto-detect on megabytes would stutter); plain escaped instead.
function highlightedCode(code, lang) {
    const esc = escapeHtml(code ?? '');
    if (!code || code.length > 200000 || typeof hljs === 'undefined') return esc;
    try {
        if (lang && hljs.getLanguage(lang))
            return hljs.highlight(code, { language: lang }).value;
        // auto-detect runs EVERY grammar in hljs - catastrophic on big
        // files with unknown extensions. only guess for small snippets.
        if (code.length > 20000) return esc;
        return hljs.highlightAuto(code).value;
    } catch {
        return esc;
    }
}

// -- shared: line-numbered highlighted code blocks ----------------------------

// split highlighted html into per-line divs with a number gutter.
// operates on hljs OUTPUT (same sanctioned escape hatch as the x-html
// these views use): tracks which token spans are open so multi-line
// tokens (python docstrings, block comments) stay colored on every line
// they span - each line closes and re-opens the spans around it.
function splitHighlightedLines(html, startLine) {
    const tokenRe = /<[^>]+>|[^<]+/g;
    const open = [];
    const lines = [];
    let cur = '';
    for (const tok of html.match(tokenRe) ?? []) {
        if (tok[0] === '<') {
            if (tok.startsWith('</')) open.pop();
            else if (!tok.endsWith('/>')) open.push(tok);
            cur += tok;
        } else {
            tok.split('\n').forEach((part, i) => {
                if (i > 0) {
                    lines.push(cur + '</span>'.repeat(open.length));
                    cur = open.join('');
                }
                cur += part;
            });
        }
    }
    lines.push(cur + '</span>'.repeat(open.length));
    return lines.map((l, i) =>
        `<div class="code-line"><span class="code-num">${startLine + i}</span>` +
        `<span class="code-text">${l || '\u200b'}</span></div>`
    ).join('');
}

// full code block for the read/create views: highlighted + line numbers.
// startLine offsets the gutter for chunked reads (line_start arg).
// memoized + throttled per view instance (see streamMemo): without it the
// full highlight + line split re-runs for every getter read on every
// streamed chunk, which turns quadratic on large streamed files.
function codeLinesHtml(code, lang, startLine, cacheKey) {
    if (!code) return '';
    return streamMemo('code:' + cacheKey, [code, lang, startLine ?? 1],
        () => splitHighlightedLines(highlightedCode(code, lang), startLine ?? 1));
}

// -- shared: error text below any custom view ----------------------------------
// every registered view shows a failed call's error text below its markup,
// in the error color (see .display-error in custom_tool_views.css). parses
// the response itself so view scopes only need `tool`; content is usually
// a string, stringified if a module returned an object.
function toolDisplayError(tool) {
    const resp = toolResponse(tool);
    if (!resp || resp.status !== 'error') return '';
    const c = resp.content;
    if (typeof c === 'string') return c;
    // structured error payloads (eg. sandboxed shell: timeouts, output
    // truncation) fail the call while keeping stdout/stderr in content -
    // show just the human-readable errors lines instead of dumping the
    // whole raw JSON object
    if (c && Array.isArray(c.errors) && c.errors.length) return c.errors.join('\n');
    return JSON.stringify(c);
}
