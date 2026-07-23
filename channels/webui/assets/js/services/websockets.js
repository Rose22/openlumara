let isWsConnected = false;
let wsReconnecting = false;
let responseSoundPlayed = false;

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
        Alpine.store('ui').notice = null;
        isWsConnected = true;
        wsReconnecting = false;
        await Alpine.store("chat").reloadChat();
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

            Alpine.store('ui').notice = "Not connected to the backend server! Is OpenLumara running?"
            stream = Alpine.store("stream")
            stream.state = 'idle';
            stream.pendingMessageId = null;

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

    const chat = Alpine.store("chat");

    data_type = data.type;
    data_content = data.content;

    if (data_type != 'token') {
        console.log(data);
    }

    // process based on broadcast type
    switch (data_type) {
        case "sync_state":
            /*
             * use the token buffer from the backend
             * to load into the frontend
             *
             * fun lil comment about this... this used to take me ages to get right in the old webUI
             * i had to basically simulate a replay of the entire token stream
             * here it's just a simple assignment!
             * thanks alpine.js
             */
        
            stream.tokens = data.buffer;
            break;
        case "user_message_added":
            // show the message, with a special "pending" status
            let msgId = Date.now();
            console.log(data.message);
            chat.messages.push({
                ...data.message,
                role: 'user',
                msgId: msgId
            });
            stream.pendingMessageId = msgId;

            // force scroll to bottom
            await Alpine.store('ui').forceScrollToBottom();
            break;
        case "user_message_confirmed":
            // aaand now we remove the pending status
            stream.pendingMessageId = null;

            // and track the index of it so we can know the index of the next assistant message
            stream.userMessageId = data.index;
            stream.state = 'received';
            break;

        case "push":
            // it's a push messsage (like a scheduler reminder)
            chat.messages.push(data.content);
            console.log(data.content);
            await AudioManager.play('response_start');
            await Alpine.store('notifications').send(data.content.content);
            break;

        case "log":
            Alpine.store('system').logs.push(data);
            break;

        case "ready":
            sys = Alpine.store("system")
            sys.running = true;
            sys.restarting = false;
            break;

        case "shutdown":
            sys = Alpine.store("system")
            if (!sys.restarting) {
                sys.message = "Server is down! Trying to reconnect..";
                sys.running = false;
            }
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

                    AudioManager.playProcessingSound();
                    break;
                case "reasoning":
                    stream.state = 'thinking';
                    stream.processing = {};

                    AudioManager.stopProcessingSound();
                    AudioManager.play("token");

                    if (!responseSoundPlayed) {
                        AudioManager.play("response_start");
                        responseSoundPlayed = true;
                    }
                    break;
                case "content":
                    stream.state = 'streaming';
                    stream.processing = {};

                    AudioManager.stopProcessingSound();
                    AudioManager.play("token");

                    if (!responseSoundPlayed) {
                        AudioManager.play("response_start");
                        responseSoundPlayed = true;
                    }
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
                    AudioManager.playProcessingSound();
                    break;
            }

            if (token.is_cmd) {
                // reload the global state in case something changed due to the command
                await chat.reloadChat();
                return
            }

            stream.tokens.push(token);

            // always scroll to the bottom upon a token coming in
            await Alpine.store('ui').scrollToBottom();

            // Notify that turns may need updating
            Alpine.store('chat').onTokenArrived();

            break;

        case "messages_updated":
            // make sure we sync chat
            await chat.reloadChat();

            // Notify that messages changed
            Alpine.store('chat').onMessagesChanged();
            break;

        case "chat_switched":
            // make sure we sync chat switches across instances
            await chat.loadChat(data.id);
            break;

        case "stream_complete":
            /*
             * Reconstruct an entire assistant turn from the raw tokens
             * and then push it to the messages array
             *
             * (so that the UI won't flicker when syncing from the backend)
             */

            lastTurn = streamedTokensToMessages(stream.tokens);
            chat.messages.push(...lastTurn);
            await stream.clearTokens();

            // then sync from the backend to make sure we're completely synced up
            await chat.reloadChat();

            AudioManager.play("completion");

            stream.state = 'idle';
            break;
    }
}
