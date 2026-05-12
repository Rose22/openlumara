// =============================================================================
// Cleanup Function
// =============================================================================

function cleanup() {
    if (pollIntervalId) {
        clearInterval(pollIntervalId);
        pollIntervalId = null;
    }
    if (apiStatusIntervalId) {
        clearInterval(apiStatusIntervalId);
        apiStatusIntervalId = null;
    }
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
    hideConnectionStatus();
}

window.addEventListener('beforeunload', cleanup);

// =============================================================================
// Service Worker Registration
// =============================================================================

if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js')
        .then(reg => console.log('Service Worker registered'))
        .catch(err => console.log('Service Worker registration failed:', err));
    });
}

// =============================================================================
// Initialization
// =============================================================================

// Don't set initial connection status - let it be determined by checkConnection()

async function init() {
    try {
        requestNotificationPermission();

        // The first time the user clicks anywhere,
        // we attempt to request notification permission.
        document.addEventListener('click', () => {
            if (typeof notificationPermission !== 'undefined' && notificationPermission === 'default') {
                requestNotificationPermission();
            }
        }, { once: true });

        await checkConnection();

        // Load current chat from backend if available
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
        // Apply saved font size on load
        const savedFontSize = localStorage.getItem('fontSize');
        if (savedFontSize) {
            document.documentElement.style.setProperty('--font-size-base', `${savedFontSize}px`);
        }

        loadTheme();
        loadChats();
        initTagFilterState();

        window.addEventListener('resize', handleTitleBarResize);

        // WebSocket Connection
        let socket = null;
        let reconnectAttempts = 0;
        const maxReconnectAttempts = 5;

        function connectWebSocket() {
            // Determine protocol (ws:// or wss://)
            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${wsProtocol}//${window.location.host}/ws`;

            socket = new WebSocket(wsUrl);

            socket.onopen = () => {
                console.log('WebSocket connected');
                isConnected = true;
                reconnectAttempts = 0; // Reset attempts on successful connection
            };

            socket.onmessage = (event) => {
                try {
                    // Native WebSockets transmit raw strings, so we parse JSON here.
                    // Socket.IO did this automatically.
                    const msg = JSON.parse(event.data);
                    handleNewMessage(msg);
                } catch (e) {
                    console.error('Error parsing WebSocket message:', e);
                }
            };

            socket.onclose = (event) => {
                console.log('WebSocket disconnected:', event.reason);
                isConnected = false;

                // Manual Reconnection Logic (since we aren't using Socket.IO's auto-reconnect)
                if (reconnectAttempts < maxReconnectAttempts) {
                    reconnectAttempts++;
                    console.log(`Attempting to reconnect (${reconnectAttempts}/${maxReconnectAttempts})...`);
                    setTimeout(connectWebSocket, 1000 * reconnectAttempts);
                }
            };

            socket.onerror = (error) => {
                console.error('WebSocket error:', error);
                // onclose will be called immediately after onerror, handling the UI state
            };
        }

        // State for turn grouping
        let pendingTurn = null;
        let pendingToolCalls = new Map();
        let waitingForToolIds = [];

        function renderAssistantTurnFromBuffer(assistantMsg, toolResponseMap) {
            // Convert Map to array of messages for renderAssistantTurn
            const turnMessages = [assistantMsg];
            const callIds = assistantMsg.tool_calls.map(tc => tc.id);
            for (const id of callIds) {
                if (toolResponseMap.has(id)) {
                    turnMessages.push(toolResponseMap.get(id));
                }
            }
            
            const lastMsg = turnMessages[turnMessages.length - 1];
            renderAssistantTurn(turnMessages, lastMsg.index, true);
        }

        function handleNewMessage(msg) {
            if (!isConnected || userIsEditing) return;
            if (msg.role === 'assistant' && isStreaming) return;
            if (chat.querySelector(`[data-index="${msg.index}"]`)) return;

            renderSingleMessage(msg, msg.index, true);
            if (typeof msg.index === 'number') {
                lastMessageIndex = msg.index + 1;
            }
            scrollToBottom();
            updateTokenUsage();
        }

        // Start WebSocket connection
        connectWebSocket();

        // Periodic API status check (still uses polling for status)
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
