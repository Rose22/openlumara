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
    isDataStreaming = true;
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

        // Check settings once at the start
        const typewriterEnabled = localStorage.getItem("typewriterEnabled") !== 'false';
        const typewriterSpeed = parseInt(localStorage.getItem("typewriterSpeed") ?? "30", 10);
        const useTypewriter = typewriterEnabled && typewriterSpeed > 0;

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
        // Render the full content as Markdown first
        html += renderMarkdown(content);
    }

    // Update the DOM
    msgDiv.innerHTML = html;

    // Highlight code blocks
    highlightCode(msgDiv);

    // Apply fade effect to the last text node if enabled
    const fadeEnabled = localStorage.getItem('typewriterFadeEnabled') === 'true';

    if (fadeEnabled && content && content.length > 0) {
        applyFadeToLastTextNode(msgDiv, content.length);
    }
}

/**
 * Traverses the DOM to find the last text node and applies the fade effect
 * to the last N characters by wrapping them in opacity spans.
 */
function applyFadeToLastTextNode(rootElement, totalContentLength) {
    const fadeLength = 8;
    const minOpacity = 0.1;

    // Find the deepest last child (the tail of the content)
    // We traverse specifically to find the last text node in the visual order.
    let lastTextNode = findLastTextNode(rootElement);

    if (!lastTextNode) return;

    const textContent = lastTextNode.textContent;
    const textLen = textContent.length;

    // We can only fade as many characters as exist in this specific node.
    // Usually, the last node contains the tail of the content.
    // Calculate how many chars to fade in THIS node.
    const fadeCount = Math.min(fadeLength, textLen);

    if (fadeCount <= 0) return;

    // Split the text node: [Stable Part] [Fade Part]
    // We keep the stable part as a text node, and replace the fade part with spans.
    const splitIndex = textLen - fadeCount;

    // If splitIndex is 0, we are fading the whole node.
    // If splitIndex > 0, we split the node.

    const stablePart = textContent.substring(0, splitIndex);
    const fadePart = textContent.substring(splitIndex);

    // Create a fragment for the faded characters
    const fragment = document.createDocumentFragment();

    // 1. Add the stable text first (if any)
    if (stablePart) {
        fragment.appendChild(document.createTextNode(stablePart));
    }

    // 2. Add the faded characters
    // To calculate opacity correctly relative to the entire message stream,
    // we need to map local index to global index.
    // However, since this node is strictly the LAST node, its characters are the last chars of the stream.
    // So local position 'i' corresponds to global position 'i'.

    const fadeChars = Array.from(fadePart); // Handle unicode

    fadeChars.forEach((char, i) => {
        // Calculate position relative to the fade window
        // i=0 -> start of fade zone (oldest in fade zone)
        // i=max -> end of fade zone (newest)

        // Position from end of stream:
        // The last char (i = length-1) is the newest.
        // The char at i=0 in fadePart is the oldest within the fade part.

        // Note: In a partial fade (e.g. fadeLength 8, but node only has 3 chars),
        // we assume these 3 chars are the absolute newest characters.
        // So the first char in this fadePart (i=0) should actually have opacity based on its position
        // relative to the global fadeLength.

        // If fadePart has 3 chars, they are positions -3, -2, -1.
        // Global fadeLength is 8.
        // Pos -3 should be opacity ~0.6?
        // Or should we just treat them as the last 3?
        // "most recent character is the lowest opacity... 8 characters back being full opacity"
        // If we only have 3 chars in this node, we don't have the "8 chars back".
        // We assume the "missing" earlier chars are in the stable text node we just created.

        // So we map opacity based on the index within the fade window.
        const progress = (fadeLength > 1) ? (i / (fadeLength - 1)) : 0;
        // Clamp progress to [0, 1] just in case
        const clampedProgress = Math.min(1, Math.max(0, progress));

        // Opacity: 1.0 (old) -> minOpacity (new)
        // i=0 is older (closer to stable). opacity = 1.0 - (0/7)*0.9 = 1.0
        // i=7 is newer. opacity = 1.0 - (7/7)*0.9 = 0.1
        // BUT, if we have only 3 chars, i=0,1,2.
        // If we use i/7:
        // i=0 -> 1.0
        // i=2 -> 1.0 - (2/7)*0.9 = 0.74
        // This makes them relatively brighter than they should be?
        // Actually, if they are the last 3 chars of the whole stream, they are the newest.
        // They should be the dimmest.
        // Last 3 chars indices globally are -3, -2, -1.
        // Positions in fade window of 8: indices 5, 6, 7.
        // Opacities: 0.35, 0.22, 0.1

        // Correct calculation:
        // Global index relative to end:
        // We need to know how many characters exist before this node in the DOM?
        // That's hard to calculate efficiently (requires traversing previous siblings).

        // Heuristic approach:
        // If this node contains less than fadeLength, we assume it is the tail of the stream.
        // We map the opacity such that the very last character is the dimmest.
        // We scale the interpolation based on how many chars we have.

        // Let's use the simple logic: The first char in 'fadePart' is the oldest among the fading ones.
        // The last char is the newest.
        // We map 0...len-1 to 1.0...minOpacity.

        // i=0 (oldest in this chunk) -> 1.0
        // i=len-1 (newest) -> minOpacity
        // This is visually correct for a "sweep fade" effect on the tail, regardless of total length.

        let opacity = 1.0;
        if (fadeChars.length > 1) {
            const localProgress = i / (fadeChars.length - 1);
            opacity = 1.0 - (localProgress * (1.0 - minOpacity));
        } else {
            // Single char, so it's the newest.
            opacity = minOpacity;
        }

        const span = document.createElement('span');
        span.style.opacity = opacity.toFixed(2);
        span.textContent = char;
        fragment.appendChild(span);
    });

    // Replace the original text node with our fragment
    // (We effectively remove the old node and insert the new structure)
    lastTextNode.parentNode.replaceChild(fragment, lastTextNode);
}

/**
 * Helper to find the last text node in a DOM tree (depth-first search).
 */
function findLastTextNode(node) {
    if (node.nodeType === Node.TEXT_NODE) {
        // Check if it's just whitespace
        if (node.textContent.trim().length === 0) return null;
        return node;
    }

    // Iterate children backwards
    for (let i = node.childNodes.length - 1; i >= 0; i--) {
        const child = node.childNodes[i];
        const result = findLastTextNode(child);
        if (result) return result;
    }

    return null;
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
