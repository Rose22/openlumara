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
        if (i === finalIndex) final.push(message);
        else if (hasVisibleChainContent(message)) chain.push(message);
    });

    return { chain, final };
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
