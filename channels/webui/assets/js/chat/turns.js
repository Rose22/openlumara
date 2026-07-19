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

    // 1. Group all finalized messages from history
    const turns = [];
    let currentAssistantTurn = null;

    for (const msg of instance.messages) {
        if (msg.role === 'user') {
            if (currentAssistantTurn) {
                turns.push(currentAssistantTurn);
                currentAssistantTurn = null;
            }
            turns.push({
                role: "user",
                messages: [{"role": "user", "content": msg.content}]
            });
        } else {
            if (!currentAssistantTurn) {
                currentAssistantTurn = {
                    role: "assistant",
                    messages: []
                };
            }

            // normalize historical messages to include a type property
            // so that it works both when not streaming and when streaming
            if (msg.tool_calls) {
                msg.type = "tool_calls"
            } else {
                msg.type = 'history';
            }
            currentAssistantTurn.messages.push(msg);
        }
    }
    if (currentAssistantTurn) turns.push(currentAssistantTurn);

    // Merge tool responses into their tool calls
    for (const turn of turns) {
        if (turn.role !== 'assistant') continue;
        const responseMap = {};
        for (const msg of turn.messages) {
            if (msg.role === 'tool') responseMap[msg.tool_call_id] = msg.content;
        }
        for (const msg of turn.messages) {
            if (msg.tool_calls) {
                for (const tool of msg.tool_calls) {
                    if (responseMap[tool.id]) tool.response = responseMap[tool.id];
                }
            }
        }
    }

    // 2. Reconstruct streaming turn from token segments
    /*
     * this is the part that handles streaming tokens...
     * absolute black magic if you ask me
     */
    const stream = Alpine.store('stream');
    if (
        stream.state != 'idle'
        && stream.tokens
        && stream.tokens.length > 0
    ) {
        const segments = [];
        let lastSegmentType = null;

        for (const token of stream.tokens) {
            // Skip non-display tokens
            if (token.type === 'prompt_progress' || token.type === 'token_usage' || token.type === 'timings') {
                continue;
            }

            // Skip tokens with no actual content (prevents blank segments)
            if (token.type === 'reasoning' && (!token.content || token.content.trim() === '')) {
                continue;
            }

            let segmentType = token.type;
            // Normalize tool call types into a single segment type
            if (token.type === 'tool_call_delta' || token.type === 'tool_calls') {
                segmentType = 'tool_calls';
            }

            const lastMsg = segments[segments.length - 1];
            if (segmentType !== lastSegmentType || (segmentType === 'tool' && lastMsg && lastMsg.tool_call_id !== token.tool_call_id)) {
                // New segment type: start a fresh message
                if (segmentType === 'reasoning') {
                    segments.push({
                        role: "assistant",
                        type: "reasoning",
                        reasoning_content: token.content || '',
                        pending: true
                    });
                } else if (segmentType === 'content') {
                    segments.push({
                        role: "assistant",
                        type: "content",
                        content: token.content || '',
                        pending: true
                    });
                } else if (segmentType === 'tool_calls') {
                    segments.push({
                        role: "assistant",
                        type: "tool_calls",
                        tool_calls: token.tool_calls || [],
                        pending: true
                    });
                } else if (segmentType === 'tool_call_delta') {
                    segments.push({
                        role: "assistant",
                        type: "tool_call_delta",
                        tool_calls: token.tool_calls || [],
                        pending: true
                    });
                } else if (segmentType === 'tool') {
                    segments.push({
                        role: "tool",
                        type: "tool_response",
                        content: token.content || '',
                        tool_call_id: token.tool_call_id || '',
                        pending: true
                    });
                }

                lastSegmentType = segmentType;
            } else {
                // Same segment type: append to the last message
                if (lastMsg) {
                    if (segmentType === 'tool_calls') {
                        if (token.tool_calls) {
                            lastMsg.tool_calls = token.tool_calls;  // replace with accumulated
                        }
                    } else if (segmentType === 'tool') {
                        lastMsg.content += (token.content || '');
                    } else {
                        if (segmentType === 'reasoning') {
                            lastMsg.reasoning_content += (token.content || '');
                        } else {
                            lastMsg.content += (token.content || '');
                        }
                    }
                }
            }
        }

        if (segments.length > 0) {
            // merge tool responses with their toolcalls, even during streaming!
            const responseMap = {};
            for (const msg of segments) {
                if (msg.type === 'tool_response') responseMap[msg.tool_call_id] = msg.content;
            }

            /*
             * filter out the raw tool responses so we don't display raw
             * json when the fancy json mapping exists
             */
            const displaySegments = segments.filter(s => s.type !== 'tool_response');

            // and merge the responsemap into the tool_calls
            for (const msg of segments) {
                if (msg.tool_calls) {
                    for (const tool of msg.tool_calls) {
                        if (responseMap[tool.id]) tool.response = responseMap[tool.id];
                    }
                }
            }

            turns.push({
                role: "assistant",
                messages: segments
            });
        }
    }

    return turns;

    /*
     * you can really see the difference between my comments and the AI's, huh?
     * well good, i want to keep it that way, so that it's obvious which parts
     * have been tainted by AI, and which haven't
     */
}
