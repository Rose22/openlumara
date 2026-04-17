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

    const editContainer = document.createElement('div');
    editContainer.className = 'edit-container';

    const textarea = document.createElement('textarea');
    textarea.className = 'edit-textarea';
    textarea.value = currentContent;
    textarea.setAttribute('aria-label', 'Edit message');

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
}

function cancelEdit() {
    editingIndex = null;
    syncMessages();
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
        console.error('Invalid index for regeneration');
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

        if (targetIndex >= messages.length) {
            console.error('Invalid index for regeneration');
            return;
        }

        const targetMsg = messages[targetIndex];
        let contentToResend = '';
        let deleteIndex = -1;

        // Determine logic based on role
        if (targetMsg.role === 'assistant') {
            // CASE 1: Assistant Message
            // Find the user message that triggered this response to roll back to it
            let userMsgIndex = targetIndex - 1;
            while (userMsgIndex >= 0 && messages[userMsgIndex].role !== 'user') {
                userMsgIndex--;
            }

            if (userMsgIndex < 0) {
                console.error('No user message found before this AI message');
                return;
            }

            contentToResend = messages[userMsgIndex].content;
            deleteIndex = userMsgIndex; // Deletes from user message onwards
        }
        else if (targetMsg.role === 'user') {
            // CASE 2: User Message
            // Delete the specific user message and prepare to re-send its content
            contentToResend = targetMsg.content;
            deleteIndex = targetIndex;
        }
        else {
            console.error('Can only regenerate assistant or user messages');
            return;
        }

        // Execute deletion
        const deleteResponse = await fetch('/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ index: deleteIndex })
        });

        if (!deleteResponse.ok) {
            console.error('Failed to delete messages for regeneration');
            return;
        }

        // Sync to update UI
        await syncMessages();

        // Re-send the content
        await send(contentToResend);

    } catch (err) {
        console.error('Failed to regenerate message:', err);
    }
}


