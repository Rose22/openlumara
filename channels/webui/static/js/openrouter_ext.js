/* openrouter-ext */
// Patches the message rendering to append OpenRouter token and cost stats

(function() {
    // Save original render functions
    const originalRenderAssistantMessageParts = window.renderAssistantMessageParts;

    // Patch renderAssistantMessageParts to append stats if _usage is present
    if (originalRenderAssistantMessageParts) {
        window.renderAssistantMessageParts = function(msg, toolResponseMap) {
            let html = originalRenderAssistantMessageParts(msg, toolResponseMap);

            // Append stats if _usage is attached to the message
            if (msg._usage) {
                const u = msg._usage;
                let statText = `↑${u.prompt || 0} ↓${u.completion || 0} tok`;
                if (u.cost !== undefined && u.cost !== null) {
                    // Format to at least 4 decimal places, or 6 if very small
                    let costStr = u.cost.toFixed(6).replace(/0+$/, '');
                    if (costStr.endsWith('.')) costStr += '00';
                    statText += ` · $${costStr}`;
                }

                // Add a small span after message content with stats
                html += `<div class="msg-stats or-stats" style="opacity: 0.55; font-size: 0.78em; font-family: monospace; margin-top: 6px; text-align: right;">${statText}</div>`;

                // Update session total if possible
                updateSessionTotal(u.session_cost, u.session_tokens);
            }
            return html;
        };
    }

    function updateSessionTotal(cost, tokens) {
        // Find existing status bar or token display element
        let tokenCountEl = document.getElementById('token-usage-text');
        if (tokenCountEl) {
            let orTotalEl = document.getElementById('or-total');
            if (!orTotalEl) {
                orTotalEl = document.createElement('span');
                orTotalEl.id = 'or-total';
                orTotalEl.style.marginLeft = '10px';
                orTotalEl.style.opacity = '0.7';
                tokenCountEl.parentNode.insertBefore(orTotalEl, tokenCountEl.nextSibling);
            }
            if (cost !== undefined && cost !== null) {
                let costStr = cost.toFixed(4);
                orTotalEl.textContent = `| Session Cost: $${costStr}`;
            }
        }
    }

    // Since we patched webui.py to yield {"_meta": {"type": "usage", "usage": {...}}}
    // We can intercept fetch calls to intercept stream processing, OR patch parseMessageContent / finalizeAllContent
    // Given we just need to append the stats to the DOM, let's observe the window object or replace JSON.parse locally if needed,
    // actually, `finalizeStreamingUI` or `renderAllMessages` gets called at the end of stream.
    // The SSE parser already handles unknown _meta events gracefully. It just ignores it unless we hook it.

    // Let's patch JSON.parse temporarily during stream to catch our usage event?
    const originalParse = JSON.parse;
    window.JSON.parse = function(text, reviver) {
        try {
            const data = originalParse(text, reviver);
            if (data && data._meta && data._meta.type === 'usage' && data.usage) {
                // We caught the usage event!
                const u = data.usage;
                let statText = `↑${u.prompt || 0} ↓${u.completion || 0} tok`;
                if (u.cost !== undefined && u.cost !== null) {
                    let costStr = u.cost.toFixed(6).replace(/0+$/, '');
                    if (costStr.endsWith('.')) costStr += '00';
                    statText += ` · $${costStr}`;
                }

                // Find the last .message.ai element and append it
                setTimeout(() => {
                    const aiMsgs = document.querySelectorAll('.message.ai');
                    if (aiMsgs.length > 0) {
                        const lastAiMsg = aiMsgs[aiMsgs.length - 1];
                        // don't append if it already has .or-stats
                        if (!lastAiMsg.querySelector('.or-stats')) {
                            const statDiv = document.createElement('div');
                            statDiv.className = "msg-stats or-stats";
                            statDiv.style = "opacity: 0.55; font-size: 0.78em; font-family: monospace; margin-top: 6px; text-align: right;";
                            statDiv.textContent = statText;
                            lastAiMsg.appendChild(statDiv);
                        }
                    }
                    updateSessionTotal(u.session_cost, u.session_tokens);
                }, 100); // give it a little time to finish rendering
            }
            return data;
        } catch (e) {
            // If the original parse fails, throw the error as usual
            throw e;
        }
    };

})();
