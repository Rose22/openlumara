// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
// tool display registry: claims specific tool calls so their body renders
// from an inline markup template (templates/chat/tool_displays.html)
// instead of the default arg rows. NO html strings - the registry only
// matches and names views; all markup lives in the template file.
// webui plugins will later hook in via registerToolDisplay() plus their
// own template branch.
//
// entry shape:
//   match:   RegExp tested against the tool function name
//   view:    name of the template branch in tool_displays.html to render
//   summary: (optional) (response) => short one-liner for the collapsed
//            header. default (no summary fn, or empty return) = show nothing.

const TOOL_DISPLAYS = [];

function registerToolDisplay(entry) {
    TOOL_DISPLAYS.push(entry);
}

function toolDisplayFor(name) {
    if (!name) return null;
    return TOOL_DISPLAYS.find(d => d.match.test(name)) ?? null;
}

// which template branch (if any) renders this call's body; null = default
function toolDisplayView(tool) {
    return toolDisplayFor(tool?.function?.name)?.view ?? null;
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

// diff rows for the view template: [{ gutter, cls, text }] - no html,
// the template renders these with x-for + x-text. works on partial
// (streaming) inputs too - it just re-diffs as the args grow.
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

// -- registry entries -----------------------------------------------------

// coder file edits: show the change as a diff, live while the args stream
registerToolDisplay({
    match: /^coder_file_edit$/,
    view: 'coder-file-edit'
});

// -- template helpers ------------------------------------------------------

// parsed (possibly PARTIAL, mid-stream) arguments for a claimed tool
// call, for use inside the view templates. {} until anything parses.
function toolArgs(tool, cacheKey) {
    try {
        const a = partialJsonParse(tool.function?.arguments ?? '{}', cacheKey + ':args');
        if (a !== null && typeof a === 'object') return a;
    } catch { /* no parsable args yet */ }
    return {};
}


