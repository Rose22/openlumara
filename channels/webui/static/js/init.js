// =============================================================================
// WebSocket Connection Management (Module Level)
// =============================================================================

let wsSocket = null;
let wsReconnectAttempts = 0;
const maxWsReconnectAttempts = 50;

function connectWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const token = window.apiToken || '';
    const tokenParam = token ? `?token=${encodeURIComponent(token)}` : '';

    const pathname = `${window.location.pathname || '/'}`;
    const pathBase = pathname.endsWith('/') ? pathname.slice(0, -1) : pathname;
    const wsPath = `${pathBase === '' ? '' : pathBase}/ws`;
    const wsUrl = `${wsProtocol}//${window.location.host}${wsPath}${tokenParam}`;

    try {
        wsSocket = new WebSocket(wsUrl);
        window.socket = wsSocket;  // Keep global reference for send.js
    } catch (e) {
        console.error('Failed to create WebSocket:', e);
        scheduleWsReconnect();
        return;
    }

    wsSocket.onopen = () => {
        console.log('WebSocket connected');
        wsReconnectAttempts = 0;
        isWsConnected = true;
        updateConnectionStatus('connected');
    };

    wsSocket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleWebSocketMessage(data);
        } catch (e) {
            console.error('Error parsing WebSocket message:', e);
        }
    };

    wsSocket.onclose = (event) => {
        console.log('WebSocket disconnected:', event.code, event.reason);
        wsSocket = null;
        window.socket = null;
        isWsConnected = false;
        updateConnectionStatus('disconnected');
        scheduleWsReconnect();
    };

    wsSocket.onerror = (error) => {
        console.error('WebSocket error:', error);
        // Don't close here - onclose will fire after onerror
    };
}

function scheduleWsReconnect() {
    if (wsReconnectAttempts >= maxWsReconnectAttempts) {
        console.error('Max WebSocket reconnection attempts reached');
        return;
    }
    wsReconnectAttempts++;
    const delay = Math.min(1000 * Math.pow(1.5, wsReconnectAttempts - 1), 30000);
    console.log(`WS reconnect attempt ${wsReconnectAttempts} in ${Math.round(delay)}ms`);
    setTimeout(connectWebSocket, delay);
}

function handleWebSocketMessage(data) {
    // Handle typed messages from backend
    if (data.type === 'message_added') {
        handleNewMessage(data.message);
        return;
    }
    if (data.type === 'chat_metadata_updated') {
        if (typeof updateChatTitleBar === 'function') {
            updateChatTitleBar(data.title, data.tags || []);
        }
        loadChats();
        return;
    }
    if (data.type === 'status_updated') {
        if (typeof updateConnectionStatus === 'function') {
            updateConnectionStatus(data.status);
        }
        return;
    }
    // Legacy: handle raw message objects (for backwards compatibility)
    // Add an index if missing to ensure proper handling
    if (data.role && data.content !== undefined) {
        if (data.index === undefined) {
            // Try to determine index from current state
            data.index = lastMessageIndex;
        }
        handleNewMessage(data);
    }
}

function handleNewMessage(msg) {
    // Skip if we're currently streaming - messages will be synced after streaming completes
    if (typeof isStreaming !== 'undefined' && isStreaming) {
        return;
    }
    
    // Only process if we have a valid WebSocket connection
    if (!isWsConnected) return;
    if (!msg || msg.index === undefined) return;
    
    // Validate index is sequential (not older than what we already have)
    if (msg.index < lastMessageIndex) {
        console.log('Skipping old message, index:', msg.index, 'current:', lastMessageIndex);
        return;
    }
    
    // Skip if message already exists (check both exact index and streaming placeholder)
    const existingWrapper = chat.querySelector(`[data-index="${msg.index}"]`);
    if (existingWrapper) {
        console.log('Message already exists at index:', msg.index);
        return;
    }

    renderSingleMessage(msg, msg.index, true);
    // Update lastMessageIndex to be one past the last rendered message
    lastMessageIndex = msg.index + 1;
    scrollToBottom();
    updateTokenUsage();
}

// =============================================================================
// Initialization
// =============================================================================

async function init() {
    try {
        requestNotificationPermission();
        document.addEventListener('click', () => {
            if (typeof notificationPermission !== 'undefined' && notificationPermission === 'default') {
                requestNotificationPermission();
            }
        }, { once: true });

        await checkConnection();
        if (isConnected) {
            await restoreCurrentChat();
        }
    } catch (err) {
        console.error('Failed to initialize connection:', err);
        isConnected = false;
        updateConnectionStatus('disconnected');
        scheduleReconnect();
    }

    try {
        const savedFontSize = localStorage.getItem('fontSize');
        if (savedFontSize) {
            document.documentElement.style.setProperty('--font-size-base', `${savedFontSize}px`);
        }

        loadTheme();
        loadChats();
        initTagFilterState();

        window.addEventListener('resize', handleTitleBarResize);

        // ─────────────────────────────────────────────────────────────
        // Safe Sound Default Initialization
        // ─────────────────────────────────────────────────────────────
        Object.entries(SOUND_DEFAULTS).forEach(([id, enabled]) => {
            const key = `${id}Enabled`;
            try {
                if (typeof localStorage !== 'undefined') {
                    const current = localStorage.getItem(key);
                    if (current === null) {
                        localStorage.setItem(key, String(enabled));
                    }
                }
            } catch (e) {
                console.warn('[Init] Storage unavailable, using runtime defaults');
            }
        });

        // ─────────────────────────────────────────────────────────────
        // WebSocket Connection
        // ─────────────────────────────────────────────────────────────
        connectWebSocket();

        // API status polling (this is still needed for API health)
        apiStatusIntervalId = setInterval(() => {
            if (isConnected) {
                checkApiStatus();
            }
        }, CONFIG.API_STATUS_INTERVAL);
    } catch (err) {
        console.error('Failed to initialize UI and polling:', err);
    }
}

init();
