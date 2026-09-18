// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-18)
// tool display CORE: the registry + generic template helpers that let
// specific tool calls render from an inline markup view
// (templates/chat/tool_displays.html) instead of the default arg rows.
// NO html strings - the registry only matches and names views; all markup
// lives in the template file.
//
// THE VIEWS THEMSELVES (per-tool helpers + registry entries) live in
// js/renderers/custom_tool_views.js - this file is system only, so the
// whole view collection can grow/ship separately (and eventually be
// replaced/extended by plugins).
//
// registry entry shape (registered by the views file):
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
// nothing is shown (Rosie's call) - displays can opt in via summary().
// summaries get (parsedResponse, tool) - many stats (diff sizes, glob
// counts) live in the ARGS, so they need the tool itself as well.
function toolCallResultSummary(tool, cacheKey) {
    const display = toolDisplayFor(tool.function?.name);
    if (!display || typeof display.summary !== 'function') return '';
    let parsed = null;
    try {
        parsed = JSON.parse(tool.response);
    } catch {
        return '';
    }
    return display.summary(parsed, tool, cacheKey) ?? '';
}

// -- generic template helpers ----------------------------------------------
// (view-specific data helpers belong in custom_tool_views.js, not here)

// parsed (possibly PARTIAL, mid-stream) arguments for a claimed tool
// call, for use inside the view templates. {} until anything parses.
function toolArgs(tool, cacheKey) {
    try {
        const a = partialJsonParse(tool.function?.arguments ?? '{}', cacheKey + ':args');
        if (a !== null && typeof a === 'object') return a;
    } catch { /* no parsable args yet */ }
    return {};
}

// parsed tool response object, or null while it's absent/incomplete.
// for use inside the view templates.
function toolResponse(tool) {
    try {
        const p = JSON.parse(tool.response);
        if (p !== null && typeof p === 'object') return p;
    } catch { /* response not (fully) here yet */ }
    return null;
}
