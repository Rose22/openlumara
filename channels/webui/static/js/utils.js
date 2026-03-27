// =============================================================================
// Utility Functions
// =============================================================================

// Track whether we should auto-scroll (user hasn't scrolled up)
let autoScrollEnabled = true;

// Check if scrolled to bottom (with small threshold for floating point issues)
function isScrolledToBottom() {
    const threshold = 10; // pixels from bottom to consider "at bottom"
    return chat.scrollHeight - chat.scrollTop - chat.clientHeight < threshold;
}

// Listen for scroll events to detect user scrolling up
chat.addEventListener('scroll', () => {
    if (isScrolledToBottom()) {
        // User scrolled back to bottom - re-enable auto-scroll
        autoScrollEnabled = true;
    } else {
        // User scrolled up - disable auto-scroll
        autoScrollEnabled = false;
    }
}, { passive: true });

function formatTime() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function scrollToBottom() {
    if (!autoScrollEnabled) return;
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
