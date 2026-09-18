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
function diffHtml(original, replacement, lang) {
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
        return (lang && hljs.getLanguage(lang))
            ? hljs.highlight(code, { language: lang }).value
            : hljs.highlightAuto(code).value;
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
function codeLinesHtml(code, lang, startLine) {
    if (!code) return '';
    return splitHighlightedLines(highlightedCode(code, lang), startLine ?? 1);
}

// -- registrations ------------------------------------------------------------

document.addEventListener('alpine:init', () => {
    // coder file edits: show the change as a diff, live while the args stream
    registerToolDisplay({
        match: /^coder_file_edit$/,
        view: 'coder-file-edit'
    });

    // web searches: render results as titled link cards
    registerToolDisplay({
        match: /^web_search_(text|images|news|videos|books)$/,
        view: 'web-search'
    });

    // coder file reads: highlighted code block
    registerToolDisplay({
        match: /^coder_file_read$/,
        view: 'file-read'
    });

    // coder file creates: the new file's content, highlighted, streamed live
    registerToolDisplay({
        match: /^coder_file_create$/,
        view: 'file-create'
    });

    // grep calls: file-grouped match lists with line numbers + context
    registerToolDisplay({
        match: /^coder_(folder|file)_grep$/,
        view: 'grep'
    });
});
