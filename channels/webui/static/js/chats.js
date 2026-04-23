// =============================================================================
// Chats
// =============================================================================

let activeCategory = 'general'; // Default category
// OPTIMIZATION: Global map for O(1) chat data lookups (prevents JSON parsing in loops)
let chatDataMap = new Map();

const CATEGORY_REGISTRY = {
    'char': {
        icon: ICONS.user,
        class: 'category-character',
        label: (name) => name,
        groupTitle: 'Characters'
    }
};

const DEFAULT_CATEGORY_HANDLER = {
    icon: ICONS.chat,
    class: 'category-default',
    label: (name) => name,
    groupTitle: 'Chats'
};

// IntersectionObserver for lazy-loading chat items
const chatListObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const el = entry.target;
            const chatId = el.dataset.chatId;
            const chat = chatDataMap.get(chatId);

            if (chat && el.classList.contains('chat-item-shell')) {
                populateChatItem(el, chat);
                chatListObserver.unobserve(el);
            }
        }
    });
}, {
    rootMargin: '100px' // Start loading slightly before they enter the viewport
});

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

function updateTagsForCategory(categoryKey) {
    const chatsInCategory = allChats.filter(chat => {
        if (categoryKey === 'general') {
            return !chat.category || chat.category === 'general';
        }
        return chat.category === categoryKey;
    });

    const categoryTags = new Set();
    chatsInCategory.forEach(chat => {
        (chat.tags || []).forEach(tag => categoryTags.add(tag));
    });

    const sortedTags = Array.from(categoryTags).sort();

    if (activeTagFilter && !sortedTags.includes(activeTagFilter)) {
        activeTagFilter = null;
        const clearBtn = document.getElementById('clear-tag-filter');
        if (clearBtn) clearBtn.style.display = 'none';
    }

    renderTagFilter(sortedTags);
}

function selectCategory(categoryKey) {
    activeCategory = categoryKey;
    updateChatPaneTitle(categoryKey);

    const items = document.querySelectorAll('.category-item');
    items.forEach(item => {
        item.classList.toggle('active', item.dataset.key === categoryKey);
    });

    const filtered = filterChatsByCategory(allChats, categoryKey);
    renderChatList(filtered);
    updateTagsForCategory(categoryKey);

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
        return chats.filter(c => !c.category || c.category === 'general');
    }
    return chats.filter(c => c.category === categoryKey);
}


function renderCategoryList(categories) {
    const list = document.getElementById('category-list');

    // FIX: Load collapsed state from localStorage instead of scanning DOM
    const collapsedGroups = new Set(JSON.parse(localStorage.getItem('sidebar_collapsed_categories') || '[]'));

    // OPTIMIZATION: Use DocumentFragment to reduce reflows
    const fragment = document.createDocumentFragment();
    const groups = {};

    groups['Chats'] = [];

    categories.forEach(catKey => {
        const parsed = parseCategory(catKey);
        const group = parsed.groupTitle || 'Other';
        if (!groups[group]) groups[group] = [];
        groups[group].push({ key: catKey, parsed: parsed });
    });

    const groupNames = Object.keys(groups).filter(g => g !== 'Chats').sort();
    if (groups['Chats']) groupNames.unshift('Chats');

    groupNames.forEach(groupName => {
        const header = createCategoryGroupHeader(groupName);
        fragment.appendChild(header);

        const content = document.createElement('div');
        content.className = 'category-group-content';

        // FIX: Apply collapsed state if found in localStorage
        if (collapsedGroups.has(groupName)) {
            content.style.display = 'none';
            const chevron = header.querySelector('.chevron');
            if (chevron) chevron.classList.add('collapsed');
        }

        const items = groups[groupName].sort((a, b) =>
        a.parsed.name.localeCompare(b.parsed.name)
        );

        if (groupName === 'Chats') {
            const generalItem = createCategoryElement('general', 'General', ICONS.home);
            content.appendChild(generalItem);
        }

        items.forEach(item => {
            const el = createCategoryElement(
                item.key,
                item.parsed.handler.label(item.parsed.name),
                                             item.parsed.handler.icon
            );
            content.appendChild(el);
        });

        fragment.appendChild(content);
    });

    // Single DOM update
    list.innerHTML = '';
    list.appendChild(fragment);
}

function createCategoryGroupHeader(name) {
    const header = document.createElement('div');
    header.className = 'category-group-header';
    header.innerHTML = `
    <svg class="chevron" xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <polyline points="6 9 12 15 18 9"></polyline>
    </svg>
    <span>${name}</span>
    `;

    header.onclick = () => {
        const content = header.nextElementSibling;
        if(!content) return;
        const isHidden = content.style.display === 'none';
        content.style.display = isHidden ? 'block' : 'none';
        header.querySelector('.chevron').classList.toggle('collapsed', !isHidden);

        // FIX: Update localStorage when user toggles
        const collapsed = new Set(JSON.parse(localStorage.getItem('sidebar_collapsed_categories') || '[]'));
        if (isHidden) {
            collapsed.delete(name); // Opening it, so remove from set
        } else {
            collapsed.add(name); // Closing it, so add to set
        }
        localStorage.setItem('sidebar_collapsed_categories', JSON.stringify(Array.from(collapsed)));
    };
    return header;
}

function createCategoryElement(key, name, icon) {
    const btn = document.createElement('button');
    btn.className = 'category-item';
    if (key === activeCategory) btn.classList.add('active');
    btn.dataset.key = key;
    btn.innerHTML = `
    <span class="category-item-icon">${icon}</span>
    <span class="category-item-name">${escapeHtml(name)}</span>
    `;

    // Allow dropping chats onto this category
    btn.addEventListener('dragover', (e) => {
        console.log('Drag over category', key, 'classList:', btn.classList);
        e.preventDefault();
        e.dataTransfer.dropEffect = 'move';
        btn.classList.add('drag-over');
        console.log('After add class:', btn.classList);
        e.stopPropagation();
    });

    btn.addEventListener('dragleave', () => {
        console.log('Drag leave category', key);
        btn.classList.remove('drag-over');
    });

    btn.addEventListener('drop', async (e) => {
        e.preventDefault();
        e.stopPropagation();
        btn.classList.remove('drag-over');
        const chatId = e.dataTransfer.getData('text/plain');
        if (chatId) {
            await moveChatToCategory(chatId, key);
        }
    });

    btn.onclick = () => selectCategory(key);
    return btn;
}

function parseCategory(categoryString) {
    if (!categoryString) return {
        prefix: null, name: 'General', fullKey: 'general', handler: DEFAULT_CATEGORY_HANDLER
    };

    const parts = categoryString.split(':');

    if (parts.length === 2 && CATEGORY_REGISTRY[parts[0]]) {
        const prefix = parts[0];
        const handler = CATEGORY_REGISTRY[prefix];
        return {
            prefix: prefix,
            name: parts[1],
            fullKey: categoryString,
            handler: handler,
            groupTitle: handler.groupTitle || 'Misc'
        };
    }

    return {
        prefix: null,
        name: categoryString,
        fullKey: categoryString,
        handler: DEFAULT_CATEGORY_HANDLER,
        groupTitle: DEFAULT_CATEGORY_HANDLER.groupTitle
    };
}

async function loadChats() {
    try {
        // OPTIMIZATION: Parallel fetch is good, ensure backend returns summary data only
        const [chatResponse, tagsResponse] = await Promise.all([
            fetch('/chats'),
                                                               fetch('/chat/tags')
        ]);

        const chatData = await chatResponse.json();
        const tagsData = await tagsResponse.json();

        allTags = tagsData.tags || [];
        allChats = chatData.chats || [];

        // OPTIMIZATION: Store chats in a Map for O(1) access by ID.
        // This prevents looping through arrays or parsing JSON strings later.
        chatDataMap.clear();
        allChats.forEach(chat => chatDataMap.set(chat.id, chat));

        const categories = new Set();
        allChats.forEach(chat => {
            if (chat.category && chat.category !== 'general') {
                if (!chat.category.startsWith('char:')) {
                    categories.add(chat.category);
                }
            }
            const characterName = chat.custom_data?.character;
            if (characterName) {
                categories.add(`char:${characterName}`);
            }
        });

        renderTagFilter();
        renderCategoryList(Array.from(categories));
        selectCategory(activeCategory);
        scrollToActiveChat();

    } catch (e) {
        console.error('Failed to load chats:', e);
    }
}

/**
 * Finds the currently active chat element in the sidebar and scrolls it into view.
 * Populates all shells above the target to ensure the scroll container has
 * the correct height, then centers the target element in the viewport.
 */
function scrollToActiveChat() {
    if (!currentChatId) return;

    const list = document.getElementById('chat-list');
    if (!list) return;

    const items = Array.from(list.children);
    const targetIndex = items.findIndex(el => el.dataset.chatId === currentChatId);

    if (targetIndex === -1) return;

    // 1. Populate all shells from the top down to the target index.
    // This ensures the container's total height is accurate.
    for (let i = 0; i <= targetIndex; i++) {
        const el = items[i];
        if (el.classList.contains('chat-item-shell')) {
            const chatId = el.dataset.chatId;
            const chat = chatDataMap.get(chatId);
            if (chat) {
                populateChatItem(el, chat);
            }
        }
    }

    // 2. Identify the target element
    const activeChatEl = items[targetIndex];

    // 3. Scroll to the center of the visible area
    requestAnimationFrame(() => {
        activeChatEl.scrollIntoView({
            behavior: 'smooth',
            block: 'center' // <--- This centers the element
        });
    });
}

async function restoreCurrentChat() {
    try {
        const response = await fetch('/chat/current');
        const data = await response.json();

        if (data.success && data.chat && data.chat.id) {
            currentChatId = data.chat.id;

            // NEW: Sync the active category to match the current chat's category
            // This ensures the sidebar is looking at the correct group/list
            if (data.chat.category && data.chat.category !== 'general') {
                activeCategory = data.chat.category;
            } else {
                activeCategory = 'general';
            }

            // NEW: Ensure the chat list is actually loaded/rendered in the sidebar
            await loadChats();

            const messages = data.chat.messages || [];
            const tags = data.chat.tags || [];

            updateChatTitleBar(data.chat.title, tags);

            if (messages.length > 0) {
                renderAllMessages(messages);
                updateTokenUsage();
                lastMessageIndex = messages.length;
            } else {
                clearChatUI();
            }

            // NEW: Scroll to the selected chat in the sidebar
            scrollToActiveChat();

        } else {
            currentChatId = null;
            clearChatUI();
            updateChatTitleBar(null);
        }
    } catch (e) {
        console.error('Failed to restore current chat:', e);
        currentChatId = null;
        updateChatTitleBar(null);
    }
}


function clearChatUI() {
    lastMessageIndex = 0;
    const wrappers = chat.querySelectorAll('.message-wrapper');
    wrappers.forEach(wrapper => wrapper.remove());
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

// Helper to create header
function createGroupHeader(name, icon, extraClass = '') {
    const header = document.createElement('div');
    header.className = `chat-group-header ${extraClass}`;

    const iconHtml = icon
    ? `<span class="header-icon">${icon}</span>`
    : `<svg class="chevron" xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg>`;

    header.innerHTML = `${iconHtml}<span class="chat-group-title">${escapeHtml(name)}</span>`;

    header.onclick = () => {
        const content = header.nextElementSibling;
        if (!content || !content.classList.contains('chat-group-content')) return;
        const isHidden = content.style.display === 'none';
        content.style.display = isHidden ? 'block' : 'none';
        const chevron = header.querySelector('.chevron');
        if(chevron) chevron.classList.toggle('collapsed', !isHidden);
    };

        return header;
}

function createGroupContainer() {
    const container = document.createElement('div');
    container.className = 'chat-group-content';
    return container;
}

function createChatElement(chat) {
    const item = document.createElement('div');
    item.className = 'chat-item' + (chat.id === currentChatId ? ' active' : '');
    item.setAttribute('draggable', 'true');
    item.dataset.chatId = chat.id;

    console.log('Created chat element', chat.id, 'draggable:', item.draggable);

    // Drag start event
    item.addEventListener('dragstart', (e) => {
        console.log('Drag start', chat.id);
        e.dataTransfer.setData('text/plain', chat.id);
        e.dataTransfer.effectAllowed = 'move';
        // Add a class for styling while dragging
        setTimeout(() => item.classList.add('dragging'), 0);
    });

    item.addEventListener('dragend', () => {
        item.classList.remove('dragging');
        // Remove any drop target highlights
        document.querySelectorAll('.category-item').forEach(el => el.classList.remove('drag-over'));
    });

    item.onclick = (e) => {
        if (e.target.closest('.chat-item-actions') || e.target.closest('.inline-rename-container')) {
            return;
        }
        loadChat(chat.id);
    };

    const title = document.createElement('div');
    title.className = 'chat-item-title';
    title.textContent = chat.title || 'New chat';

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
        renderFittedTags(tagsContainer, tags, { maxStart: 3, minTags: 1, showTooltip: true });
        item.appendChild(tagsContainer);
    }

    item.appendChild(title);
    item.appendChild(meta);

    return item;
}

/**
 * Creates a lightweight placeholder for a chat item.
 * This prevents the initial DOM overhead of creating hundreds of complex elements.
 */
/**
 * Creates a lightweight placeholder for a chat item.
 * This prevents the initial DOM overhead of creating hundreds of complex elements.
 */
function createChatItemShell(chat) {
    const item = document.createElement('div');
    item.className = 'chat-item chat-item-shell' + (chat.id === currentChatId ? ' active' : '');
    item.setAttribute('draggable', 'true');
    item.dataset.chatId = chat.id;

    // Crucial: Set a min-height so the scrollbar behaves correctly
    // before the item is fully rendered.
    item.style.minHeight = '55px';

    // Only enable drag-and-drop on desktop (not mobile)
    const isMobile = window.matchMedia('(max-width: 768px)').matches || 'ontouchstart' in window;

    if (!isMobile) {
        // Drag start event
        item.addEventListener('dragstart', (e) => {
            console.log('Drag start', chat.id);
            e.dataTransfer.setData('text/plain', chat.id);
            e.dataTransfer.effectAllowed = 'move';
            // Add a class for styling while dragging
            setTimeout(() => item.classList.add('dragging'), 0);
            // Set flag to prevent file upload overlay
            window.isDraggingChat = true;
            // Prevent the drag from bubbling up to the main content area
            e.stopPropagation();
        });

        // Prevent dragover events from bubbling up to the document body
        item.addEventListener('dragover', (e) => {
            e.stopPropagation();
        }, true); // Use capture phase to catch events before they bubble

        item.addEventListener('dragend', () => {
            item.classList.remove('dragging');
            // Remove any drop target highlights
            document.querySelectorAll('.category-item').forEach(el => el.classList.remove('drag-over'));
            // Clear flag when drag ends
            window.isDraggingChat = false;
        });
    }

    // Always attach click handler for both mobile and desktop
    item.onclick = (e) => {
        if (e.target.closest('.chat-item-actions') || e.target.closest('.inline-rename-container')) {
            return;
        }
        loadChat(chat.id);
    };

    return item;
}

/**
 * Fills a chat item shell with its actual content.
 * This is called only when the item is about to enter the view.
 */
function populateChatItem(item, chat) {
    // Remove the shell class
    item.classList.remove('chat-item-shell');

    const title = document.createElement('div');
    title.className = 'chat-item-title';
    title.textContent = chat.title || 'New chat';

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
        renderFittedTags(tagsContainer, tags, { maxStart: 3, minTags: 1, showTooltip: true });
        item.appendChild(tagsContainer);
    }

    item.appendChild(title);
    item.appendChild(meta);
}

function renderChatList(chats) {
    try {
        const list = document.getElementById('chat-list');
        if (!list) {
            console.warn('Chat list container not found');
            return;
        }
        const searchInput = document.getElementById('chat-search');
        const currentSearchQuery = searchInput ? searchInput.value : '';

        const fragment = document.createDocumentFragment();

        if (chats.length === 0) {
            const emptyMsg = document.createElement('div');
            emptyMsg.className = 'chat-empty';
            emptyMsg.textContent = 'No chats in this category';
            emptyMsg.style.cssText = 'padding: 20px; text-align: center; color: var(--text-muted); font-size: 0.85rem;';
            fragment.appendChild(emptyMsg);
        } else {
            chats.sort((a, b) => (b.updated || 0) - (a.updated || 0));
            chats.forEach(chat => {
                // Create the shell instead of the full element
                const shell = createChatItemShell(chat);
                fragment.appendChild(shell);
            });
        }

        list.innerHTML = '';
        list.appendChild(fragment);

        // Initialize observer on the new shells
        const shells = list.querySelectorAll('.chat-item-shell');
        shells.forEach(shell => chatListObserver.observe(shell));

        // Re-apply filters if active
        if (activeTagFilter) filterChatsByTag();
        if (currentSearchQuery) filterChats(currentSearchQuery);
    } catch (err) {
        console.error('Failed to render chat list:', err);
    }
}

async function moveChatToCategory(chatId, newCategory) {
    if (!chatId || !newCategory) return;

    try {
        const response = await fetch('/chat/update_category', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chat_id: chatId, category: newCategory })
        });

        const data = await response.json();

        if (data.success) {
            // Refresh the chat list to reflect the change
            await loadChats();
        } else {
            console.error('Failed to move chat:', data.error);
        }
    } catch (e) {
        console.error('Error moving chat:', e);
    }
}

async function newChat() {
    if (isStreaming) await stopGeneration();
    try {
        const response = await fetch('/chat/new', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: '', category: activeCategory })
        });

        const data = await response.json();

        if (data.success && data.chat) {
            currentChatId = data.chat.id;
            lastMessageIndex = 0;
            updateChatTitleBar(data.chat.title);
            updateTokenUsage();

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

async function updateTokenUsage() {
    try {
        const response = await fetch('/api/token_usage');
        const data = await response.json();

        if (data.current !== undefined && data.max !== undefined) {
            const container = document.getElementById('token-usage-container');
            const fill = document.getElementById('token-usage-fill');
            const text = document.getElementById('token-usage-text');

            const percentage = (data.current / data.max) * 100;
            const NOTIFY_THRESHOLD = 70;

            // 1. Always update the numbers and the width
            fill.style.width = `${Math.min(percentage, 100)}%`;
            text.textContent = `${data.current.toLocaleString()} / ${data.max.toLocaleString()}`;

            // 2. Handle "Notification" (Visual Prominence)
            if (percentage >= NOTIFY_THRESHOLD) {
                // Make it bright and "active"
                container.classList.add('active');

                // Change color based on urgency
                if (percentage >= 90) {
                    fill.style.backgroundColor = '#ef4444'; // Red
                } else if (percentage >= 75) {
                    fill.style.backgroundColor = '#f59e0b'; // Amber
                } else {
                    fill.style.backgroundColor = '#10b981'; // Green
                }
            } else {
                // Keep it "quiet" (dimmed)
                container.classList.remove('active');
                fill.style.backgroundColor = '#10b981'; // Reset to green
            }
        }
    } catch (e) {
        console.error('Token usage update failed:', e);
    }
}

async function loadChat(chatId) {
    if (chatId === currentChatId) {
        closeSidebar();
        return;
    }

    if (isStreaming) await stopGeneration();

    try {
        const response = await fetch('/chat/load?id=' + chatId);
        const data = await response.json();

        if (data.success && data.chat) {
            currentChatId = chatId;
            const messages = data.chat.messages || [];
            renderAllMessages(messages, true);
            lastMessageIndex = data.chat.total || (messages.length > 0 ? messages[messages.length - 1].index + 1 : 0);

            updateChatTitleBar(data.chat.title, data.chat.tags || []);
            updateTokenUsage();
            closeSidebar();

            // SMART UPDATE:
            // Only perform a full re-render if the category actually changes.
            // This prevents the "jump" during normal chat selection on desktop.
            const chatCategory = data.chat.category || 'general';

            if (chatCategory !== activeCategory) {
                // Category changed (e.g., clicking a character chat while in 'General')
                // We must reload to show the correct list and update the category strip
                await loadChats();
            } else {
                // Same category (e.g., clicking a different chat in the current list)
                // Just swap the active class on the existing element
                updateSidebarActiveChat(chatId);
            }
        }
    } catch (e) {
        console.error('Failed to load chat:', e);
    }
}

/**
 * Updates the visual 'active' state in the sidebar without re-rendering the whole list.
 * This prevents layout jumps and scroll stutters.
 */
function updateSidebarActiveChat(chatId) {
    // 1. Remove active class from the current active item
    const currentActive = document.querySelector('.chat-item.active');
    if (currentActive) {
        currentActive.classList.remove('active');
    }

    // 2. Find the new chat item and add the active class
    // This works whether the item is a fully rendered item or still a 'shell'
    const newActive = document.querySelector(`.chat-item[data-chat-id="${chatId}"]`);
    if (newActive) {
        newActive.classList.add('active');
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
        const response = await fetch('/chat/delete?id=' + chatId, { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            await restoreCurrentChat();
            await loadChats();
            closeSidebar();
        } else {
            alert('Failed to delete chat: ' + (data.error || 'Unknown error'));
        }
    } catch (e) {
        console.error('Failed to delete chat:', e);
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

// =============================================================================
// Chat Search/Filter (OPTIMIZED)
// =============================================================================

function filterChats(query) {
    const searchQuery = (query || '').toLowerCase().trim();
    const items = document.querySelectorAll('.chat-item');

    items.forEach(item => {
        const existingSnippet = item.querySelector('.chat-snippet');
        if (existingSnippet) existingSnippet.remove();
        item.classList.remove('hidden-by-search');
    });

    if (!searchQuery) {
        filterTagsBySearch('');
        return;
    }

    items.forEach(item => {
        const titleText = item.querySelector('.chat-item-title')?.textContent.toLowerCase() || '';
        const chatId = item.dataset.chatId;

        // PERFORMANCE: Lookup data from Map instead of JSON.parse
        const chatData = chatDataMap.get(chatId);

        let matchesTitle = titleText.includes(searchQuery);
        let matchSnippet = null;

        if (searchInContent && chatData && chatData.messages) {
            for (const msg of chatData.messages) {
                // FIX: Use extractTextContent to handle multimodal arrays
                const content = extractTextContent(msg.content).toLowerCase();
                if (content.includes(searchQuery)) {
                    // Pass the extracted string to extractSnippet
                    matchSnippet = extractSnippet(content, searchQuery, 60);
                    break;
                }
            }
        }

        const isVisible = matchesTitle || matchSnippet;

        if (!isVisible) {
            item.classList.add('hidden-by-search');
        } else if (matchSnippet && searchInContent) {
            const metaEl = item.querySelector('.chat-item-meta');
            if (metaEl && !item.querySelector('.chat-snippet')) {
                const snippetEl = document.createElement('div');
                snippetEl.className = 'chat-snippet';
                snippetEl.innerHTML = matchSnippet;
                metaEl.insertAdjacentElement('afterend', snippetEl);
            }
        }
    });

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
