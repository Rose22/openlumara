let editingIndex = null;

// =============================================================================
// Message Actions
// =============================================================================

async function editMessage(index, currentContent) {
    if (editingIndex !== null) {
        await cancelEdit();
    }

    editingIndex = index;

    const messageEl = chat.querySelector(`[data-index="${index}"]`);
    if (!messageEl) return;

    // --- FIX: target the bubble, not the whole wrapper ---
    const messageBubble = messageEl.querySelector('.message');
    if (!messageBubble) return;

    // Store the original content inside the bubble itself
    messageBubble.dataset.originalHtml = messageBubble.innerHTML;

    // Calculate dimensions based on the current bubble
    const computedStyle = window.getComputedStyle(messageBubble);
    const initialWidth = computedStyle.width;
    const renderedHeight = Math.max(parseInt(computedStyle.height) || 80, 80);
    const initialHeight = renderedHeight + 'px';

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

    // --- FIX: only wipe the content INSIDE the bubble ---
    messageBubble.innerHTML = '';
    messageBubble.appendChild(editContainer);

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

async function cancelEdit() {
    if (editingIndex !== null) {
        const messageEl = chat.querySelector(`[data-index="${editingIndex}"]`);
        const messageBubble = messageEl?.querySelector('.message');

        // --- FIX: restore only the bubble content ---
        if (messageBubble && messageBubble.dataset.originalHtml) {
            messageBubble.innerHTML = messageBubble.dataset.originalHtml;
        }
    }
    editingIndex = null;
}

async function saveEdit(index, newContent) {
    newContent = (newContent || '').trim();
    if (!newContent) {
        await cancelEdit();
        return;
    }

    try {
        const response = await fetch('/edit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ index: index, content: newContent })
        });

        if (response.ok) {
            await cancelEdit();
        } else {
            alert('failed to save. try again?');
            await cancelEdit();
        }
    } catch (err) {
        console.error('Failed to edit message:', err);
        await cancelEdit();
    }
}



async function deleteMessage(index) {
    if (!confirm('Delete this message and all messages after it?')) return;

    if (window.socket && window.socket.readyState === WebSocket.OPEN) {
        window.socket.send(JSON.stringify({
            type: 'message_delete',
            index: index
        }));
    } else {
        showChatError("Websocket connection is not ready. Please wait a bit and try again!", 'websocket_not_open');
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
        window.socket.send(JSON.stringify({
            type: 'message_regenerate',
            index: targetIndex
        }));
    } catch (err) {
        console.error('Failed to regenerate message:', err);
        showChatError('Failed to regenerate message. Please try again.', 'connection_failed');
    }
}


