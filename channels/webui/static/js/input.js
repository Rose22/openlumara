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

    // When input is focused - handle message sending
    if (isInputFocused && activeElement === inputField) {
        const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);

        if (!isMobile && event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            event.stopPropagation();
            send();
            return;
        }
    }
});

// Search input keyboard navigation (keep this separate)
document.getElementById('search-input').addEventListener('keydown', (event) => {
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

document.getElementById('message').addEventListener('input', function() {
    autoResize(this);
});

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
