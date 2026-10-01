/*
 * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
 * step grouping now lives in the backend (core/turns.py): history turns
 * arrive with a ready-made `steps` list, streaming segments carry a `step`
 * number + `step_status` stamped by group_stream. what's left here:
 *  - streamSteps(): fold the active-step-only stream segments into step
 *    objects shaped exactly like the backend history steps
 *  - streamTurnSplit(): the final-content-detection heuristic the backend
 *    can't know mid-stream
 *  - toolCallArgsSummary(): the one-line arg hint (pending backend move)
 * failed flags and collapsed-header labels are stamped by the backend now.
 */

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
// group streaming segments by the step number the backend stamped on them
// into objects shaped like the backend's history steps. segments of one
// step: reasoning runs, narration content, then the tool_calls segment
// that carries the step's status + modules.
function streamSteps(chain) {
    const steps = new Map();
    for (const m of chain) {
        if (m.step == null) continue;
        let s = steps.get(m.step);
        if (!s) {
            s = { step: m.step, status: 'thinking', reasoning_content: '', content: '', tool_calls: [], modules: [] };
            steps.set(m.step, s);
        }
        if (m.reasoning_content && m.reasoning_content.trim() !== '') {
            s.reasoning_content += (s.reasoning_content ? '\n\n' : '') + m.reasoning_content;
        }
        if (!m.tool_calls && typeof m.content === 'string' && m.content.trim() !== '') {
            s.content += (s.content ? '\n\n' : '') + m.content;
        }
        if (Array.isArray(m.tool_calls) && m.tool_calls.length > 0) {
            s.tool_calls = m.tool_calls;
            s.modules = m.modules ?? [];
        }
        // status: the backend stamps step_status on every yielded segment;
        // a step with tools takes the tool segment's status (running ->
        // done/failed as responses land), a tool-less step stays thinking
        s.status = (s.tool_calls.length > 0)
            ? (m.step_status ?? (s.status === 'thinking' ? 'running' : s.status))
            : (m.step_status ?? s.status);
        s._tail = m;
    }
    return Array.from(steps.values());
}

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
// one-line arg summary for a COMPLETED tool call header: the single most
// informative argument, value only (no key), eg. "Coder: file edit
// (toolcalls.css)". paths keep their TAIL (the interesting end).
const ARG_PRIORITY = [
    'path', 'file_path', 'filepath', 'file', 'filename', 'url',
    'query', 'pattern', 'regex_pattern', 'sub_path', 'subfolder',
    'folder', 'id', 'name', 'content', 'text'
];

// keep the end of path-ish strings, the end of everything else
function truncateArg(s) {
    if (s.length <= 70) return s;
    if (s.includes('/') || s.includes('\\')) return '..' + s.slice(-68);
    return s.slice(0, 69).trimEnd() + '..';
}

function argToString(v) {
    if (v !== null && typeof v === 'object') return JSON.stringify(v);
    if (typeof v === 'string') return v;
    return String(v);
}

function toolCallArgsSummary(tool) {
    let args;
    try {
        args = JSON.parse(tool.function?.arguments ?? '{}');
    } catch {
        return '';
    }
    if (!args || typeof args !== 'object' || Array.isArray(args)) return '';
    const entries = Object.entries(args);
    if (entries.length === 0) return '';
    // highest-priority known key wins; otherwise the first string value;
    // otherwise the first value, period
    let chosen = null;
    for (const pk of ARG_PRIORITY) {
        const hit = entries.find(([k]) => k === pk);
        if (hit) { chosen = hit; break; }
    }
    if (!chosen) chosen = entries.find(([, v]) => typeof v === 'string');
    if (!chosen) chosen = entries[0];
    return '(' + truncateArg(argToString(chosen[1])) + ')';
}

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
// while streaming we can't know which content will be the final one:
// content only counts as final while it is the most recent segment. if a
// reasoning/toolcall segment arrives afterwards, it gets pulled back into
// the chain automatically
function streamTurnSplit(turn) {
    const messages = turn?.messages || [];
    const last = messages[messages.length - 1];

    // empty segments are already filtered out backend-side (group_stream
    // only yields segments with visible content), so no filter here
    if (last && last.type === 'content' && !last.tool_calls) {
        return { chain: messages.slice(0, -1), final: [last] };
    }

    return { chain: messages, final: [] };
}
