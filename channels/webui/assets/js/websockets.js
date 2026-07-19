let isWsConnected = false;
let wsReconnecting = false;

// intended to be used to queue up messages for sending to the backend in case the
// websocket isn't connected. it's a stub for now
let sendQueue = [];

async function connectWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const token = window.apiToken || '';
    const tokenParam = token ? `?token=${encodeURIComponent(token)}` : '';

    const pathname = `${window.location.pathname || '/'}`;
    const pathBase = pathname.endsWith('/') ? pathname.slice(0, -1) : pathname;
    const wsPath = `${pathBase === '' ? '' : pathBase}/ws`;
    const wsUrl = `${wsProtocol}//${window.location.host}${wsPath}${tokenParam}`;

    try {
        wsSocket = new WebSocket(wsUrl);

        // store a global reference of it
        window.socket = wsSocket;
    } catch (e) {
        await scheduleWsReconnect();
        return;
    }

    wsSocket.onopen = async () => {
        console.log('WebSocket connected');
        isWsConnected = true;
        wsReconnecting = false;
        await getMain().reloadChat();
    };

    wsSocket.onmessage = async (event) => {
        try {
            const data = JSON.parse(event.data);
            await handleWebSocketMessage(data);
        } catch (e) {
            console.error('Error parsing WebSocket message:', e);
        }
    };

    wsSocket.onclose = async (event) => {
        if (!wsReconnecting) {
            console.log('WebSocket disconnected:', event.code, event.reason);
            wsSocket = null;
            window.socket = null;
            isWsConnected = false;
            await scheduleWsReconnect();
        }
    };

    wsSocket.onerror = async (error) => {
        if (!wsReconnecting) {
            console.error('WebSocket error:', error);
        }
    };
}

async function scheduleWsReconnect() {
    console.log(`attempting to reconnect to websocket..`);
    setTimeout(function () {
        connectWebSocket();
    }, 1000);
}

async function handleWebSocketMessage(data) {
    // we store all the stream-related data in an Alpine store
    const stream = Alpine.store("stream");

    data_type = data.type;
    data_content = data.content;

    if (data_type != 'token') {
        console.log(data);
    }

    // process based on broadcast type
    switch (data_type) {
        case "sync_state":
            // use the token buffer from the backend
            // to load into the frontend
            stream.tokens = data.buffer;
            break;

        case "token":
            token = data_content;
            token_type = token.type;
            token_content = token.content;

            // process tokens based on their type
            switch (token_type) {
                case "prompt_progress":
                    if (stream.state != "processing_tools") {
                        // let it stay in that state if it's been set
                        stream.state = 'processing';
                    }

                    stream.processing = token_content;
                    break;
                case "reasoning":
                    stream.state = 'thinking';
                    stream.processing = {};
                    break;
                case "content":
                    stream.state = 'streaming';
                    stream.processing = {};
                    break;
                case "tool_call_delta":
                    stream.state = 'calling_tools';
                    stream.processing = {};
                    break;
                case "tool_calls":
                    stream.state = 'calling_tools';
                    break;
                case "tool":
                    stream.state = 'processing_tools';
                    break;
            }

            stream.tokens.push(token);
            break;

        case "chat_switched":
            // make sure we sync chat switches across instances
            await getMain().loadChat(data.id);
            break;

        case "user_message_confirmed":
            stream.state = 'received';
            break;

        case "stream_complete":
            /*
             * Reconstruct an entire assistant turn from the raw tokens
             * and then push it to the messages array
             */
            lastTurn = streamedTokensToMessages(stream.tokens);
            getMain().messages.push(...lastTurn);
            await stream.clearTokens();

            stream.state = 'idle';
            break;
    }
}
