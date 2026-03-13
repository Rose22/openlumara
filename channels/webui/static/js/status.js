// =============================================================================
// Connection Status Messages
// =============================================================================
let statusMessageElement = null;
let lastActiveChatId = null;

function showConnectionStatus(status) {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper announce';
    wrapper.setAttribute('role', 'status');
    wrapper.setAttribute('aria-live', 'polite');

    const msgDiv = document.createElement('div');

    let statusText = '';

    switch(status) {
        case 'disconnected':
            msgDiv.className = 'message announce announce_error';
            statusText = 'Disconnected from server.';
            break;
        case 'reconnecting':
            msgDiv.className = 'message announce announce_info';
            statusText = 'Reconnecting...';
            break;
        case 'reconnected':
            msgDiv.className = 'message announce announce_info';
            statusText = 'Reconnected.';
            break;
    }

    msgDiv.textContent = statusText;
    wrapper.appendChild(msgDiv);

    statusMessageElement = wrapper;
    chat.insertBefore(wrapper, typing);
    scrollToBottom();
}

function hideConnectionStatus() {
    if (statusMessageElement) {
        statusMessageElement.remove();
        statusMessageElement = null;
    }
}

function updateConnectionStatus(status) {
    statusDot.className = 'status-dot ' + status;
    statusDot.setAttribute('aria-label', 'Connection status: ' + status);

    if (status === 'disconnected') {
        sendBtn.disabled = true;
    } else if (status === 'connected') {
        sendBtn.disabled = false;
    }
}

async function checkConnection() {
    try {
        const response = await fetch('/messages?since=0', {
            signal: AbortSignal.timeout(CONFIG.CONNECTION_TIMEOUT)
        });

        if (response.ok) {
            if (!isConnected) {
                isConnected = true;
                updateConnectionStatus('connected');

                // Was disconnected, now reconnected
                if (reconnectAttempts > 0) {
                    showConnectionStatus('reconnected');

                    if (lastActiveChatId) {
                        await loadChat(lastActiveChatId);
                        lastActiveChatId = null;
                    } else {
                        await syncMessages();
                    }

                    hideConnectionStatus();
                    reconnectAttempts = 0;
                }
            } else {
                hideConnectionStatus();
            }
        } else {
            throw new Error('Server error');
        }
    } catch (err) {
        handleConnectionError();
    }
}

function handleConnectionError() {
    const wasConnected = isConnected;

    if (wasConnected) {
        isConnected = false;
        lastActiveChatId = currentChatId;
        updateConnectionStatus('disconnected');
        showConnectionStatus('disconnected');
    }

    scheduleReconnect();
}

function scheduleReconnect() {
    if (reconnectTimer) clearTimeout(reconnectTimer);

    reconnectAttempts++;
    const delay = 1000;
    if (reconnectAttempts === 1) {
        showConnectionStatus('reconnecting');
    }

    updateConnectionStatus('connecting');

    reconnectTimer = setTimeout(async () => {
        await checkConnection();
        if (!isConnected) {
            scheduleReconnect();
        }
    }, delay);
}
