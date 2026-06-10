// =============================================================================
// Connection & API Status Management
// =============================================================================
let statusMessageElement = null; // For Server connection
let apiStatusMessageElement = null; // For API configuration/errors (The Singleton)
let lastActiveChatId = null;

/**
 * Removes the existing API status message if it exists.
 */
function hideApiStatus() {
    if (apiStatusMessageElement) {
        apiStatusMessageElement.remove();
        apiStatusMessageElement = null;
    }
}

/**
 * A simple, non-intrusive way to show success/info messages
 * that replaces any existing error.
 */
function showApiStatusUpdate(type, message) {
    hideApiStatus(); // Remove old error before showing success

    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper announce';
    const msgDiv = document.createElement('div');

    // Use different styles based on type
    if (type === 'success') {
        msgDiv.className = 'message announce announce_info';
    } else {
        msgDiv.className = 'message announce announce_info';
        msgDiv.style.borderLeft = '4px solid #FF0000;';
    }

    msgDiv.textContent = message;
    wrapper.appendChild(msgDiv);

    apiStatusMessageElement = wrapper;
    chat.insertBefore(wrapper, typing);
    scrollToBottom();

    // Auto-hide success messages after 5 seconds so they don't clutter chat
    if (type === 'success') {
        setTimeout(hideApiStatus, 5000);
    }
}

function showConnectionStatus(status) {
    hideConnectionStatus();
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
    
    // Update WebSocket-specific indicator if we have separate tracking
    if (status === 'connected' && isWsConnected) {
        statusDot.classList.add('ws-connected');
    } else {
        statusDot.classList.remove('ws-connected');
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

            // Use the new unified updater instead of creating a new chat message
            showApiStatusUpdate('success', 'API reconnected successfully.');
            return true;
        } else {
            const errorMsg = result.error || 'Failed to reconnect';
            const actionMsg = result.action || '';

            // Use the error function which handles the singleton logic
            showApiConfigError(errorMsg, 'connection_failed', actionMsg);
            return false;
        }
    } catch (err) {
        console.error('Failed to reconnect API:', err);
        showApiConfigError('Network error during reconnection attempt.', 'connection_failed');
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
 * This replaces any existing API message instead of adding a new one.
 */
function showApiConfigError(message, errorType = null, action = null, rawError = null) {
    hideApiStatus(); // IMPORTANT: Remove the old error/message first

    const errorWrapper = document.createElement('div');
    errorWrapper.className = 'message-wrapper system';

    let header = 'API Error';
    let guidance = 'Please check your API settings.';
    let buttons = [];

    switch (errorType) {
        case 'config_missing':
            header = 'Setup Required';
            guidance = 'Your API configuration is missing. Please provide a valid API URL and Key.';
            buttons = [{ text: 'Open Settings', action: "toggleModal('settings')", style: 'primary' }];
            break;
        case 'auth_failed':
            header = 'Authentication Failed';
            guidance = 'The API key is invalid. Please verify your API Key in the settings.';
            buttons = [{ text: 'Open Settings', action: "toggleModal('settings')", style: 'primary' }];
            break;
        case 'connection_failed':
            header = 'Connection Failed';
            guidance = 'Unable to reach the API server. Please verify your API URL is correct.';
            buttons = [
                { text: 'Retry Connection', action: 'reconnectApi()', style: 'secondary' },
                { text: 'Open Settings', action: "toggleModal('settings')", style: 'primary' }
            ];
            break;
        default:
            header = 'API Error';
            guidance = 'An unexpected error occurred.';
            buttons = [{ text: 'Retry Connection', action: 'reconnectApi()', style: 'primary' }];
            break;
    }

    // Use the provided message if it's meaningful (not just the generic guidance)
    const displayMessage = message && message !== guidance ? message : guidance;

    let errorHtml = `
    <div class="message system-error" style="
    background: #2a1a1a;
    border: 1px solid #5a3030;
    border-radius: 12px;
    padding: 16px;
    margin: 8px 0;
    box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    ">
    <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
    <span style="font-size: 1.2em;">⚠️</span>
    <strong style="color: #ff8888; font-size: 1.1em;">${escapeHtml(header)}</strong>
    </div>
    <p style="margin: 0 0 12px 0; color: #e0e0e0; font-size: 0.95em; line-height: 1.4; white-space: pre-wrap;">${escapeHtml(displayMessage)}</p>
    ${rawError ? `<details style="margin: 0 0 12px 0; color: #aaa; font-size: 0.85em;"><summary style="cursor: pointer; color: #888; margin-bottom: 4px;">Technical details</summary><pre style="margin: 8px 0 0 0; padding: 8px; background: #1a1a1a; border-radius: 4px; overflow-x: auto; white-space: pre-wrap; word-break: break-all;">${escapeHtml(rawError)}</pre></details>` : ''}
    ${action && !rawError ? `<p style="margin: 0 0 12px 0; color: #aaa; font-size: 0.85em; font-style: italic;">${escapeHtml(action)}</p>` : ''}
    <div style="display: flex; gap: 8px; flex-wrap: wrap;">
    `;

    buttons.forEach(btn => {
        const isPrimary = btn.style === 'primary';
        const btnStyle = `
        background: ${isPrimary ? '#4a6fa5' : 'transparent'};
        color: ${isPrimary ? '#ffffff' : '#aaa'};
        border: ${isPrimary ? 'none' : '1px solid #555'};
        padding: 6px 14px;
        border-radius: 6px;
        cursor: pointer;
        font-size: 0.85em;
        font-weight: 500;
        `;
        errorHtml += `<button onclick="${btn.action}" style="${btnStyle}">${escapeHtml(btn.text)}</button>`;
    });

    errorHtml += `</div></div>`;
    errorWrapper.innerHTML = errorHtml;

    apiStatusMessageElement = errorWrapper; // Store reference to allow removal
    chat.insertBefore(errorWrapper, typing);
    scrollToBottom();
}
