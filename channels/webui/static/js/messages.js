// =============================================================================
// Content Helpers
// =============================================================================

/**
 * Extracts plain text from message content (handles multi-modal arrays)
 */
function extractTextContent(content) {
    if (typeof content === 'string') return content;
    if (Array.isArray(content)) {
        return content
        .filter(part => part.type === 'text')
        .map(part => part.text)
        .join('\n');
    }
    return '';
}

/**
 * Renders message content - handles both text strings and multi-modal arrays
 */
function renderContentBody(content) {
    // Handle multi-modal content (images + text)
    if (Array.isArray(content)) {
        return content.map(part => {
            if (part.type === 'text') {
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

    // Standard string content
    return renderMarkdown(content || '');
}

// =============================================================================
// Parse message content to determine display type
// =============================================================================

function parseMessageContent(content) {
    // Normalize content to string for parsing logic
    const textContent = extractTextContent(content);

    const systemMatch = textContent.match(/^\[System (\w+)\]:\s*/i);
    if (systemMatch) {
        const type = systemMatch[1].toLowerCase();
        return {
            type: `announce_${type}`,
            displayContent: textContent.substring(systemMatch[0].length),
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

function getRoleClass(role, content) {
    // Use text extraction for checking logic
    const textContent = extractTextContent(content);
    const parsed = parseMessageContent(content);

    if (parsed.isAnnouncement) {
        return `announce ${parsed.type}`;
    }
    if (parsed.isCommandOutput) {
        return 'command_response';
    }

    if (role === 'user' && textContent.trim().startsWith('/')) {
        return 'user_command';
    }

    const roleMap = {
        'user': 'user',
        'assistant': 'ai'
    };

    return roleMap[role] || role;
}

function getRoleDisplay(role, content) {
    const textContent = extractTextContent(content);
    const parsed = parseMessageContent(content);

    if (parsed.isAnnouncement) {
        const type = parsed.type.replace('announce_', '');
        return type.charAt(0).toUpperCase() + type.slice(1);
    }
    if (parsed.isCommandOutput) {
        return 'Command';
    }
    if (role === 'user' && textContent.trim().startsWith('/')) {
        return 'Command';
    }

    const displayMap = {
        'user': 'You',
        'assistant': 'AI'
    };

    return displayMap[role] || role;
}

// =============================================================================
// Message Rendering
// =============================================================================

function renderAllMessages(messages, animate = false) {
    const wrappers = chat.querySelectorAll('.message-wrapper');
    wrappers.forEach(wrapper => wrapper.remove());

    messages.forEach((msg, i) => {
        // Use the index from the message, or fall back to array position
        const index = msg.index !== undefined ? msg.index : i;
        createMessageElement(msg, index, animate);
    });

    scrollToBottom();
}

function renderReasoningBlock(reasoningContent, isCollapsed = true) {
    if (!reasoningContent) return '';

    const escaped = escapeHtml(reasoningContent);
    const collapsedClass = isCollapsed ? 'collapsed' : 'expanded';

    return `
    <div class="reasoning-wrapper ${collapsedClass}">
    <div class="reasoning-header" onclick="toggleReasoningBlock(this)">
    <svg class="reasoning-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
    <circle cx="12" cy="12" r="3"/>
    </svg>
    <span>Thinking</span>
    <svg class="reasoning-toggle" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <polyline points="6 9 12 15 18 9"></polyline>
    </svg>
    </div>
    <div class="reasoning-block">
    <div class="reasoning-content">${escaped}</div>
    </div>
    </div>
    `;
}

function toggleReasoningBlock(headerElement) {
    const wrapper = headerElement.closest('.reasoning-wrapper');
    if (wrapper) {
        wrapper.classList.toggle('collapsed');
        wrapper.classList.toggle('expanded');
    }
}

function createMessageElement(msg, index, animate = false) {
    const role = msg.role || 'user';
    const rawContent = msg.content || ''; // Can be string or array
    const reasoningContent = msg.reasoning_content || null;
    const toolCalls = msg.tool_calls || null;
    const toolCallId = msg.tool_call_id || null;
    const timestamp = msg.timestamp || formatTime();

    // Extract text for logic checks
    const rawText = extractTextContent(rawContent);

    // Handle tool response - find and update existing tool call
    if (role === 'tool' && toolCallId) {
        const existingWrapper = document.querySelector(`[data-tool-call-id="${toolCallId}"]`);
        if (existingWrapper) {
            updateToolCallWithResponse(existingWrapper, rawText);
            return existingWrapper.closest('.message-wrapper');
        }
    }

    const parsed = parseMessageContent(rawContent);
    const displayContent = parsed.displayContent || rawText;

    let wrapperClass, msgClass;

    if (rawText === '[SYSTEM_TICK]') {
        wrapperClass = 'system-tick';
        msgClass = 'system-tick';
    } else if (parsed.isAnnouncement) {
        wrapperClass = 'announce';
        msgClass = `announce ${parsed.type}`;
    } else if (parsed.isCommandOutput) {
        wrapperClass = 'command_response';
        msgClass = 'command_response';
    } else if (role === 'tool') {
        wrapperClass = 'tool';
        msgClass = 'tool';
    } else if (toolCalls && toolCalls.length > 0) {
        wrapperClass = 'tool_call';
        msgClass = 'tool_call';
    } else if (role === 'schedule') {
        wrapperClass = 'schedule';
        msgClass = 'schedule';
    } else if (role === 'user') {
        if (rawText.trim().startsWith('/')) {
            wrapperClass = 'user_command';
            msgClass = 'user_command';
        } else {
            wrapperClass = 'user';
            msgClass = 'user';
        }
    } else {
        wrapperClass = 'ai';
        msgClass = 'ai';
    }

    const wrapper = document.createElement('div');
    wrapper.className = `message-wrapper ${wrapperClass}`;

    if (animate) {
        wrapper.classList.add('animate-in');
    }

    wrapper.setAttribute('role', 'article');
    wrapper.dataset.index = index;

    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${msgClass}`;

    // Build message content
    let messageHtml = '';

    // Add reasoning block BEFORE the main content (only for assistant messages)
    if (role === 'assistant' && reasoningContent) {
        messageHtml += renderReasoningBlock(reasoningContent);
    }

    // Render based on message type
    if (parsed.isAnnouncement) {
        messageHtml += escapeHtml(displayContent);
    } else if (role === 'tool' && !toolCallId) {
        messageHtml += renderStandaloneToolResponse(rawText);
    } else if (toolCalls && toolCalls.length > 0) {
        // Render tool decision text with proper styling
        if (displayContent && displayContent.trim()) {
            messageHtml += `<div class="tool-decision-text">${renderMarkdown(displayContent)}</div>`;
        }
        messageHtml += renderToolCalls(toolCalls);
    } else if (role === 'schedule') {
        messageHtml += renderScheduleMessage(rawText);
    } else if (parsed.isCommandOutput || wrapperClass === 'user_command') {
        messageHtml += `<pre>${escapeHtml(displayContent)}</pre>`;
    } else {
        // MODIFIED: Use renderContentBody which handles images
        messageHtml += renderContentBody(rawContent);
    }

    msgDiv.innerHTML = messageHtml;

    // Highlight code if not announcement/command
    if (!parsed.isAnnouncement && !parsed.isCommandOutput && !wrapperClass.includes('command')) {
        highlightCode(msgDiv);
    }

    const isToolMessage = toolCalls && toolCalls.length > 0;

    // Only add timestamp for non-tool messages
    if (!isToolMessage) {
        const ts = document.createElement('span');
        ts.className = 'timestamp';

        if (wrapperClass === 'user' || wrapperClass === 'user_command') {
            ts.classList.add('timestamp-right');
        } else if (wrapperClass === 'ai' || wrapperClass === 'command_response') {
            ts.classList.add('timestamp-left');
        } else {
            ts.classList.add('timestamp-center');
        }

        ts.textContent = timestamp;
        ts.innerHTML += ` <span class="index-badge">#${index}</span>`;

        msgDiv.appendChild(ts);
    }

    wrapper.appendChild(msgDiv);

    // Only add action buttons for regular user/assistant messages, not tool messages
    if ((role === 'user' || role === 'assistant') && !isToolMessage && !parsed.isAnnouncement && !parsed.isCommandOutput) {
        // Pass the extracted text (rawText) to action buttons for copying/editing
        const actions = createActionButtons(role, index, rawText);
        wrapper.appendChild(actions);
    }

    chat.insertBefore(wrapper, typing);
    return wrapper;
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


function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// =============================================================================
// Special Message Renderers
// =============================================================================

function renderToolCalls(toolCalls) {
    if (!toolCalls || toolCalls.length === 0) {
        return '';
    }

    let html = '';

    toolCalls.forEach((call, idx) => {
        const func = call.function || call;
        const toolName = func.name || 'Unknown Tool';
        const argsRaw = func.arguments || '{}';
        const callId = call.id || `tool-${Date.now()}-${idx}`;

        let args = {};
        try {
            args = typeof argsRaw === 'string' ? JSON.parse(argsRaw) : argsRaw;
        } catch (e) {
            args = { raw: argsRaw };
        }

        const argEntries = Object.entries(args);
        let headerExtraHtml = '';

        // If only one argument, show it in the header
        if (argEntries.length === 1) {
            const [argName, argValue] = argEntries[0];
            let displayValue = typeof argValue === 'object'
            ? JSON.stringify(argValue)
            : String(argValue);

            if (displayValue.length > 50) {
                displayValue = displayValue.substring(0, 50) + '...';
            }
            headerExtraHtml = `<span class="tool-call-inline-arg">${escapeHtml(displayValue)}</span>`;
        } else if (argEntries.length > 1) {
            // If multiple arguments, show count in a circle
            headerExtraHtml = `<span class="tool-call-arg-count">${argEntries.length}</span>`;
        }

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
        <span class="tool-call-status pending">calling...</span>
        </div>
        <div class="tool-call-body">
        <div class="tool-call-section">
        <div class="tool-call-section-title">Arguments</div>
        <div class="tool-call-args">
        `;

        if (argEntries.length > 0) {
            argEntries.forEach(([argName, argValue]) => {
                let displayValue = typeof argValue === 'object'
                ? JSON.stringify(argValue)
                : String(argValue);

                // if (displayValue.length > 50) {
                //     displayValue = displayValue.substring(0, 50) + '...';
                // }

                html += `
                <div class="tool-call-arg-row">
                <span class="tool-call-arg-name">${escapeHtml(argName)}</span>
                <span class="tool-call-arg-value">${escapeHtml(displayValue)}</span>
                </div>
                `;
            });
        } else {
            html += `<div class="tool-call-no-args">No arguments</div>`;
        }

        html += `
        </div>
        </div>
        <div class="tool-call-section tool-response-section" style="display: none;">
        <div class="tool-call-section-title">Response</div>
        <div class="tool-response-content"></div>
        </div>
        </div>
        </div>
        `;
    });

    return html;
}

function toggleToolCard(headerElement) {
    const card = headerElement.closest('.tool-call-card');
    if (card) {
        card.classList.toggle('collapsed');
    }
}

function updateToolCallWithResponse(cardElement, responseContent) {
    // Update status
    const status = cardElement.querySelector('.tool-call-status');
    if (status) {
        status.classList.remove('pending');
        status.classList.add('completed');
        status.textContent = 'done';
    }

    // Show and populate response section
    const responseSection = cardElement.querySelector('.tool-response-section');
    const responseContentDiv = cardElement.querySelector('.tool-response-content');

    if (responseSection && responseContentDiv) {
        responseSection.style.display = 'block';
        responseContentDiv.innerHTML = renderToolResponseContent(responseContent);
    }
}

function renderToolResponseContent(content) {
    let displayContent = content;
    let isJson = false;
    let parsedData = null;

    try {
        parsedData = JSON.parse(content);
        isJson = true;
    } catch (e) {
        // Not JSON, use as-is
    }

    if (isJson && parsedData !== null) {
        return renderJsonResponseCompact(parsedData);
    }

    // Truncate long plain text
    // if (displayContent.length > 500) {
    //     displayContent = displayContent.substring(0, 500) + '...';
    // }

    return `<div class="tool-response-string">${escapeHtml(displayContent)}</div>`;
}

function renderJsonResponseCompact(data) {
    if (typeof data === 'string') {
        try {
            const inner = JSON.parse(data);
            return renderJsonResponseCompact(inner);
        } catch (e) {
            let str = data;
            // if (str.length > 500) {
            //     str = str.substring(0, 500) + '...';
            // }
            return `<div class="tool-response-string">${escapeHtml(str)}</div>`;
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
                // if (strVal.length > 80) strVal = strVal.substring(0, 80) + '...';
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
        entries.forEach(([key, value]) => {
            html += `<div class="tool-response-kv-compact">`;
            html += `<span class="tool-response-key">${escapeHtml(key)}</span>`;
            html += `<span class="tool-response-colon">:</span>`;

            if (typeof value === 'object' && value !== null) {
                html += renderJsonResponseCompact(value);
            } else {
                let strVal = String(value);
                // if (strVal.length > 100) strVal = strVal.substring(0, 100) + '...';
                html += `<span class="tool-response-scalar">${escapeHtml(strVal)}</span>`;
            }

            html += `</div>`;
        });
        html += `</div>`;
        return html;
    }

    // Primitive
    let strVal = String(data);
    // if (strVal.length > 100) strVal = strVal.substring(0, 100) + '...';
    return `<span class="tool-response-scalar">${escapeHtml(strVal)}</span>`;
}

function renderStandaloneToolResponse(content) {
    // For tool responses without a matching call
    const responseId = 'tool-res-' + Math.random().toString(36).substring(2, 9);

    let preview = content;
    if (preview.length > 80) {
        preview = preview.substring(0, 80).replace(/\n/g, ' ') + '...';
    }

    return `
    <div class="tool-call-card" id="${responseId}">
    <div class="tool-call-header" onclick="toggleToolCard(this)">
    <svg class="tool-call-toggle" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <polyline points="9 18 15 12 9 6"></polyline>
    </svg>
    <svg class="tool-call-status-icon done" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <polyline points="20 6 9 17 4 12"></polyline>
    </svg>
    <span class="tool-call-name">Tool Response</span>
    <span class="tool-call-status completed">done</span>
    </div>
    <div class="tool-call-body">
    <div class="tool-call-section">
    <div class="tool-call-section-title">Response</div>
    <div class="tool-response-content">
    ${renderToolResponseContent(content)}
    </div>
    </div>
    </div>
    </div>
    `;
}

function renderScheduleMessage(content) {
    let data;
    try {
        data = typeof content === 'string' ? JSON.parse(content) : content;
    } catch (e) {
        return `<pre>${escapeHtml(content)}</pre>`;
    }

    const title = data.title || data.action || 'Scheduled Action';
    const description = data.description || data.content || '';
    const scheduledTime = data.scheduled_time || data.time || data.when;
    const actions = data.actions || [];

    let html = `
    <div class="schedule-header">
    <svg class="schedule-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <circle cx="12" cy="12" r="10"/>
    <polyline points="12 6 12 12 16 14"/>
    </svg>
    <span class="schedule-title">${escapeHtml(title)}</span>
    </div>
    `;

    if (description) {
        html += `<div class="schedule-content">${escapeHtml(description)}</div>`;
    }

    if (scheduledTime) {
        const timeStr = typeof scheduledTime === 'object'
        ? new Date(scheduledTime).toLocaleString()
        : scheduledTime;
        html += `
        <div class="schedule-time">
        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
        <line x1="16" y1="2" x2="16" y2="6"/>
        <line x1="8" y1="2" x2="8" y2="6"/>
        <line x1="3" y1="10" x2="21" y2="10"/>
        </svg>
        <span>${escapeHtml(timeStr)}</span>
        </div>
        `;
    }

    if (actions && actions.length > 0) {
        html += '<div class="schedule-actions">';
        actions.forEach(action => {
            const actionClass = action.type === 'cancel' ? 'danger' : '';
            html += `<button class="schedule-action ${actionClass}" onclick="handleScheduleAction('${action.type}', '${action.id || ''}')">${escapeHtml(action.label || action.type)}</button>`;
        });
        html += '</div>';
    }

    return html;
}

function handleScheduleAction(type, id) {
    console.log('Schedule action:', type, id);
}
