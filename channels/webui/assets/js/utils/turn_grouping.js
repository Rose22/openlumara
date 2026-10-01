/*
 * -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
 * splits assistant turns into a collapsible "agent chain" (reasoning, tool
 * calls and intermediate content) and the final content that renders outside
 * of the wrapper.
 */

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
// a final content message is assistant content with no tool calls attached
function isFinalContentMessage(message) {
    return (
        message.role === 'assistant' &&
        !message.tool_calls &&
        typeof message.content === 'string' &&
        message.content.trim() !== ''
    );
}

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
// messages that render nothing at all (empty content segments, empty
// reasoning) would become ghost stations on the timeline: invisible body
// with a node dot. they get filtered out of the chain entirely.
function hasVisibleChainContent(message) {
    // tool calls: needs an actual non-empty array (the template loops over
    // message.tool_calls; an empty/missing array renders nothing)
    if (message.tool_calls || message.type === 'tool_calls' || message.type === 'tool_call_delta') {
        return Array.isArray(message.tool_calls) && message.tool_calls.length > 0;
    }
    if (message.reasoning_content && message.reasoning_content.trim() !== '') return true;
    // content only renders for assistant messages (see assistant_history.html);
    // tool-result / system messages with string content would be ghost stations
    if (message.role === 'assistant' && typeof message.content === 'string' && message.content.trim() !== '') return true;
    return false;
}

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
// for finalized history: the last content-without-toolcalls message of the
// turn is the final answer, everything before it is chain
function historyTurnSplit(turn) {
    const messages = turn?.messages || [];

    let finalIndex = -1;
    for (let i = messages.length - 1; i >= 0; i--) {
        if (isFinalContentMessage(messages[i])) {
            finalIndex = i;
            break;
        }
    }

    const chain = [];
    const final = [];
    messages.forEach((message, i) => {
        if (i === finalIndex) {
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
            // the final answer often carries its reasoning on the same
            // object: split it into a chain message so it renders as a
            // "Thoughts" step INSIDE the chain, matching streaming (copies,
            // never mutate stored messages)
            if (message.reasoning_content && message.reasoning_content.trim() !== '') {
                const chainCopy = { ...message, content: '' };
                const finalCopy = { ...message };
                // delete rather than blank: the history template gates the
                // reasoning block on Object.hasOwn(), so an empty-string
                // value would still render an empty Thoughts block
                delete finalCopy.reasoning_content;
                chain.push(chainCopy);
                final.push(finalCopy);
            } else {
                final.push(message);
            }
        }
        else if (hasVisibleChainContent(message)) chain.push(message);
    });

    return { chain, final };
}

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
// a tool call failed when its parsed response is {status: "error", ..}
function toolCallFailed(tool) {
    try {
        const p = JSON.parse(tool.response);
        return p !== null && typeof p === 'object' && p.status === 'error';
    } catch {
        return false;
    }
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

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-17)
// short human label for a chain segment, shown in parentheses on the
// collapsed Process header (what is the agent busy with right now?)
function chainItemLabel(message) {
    if (Array.isArray(message.tool_calls) && message.tool_calls.length > 0) {
        const fn = message.tool_calls[message.tool_calls.length - 1].function?.name;
        if (fn) {
            const parts = fn.split('_');
            return parts[0].replace(/^\w/, c => c.toUpperCase()) + ': ' + parts.slice(1).join(' ');
        }
    }
    if (message.reasoning_content && message.reasoning_content.trim() !== '') return 'Thinking..';
    if (message.role === 'assistant' && typeof message.content === 'string' && message.content.trim() !== '') {
        // content segments: the ai is putting words together, not reasoning -
        // 'writing' reads better than a raw snippet here
        return 'writing';
    }
    return '';
}

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-26)
// groups a chain into render items so reasoning + its tool calls share ONE
// collapsible header instead of stacking two. history messages carry both
// fields on a single object; streaming delivers them as adjacent segments,
// which get folded into a merged item referencing the tool_calls segment
// (_tail) so the block knows when it's still the live one.
function chainDisplay(chain) {
    const out = [];
    let step = 0;
    let i = 0;
    while (i < chain.length) {
        const m = chain[i];
        const hasTools = Array.isArray(m.tool_calls) && m.tool_calls.length > 0;

        if (hasTools) {
            // history shape: one message carrying tool calls (reasoning
            // and/or intermediate content optional on the same object)
            out.push({ _combined: true, _step: ++step, reasoning_content: m.reasoning_content ?? '', content: m.content ?? '', tool_calls: m.tool_calls, _tail: m });
            i++;
            continue;
        }

        // stream shape: consecutive reasoning/content segments that lead to
        // a tool_calls segment fold into that step; if no tool call follows
        // (pure thinking or standalone content), they render as-is
        const isThoughtSeg = (x) => !!x && !Array.isArray(x.tool_calls) &&
            ((!!x.reasoning_content && x.reasoning_content.trim() !== '') ||
             (typeof x.content === 'string' && x.content.trim() !== ''));
        let j = i;
        while (j < chain.length && isThoughtSeg(chain[j])) j++;
        const toolSeg = (j > i && j < chain.length && Array.isArray(chain[j].tool_calls) && chain[j].tool_calls.length > 0) ? chain[j] : null;
        if (toolSeg) {
            let reasoning = '', content = '';
            for (let k = i; k < j; k++) {
                if (chain[k].reasoning_content) reasoning += (reasoning ? '\n\n' : '') + chain[k].reasoning_content;
                if (chain[k].content) content += (content ? '\n\n' : '') + chain[k].content;
            }
            out.push({ _combined: true, _step: ++step, reasoning_content: reasoning, content: content, tool_calls: toolSeg.tool_calls, _tail: toolSeg });
            i = j + 1;
        } else if (j === chain.length) {
            // -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
            // thought run at the END of the chain with no tool call yet:
            // render as a provisional step (empty tool_calls) so streaming
            // reasoning appears AS a step from the start. when the tool
            // call segment lands it folds into this same step via the
            // branch above - same index, so Alpine keeps the DOM and the
            // step number never jumps
            let reasoning = '', content = '';
            for (let k = i; k < j; k++) {
                if (chain[k].reasoning_content) reasoning += (reasoning ? '\n\n' : '') + chain[k].reasoning_content;
                if (chain[k].content) content += (content ? '\n\n' : '') + chain[k].content;
            }
            out.push({ _combined: true, _step: ++step, reasoning_content: reasoning, content: content, tool_calls: [], _tail: chain[j - 1] });
            i = j;
        } else {
            out.push(m);
            i++;
        }
    }
    return out;
}

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
// deduped, prettified tool names for the step header, GROUPED by module
// (first token): "Coder: glob, file read · Memory: create, search" -
// actions within a module are comma-joined, modules separated by the same
// · the tool result summaries use. one entry per function no matter how
// many times it was called, order of first appearance kept for both
// groups and actions within a group.
function stepToolNames(tool_calls) {
    const seen = new Set();
    const groups = new Map();
    for (const t of tool_calls ?? []) {
        const fn = t.function?.name;
        if (!fn || seen.has(fn)) continue;
        seen.add(fn);
        const parts = fn.split('_');
        const module = parts[0].replace(/^\w/, c => c.toUpperCase());
        const action = parts.slice(1).join(' ');
        if (!groups.has(module)) groups.set(module, []);
        groups.get(module).push(action);
    }
    const names = [];
    for (const [module, actions] of groups) {
        // single-token tool names have no action part: no trailing colon
        names.push(actions.length > 0 && actions[0] !== '' ? module + ': ' + actions.join(', ') : module);
    }
    return names.join(' · ');
}

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-10-01)
// html variant of stepToolNames for the step header: module names wrapped
// in a bold span (mirrors .module in the tool call headers). safe to feed
// to x-html - tokens are split on '_' from function names, so they can
// only contain letters/digits/underscores; spaces are inserted by us.
function stepToolNamesHtml(tool_calls) {
    // count per function so repeated calls can show an xN badge
    const counts = new Map();
    const order = [];
    for (const t of tool_calls ?? []) {
        const fn = t.function?.name;
        if (!fn) continue;
        if (!counts.has(fn)) { counts.set(fn, 0); order.push(fn); }
        counts.set(fn, counts.get(fn) + 1);
    }
    const groups = new Map();
    for (const fn of order) {
        const parts = fn.split('_');
        const module = parts[0].replace(/^\w/, c => c.toUpperCase());
        // sanitize FIRST, then wrap the badge: nothing user-derived ever
        // touches the markup
        const action = parts.slice(1).join(' ').replace(/[^\w ]/g, '');
        const repeat = counts.get(fn) > 1 ? ' <span class="tool-repeat">x' + counts.get(fn) + '</span>' : '';
        if (!groups.has(module)) groups.set(module, []);
        groups.get(module).push({ action, repeat });
    }
    const names = [];
    for (const [module, actions] of groups) {
        const safe = module.replace(/[^\w]/g, '');
        const actionText = actions.map(a => a.action + a.repeat).join(', ');
        const hasAction = actions.some(a => a.action !== '');
        names.push(hasAction
            ? '<span class="tool-module">' + safe + ':</span> ' + actionText
            : '<span class="tool-module">' + safe + '</span>');
    }
    return names.join(' · ');
}

// -- AI GENERATED CODE (Qwen3.8-Flash-Next) :: (2026-09-16)
// while streaming we can't know which content will be the final one:
// content only counts as final while it is the most recent segment. if a
// reasoning/toolcall segment arrives afterwards, it gets pulled back into
// the chain automatically
function streamTurnSplit(turn) {
    const messages = turn?.messages || [];
    const last = messages[messages.length - 1];

    if (last && last.type === 'content' && !last.tool_calls) {
        return { chain: messages.slice(0, -1).filter(hasVisibleChainContent), final: [last] };
    }

    return { chain: messages.filter(hasVisibleChainContent), final: [] };
}
