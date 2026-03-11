// =============================================================================
// Icon Templates for Action Buttons
// =============================================================================

const ICONS = {
    copy: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>`,
    edit: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>`,
    trash: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>`,
    check: `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`
};

// =============================================================================
// State Management - Backend is source of truth
// =============================================================================

let isConnected = false;
let reconnectAttempts = 0;
let reconnectTimer = null;
let lastMessageIndex = 0;
let currentConversationId = null;

// Stream state
let isStreaming = false;
let streamFrozen = false;
let currentController = null;
let currentStreamId = null;
let editingIndex = null;

// Search state
let searchQuery = '';
let searchResults = [];
let allConversations = [];
let searchInContent = false;

// Polling cleanup
let pollIntervalId = null;

// Notification state
let notificationPermission = 'default';

// DOM references
const chat = document.getElementById('chat');
const typing = document.getElementById('typing');
const inputField = document.getElementById('message');
const sendBtn = document.getElementById('send');
const stopBtn = document.getElementById('stop');
const statusDot = document.getElementById('status');
const dropOverlay = document.getElementById('drop-overlay');
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebar-overlay');

// =============================================================================
// Configuration
// =============================================================================

const CONFIG = {
    RECONNECT_BASE_DELAY: 1000,
    RECONNECT_MAX_DELAY: 30000,
    RECONNECT_DELAY_FACTOR: 1.5,
    CONNECTION_TIMEOUT: 3000,
    POLL_INTERVAL: 500
};

// =============================================================================
// Markdown Rendering
// =============================================================================

marked.setOptions({
    breaks: true,
    gfm: true
});

function renderMarkdown(text) {
    return marked.parse(text);
}

function highlightCode(element) {
    if (typeof hljs === 'undefined') return;

    element.querySelectorAll('pre code').forEach((block) => {
        hljs.highlightElement(block);

        const pre = block.parentElement;
        if (!pre.querySelector('.copy-btn')) {
            const btn = document.createElement('button');
            btn.className = 'copy-btn';
            btn.textContent = 'Copy';
            btn.setAttribute('aria-label', 'Copy code');
            btn.onclick = () => {
                navigator.clipboard.writeText(block.textContent).then(() => {
                    btn.textContent = 'Copied!';
                    btn.classList.add('copied');
                    setTimeout(() => {
                        btn.textContent = 'Copy';
                        btn.classList.remove('copied');
                    }, 1500);
                });
            };
            pre.style.position = 'relative';
            pre.appendChild(btn);
        }
    });
}

// =============================================================================
// Parse message content to determine display type
// =============================================================================

function parseMessageContent(content) {
    const systemMatch = content.match(/^\[System (\w+)\]:\s*/i);
    if (systemMatch) {
        const type = systemMatch[1].toLowerCase();
        return {
            type: `announce_${type}`,
            displayContent: content.substring(systemMatch[0].length),
            isAnnouncement: true
        };
    }

    const cmdMatch = content.match(/^\[Command Output\]:\s*/i);
    if (cmdMatch) {
        return {
            type: 'command_response',
            displayContent: content.substring(cmdMatch[0].length),
            isCommandOutput: true
        };
    }

    return {
        type: null,
        displayContent: content
    };
}

function getRoleClass(role, content) {
    const parsed = parseMessageContent(content);

    if (parsed.isAnnouncement) {
        return `announce ${parsed.type}`;
    }
    if (parsed.isCommandOutput) {
        return 'command_response';
    }

    if (role === 'user' && content.trim().startsWith('/')) {
        return 'user_command';
    }

    const roleMap = {
        'user': 'user',
        'assistant': 'ai'
    };

    return roleMap[role] || role;
}

function getRoleDisplay(role, content) {
    const parsed = parseMessageContent(content);

    if (parsed.isAnnouncement) {
        const type = parsed.type.replace('announce_', '');
        return type.charAt(0).toUpperCase() + type.slice(1);
    }
    if (parsed.isCommandOutput) {
        return 'Command';
    }
    if (role === 'user' && content.trim().startsWith('/')) {
        return 'Command';
    }

    const displayMap = {
        'user': 'You',
        'assistant': 'AI'
    };

    return displayMap[role] || role;
}

// =============================================================================
// Sidebar Management
// =============================================================================

function toggleSidebar() {
    sidebar.classList.toggle('open');
    sidebarOverlay.classList.toggle('show');
}

function closeSidebar() {
    sidebar.classList.remove('open');
    sidebarOverlay.classList.remove('show');
}

// Touch swipe handling for mobile sidebar
let touchStartX = 0;
let touchEndX = 0;

function handleSwipe() {
    const swipeThreshold = 50;
    const diff = touchEndX - touchStartX;

    if (diff > swipeThreshold && touchStartX < 30) {
        sidebar.classList.add('open');
        sidebarOverlay.classList.add('show');
    } else if (diff < -swipeThreshold && sidebar.classList.contains('open')) {
        closeSidebar();
    }
}

document.addEventListener('touchstart', (e) => {
    touchStartX = e.changedTouches[0].screenX;
}, { passive: true });

document.addEventListener('touchend', (e) => {
    touchEndX = e.changedTouches[0].screenX;
    handleSwipe();
}, { passive: true });

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

// =============================================================================
// Reasoning Block Renderer
// =============================================================================

function renderReasoningBlock(reasoningContent, isCollapsed = true) {
    if (!reasoningContent) return '';

    const escaped = escapeHtml(reasoningContent);
    const collapsedClass = isCollapsed ? 'collapsed' : '';

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
    }
}

function createMessageElement(msg, index, animate = false) {
    const role = msg.role || 'user';
    const rawContent = msg.content || '';
    const reasoningContent = msg.reasoning_content || null;
    const toolCalls = msg.tool_calls || null;
    const toolCallId = msg.tool_call_id || null;
    const timestamp = msg.timestamp || formatTime();

    // Handle tool response - find and update existing tool call
    if (role === 'tool' && toolCallId) {
        const existingWrapper = document.querySelector(`[data-tool-call-id="${toolCallId}"]`);
        if (existingWrapper) {
            updateToolCallWithResponse(existingWrapper, rawContent);
            return existingWrapper.closest('.message-wrapper');
        }
    }

    const parsed = parseMessageContent(rawContent);
    const displayContent = parsed.displayContent || rawContent;

    let wrapperClass, msgClass;

    if (rawContent === '[SYSTEM_TICK]') {
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
        if (rawContent.trim().startsWith('/')) {
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
        messageHtml += renderStandaloneToolResponse(rawContent);
    } else if (toolCalls && toolCalls.length > 0) {
        // Render tool decision text with proper styling
        if (displayContent && displayContent.trim()) {
            messageHtml += `<div class="tool-decision-text">${renderMarkdown(displayContent)}</div>`;
        }
        messageHtml += renderToolCalls(toolCalls);
    } else if (role === 'schedule') {
        messageHtml += renderScheduleMessage(rawContent);
    } else if (parsed.isCommandOutput || wrapperClass === 'user_command') {
        messageHtml += `<pre>${escapeHtml(displayContent)}</pre>`;
    } else if (role === 'user') {
        messageHtml += renderMarkdown(displayContent);
    } else {
        messageHtml += renderMarkdown(displayContent);
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
        const actions = createActionButtons(role, index, displayContent);
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

// =============================================================================
// Utility Functions
// =============================================================================

function formatTime() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        chat.scrollTop = chat.scrollHeight;
    });
}

function scrollToBottomDelayed() {
    setTimeout(scrollToBottom, 10);
}

function autoResize(textarea) {
    if (!textarea.value) {
        textarea.style.height = '48px';
    } else {
        textarea.style.height = 'auto';
        textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
    }
}

function clearInput() {
    inputField.value = '';
    autoResize(inputField);
}

// =============================================================================
// Browser Notifications
// =============================================================================

function requestNotificationPermission() {
    if (!('Notification' in window)) {
        console.log('Browser notifications not supported');
        return;
    }

    if (Notification.permission === 'default') {
        Notification.requestPermission().then(permission => {
            notificationPermission = permission;
        });
    } else {
        notificationPermission = Notification.permission;
    }
}

function showAnnouncementNotification(content, type) {
    if (notificationPermission !== 'granted') return;
    if (!('Notification' in window)) return;

    if (type !== "schedule") {
        // only notify for scheduler events
        return;
    }

    // Determine notification options based on type
    const typeSettings = {
        schedule: { icon: '📢', tag: 'announce-info' },
        warning: { icon: '⚠️', tag: 'announce-warning' },
        error: { icon: '❌', tag: 'announce-error' },
        success: { icon: '✅', tag: 'announce-success' }
    };

    const settings = typeSettings[type] || typeSettings.info;

    const notification = new Notification(`System ${type.charAt(0).toUpperCase() + type.slice(1)}`, {
        body: content,
        icon: settings.icon,
        tag: settings.tag,
        renotify: true
    });

    notification.onclick = () => {
        window.focus();
        notification.close();
    };

    // Auto-close after 5 seconds
    setTimeout(() => notification.close(), 5000);
}

// =============================================================================
// Connection Status Messages
// =============================================================================
let statusMessageElement = null;
let lastActiveConversationId = null;

function showConnectionStatus(status) {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper announce';
    wrapper.setAttribute('role', 'status');
    wrapper.setAttribute('aria-live', 'polite');

    const msgDiv = document.createElement('div');

    let statusText = '';

    switch(status) {
        case 'disconnected':
            msgDiv.className = 'message announce announce_error';
            statusText = 'Disconnected from server.';
            break;
        case 'reconnecting':
            msgDiv.className = 'message announce announce_info';
            statusText = 'Reconnecting...';
            break;
        case 'reconnected':
            msgDiv.className = 'message announce announce_info';
            statusText = 'Reconnected.';
            break;
    }

    msgDiv.textContent = statusText;
    wrapper.appendChild(msgDiv);

    statusMessageElement = wrapper;
    chat.insertBefore(wrapper, typing);
    scrollToBottom();
}

function hideConnectionStatus() {
    if (statusMessageElement) {
        statusMessageElement.remove();
        statusMessageElement = null;
    }
}

function updateConnectionStatus(status) {
    statusDot.className = 'status-dot ' + status;
    statusDot.setAttribute('aria-label', 'Connection status: ' + status);

    if (status === 'disconnected') {
        sendBtn.disabled = true;
    } else if (status === 'connected') {
        sendBtn.disabled = false;
    }
}

async function checkConnection() {
    try {
        const response = await fetch('/messages?since=0', {
            signal: AbortSignal.timeout(CONFIG.CONNECTION_TIMEOUT)
        });

        if (response.ok) {
            if (!isConnected) {
                isConnected = true;
                updateConnectionStatus('connected');

                // Was disconnected, now reconnected
                if (reconnectAttempts > 0) {
                    showConnectionStatus('reconnected');

                    if (lastActiveConversationId) {
                        await loadConversation(lastActiveConversationId);
                        lastActiveConversationId = null;
                    } else {
                        await syncMessages();
                    }

                    hideConnectionStatus();
                    reconnectAttempts = 0;
                }
            } else {
                hideConnectionStatus();
            }
        } else {
            throw new Error('Server error');
        }
    } catch (err) {
        handleConnectionError();
    }
}

function handleConnectionError() {
    const wasConnected = isConnected;

    if (wasConnected) {
        isConnected = false;
        lastActiveConversationId = currentConversationId;
        updateConnectionStatus('disconnected');
        showConnectionStatus('disconnected');
    }

    scheduleReconnect();
}

function scheduleReconnect() {
    if (reconnectTimer) clearTimeout(reconnectTimer);

    reconnectAttempts++;
    const delay = 1000;
    if (reconnectAttempts === 1) {
        showConnectionStatus('reconnecting');
    }

    updateConnectionStatus('connecting');

    reconnectTimer = setTimeout(async () => {
        await checkConnection();
        if (!isConnected) {
            scheduleReconnect();
        }
    }, delay);
}

// =============================================================================
// Polling - Backend is source of truth
// =============================================================================

async function pollMessages() {
    if (!isConnected) return;

    try {
        const response = await fetch('/messages/since?index=' + lastMessageIndex, {
            signal: AbortSignal.timeout(CONFIG.POLL_INTERVAL)
        });

        if (!response.ok) {
            if (response.status >= 500) handleConnectionError();
            return;
        }

        const data = await response.json();
        const messages = data.messages || [];

        if (messages.length > 0) {
            for (const msg of messages) {
                const msgIndex = msg.index;
                const parsed = parseMessageContent(msg.content || '');
                const hasToolCalls = msg.tool_calls && msg.tool_calls.length > 0;
                const isToolResponse = msg.role === 'tool';
                const isToolMessage = hasToolCalls || isToolResponse;
                const isUserCommand = msg.role === 'user' && (msg.content || '').trim().startsWith('/');
                const isCommandOutput = parsed.isCommandOutput;

                // Freeze streaming content when first tool call appears
                if (isStreaming && hasToolCalls && !streamFrozen) {
                    streamFrozen = true;
                    // Don't update aiContent anymore - it's frozen
                }

                if (isStreaming && !parsed.isAnnouncement) {
                    if (!isUserCommand && !isCommandOutput && !isToolMessage) {
                        continue;
                    }
                }

                if (parsed.isAnnouncement) {
                    showAnnouncementNotification(
                        parsed.displayContent,
                        parsed.type.replace('announce_', '')
                    );
                }

                const existing = chat.querySelector(`[data-index="${msgIndex}"]`);
                if (!existing) {
                    createMessageElement(msg, msgIndex, true);
                }
            }
            lastMessageIndex = data.total;
            scrollToBottom();
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
            // Messages should now have indices from backend
            // Re-render everything to ensure indices are in sync
            renderAllMessages(messages);
            // Update lastMessageIndex to the last message's index
            lastMessageIndex = messages[messages.length - 1].index;
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
// Conversations
// =============================================================================

async function loadConversations() {
    try {
        const response = await fetch('/conversations');
        const data = await response.json();
        renderConversationList(data.conversations || []);
    } catch (e) {
        console.error('Failed to load conversations:', e);
    }
}

async function restoreCurrentConversation() {
    try {
        const response = await fetch('/conversation/current');
        const data = await response.json();

        if (data.success && data.conversation && data.conversation.id) {
            currentConversationId = data.conversation.id;
            const messages = data.conversation.messages || [];

            updateConversationTitleBar(data.conversation.title);

            if (messages.length > 0) {
                renderAllMessages(messages);
                // Use total from response, or calculate from last message index
                lastMessageIndex = data.conversation.total ||
                (messages[messages.length - 1].index + 1);
            } else {
                lastMessageIndex = 0;
            }
        } else if (data.success && data.current_id === null) {
            currentConversationId = null;
            lastMessageIndex = 0;
            updateConversationTitleBar(null);
        }
    } catch (e) {
        console.error('Failed to restore current conversation:', e);
        currentConversationId = null;
        updateConversationTitleBar(null);
    }
}

async function getCurrentConversationId() {
    try {
        const response = await fetch('/conversation/current');
        const data = await response.json();

        if (data.success && data.conversation && data.conversation.id) {
            currentConversationId = data.conversation.id;
            return data.conversation.id;
        }
        return null;
    } catch (e) {
        console.error('Failed to get current conversation ID:', e);
        return null;
    }
}

function renderConversationList(conversations) {
    allConversations = conversations;

    const list = document.getElementById('conv-list');
    const searchInput = document.getElementById('conv-search');
    const currentSearchQuery = searchInput ? searchInput.value : '';

    list.innerHTML = '';

    if (conversations.length === 0) {
        const emptyMsg = document.createElement('div');
        emptyMsg.className = 'conv-empty';
        emptyMsg.textContent = 'No conversations yet';
        emptyMsg.style.cssText = 'padding: 20px; text-align: center; color: var(--text-muted); font-size: 0.85rem;';
        list.appendChild(emptyMsg);
        return;
    }

    conversations.forEach(conv => {
        const item = document.createElement('div');
        item.className = 'conv-item' + (conv.id === currentConversationId ? ' active' : '');

        item.dataset.convId = conv.id;
        item.dataset.convData = JSON.stringify(conv);

        item.onclick = () => loadConversation(conv.id);

        const title = document.createElement('div');
        title.className = 'conv-item-title';
        title.textContent = conv.title || 'New Conversation';

        const meta = document.createElement('div');
        meta.className = 'conv-item-meta';

        const date = document.createElement('span');
        date.textContent = formatDate(conv.updated || conv.created);

        const actions = document.createElement('div');
        actions.className = 'conv-item-actions';

        // Only delete button, no rename
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'conv-action-btn delete';
        deleteBtn.textContent = 'Delete';
        deleteBtn.onclick = (e) => {
            e.stopPropagation();
            deleteConversation(conv.id);
        };

        actions.appendChild(deleteBtn);
        meta.appendChild(date);
        meta.appendChild(actions);

        item.appendChild(title);
        item.appendChild(meta);
        list.appendChild(item);
    });

    if (currentSearchQuery) {
        filterConversations(currentSearchQuery);
    }
}

async function newConversation() {
    if (isStreaming) {
        return;
    }

    try {
        const response = await fetch('/conversation/new', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: 'New Conversation' })
        });

        const data = await response.json();

        if (data.success && data.conversation) {
            currentConversationId = data.conversation.id;
            lastMessageIndex = 0;

            updateConversationTitleBar(data.conversation.title);

            const wrappers = chat.querySelectorAll('.message-wrapper');
            wrappers.forEach(wrapper => wrapper.remove());

            await loadConversations();
            closeSidebar();
        }
    } catch (e) {
        console.error('Failed to create new conversation:', e);
    }
}


// Internal helper to load a conversation without closing the sidebar
async function loadConversationInternal(convId, cachedMessages = null) {
    try {
        // Use cached messages if available (avoids extra fetch)
        if (cachedMessages) {
            currentConversationId = convId;
            renderAllMessages(cachedMessages);
            lastMessageIndex = cachedMessages.length;
            return;
        }

        const response = await fetch('/conversation/load?id=' + convId);
        const data = await response.json();

        if (data.success && data.conversation) {
            currentConversationId = convId;
            renderAllMessages(data.conversation.messages || []);
            lastMessageIndex = (data.conversation.messages || []).length;
        }
    } catch (e) {
        console.error('Failed to load conversation internally:', e);
    }
}

async function loadConversation(convId) {
    if (isStreaming) {
        return;
    }

    try {
        const response = await fetch('/conversation/load?id=' + convId);
        const data = await response.json();

        if (data.success && data.conversation) {
            currentConversationId = convId;
            const messages = data.conversation.messages || [];
            renderAllMessages(messages, true);
            // Use total from response, or calculate from last message index
            lastMessageIndex = data.conversation.total ||
            (messages.length > 0 ? messages[messages.length - 1].index + 1 : 0);
            await loadConversations();
            closeSidebar();
        } else {
            console.error('Failed to load conversation:', data.error);
        }
    } catch (e) {
        console.error('Failed to load conversation:', e);
    }
}

// Note: Conversations are auto-saved by the backend when messages are added.
// No explicit save endpoint exists. This function is kept for potential future use
// or for triggering a UI state sync.
async function saveCurrentConversation() {
    // Backend auto-saves, so this is a no-op for now
    // Refresh the conversation list to reflect any changes
    await loadConversations();
}

async function deleteConversation(convId) {
    if (!confirm('Delete this conversation?')) return;

    try {
        const response = await fetch('/conversation/delete?id=' + convId, {
            method: 'POST'
        });
        const data = await response.json();

        if (data.success) {
            // If we deleted the current conversation, create a new one
            if (currentConversationId === convId) {
                currentConversationId = null;
                lastMessageIndex = 0;

                // Clear the chat display
                const wrappers = chat.querySelectorAll('.message-wrapper');
                wrappers.forEach(wrapper => wrapper.remove());

                // Create a new conversation
                await newConversation();
            } else {
                await loadConversations();
            }
        }
    } catch (e) {
        console.error('Failed to delete conversation:', e);
    }
}

async function renameConversation(convId, currentTitle) {
    const newTitle = prompt('Enter new name:', currentTitle);
    if (!newTitle || newTitle.trim() === '' || newTitle === currentTitle) return;

    // The backend only allows renaming the CURRENT conversation
    // Strategy: if renaming a different conversation, load it first, rename, then restore
    const wasCurrentConversation = currentConversationId === convId;
    const previousConvId = currentConversationId;

    try {
        // If this is not the current conversation, we need to load it first
        if (!wasCurrentConversation) {
            const loadResponse = await fetch('/conversation/load?id=' + convId);
            const loadData = await loadResponse.json();

            if (!loadData.success) {
                alert('Failed to load conversation for renaming');
                return;
            }
        }

        // Now rename it (it's the current conversation)
        const response = await fetch('/conversation/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: newTitle.trim() })
        });

        const data = await response.json();

        if (data.success) {
            // Refresh conversation list
            await loadConversations();

            // If we loaded a different conversation, restore the previous one
            if (!wasCurrentConversation && previousConvId) {
                await loadConversationInternal(previousConvId);
            }

            // Update the current conversation ID if we renamed the current one
            if (wasCurrentConversation) {
                // Title changed but ID stays the same
            }
        } else {
            alert('Failed to rename: ' + (data.error || 'Unknown error'));

            // Restore previous conversation if we changed it
            if (!wasCurrentConversation && previousConvId) {
                await loadConversationInternal(previousConvId);
            }
        }
    } catch (e) {
        console.error('Failed to rename conversation:', e);

        // Restore previous conversation if we changed it
        if (!wasCurrentConversation && previousConvId) {
            try {
                await loadConversationInternal(previousConvId);
            } catch (restoreErr) {
                console.error('Failed to restore conversation:', restoreErr);
            }
        }
    }
}

// =============================================================================
// Conversation Title Bar Management
// =============================================================================

function updateConversationTitleBar(title = null) {
    const titleBar = document.getElementById('conv-title-bar');
    const titleText = document.getElementById('conv-title-text');

    if (!title && currentConversationId === null) {
        // No active conversation
        titleBar.classList.add('no-conversation');
        titleText.textContent = 'New Conversation';
    } else {
        titleBar.classList.remove('no-conversation');
        titleText.textContent = title || 'New Conversation';
    }
}

async function renameCurrentConversation() {
    if (currentConversationId === null) {
        return;
    }

    const titleText = document.getElementById('conv-title-text');
    const currentTitle = titleText.textContent;
    const newTitle = prompt('Enter new name:', currentTitle);

    if (!newTitle || newTitle.trim() === '' || newTitle === currentTitle) return;

    try {
        const response = await fetch('/conversation/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: newTitle.trim() })
        });

        const data = await response.json();

        if (data.success) {
            updateConversationTitleBar(newTitle.trim());
            await loadConversations();
        } else {
            alert('Failed to rename: ' + (data.error || 'Unknown error'));
        }
    } catch (e) {
        console.error('Failed to rename conversation:', e);
    }
}

// =============================================================================
// Conversation Search/Filter
// =============================================================================

function toggleSearchMode() {
    searchInContent = !searchInContent;

    const toggleBtn = document.getElementById('search-toggle');
    const searchInput = document.getElementById('conv-search');

    if (searchInContent) {
        toggleBtn.classList.add('active');
        toggleBtn.setAttribute('aria-pressed', 'true');
        toggleBtn.title = 'Search in content (enabled)';
    } else {
        toggleBtn.classList.remove('active');
        toggleBtn.setAttribute('aria-pressed', 'false');
        toggleBtn.title = 'Search in content (disabled)';
    }

    // Re-run filter with current query
    const currentQuery = searchInput ? searchInput.value : '';
    filterConversations(currentQuery);
}

function filterConversations(query) {
    const searchQuery = (query || '').toLowerCase().trim();
    const items = document.querySelectorAll('.conv-item');

    // Clear all snippets and visibility states first
    items.forEach(item => {
        const existingSnippet = item.querySelector('.conv-snippet');
        if (existingSnippet) {
            existingSnippet.remove();
        }
        item.classList.remove('hidden-by-search');
    });

    // Show all when search is empty
    if (!searchQuery) {
        return;
    }

    items.forEach(item => {
        const titleEl = item.querySelector('.conv-item-title');
        const titleText = titleEl ? titleEl.textContent.toLowerCase() : '';

        // Get conversation data from dataset
        let convData = null;
        try {
            convData = JSON.parse(item.dataset.convData || 'null');
        } catch (e) {
            convData = null;
        }

        let matchesTitle = titleText.includes(searchQuery);
        let matchSnippet = null;

        // If content search is enabled, also search in messages
        if (searchInContent && convData && convData.messages) {
            for (const msg of convData.messages) {
                const content = (msg.content || '').toLowerCase();
                if (content.includes(searchQuery)) {
                    matchSnippet = extractSnippet(msg.content, searchQuery, 60);
                    break; // Use first match
                }
            }
        }

        const isVisible = matchesTitle || matchSnippet;

        if (!isVisible) {
            item.classList.add('hidden-by-search');
        } else if (matchSnippet && searchInContent) {
            // Add snippet after the meta element
            const metaEl = item.querySelector('.conv-item-meta');
            if (metaEl && !item.querySelector('.conv-snippet')) {
                const snippetEl = document.createElement('div');
                snippetEl.className = 'conv-snippet';
                snippetEl.innerHTML = matchSnippet;
                // Insert after meta
                metaEl.insertAdjacentElement('afterend', snippetEl);
            }
        }
    });
}

function extractSnippet(content, query, maxLength) {
    if (!content) return '';

    const lowerContent = content.toLowerCase();
    const queryLower = query.toLowerCase();
    const matchIndex = lowerContent.indexOf(queryLower);

    if (matchIndex === -1) return '';

    // Calculate snippet boundaries
    const contextChars = Math.floor((maxLength - query.length) / 2);
    let start = Math.max(0, matchIndex - contextChars);
    let end = Math.min(content.length, matchIndex + query.length + contextChars);

    // Adjust to not cut words
    if (start > 0) {
        const spaceIndex = content.lastIndexOf(' ', start);
        if (spaceIndex > matchIndex - contextChars - 10) {
            start = spaceIndex + 1;
        }
    }
    if (end < content.length) {
        const spaceIndex = content.indexOf(' ', end);
        if (spaceIndex !== -1 && spaceIndex < end + 10) {
            end = spaceIndex;
        }
    }

    let snippet = content.substring(start, end);

    // Add ellipsis
    if (start > 0) snippet = '...' + snippet;
    if (end < content.length) snippet = snippet + '...';

    // Escape HTML and highlight match
    snippet = escapeHtml(snippet);
    const regex = new RegExp(`(${escapeRegex(query)})`, 'gi');
    snippet = snippet.replace(regex, '<mark>$1</mark>');

    return snippet;
}

function escapeRegex(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\$&');
}

function formatDate(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now - date;

    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return Math.floor(diff / 60000) + 'm ago';
    if (diff < 86400000) return Math.floor(diff / 3600000) + 'h ago';
    if (diff < 604800000) return Math.floor(diff / 86400000) + 'd ago';

    return date.toLocaleDateString();
}

// =============================================================================
// Message Actions
// =============================================================================

async function editMessage(index, currentContent) {
    if (editingIndex !== null) {
        cancelEdit();
    }

    editingIndex = index;

    const messageEl = chat.querySelector(`[data-index="${index}"]`);
    if (!messageEl) return;

    const editContainer = document.createElement('div');
    editContainer.className = 'edit-container';

    const textarea = document.createElement('textarea');
    textarea.className = 'edit-textarea';
    textarea.value = currentContent;
    textarea.setAttribute('aria-label', 'Edit message');

    const actions = document.createElement('div');
    actions.className = 'edit-actions';

    const saveBtn = document.createElement('button');
    saveBtn.className = 'edit-save';
    saveBtn.textContent = 'Save';
    saveBtn.onclick = () => saveEdit(index, textarea.value);

    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'edit-cancel';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.onclick = cancelEdit;

    actions.appendChild(cancelBtn);
    actions.appendChild(saveBtn);
    editContainer.appendChild(textarea);
    editContainer.appendChild(actions);

    messageEl.innerHTML = '';
    messageEl.appendChild(editContainer);

    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);

    textarea.onkeydown = (e) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            saveEdit(index, textarea.value);
        }
        if (e.key === 'Escape') {
            cancelEdit();
        }
    };
}

async function saveEdit(index, newContent) {
    newContent = (newContent || '').trim();
    if (!newContent) {
        cancelEdit();
        return;
    }

    try {
        const response = await fetch('/edit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ index: index, content: newContent })
        });

        if (response.ok) {
            await syncMessages();
        }
    } catch (err) {
        console.error('Failed to edit message:', err);
    }

    editingIndex = null;
}

function cancelEdit() {
    editingIndex = null;
    syncMessages();
}

async function deleteMessage(index) {
    if (!confirm('Delete this message and all messages after it?')) return;

    try {
        const response = await fetch('/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ index: index })
        });

        if (response.ok) {
            await syncMessages();
        }
    } catch (err) {
        console.error('Failed to delete message:', err);
    }
}

// =============================================================================
// Search
// =============================================================================

function toggleSearch() {
    const container = document.getElementById('search-container');
    const input = document.getElementById('search-input');

    if (container.classList.contains('active')) {
        clearSearch();
    } else {
        container.classList.add('active');
        input.focus();
    }
}

function clearSearch() {
    const container = document.getElementById('search-container');
    const input = document.getElementById('search-input');
    const count = document.getElementById('search-count');

    container.classList.remove('active');
    input.value = '';
    count.textContent = '0 results';
    searchQuery = '';
    searchResults = [];
}

function performSearch(query) {
    searchQuery = query.toLowerCase();
    if (!searchQuery) {
        document.getElementById('search-count').textContent = '0 results';
        return;
    }

    const wrappers = chat.querySelectorAll('.message-wrapper');
    searchResults = [];

    wrappers.forEach(wrapper => {
        const msgDiv = wrapper.querySelector('.message');
        const text = msgDiv.textContent.toLowerCase();

        if (text.includes(searchQuery)) {
            searchResults.push(parseInt(wrapper.dataset.index));
            msgDiv.classList.add('search-highlight');
        } else {
            msgDiv.classList.remove('search-highlight');
        }
    });

    document.getElementById('search-count').textContent = searchResults.length + ' result' + (searchResults.length !== 1 ? 's' : '');
}

// =============================================================================
// Export
// =============================================================================

function showExportModal() {
    toggleModal('export');
}

async function exportChat(format) {
    try {
        const response = await fetch('/messages');
        const data = await response.json();
        const messages = data.messages || [];

        let content, filename, mimeType;

        if (format === 'json') {
            content = JSON.stringify(messages, null, 2);
            filename = 'chat-export.json';
            mimeType = 'application/json';
        } else if (format === 'markdown') {
            let md = '# Chat Export\n\n';
            md += 'Exported on ' + new Date().toLocaleString() + '\n\n---\n\n';

            messages.forEach(msg => {
                const role = getRoleDisplay(msg.role);
                md += '**' + role + '**:\n\n' + (msg.content || '') + '\n\n---\n\n';
            });

            content = md;
            filename = 'chat-export.md';
            mimeType = 'text/markdown';
        } else {
            let txt = 'Chat Export\n';
            txt += 'Exported on ' + new Date().toLocaleString() + '\n';
            txt += '================================\n\n';

            messages.forEach(msg => {
                const role = getRoleDisplay(msg.role);
                txt += '[' + role + ']:\n' + (msg.content || '') + '\n\n';
            });

            content = txt;
            filename = 'chat-export.txt';
            mimeType = 'text/plain';
        }

        const blob = new Blob([content], { type: mimeType });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        toggleModal('export');
    } catch (err) {
        console.error('Export failed:', err);
    }
}

// =============================================================================
// Modal Management
// =============================================================================

function toggleModal(modalName) {
    const overlay = document.getElementById(modalName + '-overlay');
    const modal = document.getElementById(modalName + '-modal');

    overlay.classList.toggle('show');
    modal.classList.toggle('show');
}

function closeModalOnOverlay(event, modalName) {
    if (event.target.id === modalName + '-overlay') {
        toggleModal(modalName);
    }
}

function showShortcutsModal() {
    toggleModal('shortcuts');
}

// =============================================================================
// Input Handling
// =============================================================================

function setInputState(disabled, showTyping = false, showStop = false) {
    // Keep input enabled so users can type/send commands during streaming
    inputField.disabled = false;
    sendBtn.disabled = disabled;

    typing.classList.toggle('show', showTyping);
    sendBtn.classList.toggle('hidden', showStop);
    stopBtn.classList.toggle('show', showStop);
}

function handleKeyDown(event) {
    const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);

    if (event.ctrlKey || event.metaKey) {
        if (event.key === 'Enter') {
            event.preventDefault();
            send();
            return;
        }
        if (event.key === 'l' || event.key === 'L') {
            event.preventDefault();
            clearChat();
            return;
        }
        if (event.key === 's' || event.key === 'S') {
            event.preventDefault();
            toggleModal('settings');
            return;
        }
        if (event.key === 'f' || event.key === 'F') {
            event.preventDefault();
            toggleSearch();
            return;
        }
        if (event.key === 'e' || event.key === 'E') {
            event.preventDefault();
            showExportModal();
            return;
        }
        if (event.key === '/') {
            showShortcutsModal();
            return;
        }
    }

    if (event.key === 'Escape') {
        if (isStreaming) {
            stopGeneration();
        }
        document.querySelectorAll('.modal.show').forEach(modal => {
            const modalName = modal.id.replace('-modal', '');
            toggleModal(modalName);
        });
        closeSidebar();
        if (document.getElementById('search-container').classList.contains('active')) {
            clearSearch();
        }
        return;
    }

    if (!isMobile && event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        send();
    }
}

document.getElementById('message').addEventListener('input', function() {
    autoResize(this);
});

// =============================================================================
// Drag and Drop
// =============================================================================

['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    chat.addEventListener(eventName, preventDefaults, false);
});

function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

['dragenter', 'dragover'].forEach(eventName => {
    chat.addEventListener(eventName, () => {
        chat.classList.add('drag-over');
        dropOverlay.classList.add('active');
    }, false);
});

['dragleave', 'drop'].forEach(eventName => {
    chat.addEventListener(eventName, () => {
        chat.classList.remove('drag-over');
        dropOverlay.classList.remove('active');
    }, false);
});

chat.addEventListener('drop', (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFileUpload({ target: { files: files } });
    }
}, false);

document.body.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropOverlay.classList.add('active');
});

document.body.addEventListener('dragleave', (e) => {
    if (e.target === document.body || !e.relatedTarget) {
        dropOverlay.classList.remove('active');
    }
});

document.body.addEventListener('drop', (e) => {
    e.preventDefault();
    dropOverlay.classList.remove('active');

    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFileUpload({ target: { files: files } });
    }
});

// =============================================================================
// Main Send Function
// =============================================================================

async function send() {
    if (!isConnected) {
        return;
    }

    const message = inputField.value.trim();
    if (!message) return;

    // Commands bypass the streaming lock entirely
    if (message.trim().startsWith('/') || message.trim().startsWith("STOP")) {
        clearInput();
        return sendCommand(message);
    }

    if (isStreaming) return;

    clearInput();

    // Track if we started without a conversation (for lazy creation)
    const startedWithoutConversation = currentConversationId === null;

    // Create user message element
    const userWrapper = document.createElement('div');
    userWrapper.className = message.trim().startsWith('/')
    ? 'message-wrapper user_command'
    : 'message-wrapper user';
    userWrapper.classList.add('animate-in');
    userWrapper.setAttribute('role', 'article');
    userWrapper.dataset.index = 'pending';

    const userMsgDiv = document.createElement('div');
    userMsgDiv.className = message.trim().startsWith('/')
    ? 'message user_command'
    : 'message user';

    if (message.trim().startsWith('/')) {
        userMsgDiv.innerHTML = `<pre>${escapeHtml(message)}</pre>`;
    } else {
        userMsgDiv.innerHTML = renderMarkdown(message);
        highlightCode(userMsgDiv);
    }

    const userTs = document.createElement('span');
    userTs.className = 'timestamp timestamp-right';
    userTs.textContent = formatTime();
    userMsgDiv.appendChild(userTs);

    const userActions = createActionButtons('user', 'pending', message, true);
    userWrapper.appendChild(userMsgDiv);
    userWrapper.appendChild(userActions);
    chat.insertBefore(userWrapper, typing);
    scrollToBottom();

    setInputState(true, true, true);
    isStreaming = true;
    currentController = new AbortController();

    // Create AI message wrapper (hidden until first token)
    const aiWrapper = document.createElement('div');
    aiWrapper.className = 'message-wrapper ai hidden';
    aiWrapper.dataset.index = 'streaming';
    chat.insertBefore(aiWrapper, typing);

    const aiMsgDiv = document.createElement('div');
    aiMsgDiv.className = 'message ai';
    aiWrapper.appendChild(aiMsgDiv);

    const aiActions = createActionButtons('assistant', 'streaming', '', true);
    aiWrapper.appendChild(aiActions);

    let aiContent = '';
    let aiReasoning = '';
    let streamStarted = false;
    let hasReasoning = false;

    try {
        const response = await fetch('/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: message }),
                                     signal: currentController.signal
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));

                        if (data.id) {
                            currentStreamId = data.id;
                        }

                        if (data.cancelled) {
                            aiWrapper.classList.remove('hidden');
                            aiMsgDiv.innerHTML = '<span style="color:#f88;">[Cancelled]</span>';
                            finishStream();
                            return;
                        }

                        if (data.type === 'content') {
                            const token = data.content || '';
                            if (token) {
                                if (!streamStarted) {
                                    streamStarted = true;
                                    typing.classList.remove('show');
                                    aiWrapper.classList.remove('hidden');
                                }
                                // Only accumulate if not frozen
                                if (!streamFrozen) {
                                    aiContent += token;
                                    updateStreamingContent(aiMsgDiv, aiContent, aiReasoning);
                                    scrollToBottomDelayed();
                                }
                            }
                        }

                        if (data.type === 'reasoning') {
                            if (!streamStarted) {
                                streamStarted = true;
                                typing.classList.remove('show');
                                aiWrapper.classList.remove('hidden');
                            }
                            hasReasoning = true;
                            // Only accumulate if not frozen
                            if (!streamFrozen) {
                                aiReasoning += data.content || '';
                                updateStreamingContent(aiMsgDiv, aiContent, aiReasoning);
                                scrollToBottomDelayed();
                            }
                        }

                        if (data.type === 'new_turn') {
                            // Start a new assistant turn during tool processing
                            currentTurnIndex++;
                            aiContent = '';
                            aiReasoning = '';

                            // Create a new turn container if needed
                            if (!aiWrapper.querySelector('.turn-container')) {
                                aiMsgDiv.innerHTML = '<div class="turn-container current"></div>';
                            }

                            // Create previous turn divs for earlier content
                            const prevTurns = streamingTurns.map(t =>
                            `<div class="assistant-turn">${renderMarkdown(t.content)}</div>`
                            ).join('');

                            // Add tool decisions container
                            aiMsgDiv.innerHTML = prevTurns + '<div class="turn-container current"></div>';
                        }

                        // Legacy token format (backward compatibility)
                        if (data.token && !data.type) {
                            if (!streamStarted) {
                                streamStarted = true;
                                typing.classList.remove('show');
                                aiWrapper.classList.remove('hidden');
                            }
                            aiContent += data.token;
                            updateStreamingContent(aiMsgDiv, aiContent, aiReasoning);
                            scrollToBottomDelayed();
                        }

                        if (data.done) {
                            streamingTurns.push({ content: aiContent, reasoning: aiReasoning });
                        }

                        if (data.error) {
                            if (!streamStarted) {
                                aiWrapper.classList.remove('hidden');
                            }
                            aiMsgDiv.innerHTML = '<span style="color:#f88;">[Error: ' + escapeHtml(data.error) + ']</span>';
                        }
                    } catch (e) {
                        // Ignore parse errors
                    }
                }
            }
        }
    } catch (err) {
        if (err.name !== 'AbortError') {
            if (!streamStarted) {
                aiWrapper.classList.remove('hidden');
            }
            aiMsgDiv.innerHTML = '<span style="color:#f88;">Error: ' + escapeHtml(err.message) + '</span>';
        }
    } finally {
        // Animate reasoning collapse before finalizing
        const reasoningWrapper = aiWrapper.querySelector('.reasoning-wrapper');
        if (reasoningWrapper && !reasoningWrapper.classList.contains('collapsed')) {
            reasoningWrapper.classList.add('collapsed');
            // Wait for animation to complete (match CSS transition duration)
            await new Promise(resolve => setTimeout(resolve, 300));
        }

        finishStream();
        userWrapper.remove();
        aiWrapper.remove();
        await syncMessages();
        await saveCurrentConversation();

        // If we started without a conversation, fetch the new ID and title
        if (startedWithoutConversation) {
            const convId = await getCurrentConversationId();
            if (convId) {
                // Fetch the title too
                const response = await fetch('/conversation/current');
                const data = await response.json();
                if (data.success && data.conversation) {
                    updateConversationTitleBar(data.conversation.title);
                }
            }
            await loadConversations();
        }
    }
}

function updateStreamingContent(msgDiv, content, reasoning) {
    let html = '';

    // Add reasoning block if present (collapsed during streaming)
    if (reasoning) {
        html += renderReasoningBlock(reasoning, false); // Not collapsed during streaming
    }

    // Add main content
    if (content) {
        html += renderMarkdown(content);
    }

    msgDiv.innerHTML = html;
    highlightCode(msgDiv);
}

function finishStream() {
    setInputState(false, false, false);
    isStreaming = false;
    streamFrozen = false;
    currentController = null;
    currentStreamId = null;
    inputField.focus();
}

async function sendCommand(message) {
    try {
        if (message.startsWith("/stop") || message.startsWith("STOP")) {
            // if the command was stop, dont await the response, just send it immediately
            const response = fetch('/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message })
            });
            await stopGeneration(true);
        } else {
            // for any other command, wait the response
            const response = await fetch('/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message })
            });
        }

        // Only sync immediately if NOT streaming - otherwise pollMessages() handles it
        // syncMessages() clears all message wrappers including the active streaming one
        if (!isStreaming) {
            await syncMessages();
            await saveCurrentConversation();
        }
    } catch (err) {
        console.error('Command failed:', err);
    }
}

async function stopGeneration(sent_from_command = false) {
    if (currentController) {
        currentController.abort();
        currentController = null;
    }

    if (currentStreamId) {
        if (!sent_from_command) {
            // send the stop command to the server
            fetch('/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: "/stop" })
            });
        }
        try {
            await fetch('/cancel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: currentStreamId })
            });
        } catch (e) {
            // Ignore
        }
        currentStreamId = null;
    }

    await syncMessages();
    finishStream();
}

async function clearChat() {
    try {
        await newConversation();
        await syncMessages();
    } catch (err) {
        console.error('Failed to clear chat:', err);
    }
}

// =============================================================================
// File Upload
// =============================================================================

async function handleFileUpload(event) {
    const file = event.target.files ? event.target.files[0] : event.dataTransfer.files[0];
    if (!file) return;

    if (event.target) {
        event.target.value = '';
    }

    try {
        const reader = new FileReader();
        const base64 = await new Promise((resolve, reject) => {
            reader.onload = () => resolve(reader.result.split(',')[1]);
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });

        const response = await fetch('/upload', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                filename: file.name,
                content: base64,
                mimetype: file.type
            })
        });

        if (response.ok) {
            await syncMessages();
        }
    } catch (err) {
        console.error('Upload failed:', err);
    }

    inputField.focus();
}

// =============================================================================
// Theme System
// =============================================================================

let currentThemeFamily = 'default';
let currentThemeMode = 'dark'; // 'dark' or 'light'

// Parse theme ID to extract family and mode
function parseThemeId(themeId) {
    // Assumes format like 'dark-black', 'light-ocean', 'dark-default', etc.
    const parts = themeId.split('-');
    if (parts.length >= 2) {
        const mode = parts[0];
        const family = parts.slice(1).join('-');
        return { mode, family };
    }
    // Fallback for themes without prefix
    return { mode: 'dark', family: themeId };
}

// Build theme ID from family and mode
function buildThemeId(family, mode) {
    return `${mode}-${family}`;
}

// Get available theme families from themes object
function getThemeFamilies() {
    const families = new Map();

    Object.keys(themes).forEach(themeId => {
        const { mode, family } = parseThemeId(themeId);
        if (!families.has(family)) {
            families.set(family, { dark: null, light: null });
        }
        families.get(family)[mode] = themeId;
    });

    return families;
}

// Apply the current theme based on family and mode
function applyTheme(family, mode) {
    const themeId = buildThemeId(family, mode);
    const theme = themes[themeId];

    // If the specific variant doesn't exist, try the other mode
    if (!theme) {
        const alternateMode = mode === 'dark' ? 'light' : 'dark';
        const alternateId = buildThemeId(family, alternateMode);
        if (themes[alternateId]) {
            // Theme exists in alternate mode only
            currentThemeMode = alternateMode;
            updateModeCheckbox();
        }
    }

    const finalThemeId = buildThemeId(family, currentThemeMode);
    const finalTheme = themes[finalThemeId];

    if (!finalTheme) {
        console.error('Theme not found:', finalThemeId);
        return;
    }

    const root = document.documentElement;
    for (const [varName, value] of Object.entries(finalTheme.vars)) {
        root.style.setProperty(varName, value);
    }

    currentThemeFamily = family;
    localStorage.setItem('themeFamily', family);
    localStorage.setItem('themeMode', currentThemeMode);
    updateThemeButtons();
}

// Apply only mode change (keep same family)
function applyThemeMode(mode) {
    currentThemeMode = mode;
    applyTheme(currentThemeFamily, mode);
}

// Toggle between dark and light mode
function toggleThemeMode(isLight) {
    const mode = isLight ? 'light' : 'dark';
    applyThemeMode(mode);
}

// Update the mode checkbox to reflect current state
function updateModeCheckbox() {
    const checkbox = document.getElementById('theme-mode-checkbox');
    if (checkbox) {
        checkbox.checked = (currentThemeMode === 'light');
    }
}

// Create combined theme buttons
function createThemeButtons() {
    const grid = document.getElementById('theme-grid');
    grid.innerHTML = '';

    const families = getThemeFamilies();

    families.forEach((variants, family) => {
        // Always use dark variant for preview (or light if dark unavailable)
        const previewThemeId = variants.dark || variants.light;
        const previewTheme = themes[previewThemeId];

        if (!previewTheme) return;

        const btn = document.createElement('button');
        btn.className = 'theme-btn' + (family === currentThemeFamily ? ' active' : '');
        btn.dataset.family = family;

        const bgColor = previewTheme.vars['--bg-primary'];
        const accentColor = previewTheme.vars['--accent'];
        const hasBothModes = variants.dark && variants.light;

        // Display name
        const displayName = family.charAt(0).toUpperCase() + family.slice(1);

        btn.innerHTML = `
        <div class="theme-preview"
        style="background: linear-gradient(135deg, ${bgColor} 50%, ${accentColor} 50%);">
        ${hasBothModes ? '<span class="theme-badge">◐</span>' : ''}
        </div>
        <span class="theme-name">${displayName}</span>
        `;

        btn.onclick = () => {
            currentThemeFamily = family;
            applyTheme(family, currentThemeMode);
        };

        grid.appendChild(btn);
    });
}

// Update theme buttons to show active state
function updateThemeButtons() {
    document.querySelectorAll('.theme-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.family === currentThemeFamily);
    });
}

// Load saved theme preferences
function loadTheme() {
    const savedFamily = localStorage.getItem('themeFamily') || 'default';
    const savedMode = localStorage.getItem('themeMode') || 'dark';

    // Verify the theme exists
    const themeId = buildThemeId(savedFamily, savedMode);
    if (!themes[themeId]) {
        // Fall back to default dark
        currentThemeFamily = 'default';
        currentThemeMode = 'dark';
    } else {
        currentThemeFamily = savedFamily;
        currentThemeMode = savedMode;
    }

    applyTheme(currentThemeFamily, currentThemeMode);
}

// =============================================================================
// Settings Management
// =============================================================================

let settingsData = {};
let settingsOriginal = {};
let settingsHasChanges = false;

// Category icons
const SETTINGS_ICONS = {
    api: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"></path><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"></path></svg>`,
    model: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"></path><polyline points="3.27 6.96 12 12.01 20.73 6.96"></polyline><line x1="12" y1="22.08" x2="12" y2="12"></line></svg>`,
    channels: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>`,
    modules: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>`,
    appearance: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"></circle><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"></path></svg>`,
    advanced: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>`,
    other: `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="1"></circle><circle cx="12" cy="5" r="1"></circle><circle cx="12" cy="19" r="1"></circle></svg>`
};

// Category descriptions (generic)
const CATEGORY_DESCRIPTIONS = {};

// Check if a setting is a toggle list (has enabled/disabled arrays)
function isToggleList(data) {
    if (typeof data !== 'object' || data === null) return false;
    return Array.isArray(data.enabled) && Array.isArray(data.disabled);
}

// Get all items from enabled/disabled structure
function getAllToggleItems(data) {
    if (!isToggleList(data)) return [];
    const enabled = Array.isArray(data.enabled) ? data.enabled : [];
    const disabled = Array.isArray(data.disabled) ? data.disabled : [];
    return [...new Set([...enabled, ...disabled])].sort();
}

// Organize settings into categories based on structure
function organizeSettingsIntoCategories(originalData) {
    const categories = {};

    // Always add appearance first for theme
    categories.appearance = {
        title: 'Appearance',
        description: 'Theme and interface customization',
        isTheme: true,
        items: [],
        order: 0
    };

    // Process each top-level key
    let order = 1;
    for (const [topKey, topValue] of Object.entries(originalData)) {
        // Skip theme-related keys
        if (topKey.toLowerCase() === 'theme' || topKey.toLowerCase() === 'theme_mode') {
            continue;
        }

        const category = topKey;
        categories[category] = {
            title: formatLabel(category),
            description: CATEGORY_DESCRIPTIONS[category] || `Configure ${formatLabel(category).toLowerCase()}`,
            items: [],
            order: order++
        };

        // Check if this is a toggle list (enabled/disabled pattern)
        if (isToggleList(topValue)) {
            categories[category].isToggleList = true;
            categories[category].toggleListKey = topKey;
            categories[category].items.push({
                key: topKey,
                value: topValue,
                type: 'toggle_list'
            });

            // Add any settings sub-object
            if (topValue.settings && typeof topValue.settings === 'object') {
                flattenSettingsObject(topValue.settings, `${topKey}.settings`, categories[category].items);
            }
            continue;
        }

        // Regular object - flatten and add items
        if (typeof topValue === 'object' && topValue !== null && !Array.isArray(topValue)) {
            flattenSettingsObject(topValue, topKey, categories[category].items);
        } else {
            // Simple value
            categories[category].items.push({
                key: topKey,
                value: topValue,
                type: detectType(topValue)
            });
        }
    }

    // Sort items: toggle lists first, then simple fields, then arrays/objects
    for (const cat of Object.keys(categories)) {
        categories[cat].items.sort((a, b) => {
            // Toggle lists always come first
            if (a.type === 'toggle_list' && b.type !== 'toggle_list') return -1;
            if (b.type === 'toggle_list' && a.type !== 'toggle_list') return 1;

            // Then simple fields before complex types
            const aComplex = a.type === 'array' || a.type === 'object';
            const bComplex = b.type === 'array' || b.type === 'object';
            if (aComplex && !bComplex) return 1;
            if (!aComplex && bComplex) return -1;

            return 0;
        });
    }

    return categories;
}

// Flatten a settings object into dot-notation items
function flattenSettingsObject(obj, prefix, items) {
    for (const [key, value] of Object.entries(obj)) {
        const fullKey = prefix ? `${prefix}.${key}` : key;

        if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
            // Nested object - recurse
            flattenSettingsObject(value, fullKey, items);
        } else {
            items.push({
                key: fullKey,
                value: value,
                type: detectType(value),
                       description: FIELD_DESCRIPTIONS[fullKey] || null
            });
        }
    }
}

// Detect field type from value
function detectType(value) {
    if (value === null || value === undefined) return 'text';
    if (typeof value === 'boolean') return 'boolean';
    if (typeof value === 'number') return 'number';
    if (Array.isArray(value)) return 'array';
    if (typeof value === 'object') return 'object';
    if (typeof value === 'string') {
        if (value.includes('\n')) return 'textarea';
        if (value.match(/^https?:\/\//)) return 'url';
    }
    return 'text';
}

// Field descriptions (optional, can be empty)
const FIELD_DESCRIPTIONS = {
    'api.key': 'API authentication key'
};

// Flatten nested object to dot-notation keys
function flattenObject(obj, prefix = '') {
    const result = {};

    for (const [key, value] of Object.entries(obj)) {
        const fullKey = prefix ? `${prefix}.${key}` : key;

        if (value !== null && typeof value === 'object' && !Array.isArray(value)) {
            const nested = flattenObject(value, fullKey);
            Object.assign(result, nested);
        } else {
            result[fullKey] = value;
        }
    }

    return result;
}

// Unflatten dot-notation keys back to nested object
function unflattenObject(flat) {
    const result = {};

    for (const [key, value] of Object.entries(flat)) {
        const parts = key.split('.');
        let current = result;

        for (let i = 0; i < parts.length - 1; i++) {
            const part = parts[i];
            if (!(part in current)) {
                current[part] = {};
            }
            current = current[part];
        }

        current[parts[parts.length - 1]] = value;
    }

    return result;
}

// Format label from key
function formatLabel(key) {
    return key
    .split('.')
    .pop()
    .replace(/_/g, ' ')
    .replace(/([A-Z])/g, ' $1')
    .replace(/^./, str => str.toUpperCase())
    .trim();
}

// Load settings from backend
async function loadSettings() {
    const loading = document.getElementById('settings-loading');
    const error = document.getElementById('settings-error');
    const form = document.getElementById('settings-form');
    const errorMsg = document.getElementById('settings-error-msg');

    loading.style.display = 'flex';
    error.style.display = 'none';
    form.style.display = 'none';

    try {
        const response = await fetch('/settings/load', {
            signal: AbortSignal.timeout(10000)
        });

        if (!response.ok) {
            throw new Error(`Server returned ${response.status}`);
        }

        settingsData = await response.json();
        settingsOriginal = JSON.parse(JSON.stringify(settingsData));

        const categories = organizeSettingsIntoCategories(settingsData);

        renderSettingsForm(categories);
        renderSettingsNav(categories);

        loading.style.display = 'none';
        form.style.display = 'block';
        settingsHasChanges = false;
        updateUnsavedIndicator();

    } catch (err) {
        console.error('Failed to load settings:', err);
        loading.style.display = 'none';
        error.style.display = 'flex';
        errorMsg.textContent = err.message || 'Failed to load settings';
    }
}

// Render settings navigation
function renderSettingsNav(categories) {
    const nav = document.getElementById('settings-nav');
    nav.innerHTML = '';

    const sortedCats = Object.entries(categories)
    .sort(([a, catA], [b, catB]) => (catA.order || 0) - (catB.order || 0));

    sortedCats.forEach(([cat, data], index) => {
        const btn = document.createElement('button');
        btn.className = 'settings-nav-item' + (index === 0 ? ' active' : '');
        btn.dataset.category = cat;
        btn.innerHTML = `
        ${SETTINGS_ICONS[cat] || SETTINGS_ICONS.other}
        <span>${data.title}</span>
        `;
        btn.onclick = () => switchSettingsCategory(cat);
        nav.appendChild(btn);
    });
}

// Switch active settings category
function switchSettingsCategory(category) {
    document.querySelectorAll('.settings-nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.category === category);
    });

    document.querySelectorAll('.settings-section').forEach(section => {
        section.classList.toggle('active', section.dataset.category === category);
    });
}

// Render settings form
function renderSettingsForm(categories) {
    const form = document.getElementById('settings-form');
    form.innerHTML = '';

    const sortedCats = Object.entries(categories)
        .sort(([a, catA], [b, catB]) => (catA.order || 0) - (catB.order || 0));

    for (const [cat, data] of sortedCats) {
        const section = document.createElement('div');
        section.className = 'settings-section';
        section.dataset.category = cat;

        section.innerHTML = `
            <h3 class="settings-section-title">${data.title}</h3>
            <p class="settings-section-desc">${data.description}</p>
        `;

        const itemsContainer = document.createElement('div');
        itemsContainer.className = 'settings-items';

        // Add theme section for appearance
        if (data.isTheme) {
            const themeSection = createThemeSection();
            itemsContainer.appendChild(themeSection);

            if (data.items && data.items.length > 0) {
                const separator = document.createElement('div');
                separator.className = 'settings-separator';
                separator.innerHTML = '<hr style="border: none; border-top: 1px solid var(--border-color); margin: 24px 0;">';
                itemsContainer.appendChild(separator);
            }
        }

        // Track if previous item was a toggle list
        let lastWasToggleList = false;

        // Render items
        for (let i = 0; i < data.items.length; i++) {
            const item = data.items[i];

            // Check if this item belongs to a toggle list's settings
            const keyParts = item.key.split('.');
            const settingsIndex = keyParts.indexOf('settings');

            // Only create collapsible group if NOT directly after a toggle list
            if (settingsIndex !== -1 && settingsIndex < keyParts.length - 2 && !lastWasToggleList) {
                const groupName = keyParts[settingsIndex + 1];
                const groupPath = keyParts.slice(0, settingsIndex + 2).join('.');

                // Find or create group
                let groupContainer = itemsContainer.querySelector(`[data-group="${groupPath}"]`);

                if (!groupContainer) {
                    groupContainer = document.createElement('div');
                    groupContainer.className = 'settings-group';
                    groupContainer.dataset.group = groupPath;
                    groupContainer.innerHTML = `
                        <div class="settings-group-header" onclick="toggleSettingsGroup(this)">
                            <span class="settings-group-title">
                                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"></polyline></svg>
                                ${formatLabel(groupName)} Settings
                            </span>
                        </div>
                        <div class="settings-group-content" style="display: none;"></div>
                    `;
                    itemsContainer.appendChild(groupContainer);
                }

                const groupContent = groupContainer.querySelector('.settings-group-content');
                const itemEl = createSettingItem(item);
                groupContent.appendChild(itemEl);
            } else {
                // Render directly
                const itemEl = createSettingItem(item);
                itemsContainer.appendChild(itemEl);
            }

            // Track if this was a toggle list
            lastWasToggleList = (item.type === 'toggle_list');
        }

        section.appendChild(itemsContainer);
        form.appendChild(section);
    }

    const firstSection = form.querySelector('.settings-section');
    if (firstSection) {
        firstSection.classList.add('active');
    }
}

// Toggle settings group collapse
function toggleSettingsGroup(header) {
    const group = header.closest('.settings-group');
    const content = group.querySelector('.settings-group-content');
    const icon = header.querySelector('svg');
    const isExpanded = content.style.display !== 'none';

    content.style.display = isExpanded ? 'none' : 'block';
    icon.style.transform = isExpanded ? '' : 'rotate(90deg)';
}

// Create a setting item element
function createSettingItem(item) {
    const wrapper = document.createElement('div');
    wrapper.className = 'setting-item';
    wrapper.dataset.key = item.key;

    const label = document.createElement('label');
    label.className = 'setting-label';
    label.textContent = formatLabel(item.key);
    wrapper.appendChild(label);

    // Create appropriate input based on type
    let inputEl;

    switch (item.type) {
        case 'toggle_list':
            inputEl = createToggleListInput(item.key, item.value);
            break;
        case 'boolean':
            inputEl = createToggleInput(item.key, item.value);
            break;
        case 'number':
            inputEl = createNumberInput(item.key, item.value);
            break;
        case 'array':
            inputEl = createArrayInput(item.key, item.value);
            break;
        case 'object':
            inputEl = createObjectInput(item.key, item.value);
            break;
        case 'textarea':
            inputEl = createTextareaInput(item.key, item.value);
            break;
        case 'password':
            inputEl = createPasswordInput(item.key, item.value);
            break;
        default:
            inputEl = createTextInput(item.key, item.value, item.type);
    }

    wrapper.appendChild(inputEl);

    if (item.description) {
        const desc = document.createElement('p');
        desc.className = 'setting-description';
        desc.textContent = item.description;
        wrapper.appendChild(desc);
    }

    return wrapper;
}

// Create toggle list (for enabled/disabled arrays)
function createToggleListInput(key, value) {
    const wrapper = document.createElement('div');
    wrapper.className = 'toggle-list';
    wrapper.dataset.key = key;

    const allItems = getAllToggleItems(value);
    const enabledSet = new Set(value.enabled || []);

    // Status bar
    const status = document.createElement('div');
    status.className = 'toggle-list-status';
    status.innerHTML = `<span class="toggle-count">${enabledSet.size} of ${allItems.length} enabled</span>`;
    wrapper.appendChild(status);

    // Grid of toggles
    const grid = document.createElement('div');
    grid.className = 'toggle-list-grid';

    allItems.forEach(item => {
        const isEnabled = enabledSet.has(item);

        const itemWrapper = document.createElement('div');
        itemWrapper.className = 'toggle-list-item' + (isEnabled ? ' enabled' : '');

        const name = document.createElement('span');
        name.className = 'toggle-list-name';
        name.textContent = formatLabel(item);

        const toggle = document.createElement('div');
        toggle.className = 'toggle-list-switch' + (isEnabled ? ' active' : '');
        toggle.onclick = () => {
            const newState = !toggle.classList.contains('active');
            toggle.classList.toggle('active', newState);
            itemWrapper.classList.toggle('enabled', newState);

            // Update the data
            if (newState) {
                enabledSet.add(item);
            } else {
                enabledSet.delete(item);
            }

            // Update status
            status.querySelector('.toggle-count').textContent =
            `${enabledSet.size} of ${allItems.length} enabled`;

            // Save to settings
            updateToggleListData(key, Array.from(enabledSet), allItems);
        };

        itemWrapper.appendChild(name);
        itemWrapper.appendChild(toggle);
        grid.appendChild(itemWrapper);
    });

    wrapper.appendChild(grid);
    return wrapper;
}

// Update toggle list data in settings
function updateToggleListData(key, enabledItems, allItems) {
    const parts = key.split('.');
    let current = settingsData;

    for (let i = 0; i < parts.length - 1; i++) {
        if (!(parts[i] in current)) {
            current[parts[i]] = {};
        }
        current = current[parts[i]];
    }

    const lastKey = parts[parts.length - 1];

    // Ensure the structure exists
    if (!current[lastKey]) {
        current[lastKey] = { enabled: [], disabled: [] };
    }

    // Update enabled and disabled arrays
    current[lastKey].enabled = enabledItems;
    current[lastKey].disabled = allItems.filter(item => !enabledItems.includes(item));

    settingsHasChanges = JSON.stringify(settingsData) !== JSON.stringify(settingsOriginal);
    updateUnsavedIndicator();
}

// Create text input (with sensitive field detection)
function createTextInput(key, value, type = 'text') {
    const keyLower = key.toLowerCase();
    const isSensitive = keyLower.includes('token') || keyLower.includes('key') ||
    keyLower.includes('secret') || keyLower.includes('password') ||
    keyLower.includes('credential');

    // For sensitive fields, use a reveal/hide toggle
    if (isSensitive) {
        const wrapper = document.createElement('div');
        wrapper.className = 'sensitive-input-wrapper';
        wrapper.dataset.key = key;

        const input = document.createElement('input');
        input.type = 'password';
        input.className = 'setting-input sensitive-input';
        input.value = value ?? '';
        input.dataset.revealed = 'false';

        const toggleBtn = document.createElement('button');
        toggleBtn.type = 'button';
        toggleBtn.className = 'sensitive-toggle';
        toggleBtn.innerHTML = `
        <svg class="eye-closed" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
        <line x1="1" y1="1" x2="23" y2="23"></line>
        </svg>
        <svg class="eye-open" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:none;">
        <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
        <circle cx="12" cy="12" r="3"></circle>
        </svg>
        `;
        toggleBtn.onclick = () => {
            const isRevealed = input.dataset.revealed === 'true';
            if (isRevealed) {
                input.type = 'password';
                input.dataset.revealed = 'false';
                toggleBtn.querySelector('.eye-closed').style.display = '';
                toggleBtn.querySelector('.eye-open').style.display = 'none';
            } else {
                input.type = 'text';
                input.dataset.revealed = 'true';
                toggleBtn.querySelector('.eye-closed').style.display = 'none';
                toggleBtn.querySelector('.eye-open').style.display = '';
            }
        };

        input.oninput = () => handleSettingChange(key, input.value);

        wrapper.appendChild(input);
        wrapper.appendChild(toggleBtn);
        return wrapper;
    }

    // Regular text input
    const input = document.createElement('input');
    input.type = type === 'url' ? 'url' : (type === 'email' ? 'email' : 'text');
    input.className = 'setting-input';
    input.dataset.key = key;
    input.value = value ?? '';
    input.oninput = () => handleSettingChange(key, input.value);
    return input;
}

// Create password input with toggle
function createPasswordInput(key, value) {
    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'position: relative; display: flex; align-items: center;';

    const input = document.createElement('input');
    input.type = 'password';
    input.className = 'setting-input';
    input.dataset.key = key;
    input.value = value ?? '';
    input.style.paddingRight = '40px';
    input.oninput = () => handleSettingChange(key, input.value);

    const toggle = document.createElement('button');
    toggle.type = 'button';
    toggle.className = 'password-toggle';
    toggle.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle></svg>`;
    toggle.style.cssText = 'position: absolute; right: 10px; background: none; border: none; cursor: pointer; color: var(--text-muted); padding: 4px;';
    toggle.onclick = () => {
        input.type = input.type === 'password' ? 'text' : 'password';
    };

    wrapper.appendChild(input);
    wrapper.appendChild(toggle);
    return wrapper;
}

// Create textarea
function createTextareaInput(key, value) {
    const textarea = document.createElement('textarea');
    textarea.className = 'setting-input setting-textarea';
    textarea.dataset.key = key;
    textarea.value = value ?? '';
    textarea.oninput = () => handleSettingChange(key, textarea.value);
    return textarea;
}

// Create number input
function createNumberInput(key, value) {
    const input = document.createElement('input');
    input.type = 'number';
    input.className = 'setting-input';
    input.dataset.key = key;
    input.value = value ?? 0;
    input.step = Number.isInteger(value) ? '1' : '0.01';
    input.oninput = () => handleSettingChange(key, parseFloat(input.value) || 0);
    return input;
}

// Create toggle switch (single boolean)
function createToggleInput(key, value) {
    const wrapper = document.createElement('div');
    wrapper.className = 'setting-toggle-wrapper';

    const toggle = document.createElement('div');
    toggle.className = 'setting-toggle' + (value ? ' active' : '');
    toggle.dataset.key = key;
    toggle.onclick = () => {
        toggle.classList.toggle('active');
        const newValue = toggle.classList.contains('active');
        label.textContent = newValue ? 'Enabled' : 'Disabled';
        handleSettingChange(key, newValue);
    };

    const label = document.createElement('span');
    label.className = 'setting-toggle-label';
    label.textContent = value ? 'Enabled' : 'Disabled';

    wrapper.appendChild(toggle);
    wrapper.appendChild(label);
    return wrapper;
}

// Create array input
function createArrayInput(key, value) {
    const wrapper = document.createElement('div');
    wrapper.className = 'setting-array';
    wrapper.dataset.key = key;

    const items = Array.isArray(value) ? [...value] : [];

    const header = document.createElement('div');
    header.className = 'setting-array-header';
    header.innerHTML = `
    <span class="setting-array-count">${items.length} item${items.length !== 1 ? 's' : ''}</span>
    <button class="setting-array-add" type="button">
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
    Add
    </button>
    `;

    const itemsContainer = document.createElement('div');
    itemsContainer.className = 'setting-array-items';

    function renderItems() {
        itemsContainer.innerHTML = '';
        header.querySelector('.setting-array-count').textContent = `${items.length} item${items.length !== 1 ? 's' : ''}`;

        if (items.length === 0) {
            itemsContainer.innerHTML = '<div class="setting-array-empty">No items added</div>';
            return;
        }

        items.forEach((item, index) => {
            const itemEl = document.createElement('div');
            itemEl.className = 'setting-array-item';

            const input = document.createElement('input');
            input.type = 'text';
            input.value = item;
            input.oninput = () => {
                items[index] = input.value;
                handleSettingChange(key, [...items]);
            };

            const removeBtn = document.createElement('button');
            removeBtn.className = 'setting-array-remove';
            removeBtn.type = 'button';
            removeBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;
            removeBtn.onclick = () => {
                items.splice(index, 1);
                renderItems();
                handleSettingChange(key, [...items]);
            };

            itemEl.appendChild(input);
            itemEl.appendChild(removeBtn);
            itemsContainer.appendChild(itemEl);
        });
    }

    header.querySelector('.setting-array-add').onclick = () => {
        items.push('');
        renderItems();
        handleSettingChange(key, [...items]);
        const lastInput = itemsContainer.querySelector('.setting-array-item:last-child input');
        if (lastInput) lastInput.focus();
    };

        renderItems();
        wrapper.appendChild(header);
        wrapper.appendChild(itemsContainer);
        return wrapper;
}

// Create object input
function createObjectInput(key, value) {
    const entries = value && typeof value === 'object' ? Object.entries(value) : [];

    const wrapper = document.createElement('div');
    wrapper.className = 'setting-object';
    wrapper.dataset.key = key;

    const header = document.createElement('div');
    header.className = 'setting-object-header';
    header.innerHTML = `<span>${entries.length} propert${entries.length !== 1 ? 'ies' : 'y'}</span>`;

    const itemsContainer = document.createElement('div');
    itemsContainer.className = 'setting-object-items';

    function renderEntries() {
        itemsContainer.innerHTML = '';
        header.querySelector('span').textContent = `${entries.length} propert${entries.length !== 1 ? 'ies' : 'y'}`;

        if (entries.length === 0) {
            itemsContainer.innerHTML = '<div class="setting-array-empty">No properties</div>';
            return;
        }

        entries.forEach(([k, v], index) => {
            const itemEl = document.createElement('div');
            itemEl.className = 'setting-object-item';

            const keyInput = document.createElement('input');
            keyInput.type = 'text';
            keyInput.value = k;
            keyInput.placeholder = 'Key';
            keyInput.oninput = () => {
                entries[index][0] = keyInput.value;
                updateObjectValue();
            };

            const valueInput = document.createElement('input');
            valueInput.type = 'text';
            valueInput.value = typeof v === 'object' ? JSON.stringify(v) : String(v ?? '');
            valueInput.placeholder = 'Value';
            valueInput.oninput = () => {
                try {
                    entries[index][1] = JSON.parse(valueInput.value);
                } catch {
                    entries[index][1] = valueInput.value;
                }
                updateObjectValue();
            };

            const removeBtn = document.createElement('button');
            removeBtn.className = 'setting-array-remove';
            removeBtn.type = 'button';
            removeBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;
            removeBtn.onclick = () => {
                entries.splice(index, 1);
                renderEntries();
                updateObjectValue();
            };

            itemEl.appendChild(keyInput);
            itemEl.appendChild(valueInput);
            itemEl.appendChild(removeBtn);
            itemsContainer.appendChild(itemEl);
        });
    }

    function updateObjectValue() {
        const obj = {};
        entries.forEach(([k, v]) => {
            if (k) obj[k] = v;
        });
            handleSettingChange(key, obj);
    }

    const addBtn = document.createElement('button');
    addBtn.className = 'setting-object-add';
    addBtn.type = 'button';
    addBtn.textContent = '+ Add Property';
    addBtn.onclick = () => {
        entries.push(['', '']);
        renderEntries();
    };

    renderEntries();
    wrapper.appendChild(header);
    wrapper.appendChild(itemsContainer);
    wrapper.appendChild(addBtn);
    return wrapper;
}

// Handle setting change
function handleSettingChange(key, value) {
    const parts = key.split('.');
    let current = settingsData;

    for (let i = 0; i < parts.length - 1; i++) {
        if (!(parts[i] in current)) {
            current[parts[i]] = {};
        }
        current = current[parts[i]];
    }

    current[parts[parts.length - 1]] = value;

    settingsHasChanges = JSON.stringify(settingsData) !== JSON.stringify(settingsOriginal);
    updateUnsavedIndicator();
}

// Update unsaved changes indicator
function updateUnsavedIndicator() {
    const form = document.getElementById('settings-form');
    let indicator = form.querySelector('.settings-unsaved');

    if (settingsHasChanges && !indicator) {
        indicator = document.createElement('div');
        indicator.className = 'settings-unsaved';
        indicator.innerHTML = `
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
        You have unsaved changes
        `;
        form.insertBefore(indicator, form.firstChild);
    } else if (!settingsHasChanges && indicator) {
        indicator.remove();
    }
}

// Reset settings form
function resetSettingsForm() {
    if (!settingsHasChanges) return;
    if (!confirm('Reset all changes to original values?')) return;

    settingsData = JSON.parse(JSON.stringify(settingsOriginal));
    settingsHasChanges = false;

    const categories = organizeSettingsIntoCategories(settingsData);
    renderSettingsForm(categories);
    updateUnsavedIndicator();
}

// Save settings to backend
async function saveSettings() {
    if (!settingsHasChanges) return;

    const saveBtn = document.getElementById('settings-save-btn');
    const btnText = saveBtn.querySelector('.btn-text');
    const btnLoading = saveBtn.querySelector('.btn-loading');

    saveBtn.disabled = true;
    btnText.style.display = 'none';
    btnLoading.style.display = 'flex';

    try {
        const response = await fetch('/settings/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settingsData),
                                     signal: AbortSignal.timeout(30000)
        });

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            throw new Error(error.message || `Server returned ${response.status}`);
        }

        settingsOriginal = JSON.parse(JSON.stringify(settingsData));
        settingsHasChanges = false;
        showSettingsSuccess();

    } catch (err) {
        console.error('Failed to save settings:', err);
        showSettingsError(err.message || 'Failed to save settings');
    } finally {
        saveBtn.disabled = false;
        btnText.style.display = 'inline';
        btnLoading.style.display = 'none';
    }
}

// Show success message
function showSettingsSuccess() {
    const form = document.getElementById('settings-form');
    const existing = form.querySelector('.setting-success-msg');
    if (existing) existing.remove();

    const success = document.createElement('div');
    success.className = 'setting-success-msg';
    success.innerHTML = `
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>
    Settings saved successfully!
    `;

    form.insertBefore(success, form.firstChild);
    setTimeout(() => success.remove(), 3000);
}

// Show error message
function showSettingsError(message) {
    const form = document.getElementById('settings-form');
    const existing = form.querySelector('.setting-error-msg');
    if (existing) existing.remove();

    const error = document.createElement('div');
    error.className = 'setting-error-msg';
    error.innerHTML = `
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
    ${escapeHtml(message)}
    `;

    form.insertBefore(error, form.firstChild);
}

// Theme section
function createThemeSection() {
    const wrapper = document.createElement('div');
    wrapper.className = 'settings-theme-section';

    const savedFamily = localStorage.getItem('themeFamily') || 'default';
    const savedMode = localStorage.getItem('themeMode') || 'dark';
    const families = getThemeFamilies();

    const themeLabel = document.createElement('h4');
    themeLabel.textContent = 'Color Theme';
    wrapper.appendChild(themeLabel);

    const themeGrid = document.createElement('div');
    themeGrid.className = 'theme-grid';
    themeGrid.id = 'theme-grid-settings';

    families.forEach((variants, family) => {
        const previewThemeId = variants.dark || variants.light;
        const previewTheme = themes[previewThemeId];
        if (!previewTheme) return;

        const btn = document.createElement('button');
        btn.className = 'theme-btn' + (family === savedFamily ? ' active' : '');
        btn.dataset.family = family;
        btn.type = 'button';

        const bgColor = previewTheme.vars['--bg-primary'];
        const accentColor = previewTheme.vars['--accent'];
        const hasBothModes = variants.dark && variants.light;

        btn.innerHTML = `
        <div class="theme-preview" style="background: linear-gradient(135deg, ${bgColor} 50%, ${accentColor} 50%);">
        ${hasBothModes ? '<span class="theme-badge">◐</span>' : ''}
        </div>
        <span class="theme-name">${family.charAt(0).toUpperCase() + family.slice(1)}</span>
        `;

        btn.onclick = () => {
            currentThemeFamily = family;
            applyTheme(family, currentThemeMode);
            updateThemeButtonsInSettings();
        };

        themeGrid.appendChild(btn);
    });

    wrapper.appendChild(themeGrid);

    const modeLabel = document.createElement('h4');
    modeLabel.textContent = 'Appearance Mode';
    modeLabel.style.marginTop = '20px';
    wrapper.appendChild(modeLabel);

    const modeToggle = document.createElement('div');
    modeToggle.className = 'theme-mode-toggle';

    modeToggle.innerHTML = `
    <span class="theme-mode-label">
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>
    Dark
    </span>
    <label class="theme-switch">
    <input type="checkbox" id="theme-mode-checkbox-settings" ${savedMode === 'light' ? 'checked' : ''}>
    <span class="theme-slider"></span>
    </label>
    <span class="theme-mode-label">
    Light
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>
    </span>
    `;

    const checkbox = modeToggle.querySelector('#theme-mode-checkbox-settings');
    checkbox.addEventListener('change', function() {
        const mode = this.checked ? 'light' : 'dark';
        currentThemeMode = mode;
        applyTheme(currentThemeFamily, mode);
        updateThemeButtonsInSettings();
    });

    wrapper.appendChild(modeToggle);
    return wrapper;
}

function getThemeFamilies() {
    const families = new Map();
    Object.keys(themes).forEach(themeId => {
        const { mode, family } = parseThemeId(themeId);
        if (!families.has(family)) {
            families.set(family, { dark: null, light: null });
        }
        families.get(family)[mode] = themeId;
    });
    return families;
}

function updateThemeButtonsInSettings() {
    const grid = document.getElementById('theme-grid-settings');
    if (!grid) return;

    grid.querySelectorAll('.theme-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.family === currentThemeFamily);
    });

    const checkbox = document.getElementById('theme-mode-checkbox-settings');
    if (checkbox) {
        checkbox.checked = (currentThemeMode === 'light');
    }
}

// Override toggleModal for settings
const originalToggleModal = toggleModal;
toggleModal = function(modalName) {
    if (modalName === 'settings') {
        const overlay = document.getElementById('settings-overlay');
        const modal = document.getElementById('settings-modal');

        if (overlay.classList.contains('show')) {
            if (settingsHasChanges) {
                if (!confirm('You have unsaved changes. Close without saving?')) {
                    return;
                }
            }
            overlay.classList.remove('show');
            modal.classList.remove('show');
        } else {
            overlay.classList.add('show');
            modal.classList.add('show');
            loadSettings();
        }
    } else {
        originalToggleModal(modalName);
    }
};

// =============================================================================
// Service Worker Registration
// =============================================================================

if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js')
            .then(reg => console.log('Service Worker registered'))
            .catch(err => console.log('Service Worker registration failed:', err));
    });
}

// =============================================================================
// Cleanup Function
// =============================================================================

function cleanup() {
    if (pollIntervalId) {
        clearInterval(pollIntervalId);
        pollIntervalId = null;
    }
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
    hideConnectionStatus();
}

window.addEventListener('beforeunload', cleanup);

// =============================================================================
// Initialization
// =============================================================================

updateConnectionStatus('connecting');

async function init() {
    try {
        await checkConnection();

        // Load current conversation from backend if available
        if (isConnected) {
            await restoreCurrentConversation();
        }
    } catch (err) {
        isConnected = false;
        updateConnectionStatus('disconnected');
        scheduleReconnect();
    }

    loadTheme();
    loadConversations();
    requestNotificationPermission();

    pollIntervalId = setInterval(() => {
        if (isConnected) {
            pollMessages();
        }
    }, CONFIG.POLL_INTERVAL);
}

init();
