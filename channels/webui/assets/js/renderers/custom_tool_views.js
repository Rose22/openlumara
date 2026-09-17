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

// diff rows for the view template: [{ gutter, cls, text }] - no html,
// the template renders these with x-for + x-text.
function diffRows(original, replacement) {
    const clsFor = sign =>
        sign === '..' ? 'diff-gap' : sign === '-' ? 'diff-del' : sign === '+' ? 'diff-add' : 'diff-ctx';
    let rows;
    if (!original && !replacement) return [];
    if (!original || !replacement) {
        // while only one side has streamed in, show it as context/plain
        const solo = (original || replacement || '').replace(/\n$/, '').split('\n');
        rows = solo.map(t => [' ', t]);
    } else {
        rows = collapseContext(diffLines(original, replacement), 2);
    }
    return rows.map(([sign, text]) => ({
        gutter: sign === '..' ? '..' : sign,
        cls: clsFor(sign),
        text,
    }));
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
});
