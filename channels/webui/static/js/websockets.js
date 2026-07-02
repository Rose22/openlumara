let wsSocket = null;
let fancyProcessingIndicatorCreated = false;
let responseStartSoundPlayed = false;
let reasoningDoneSoundPlayed = false;
let catchingUpFromBuffer = false;
const BUFFER_BATCH_SIZE = 50; // Tokens per batch

let sending_status = null;
let wsReconnecting = false;
let statusMessageElement = null; // For Server connection

// Send queue: messages waiting to be sent while disconnected
let sendQueue = [];

/**
 * Send a message immediately if the socket is open, otherwise queue it.
 */
function safeSocketSend(data) {
    if (window.socket && window.socket.readyState === WebSocket.OPEN) {
        window.socket.send(JSON.stringify(data));
    } else {
        sendQueue.push(data);
    }
}

/**
 * Drain the send queue by transmitting all queued messages over the WebSocket.
 */
function drainSendQueue() {
    if (!window.socket || window.socket.readyState !== WebSocket.OPEN) {
        return;
    }
    const messages = [...sendQueue];
    sendQueue = [];
    for (const msg of messages) {
        try {
            window.socket.send(JSON.stringify(msg));
        } catch (e) {
            // If sending fails, put it back in the queue
            sendQueue.unshift(msg);
            break;
        }
    }
}

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
        scheduleWsReconnect();
        return;
    }

    wsSocket.onopen = () => {
        console.log('WebSocket connected');
        isWsConnected = true;
        wsReconnecting = false;
        showConnectionStatus('reconnected');

        // sync back up with the backend
        try {
            wsSocket.send(JSON.stringify({
                type: 'reload_messages'
            }));
        } catch (e) {
            console.warn('Failed to send message reload request:', e);
        }

        // Drain any queued messages
        drainSendQueue();
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
        if (!wsReconnecting) {
            console.log('WebSocket disconnected:', event.code, event.reason);
            wsSocket = null;
            window.socket = null;
            isWsConnected = false;
            showConnectionStatus('reconnecting');
            scheduleWsReconnect();
        }
    };

    wsSocket.onerror = (error) => {
        if (!wsReconnecting) {
            console.error('WebSocket error:', error);
        }
        scheduleWsReconnect();
    };
}

function scheduleWsReconnect() {
    console.log(`attempting to reconnect to websocket..`);
    wsReconnecting = true;
    setTimeout(function () {
        connectWebSocket();
    }, 1000);
}

function handlePromptProgress(prog) {
    let progressData = prog;
    try {
        if (typeof prog === 'string') {
            progressData = JSON.parse(prog);
        }
    } catch (e) {
        return;
    }

    const cache = progressData.cache || 0;
    const processed = progressData.processed - cache;
    const total = progressData.total - cache;
    const percent = total > 0 ? Math.round((processed / total) * 100) : 0;
    const elapsed = progressData.time_ms / 1000;
    const remaining = (total - processed) > 0 ? (elapsed / processed) * (total - processed) : 0;

    // 1. create indicator
    if (!fancyProcessingIndicatorCreated) {
        // hide typing indicator
        setInputState(true, false, true);

        fancyProcessingIndicator = document.createElement('div');
        fancyProcessingIndicator.className = 'prompt-processing-indicator-wrapper tool-processing-content';

        chat.appendChild(fancyProcessingIndicator);

        fancyProcessingIndicator.innerHTML = `
        <div class="prompt-processing-indicator">
        <div class="progress-header">
        <span class="prompt-processing-percent">0%</span>
        <span class="prompt-processing-eta" style="opacity: 0.7">(ETA: 0s)</span>
        </div>
        <div class="prompt-progress-bar">
        <div class="prompt-progress-bar-fill" style="width: 0%"></div>
        </div>
        </div>
        `;

        progressBarFill = fancyProcessingIndicator.querySelector('.prompt-progress-bar-fill');
        progressTextPercent = fancyProcessingIndicator.querySelector('.prompt-processing-percent');
        progressTextETA = fancyProcessingIndicator.querySelector('.prompt-processing-eta');

        TypewriterAudioManager.playProcessingSound();
        scrollToBottom();

        fancyProcessingIndicatorCreated = true;
    }

    if (typeof toolProcessingIndicatorElement !== 'undefined' && toolProcessingIndicatorElement && toolProcessingIndicatorElement.updateProgress) {
        toolProcessingIndicatorElement.updateProgress(percent);
    }

    if (typeof progressBarFill !== 'undefined') {
        progressBarFill.style.width = `${percent}%`;
    }
    if (progressTextPercent && progressTextETA) {
        progressTextPercent.textContent = `${percent}%`;
        progressTextETA.textContent = `(ETA: ${Math.ceil(remaining)}s)`;
    }
}

/**
 * Unified token processor for both live streaming and initial buffer catch-up.
 * @param {Object} msg - The message object containing type and content (or tool_calls).
 * @param {boolean} isSimulated - If true, suppresses playback sounds (used for initial catch-up).
 */
function processToken(msg, isSimulated = false) {
    const type = msg.type || 'content';
    const content = msg.content || '';

    // show ongoing prompt processing progress
    if (type === 'prompt_progress') {
        handlePromptProgress(content);
        return;
    }

    if (type === 'token_usage') {
        updateTokenUsage(content);
        return;
    }

    if (!window._currentAiMsgDiv) {
        createAiWrapper();
    } else if (window._currentAiWrapper && !window._currentAiWrapper.parentNode) {
        chat.insertBefore(window._currentAiWrapper, typing);
    }

    if (!responseStartSoundPlayed) {
        TypewriterAudioManager.play('response_start');
        responseStartSoundPlayed = true;
    }

    // 1. Handle Reasoning
    if (type === 'reasoning' && content) {
        clearProcessingIndicators();
        if (fancyProcessingIndicator) {
            fancyProcessingIndicator.remove();
        }

        if (reasoningDoneSoundPlayed) {
            reasoningDoneSoundPlayed = false;
        }

        appendStreamText(type, content, false);
        renderStreamSegments(window._currentAiMsgDiv);
        if (!isSimulated && window._currentUseStreamingSound) {
            TypewriterAudioManager.play('token');
        }
        updateStopButtonState();
        return;
    }

    // 2. Handle Content
    if (type === 'content' && content) {
        clearProcessingIndicators();
        if (fancyProcessingIndicator) {
            fancyProcessingIndicator.remove();
        }

        if (!reasoningDoneSoundPlayed) {
            TypewriterAudioManager.play('reasoning_end');
            reasoningDoneSoundPlayed = true;
        }

        appendStreamText(type, content, window._currentUseTypewriter);

        if (window._currentUseTypewriter) {
            // Manually queue characters for typewriter mode
            if (typeof activeTypewriterSegId !== 'undefined' && activeTypewriterSegId !== -1) {
                const activeSeg = streamSegments.find(s => s.id === activeTypewriterSegId);
                if (activeSeg && activeSeg.type === 'content') {
                    for (const char of content) {
                        typewriterQueue.push({ segId: activeSeg.id, char });
                    }
                    if (typeof isTypewriterRunning === 'undefined' || !isTypewriterRunning) {
                        startTypewriterProcessSegments(window._currentAiMsgDiv);
                    }
                }
            }
        } else {
            renderStreamSegments(window._currentAiMsgDiv);
            if (!isSimulated && window._currentUseStreamingSound) {
                TypewriterAudioManager.play('token');
            }
        }
        updateStopButtonState();
        return;
    }

    // 3. Handle Tool Call Delta
    if (type === 'tool_call_delta') {
        clearProcessingIndicators();

        ensureToolCallsSegment();
        handleToolCallDelta(msg, window._currentAiMsgDiv, window._currentAiWrapper);
        if (!isSimulated && window._currentUseStreamingSound && !window._currentUseTypewriter) {
            TypewriterAudioManager.play('token');
        }
        updateStopButtonState();
        return;
    }

    // 4. Handle Completed Tool Calls
    if (type === 'tool_calls') {
        clearProcessingIndicators();

        finalizeStreamingToolCalls(msg.tool_calls || [], window._currentAiMsgDiv);
        TypewriterAudioManager.stopProcessingSound();
        updateStopButtonState();
        return;
    }

    // 5. Handle Tool Responses
    if (type === 'tool') {
        handleToolResponse(msg, window._currentAiMsgDiv);
        TypewriterAudioManager.playProcessingSound();
        updateStopButtonState();
        return;
    }

    // gee, ai REALLY likes numbered lists huh
}

// turns out it's really easy to overflow
// a browser's memory and cause a total crash. oopsies!
// processing the catchup buffer in batches fixes that
// ketchup buffer
// ketchup
// yummy
function processBuffer(buffer) {
    if (!buffer.length) return;

    catchingUpFromBuffer = true;

    function processNextBatch() {
        let processed = 0;

        while (processed < BUFFER_BATCH_SIZE && buffer.length > 0) {
            // remove the token from the in-memory buffer
            // so that the buffer shrinks as we process it
            const token = buffer.shift();
            if (!token) break;

            try {
                // process the token as if we're streaming live
                // (but we're not, this is a rapid simulation of a token stream that already happened)
                processToken(token, true);
                processed++;
            } catch (error) {
                console.error('Token processing error:', error);
            }
        }

        if (buffer.length > 0) {
            // use browser's refresh rate to sync everything
            // and prevent totally freezing/crashing the browser
            // this is near-instant, yet much more memory-friendly
            // than doing it all at once
            requestAnimationFrame(processNextBatch);
        } else {
            catchingUpFromBuffer = false;
        }
    }

    processNextBatch();
}

function handleWebSocketMessage(data) {
    if (data.type !== 'token') {
        console.log(data);
    }

    // Handle typed messages from backend
    if (data.type === 'sync_state') {
        if (data.buffer.length > 0) {
            catchingUpFromBuffer = true;
            loadChat(data.active_chat_id, catchingUpFromBuffer);
            createAiWrapper();
            isStreaming = true;
            isDataStreaming = true;
            setInputState(true, false, true);

            // process the buffer in batches so that we don't crash the browser
            processBuffer(data.buffer);
        } else {
            if (data.active_chat_id) {
                loadChat(data.active_chat_id);
            }
        }
        return;
    }

    if (data.type === 'chat_switched') {
        if (data.chat_id === currentChatId) return;
        window.loadChat(data.chat_id, catchingUpFromBuffer, true);
        return;
    }

    if (data.type === 'user_message_added') {
        msgEl = handleNewMessage(data.message);
        msgEl.classList.add('user-placeholder');

        // show the message as a "placeholder" (sent to backend but not sent to API yet)
        sending_status = document.createElement('span');
        sending_status.className = 'placeholder-status';
        sending_status.textContent = 'Sending...';
        msgEl.querySelector('.message').appendChild(sending_status);

        // play the sound
        TypewriterAudioManager.play('send_message');

        // clean up the upload queue
        if (window.upload_queue) {
            window.upload_queue.wrappers.forEach(w => w.remove());
            window.upload_queue.files = [];
            window.upload_queue.wrappers = [];
            window.updateUploadQueueUI();
        }

        return;
    }

    if (data.type === 'user_message_confirmed') {
        // remove the placeholder styling from the user message
        const msgWrapper = chat.querySelector(`[data-index="${data.index}"]`);
        if (msgWrapper) {
            msgWrapper.classList.remove('user-placeholder');
            msgWrapper.querySelector('.message').removeChild(sending_status);
        }

        // show typing indicator
        setInputState(true, true, true);
        return;
    }

    if (data.type === 'token') {
        if (!isStreaming) {
            // keep input field blocked until the stream is done
            setInputState(true, true, true);
            isStreaming = true;
            isDataStreaming = true;

            // create the ai message wrapper
            if (!window._currentAiMsgDiv) {
                createAiWrapper();
            } else if (window._currentAiWrapper && !window._currentAiWrapper.parentNode) {
                chat.insertBefore(window._currentAiWrapper, typing);
            }
        }

        // Extract token type and content correctly
        let tokenType = 'content';
        let msgPayload = data.message;

        if (data.message) {
            tokenType = data.message.type || 'content';
        } else if (data.content) {
            msgPayload = { type: 'content', content: data.content };
            tokenType = 'content';
        }

        processToken(msgPayload, false);
        return;
    }

    if (data.type === 'stream_complete') {
        isDataStreaming = false;
        isStreaming = false;
        streamStarted = false;
        fancyProcessingIndicatorCreated = false;
        responseStartSoundPlayed = false;
        updateStopButtonState();

        if (window._currentAiWrapper) {
            window._currentAiWrapper.dataset.index = data.index;

            if (typeof isTypewriterRunning === 'undefined' || !isTypewriterRunning) {
                if (window._currentAiWrapper) {
                    finalizeStreamingUI(window._currentAiWrapper, window._currentAiMsgDiv);
                }
            } else {
                waitForTypewriter().then(() => {
                    if (window._currentAiWrapper) {
                        finalizeStreamingUI(window._currentAiWrapper, window._currentAiMsgDiv);
                    }
                });
            }
            window._streamInitialized = false;
        }

        setInputState(false, false, false);
    }

    if (data.type === 'messages_updated') {
        try {
            renderAllMessages(data.messages, false);

            if (!catchingUpFromBuffer) {
                // Clear streaming state - the chat structure has changed,
                // so any existing wrapper references are stale.
                // This ensures a new AI wrapper is created when streaming starts
                // (e.g., during message regeneration).

                // thanks Qwen, your comments are kinda verbose though
                // imagine commenting on your AI's comments in your code
                // hi potential readers of the code, you enjoying this?
                // im starting to learn more and more javascript and
                // hope to get the webUI to be more and more manually coded
                // as it is the one part of openlumara that's 90% AI generated
                // which im definitely not happy about

                // also it's way too hot here right now
                // did you know 2026 had a really bad heatwave? yup.
                // hows your day, reader? i know you cant talk back but like,
                // imagine if someone actually read this code and found it and
                // talked to me about it. that would be funny lol

                // it's hard to focus in this heat
                // i'll probably look back on this code after the heatwave is over
                // and be like... WTF Rose
                // but like whatever

                // all AI-assisted code in openlumara is done by local models btw
                // barely any reliance on cloud API coding except for the initial draft of the webUI
                // which was done by GLM-5 on NanoGPT
                window._currentAiWrapper = null;
                window._currentAiMsgDiv = null;
            }
        } catch (e) {
            console.log(e);
        }
        return;
    }

    if (data.type === 'push') {
        if (data.message.content) {
            showNotification(data.message.content, localStorage.getItem('notification_timeout'));
        }

        handleNewMessage(data.message);
        return;
    }

    if (data.type === 'chat_metadata_updated') {
        updateChatTitleBar(data.title, data.tags || []);
        loadChats();
        return;
    }

    if (data.type === 'status_updated') {
        return;
    }

    if (data.type === 'log') {
        handleLogMessage(data);
        return;
    }

    if (data.type === 'log_history') {
        handleLogHistory(data.logs);
        return;
    }

    if (data.type === 'ready') {
        // close the modal and resume everything
        closeModal('log');
    }
    if (data.type === 'shutdown') {
        // show system logs
        closeModal('settings');
        showModal('log', true);
    }

    if (data.type === 'error') {
        handleServerError(data.error);
        return;
    }
}

function handleNewMessage(msg) {
    if (!isWsConnected) return;
    if (!msg || msg.index === undefined) return;
    if (msg.index < lastMessageIndex) return;

    msgEl = renderSingleMessage(msg, msg.index, true);

    if (msg.role !== 'user') {
        TypewriterAudioManager.play('response_start');
    }

    lastMessageIndex = msg.index + 1;
    scrollToBottom();
    updateTokenUsage();

    return msgEl;
}

function showConnectionStatus(status) {
    hideConnectionStatus();
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper announce connection-status-banner';
    if (status === 'reconnecting') {
        wrapper.classList.add('reconnecting-pulse');
    }
    wrapper.setAttribute('role', 'status');
    wrapper.setAttribute('aria-live', 'polite');

    const msgDiv = document.createElement('div');

    let statusText = '';
    let showReconnectBtn = false;

    switch(status) {
        case 'disconnected':
            msgDiv.className = 'message announce announce_error';
            statusText = 'Disconnected from server.';
            showReconnectBtn = true;
            break;
        case 'reconnecting':
            msgDiv.className = 'message announce announce_info';
            statusText = 'Reconnecting...';
            showReconnectBtn = true;
            break;
        case 'reconnected':
            msgDiv.className = 'message announce announce_info';
            statusText = 'Reconnected.';
            break;
        case 'api_disconnected':
            msgDiv.className = 'message announce announce_warning';
            statusText = 'API disconnected. Use /connect to reconnect.';
            break;
    }

    msgDiv.textContent = statusText;
    wrapper.appendChild(msgDiv);

    if (showReconnectBtn) {
        const btn = document.createElement('button');
        btn.className = 'reconnect-btn';
        btn.textContent = 'Reconnect';
        btn.addEventListener('click', () => {
            wsReconnecting = true;
            scheduleWsReconnect();
        });
        wrapper.appendChild(btn);
    }

    statusMessageElement = wrapper;
    chat.insertBefore(wrapper, typing);
    scrollToBottom();
}

function hideConnectionStatus() {
    if (statusMessageElement) {
        statusMessageElement.remove();
        statusMessageElement = null;
    }
}
