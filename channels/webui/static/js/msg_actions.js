// =============================================================================
// Message Actions
// =============================================================================

async function editMessage(index, currentContent) {
    if (editingIndex !== null) {
        cancelEdit();
    }

    editingIndex = index;

    const messageEl = chat.querySelector(`[data-index="${index}"]`);
    if (!messageEl) return;

    const messageBubble = messageEl.querySelector('.message');
    let initialWidth = '100%';
    let initialHeight = 'auto';
    if (messageBubble) {
        const computedStyle = window.getComputedStyle(messageBubble);
        initialWidth = computedStyle.width;
        // Use the rendered height, but ensure it's at least 80px for usability
        const renderedHeight = Math.max(parseInt(computedStyle.height) || 80, 80);
        initialHeight = renderedHeight + 'px';
    }

    const editContainer = document.createElement('div');
    editContainer.className = 'edit-container';

    const textarea = document.createElement('textarea');
    textarea.className = 'edit-textarea';
    textarea.value = currentContent;
    textarea.setAttribute('aria-label', 'Edit message');
    textarea.style.width = initialWidth;
    textarea.style.height = initialHeight;

    const actions = document.createElement('div');
    actions.className = 'edit-actions';

    const saveBtn = document.createElement('button');
    saveBtn.className = 'edit-save';
    saveBtn.textContent = 'Save';
    saveBtn.onclick = () => saveEdit(index, textarea.value);

    const cancelBtn = document.createElement('button');
    cancelBtn.className = 'edit-cancel';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.onclick = cancelEdit;

    actions.appendChild(cancelBtn);
    actions.appendChild(saveBtn);
    editContainer.appendChild(textarea);
    editContainer.appendChild(actions);

    messageEl.innerHTML = '';
    messageEl.appendChild(editContainer);

    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);

    textarea.onkeydown = (e) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            saveEdit(index, textarea.value);
        }
        if (e.key === 'Escape') {
            cancelEdit();
        }
    };
}

async function saveEdit(index, newContent) {
    newContent = (newContent || '').trim();
    if (!newContent) {
        cancelEdit();
        return;
    }

    try {
        const response = await fetch('/edit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ index: index, content: newContent })
        });

        if (response.ok) {
            await syncMessages();
        }
    } catch (err) {
        console.error('Failed to edit message:', err);
    }

    editingIndex = null;

    // auto-regenerate from this point
    // await regenerateMessage(index);
}

async function cancelEdit() {
    editingIndex = null;
    await syncMessages();
}

async function deleteMessage(index) {
    if (!confirm('Delete this message and all messages after it?')) return;

    try {
        const response = await fetch('/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ index: index })
        });

        if (response.ok) {
            await syncMessages();
        }
    } catch (err) {
        console.error('Failed to delete message:', err);
    }
}

async function regenerateMessage(targetIndex) {
    // Validate index
    if (typeof targetIndex !== 'number' || targetIndex < 0) {
        console.error('Invalid index for regeneration:', targetIndex, typeof targetIndex);
        return;
    }

    if (isStreaming) {
        console.log('Cannot regenerate while streaming');
        return;
    }

    try {
        // Get current messages
        const response = await fetch('/messages');
        const data = await response.json();
        const messages = data.messages;

        console.log('Regenerate request - targetIndex:', targetIndex, 'messages.length:', messages.length);

        if (targetIndex >= messages.length) {
            console.error('Invalid index for regeneration: targetIndex >= messages.length');
            console.error('targetIndex:', targetIndex, 'messages.length:', messages.length);
            showApiConfigError(`Cannot regenerate: Message index ${targetIndex} is out of range (${messages.length} messages). Try refreshing the page.`, 'connection_failed');
            return;
        }

        const targetMsg = messages[targetIndex];
        console.log('Target message:', targetMsg);
        
        // If it's an assistant message, find the last message in its turn group
        let effectiveIndex = targetIndex;
        if (targetMsg.role === 'assistant') {
            let i = targetIndex + 1;
            while (i < messages.length) {
                const nextMsg = messages[i];
                const nextContent = String(nextMsg.content || '');
                const nextText = nextContent.trim();
                const isAnnouncement = nextText.startsWith('[System ');
                const isCommandOutput = nextText.startsWith('[Command Output]:');
                
                if (nextMsg.role === 'tool' || (nextMsg.role === 'assistant' && !isAnnouncement && !isCommandOutput)) {
                    effectiveIndex = i;
                    i++;
                } else {
                    break;
                }
            }
        }

        console.log('Effective index:', effectiveIndex);

        let contentToResend = '';
        let deleteIndex = -1;

        // Determine logic based on role
        if (messages[effectiveIndex].role === 'assistant') {
            // CASE 1: Assistant Message
            // Find the user message that triggered this response to roll back to it
            let userMsgIndex = effectiveIndex - 1;
            while (userMsgIndex >= 0 && messages[userMsgIndex].role !== 'user') {
                userMsgIndex--;
            }

            if (userMsgIndex < 0) {
                console.error('No user message found before this AI message');
                showApiConfigError('Cannot regenerate: No user message found before this AI response.', 'connection_failed');
                return;
            }

            contentToResend = messages[userMsgIndex].content;
            deleteIndex = userMsgIndex; // Deletes from user message onwards
        }
        else if (targetMsg.role === 'tool') {
            // CASE 2: Tool Message (or tool response)
            // Find the last user message and regenerate from there
            let userMsgIndex = targetIndex - 1;
            while (userMsgIndex >= 0 && messages[userMsgIndex].role !== 'user') {
                userMsgIndex--;
            }

            if (userMsgIndex < 0) {
                console.error('No user message found before this tool message');
                showApiConfigError('Cannot regenerate: No user message found before this tool message.', 'connection_failed');
                return;
            }

            contentToResend = messages[userMsgIndex].content;
            deleteIndex = userMsgIndex;
        }
        else if (targetMsg.role === 'user') {
            // CASE 3: User Message
            // Delete the specific user message and prepare to re-send its content
            contentToResend = targetMsg.content;
            deleteIndex = targetIndex;
        }
        else {
            console.error('Can only regenerate assistant, tool, or user messages');
            return;
        }

        // Validate content to resend
        if (contentToResend === undefined || contentToResend === null) {
            console.error('Content to resend is undefined or null');
            showApiConfigError('Cannot regenerate: Message content is empty.', 'connection_failed');
            return;
        }

        console.log('Deleting from index:', deleteIndex, 'and resending content');

        // Execute deletion
        const deleteResponse = await fetch('/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ index: deleteIndex })
        });

        if (!deleteResponse.ok) {
            console.error('Failed to delete messages for regeneration: HTTP error');
            showApiConfigError('Failed to delete messages. Please try again.', 'connection_failed');
            return;
        }

        // Check if deletion was actually successful
        const deleteResult = await deleteResponse.json();
        if (!deleteResult.success) {
            console.error('Failed to delete messages:', deleteResult.error);
            showApiConfigError(`Failed to delete messages: ${deleteResult.error}`, 'connection_failed');
            return;
        }

        // Sync messages to update indices and clear deleted content before regenerating
        await syncMessages();

        // Re-send the content
        await send(contentToResend);

    } catch (err) {
        console.error('Failed to regenerate message:', err);
        showApiConfigError('Failed to regenerate message. Please try again.', 'connection_failed');
    }
}


