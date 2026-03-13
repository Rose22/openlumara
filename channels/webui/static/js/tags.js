// =============================================================================
// Tag Management Functions
// =============================================================================

async function loadTags() {
    try {
        const response = await fetch('/chat/tags');
        const data = await response.json();
        allTags = data.tags || [];
        renderTagFilter();
    } catch (e) {
        console.error('Failed to load tags:', e);
    }
}

function toggleTagFilterSection() {
    tagFilterCollapsed = !tagFilterCollapsed;

    // Update header arrow
    const header = document.querySelector('.tag-filter-header');
    const arrow = header?.querySelector('.tag-filter-arrow');
    const tagList = document.getElementById('tag-list');

    if (arrow) {
        arrow.classList.toggle('expanded', !tagFilterCollapsed);
    }

    if (tagList) {
        tagList.classList.toggle('collapsed', tagFilterCollapsed);
    }

    // Save preference to localStorage
    localStorage.setItem('tagFilterCollapsed', tagFilterCollapsed);
}

function renderTagFilter() {
    const tagList = document.getElementById('tag-list');
    const clearBtn = document.getElementById('clear-tag-filter');
    const arrow = document.querySelector('.tag-filter-arrow');

    if (!tagList) return;

    // Update arrow state
    if (arrow) {
        arrow.classList.toggle('expanded', !tagFilterCollapsed);
    }

    tagList.innerHTML = '';

    if (allTags.length === 0) {
        const emptyHint = document.createElement('span');
        emptyHint.className = 'no-tags-hint';
        emptyHint.textContent = 'No tags yet';
        tagList.appendChild(emptyHint);
    } else {
        allTags.forEach(tag => {
            const chip = document.createElement('button');
            chip.className = 'tag-chip' + (activeTagFilter === tag ? ' active' : '');
            chip.textContent = tag;
            chip.onclick = (e) => {
                e.stopPropagation();
                toggleTagFilter(tag);
            };
            tagList.appendChild(chip);
        });
    }

    // Show/hide clear button
    if (clearBtn) {
        clearBtn.style.display = activeTagFilter ? 'flex' : 'none';
    }

    // Apply collapsed state
    tagList.classList.toggle('collapsed', tagFilterCollapsed);
}

function toggleTagFilter(tag) {
    if (activeTagFilter === tag) {
        // Clicking active tag clears the filter
        activeTagFilter = null;
    } else {
        activeTagFilter = tag;
    }

    renderTagFilter();
    filterChatsByTag();
}

function clearTagFilter() {
    activeTagFilter = null;
    renderTagFilter();
    filterChatsByTag();
}

function filterChatsByTag() {
    const items = document.querySelectorAll('.chat-item');

    items.forEach(item => {
        if (activeTagFilter) {
            const chatData = JSON.parse(item.dataset.chatData || '{}');
            const tags = chatData.tags || [];

            if (tags.includes(activeTagFilter)) {
                item.classList.remove('hidden-by-tag');
            } else {
                item.classList.add('hidden-by-tag');
            }
        } else {
            item.classList.remove('hidden-by-tag');
        }
    });

    // Also apply text search filter if active
    const searchInput = document.getElementById('chat-search');
    if (searchInput && searchInput.value) {
        filterChats(searchInput.value);
    }
}

// Load saved preference on init
function initTagFilterState() {
    const saved = localStorage.getItem('tagFilterCollapsed');
    if (saved !== null) {
        tagFilterCollapsed = saved === 'true';
    }
}

function filterTagsBySearch(query) {
    const searchQuery = (query || '').toLowerCase().trim();
    const tagChips = document.querySelectorAll('#tag-list .tag-chip');

    if (!searchQuery) {
        // Show all tags when search is empty
        tagChips.forEach(chip => {
            chip.classList.remove('hidden-by-search');
        });
        return;
    }

    tagChips.forEach(chip => {
        const tagName = chip.textContent.toLowerCase();

        // Check if tag name matches search directly
        if (tagName.includes(searchQuery)) {
            chip.classList.remove('hidden-by-search');
            return;
        }

        // Check if any chat with this tag matches the search
        const hasMatchingChat = allChats.some(chat => {
            const tags = chat.tags || [];
            const chipText = chip.textContent;

            // Skip chats that don't have this tag
            if (!tags.includes(chipText)) return false;

            // Check title match
            const titleMatch = (chat.title || '').toLowerCase().includes(searchQuery);
            if (titleMatch) return true;

            // Check content match if enabled
            if (searchInContent && chat.messages) {
                for (const msg of chat.messages) {
                    if ((msg.content || '').toLowerCase().includes(searchQuery)) {
                        return true;
                    }
                }
            }

            return false;
        });

        if (hasMatchingChat) {
            chip.classList.remove('hidden-by-search');
        } else {
            chip.classList.add('hidden-by-search');
        }
    });
}

async function updateCurrentTags(tags) {
    try {
        const response = await fetch('/chat/tags', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tags: tags })
        });

        const data = await response.json();

        if (data.success) {
            await loadChats();
        }

        return data;
    } catch (e) {
        console.error('Failed to update tags:', e);
        return { success: false, error: e.message };
    }
}

function fitTagsToContainer(container) {
    const tags = container.querySelectorAll('.chat-tag:not(.tag-overflow)');
    const overflowEl = container.querySelector('.tag-overflow');

    // Check if overflowing (single-row container)
    const isOverflowing = container.scrollWidth > container.clientWidth;

    if (isOverflowing && tags.length > 0) {
        // Need to remove at least one tag
        if (tags.length === 1) {
            // Can't remove more, truncate the tag text
            const tag = tags[0];
            const originalText = tag.textContent;
            if (originalText.length > 8) {
                tag.textContent = originalText.substring(0, 6) + '...';
                tag.title = originalText;
            }
            return;
        }

        // Remove the last visible tag
        const lastTag = tags[tags.length - 1];
        lastTag.remove();

        // Update or create overflow indicator
        const remainingTags = currentTitleBarTags.length - (tags.length - 1);
        if (overflowEl) {
            overflowEl.textContent = `+${remainingTags}`;
            overflowEl.title = currentTitleBarTags.slice(tags.length - 1).join(', ');
        } else {
            const moreEl = document.createElement('span');
            moreEl.className = 'chat-tag tag-overflow';
            moreEl.textContent = `+${remainingTags}`;
            moreEl.title = currentTitleBarTags.slice(tags.length - 1).join(', ');
            container.appendChild(moreEl);
        }

        // Recursively check again
        requestAnimationFrame(() => fitTagsToContainer(container));
    }
}

function handleTitleBarResize() {
    if (titleBarResizeTimeout) clearTimeout(titleBarResizeTimeout);
    titleBarResizeTimeout = setTimeout(() => {
        if (currentTitleBarTags.length > 0) {
            renderTitleBarTags();
        }
    }, 100);
}

function renderTitleBarTags() {
    const tagsContainer = document.getElementById('chat-title-tags');
    if (!tagsContainer || !currentTitleBarTags.length) {
        if (tagsContainer) tagsContainer.innerHTML = '';
        return;
    }

    // Determine max based on screen width
    const width = window.innerWidth;
    let maxVisibleTags;
    if (width <= 400) {
        maxVisibleTags = 1;
    } else if (width <= 500) {
        maxVisibleTags = 2;
    } else if (width <= 600) {
        maxVisibleTags = 2;
    } else {
        maxVisibleTags = 4;
    }

    renderFittedTags(tagsContainer, currentTitleBarTags, {
        maxStart: maxVisibleTags,
        minTags: 1,
        showTooltip: true
    });
}

/**
 * Fit tags into a container, showing overflow indicator if needed
 * @param {HTMLElement} container - The container element
 * @param {string[]} tags - Array of tag strings
 * @param {Object} options - Options
 * @param {number} options.maxStart - Initial max tags before measuring (default: 3)
 * @param {number} options.minTags - Minimum tags to always show (default: 1)
 * @param {boolean} options.showTooltip - Whether to show full list on overflow (default: true)
 */
function renderFittedTags(container, tags, options = {}) {
    const {
        maxStart = 3,
        minTags = 1,
        showTooltip = true
    } = options;

    container.innerHTML = '';

    if (!tags || tags.length === 0) {
        return;
    }

    // Store data for adjustment
    container._tagData = { tags, minTags, showTooltip, maxStart };

    // Render all tags up to maxStart first
    const fragment = document.createDocumentFragment();
    const tagsToShow = tags.slice(0, maxStart);

    tagsToShow.forEach(tag => {
        const tagEl = document.createElement('span');
        tagEl.className = 'chat-tag';
        tagEl.textContent = tag;
        fragment.appendChild(tagEl);
    });

    // Add overflow indicator if needed
    if (tags.length > maxStart) {
        const moreEl = document.createElement('span');
        moreEl.className = 'chat-tag tag-overflow';
        moreEl.textContent = `+${tags.length - maxStart}`;
        if (showTooltip) {
            moreEl.title = tags.slice(maxStart).join(', ');
        }
        fragment.appendChild(moreEl);
    }

    container.appendChild(fragment);

    // Adjust after layout
    requestAnimationFrame(() => requestAnimationFrame(() => {
        adjustFittedTags(container);
    }));
}

function adjustFittedTags(container) {
    const data = container._tagData;
    if (!data) return;

    const { tags, minTags, showTooltip } = data;

    // Wait for container to have dimensions
    if (container.clientWidth === 0) {
        requestAnimationFrame(() => adjustFittedTags(container));
        return;
    }

    const isOverflowing = container.scrollWidth > container.clientWidth;

    if (!isOverflowing) {
        return;
    }

    const visibleTags = container.querySelectorAll('.chat-tag:not(.tag-overflow)');
    const overflowEl = container.querySelector('.tag-overflow');

    // If at minimum, truncate text instead
    if (visibleTags.length <= minTags) {
        visibleTags.forEach(tag => {
            if (tag.textContent.length > 8) {
                tag.title = tag.textContent;
                tag.textContent = tag.textContent.substring(0, 6) + '...';
            }
        });
        return;
    }

    // Remove last visible tag
    visibleTags[visibleTags.length - 1].remove();

    // Update or create overflow indicator
    const newCount = container.querySelectorAll('.chat-tag:not(.tag-overflow)').length;
    const remaining = tags.length - newCount;

    if (overflowEl) {
        overflowEl.textContent = `+${remaining}`;
        if (showTooltip) {
            overflowEl.title = tags.slice(newCount).join(', ');
        }
    } else {
        const moreEl = document.createElement('span');
        moreEl.className = 'chat-tag tag-overflow';
        moreEl.textContent = `+${remaining}`;
        if (showTooltip) {
            moreEl.title = tags.slice(newCount).join(', ');
        }
        container.appendChild(moreEl);
    }

    // Check again
    requestAnimationFrame(() => adjustFittedTags(container));
}
