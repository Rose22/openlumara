// ============================================================
// OPTIMIZED getTurns() — version 2
// Changes: versioned caching, streaming-only append, pre-filtering
// ============================================================

// Version counter stored on the chat store instance
// Incremented whenever messages or stream tokens change

const DEBUG_TURNS = false;

function getTurns(instance) {
    /*
     * this absolute black magic, ported over from the old webUI,
     * with help from my local AI (not vibecoded, but i needed help for this because this is really hard!),
     * emits an array of messages where every message
     * inbetween the latest user message,
     * is grouped into one assistant turn.
     *
     * this makes it disgetplay just like in the old webUI,
     * but using alpine's reactivity and none of the horrible DOM injection hackiness
     * that the AI decided to vibecode back then
     *
     * if anyone wants to know, i used Qwen3.6 35B for this, at Q6_K_M quant.
     * i barely use cloud AI anymore for coding help,
     * and in fact, when i use AI to help coding on openlumara,
     * i use openlumara itself for it :)
     */
    const stream = Alpine.store('stream');
    const messages = instance.messages;

    // --- STEP 1: Compute history hash (messages only, no tokens) ---
    let msgHash = messages.length;
    for (let i = 0; i < messages.length; i++) {
        const m = messages[i];
        msgHash += m.index;
        const content = typeof m.content === 'string' ? m.content : '';
        for (let c = Math.max(0, content.length - 50); c < content.length; c++) {
            msgHash += content.charCodeAt(c) * (i + 1);
        }
    }
    const historyHash = `${msgHash}`;

    // --- STEP 2: Compute streaming hash (tokens only) ---
    let tokenHash = stream.tokens.length;
    for (let i = 0; i < stream.tokens.length; i++) {
        const t = stream.tokens[i];
        tokenHash += t.type.charCodeAt(0);
        const content = t.content || '';
        for (let c = Math.max(0, content.length - 30); c < content.length; c++) {
            tokenHash += content.charCodeAt(c) * (i + 1);
        }
    }
    const streamingHash = `${tokenHash}-${stream.state}`;

    // --- STEP 3: Build/rebuild history turns (only when messages change) ---
    let historyTurns = instance._historyTurns;
    if (historyHash !== instance._historyTurnsHash) {
        historyTurns = buildHistoryTurns(messages);
        instance._historyTurns = historyTurns;
        instance._historyTurnsHash = historyHash;

        if (DEBUG_TURNS) {
            console.log(
                `%c[getTurns] History rebuilt — ${historyTurns.length} turns`,
                'color: #4af; font-weight: bold'
            );
        }
    }

    // --- STEP 4: Build/rebuild streaming turn (only when tokens change) ---
    let streamingTurn = instance._streamingTurn;
    if (streamingHash !== instance._streamingTurnHash) {
        streamingTurn = buildStreamingTurn(stream);
        instance._streamingTurn = streamingTurn;
        instance._streamingTurnHash = streamingHash;

        if (DEBUG_TURNS) {
            console.log(
                `%c[getTurns] Streaming turn rebuilt — ${streamingTurn ? streamingTurn.messages.length : 0} segments`,
                'color: #f90; font-weight: bold'
            );
        }
    }

    // --- STEP 5: Combine ---
    const turns = streamingTurn
        ? [...historyTurns, streamingTurn]
        : historyTurns;

    return turns;
}

// ============================================================
// buildHistoryTurns(messages) — extracts and groups ALL non-streaming messages
// Returns: array of turn objects (user + assistant)
// ============================================================
function buildHistoryTurns(messages) {
    const turns = [];
    let currentAssistantTurn = null;

    for (const msg of messages) {
        if (msg.role === 'user') {
            if (currentAssistantTurn) {
                turns.push(currentAssistantTurn);
                currentAssistantTurn = null;
            }
            turns.push({
                role: "user",
                messages: [Object.assign({}, msg)]
            });
        } else {
            if (!currentAssistantTurn) {
                currentAssistantTurn = {
                    role: "assistant",
                    index: msg.index,
                    messages: []
                };
            }

            msg.type = msg.tool_calls ? "tool_calls" : 'history';

            // Tool responses get merged, not displayed as separate messages
            if (msg.role === 'tool') {
                if (!currentAssistantTurn._toolResponses) {
                    currentAssistantTurn._toolResponses = {};
                }
                currentAssistantTurn._toolResponses[msg.tool_call_id] = msg.content;
                continue;
            }

            currentAssistantTurn.messages.push(msg);
        }
    }
    if (currentAssistantTurn) {
        // Merge tool responses into tool calls
        if (currentAssistantTurn._toolResponses) {
            for (const msg of currentAssistantTurn.messages) {
                if (msg.tool_calls) {
                    for (const tool of msg.tool_calls) {
                        if (currentAssistantTurn._toolResponses[tool.id]) {
                            tool.response = currentAssistantTurn._toolResponses[tool.id];
                        }
                    }
                }
            }
        }
        delete currentAssistantTurn._toolResponses;
        turns.push(currentAssistantTurn);
    }

    return turns;
}

// ============================================================
// buildStreamingTurn(stream) — builds ONLY the current streaming turn
// Returns: a single turn object, or null if idle
// ============================================================
function buildStreamingTurn(stream) {
    if (stream.state === 'idle' || stream.tokens.length === 0) {
        return null;
    }

    const segments = [];
    let lastSegmentType = null;

    for (const token of stream.tokens) {
        if (token.type === 'prompt_progress' ||
            token.type === 'token_usage' ||
            token.type === 'timings') {
            continue;
        }

        let segmentType = token.type;
        if (token.type === 'tool_call_delta' || token.type === 'tool_calls') {
            segmentType = 'tool_calls';
        }

        const lastMsg = segments[segments.length - 1];
        const isNewSegment = segmentType !== lastSegmentType ||
            (segmentType === 'tool' && lastMsg && lastMsg.tool_call_id !== token.tool_call_id);

        if (isNewSegment) {
            const newMsg = { role: "assistant", pending: true };
            if (segmentType === 'reasoning') {
                newMsg.type = "reasoning";
                newMsg.reasoning_content = token.content || '';
            } else if (segmentType === 'content') {
                newMsg.type = "content";
                newMsg.content = token.content || '';
            } else if (segmentType === 'tool_calls') {
                newMsg.type = "tool_calls";
                newMsg.tool_calls = token.tool_calls || [];
            } else if (segmentType === 'tool_call_delta') {
                newMsg.type = "tool_call_delta";
                newMsg.tool_calls = token.tool_calls || [];
            } else if (segmentType === 'tool') {
                newMsg.role = "tool";
                newMsg.type = "tool_response";
                newMsg.content = token.content || '';
                newMsg.tool_call_id = token.tool_call_id || '';
            }
            segments.push(newMsg);
            lastSegmentType = segmentType;
        } else {
            if (lastMsg) {
                if (segmentType === 'tool_calls' || segmentType === 'tool_call_delta') {
                    if (token.tool_calls) lastMsg.tool_calls = token.tool_calls;
                } else if (segmentType === 'tool') {
                    lastMsg.content += (token.content || '');
                } else if (segmentType === 'reasoning') {
                    lastMsg.reasoning_content += (token.content || '');
                } else {
                    lastMsg.content += (token.content || '');
                }
            }
        }
    }

    if (segments.length === 0) return null;

    // Merge tool responses
    const responseMap = {};
    for (const msg of segments) {
        if (msg.type === 'tool_response') responseMap[msg.tool_call_id] = msg.content;
    }
    const displaySegments = segments.filter(s => s.type !== 'tool_response');
    for (const msg of displaySegments) {
        if (msg.tool_calls) {
            for (const tool of msg.tool_calls) {
                if (responseMap[tool.id]) tool.response = responseMap[tool.id];
            }
        }
    }

    return {
        role: "assistant",
        messages: displaySegments,
        index: stream.userMessageIndex + 1
    };
}

function streamedTokensToMessages(tokens) {
    const messages = [];
    let current = null;

    for (const token of tokens) {
        if (token.type === 'prompt_progress' || token.type === 'token_usage' || token.type === 'timings') {
            continue;
        }

        // Tool responses are separate messages with role 'tool'
        if (token.type === 'tool') {
            if (current) {
                messages.push(current);
                current = null;
            }
            messages.push({
                ...token,
                role: "tool",
                type: "tool_response",
                content: token.content || ''
            });
            continue;
        }

        if (!current) {
            current = { ...token, role: "assistant", content: '', reasoning_content: '' };
        }

        if (token.type === 'reasoning') {
            current.type = "reasoning";
            current.reasoning_content += (token.content || '');
        } else if (token.type === 'content') {
            current.type = "content";
            current.content += (token.content || '');
        } else if (token.type === 'tool_call_delta' || token.type === 'tool_calls') {
            current.type = "tool_calls";
            current.tool_calls = token.tool_calls || [];
        }
    }

    if (current && (current.content || current.reasoning_content || (current.tool_calls && current.tool_calls.length > 0))) {
        messages.push(current);
    }

    return messages;
}
