// =============================================================================
// Main Send Function
// =============================================================================

// Typewriter State
let typewriterQueue = [];
let displayedContent = '';
let isTypewriterRunning = false;
let isDataStreaming = false;

async function send(providedContent = null) {
    // Reset typewriter state for a new send
    typewriterQueue = [];
    displayedContent = '';
    isTypewriterRunning = false;
    isDataStreaming = true; // Start data stream flag

    // Use provided content or get from input field
    const rawContent = providedContent !== null ? providedContent : inputField.value.trim();
    const message = typeof rawContent === 'string' ? rawContent : extractTextContent(rawContent);

    if (!message) return;

    // Check if this is a regeneration (provided content)
    const isRegenerate = providedContent !== null;

    // Only clear input and check commands for regular sends (not regenerate)
    if (!isRegenerate) {
        clearInput();

        // Commands bypass all checks entirely
        if (message.trim().startsWith('/') || message.trim().startsWith("STOP")) {
            return sendCommand(message);
        }
    }

    // Check API connection status before sending regular messages
    try {
        const statusResponse = await fetch('/api/status', {
            signal: AbortSignal.timeout(5000)
        });

        if (statusResponse.ok) {
            const statusData = await statusResponse.json();

            if (!statusData.connected) {
                if (!isRegenerate) {
                    showApiConfigError(
                        statusData.error || 'API is not connected.',
                        statusData.error_type,
                        statusData.action
                    );
                }
                return;
            }
        }
    } catch (err) {
        console.error('Could not check API status:', err);
    }

    if (isStreaming) return;

    // Only clear input if not regenerating
    if (!isRegenerate) {
        clearInput();
    }

    // Track if we started without a chat (for lazy creation)
    const startedWithoutChat = currentChatId === null;

    // Track if stream had an error
    let streamHadError = false;

    // Create user message element
    const userWrapper = document.createElement('div');
    userWrapper.className = message.trim().startsWith('/')
    ? 'message-wrapper user_command'
    : 'message-wrapper user';
    userWrapper.classList.add('animate-in');
    userWrapper.setAttribute('role', 'article');
    userWrapper.dataset.index = 'pending';

    const userMsgDiv = document.createElement('div');
    userMsgDiv.className = message.trim().startsWith('/')
    ? 'message user_command'
    : 'message user';

    if (message.trim().startsWith('/')) {
        userMsgDiv.innerHTML = `<pre>${escapeHtml(message)}</pre>`;
    } else {
        // Use renderContentBody for multi-modal content support
        userMsgDiv.innerHTML = renderContentBody(rawContent);
        highlightCode(userMsgDiv);
    }

    const userTs = document.createElement('span');
    userTs.className = 'timestamp timestamp-right';
    userTs.textContent = formatTime();
    userMsgDiv.appendChild(userTs);

    const userActions = createActionButtons('user', 'pending', message, true);
    userWrapper.appendChild(userMsgDiv);
    userWrapper.appendChild(userActions);
    chat.insertBefore(userWrapper, typing);
    scrollToBottom();

    setInputState(true, true, true);
    isStreaming = true;
    currentController = new AbortController();

    // Create AI message wrapper (hidden until first token)
    const aiWrapper = document.createElement('div');
    aiWrapper.className = 'message-wrapper ai hidden streaming';
    aiWrapper.dataset.index = 'streaming';
    chat.insertBefore(aiWrapper, typing);

    const aiMsgDiv = document.createElement('div');
    aiMsgDiv.className = 'message ai';
    aiWrapper.appendChild(aiMsgDiv);

    const aiActions = createActionButtons('assistant', 'streaming', '', true);
    aiWrapper.appendChild(aiActions);

    let aiContent = '';
    let aiReasoning = '';
    let streamStarted = false;
    let hasReasoning = false;

    try {
        const response = await fetch('/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            // Use raw content to preserve multi-modal structure
            body: JSON.stringify({ role: "user", content: rawContent }),
                                     signal: currentController.signal
        });

        // Handle server errors (not API errors)
        if (!response.ok) {
            if (response.status === 503) {
                let errorData;
                try {
                    errorData = await response.json();
                } catch (e) {
                    errorData = { error: 'API is not available.' };
                }
                userWrapper.remove();
                aiWrapper.remove();
                showApiConfigError(
                    errorData.error || 'API is not available.',
                    errorData.error_type,
                    errorData.action
                );
                finishStream();
                return;
            } else {
                throw new Error(`Server error: ${response.status}`);
            }
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        // Check typewriter speed setting once at the start
        const typewriterSpeed = parseInt(localStorage.getItem("typewriterSpeed") ?? "30", 10);
        const useTypewriter = typewriterSpeed > 0;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));

                        if (data.id) {
                            currentStreamId = data.id;
                        }

                        if (data.cancelled) {
                            aiWrapper.classList.remove('hidden');
                            aiMsgDiv.innerHTML = '<span style="color:#f88;">[Cancelled]</span>';
                            finishStream();
                            return;
                        }

                        if (data.type === 'content' || data.token) {
                            const token = data.content || data.token || '';
                            if (token) {
                                if (!streamStarted) {
                                    streamStarted = true;
                                    typing.classList.remove('show');
                                    aiWrapper.classList.remove('hidden');
                                }

                                aiContent += token;

                                if (useTypewriter) {
                                    // Push characters to the typewriter queue
                                    for (const char of token) {
                                        typewriterQueue.push(char);
                                    }

                                    // Start the typewriter playback loop if it isn't running
                                    if (!isTypewriterRunning) {
                                        startTypewriterProcess(aiMsgDiv, aiReasoning);
                                    }
                                } else {
                                    // Speed is 0: Direct update bypassing the queue
                                    displayedContent += token;
                                    updateStreamingContent(aiMsgDiv, displayedContent, aiReasoning);
                                    scrollToBottomDelayed();
                                }
                            }
                        }

                        if (data.type === 'reasoning') {
                            if (!streamStarted) {
                                streamStarted = true;
                                typing.classList.remove('show');
                                aiWrapper.classList.remove('hidden');
                            }
                            hasReasoning = true;
                            if (!streamFrozen) {
                                aiReasoning += data.content || '';
                                updateStreamingContent(aiMsgDiv, aiContent, aiReasoning);
                                scrollToBottomDelayed();
                            }
                        }

                        if (data.type === 'new_turn') {
                            currentTurnIndex++;
                            aiContent = '';
                            aiReasoning = '';
                            displayedContent = ''; // Reset typewriter buffer for the new turn

                            if (!aiWrapper.querySelector('.turn-container')) {
                                aiMsgDiv.innerHTML = '<div class="turn-container current"></div>';
                            }

                            const prevTurns = streamingTurns.map(t =>
                            `<div class="assistant-turn">${renderMarkdown(t.content)}</div>`
                            ).join('');

                            aiMsgDiv.innerHTML = prevTurns + '<div class="turn-container current"></div>';
                        }

                        if (data.done) {
                            streamingTurns.push({ content: aiContent, reasoning: aiReasoning });
                        }

                        if (data.error) {
                            if (!streamStarted) {
                                aiWrapper.classList.remove('hidden');
                            }

                            const errorDetails = data.error_data || {};
                            const errorMessage = errorDetails.message || 'An error occurred';
                            const errorType = errorDetails.error || 'unknown';

                            const errorTypeInfo = {
                                'not_connected': { title: 'Not Connected', action: 'Please check your API configuration.' },
                                'auth_failed': { title: 'Authentication Failed', action: 'Your API key may be invalid. Please check your settings.' },
                                'connection_lost': { title: 'Connection Lost', action: 'Lost connection to the API server. Please try again.' },
                                'rate_limit': { title: 'Rate Limit Exceeded', action: 'Please wait a moment and try again.' },
                                'api_error': { title: 'API Error', action: 'The API returned an error. Please try again.' },
                                'stream_failed': { title: 'Stream Failed', action: 'The response stream was interrupted.' },
                                'processing_failed': { title: 'Processing Failed', action: 'Failed to process the AI response.' },
                                'invalid_response': { title: 'Invalid Response', action: 'Received an invalid response from the API.' }
                            };

                            const info = errorTypeInfo[errorType] || { title: 'Error', action: '' };

                            aiMsgDiv.innerHTML = `
                            <div class="api-error-inline">
                            <div class="api-error-header">
                            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <circle cx="12" cy="12" r="10"/>
                            <line x1="12" y1="8" x2="12" y2="12"/>
                            <line x1="12" y1="16" x2="12.01" y2="16"/>
                            </svg>
                            <span class="api-error-title">${escapeHtml(info.title)}</span>
                            </div >
                            <div class="api-error-message">${escapeHtml(errorMessage)}</div >
                            ${info.action ? `<div class="api-error-action">${escapeHtml(info.action)}</div >` : ''}
                            </div >
                            `;

                            streamHadError = true;
                            // Stop the typewriter from continuing after an error
                            typewriterQueue = [];
                        }
                    } catch (e) {
                        // Ignore parse errors
                    }
                }
            }
        }
    } catch (err) {
        if (err.name !== 'AbortError') {
            if (!streamStarted) {
                aiWrapper.classList.remove('hidden');
            }
            aiMsgDiv.innerHTML = `
            <div class="api-error-inline">
            <div class="api-error-header">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <span class="api-error-title">Connection Error</span>
            </div >
            <div class="api-error-message">${escapeHtml(err.message)}</div >
            <div class="api-error-action">Could not reach the server. Please check your connection.</div >
            </div >
            `;
            streamHadError = true;
            typewriterQueue = []; // Stop typewriter on catch
        }
    } finally {
        // Signal that NO MORE DATA is coming from the network
        // This allows the typewriter loop to finish draining its queue
        isDataStreaming = false;

        // If typewriter is active, wait for it to finish flushing the queue
        if (isTypewriterRunning) {
            await new Promise(resolve => {
                const interval = setInterval(() => {
                    if (!isTypewriterRunning) {
                        clearInterval(interval);
                        resolve();
                    }
                }, 20);
            });
        }

        const reasoningWrapper = aiWrapper.querySelector('.reasoning-wrapper');
        if (reasoningWrapper && !reasoningWrapper.classList.contains('collapsed')) {
            reasoningWrapper.classList.add('collapsed');
            await new Promise(resolve => setTimeout(resolve, 300));
        }

        finishStream();

        if (!streamHadError) {
            userWrapper.remove();
            aiWrapper.remove();
            await syncMessages();
        } else {
            userWrapper.remove();
            aiWrapper.classList.remove('streaming');
            const actions = aiWrapper.querySelector('.message-actions');
            if (actions) {
                actions.querySelectorAll('button').forEach(btn => btn.disabled = false);
            }
        }

        const chatResponse = await fetch('/chat/current');
        const chatData = await chatResponse.json();
        if (chatData.success && chatData.chat) {
            currentChatId = chatData.chat.id;
            updateChatTitleBar(
                chatData.chat.title,
                chatData.chat.tags || []
            );
        }

        await loadChats();
    }
}

/**
 * Typewriter Logic: Processes the character queue one-by-one
 */
async function startTypewriterProcess(msgDiv, reasoning) {
    isTypewriterRunning = true;

    const typewriterEnabled = localStorage.getItem("typewriterEnabled") !== 'false';
    if (!typewriterEnabled) {
        displayedContent += typewriterQueue.join('');
        typewriterQueue = [];
        updateStreamingContent(msgDiv, displayedContent, reasoning);
        isTypewriterRunning = false;
        return;
    }

    const speed = parseInt(localStorage.getItem("typewriterSpeed") ?? "30", 10);

    // Loop runs while:
    // 1. There are characters to type OR
    // 2. The network data hasn't finished arriving yet (isDataStreaming)
    while (typewriterQueue.length > 0 || isDataStreaming) {
        if (typewriterQueue.length > 0) {
            const char = typewriterQueue.shift();
            displayedContent += char;

            updateStreamingContent(msgDiv, displayedContent, reasoning);
            scrollToBottomDelayed();

            // Play sound using AudioContext (CSP safe)
            if (char.trim() !== '') {
                TypewriterAudioManager.play('typewriter');
            }

            await new Promise(resolve => setTimeout(resolve, speed));
        } else {
            // Queue is empty, but network stream is still active.
            // Wait briefly for more data.
            await new Promise(resolve => setTimeout(resolve, 20));
        }
    }

    // Play completion sound using AudioContext (CSP safe)
    TypewriterAudioManager.play('completion');

    isTypewriterRunning = false;
}

async function sendCommand(message) {
    try {
        if (message.toLowerCase() === '/connect') {
            await reconnectApi();
            return;
        }

        if (message.startsWith("/stop") || message.startsWith("STOP")) {
            fetch('/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({role: "user", content: message })
            });
            await stopGeneration(true);
        } else {
            const response = await fetch('/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({role: "user", content: message })
            });

            if (response.status === 503) {
                let errorData;
                try {
                    errorData = await response.json();
                } catch (e) {
                    errorData = { error: 'API is not available.' };
                }
                showApiConfigError(
                    errorData.error || 'API is not available.',
                    errorData.error_type,
                    errorData.action
                );
                return;
            }

            if (!isStreaming) {
                await syncMessages();
            }
        }

        const chatResponse = await fetch('/chat/current');
        const chatData = await chatResponse.json();
        if (chatData.success && chatData.chat) {
            currentChatId = chatData.chat.id;
            updateChatTitleBar(
                chatData.chat.title,
                chatData.chat.tags || []
            );
        }

        await loadChats();
    } catch (err) {
        console.error('Command failed:', err);
    }
}

function updateStreamingContent(msgDiv, content, reasoning) {
    let html = '';

    if (reasoning) {
        const expandByDefault = localStorage.getItem('reasoningExpandedByDefault') === 'true';
        const isCollapsed = !expandByDefault;
        html += renderReasoningBlock(reasoning, isCollapsed);
    }

    if (content) {
        html += renderMarkdown(content);
    }

    msgDiv.innerHTML = html;
    highlightCode(msgDiv);
}

function finishStream() {
    setInputState(false, false, false);
    isStreaming = false;
    streamFrozen = false;
    currentController = null;
    currentStreamId = null;

    // Reset typewriter states
    typewriterQueue = [];
    displayedContent = '';
    isTypewriterRunning = false;

    inputField.focus();
}

async function stopGeneration(sent_from_command = false) {
    if (currentController) {
        currentController.abort();
        currentController = null;
    }

    if (currentStreamId) {
        if (!sent_from_command) {
            fetch('/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({role: "user", content: "/stop" })
            });
        }
        try {
            await fetch('/cancel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: currentStreamId })
            });
        } catch (e) {
            // Ignore
        }
        currentStreamId = null;
    }

    await syncMessages();
    finishStream();
}
