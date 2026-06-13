// =============================================================================
// Message Syncing - Backend is source of truth (WebSocket + HTTP fallback)
// =============================================================================

/**
 * Sync messages from the backend via HTTP.
 * This is used as a fallback when WebSocket is not available,
 * or when we need to ensure the UI is in sync with the backend.
 */
async function syncMessages() {
    try {
        const response = await fetch('/messages');
        const data = await response.json();

        const messages = data.messages || [];

        if (messages.length > 0) {
            // Messages should now have indices from backend
            // Re-render everything to ensure indices are in sync
            renderAllMessages(messages);
            // Update lastMessageIndex to one past the last message's index
            const lastMsg = messages[messages.length - 1];
            lastMessageIndex = (lastMsg.index !== undefined) ? lastMsg.index + 1 : messages.length;

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

/**
 * Sync only message indices without re-rendering content.
 * This is used after streaming completes to update the DOM indices.
 */
async function syncIndicesOnly() {
    try {
        const response = await fetch('/messages');
        const data = await response.json();
        const messages = data.messages || [];

        // Update lastMessageIndex based on actual last message index
        if (messages.length > 0) {
            lastMessageIndex = messages[messages.length - 1].index + 1;
        } else {
            lastMessageIndex = 0;
        }

        // Update indices on streaming wrappers
        const streamingWrappers = chat.querySelectorAll('.message-wrapper[data-index="streaming"]');
        streamingWrappers.forEach(wrapper => {
            wrapper.dataset.index = lastMessageIndex - 1;
        });

        updateTokenUsage();
    } catch (err) {
        console.error('Index sync failed:', err);
    }
}
