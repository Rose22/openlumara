let isWsConnected = false;
let wsReconnecting = false;

// Send queue: messages waiting to be sent while disconnected
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
     const store = Alpine.store("stream");
 
     data_type = data.type;
     data_content = data.content;
 
     // process based on broadcast type
     switch (data_type) {
         case "token":
             token = data_content;
             token_type = token.type;
             token_content = token.content;
 
             // process tokens based on their type
             switch (token_type) {
                 case "prompt_progress":
                     if (store.state != "processing_tools") {
                         // let it stay in that state if it's been set
                         store.state = 'processing';
                     }

                     store.processing = token_content;
                     break;
                 case "reasoning":
                     store.state = 'thinking';
                     break;
                 case "content":
                     store.state = 'streaming';
                     break;
                 case "tool_call_delta":
                     store.state = 'calling_tools';
                     break;
                 case "tool_calls":
                     store.state = 'calling_tools';
                     break;
                 case "tool":
                     store.state = 'processing_tools';
                     break;
             }

             console.log(token);
             store.tokens.push(token);
             break;
         case "stream_complete":
             store.state = 'idle';
             await store.clearTokens();
             break;
     }
 }
