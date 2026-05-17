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
        let socket = null;
        let reconnectAttempts = 0;
        const maxReconnectAttempts = 5;

        function connectWebSocket() {
            const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const pathname = `${window.location.pathname || '/'}`;
            const pathBase = pathname.endsWith('/') ? pathname.slice(0, -1) : pathname;
            const wsPath = `${pathBase === '' ? '' : pathBase}/ws`;
            const wsUrl = `${wsProtocol}//${window.location.host}${wsPath}`;

            socket = new WebSocket(wsUrl);
            window.socket = socket;

            socket.onopen = () => {
                console.log('WebSocket connected');
                isConnected = true;
                reconnectAttempts = 0;
            };

            socket.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data);
                    if (msg.type === 'message_added') {
                        handleNewMessage(msg.message);
                        return;
                    }
                    if (msg.type === 'chat_metadata_updated') {
                        if (typeof updateChatTitleBar === 'function') updateChatTitleBar(msg.title, msg.tags || []);
                        loadChats();
                        return;
                    }
                    if (msg.type === 'status_updated') {
                        if (typeof updateConnectionStatus === 'function') updateConnectionStatus(msg.status);
                        return;
                    }
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

        connectWebSocket();

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
