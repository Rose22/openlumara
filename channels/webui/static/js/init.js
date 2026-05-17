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
    if (window.socket) {
        window.socket.close();
        window.socket = null;
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

        // Sound default initialization
        const soundDefaults = {
            send_message: true,
            response_start: true,
            token: false,
            typing: true,
            reasoning_end: true,
            completion: true,
            typewriter: false
        };

        Object.entries(soundDefaults).forEach(([id, enabled]) => {
            const key = `${id}Enabled`;
            if (!localStorage.getItem(key)) {
                localStorage.setItem(key, enabled.toString());
            }
        });

        // WebSocket Connection
        let socket = null;
        let reconnectAttempts = 0;
        const maxReconnectAttempts = 5;

        function connectWebSocket() {
            // Determine protocol (ws:// or wss://)
            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${wsProtocol}//${window.location.host}/ws`;

            socket = new WebSocket(wsUrl);
            window.socket = socket; // Make socket globally accessible for send.js etc.

            socket.onopen = () => {
                console.log('WebSocket connected');
                isConnected = true;
                reconnectAttempts = 0; 
            };

            socket.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    
                    // Handle event-based messages from the backend
                    if (msg.type === 'message_added') {
                        handleNewMessage(msg.message);
                        return;
                    }

                    if (msg.type === 'chat_metadata_updated') {
                        if (typeof updateChatTitleBar === 'function') {
                            updateChatTitleBar(msg.title, msg.tags || []);
                        }
                        loadChats();
                        return;
                    }

                    if (msg.type === 'status_updated') {
                        if (typeof updateConnectionStatus === 'function') {
                            updateConnectionStatus(msg.status);
                        }
                        return;
                    }

                    // Fallback for direct messages or old format
                    handleNewMessage(msg);
                } catch (e) {
                    console.error('Error parsing WebSocket message:', e);
                }
            };

            socket.onclose = (event) => {
                console.log('WebSocket disconnected:', event.reason);
                isConnected = false;
                window.socket = null;

                reconnectAttempts++;
                console.log(`Attempting to reconnect (attempt ${reconnectAttempts})...`);
                setTimeout(connectWebSocket, 1000 * reconnectAttempts);
            };

            socket.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        }

        // State for turn grouping
        let pendingTurn = null;
        let pendingToolCalls = new Map();
        let waitingForToolIds = [];

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

        // Periodic API status check (still uses polling for status as a fallback/heartbeat)
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
