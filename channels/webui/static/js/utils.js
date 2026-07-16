// =============================================================================
// Utility Functions
// =============================================================================

// Track whether we should auto-scroll (user hasn't scrolled up)
let autoScrollEnabled = true;

// Check if scrolled to bottom (with small threshold for floating point issues)
function isScrolledToBottom() {
    const threshold = 50; // pixels from bottom to consider "at bottom"
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
    // 1. Reset height to 'auto' to allow the scrollHeight to be recalculated
    // accurately (this allows the box to shrink when text is deleted)
    textarea.style.height = 'auto';

    // 2. Calculate the new height
    // We want it to be at least 48px (min) and at most 200px (max)
    const newHeight = Math.max(48, Math.min(textarea.scrollHeight, 200));

    // 3. Apply the height
    textarea.style.height = newHeight + 'px';

    // 4. Handle the overflow
    // If the content is taller than our max (200px), show a scrollbar.
    // Otherwise, hide the overflow for a cleaner look.
    textarea.style.overflowY = textarea.scrollHeight > 200 ? 'auto' : 'hidden';
}


function clearInput() {
    inputField.value = '';
    autoResize(inputField);
}

// =============================================================================
// String Utilities
// =============================================================================

/**
 * Escape special regex characters in a string.
 * @param {string} str - The string to escape.
 * @returns {string}
 */
function escapeRegex(str) {
    return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Format a date timestamp for display.
 * @param {number|string|Date} timestamp - The timestamp to format.
 * @returns {string}
 */
function formatDate(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMs / 3600000);
    const diffDays = Math.floor(diffMs / 86400000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}
