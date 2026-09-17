// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
// tool display registry: custom renderers for specific tool calls.
// this is the seam webui plugins will later hook into via
// registerToolDisplay(); entries are checked top-down, first match wins.
//
// entry shape:
//   match:   RegExp tested against the tool function name
//   live:    (optional) render the body even before a response exists,
//            ie. stream live from the arguments
//   body:    (response, args) => html. response/args may be PARTIAL while
//            streaming; both are null until they parse to something.
//   summary: (optional) (response) => short one-liner for the collapsed
//            header. default (no summary fn, or empty return) = show nothing.
// body() owns the ENTIRE custom area - it returns raw html and is free to
// include any structure (boxes, footers, whatever) with .display-* classes.

const TOOL_DISPLAYS = [];

function registerToolDisplay(entry) {
    TOOL_DISPLAYS.push(entry);
}

function toolDisplayFor(name) {
    if (!name) return null;
    return TOOL_DISPLAYS.find(d => d.match.test(name)) ?? null;
}

// one-line result hint for the completed tool call header; by default
// nothing is shown (Rosie's call) - displays can opt in via summary()
function toolCallResultSummary(tool) {
    const display = toolDisplayFor(tool.function?.name);
    if (!display || typeof display.summary !== 'function') return '';
    let parsed = null;
    try {
        parsed = JSON.parse(tool.response);
    } catch {
        return '';
    }
    return display.summary(parsed) ?? '';
}

// -- generic helper: true line diff (LCS) between two code strings.
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

function codeDiffHtml(original, replacement) {
    if (!original && !replacement) return '';
    const line = (sign, cls, text) =>
        `<div class="diff-line ${cls}"><span class="diff-gutter">${sign}</span><span class="diff-text">${escapeHtml(text)}</span></div>`;
    // while only one side has streamed in, show it as context/plain
    if (!original || !replacement) {
        const solo = (original || replacement).replace(/\n$/, '').split('\n');
        return solo.map(t => line(' ', 'diff-ctx', t)).join('');
    }
    return collapseContext(diffLines(original, replacement), 2)
        .map(([sign, text]) =>
            sign === '..'
                ? `<div class="diff-line diff-gap"><span class="diff-gutter">..</span><span class="diff-text">${escapeHtml(text)}</span></div>`
                : line(sign, sign === '-' ? 'diff-del' : sign === '+' ? 'diff-add' : 'diff-ctx', text)
        )
        .join('');
}

// -- registry entries -----------------------------------------------------

// coder file edits: show the change as a diff, live while the args stream
registerToolDisplay({
    match: /^coder_file_edit$/,
    body: (response, args) => {
        const diff = codeDiffHtml(args?.original_code, args?.replacement_code);
        if (!diff) return '';
        const footer = args?.path
            ? `<div class="display-footer">file: ${escapeHtml(args.path)}</div>`
            : '';
        return `<div class="tool-display" x-auto-scroll>${diff}</div>${footer}`;
    }
});

// -- template helpers ------------------------------------------------------

// does this tool have a custom display? if so, it owns the body from the
// very first token - the default arg rows NEVER show for claimed tools.
function hasToolDisplay(tool) {
    return !!toolDisplayFor(tool?.function?.name);
}

// auto-scroll convention for .tool-display boxes inside registry html:
// x-html replaces the box on every chunk, so re-find it each repaint and
// keep it pinned to the bottom - unless the user scrolled up to read
function autoScrollToolDisplay(el, body) {
    const box = el.querySelector('.tool-display');
    if (!box) return;
    if (box._stick === undefined) {
        box._stick = true;
        box.addEventListener('scroll', () => {
            box._stick = box.scrollHeight - box.scrollTop - box.clientHeight < 24;
        });
    }
    if (box._stick) requestAnimationFrame(() => { box.scrollTop = box.scrollHeight; });
}

// render a claimed tool call's body; response and args may be partial
// (mid-stream) or null (not parseable yet). empty string = nothing to
// show yet (empty box is hidden by css).
function toolDisplayBody(tool, cacheKey) {
    const d = toolDisplayFor(tool.function?.name);
    if (!d) return null;
    let response = null;
    try {
        const p = JSON.parse(tool.response);
        if (p !== null && typeof p === 'object') response = p;
    } catch { /* response not (fully) here yet */ }
    let args = null;
    try {
        const a = partialJsonParse(tool.function?.arguments ?? '{}', cacheKey + ':display');
        if (a !== null && typeof a === 'object') args = a;
    } catch { /* no parsable args yet */ }
    return d.body(response, args) || null;
}


