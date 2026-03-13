// =============================================================================
// Main Send Function
// =============================================================================

async function send() {
    // Don't block on server connection check - let it fail naturally
    // This allows the initial message to trigger the connection check
    const message = inputField.value.trim();
    if (!message) return;

    // Commands bypass all checks entirely
    if (message.trim().startsWith('/') || message.trim().startsWith("STOP")) {
        clearInput();
        return sendCommand(message);
    }

    // Check API connection status before sending regular messages
    try {
        const statusResponse = await fetch('/api/status', {
            signal: AbortSignal.timeout(5000)
        });

        if (statusResponse.ok) {
            const statusData = await statusResponse.json();

            if (!statusData.connected) {
                clearInput();
                showApiConfigError(
                    statusData.error || 'API is not connected.',
                    statusData.error_type,
                    statusData.action
                );
                return;
            }
        }
    } catch (err) {
        // Server might be unreachable - let the send attempt fail naturally
        console.error('Could not check API status:', err);
    }

    if (isStreaming) return;

    clearInput();

    // Track if we started without a chat (for lazy creation)
    const startedWithoutChat = currentChatId === null;

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
        userMsgDiv.innerHTML = renderMarkdown(message);
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
    aiWrapper.className = 'message-wrapper ai hidden';
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
            body: JSON.stringify({ message: message }),
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

                        if (data.type === 'content') {
                            const token = data.content || '';
                            if (token) {
                                if (!streamStarted) {
                                    streamStarted = true;
                                    typing.classList.remove('show');
                                    aiWrapper.classList.remove('hidden');
                                }
                                if (!streamFrozen) {
                                    aiContent += token;
                                    updateStreamingContent(aiMsgDiv, aiContent, aiReasoning);
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

                            if (!aiWrapper.querySelector('.turn-container')) {
                                aiMsgDiv.innerHTML = '<div class="turn-container current"></div>';
                            }

                            const prevTurns = streamingTurns.map(t =>
                            `<div class="assistant-turn">${renderMarkdown(t.content)}</div>`
                            ).join('');

                            aiMsgDiv.innerHTML = prevTurns + '<div class="turn-container current"></div>';
                        }

                        if (data.token && !data.type) {
                            if (!streamStarted) {
                                streamStarted = true;
                                typing.classList.remove('show');
                                aiWrapper.classList.remove('hidden');
                            }
                            aiContent += data.token;
                            updateStreamingContent(aiMsgDiv, aiContent, aiReasoning);
                            scrollToBottomDelayed();
                        }

                        if (data.done) {
                            streamingTurns.push({ content: aiContent, reasoning: aiReasoning });
                        }

                        if (data.error) {
                            if (!streamStarted) {
                                aiWrapper.classList.remove('hidden');
                            }
                            const errorDetails = data.error_data || {};
                            aiMsgDiv.innerHTML = `<span style="color:#f88;">[Error: ${escapeHtml(errorDetails.message || data.error)}]</span>`;
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
            aiMsgDiv.innerHTML = '<span style="color:#f88;">Error: ' + escapeHtml(err.message) + '</span>';
        }
    } finally {
        const reasoningWrapper = aiWrapper.querySelector('.reasoning-wrapper');
        if (reasoningWrapper && !reasoningWrapper.classList.contains('collapsed')) {
            reasoningWrapper.classList.add('collapsed');
            await new Promise(resolve => setTimeout(resolve, 300));
        }

        finishStream();
        userWrapper.remove();
        aiWrapper.remove();

        await syncMessages();

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

async function sendCommand(message) {
    // Commands work even when API is disconnected
    try {
        // Handle /connect command specially
        if (message.toLowerCase() === '/connect') {
            await reconnectApi();
            return;
        }

        if (message.startsWith("/stop") || message.startsWith("STOP")) {
            fetch('/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message })
            });
            await stopGeneration(true);
        } else {
            const response = await fetch('/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: message })
            });

            // Handle API configuration errors
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

        // Always sync current chat from backend
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

    // Add reasoning block if present (collapsed during streaming)
    if (reasoning) {
        html += renderReasoningBlock(reasoning, false);
    }

    // Add main content
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
    inputField.focus();
}

async function stopGeneration(sent_from_command = false) {
    if (currentController) {
        currentController.abort();
        currentController = null;
    }

    if (currentStreamId) {
        if (!sent_from_command) {
            // send the stop command to the server
            fetch('/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: "/stop" })
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
