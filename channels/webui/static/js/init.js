// =============================================================================
// WebSocket Connection Management (Module Level)
// =============================================================================

let wsSocket = null;

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
    console.log(`attempting to reconnect to websocket..`);
    setTimeout(connectWebSocket, 1000);
}

function handlePromptProgress(prog) {
    if (!prog || typeof prog !== 'object') return;

    const cache = prog.cache || 0;
    const processed = prog.processed - cache;
    const total = prog.total - cache;
    const percent = total > 0 ? Math.round((processed / total) * 100) : 0;
    const elapsed = prog.time_ms / 1000;
    const remaining = (total - processed) > 0 ? (elapsed / processed) * (total - processed) : 0;

    // Update Tool Processing Indicator if it exists
    if (typeof toolProcessingIndicatorElement !== 'undefined' && toolProcessingIndicatorElement && toolProcessingIndicatorElement.updateProgress) {
        toolProcessingIndicatorElement.updateProgress(percent);
    }

    // Update progress bar and text
    if (typeof progressBarFill !== 'undefined' && progressBarFill) {
        progressBarFill.style.width = `${percent}%`;
    }
    if (typeof progressTextPercent !== 'undefined' && progressTextPercent && typeof progressTextETA !== 'undefined' && progressTextETA) {
        progressTextPercent.textContent = `${percent}%`;
        progressTextETA.textContent = `(ETA: ${Math.ceil(remaining)}s)`;
    }
}

function handleWebSocketMessage(data) {
    // Handle typed messages from backend
    if (data.type === 'sync_state') {
        // Sync handshake: restore active chat and buffer
        if (data.active_chat_id) {
            switchChat(data.active_chat_id, true);
        }
        if (data.buffer) {
            // Append buffer to current message if streaming
            if (typeof appendStreamText === 'function') {
                appendStreamText(data.buffer);
            }
            if (typeof renderStreamSegments === 'function' && window._currentAiMsgDiv) {
                renderStreamSegments(window._currentAiMsgDiv);
            }
        }
        return;
    }
    if (data.type === 'chat_switched') {
        // Force switch chat on all devices
        loadChat(data.chat_id);
        // Clear buffer if empty
        if (!data.buffer || data.buffer.length === 0) {
            if (typeof resetStreamState === 'function') resetStreamState();
            window._streamInitialized = false;
        } else {
            if (typeof appendStreamText === 'function') {
                appendStreamText(data.buffer.join(''));
            }
            if (typeof renderStreamSegments === 'function' && window._currentAiMsgDiv) {
                renderStreamSegments(window._currentAiMsgDiv);
            }
        }
        return;
    }
    if (data.type === 'token') {
        // Real-time token broadcasting
        if (!window._currentAiMsgDiv) {
            // If no AI message wrapper exists, it means a new stream has started.
            // We create the streaming AI wrapper here.
            console.log('[DEBUG] First token received. Creating streaming AI wrapper.');
            
            const aiWrapper = document.createElement('div');
            aiWrapper.className = 'message-wrapper ai hidden streaming';
            // Use lastMessageIndex because the user message was just broadcast with next_index
            aiWrapper.dataset.index = lastMessageIndex; 

            const aiMsgDiv = document.createElement('div');
            aiMsgDiv.className = 'message ai';
            aiWrapper.appendChild(aiMsgDiv);

            const aiActions = createActionButtons('assistant', 'streaming', '', true);
            const statsDiv = document.createElement('div');
            statsDiv.id = 'message-stats-container';
            statsDiv.className = 'action-stats';
            const actionsRow = document.createElement('div');
            actionsRow.className = 'actions-stats-row';
            actionsRow.appendChild(aiActions);
            actionsRow.appendChild(statsDiv);
            aiWrapper.appendChild(actionsRow);

            chat.insertBefore(aiWrapper, typing);
            
            // FIX: Make the wrapper visible immediately
            aiWrapper.classList.remove('hidden');
            
            // Set globals for subsequent tokens in this stream
            window._currentAiWrapper = aiWrapper;
            window._currentAiMsgDiv = aiMsgDiv;
            window._currentUseTypewriter = localStorage.getItem("typewriterEnabled") === 'true';
            window._currentUseStreamingSound = localStorage.getItem("tokenEnabled") === 'true';

            // Initialize local streaming state
            isStreaming = true;
            isDataStreaming = true;

            // Remove progress indicator when first token arrives
            if (fancyProcessingIndicator) {
                fancyProcessingIndicator.remove();
                fancyProcessingIndicator = null;
                if (typing) typing.style.display = '';
            }
        } else if (window._currentAiWrapper && !window._currentAiWrapper.parentNode) {
            // Fallback: Insert AI wrapper if it was created but not yet in the DOM
            chat.insertBefore(window._currentAiWrapper, typing);
        }

        // Extract token type and content correctly
        let tokenType = 'content';
        let tokenContent = '';
        
        if (data.message) {
            tokenType = data.message.type || 'content';
            tokenContent = data.message.content || '';
        } else if (data.content) {
            tokenContent = data.content;
        }

        // Handle prompt progress
        if (tokenType === 'prompt_progress' && tokenContent) {
            if (typeof handlePromptProgress === 'function') {
                handlePromptProgress(tokenContent);
            }
            return;
        }

        if (tokenType === 'reasoning' && tokenContent) {
            if (typeof appendStreamText === 'function') {
                appendStreamText(tokenType, tokenContent, false);
            }
            if (typeof renderStreamSegments === 'function') {
                renderStreamSegments(window._currentAiMsgDiv);
            }
            if (window._currentUseStreamingSound) {
                TypewriterAudioManager.play('token');
            }
            updateStopButtonState();
        } else if (tokenType === 'content' && tokenContent) {
            if (typeof appendStreamText === 'function') {
                appendStreamText(tokenType, tokenContent, window._currentUseTypewriter);
            }
            if (window._currentUseTypewriter) {
                // Manually queue characters for typewriter mode
                if (typeof activeTypewriterSegId !== 'undefined' && activeTypewriterSegId !== -1) {
                    const activeSeg = streamSegments.find(s => s.id === activeTypewriterSegId);
                    if (activeSeg && activeSeg.type === 'content') {
                        for (const char of tokenContent) {
                            typewriterQueue.push({ segId: activeSeg.id, char });
                        }
                        if (typeof isTypewriterRunning === 'undefined' || !isTypewriterRunning) {
                            if (typeof startTypewriterProcessSegments === 'function') {
                                startTypewriterProcessSegments(window._currentAiMsgDiv);
                            }
                        }
                    }
                }
            } else {
                if (typeof renderStreamSegments === 'function') {
                    renderStreamSegments(window._currentAiMsgDiv);
                }
                if (window._currentUseStreamingSound) {
                    TypewriterAudioManager.play('token');
                }
            }
            updateStopButtonState();
        } else if (tokenType === 'tool_call_delta') {
            // Handle tool call deltas
            if (typeof ensureToolCallsSegment === 'function') {
                ensureToolCallsSegment();
            }
            if (typeof handleToolCallDelta === 'function') {
                handleToolCallDelta(data.message, window._currentAiMsgDiv, window._currentAiWrapper);
            }
            if (window._currentUseStreamingSound && !window._currentUseTypewriter) {
                TypewriterAudioManager.play('token');
            }
            updateStopButtonState();
        } else if (tokenType === 'tool_calls') {
            // Handle completed tool calls
            if (typeof finalizeStreamingToolCalls === 'function') {
                finalizeStreamingToolCalls(data.message.tool_calls || [], window._currentAiMsgDiv);
            }
            if (typeof TypewriterAudioManager !== 'undefined') {
                TypewriterAudioManager.stopProcessingSound();
            }
            updateStopButtonState();
        } else if (tokenType === 'tool') {
            // Handle tool responses
            if (typeof handleToolResponse === 'function') {
                handleToolResponse(data.message, window._currentAiMsgDiv);
            }
            if (typeof TypewriterAudioManager !== 'undefined') {
                TypewriterAudioManager.playProcessingSound();
            }
            updateStopButtonState();
        }
        return;
    }
    if (data.type === 'stream_complete') {
        // Signal end of streaming
        isDataStreaming = false; // Mark stream as complete
        isStreaming = false; // Reset global flag
        updateStopButtonState(); // Update button state immediately
        
        // Wait for typewriter to finish if it's still running
        if (typeof isTypewriterRunning === 'undefined' || !isTypewriterRunning) {
            if (typeof finalizeStreamingUI === 'function' && window._currentAiWrapper) {
                finalizeStreamingUI(window._currentAiWrapper, window._currentAiMsgDiv);
            }
        } else {
            // If typewriter is running, wait for it to finish before finalizing
            if (typeof waitForTypewriter === 'function') {
                waitForTypewriter().then(() => {
                    if (typeof finalizeStreamingUI === 'function' && window._currentAiWrapper) {
                        finalizeStreamingUI(window._currentAiWrapper, window._currentAiMsgDiv);
                    }
                });
            }
        }
        window._streamInitialized = false;
        return;
    }
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
        if (typeof handleServerError === 'function') {
            handleServerError(data.error);
        }
        return;
    }
    // Legacy: handle raw message objects (for backwards compatibility)
    if (data.role && data.content !== undefined) {
        if (data.index === undefined) {
            // Try to determine index from current state
            data.index = lastMessageIndex;
        }
        handleNewMessage(data.message);
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

    // If this is a user message and we have a placeholder, remove it
    if (msg.role === 'user' && typeof placeholderUserWrapper !== 'undefined' && placeholderUserWrapper.parentNode) {
        console.log('[DEBUG] Removing user message placeholder');
        placeholderUserWrapper.remove();
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

// =============================================================================
// Log Modal Functions
// =============================================================================

let logAutoScroll = true;

function handleLogMessage(data) {
    const logContent = document.getElementById('log-log-content');
    if (!logContent) return;

    const timestamp = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `<span class="log-timestamp">[${timestamp}]</span> <span class="log-category">[${data.category.toUpperCase()}]</span> <span class="log-message">${escapeHtml(data.message)}</span>`;

    logContent.appendChild(entry);

    if (logAutoScroll) {
        const logContainer = document.getElementById('log-log-container');
        if (logContainer) {
            logContainer.scrollTop = logContainer.scrollHeight;
        }
    }
}

function handleLogHistory(logs) {
    const logContent = document.getElementById('log-log-content');
    if (!logContent) return;

    // Clear existing logs
    logContent.innerHTML = '';

    // Add all historical logs
    for (const log of logs) {
        const entry = document.createElement('div');
        entry.className = 'log-entry';
        entry.innerHTML = `<span class="log-timestamp">[${new Date().toLocaleTimeString()}]</span> <span class="log-category">[${log.category.toUpperCase()}]</span> <span class="log-message">${escapeHtml(log.message)}</span>`;
        logContent.appendChild(entry);
    }
}

function clearLog() {
    const logContent = document.getElementById('log-log-content');
    if (logContent) {
        logContent.innerHTML = '';
    }
}

function toggleLogAutoScroll() {
    logAutoScroll = !logAutoScroll;
    const btn = document.getElementById('log-autoscroll-btn');
    if (btn) {
        btn.textContent = `Auto-scroll: ${logAutoScroll ? 'ON' : 'OFF'}`;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

init();
