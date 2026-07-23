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
        
            // actually nope its not even needed anymore because we just stream an entire turn from the backend LOL
            // this is now just here for a memory, this data type doesn't actually get broadcast anymore
            break;

        case "user_message_added":
            // show the message, with a special "pending" status
            stream.userMsg = data.message;
            stream.userMsgPending = true;

            // force scroll to bottom
            await Alpine.store('ui').forceScrollToBottom();
            break;

        case "user_message_confirmed":
            // aaand now we remove the pending status
            stream.userMsgPending = false;
            stream.state = 'received';
            break;

        case "turn_stream":
            stream.turn = data.turns;

            // always scroll to the bottom upon a token coming in
            await Alpine.store('ui').scrollToBottom();

            // process depending on what segment we're in
            const current_segment = stream.turn.messages[stream.turn.messages.length-1]
            const segment_type = current_segment.type;
            switch (segment_type) {
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
            }

            if (current_segment.is_cmd) {
                // reload the global state in case something changed due to the command
                await chat.reloadChat();
            }

            break;

        case "push":
            // it's a push messsage (like a scheduler reminder)
            chat.turnHistory.push(data.content);
            await chat.reloadChat();

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
                case "error":
                    // force a refresh
                    await chat.reloadChat();
                    break;
                case "prompt_progress":
                    if (stream.state != "processing_tools") {
                        // let it stay in that state if it's been set
                        stream.state = 'processing';
                    }

                    stream.processing = token_content;

                    AudioManager.playProcessingSound();
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

            // always scroll to the bottom upon a token coming in
            await Alpine.store('ui').scrollToBottom();

            break;

        case "messages_updated":
            // make sure we sync chat
            await chat.reloadChat();
            break;

        case "chat_switched":
            // make sure we sync chat switches across instances
            await chat.loadChat(data.id);
            break;

        case "stream_complete":
            /*
             * this prevents UI flicker that comes from re-rendering the entire turn history
             */

            // push the user message + the fully collected assistant turn to the history
            chat.turnHistory.push({"role": "user", "messages": [stream.userMsg]});
            chat.turnHistory.push(stream.turn);
            
            // then clear the user message placeholder and the current turn
            stream.userMsg = null;
            stream.turn = [];

            // finalize the stream
            AudioManager.play("completion");
            await Alpine.store('ui').scrollToBottom();
            stream.state = 'idle';

            // and finally, sync back up with the backend
            await chat.reloadChat();

            break;
    }
}
