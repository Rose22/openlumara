let isWsConnected = false;
let wsReconnecting = false;
let responseSoundPlayed = false;

let serverShutdownSeen = false;
let wsClosedAt = null;

let wsHeartbeatTimer = null;
window.wsLastRx = Date.now();

// intended to be used to queue up messages for sending to the backend in case the
// websocket isn't connected. it's a stub for now
let sendQueue = [];

let streamFinalizing = false;

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

        // the server came back after having gone away: reload the page
        const downFor = wsClosedAt ? Date.now() - wsClosedAt : 0;
        wsClosedAt = null;
        if (serverShutdownSeen || Alpine.store('system').restarting || downFor > 2500) {
            window.location.reload();
            return;
        }

        // start the app-level heartbeat (server answers {type:"pong"}
        clearInterval(wsHeartbeatTimer);
        wsHeartbeatTimer = setInterval(() => {
            if (wsSocket && wsSocket.readyState === WebSocket.OPEN) {
                try { wsSocket.send(JSON.stringify({ type: "ping" })); } catch (e) {}
            }
        }, 25000);

        await Alpine.store("chat").reloadChat();
    };

    wsSocket.onmessage = async (event) => {
        let data = null;
        window.wsLastRx = Date.now();
        try {
            data = JSON.parse(event.data);
            await handleWebSocketMessage(data);
        } catch (e) {
            console.error('Error parsing WebSocket message:', e);
        } finally {
            if (data && data.type === 'stream_complete') {
                streamFinalizing = false;
            }
        }
    };

    wsSocket.onclose = async (event) => {
        if (!wsReconnecting) {
            clearInterval(wsHeartbeatTimer);
            const silence = Math.round((Date.now() - window.wsLastRx) / 1000);
            console.log('WebSocket disconnected:', event.code, event.reason, `(silent for ${silence}s before the drop)`);
            wsSocket = null;
            window.socket = null;
            isWsConnected = false;
            wsClosedAt = Date.now();

            let notice = "Not connected to the backend server! Is OpenLumara running?";
            if (event.code === 4001) {
                notice = "Login session no longer accepted (expired, or the session secret changed). Log out and back in.";
            } else if (event.code === 4003) {
                notice = "WebSocket blocked: origin mismatch. The address in the URL bar does not match the webui's host/port settings.";
            } else if (event.code === 1012 || event.code === 1011 || event.code === 1006) {
                notice = "Connection to the backend dropped. Reconnecting..";
            }
            notice += " [" + event.code + (event.reason ? ' - ' + event.reason : '') + "]";
            Alpine.store('ui').notice = notice;
            stream = Alpine.store("stream")
            stream.state = 'idle';

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
    const ui = Alpine.store('ui');

    data_type = data.type;
    data_content = data.content;

    // if (data_type != 'token' && data_type != "turn_stream") {
    //     console.log(data);
    // }

    // process based on broadcast type
    switch (data_type) {
        case "stream_state":
            stream.state = data.state;
            break;

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
            // keep a reference to the user message so stream_complete can push
            // it to the turn history without it being null
            stream.userMsg = data.message;

            // reload chat from backend so that the new user message shows up
            await chat.reloadChat();

            // force scroll to bottom
            await ui.forceScrollToBottom();
            break;

        case "user_message_confirmed":
            break;

        case "turn_step":
        case "turn_final": {
            // step-based stream
            if (stream.turn.length <= 0) {
                while (chat.turnHistory.length > 0 &&
                       chat.turnHistory[chat.turnHistory.length - 1].role === 'assistant' &&
                       chat.turnHistory[chat.turnHistory.length - 1].live !== true) {
                    chat.turnHistory.pop();
                }

                stream.turn = {role: "assistant", live: true, steps: [], final_messages: []};
                chat.turnHistory.push(stream.turn);
                Alpine.store('ui').syncMountWindows();
            }

            if (data_type === "turn_step") {
                const step = data.step;
                const steps = stream.turn.steps;
                const stepIdx = steps.findIndex(s => s.step === step.step);

                let grew = false;
                if (stepIdx >= 0) {
                    const prev = steps[stepIdx];
                    grew = (step.reasoning_content || '').length !== (prev.reasoning_content || '').length
                        || (step.content || '').length !== (prev.content || '').length;
                    Object.assign(prev, step);
                } else {
                    steps.push(step);
                    steps.sort((a, b) => a.step - b.step);
                    grew = true;
                }

                if (grew) {
                    stream.processing = {};
                    stream.modelLoad = null;
                    AudioManager.stopProcessingSound();
                    AudioManager.play("token");
                    if (!responseSoundPlayed) {
                        AudioManager.play("response_start");
                        responseSoundPlayed = true;
                    }
                }

                if (step.is_cmd) {
                    await chat.reloadChats();
                    await chat.reloadCategories();
                }
            } else {
                // authoritative final snapshot: replace wholesale, the
                // empty list is a retract (content slid back into the chain)
                stream.turn.final_messages = data.messages || [];

                if (stream.turn.final_messages.length > 0) {
                    stream.processing = {};
                    stream.modelLoad = null;
                    AudioManager.stopProcessingSound();
                    AudioManager.play("token");
                    if (!responseSoundPlayed) {
                        AudioManager.play("response_start");
                        responseSoundPlayed = true;
                    }
                }

                if (stream.turn.final_messages.some(m => m.is_cmd)) {
                    await chat.reloadChats();
                    await chat.reloadCategories();
                }
            }

            // scroll
            await ui.scrollToBottom();
            break;
        }

        case "queue_queued":
            stream.queued = data.messages ?? [];
            break;

        case "queue_flushed":
            (data.messages ?? []).forEach(msg => {
                const idx = stream.queued.findIndex(q => q.content === msg.content);
                if (idx !== -1) { stream.queued.splice(idx, 1); }
            });
            AudioManager.play("token");

            if (data.end_of_chain) {
                const hist = chat.turnHistory;
                if (hist.length > 0 && hist[hist.length - 1]?.live === true) {
                    // its content comes back from the reloaded history
                    hist.pop();
                }

                stream.turn = { role: "assistant", live: true, steps: [], final_messages: [] };
                await chat.reloadChat();
                chat.turnHistory.push(stream.turn);
                stream.userMsg = null;
                await ui.forceScrollToBottom();
            }
            // no scroll needed for mid-chain pops: the queue is pinned
            // above the input bar
            break;

        case "push":
            // it's a push messsage (like a scheduler reminder)
            if (stream.state !== 'idle' || streamFinalizing) {
                await AudioManager.play('response_start');
                await Alpine.store('notifications').send(data.content.content);
                break;
            }

            await chat.reloadChat();

            await AudioManager.play('response_start');
            await Alpine.store('notifications').send(data.content.content);

            await ui.forceScrollToBottom();
            break;

        case "log":
            // cap the log buffer so a chatty backend can't grow it forever
            const logs = Alpine.store('system').logs;
            logs.push(data);
            if (logs.length > 1000) logs.splice(0, 500);
            break;

        case "ready":
            sys = Alpine.store("system")
            sys.running = true;
            sys.restarting = false;

            // reload the system data from the backend
            await sys.loadData();
            break;

        case "shutdown":
            sys = Alpine.store("system")
            serverShutdownSeen = true;
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
                    stream.modelLoad = null;
                    // restore the user's last input
                    if (!chat.user_input && chat.last_user_input) {
                        chat.user_input = chat.last_user_input;
                    }
                    await chat.reloadChat();
                    break;
                case "tool":
                    AudioManager.playProcessingSound();
                    break;
                case "prompt_progress":
                    // prompt eval started, so any model-load progress is done
                    stream.modelLoad = null;

                    stream.processing = token_content;

                    AudioManager.playProcessingSound();
                    break;
                case "model_load_progress":
                    stream.modelLoad = token_content;

                    AudioManager.playProcessingSound();
                    break;
                case "token_usage":
                    chat.currentTokenUsage = token_content;
                    break;
                case "tool_call_delta":
                    stream.processing = {};
                    stream.modelLoad = null;
                    break;
                case "tool_calls":
                    break;
            }

            // always scroll to the bottom upon a token coming in
            await ui.scrollToBottom();

            break;

        case "token_usage":
            chat.currentTokenUsage = data.content;
            break;
        case "context_size":
            chat.contextBreakdown = data.content;
            break;

        case "sync":
            // make sure we sync chat
            chat.turnHistory = [];
            await stream.clear();
            await chat.reloadChat();

            if (ui.scrollToTurnIndex) {
                await ui.scrollToTurn(ui.scrollToTurnIndex);
            } else {
                await ui.forceScrollToBottom();
            }

            break;

        case "refresh_page":
            // -- AI GENERATED CODE (Qwen3-Coder Next) :: (11-06-2026) harness:openlumara
            // webui settings changed on the server: reload so they apply
            window.location.reload();
            break;

        case "chat_switched":
            // make sure we sync chat switches across instances
            await chat.loadChat(data.id);
            break;

        case "stream_complete":
            /*
             * this prevents UI flicker that comes from re-rendering the entire turn history
             */

            streamFinalizing = true;

            const foldEl = document.querySelector('.agent-chain.is-streaming .agent-chain-body');
            if (foldEl && !window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
                const foldMsgs = document.getElementById('messages');
                foldEl.style.overflow = 'hidden';
                const fold = foldEl.animate(
                    [{ height: foldEl.offsetHeight + 'px' }, { height: '0px' }],
                    { duration: 250, easing: 'ease-in-out', fill: 'forwards' }
                );
                let foldCancelled = false;
                const cancelFoldPin = () => { foldCancelled = true; };
                foldMsgs.addEventListener('wheel', cancelFoldPin, { passive: true });
                foldMsgs.addEventListener('touchstart', cancelFoldPin, { passive: true });
                const pinBottom = () => {
                    if (foldCancelled || !ui.shouldScroll) return;
                    foldMsgs.scrollTo({ top: foldMsgs.scrollHeight - foldMsgs.clientHeight, behavior: 'instant' });
                    if (fold.playState === 'running') requestAnimationFrame(pinBottom);
                };
                requestAnimationFrame(pinBottom);
                try { await fold.finished; } catch (err) { /* cancelled or gone: fine */ }
                foldMsgs.removeEventListener('wheel', cancelFoldPin);
                foldMsgs.removeEventListener('touchstart', cancelFoldPin);
            }

            const hist = chat.turnHistory;
            const hasLiveTail = hist.length > 0 && hist[hist.length - 1] && hist[hist.length - 1].live === true;
            const lastTurn = hist[hist.length - 1 - (hasLiveTail ? 1 : 0)];
            const userAlreadyShown = lastTurn && lastTurn.role === 'user' &&
                stream.userMsg && lastTurn.messages?.[0]?.index === stream.userMsg.index;

            if (!userAlreadyShown && stream.userMsg) {
                const userTurn = {"role": "user", "messages": [stream.userMsg]};
                if (hasLiveTail) hist.splice(hist.length - 1, 0, userTurn);
                else hist.push(userTurn);
            }

            (stream.turn.steps ?? []).forEach(s => {
                s.reasoning_live = false;
                s.is_tail = false;
                if (s.status === 'thinking' && (!s.tool_calls || s.tool_calls.length === 0)) {
                    s.status = 'thoughts';
                }
                if (s.label === 'Thinking..') {
                    s.label = 'Thoughts';
                }
            });

            if (hist.length > 0 && hist[hist.length - 1] && hist[hist.length - 1].live === true) {
                stream.turn.live = false;
            } else {
                chat.turnHistory.push(stream.turn);
            }

            Alpine.store('ui').syncMountWindows();

            // then clear the user message placeholder and the current turn
            await stream.clear();

            // finalize the stream
            responseSoundPlayed = false;
            AudioManager.play("completion");
            await ui.scrollToBottom('messages');

            // and finally, sync back up with the backend
            await chat.reloadChat();
            await chat.reloadChats();

            await ui.scrollToBottom('messages');

            break;
    }
}
