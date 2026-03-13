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
