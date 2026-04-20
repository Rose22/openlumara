// =============================================================================
// Message Rendering - OpenAI-Compliant
// =============================================================================

/**
 * Render all messages with proper turn handling.
 */
function renderAllMessages(messages, animate = false) {
    const wrappers = chat.querySelectorAll('.message-wrapper');
    wrappers.forEach(wrapper => wrapper.remove());

    if (!messages || messages.length === 0) {
        lastMessageIndex = 0;
        return;
    }

    let i = 0;
    while (i < messages.length) {
        const msg = messages[i];

        if (msg.role === 'assistant') {
            // Collect complete assistant turn (may span multiple messages due to tool calls)
            const turnInfo = collectAssistantTurn(messages, i);
            renderAssistantTurn(turnInfo.messages, turnInfo.endIndex, animate);
            i = turnInfo.endIndex + 1;
        } else {
            // Single message (user, tool, command, etc.)
            renderSingleMessage(msg, i, animate);
            i++;
        }
    }

    lastMessageIndex = messages.length;
    scrollToBottom();
}

/**
 * Collect a complete assistant turn including all tool calls and responses.
 * Returns all messages that should be rendered together.
 */
function collectAssistantTurn(messages, startIndex) {
    const collected = [];
    let i = startIndex;
    let endIndex = startIndex;

    while (i < messages.length) {
        const msg = messages[i];

        if (msg.role === 'assistant') {
            collected.push(msg);
            endIndex = i;

            // If this assistant has tool_calls, look for tool responses
            if (msg.tool_calls && msg.tool_calls.length > 0) {
                i++;
                // Collect following tool responses
                while (i < messages.length && messages[i].role === 'tool') {
                    collected.push(messages[i]);
                    endIndex = i;
                    i++;
                }
                // If there's another assistant message after, it's part of this turn
                // (the AI's response after processing tools)
            } else {
                // No tool calls - end of this assistant's turn
                i++;
                break;
            }
        } else if (msg.role === 'tool' && i === startIndex) {
            // Orphaned tool response at start - collect and look for next assistant
            collected.push(msg);
            endIndex = i;
            i++;
        } else {
            // Different role - end of assistant turn
            break;
        }
    }

    return { messages: collected, endIndex };
}

/**
 * Render an assistant turn (one or more assistant messages with tool calls).
 */
function renderAssistantTurn(messages, index, animate) {
    if (!messages || messages.length === 0) return;

    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper ai';
    if (animate) wrapper.classList.add('animate-in');
    wrapper.setAttribute('role', 'article');
    wrapper.dataset.index = index;

    const msgDiv = document.createElement('div');
    msgDiv.className = 'message ai';

    // Build tool response lookup map
    const toolResponseMap = new Map();
    for (const msg of messages) {
        if (msg.role === 'tool' && msg.tool_call_id) {
            toolResponseMap.set(msg.tool_call_id, msg);
        }
    }

    // Render each assistant message in order
    let html = '';
    for (const msg of messages) {
        if (msg.role === 'assistant') {
            html += renderAssistantMessageParts(msg, toolResponseMap);
        }
    }

    // Collect all tool calls that didn't have responses yet (edge case)
    const allToolCalls = [];
    for (const msg of messages) {
        if (msg.role === 'assistant' && msg.tool_calls) {
            for (const tc of msg.tool_calls) {
                if (!toolResponseMap.has(tc.id)) {
                    allToolCalls.push({ call: tc, response: null });
                }
            }
        }
    }
    if (allToolCalls.length > 0) {
        html += renderToolCallsWithResponses(allToolCalls);
    }

    msgDiv.innerHTML = html;
    highlightCode(msgDiv);

    // Timestamp
    const ts = document.createElement('span');
    ts.className = 'timestamp timestamp-left';
    ts.textContent = formatTime();
    ts.innerHTML += ` <span class="index-badge">#${index}</span>`;
    msgDiv.appendChild(ts);

    wrapper.appendChild(msgDiv);

    // Get combined content for action buttons
    const combinedContent = messages
    .filter(m => m.role === 'assistant' && m.content)
    .map(m => m.content)
    .join('');

    const actions = createActionButtons('assistant', index, combinedContent);
    wrapper.appendChild(actions);

    chat.insertBefore(wrapper, typing);
}

/**
 * Render parts of a single assistant message in OpenAI order:
 * 1. reasoning_content (if present)
 * 2. content (if present)
 * 3. tool_calls with responses (if present)
 */
function renderAssistantMessageParts(msg, toolResponseMap) {
    let html = '';

    // 1. Reasoning first
    if (msg.reasoning_content) {
        const expandByDefault = localStorage.getItem('reasoningExpandedByDefault') === 'true';
        html += renderReasoningBlock(msg.reasoning_content, !expandByDefault, 'Thoughts');
    }

    // 2. Content second
    if (msg.content) {
        html += `<div class="message-content-container">${renderMarkdown(msg.content)}</div>`;
    }

    // 3. Tool calls with their responses third
    if (msg.tool_calls && msg.tool_calls.length > 0) {
        const toolCallsData = msg.tool_calls.map(tc => ({
            call: tc,
            response: toolResponseMap.get(tc.id) || null
        }));
        html += renderToolCallsWithResponses(toolCallsData);
    }

    return html;
}

/**
 * Render a single message (non-assistant).
 */
function renderSingleMessage(msg, index, animate) {
    const role = msg.role || 'user';
    const rawContent = msg.content || '';
    const rawText = extractTextContent(rawContent);
    const parsed = parseMessageContent(rawContent);

    if (rawText === '[SYSTEM_TICK]') return;

    let wrapperClass, msgClass;
    if (parsed.isAnnouncement) {
        wrapperClass = 'announce';
        msgClass = `announce ${parsed.type}`;
    } else if (parsed.isCommandOutput) {
        wrapperClass = 'command_response';
        msgClass = 'command_response';
    } else if (role === 'user') {
        wrapperClass = rawText.trim().startsWith('/') ? 'user_command' : 'user';
        msgClass = wrapperClass;
    } else if (role === 'tool') {
        // Orphaned tool message
        wrapperClass = 'ai';
        msgClass = 'ai';
    } else {
        wrapperClass = 'ai';
        msgClass = 'ai';
    }

    const wrapper = document.createElement('div');
    wrapper.className = `message-wrapper ${wrapperClass}`;
    if (animate) wrapper.classList.add('animate-in');
    wrapper.setAttribute('role', 'article');
    wrapper.dataset.index = index;

    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${msgClass}`;

    let messageHtml = '';
    if (parsed.isAnnouncement) {
        messageHtml = escapeHtml(parsed.displayContent);
    } else if (parsed.isCommandOutput) {
        messageHtml = `<pre>${escapeHtml(parsed.displayContent)}</pre>`;
    } else if (wrapperClass === 'user_command') {
        messageHtml = `<pre>${escapeHtml(rawText)}</pre>`;
    } else {
        messageHtml = renderContentBody(rawContent);
    }

    msgDiv.innerHTML = messageHtml;

    if (!parsed.isAnnouncement && !parsed.isCommandOutput && wrapperClass !== 'user_command') {
        highlightCode(msgDiv);
    }

    const ts = document.createElement('span');
    ts.className = 'timestamp';
    ts.classList.add(wrapperClass === 'user' || wrapperClass === 'user_command' ? 'timestamp-right' : 'timestamp-left');
    ts.textContent = msg.timestamp || formatTime();
    ts.innerHTML += ` <span class="index-badge">#${index}</span>`;
    msgDiv.appendChild(ts);

    wrapper.appendChild(msgDiv);

    if (role === 'user' || role === 'assistant') {
        const actions = createActionButtons(role, index, rawText);
        wrapper.appendChild(actions);
    }

    chat.insertBefore(wrapper, typing);
}

/**
 * Render tool calls with their responses.
 */
function renderToolCallsWithResponses(toolCallsData) {
    if (!toolCallsData || toolCallsData.length === 0) return '';

    let html = '<div class="tool-calls-container">';

    for (const tcData of toolCallsData) {
        const call = tcData.call;
        const response = tcData.response;

        const func = call.function || call;
        const toolName = func.name || 'Unknown Tool';
        const argsRaw = func.arguments || '{}';
        const callId = call.id || `tool-${Date.now()}`;

        let args = {};
        try {
            args = typeof argsRaw === 'string' ? JSON.parse(argsRaw) : argsRaw;
        } catch (e) {
            args = { raw: argsRaw };
        }

        const argEntries = Object.entries(args);
        let headerExtraHtml = '';

        if (argEntries.length === 1) {
            const [argName, argValue] = argEntries[0];
            let displayValue = typeof argValue === 'object' ? JSON.stringify(argValue) : String(argValue);
            if (displayValue.length > 50) displayValue = displayValue.substring(0, 50) + '...';
            headerExtraHtml = `<span class="tool-call-inline-arg">${escapeHtml(displayValue)}</span>`;
        } else if (argEntries.length > 1) {
            headerExtraHtml = `<span class="tool-call-arg-count">${argEntries.length}</span>`;
        }

        const hasResponse = response !== null;
        const statusClass = hasResponse ? 'completed' : 'pending';
        const statusText = hasResponse ? 'done' : 'calling...';

        html += `
        <div class="tool-call-card collapsed" data-tool-call-id="${escapeHtml(callId)}">
        <div class="tool-call-header" onclick="toggleToolCard(this)">
        <svg class="tool-call-toggle" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="9 18 15 12 9 6"></polyline>
        </svg>
        <svg class="tool-call-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
        </svg>
        <span class="tool-call-name">${escapeHtml(toolName)}</span>
        ${headerExtraHtml}
        <span class="tool-call-status ${statusClass}">${statusText}</span>
        </div>
        <div class="tool-call-body">
        <div class="tool-call-section">
        <div class="tool-call-section-title">Arguments</div>
        <div class="tool-call-args">`;

        if (argEntries.length > 0) {
            for (const [argName, argValue] of argEntries) {
                const displayValue = typeof argValue === 'object' ? JSON.stringify(argValue) : String(argValue);
                html += `
                <div class="tool-call-arg-row">
                <span class="tool-call-arg-name">${escapeHtml(argName)}</span>
                <span class="tool-call-arg-value">${escapeHtml(displayValue)}</span>
                </div>`;
            }
        } else {
            html += `<div class="tool-call-no-args">No arguments</div>`;
        }

        html += `
        </div>
        </div>`;

        if (hasResponse) {
            const responseContent = extractTextContent(response.content);
            html += `
            <div class="tool-call-section tool-response-section">
            <div class="tool-call-section-title">Response</div>
            <div class="tool-response-content">
            ${renderToolResponseContent(responseContent)}
            </div>
            </div>`;
        }

        html += `
        </div>
        </div>`;
    }

    html += '</div>';
    return html;
}

// =============================================================================
// Polling - Updated to use new turn-based rendering
// =============================================================================

async function pollMessages() {
    if (!isConnected) return;
    if (userIsEditing) return;

    try {
        const response = await fetch('/messages/since?index=' + lastMessageIndex, {
            signal: AbortSignal.timeout(CONFIG.POLL_INTERVAL)
        });

        if (!response.ok) {
            if (response.status >= 500) handleConnectionError();
            return;
        }

        const data = await response.json();

        // Check if backend switched chats
        if (data.current_chat_id !== undefined) {
            if (data.current_chat_id !== currentChatId) {
                await restoreCurrentChat();
                await loadChats();
                return;
            }

            if (data.current_chat_title !== undefined) {
                updateChatTitleBar(
                    data.current_chat_title,
                    data.current_chat_tags || []
                );
            }
        }

        const messages = data.messages || [];

        if (messages.length > 0) {
            // Use turn-based rendering for polled messages too
            const turns = groupMessagesIntoTurns(messages);

            for (const turn of turns) {
                // Check if this turn is already rendered
                const existingWrapper = chat.querySelector(
                    `[data-index="${turn.lastIndex}"]`
                );

                if (!existingWrapper) {
                    renderTurn(turn, true);
                }
            }

            lastMessageIndex = data.total;
            scrollToBottom();
            updateTokenUsage();
        }
    } catch (err) {
        // Connection issues handled elsewhere
    }
}

async function syncMessages() {
    try {
        const response = await fetch('/messages');
        const data = await response.json();

        const messages = data.messages || [];

        if (messages.length > 0) {
            renderAllMessages(messages);
            lastMessageIndex = messages[messages.length - 1].index;
            updateTokenUsage();
        } else {
            const wrappers = chat.querySelectorAll('.message-wrapper');
            wrappers.forEach(wrapper => wrapper.remove());
            lastMessageIndex = 0;
        }
    } catch (err) {
        console.error('Failed to sync messages:', err);
    }
}

// =============================================================================
// Content Helpers
// =============================================================================

function extractTextContent(content) {
    if (typeof content === 'string') return content;
    if (Array.isArray(content)) {
        return content
        .map(part => {
            if (part.type === 'text') return part.text;
            if (part.type === 'file') return `File: ${part.filename}`;
            if (part.type === 'image_url') return `[Image]`;
            return '';
        })
        .filter(t => t.trim() !== '')
        .join('\n');
    }
    return '';
}

function parseMessageContent(content) {
    const textContent = extractTextContent(content);

    const systemMatch = textContent.match(/\[System (\w+)\]:\s*/i);

    if (systemMatch) {
        const type = systemMatch[1].toLowerCase();
        const contentStart = systemMatch.index + systemMatch[0].length;

        return {
            type: `announce_${type}`,
            displayContent: textContent.substring(contentStart).trim(),
            isAnnouncement: true
        };
    }

    const cmdMatch = textContent.match(/^\[Command Output\]:\s*/i);
    if (cmdMatch) {
        return {
            type: 'command_response',
            displayContent: textContent.substring(cmdMatch[0].length),
            isCommandOutput: true
        };
    }

    return {
        type: null,
        displayContent: textContent
    };
}

function renderContentBody(content) {
    if (!content) return '';

    if (typeof content === 'string') {
        return renderMarkdown(content);
    }

    const parts = Array.isArray(content) ? content : [content];

    return parts.map(part => {
        if (part.type === 'text') {
            const filePattern = /^\[(File|Image): (.*?)\](\n([\s\S]*))?$/;
            const match = part.text.match(filePattern);

            if (match) {
                const type = match[1];
                const filename = match[2];
                const icon = type === 'File' ? '📄' : '🖼️';

                return `
                <div class="file-preview-container">
                <div class="file-preview">
                <span class="file-icon">${icon}</span>
                <span class="file-name">${escapeHtml(filename)}</span>
                </div>
                </div>`;
            }

            return renderMarkdown(part.text);
        } else if (part.type === 'image_url') {
            const url = part.image_url?.url || '';
            if (url.startsWith('data:image') || url.startsWith('http')) {
                return `
                <div class="uploaded-image-container">
                <img src="${escapeHtml(url)}" class="uploaded-image-preview" alt="Uploaded image">
                </div>`;
            }
            return '';
        }
        return '';
    }).join('');
}

// =============================================================================
// Reasoning Block Rendering
// =============================================================================

function renderReasoningBlock(reasoningContent, isCollapsed = true, label = 'Thinking') {
    if (!reasoningContent) return '';

    const escaped = escapeHtml(reasoningContent);
    const collapsedClass = isCollapsed ? 'collapsed' : 'expanded';

    return `
    <div class="reasoning-wrapper ${collapsedClass}">
    <div class="reasoning-header" onclick="toggleReasoningBlock(this)">
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="24" height="24">
    <path fill="currentColor" d="M256 448c141.4 0 256-93.1 256-208S397.4 32 256 32S0 125.1 0 240c0 45.1 17.7 86.8 47.7 120.9c-1.9 24.5-11.4 46.3-21.4 62.9c-5.5 9.2-11.1 16.6-15.2 21.6c-2.1 2.5-3.7 4.4-4.9 5.7c-.6 .6-1 1.1-1.3 1.4l-.3 .3c0 0 0 0 0 0c0 0 0 0 0 0s0 0 0 0s0 0 0 0c-4.6 4.6-5.9 11.4-3.4 17.4c2.5 6 8.3 9.9 14.8 9.9c28.7 0 57.6-8.9 81.6-19.3c22.9-10 42.4-21.9 54.3-30.6c31.8 11.5 67 17.9 104.1 17.9zM128 208a32 32 0 1 1 0 64 32 32 0 1 1 0-64zm128 0a32 32 0 1 1 0 64 32 32 0 1 1 0-64zm96 32a32 32 0 1 1 64 0 32 32 0 1 1 -64 0z"/>
    </svg>
    <span class="reasoning-text">
    <span class="reasoning-label">${label}</span>
    <span class="reasoning-dots"><span aria-hidden="true">&nbsp;</span><span aria-hidden="true">&nbsp;</span><span aria-hidden="true">&nbsp;</span></span>
    </span>
    <svg class="reasoning-toggle" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <polyline points="6 9 12 15 18 9"></polyline>
    </svg>
    </div>
    <div class="reasoning-block">
    <div class="reasoning-content">${escaped}</div>
    </div>
    </div>`;
}

function toggleReasoningBlock(headerElement) {
    const wrapper = headerElement.closest('.reasoning-wrapper');
    if (wrapper) {
        wrapper.classList.toggle('collapsed');
        wrapper.classList.toggle('expanded');
    }
}

function toggleToolCard(headerElement) {
    const card = headerElement.closest('.tool-call-card');
    if (card) {
        card.classList.toggle('collapsed');
    }
}

// =============================================================================
// Tool Response Rendering
// =============================================================================

function renderToolResponseContent(content) {
    let displayContent = content;
    let isJson = false;
    let parsedData = null;

    try {
        parsedData = JSON.parse(content);
        isJson = true;
    } catch (e) {
        // Not JSON
    }

    if (isJson && parsedData !== null) {
        return renderJsonResponseCompact(parsedData);
    }

    return `<div class="tool-response-string">${escapeHtml(displayContent)}</div>`;
}

function renderJsonResponseCompact(data) {
    if (typeof data === 'string') {
        try {
            const inner = JSON.parse(data);
            return renderJsonResponseCompact(inner);
        } catch (e) {
            return `<div class="tool-response-string">${escapeHtml(data)}</div>`;
        }
    }

    if (Array.isArray(data)) {
        if (data.length === 0) {
            return `<div class="tool-response-empty">Empty array</div>`;
        }

        let html = `<div class="tool-response-header-compact">Array (${data.length} items)</div>`;
        html += `<div class="tool-response-array-compact">`;
        const maxItems = Math.min(data.length, 5);
        for (let i = 0; i < maxItems; i++) {
            const item = data[i];
            html += `<div class="tool-response-item-compact">`;
            html += `<span class="tool-response-item-index">[${i}]</span>`;
            if (typeof item === 'object' && item !== null) {
                html += renderJsonResponseCompact(item);
            } else {
                let strVal = String(item);
                html += `<span class="tool-response-scalar">${escapeHtml(strVal)}</span>`;
            }
            html += `</div>`;
        }
        if (data.length > 5) {
            html += `<div class="tool-response-more">+ ${data.length - 5} more items</div>`;
        }
        html += `</div>`;
        return html;
    }

    if (typeof data === 'object' && data !== null) {
        const entries = Object.entries(data);

        if (entries.length === 0) {
            return `<div class="tool-response-empty">Empty object</div>`;
        }

        let html = `<div class="tool-response-object-compact">`;
        for (const [key, value] of entries) {
            html += `<div class="tool-response-kv-compact">`;
            html += `<span class="tool-response-key">${escapeHtml(key)}</span>`;
            html += `<span class="tool-response-colon">:</span>`;

            if (typeof value === 'object' && value !== null) {
                html += renderJsonResponseCompact(value);
            } else {
                let strVal = String(value);
                html += `<span class="tool-response-scalar">${escapeHtml(strVal)}</span>`;
            }

            html += `</div>`;
        }
        html += `</div>`;
        return html;
    }

    let strVal = String(data);
    return `<span class="tool-response-scalar">${escapeHtml(strVal)}</span>`;
}

// =============================================================================
// Utility Functions
// =============================================================================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatTime() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function createActionButtons(role, index, content, disabled = false) {
    const actions = document.createElement('div');
    actions.className = 'message-actions';

    const copyBtn = document.createElement('button');
    copyBtn.className = 'message-action-btn';
    copyBtn.innerHTML = ICONS.copy;
    copyBtn.setAttribute('aria-label', 'Copy message');
    copyBtn.setAttribute('title', 'Copy');
    copyBtn.disabled = disabled;
    copyBtn.onclick = () => {
        navigator.clipboard.writeText(content).then(() => {
            copyBtn.innerHTML = ICONS.check;
            copyBtn.classList.add('copied');
            setTimeout(() => {
                copyBtn.innerHTML = ICONS.copy;
                copyBtn.classList.remove('copied');
            }, 1500);
        });
    };
    actions.appendChild(copyBtn);

    if (role === 'user') {
        const editBtn = document.createElement('button');
        editBtn.className = 'message-action-btn';
        editBtn.innerHTML = ICONS.edit;
        editBtn.setAttribute('aria-label', 'Edit message');
        editBtn.setAttribute('title', 'Edit');
        editBtn.disabled = disabled;
        editBtn.onclick = () => editMessage(index, content);
        actions.appendChild(editBtn);
    }

    if (role === 'assistant') {
        const regenBtn = document.createElement('button');
        regenBtn.className = 'message-action-btn regenerate';
        regenBtn.innerHTML = ICONS.regenerate;
        regenBtn.setAttribute('aria-label', 'Regenerate response');
        regenBtn.setAttribute('title', 'Regenerate');
        regenBtn.disabled = disabled;
        regenBtn.onclick = () => regenerateMessage(index);
        actions.appendChild(regenBtn);
    }

    const deleteBtn = document.createElement('button');
    deleteBtn.className = 'message-action-btn delete';
    deleteBtn.innerHTML = ICONS.trash;
    deleteBtn.setAttribute('aria-label', 'Delete message');
    deleteBtn.setAttribute('title', 'Delete');
    deleteBtn.disabled = disabled;
    deleteBtn.onclick = () => deleteMessage(index);
    actions.appendChild(deleteBtn);

    return actions;
}
