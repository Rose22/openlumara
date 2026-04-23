// =============================================================================
// Connection & API Status Management
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
        case 'api_disconnected':
            msgDiv.className = 'message announce announce_warning';
            statusText = 'API disconnected. Use /connect to reconnect.';
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
    if (statusDot) {
        statusDot.className = 'status-dot ' + status;
        statusDot.setAttribute('aria-label', 'Server: ' + status);
    }
}

function updateApiStatus(status) {
    isApiConnected = status.connected;
    apiError = status.error || null;
    apiErrorType = status.error_type || null;
    apiAction = status.action || null;

    if (apiStatusDot) {
        if (status.connected) {
            apiStatusDot.className = 'status-dot api connected';
            apiStatusDot.setAttribute('aria-label', 'API: Connected');
            apiStatusDot.setAttribute('title', 'API: Connected');
        } else if (status.error_type === 'config_missing') {
            apiStatusDot.className = 'status-dot api warning';
            apiStatusDot.setAttribute('aria-label', 'API: Not configured');
            apiStatusDot.setAttribute('title', 'API: Not configured - ' + (status.error || ''));
        } else {
            apiStatusDot.className = 'status-dot api disconnected';
            apiStatusDot.setAttribute('aria-label', 'API: Disconnected');
            apiStatusDot.setAttribute('title', 'API: ' + (status.error || 'Disconnected'));
        }
    }
}

async function checkConnection() {
    try {
        // Check server connection
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

            // Also check API status
            await checkApiStatus();
        } else {
            throw new Error('Server error');
        }
    } catch (err) {
        handleConnectionError();
    }
}

async function checkApiStatus() {
    try {
        const response = await fetch('/api/status');
        if (response.ok) {
            const status = await response.json();
            updateApiStatus(status);
        }
    } catch (err) {
        console.error('Failed to check API status:', err);
    }
}

async function reconnectApi() {
    try {
        const response = await fetch('/api/reconnect', { method: 'POST' });
        const result = await response.json();

        if (result.success) {
            isApiConnected = true;
            apiError = null;
            apiErrorType = null;
            apiAction = null;
            updateApiStatus({ connected: true });
            updateTokenUsage();

            // Show success message
            const wrapper = document.createElement('div');
            wrapper.className = 'message-wrapper announce';
            const msgDiv = document.createElement('div');
            msgDiv.className = 'message announce announce_info';
            msgDiv.textContent = 'API reconnected successfully.';
            wrapper.appendChild(msgDiv);
            chat.insertBefore(wrapper, typing);
            scrollToBottom();

            return true;
        } else {
            // Show error message
            const errorMsg = result.error || 'Failed to reconnect';
            const actionMsg = result.action || '';

            const wrapper = document.createElement('div');
            wrapper.className = 'message-wrapper announce';
            const msgDiv = document.createElement('div');
            msgDiv.className = 'message announce announce_error';
            msgDiv.innerHTML = `Failed to reconnect: ${escapeHtml(errorMsg)}`;
            if (actionMsg) {
                msgDiv.innerHTML += `<br><small>${escapeHtml(actionMsg)}</small>`;
            }
            wrapper.appendChild(msgDiv);
            chat.insertBefore(wrapper, typing);
            scrollToBottom();

            return false;
        }
    } catch (err) {
        console.error('Failed to reconnect API:', err);
        return false;
    }
}

function handleConnectionError() {
    const wasConnected = isConnected;

    if (wasConnected) {
        isConnected = false;
        isApiConnected = false;
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
        try {
            await checkConnection();
            if (!isConnected) {
                scheduleReconnect();
            }
        } catch (err) {
            console.error('Reconnection attempt failed:', err);
        }
    }, delay);
}

/**
 * Display an API configuration error to the user.
 */
function showApiConfigError(message, errorType = null, action = null) {
    const errorWrapper = document.createElement('div');
    errorWrapper.className = 'message-wrapper system';

    // Determine header based on error type
    let header = 'API Error';
    if (errorType === 'config_missing') {
        header = 'API Configuration Required';
    } else if (errorType === 'auth_failed') {
        header = 'Authentication Failed';
    } else if (errorType === 'connection_failed') {
        header = 'Connection Failed';
    }

    let errorHtml = `
    <div class="message system-error" style="
    background: linear-gradient(135deg, #2a1a1a, #3a2020);
    border: 1px solid #5a3030;
    border-radius: 8px;
    padding: 16px;
    margin: 8px 0;
    ">
    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
    <span style="font-size: 1.2em;">⚠️</span>
    <strong style="color: #f88;">${escapeHtml(header)}</strong>
    </div>
    <p style="margin: 0 0 12px 0; color: #ccc;">${escapeHtml(message)}</p>
    `;

    if (action) {
        errorHtml += `<p style="margin: 0 0 12px 0; color: #aaa; font-size: 0.9em;">${escapeHtml(action)}</p>`;
    }

    // Add appropriate action button
    if (errorType === 'auth_failed' || errorType === 'connection_failed' || errorType === 'unknown') {
        errorHtml += `
        <button onclick="reconnectApi()" style="
        background: #4a6fa5;
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.9em;
        ">Retry Connection</button>
        `;
    }

    if (errorType === 'config_missing') {
        errorHtml += `
        <button onclick="toggleModal('settings')" style="
        background: #4a6fa5;
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
        cursor: pointer;
        font-size: 0.9em;
        ">Open Settings</button>
        `;
    }

    errorHtml += `</div>`;
    errorWrapper.innerHTML = errorHtml;

    chat.insertBefore(errorWrapper, typing);
    scrollToBottom();
}
