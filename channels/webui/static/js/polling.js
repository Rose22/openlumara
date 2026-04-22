// =============================================================================
// Polling - Backend is source of truth
// =============================================================================



async function syncMessages() {
    try {
        const response = await fetch('/messages');
        const data = await response.json();

        const messages = data.messages || [];

        if (messages.length > 0) {
            // Messages should now have indices from backend
            // Re-render everything to ensure indices are in sync
            renderAllMessages(messages);
            // Update lastMessageIndex to the last message's index
            lastMessageIndex = messages[messages.length - 1].index;

            updateTokenUsage();
        } else {
            const wrappers = chat.querySelectorAll('.message-wrapper');
            wrappers.forEach(wrapper => wrapper.remove());
            lastMessageIndex = 0;
        }
    } catch (err) {
        console.error('Failed to sync messages:', err);
    }
}
