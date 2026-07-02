// =============================================================================
// Error Handlers
// =============================================================================
let chatErrorElement = null;

/**
 * Centralized dictionary to map technical errors to human-friendly
 * messages and actionable advice.
 */
const ERROR_MAP = {
    // API/Connection Errors
    'stream_failed': {
        title: 'Stream Interrupted',
        message: 'The response was cut off unexpectedly.',
        action: 'Try clicking "Regenerate" to restart.',
        icon: 'server'
    },
    'server_error': {
        title: 'Server Hiccup',
        message: 'The server encountered an internal error.',
        action: 'This is usually temporary. Please try again in a few seconds.',
        icon: 'server'
    },
    'network_error': {
        title: 'Network Error',
        message: 'Unable to reach the server.',
        action: 'Check your internet connection and try again.',
        icon: 'globe'
    },
    'websocket_not_open': {
        title: 'WebSocket Unavailable',
        message: 'The connection is not ready yet. Your message is queued.',
        action: 'It will be sent automatically when reconnected.',
        icon: 'server'
    },
    'default': {
        title: 'Something went wrong',
        message: 'An unexpected error occurred.',
        action: 'Please try again.',
        icon: 'error'
    }
};

// Helper to get icon SVG based on type
function getErrorIcon(type) {
    const icons = {
        'lock': '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
        'clock': '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
        'alert_circle': '<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>',
        'globe': '<circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>',
        'server': '<rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/>'
    };
    return icons[type] || icons['alert_circle'];
}


/**
 * Extracts a user-friendly message from a raw error string.
 * Parses JSON error responses to extract the 'message' field if present.
 */
function extractErrorMessage(rawError) {
    if (!rawError) return null;
    
    // Try to parse as JSON to extract the message field
    try {
        // Handle "Error code: 402 - {...}" format
        const jsonMatch = rawError.match(/Error code: \d+ - (\{[\s\S]*\})/);
        const jsonStr = jsonMatch ? jsonMatch[1] : rawError;
        
        const parsed = JSON.parse(jsonStr);
        
        // Navigate common error structures
        if (parsed.error?.message) return parsed.error.message;
        if (parsed.message) return parsed.message;
        if (parsed.error?.error?.message) return parsed.error.error.message;
        if (typeof parsed.error === 'string') return parsed.error;
    } catch (e) {
        // Not JSON, check for common patterns
    }
    
    // Try to extract message from string format like "{'error': {'message': '...'}}"
    const messageMatch = rawError.match(/'message':\s*'([^']+)'/);
    if (messageMatch) return messageMatch[1];
    
    const messageMatch2 = rawError.match(/"message":\s*"([^"]+)"/);
    if (messageMatch2) return messageMatch2[1];
    
    return null;
}

/**
 * Handles HTTP error responses (4xx, 5xx)
 */
async function handleServerError(response, aiWrapper) {
    let errorType = 'server_error';
    let customMessage = '';
    let rawError = '';

    try {
        const errorData = await response.json();
        // Use the error_type provided by backend, or fallback to the error message
        errorType = errorData.error_type || errorData.error || 'server_error';
        customMessage = errorData.message || '';
        rawError = errorData.raw_error || '';
    } catch (e) {
        // Fallback if JSON parsing fails
        if (response.status === 401 || response.status === 403) errorType = 'auth_failed';
        else if (response.status === 429) errorType = 'rate_limit';
        else if (response.status >= 500) errorType = 'server_error';
    }

    const info = ERROR_MAP[errorType] || ERROR_MAP['default'];

    // Try to extract a meaningful message from raw error
    const extractedMessage = extractErrorMessage(rawError);
    
    // Use extracted message, then custom message, then generic message
    const displayMsg = extractedMessage || customMessage || info.message;

    // Pass both the display message and raw error
    showChatError(displayMsg, errorType, info.action, rawError);
    removePlaceholder();

    if (aiWrapper && aiWrapper.parentNode) {
        aiWrapper.remove();
    }

    finishStream();
}

/**
 * Handles errors that occur mid-stream (sent via data: {"type": "error", ...})
 */
function handleInlineError(data, aiMsgDiv, aiWrapper, streamStarted) {
    if (!streamStarted) aiWrapper.classList.remove('hidden');

    const errorDetails = data.error_data || {};
    const type = errorDetails.error || 'api_error';
    const info = ERROR_MAP[type] || ERROR_MAP['default'];

    // Try to extract a meaningful message from raw error
    const rawError = errorDetails.raw_error || '';
    const extractedMessage = extractErrorMessage(rawError);
    
    // Use extracted message, then backend message, then generic message
    const userMessage = extractedMessage || errorDetails.message || info.message;

    // Build the error display - show message prominently, raw error in details
    let errorContent = escapeHtml(userMessage);
    if (rawError) {
        errorContent += `<details class="api-error-details"><summary>Technical details</summary><pre>${escapeHtml(rawError)}</pre></details>`;
    }

    aiMsgDiv.innerHTML = `
    <div class="api-error-inline">
    <div class="api-error-header">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    ${getErrorIcon(type)}
    </svg>
    <span class="api-error-title">${escapeHtml(info.title)}</span>
    </div>
    <div class="api-error-message">${errorContent}</div>
    <div class="api-error-footer">
    <div class="api-error-action">${escapeHtml(info.action)}</div>
    </div>
    </div>`;
}

/**
 * Handles hard network failures (DNS, CORS, Offline)
 */
function handleCatchError(err, aiMsgDiv, aiWrapper, streamStarted) {
    if (!streamStarted) aiWrapper.classList.remove('hidden');

    let type = 'network_error';
    // Detect if it's a specific browser error
    if (err.name === 'AbortError') return;

    const info = ERROR_MAP[type];

    aiMsgDiv.innerHTML = `
    <div class="api-error-inline">
    <div class="api-error-header">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    ${getErrorIcon(type)}
    </svg>
    <span class="api-error-title">${escapeHtml(info.title)}</span>
    </div>
    <div class="api-error-message">${escapeHtml(err.message)}</div>
    <div class="api-error-footer">
    <div class="api-error-action">${escapeHtml(info.action)}</div>
    </div>
    </div>`;
}

function hideChatError() {
    if (chatErrorElement) {
        chatErrorElement.remove();
        chatErrorElement = null;
    }
}

function showChatError(message, errorType = null, action = null, rawError = null) {
    hideChatError(); // IMPORTANT: Remove the old error/message first

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
    <span style="font-size: 1.2em;">⚠</span>
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

    chatErrorElement = errorWrapper; // Store reference to allow removal
    chat.insertBefore(errorWrapper, typing);
    scrollToBottom();
}

