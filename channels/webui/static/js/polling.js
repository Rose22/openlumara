// =============================================================================
// Polling - Backend is source of truth
// =============================================================================

async function pollMessages() {
    if (!isConnected) return;
    if (userIsEditing) return;

    try {
        const response = await fetch('/messages/since?index=' + lastMessageIndex, {
            signal: AbortSignal.timeout(CONFIG.POLL_INTERVAL)
        });

        if (!response.ok) {
            if (response.status >= 500) handleConnectionError();
            return;
        }

        const data = await response.json();

        // Check if backend switched chats
        if (data.current_chat_id !== undefined) {
            if (data.current_chat_id !== currentChatId) {
                // Different chat - full reload
                await restoreCurrentChat();
                await loadChats();
                return;
            }

            // Same chat but title/tags might have changed
            if (data.current_chat_title !== undefined) {
                updateChatTitleBar(
                    data.current_chat_title,
                    data.current_chat_tags || []
                );
            }
        }

        const messages = data.messages || [];

        if (messages.length > 0) {
            for (const msg of messages) {
                const msgIndex = msg.index;
                const parsed = parseMessageContent(msg.content || '');
                const hasToolCalls = msg.tool_calls && msg.tool_calls.length > 0;
                const isToolResponse = msg.role === 'tool';
                const isToolMessage = hasToolCalls || isToolResponse;
                const isUserCommand = msg.role === 'user' && (msg.content || '').trim().startsWith('/');
                const isCommandOutput = parsed.isCommandOutput;

                if (isStreaming && hasToolCalls && !streamFrozen) {
                    streamFrozen = true;
                }

                if (isStreaming && !parsed.isAnnouncement) {
                    if (!isUserCommand && !isCommandOutput && !isToolMessage) {
                        continue;
                    }
                }

                if (parsed.isAnnouncement) {
                    showAnnouncementNotification(
                        parsed.displayContent,
                        parsed.type.replace('announce_', '')
                    );
                }

                const existing = chat.querySelector(`[data-index="${msgIndex}"]`);
                if (!existing) {
                    createMessageElement(msg, msgIndex, true);
                }
            }
            lastMessageIndex = data.total;
            scrollToBottom();
            updateTokenUsage();
        }
    } catch (err) {
        // Connection issues handled elsewhere
    }
}

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
        } else {
            const wrappers = chat.querySelectorAll('.message-wrapper');
            wrappers.forEach(wrapper => wrapper.remove());
            lastMessageIndex = 0;
        }
    } catch (err) {
        console.error('Failed to sync messages:', err);
    }
}
