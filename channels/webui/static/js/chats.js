// =============================================================================
// Chats
// =============================================================================

async function loadChats() {
    try {
        const [chatResponse, tagsResponse] = await Promise.all([
            fetch('/chats'),
                                                               fetch('/chat/tags')
        ]);

        const chatData = await chatResponse.json();
        const tagsData = await tagsResponse.json();

        allTags = tagsData.tags || [];
        renderTagFilter();
        renderChatList(chatData.chats || []);
    } catch (e) {
        console.error('Failed to load chats:', e);
    }
}

async function restoreCurrentChat() {
    try {
        const response = await fetch('/chat/current');
        const data = await response.json();

        if (data.success && data.chat && data.chat.id) {
            currentChatId = data.chat.id;
            const messages = data.chat.messages || [];
            const tags = data.chat.tags || [];

            updateChatTitleBar(data.chat.title, tags);

            if (messages.length > 0) {
                renderAllMessages(messages);
                lastMessageIndex = messages.length;
            } else {
                const wrappers = chat.querySelectorAll('.message-wrapper');
                wrappers.forEach(wrapper => wrapper.remove());
                lastMessageIndex = 0;
            }
        } else {
            currentChatId = null;
            lastMessageIndex = 0;
            const wrappers = chat.querySelectorAll('.message-wrapper');
            wrappers.forEach(wrapper => wrapper.remove());
            updateChatTitleBar(null);
        }
    } catch (e) {
        console.error('Failed to restore current chat:', e);
        currentChatId = null;
        updateChatTitleBar(null);
    }
}

async function getCurrentChatId() {
    try {
        const response = await fetch('/chat/current');
        const data = await response.json();

        if (data.success && data.chat && data.chat.id) {
            currentChatId = data.chat.id;
            return data.chat.id;
        }
        return null;
    } catch (e) {
        console.error('Failed to get current chat ID:', e);
        return null;
    }
}

function renderChatList(chats) {
    allChats = chats;

    const list = document.getElementById('chat-list');
    const searchInput = document.getElementById('chat-search');
    const currentSearchQuery = searchInput ? searchInput.value : '';

    list.innerHTML = '';

    if (chats.length === 0) {
        const emptyMsg = document.createElement('div');
        emptyMsg.className = 'chat-empty';
        emptyMsg.textContent = 'No chats yet';
        emptyMsg.style.cssText = 'padding: 20px; text-align: center; color: var(--text-muted); font-size: 0.85rem;';
        list.appendChild(emptyMsg);
        return;
    }

    chats.forEach(chat => {
        const item = document.createElement('div');
        item.className = 'chat-item' + (chat.id === currentChatId ? ' active' : '');

        item.dataset.chatId = chat.id;
        item.dataset.chatData = JSON.stringify(chat);

        item.onclick = (e) => {
            // Don't trigger load if clicking on action buttons or editing
            if (e.target.closest('.chat-item-actions') ||
                e.target.closest('.inline-rename-container')) {
                return;
                }
                loadChat(chat.id);
        };

        const title = document.createElement('div');
        title.className = 'chat-item-title';
        title.textContent = chat.title || 'New chat';

        // Tags container
        const tagsContainer = document.createElement('div');
        tagsContainer.className = 'chat-tags';

        const tags = chat.tags || [];
        const meta = document.createElement('div');
        meta.className = 'chat-item-meta';

        const date = document.createElement('span');
        date.textContent = formatDate(chat.updated || chat.created);

        const actions = document.createElement('div');
        actions.className = 'chat-item-actions';

        const editBtn = document.createElement('button');
        editBtn.className = 'chat-action-btn edit';
        editBtn.innerHTML = ICONS.edit;
        editBtn.setAttribute('aria-label', 'Rename');
        editBtn.setAttribute('title', 'Rename');
        editBtn.onclick = (e) => {
            e.stopPropagation();
            renameChat(chat.id, chat.title || 'New chat');
        };

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'chat-action-btn delete';
        deleteBtn.innerHTML = ICONS.trash;
        deleteBtn.setAttribute('aria-label', 'Delete');
        deleteBtn.setAttribute('title', 'Delete');
        deleteBtn.onclick = (e) => {
            e.stopPropagation();
            deleteChat(chat.id);
        };

        actions.appendChild(editBtn);
        actions.appendChild(deleteBtn);
        meta.appendChild(date);
        meta.appendChild(actions);
        if (tags.length > 0) {
            renderFittedTags(tagsContainer, tags, {
                maxStart: 3,
                minTags: 1,
                showTooltip: true
            });
            item.appendChild(tagsContainer);
        }
        item.appendChild(title);
        item.appendChild(meta);
        list.appendChild(item);
    });

    // Apply active tag filter
    if (activeTagFilter) {
        filterChatsByTag();
    }

    // Apply text search if active
    if (currentSearchQuery) {
        filterChats(currentSearchQuery);
    }
}


async function newChat() {
    if (isStreaming) {
        return;
    }

    try {
        const response = await fetch('/chat/new', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: 'New chat' })
        });

        const data = await response.json();

        if (data.success && data.chat) {
            currentChatId = data.chat.id;
            lastMessageIndex = 0;

            updateChatTitleBar(data.chat.title);

            const wrappers = chat.querySelectorAll('.message-wrapper');
            wrappers.forEach(wrapper => wrapper.remove());

            await loadChats();
            closeSidebar();
        }
    } catch (e) {
        console.error('Failed to create new chat:', e);
    }
}


// Internal helper to load a chat without closing the sidebar
async function loadChatInternal(chatId, cachedMessages = null) {
    try {
        // Use cached messages if available (avoids extra fetch)
        if (cachedMessages) {
            currentChatId = chatId;
            renderAllMessages(cachedMessages);
            lastMessageIndex = cachedMessages.length;
            return;
        }

        const response = await fetch('/chat/load?id=' + chatId);
        const data = await response.json();

        if (data.success && data.chat) {
            currentChatId = chatId;
            renderAllMessages(data.chat.messages || []);
            lastMessageIndex = (data.chat.messages || []).length;
        }
    } catch (e) {
        console.error('Failed to load chat internally:', e);
    }
}

async function loadChat(chatId) {
    if (isStreaming) {
        return;
    }

    try {
        const response = await fetch('/chat/load?id=' + chatId);
        const data = await response.json();

        if (data.success && data.chat) {
            currentChatId = chatId;
            const messages = data.chat.messages || [];
            renderAllMessages(messages, true);
            lastMessageIndex = data.chat.total ||
            (messages.length > 0 ? messages[messages.length - 1].index + 1 : 0);

            // Update the titlebar with title and tags
            updateChatTitleBar(
                data.chat.title,
                data.chat.tags || []
            );

            await loadChats();
            closeSidebar();
        } else {
            console.error('Failed to load chat:', data.error);
        }
    } catch (e) {
        console.error('Failed to load chat:', e);
    }
}

// Note: Chats are auto-saved by the backend when messages are added.
// No explicit save endpoint exists. This function is kept for potential future use
// or for triggering a UI state sync.
async function saveCurrentChat() {
    // Backend auto-saves, so this is a no-op for now
    // Refresh the chat list to reflect any changes
    await loadChats();
}

async function deleteChat(chatId) {
    if (!confirm('Delete this chat?')) return;

    try {
        const response = await fetch('/chat/delete?id=' + chatId, {
            method: 'POST'
        });
        const data = await response.json();

        if (data.success) {
            // Sync with backend's chat.current
            await restoreCurrentChat();

            // Force refresh the chat list
            await loadChats();

            // Close sidebar on mobile
            closeSidebar();
        } else {
            console.error('Failed to delete:', data.error);
            alert('Failed to delete chat: ' + (data.error || 'Unknown error'));
        }
    } catch (e) {
        console.error('Failed to delete chat:', e);
        alert('Failed to delete chat');
    }
}

async function renameChat(chatId, currentTitle) {
    const chatItem = document.querySelector(`[data-chat-id="${chatId}"]`);
    if (!chatItem) return;

    const titleEl = chatItem.querySelector('.chat-item-title');
    if (!titleEl) return;

    // Don't start editing if already editing
    if (titleEl.dataset.editing === 'true') return;

    userIsEditing = true;

    // Create inline edit container
    const editContainer = document.createElement('div');
    editContainer.className = 'inline-rename-container sidebar-rename';

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'inline-rename-input';
    input.value = currentTitle;

    const actions = document.createElement('div');
    actions.className = 'inline-rename-actions';

    const saveBtn = document.createElement('button');
    saveBtn.className = 'inline-rename-btn save';
    saveBtn.innerHTML = ICONS.check;
    saveBtn.setAttribute('aria-label', 'Save');

    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'inline-rename-btn cancel';
    cancelBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;
    cancelBtn.setAttribute('aria-label', 'Cancel');

    actions.appendChild(cancelBtn);
    actions.appendChild(saveBtn);

    editContainer.appendChild(input);
    editContainer.appendChild(actions);

    // Store original
    const originalContent = titleEl.innerHTML;
    titleEl.innerHTML = '';
    titleEl.appendChild(editContainer);
    titleEl.dataset.editing = 'true';

    input.focus();
    input.select();

    // Cleanup function
    const cleanup = () => {
        titleEl.innerHTML = originalContent;
        delete titleEl.dataset.editing;
        userIsEditing = false;
    };

    // Save function
    const saveRename = async () => {
        const newTitle = input.value.trim();
        if (!newTitle || newTitle === currentTitle) {
            cleanup();
            return;
        }

        // The backend only allows renaming the CURRENT chat
        // Strategy: if renaming a different chat, load it first, rename, then restore
        const wasCurrentChat = currentChatId === chatId;
        const previousConvId = currentChatId;

        try {
            // If this is not the current chat, we need to load it first
            if (!wasCurrentChat) {
                const loadResponse = await fetch('/chat/load?id=' + chatId);
                const loadData = await loadResponse.json();

                if (!loadData.success) {
                    alert('Failed to load chat for renaming');
                    cleanup();
                    return;
                }
            }

            // Now rename it (it's the current chat)
            const response = await fetch('/chat/rename', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: newTitle })
            });

            const data = await response.json();

            if (data.success) {
                // Refresh chat list
                await loadChats();

                // If we loaded a different chat, restore the previous one
                if (!wasCurrentChat && previousConvId) {
                    await loadChatInternal(previousConvId);
                }

                // Update the current chat ID if we renamed the current one
                if (wasCurrentChat) {
                    // Title changed but ID stays the same
                    const titleText = document.getElementById('chat-title-text');
                    if (titleText) {
                        titleText.textContent = newTitle;
                    }
                }
            } else {
                alert('Failed to rename: ' + (data.error || 'Unknown error'));

                // Restore previous chat if we changed it
                if (!wasCurrentChat && previousConvId) {
                    await loadChatInternal(previousConvId);
                }
            }
        } catch (e) {
            console.error('Failed to rename chat:', e);

            // Restore previous chat if we changed it
            if (!wasCurrentChat && previousConvId) {
                try {
                    await loadChatInternal(previousConvId);
                } catch (restoreErr) {
                    console.error('Failed to restore chat:', restoreErr);
                }
            }
        }

        cleanup();
    };

    // Event handlers
    saveBtn.onclick = saveRename;
    cancelBtn.onclick = cleanup;

    input.onkeydown = (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            saveRename();
        }
        if (e.key === 'Escape') {
            e.preventDefault();
            cleanup();
        }
    };

    input.onblur = (e) => {
        setTimeout(() => {
            if (titleEl.dataset.editing === 'true' &&
                !editContainer.contains(document.activeElement)) {
                cleanup();
                }
        }, 100);
    };
}2

// =============================================================================
// Chat Title Bar Management
// =============================================================================

function updateChatTitleBar(title = null, tags = []) {
    const titleBar = document.getElementById('chat-title-bar');
    const titleText = document.getElementById('chat-title-text');
    const tagsContainer = document.getElementById('chat-title-tags');

    if (!title && currentChatId === null) {
        titleBar.classList.add('no-chat');
        titleText.textContent = 'New chat';
        tagsContainer.innerHTML = '';
        titleBar.classList.remove('has-tags');
        currentTitleBarTags = [];
    } else {
        titleBar.classList.remove('no-chat');
        titleText.textContent = title || 'New chat';
        currentTitleBarTags = tags || [];

        if (tagsContainer) {
            if (tags && tags.length > 0) {
                titleBar.classList.add('has-tags');
                renderTitleBarTags();
            } else {
                tagsContainer.innerHTML = '';
                titleBar.classList.remove('has-tags');
            }
        }
    }
}

async function renameCurrentChat() {
    if (currentChatId === null) {
        return;
    }

    const titleText = document.getElementById('chat-title-text');
    const currentTitle = titleText.textContent;

    // Don't start editing if already editing
    if (titleText.dataset.editing === 'true') return;

    userIsEditing = true;

    // Create inline edit container
    const editContainer = document.createElement('div');
    editContainer.className = 'inline-rename-container';

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'inline-rename-input';
    input.value = currentTitle;
    input.setAttribute('aria-label', 'Edit chat name');

    const actions = document.createElement('div');
    actions.className = 'inline-rename-actions';

    const saveBtn = document.createElement('button');
    saveBtn.className = 'inline-rename-btn save';
    saveBtn.innerHTML = ICONS.check;
    saveBtn.setAttribute('aria-label', 'Save');
    saveBtn.setAttribute('title', 'Save');

    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'inline-rename-btn cancel';
    cancelBtn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;
    cancelBtn.setAttribute('aria-label', 'Cancel');
    cancelBtn.setAttribute('title', 'Cancel');

    actions.appendChild(cancelBtn);
    actions.appendChild(saveBtn);

    editContainer.appendChild(input);
    editContainer.appendChild(actions);

    // Store original element state
    const originalContent = titleText.innerHTML;
    titleText.innerHTML = '';
    titleText.appendChild(editContainer);
    titleText.dataset.editing = 'true';

    input.focus();
    input.select();

    // Cleanup function
    const cleanup = () => {
        titleText.innerHTML = originalContent;
        delete titleText.dataset.editing;
        userIsEditing = false;
    };

    // Save function
    const saveRename = async () => {
        const newTitle = input.value.trim();
        if (!newTitle || newTitle === currentTitle) {
            cleanup();
            return;
        }

        try {
            const response = await fetch('/chat/rename', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: newTitle })
            });

            const data = await response.json();

            if (data.success) {
                titleText.textContent = newTitle;
                await loadChats();
            } else {
                alert('Failed to rename: ' + (data.error || 'Unknown error'));
            }
        } catch (e) {
            console.error('Failed to rename chat:', e);
            alert('Failed to rename chat');
        }

        cleanup();
    };

    // Event handlers
    saveBtn.onclick = saveRename;
    cancelBtn.onclick = cleanup;

    input.onkeydown = (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            saveRename();
        }
        if (e.key === 'Escape') {
            e.preventDefault();
            cleanup();
        }
    };

    input.onblur = (e) => {
        // Small delay to allow button clicks to register
        setTimeout(() => {
            if (titleText.dataset.editing === 'true' &&
                !editContainer.contains(document.activeElement)) {
                cleanup();
                }
        }, 100);
    };
}

// =============================================================================
// Chat Search/Filter
// =============================================================================

function toggleSearchMode() {
    searchInContent = !searchInContent;

    const toggleBtn = document.getElementById('search-toggle');
    const searchInput = document.getElementById('chat-search');

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
    filterChats(currentQuery);
}

function filterChats(query) {
    const searchQuery = (query || '').toLowerCase().trim();
    const items = document.querySelectorAll('.chat-item');

    // Clear all snippets and visibility states first
    items.forEach(item => {
        const existingSnippet = item.querySelector('.chat-snippet');
        if (existingSnippet) {
            existingSnippet.remove();
        }
        item.classList.remove('hidden-by-search');
    });

    // Show all when search is empty
    if (!searchQuery) {
        filterTagsBySearch('');
        return;
    }

    items.forEach(item => {
        const titleEl = item.querySelector('.chat-item-title');
        const titleText = titleEl ? titleEl.textContent.toLowerCase() : '';

        // Get chat data from dataset
        let chatData = null;
        try {
            chatData = JSON.parse(item.dataset.chatData || 'null');
        } catch (e) {
            chatData = null;
        }

        let matchesTitle = titleText.includes(searchQuery);
        let matchSnippet = null;

        // If content search is enabled, also search in messages
        if (searchInContent && chatData && chatData.messages) {
            for (const msg of chatData.messages) {
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
            const metaEl = item.querySelector('.chat-item-meta');
            if (metaEl && !item.querySelector('.chat-snippet')) {
                const snippetEl = document.createElement('div');
                snippetEl.className = 'chat-snippet';
                snippetEl.innerHTML = matchSnippet;
                // Insert after meta
                metaEl.insertAdjacentElement('afterend', snippetEl);
            }
        }
    });

    // Also filter tags based on search
    filterTagsBySearch(query);
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
