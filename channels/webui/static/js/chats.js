// =============================================================================
// Chats
// =============================================================================

let activeCategory = 'general'; // Default category

const CATEGORY_REGISTRY = {
    'char': {
        icon: ICONS.user,
        class: 'category-character',
        label: (name) => name,
        groupTitle: 'Characters' // New property
    },
    // Add others here if needed
};

const DEFAULT_CATEGORY_HANDLER = {
    icon: ICONS.chat,
    class: 'category-default',
    label: (name) => name,
    groupTitle: 'Chats' // Default group for non-prefixed categories
};

/**
 * Handles click on the Chat Pane Header.
 * Desktop: Does nothing (or could open a dropdown if desired).
 * Mobile: Slides the Category Pane (fullscreen) into view.
 */
function handlePaneHeaderClick() {
    if (window.innerWidth <= 768) {
        openCategoryPane();
    }
}

function openCategoryPane() {
    const pane = document.getElementById('category-pane');
    if (pane) pane.classList.add('open');
}

function closeCategoryPane() {
    const pane = document.getElementById('category-pane');
    if (pane) pane.classList.remove('open');
}

// Helper to filter tags based on the active category
function updateTagsForCategory(categoryKey) {
    // 1. Filter chats to get the ones in this category
    const chatsInCategory = allChats.filter(chat => {
        if (categoryKey === 'general') {
            return !chat.category || chat.category === 'general';
        }
        return chat.category === categoryKey;
    });

    // 2. Extract unique tags from these chats
    const categoryTags = new Set();
    chatsInCategory.forEach(chat => {
        (chat.tags || []).forEach(tag => categoryTags.add(tag));
    });

    // 3. Convert to sorted array
    const sortedTags = Array.from(categoryTags).sort();

    // 4. Check if currently active tag is valid for this category
    if (activeTagFilter && !sortedTags.includes(activeTagFilter)) {
        // If the active tag isn't in this category, clear it
        activeTagFilter = null;
        const clearBtn = document.getElementById('clear-tag-filter');
        if (clearBtn) clearBtn.style.display = 'none';
    }

    // 5. Render the tag list
    renderTagFilter(sortedTags);
}

/**
 * Selects a category.
 * Desktop: Filters list immediately.
 * Mobile: Filters list AND slides the Category Pane away (revealing Chat Pane).
 */
function selectCategory(categoryKey) {
    activeCategory = categoryKey;

    // 1. Update Header
    updateChatPaneTitle(categoryKey);

    // 2. Update Active State
    const items = document.querySelectorAll('.category-item');
    items.forEach(item => {
        item.classList.toggle('active', item.dataset.key === categoryKey);
    });

    // 3. Filter and Render
    // We filter the MASTER list (allChats) and pass the subset to renderChatList
    const filtered = filterChatsByCategory(allChats, categoryKey);
    renderChatList(filtered);

    // 4. Update Tags
    updateTagsForCategory(categoryKey);

    // 5. Mobile close
    if (window.innerWidth <= 768) {
        closeCategoryPane();
    }
}


function updateChatPaneTitle(categoryKey) {
    const titleEl = document.getElementById('chat-pane-title');
    let displayName = 'General';

    if (categoryKey !== 'general') {
        const parsed = parseCategory(categoryKey);
        displayName = parsed.handler.label(parsed.name);
    }

    titleEl.textContent = displayName;
}

function filterChatsByCategory(chats, categoryKey) {
    if (categoryKey === 'general') {
        // General includes null, undefined, or "general"
        return chats.filter(c => !c.category || c.category === 'general');
    }
    return chats.filter(c => c.category === categoryKey);
}


function renderCategoryList(categories) {
    const list = document.getElementById('category-list');
    list.innerHTML = '';

    // 1. Group the data
    const groups = {};

    // Add the "Chats" group explicitly first if it doesn't exist,
    // or rely on the loop. Let's ensure "Chats" exists to hold "General".
    groups['Chats'] = [];

    categories.forEach(catKey => {
        const parsed = parseCategory(catKey);
        const group = parsed.groupTitle || 'Other';

        if (!groups[group]) {
            groups[group] = [];
        }

        // Store the original key and parsed data
        groups[group].push({ key: catKey, parsed: parsed });
    });

    // 2. Define Render Order
    // "Chats" always first, then others alphabetically
    const groupNames = Object.keys(groups).filter(g => g !== 'Chats').sort();
    if (groups['Chats']) {
        groupNames.unshift('Chats');
    }

    // 3. Render Groups
    groupNames.forEach(groupName => {
        // Create Group Header
        const header = createCategoryGroupHeader(groupName);
        list.appendChild(header);

        // Create Group Content Container
        const content = document.createElement('div');
        content.className = 'category-group-content';

        // Sort items inside the group alphabetically
        const items = groups[groupName].sort((a, b) =>
        a.parsed.name.localeCompare(b.parsed.name)
        );

        // Special Case: If this is the "Chats" group, prepend "General"
        if (groupName === 'Chats') {
            // Use ICONS.home specifically for the General category
            const generalItem = createCategoryElement('general', 'General', ICONS.home);
            content.appendChild(generalItem);
        }

        // Render Items
        items.forEach(item => {
            const el = createCategoryElement(
                item.key,
                item.parsed.handler.label(item.parsed.name),
                                             item.parsed.handler.icon
            );
            content.appendChild(el);
        });

        list.appendChild(content);
    });
}

function createCategoryGroupHeader(name) {
    const header = document.createElement('div');
    header.className = 'category-group-header';

    // Default state: Expanded
    header.innerHTML = `
    <svg class="chevron" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <polyline points="6 9 12 15 18 9"></polyline>
    </svg>
    <span>${name}</span>
    `;

    header.onclick = () => {
        const content = header.nextElementSibling;
        const isHidden = content.style.display === 'none';
        content.style.display = isHidden ? 'block' : 'none';
        header.querySelector('.chevron').classList.toggle('collapsed', !isHidden);
    };

    return header;
}

function createCategoryElement(key, name, icon) {
    const btn = document.createElement('button');
    // Use specific class for styling
    btn.className = 'category-item';
    if (key === activeCategory) btn.classList.add('active');

    btn.dataset.key = key;

    btn.innerHTML = `
    <span class="category-item-icon">${icon}</span>
    <span class="category-item-name">${escapeHtml(name)}</span>
    `;

    btn.onclick = () => selectCategory(key);
    return btn;
}

function parseCategory(categoryString) {
    if (!categoryString) return {
        prefix: null,
        name: 'General',
        fullKey: 'general',
        handler: DEFAULT_CATEGORY_HANDLER
    };

    const parts = categoryString.split(':');

    // Case 1: Special "prefix:name" format
    if (parts.length === 2 && CATEGORY_REGISTRY[parts[0]]) {
        const prefix = parts[0];
        const handler = CATEGORY_REGISTRY[prefix];
        return {
            prefix: prefix,
            name: parts[1],
            fullKey: categoryString,
            handler: handler,
            groupTitle: handler.groupTitle || 'Misc' // Fallback
        };
    }

    // Case 2: Standard "name" format
    return {
        prefix: null,
        name: categoryString,
        fullKey: categoryString,
        handler: DEFAULT_CATEGORY_HANDLER,
        groupTitle: DEFAULT_CATEGORY_HANDLER.groupTitle // "Chats"
    };
}

async function loadChats() {
    try {
        const [chatResponse, tagsResponse] = await Promise.all([
            fetch('/chats'),
                                                               fetch('/chat/tags')
        ]);

        const chatData = await chatResponse.json();
        const tagsData = await tagsResponse.json();

        allTags = tagsData.tags || [];
        allChats = chatData.chats || [];

        // Extract Unique Categories
        const categories = new Set();
        allChats.forEach(chat => {
            if (chat.category && chat.category !== 'general') {
                categories.add(chat.category);
            }
        });

        renderTagFilter();
        renderCategoryList(Array.from(categories));

        // Initial Load based on active state
        selectCategory(activeCategory);

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

// Helper to create header (Updated to accept icon/class)
function createGroupHeader(name, icon, extraClass = '') {
    const header = document.createElement('div');
    header.className = `chat-group-header ${extraClass}`;

    // Use provided icon or default arrow
    const iconHtml = icon
    ? `<span class="header-icon">${icon}</span>`
    : `<svg class="chevron" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg>`;

    header.innerHTML = `
    ${iconHtml}
    <span class="chat-group-title">${escapeHtml(name)}</span>
    `;

    header.onclick = () => {
        const content = header.nextElementSibling;
        // Toggle logic...
        // If you want clicking "Luna" to open character settings, handle that here
        // Otherwise, just toggle collapse
        const isHidden = content.style.display === 'none';
        content.style.display = isHidden ? 'block' : 'none';
    };

    return header;
}

// Helper to create the container for a group's chats
function createGroupContainer() {
    const container = document.createElement('div');
    container.className = 'chat-group-content';
    return container;
}

// Extracted helper to create a single chat item element
function createChatElement(chat) {
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

    return item;
}

function renderChatList(chats) {
    const list = document.getElementById('chat-list');
    const searchInput = document.getElementById('chat-search');
    const currentSearchQuery = searchInput ? searchInput.value : '';

    list.innerHTML = '';

    // IMPORTANT: Do NOT overwrite allChats here.
    // allChats is the master list loaded from the backend.
    // This function receives the filtered subset to render.

    if (chats.length === 0) {
        const emptyMsg = document.createElement('div');
        emptyMsg.className = 'chat-empty';
        emptyMsg.textContent = 'No chats in this category';
        emptyMsg.style.cssText = 'padding: 20px; text-align: center; color: var(--text-muted); font-size: 0.85rem;';
        list.appendChild(emptyMsg);
        return;
    }

    // Sort by updated time (newest first)
    chats.sort((a, b) => (b.updated || 0) - (a.updated || 0));

    // Render a flat list (No grouping headers needed here anymore)
    chats.forEach(chat => {
        list.appendChild(createChatElement(chat));
    });

    // Re-apply active tag filter
    if (activeTagFilter) {
        filterChatsByTag();
    }

    // Re-apply text search if active
    if (currentSearchQuery) {
        filterChats(currentSearchQuery);
    }
}

// Helper to create the group header element (Refined)
function createGroupHeader(name, icon, extraClass = '') {
    const header = document.createElement('div');
    header.className = `chat-group-header ${extraClass}`;

    const iconHtml = icon
    ? `<span class="header-icon">${icon}</span>`
    : `<svg class="chevron" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg>`;

    header.innerHTML = `
    ${iconHtml}
    <span class="chat-group-title">${escapeHtml(name)}</span>
    `;

    header.onclick = () => {
        const content = header.nextElementSibling;
        if (!content || !content.classList.contains('chat-group-content')) return;

        const isHidden = content.style.display === 'none';
        content.style.display = isHidden ? 'block' : 'none';

        // Toggle chevron rotation if using default icon
        const chevron = header.querySelector('.chevron');
        if(chevron) chevron.classList.toggle('collapsed', !isHidden);
    };

        return header;
}

// Helper to create the container (Crucial for spacing)
function createGroupContainer() {
    const container = document.createElement('div');
    container.className = 'chat-group-content';
    // Ensure it matches the flat list behavior
    return container;
}


async function newChat() {
    if (isStreaming) {
        return;
    }

    try {
        const response = await fetch('/chat/new', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: '' })
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

async function clearChat() {
    if (!confirm("Really clear the chat?")) return false;

    try {
        const response = await fetch('/chat/clear', {
            method: 'POST'
        });

        if (response.ok) {
            // Reload
            if (currentChatId) {
                await loadChat(currentChatId);
            }
            await loadChats();
        }
    } catch (err) {
        console.error('Failed to clear chat:', err);
    }
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
