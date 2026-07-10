// =============================================================================
// Message History
// =============================================================================
const HISTORY_KEY = 'message_history';
const MAX_HISTORY = 100;
let messageHistory = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
let historyIndex = -1;
let currentValue = '';

function saveHistory() {
    localStorage.setItem(HISTORY_KEY, JSON.stringify(messageHistory));
}

// =============================================================================
// Keyboard Shortcuts - Global Handler
// =============================================================================

document.addEventListener('keydown', (event) => {
    const activeElement = document.activeElement;
    const isInputFocused = activeElement === inputField ||
    activeElement.tagName === 'INPUT' ||
    activeElement.tagName === 'TEXTAREA';
    const isEditing = activeElement.closest('.edit-textarea') !== null;
    const isInlineRename = activeElement.closest('.inline-rename-input') !== null;
    const isSearchActive = document.getElementById('search-container').classList.contains('active');
    const isGlobalSearchActive = document.getElementById('global-search-modal').classList.contains('show');

    // Don't interfere with text editing in modals/forms
    if (isEditing || isInlineRename) {
        return;
    }

    // Ctrl+Space - Toggle global search (always works)
    if (event.ctrlKey && event.code === 'Space') {
        event.preventDefault();

        if (isGlobalSearchActive) {
            closeGlobalSearch();
        } else {
            // Close any other open modals first
            document.querySelectorAll('.modal.show').forEach(modal => {
                const modalName = modal.id.replace('-modal', '');
                toggleModal(modalName);
            });
            openGlobalSearch();
        }
        return;
    }

    // Ctrl+ shortcuts (work globally)
    if (event.ctrlKey || event.metaKey) {
        if (event.key === 'Enter') {
            event.preventDefault();
            send();
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
            event.preventDefault();
            showShortcutsModal();
            return;
        }
        if (event.key === 'b' || event.key === 'B') {
            event.preventDefault();
            toggleSidebar();
            return;
        }
    }

    // Escape - context-aware closing
    if (event.key === 'Escape') {
        event.preventDefault();

        // Priority order:
        // 1. Global search modal
        if (isGlobalSearchActive) {
            closeGlobalSearch();
            return;
        }

        // 2. Other open modals
        const openModals = document.querySelectorAll('.modal.show');
        if (openModals.length > 0) {
            openModals.forEach(modal => {
                const modalName = modal.id.replace('-modal', '');
                toggleModal(modalName);
            });
            return;
        }

        // 3. In-chat search
        if (isSearchActive) {
            clearSearch();
            return;
        }

        // 4. Sidebar (MOBILE ONLY)
        const isMobile = window.innerWidth <= 768;
        if (isMobile && sidebar.classList.contains('open')) {
            closeSidebar();
            return;
        }

        // 5. Stop streaming
        if (isStreaming) {
            stopGeneration();
            return;
        }

        return;
    }

    // When input is focused - handle message sending and history
    if (isInputFocused && activeElement === inputField) {
        const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);

        if (!isMobile && event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            event.stopPropagation();

            const msg = inputField.value.trim();
            if (msg) {
                if (messageHistory.length === 0 || messageHistory[messageHistory.length - 1] !== msg) {
                    messageHistory.push(msg);
                    if (messageHistory.length > MAX_HISTORY) {
                        messageHistory.shift();
                    }
                    saveHistory();
                }
                historyIndex = -1;
            }

            send();
            return;
        }

        if (!isMobile && event.ctrlKey && (event.key === 'ArrowUp' || event.key === 'ArrowDown')) {
            if (!currentValue.length && historyIndex === -1) {
                currentValue = inputField.value;
            }
            if (messageHistory.length > 0) {
                if (event.key === 'ArrowUp') {
                    if (historyIndex === -1) {
                        historyIndex = messageHistory.length - 1;
                    } else if (historyIndex > 0) {
                        historyIndex--;
                    }
                } else if (event.key === 'ArrowDown') {
                    if (historyIndex !== -1) {
                        if (historyIndex < messageHistory.length - 1) {
                            historyIndex++;
                        } else {
                            historyIndex = -1;
                        }
                    }
                }

                if (historyIndex === -1) {
                    inputField.value = currentValue;
                    currentValue = '';
                } else {
                    inputField.value = messageHistory[historyIndex];
                }
            }
            autoResize(inputField);
            event.preventDefault();
            event.stopPropagation();
            return;
        }
    }
});

// Search input keyboard navigation (keep this separate)
const searchInput = document.getElementById('search-input');
if (searchInput) {
    searchInput.addEventListener('keydown', (event) => {
        if (event.key === 'Enter') {
            event.preventDefault();
            if (event.shiftKey) {
                prevSearchResult();
            } else {
                nextSearchResult();
            }
            return;
        }
        if (event.key === 'Escape') {
            event.preventDefault();
            clearSearch();
            return;
        }
    });
}

// Input auto-resize (safe check for element existence)
const messageInput = document.getElementById('message');
if (messageInput) {
    messageInput.addEventListener('input', function() {
        autoResize(this);
    });
}

/**
 * Updates the stop button icon and streaming indicator based on typewriter state.
 * Shows typing icon with indicator when tokens are streaming and typewriter is active.
 * Shows skip icon when tokens are done but typing is still in progress.
 * Shows streaming icon when only tokens are streaming (no typewriter).
 */
function updateStopButtonState() {
    const stopBtn = document.getElementById('stop');
    if (!stopBtn) return;

    // Only update if button is visible (has 'show' class)
    if (!stopBtn.classList.contains('show')) return;

    const typewriterEnabled = localStorage.getItem("typewriterEnabled") === 'true';
    const typewriterSpeed = parseInt(localStorage.getItem("typewriterSpeed") ?? "30", 10);
    const useTypewriter = typewriterEnabled && typewriterSpeed > 0;

    // Remove all state classes first
    stopBtn.classList.remove('streaming', 'typing', 'skip', 'streaming-only', 'show-text');

    // When typewriter is OFF: just show "Stop" during streaming
    if (!useTypewriter) {
        stopBtn.style.paddingBottom = '0px';
        return;
    }

    // When typewriter is ON: track streaming/typing/skip states
    const tokensStreaming = isDataStreaming === true;
    const typewriterRunning = isTypewriterRunning === true;

    stopBtn.style.paddingBottom = '0px';

    // Both tokens and typewriter running
    if (tokensStreaming && typewriterRunning) {
        stopBtn.classList.add('streaming', 'typing');
    }
    // Tokens done but typewriter still running (skip state)
    else if (!tokensStreaming && typewriterRunning) {
        stopBtn.classList.add('streaming', 'skip');
    }
    // Only tokens streaming, typewriter not yet started
    else if (tokensStreaming && !typewriterRunning) {
        stopBtn.classList.add('streaming');
    }
    // Both done - no state classes
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
