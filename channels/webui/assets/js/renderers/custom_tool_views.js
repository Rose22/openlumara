// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-18)
// custom tool call VIEWS: per-tool data helpers + registry entries.
// the display SYSTEM (registry, toolDisplayView, generic helpers) lives in
// tool_display.js; everything view-specific lives here. styling for these
// views is in css/chat/custom_tool_views.css, markup in
// templates/chat/tool_displays.html.
//
// to add a view: helper(s) here -> registerToolDisplay({match, view}) ->
// template branch with that view name -> styles in custom_tool_views.css.
//
// helpers are top-level (alpine expressions resolve them as globals at
// render time); registration happens on alpine:init (the app's boot hook,
// same as init.js) - scripts are globbed in without a guaranteed order,
// but alpine:init fires from alpine's deferred script, so by then every
// globbed script (incl. the tool_display.js registry) has loaded, and it
// still runs well before any chat messages render.

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
const _STREAM_MEMOS = new Map();
let _RENDER_TICK = null;

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
        m.inputs.every((v, i) => v === inputs[i])) return m.out;

    if (!m) {
        m = { inputs: [], out: null, at: 0, timer: null };
        _STREAM_MEMOS.set(key, m);
        while (_STREAM_MEMOS.size > STREAM_MEMO_MAX) {
            const oldest = _STREAM_MEMOS.keys().next().value;
            const evicted = _STREAM_MEMOS.get(oldest);
            if (evicted.timer) clearTimeout(evicted.timer);
            _STREAM_MEMOS.delete(oldest);
        }
    }

    const tick = _renderTick();
    const now = performance.now();
    if (m.out !== null && now - m.at < STREAM_MEMO_MIN_MS) {
        // within the throttle window: serve the stale render and wake the
        // getter again when the window elapses so nothing is left behind
        if (m.timer === null) {
            m.timer = setTimeout(() => {
                m.timer = null;
                _RENDER_TICK.v++;
            }, STREAM_MEMO_MIN_MS);
        }
        return m.out;
    }

    m.inputs = inputs;
    m.out = compute();
    m.at = now;
    return m.out;
}

// -- coder_file_edit: diff view ---------------------------------------------

// generic helper: true line diff (LCS) between two code strings.
// common lines render as context, changed lines as -/+; long unchanged
// stretches collapse to a '..' marker with a couple context lines kept.
// works on partial (streaming) inputs too - it just re-diffs as it grows.
function diffLines(aText, bText) {
    const a = (aText || '').replace(/\n$/, '').split('\n');
    const b = (bText || '').replace(/\n$/, '').split('\n');
    if (a.length === 1 && a[0] === '') a.pop();
    if (b.length === 1 && b[0] === '') b.pop();

    // LCS table (classic dp). bail to naive mode for huge inputs.
    const n = a.length, m = b.length;
    if (n * m > 250000) return [...a.map(t => ['-', t]), ...b.map(t => ['+', t])];

    const dp = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
    for (let i = n - 1; i >= 0; i--)
        for (let j = m - 1; j >= 0; j--)
            dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);

    const out = [];
    let i = 0, j = 0;
    while (i < n && j < m) {
        if (a[i] === b[j]) { out.push([' ', a[i]]); i++; j++; }
        else if (dp[i + 1][j] >= dp[i][j + 1]) { out.push(['-', a[i]]); i++; }
        else { out.push(['+', b[j]]); j++; }
    }
    while (i < n) out.push(['-', a[i++]]);
    while (j < m) out.push(['+', b[j++]]);
    return out;
}

function collapseContext(rows, keep) {
    // keep `keep` context lines around changes, collapse the rest
    const out = [];
    let run = [];
    const flush = () => {
        if (run.length > keep * 2 + 1) {
            out.push(...run.slice(0, keep));
            out.push(['..', `${run.length - keep * 2} unchanged`]);
            out.push(...run.slice(-keep));
        } else out.push(...run);
        run = [];
    };
    for (const row of rows) {
        if (row[0] === ' ') run.push(row);
        else { flush(); out.push(row); }
    }
    flush();
    return out;
}

// full diff markup for the view box. THE ONE html-string view: the box is
// painted via x-fade-html, and token fade requires whole-content repaints
// (x-for rows can't survive that), so this view generates its row markup
// here instead of in the template. all text goes through escapeHtml or
// hljs (whose output is escaped), so it's safe markup.
function diffHtml(original, replacement, lang, cacheKey) {
    // memoized + throttled while the args stream in (see streamMemo)
    return streamMemo('edit:' + cacheKey, [original, replacement, lang],
        () => _diffHtmlNow(original, replacement, lang));
}

function _diffHtmlNow(original, replacement, lang) {
    const clsFor = sign =>
        sign === '..' ? 'diff-gap' : sign === '-' ? 'diff-del' : sign === '+' ? 'diff-add' : 'diff-ctx';
    let rows;
    if (!original && !replacement) return '';
    if (!original || !replacement) {
        // while only one side has streamed in, show it as context/plain
        const solo = (original || replacement || '').replace(/\n$/, '').split('\n');
        rows = solo.map(t => [' ', t]);
    } else {
        rows = collapseContext(diffLines(original, replacement), 2);
    }
    return rows.map(([sign, text]) => {
        const gutter = sign === '..' ? '..' : sign;
        const body = sign === '..' ? escapeHtml(text) : highlightDiffLine(text, lang);
        return `<div class="diff-line ${clsFor(sign)}">` +
            `<span class="diff-gutter">${gutter}</span>` +
            `<span class="diff-text">${body}</span></div>`;
    }).join('');
}

// -- web_search_*: result cards ---------------------------------------------

// flatten a web_search response into display cards: [{ title, url, thumb,
// snippet }]. response shape: { status, content: [ wrapped, instruction ] }
// with the results living in wrapped.web_content. url key differs per kind
// (href for text, url/image for the rest), snippet likewise
// (body/description/info). only http(s) urls are passed through; anything
// else renders as plain text.
function searchResults(response) {
    const wrapped = response?.content?.find?.(c => c && typeof c === 'object' && c.web_content);
    const items = Array.isArray(wrapped?.web_content) ? wrapped.web_content : [];
    const safeUrl = u => (typeof u === 'string' && /^https?:\/\//i.test(u)) ? u : '';
    return items.map(res => ({
        title: res.title || '(untitled)',
        url: safeUrl(res.href || res.url || res.image),
        thumb: safeUrl(res.thumbnail),
        snippet: res.body || res.description || res.info || '',
    }));
}

// -- coder_file_read: highlighted code block ----------------------------------

// pick an hljs language from the file extension; undefined -> auto-detect.
const READ_LANG_BY_EXT = {
    py: 'python', js: 'javascript', mjs: 'javascript', ts: 'typescript',
    json: 'json', html: 'html', xml: 'xml', css: 'css', scss: 'scss',
    yml: 'yaml', yaml: 'yaml', md: 'markdown', rs: 'rust', go: 'go',
    c: 'c', h: 'c', cpp: 'cpp', hpp: 'cpp', sh: 'bash', bash: 'bash',
    toml: 'ini', ini: 'ini', sql: 'sql', java: 'java', rb: 'ruby',
    php: 'php', txt: 'plaintext',
};

function langForPath(path) {
    const ext = (path || '').split('.').pop()?.toLowerCase();
    return READ_LANG_BY_EXT[ext];
}

// highlighted html for a read file. hljs escapes the code itself, so the
// output is safe markup regardless of content. huge dumps skip highlight
// (auto-detect on megabytes would stutter); plain escaped instead.
function highlightedCode(code, lang) {
    const esc = escapeHtml(code ?? '');
    if (!code || code.length > 200000 || typeof hljs === 'undefined') return esc;
    try {
        if (lang && hljs.getLanguage(lang))
            return hljs.highlight(code, { language: lang }).value;
        // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-18)
        // auto-detect runs EVERY grammar in hljs - catastrophic on big
        // files with unknown extensions. only guess for small snippets.
        if (code.length > 20000) return esc;
        return hljs.highlightAuto(code).value;
    } catch {
        return esc;
    }
}

// per-line highlighting for diff rows. lines are highlighted in ISOLATION
// (the diff only shows excerpts, so whole-file highlighting is impossible):
// known languages only - per-line auto-detect would guess wildly. tiny
// cache: diffs re-run on every streamed chunk, and context lines mostly
// repeat between runs.
const _diffLineCache = new Map();
function highlightDiffLine(text, lang) {
    if (!text) return '';
    if (!lang || typeof hljs === 'undefined' || !hljs.getLanguage(lang))
        return escapeHtml(text);
    const key = lang + '\u0000' + text;
    let html = _diffLineCache.get(key);
    if (html === undefined) {
        try {
            html = hljs.highlight(text, { language: lang, ignoreIllegals: true }).value;
        } catch {
            html = escapeHtml(text);
        }
        if (_diffLineCache.size > 2000) _diffLineCache.clear();
        _diffLineCache.set(key, html);
    }
    return html;
}

// -- coder_folder_grep / coder_file_grep: match lists --------------------------

// normalize the grep response into [{ file, matches }]. content is a flat
// array of match dicts, or { matches, note } when the max_matches cap hit.
// folder_grep matches carry a per-match file; file_grep matches don't, so
// those group under the file_path argument instead.
function grepGroups(response, args) {
    if (!response || response.status !== 'success') return [];
    const c = response.content;
    const items = Array.isArray(c) ? c : (Array.isArray(c?.matches) ? c.matches : []);
    const fallbackFile = args?.file_path ?? args?.sub_path ?? 'matches';
    const groups = new Map();
    for (const m of items) {
        const file = m.file ?? fallbackFile;
        if (!groups.has(file)) groups.set(file, []);
        groups.get(file).push(m);
    }
    return [...groups.entries()].map(([file, matches]) => ({ file, matches }));
}

// flatten one file's matches into display rows: dimmed context_before, the
// highlighted match line, dimmed context_after. line numbers only on the
// match itself (context lines get a blank gutter).
function grepRows(matches) {
    const rows = [];
    for (const m of matches ?? []) {
        for (const line of m.context_before ?? [])
            rows.push({ num: '', text: line, kind: 'ctx' });
        rows.push({ num: m.line_num, text: m.line, kind: 'hit' });
        for (const line of m.context_after ?? [])
            rows.push({ num: '', text: line, kind: 'ctx' });
    }
    return rows;
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

// -- scheduler_add_job: schedule card ------------------------------------------

const WEEKDAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

// derive the display bits from a scheduler job's args. only fields the
// model actually passed show up; everything optional stays hidden.
function schedulerInfo(args) {
    const when = args.relative_duration ?? args.target_time ?? '';
    const tags = [];
    if (args.recurring) tags.push('recurring');
    if (args.weekdays_only) tags.push('weekdays');
    if (Number.isInteger(args.target_weekday))
        tags.push(WEEKDAY_NAMES[args.target_weekday] ?? `day ${args.target_weekday}`);
    return { when, tags, action: args.action ?? '' };
}

// -- tools_load: module chips ---------------------------------------------------

// meta tool that loads other tools; the args' module_names list is the
// whole story, the response is boilerplate. error responses (unknown
// module) are shown as plain text instead.
function toolLoadModules(args) {
    return Array.isArray(args.module_names) ? args.module_names : [];
}

// -- registrations ------------------------------------------------------------

document.addEventListener('alpine:init', () => {
    // coder file edits: show the change as a diff, live while the args stream
    registerToolDisplay({
        match: /^coder_file_edit$/,
        view: 'coder-file-edit',
        summary: (res, tool, cacheKey) => {
            if (res?.status !== 'success') return '';
            const args = toolArgs(tool, cacheKey);
            if (!args.original_code || !args.replacement_code) return '';
            // full diff per reactive flush adds up (x-text evaluates even
            // while collapsed) - memoize it like the view itself
            return streamMemo('edit-sum:' + cacheKey,
                [args.original_code, args.replacement_code], () => {
                    let add = 0, del = 0;
                    for (const [sign] of diffLines(args.original_code, args.replacement_code)) {
                        if (sign === '+') add++;
                        else if (sign === '-') del++;
                    }
                    return `+${add} −${del}`;
                });
        }
    });

    // web searches: render results as titled link cards
    registerToolDisplay({
        match: /^web_search_(text|images|news|videos|books)$/,
        view: 'web-search',
        summary: res => {
            const n = searchResults(res).length;
            return n ? `${n} result${n === 1 ? '' : 's'}` : '';
        }
    });

    // coder file reads: highlighted code block
    registerToolDisplay({
        match: /^coder_file_read$/,
        view: 'file-read',
        summary: res => {
            if (!res || res.status === 'error' || typeof res.content !== 'string') return '';
            const n = res.content.split('\n').length;
            return `${n} line${n === 1 ? '' : 's'}`;
        }
    });

    // coder file creates: the new file's content, highlighted, streamed live
    registerToolDisplay({
        match: /^coder_file_create$/,
        view: 'file-create',
        summary: (res, tool, cacheKey) => {
            if (res?.status !== 'success') return '';
            const content = toolArgs(tool, cacheKey).content;
            if (!content) return '';
            const n = content.replace(/\n$/, '').split('\n').length;
            return `${n} line${n === 1 ? '' : 's'}`;
        }
    });

    // grep calls: file-grouped match lists with line numbers + context
    registerToolDisplay({
        match: /^coder_(folder|file)_grep$/,
        view: 'grep',
        summary: (res, tool, cacheKey) => {
            const groups = grepGroups(res, toolArgs(tool, cacheKey));
            const n = groups.reduce((sum, g) => sum + g.matches.length, 0);
            if (!n) return '';
            return groups.length > 1 ? `${n} matches · ${groups.length} files` : `${n} match${n === 1 ? '' : 'es'}`;
        }
    });

    // coder glob: file list + count
    registerToolDisplay({
        match: /^coder_glob$/,
        summary: res => {
            const n = Array.isArray(res?.content) ? res.content.length : 0;
            return n ? `${n} file${n === 1 ? '' : 's'}` : '';
        }
    });

    // scheduler jobs: card with clock, when + action
    registerToolDisplay({
        match: /^scheduler_add_job$/,
        view: 'scheduler-job',
        summary: (res, tool, cacheKey) => schedulerInfo(toolArgs(tool, cacheKey)).when
    });

    // tools_load: which modules' tools just got loaded
    registerToolDisplay({
        match: /^tools_load$/,
        view: 'tools-load',
        summary: (res, tool, cacheKey) => {
            const mods = toolLoadModules(toolArgs(tool, cacheKey));
            return mods.length ? mods.join(' + ') : '';
        }
    });
});
