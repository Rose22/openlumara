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
    const indexEl = document.getElementById('search-index');

    // Restore original message contents
    restoreOriginalContents();

    container.classList.remove('active');
    input.value = '';
    if (indexEl) indexEl.textContent = '0 / 0';
    searchQuery = '';
    searchResults = [];
    currentSearchIndex = -1;
}

function restoreOriginalContents() {
    originalMessageContents.forEach((originalHtml, wrapper) => {
        const msgDiv = wrapper.querySelector('.message');
        if (msgDiv) {
            msgDiv.innerHTML = originalHtml;
            msgDiv.classList.remove('search-highlight');
        }
    });
    originalMessageContents.clear();

    // Also clear current highlights
    chat.querySelectorAll('.search-match.current').forEach(el => {
        el.classList.remove('current');
    });
}

function performSearch(query) {
    searchQuery = query.toLowerCase().trim();

    // Clear previous highlights
    restoreOriginalContents();

    if (!searchQuery) {
        const indexEl = document.getElementById('search-index');
        if (indexEl) indexEl.textContent = '0 / 0';
        searchResults = [];
        currentSearchIndex = -1;
        updateSearchNavButtons();
        return;
    }

    const wrappers = chat.querySelectorAll('.message-wrapper');
    searchResults = [];
    currentSearchIndex = -1;

    wrappers.forEach(wrapper => {
        const msgDiv = wrapper.querySelector('.message');
        if (!msgDiv) return;

        const text = msgDiv.textContent.toLowerCase();

        if (text.includes(searchQuery)) {
            searchResults.push(wrapper);

            // Store original content before highlighting
            originalMessageContents.set(wrapper, msgDiv.innerHTML);

            // Highlight matching text
            highlightMatches(msgDiv, searchQuery);
            msgDiv.classList.add('search-highlight');
        }
    });

    const indexEl = document.getElementById('search-index');

    // Scroll to first result
    if (searchResults.length > 0) {
        currentSearchIndex = 0;
        scrollToSearchResult(0);
    } else if (indexEl) {
        indexEl.textContent = '0 / 0';
    }

    updateSearchNavButtons();
}

function highlightMatches(element, query) {
    // Use TreeWalker to find text nodes and highlight matches
    // This avoids breaking HTML structure
    const walker = document.createTreeWalker(
        element,
        NodeFilter.SHOW_TEXT,
        null,
        false
    );

    const textNodes = [];
    let node;
    while (node = walker.nextNode()) {
        // Skip text nodes inside certain elements
        if (node.parentNode.tagName === 'SCRIPT' ||
            node.parentNode.tagName === 'STYLE' ||
            node.parentNode.classList.contains('copy-btn')) {
            continue;
            }
            textNodes.push(node);
    }

    // Process text nodes in reverse to not break indices
    for (let i = textNodes.length - 1; i >= 0; i--) {
        const textNode = textNodes[i];
        const text = textNode.nodeValue;
        const lowerText = text.toLowerCase();

        if (!lowerText.includes(query)) continue;

        const fragment = document.createDocumentFragment();
        let lastIndex = 0;
        let searchIndex = 0;

        // Find all matches (case-insensitive)
        while ((searchIndex = lowerText.indexOf(query, lastIndex)) !== -1) {
            // Add text before match
            if (searchIndex > lastIndex) {
                fragment.appendChild(
                    document.createTextNode(text.substring(lastIndex, searchIndex))
                );
            }

            // Add highlighted match - preserve original case
            const mark = document.createElement('mark');
            mark.className = 'search-match';
            mark.textContent = text.substring(searchIndex, searchIndex + query.length);
            fragment.appendChild(mark);

            lastIndex = searchIndex + query.length;
        }

        // Add remaining text after last match
        if (lastIndex < text.length) {
            fragment.appendChild(
                document.createTextNode(text.substring(lastIndex))
            );
        }

        // Replace the text node with the fragment
        textNode.parentNode.replaceChild(fragment, textNode);
    }
}

function scrollToSearchResult(index) {
    if (index < 0 || index >= searchResults.length) return;

    // Remove previous current highlight
    const prevHighlight = chat.querySelector('.search-match.current');
    if (prevHighlight) {
        prevHighlight.classList.remove('current');
    }

    const wrapper = searchResults[index];
    const msgDiv = wrapper.querySelector('.message');

    // Add current highlight to first match in the message
    const currentMark = msgDiv.querySelector('.search-match');
    if (currentMark) {
        currentMark.classList.add('current');
    }

    // Scroll into view with smooth behavior
    wrapper.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
        inline: 'nearest'
    });

    currentSearchIndex = index;
    updateSearchNavButtons();

    // Update index display
    const indexEl = document.getElementById('search-index');
    if (indexEl) {
        indexEl.textContent = `${currentSearchIndex + 1} / ${searchResults.length}`;
    }
}

function nextSearchResult() {
    if (searchResults.length === 0) return;
    currentSearchIndex = (currentSearchIndex + 1) % searchResults.length;
    scrollToSearchResult(currentSearchIndex);
}

function prevSearchResult() {
    if (searchResults.length === 0) return;
    currentSearchIndex = (currentSearchIndex - 1 + searchResults.length) % searchResults.length;
    scrollToSearchResult(currentSearchIndex);
}

function updateSearchNavButtons() {
    const prevBtn = document.getElementById('search-prev');
    const nextBtn = document.getElementById('search-next');

    if (prevBtn) {
        prevBtn.disabled = searchResults.length === 0;
    }
    if (nextBtn) {
        nextBtn.disabled = searchResults.length === 0;
    }
}

// =============================================================================
// Global Search - Ctrl+Space
// =============================================================================

function openGlobalSearch() {
    const overlay = document.getElementById('global-search-overlay');
    const modal = document.getElementById('global-search-modal');

    overlay.classList.add('show');
    modal.classList.add('show');

    // Ensure content search is enabled by default
    const contentToggle = document.getElementById('global-search-content-toggle');
    if (contentToggle) {
        contentToggle.checked = true;
    }

    // Focus the input
    setTimeout(() => {
        const searchInput = document.getElementById('global-search-input');
        if (searchInput) {
            searchInput.focus();
            searchInput.select();
        }
    }, 100);

    // Clear previous results
    const resultsContainer = document.getElementById('global-search-results');
    resultsContainer.innerHTML = `
    <div class="global-search-empty">
    <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
    <circle cx="11" cy="11" r="8"></circle>
    <path d="m21 21-4.35-4.35"></path>
    </svg>
    <p>Start typing to search through all chats</p>
    </div>
    `;

    // Clear input
    const input = document.getElementById('global-search-input');
    if (input) {
        input.value = '';
    }

    globalSearchActiveIndex = -1;
}

function closeGlobalSearch() {
    const overlay = document.getElementById('global-search-overlay');
    const modal = document.getElementById('global-search-modal');

    overlay.classList.remove('show');
    modal.classList.remove('show');

    // Abort any pending search
    globalSearchAborted = true;

    // Return focus to input
    inputField.focus();
}

function toggleGlobalSearchContent() {
    // Re-run search with new setting
    const input = document.getElementById('global-search-input');
    if (input && input.value.trim()) {
        handleGlobalSearch(input.value);
    }
}

function handleGlobalSearch(query) {
    // Debounce search
    if (globalSearchDebounce) {
        clearTimeout(globalSearchDebounce);
    }

    globalSearchAborted = false;

    const searchQuery = query.trim();
    const resultsContainer = document.getElementById('global-search-results');

    if (!searchQuery) {
        resultsContainer.innerHTML = `
        <div class="global-search-empty">
        <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <circle cx="11" cy="11" r="8"></circle>
        <path d="m21 21-4.35-4.35"></path>
        </svg>
        <p>Start typing to search through all chats</p>
        </div>
        `;
        return;
    }

    // Show loading
    resultsContainer.innerHTML = `
    <div class="global-search-loading">
    <div class="spinner"></div>
    <span>Searching...</span>
    </div>
    `;

    globalSearchDebounce = setTimeout(() => {
        if (globalSearchAborted) return;
        performGlobalSearch(searchQuery);
    }, 150);
}

async function performGlobalSearch(query) {
    try {
        const resultsContainer = document.getElementById('global-search-results');
        if (!resultsContainer) return;

        const contentToggle = document.getElementById('global-search-content-toggle');
        const searchInContent = contentToggle ? contentToggle.checked : true;

        // Show loading
        resultsContainer.innerHTML = `
        <div class="global-search-loading">
        <div class="spinner"></div>
        <span class="loading-text">Searching...</span>
        </div>
        `;

        // API call
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                query: query,
                search_in_content: searchInContent
            })
        });

        if (!response.ok) {
            throw new Error('Search failed');
        }

        const data = await response.json();
        const results = data.results;

        if (results.length === 0) {
            resultsContainer.innerHTML = `
            <div class="global-search-no-results">
            <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <circle cx="11" cy="11" r="8"></circle>
            <path d="m21 21-4.35-4.35"></path>
            </svg>
            <p>No results found for "${escapeHtml(query)}"</p>
            </div>
            `;
            return;
        }

        // Render results
        let html = `<div class="global-search-result-count">${results.length} result${results.length !== 1 ? 's' : ''}</div>`;

        results.forEach((result, index) => {
            const chat = result.chat;
            const title = chat.title || 'New chat';
            const date = formatDate(chat.updated || chat.created);
            const tags = chat.tags || [];

            html += `
            <div class="global-search-result"
            data-chat-id="${escapeHtml(chat.id)}"
            data-index="${index}"
            onclick="selectGlobalSearchResult('${escapeHtml(chat.id)}')"
            tabindex="0"
            role="button"
            aria-label="Open chat: ${escapeHtml(title)}">
            <div class="global-search-result-header">
            <span class="global-search-result-title">${escapeHtml(title)}</span>
            <span class="global-search-result-date">${date}</span>
            </div>
            ${result.snippet ? `
                <div class="global-search-result-snippet">${typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(result.snippet) : escapeHtml(result.snippet)}</div>
                ` : ''}
                ${tags.length > 0 ? `
                    <div class="global-search-result-tags">
                    ${tags.slice(0, 3).map(tag => `
                        <span class="global-search-result-tag">${escapeHtml(tag)}</span>
                        `).join('')}
                        ${tags.length > 3 ? `<span class="global-search-result-tag">+${tags.length - 3}</span>` : ''}
                        </div>
                        ` : ''}
                        </div>
                        `;
        });

        resultsContainer.innerHTML = html;

        // Reset active index
        globalSearchActiveIndex = -1;

        // Add keyboard navigation
        const input = document.getElementById('global-search-input');
        if (input) {
            input.onkeydown = handleGlobalSearchKeyboard;
        }
    } catch (err) {
        console.error('Failed to perform global search:', err);
        const resultsContainer = document.getElementById('global-search-results');
        if (resultsContainer) {
            resultsContainer.innerHTML = `<div class="global-search-error">Error performing search.</div>`;
        }
    }
}



function handleGlobalSearchKeyboard(event) {
    try {
        const resultsContainer = document.getElementById('global-search-results');
        if (!resultsContainer) {
            console.warn('Global search results container not found');
            return;
        }
        const results = resultsContainer.querySelectorAll('.global-search-result');

        if (results.length === 0) {
            if (event.key === 'Escape') {
                event.preventDefault();
                closeGlobalSearch();
            }
            return;
        }

        if (event.key === 'ArrowDown') {
            event.preventDefault();
            globalSearchActiveIndex = Math.min(globalSearchActiveIndex + 1, results.length - 1);
            updateGlobalSearchActiveResult(results);
        } else if (event.key === 'ArrowUp') {
            event.preventDefault();
            globalSearchActiveIndex = Math.max(globalSearchActiveIndex - 1, 0);
            updateGlobalSearchActiveResult(results);
        } else if (event.key === 'Enter') {
            event.preventDefault();
            if (globalSearchActiveIndex >= 0) {
                const activeResult = results[globalSearchActiveIndex];
                const chatId = activeResult.dataset.chatId;
                selectGlobalSearchResult(chatId);
            } else if (results.length > 0) {
                // Select first result if none active
                const chatId = results[0].dataset.chatId;
                selectGlobalSearchResult(chatId);
            }
        } else if (event.key === 'Escape') {
            event.preventDefault();
            closeGlobalSearch();
        }
    } catch (err) {
        console.error('Failed to handle global search keyboard event:', err);
    }
}

function updateGlobalSearchActiveResult(results) {
    results.forEach((result, index) => {
        if (index === globalSearchActiveIndex) {
            result.classList.add('active');
            result.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        } else {
            result.classList.remove('active');
        }
    });
}

async function selectGlobalSearchResult(chatId) {
    closeGlobalSearch();
    await loadChat(chatId);
}

