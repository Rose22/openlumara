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

    messages.forEach((msg) => {
        const wrapper = createMessageElement(msg, msg.index, animate);  // Use msg.index
    });

    scrollToBottom();
}

function createMessageElement(msg, index, animate = false) {
    const role = msg.role || 'user';
    const rawContent = msg.content || '';
    const timestamp = msg.timestamp || formatTime();

    const parsed = parseMessageContent(rawContent);
    const displayContent = parsed.displayContent || rawContent;

    let wrapperClass, msgClass;

    if (parsed.isAnnouncement) {
        wrapperClass = 'announce';
        msgClass = `announce ${parsed.type}`;
    } else if (parsed.isCommandOutput) {
        wrapperClass = 'command_response';
        msgClass = 'command_response';
    } else if (role === 'tool') {
        wrapperClass = 'tool';
        msgClass = 'tool';
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

    // Render based on message type
    if (parsed.isAnnouncement) {
        msgDiv.innerHTML = escapeHtml(displayContent);
    } else if (role === 'tool') {
        msgDiv.innerHTML = renderToolMessage(rawContent);
    } else if (role === 'schedule') {
        msgDiv.innerHTML = renderScheduleMessage(rawContent);
    } else if (parsed.isCommandOutput || wrapperClass === 'user_command') {
        msgDiv.innerHTML = `<pre>${escapeHtml(displayContent)}</pre>`;
    } else if (role === 'user') {
        msgDiv.innerHTML = renderMarkdown(displayContent);
        highlightCode(msgDiv);
    } else {
        msgDiv.innerHTML = renderMarkdown(displayContent);
        highlightCode(msgDiv);
    }

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
    wrapper.appendChild(msgDiv);

    if (role === 'user' || role === 'assistant') {
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

function renderToolMessage(content) {
    let data;
    try {
        data = typeof content === 'string' ? JSON.parse(content) : content;
    } catch (e) {
        return `<pre>${escapeHtml(content)}</pre>`;
    }

    const toolName = data.name || data.tool || data.function || 'Tool';
    const status = data.status || data.result?.status || 'success';
    const args = data.arguments || data.args || data.params || null;
    const result = data.result || data.output || data.response || data;

    const statusClass = status === 'error' ? 'error' : 'success';
    const statusIcon = status === 'error'
        ? `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`
        : `<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`;

    let html = `
        <div class="tool-header">
            <svg class="tool-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
            </svg>
            <span class="tool-name">${escapeHtml(toolName)}</span>
            <span class="tool-status ${statusClass}">${statusIcon} ${escapeHtml(status)}</span>
        </div>
    `;

    if (args && Object.keys(args).length > 0) {
        html += `<div class="tool-args"><strong>Arguments:</strong> ${escapeHtml(JSON.stringify(args))}</div>`;
    }

    /*
    if (result) {
        const resultStr = typeof result === 'string' ? result : JSON.stringify(result, null, 2);
        html += `<div class="tool-result"><pre>${escapeHtml(resultStr)}</pre></div>`;
    }
    */

    return html;
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
    // Handle schedule actions (cancel, snooze, etc.)
    console.log('Schedule action:', type, id);
    // You can implement this to send requests to your backend
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

        if (data.messages && data.messages.length > 0) {
            for (const msg of data.messages) {
                const parsed = parseMessageContent(msg.content);

                // During streaming, allow announcements and command-related messages through
                if (isStreaming && !parsed.isAnnouncement) {
                    const isUserCommand = msg.role === 'user' && msg.content.trim().startsWith('/');
                    const isCommandOutput = parsed.isCommandOutput;
                    if (!isUserCommand && !isCommandOutput) continue;
                }

                // Show browser notification for announcements (always)
                if (parsed.isAnnouncement) {
                    showAnnouncementNotification(
                        parsed.displayContent,
                        parsed.type.replace('announce_', '')
                    );
                }

                // Check if message already exists
                const existing = chat.querySelector(`[data-index="${msg.index}"]`);
                if (!existing) {
                    createMessageElement(msg, msg.index, true);
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

        if (data.messages) {
            renderAllMessages(data.messages);
            lastMessageIndex = data.count;
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

        if (data.success && data.current_id && data.conversation) {
            currentConversationId = data.current_id;
            const messages = data.conversation.messages || [];

            if (messages.length > 0) {
                renderAllMessages(messages);
                lastMessageIndex = messages.length;
            }
        }
    } catch (e) {
        console.error('Failed to restore current conversation:', e);
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

        // Store conversation data on the element for easy access during filtering
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

        const renameBtn = document.createElement('button');
        renameBtn.className = 'conv-action-btn rename';
        renameBtn.textContent = 'Rename';
        renameBtn.onclick = (e) => {
            e.stopPropagation();
            renameConversation(conv.id, conv.title);
        };

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'conv-action-btn delete';
        deleteBtn.textContent = 'Delete';
        deleteBtn.onclick = (e) => {
            e.stopPropagation();
            deleteConversation(conv.id);
        };

        actions.appendChild(renameBtn);
        actions.appendChild(deleteBtn);
        meta.appendChild(date);
        meta.appendChild(actions);

        item.appendChild(title);
        item.appendChild(meta);
        list.appendChild(item);
    });

    // Re-apply filter after render
    if (currentSearchQuery) {
        filterConversations(currentSearchQuery);
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

async function newConversation() {
    if (lastMessageIndex > 0) {
        await saveCurrentConversation();
    }

    try {
        await fetch('/send', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: '/new' })
        });
    } catch (e) {
        console.error('Failed to clear backend:', e);
    }

    currentConversationId = null;
    lastMessageIndex = 0;

    const wrappers = chat.querySelectorAll('.message-wrapper');
    wrappers.forEach(wrapper => wrapper.remove());

    await loadConversations();
    closeSidebar();
}

async function loadConversation(convId) {
    try {
        const response = await fetch('/conversation/load?id=' + convId);
        const data = await response.json();

        if (data.success && data.conversation) {
            currentConversationId = convId;
            renderAllMessages(data.conversation.messages || [], true);
            lastMessageIndex = data.conversation.messages.length;
            await loadConversations();
            closeSidebar();
        }
    } catch (e) {
        console.error('Failed to load conversation:', e);
    }
}

async function saveCurrentConversation() {
    if (lastMessageIndex === 0) return;

    try {
        const response = await fetch('/conversation/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: currentConversationId })
        });

        const data = await response.json();
        if (data.success) {
            currentConversationId = data.id;
            await loadConversations();
        }
    } catch (e) {
        console.error('Failed to save conversation:', e);
    }
}

async function deleteConversation(convId) {
    if (!confirm('Delete this conversation?')) return;

    try {
        const response = await fetch('/conversation/delete?id=' + convId, { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            if (currentConversationId === convId) {
                currentConversationId = null;
                const wrappers = chat.querySelectorAll('.message-wrapper');
                wrappers.forEach(wrapper => wrapper.remove());
                lastMessageIndex = 0;
            }
            await loadConversations();
        }
    } catch (e) {
        console.error('Failed to delete conversation:', e);
    }
}

async function renameConversation(convId, currentTitle) {
    const newTitle = prompt('Enter new name:', currentTitle);
    if (!newTitle || newTitle.trim() === '' || newTitle === currentTitle) return;

    try {
        const response = await fetch('/conversation/rename', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: convId, title: newTitle.trim() })
        });

        const data = await response.json();
        if (data.success) {
            await loadConversations();
        } else {
            alert('Failed to rename: ' + data.error);
        }
    } catch (e) {
        console.error('Failed to rename conversation:', e);
    }
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
    if (message.trim().startsWith('/')) {
        clearInput();
        return sendCommand(message);
    }

    if (isStreaming) return;

    clearInput();

    const userWrapper = document.createElement('div');

    if (message.trim().startsWith('/')) {
        userWrapper.className = 'message-wrapper user_command';
    } else {
        userWrapper.className = 'message-wrapper user';
    }

    userWrapper.classList.add('animate-in');

    userWrapper.setAttribute('role', 'article');
    userWrapper.dataset.index = 'pending';

    const userMsgDiv = document.createElement('div');
    if (message.trim().startsWith('/')) {
        userMsgDiv.className = 'message user_command';
        userMsgDiv.innerHTML = `<pre>${escapeHtml(message)}</pre>`;
    } else {
        userMsgDiv.className = 'message user';
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
    let streamStarted = false;

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

                        if (data.token) {
                            if (!streamStarted) {
                                streamStarted = true;
                                typing.classList.remove('show');
                                aiWrapper.classList.remove('hidden');
                            }
                            aiContent += data.token;
                            aiMsgDiv.innerHTML = renderMarkdown(aiContent);
                            highlightCode(aiMsgDiv);
                            scrollToBottomDelayed();
                        }

                        if (data.done) {
                            // handle in finally()
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
        finishStream();
        userWrapper.remove();
        aiWrapper.remove();
        await syncMessages();
        await saveCurrentConversation();
    }
}

function finishStream() {
    setInputState(false, false, false);
    isStreaming = false;
    currentController = null;
    currentStreamId = null;
    inputField.focus();
}

async function sendCommand(message) {
    try {
        if (message.startsWith("/stop")) {
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

let currentTheme = 'dark-black';

function applyTheme(themeId) {
    const theme = themes[themeId];
    if (!theme) return;

    const root = document.documentElement;
    for (const [varName, value] of Object.entries(theme.vars)) {
        root.style.setProperty(varName, value);
    }

    currentTheme = themeId;
    localStorage.setItem('theme', themeId);
    updateThemeButtons();
}

function updateThemeButtons() {
    document.querySelectorAll('.theme-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.theme === currentTheme);
    });
}

function createThemeButtons() {
    const grid = document.getElementById('theme-grid');
    grid.innerHTML = '';

    Object.entries(themes).forEach(([id, theme]) => {
        const btn = document.createElement('button');
        btn.className = 'theme-btn' + (id === currentTheme ? ' active' : '');
        btn.dataset.theme = id;

        const bgColor = theme.vars['--bg-primary'];
        const accentColor = theme.vars['--accent'];

        btn.innerHTML = `
            <div class="theme-preview" style="background: linear-gradient(135deg, ${bgColor} 50%, ${accentColor} 50%);"></div>
            ${theme.name}
        `;

        btn.onclick = () => applyTheme(id);
        grid.appendChild(btn);
    });
}

function loadTheme() {
    const saved = localStorage.getItem('theme');
    if (saved && themes[saved]) {
        applyTheme(saved);
    } else {
        applyTheme('dark-black');
    }
    createThemeButtons();
}

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
