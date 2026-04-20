// =============================================================================
// Main Send Function
// =============================================================================
let placeholderUserWrapper = null;
let typingStatusEl = null;

async function send(providedContent = null) {
    // 1. Pre-checks and State Reset
    if (isStreaming) return;

    // if the last message is a user message, and the user presses the Send button while no input is in the input box, regenerate
    if (providedContent === null && inputField.value.trim() === '') {
        const allMessages = chat.querySelectorAll('.message-wrapper');
        const lastMsg = allMessages[allMessages.length - 1];

        // Only proceed if the last message in the chat is actually a user message
        if (lastMsg && lastMsg.classList.contains('user')) {
            const index = parseInt(lastMsg.dataset.index);
            if (!isNaN(index)) {
                regenerateMessage(index);
                return;
            }
        }
        // If the last message is an assistant message (or no messages exist), just exit
        return;
    }

    const isRegenerate = providedContent !== null;
    const rawContent = providedContent !== null ? providedContent : inputField.value.trim();
    const message = typeof rawContent === 'string' ? rawContent : extractTextContent(rawContent);

    if (!message) return;

    // Reset typewriter state
    typewriterQueue = [];
    displayedContent = '';
    isTypewriterRunning = false;

    // 2. Handle Commands
    if (!isRegenerate) {
        clearInput();
        if (message.trim().startsWith('/') || message.trim().startsWith("STOP")) {
            return sendCommand(message);
        }
    }

    // 3. STAGE: SENDING (Optimistic UI)
    if (!isRegenerate) {
        // Standard new message: Show the "Sending..." placeholder
        placeholderUserWrapper = createPlaceholderUserMessage(message);
        chat.insertBefore(placeholderUserWrapper, typing);
    } else {
        // REGENERATION: Create a standard user message immediately
        // so it doesn't "vanish" while the AI is thinking.
        const allMessages = chat.querySelectorAll('.message-wrapper')
        const userMsgWrapper = createMessageElement({"role": "user", "content": message}, allMessages.length);
        chat.insertBefore(userMsgWrapper, typing);
    }

    // 4. API Status Check
    try {
        const statusResponse = await fetch('/api/status', { signal: AbortSignal.timeout(5000) });
        if (statusResponse.ok) {
            const statusData = await statusResponse.json();
            if (!statusData.connected) {
                removePlaceholder();
                if (!isRegenerate) {
                    showApiConfigError(statusData.error || 'API is not connected.', statusData.error_type, statusData.action);
                }
                return;
            }
        }
    } catch (err) {
        console.error('Could not check API status:', err);
    }

    // 5. Prepare Payload
    const hasFiles = window.upload_queue && window.upload_queue.files.length > 0;
    const isMultimodalInput = typeof rawContent !== 'string';
    let payloadBody;

    if (!hasFiles && !isMultimodalInput) {
        payloadBody = { role: "user", content: rawContent };
    } else {
        let contentPayload = [];
        if (typeof rawContent === 'string') {
            contentPayload.push({ type: 'text', text: rawContent });
        } else {
            contentPayload = [...rawContent];
        }
        if (hasFiles) {
            const queuedContents = window.upload_queue.files.map(f => f.content);
            contentPayload.push(...queuedContents);
        }
        contentPayload = contentPayload.flat();
        payloadBody = { role: "user", content: contentPayload };
    }

    // 6. UI Preparation
    setInputState(true, true, true);
    isStreaming = true;
    isDataStreaming = true;
    currentController = new AbortController();

    const aiWrapper = document.createElement('div');
    aiWrapper.className = 'message-wrapper ai hidden streaming';
    aiWrapper.dataset.index = 'streaming';

    const aiMsgDiv = document.createElement('div');
    aiMsgDiv.className = 'message ai';
    aiWrapper.appendChild(aiMsgDiv);

    const aiActions = createActionButtons('assistant', 'streaming', '', true);
    aiWrapper.appendChild(aiActions);

    let streamHadError = false;

    try {
        const response = await fetch('/stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payloadBody),
            signal: currentController.signal
        });

        if (!response.ok) {
            removePlaceholder();
            return await handleServerError(response, aiWrapper);
        }

        await syncMessages();

        // Handle file upload cleanup
        if (window.upload_queue) {
            window.upload_queue.wrappers.forEach(w => w.remove());
            window.upload_queue.files = [];
            window.upload_queue.wrappers = [];
            window.updateUploadQueueUI();
        }

        chat.insertBefore(aiWrapper, typing);

        // 8. Stream Reading Loop
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        const typewriterEnabled = localStorage.getItem("typewriterEnabled") !== 'false';
        const typewriterSpeed = parseInt(localStorage.getItem("typewriterSpeed") ?? "30", 10);
        const useTypewriter = typewriterEnabled && typewriterSpeed > 0;

        let aiContent = '';
        let aiReasoning = '';
        let streamStarted = false;

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (!line.startsWith('data: ')) continue;

                try {
                    const data = JSON.parse(line.slice(6));

                    if (data.id) currentStreamId = data.id;

                    if (data.cancelled) {
                        aiWrapper.classList.remove('hidden');
                        aiMsgDiv.innerHTML = '<span style="color:#f88;">[Cancelled]</span>';
                        finishStream();
                        return;
                    }

                    // 9. STAGE: STREAMING (No special text, clear indicators)
                    if (data.type === 'content' || data.token || data.type === 'reasoning' || data.type === 'tool_call_delta' || data.type === 'tool_calls') {
                        if (!streamStarted) {
                            // Transition from "Processing" to real streaming
                            removePlaceholder();
                            startStreamingUI(aiWrapper, typing);
                            streamStarted = true;
                        }

                        // Handle Content Tokens
                        if (data.type === 'content' || data.token) {
                            const token = data.content || data.token || '';
                            if (token) {
                                const reasoningWrapper = aiWrapper.querySelector('.reasoning-wrapper');
                                if (reasoningWrapper) reasoningWrapper.classList.remove('is-reasoning-active');

                                aiContent += token;

                                if (useTypewriter) {
                                    for (const char of token) typewriterQueue.push(char);
                                    if (!isTypewriterRunning) startTypewriterProcess(aiMsgDiv, aiReasoning);
                                } else {
                                    displayedContent += token;
                                    updateStreamingContent(aiMsgDiv, displayedContent, aiReasoning);
                                    scrollToBottomDelayed();
                                }
                            }
                        }

                        // Handle Reasoning Tokens
                        if (data.type === 'reasoning') {
                            if (!streamFrozen) {
                                aiReasoning += data.content || '';
                                updateStreamingContent(aiMsgDiv, aiContent, aiReasoning);
                                const reasoningWrapper = aiWrapper.querySelector('.reasoning-wrapper');
                                if (reasoningWrapper) reasoningWrapper.classList.add('is-reasoning-active');
                                scrollToBottomDelayed();
                            }
                        }

                        // NEW: Handle Streaming Tool Call Deltas (with safety check)
                        if (data.type === 'tool_call_delta' && Array.isArray(data.tool_calls)) {
                            for (const tc of data.tool_calls) {
                                handleStreamingToolCall(aiWrapper, tc);
                            }
                        }

                        // NEW: Handle Final Tool Call Signal
                        if (data.type === 'tool_calls') {
                            finalizeStreamingToolCall(aiWrapper);
                        }
                    }

                    // Handle New Turn
                    if (data.type === 'new_turn') {
                        currentTurnIndex++;
                        aiContent = ''; aiReasoning = ''; displayedContent = '';
                        if (!aiWrapper.querySelector('.turn-container')) {
                            aiMsgDiv.innerHTML = '<div class="turn-container current"></div>';
                        }
                        const prevTurns = streamingTurns.map(t => `<div class="assistant-turn">${renderMarkdown(t.content)}</div\>`).join('');
                        aiMsgDiv.innerHTML = prevTurns + '<div class="turn-container current"></div>';
                    }

                    // Handle Errors
                    if (data.error) {
                        streamHadError = true;
                        handleInlineError(data, aiMsgDiv, aiWrapper, streamStarted);
                    }

                    if (data.done) {
                        streamingTurns.push({ content: aiContent, reasoning: aiReasoning });
                    }

                } catch (e) { /* Ignore parse errors */ }
            }
        }
    } catch (err) {
        removePlaceholder();
        if (err.name !== 'AbortError') {
            console.log(err);
            streamHadError = true;
            typewriterQueue = [];
            handleCatchError(err, aiMsgDiv, aiWrapper, False);
        }
    } finally {
        // 10. Cleanup and Finalization
        isDataStreaming = false;

        if (window.upload_queue && window.upload_queue.files.length > 0) {
            window.upload_queue.wrappers.forEach(w => w.remove());
            window.upload_queue.files = [];
            window.upload_queue.wrappers = [];
            window.updateUploadQueueUI();
        }

        if (isTypewriterRunning) {
            await waitForTypewriter();
        }

        const reasoningWrapper = aiWrapper.querySelector('.reasoning-wrapper');
        if (reasoningWrapper && !reasoningWrapper.classList.contains('collapsed')) {
            reasoningWrapper.classList.add('collapsed');
            await new Promise(resolve => setTimeout(resolve, 300));
        }

        finishStream();

        if (!streamHadError) {
            aiWrapper.remove();
            await syncMessages();
        } else {
            aiWrapper.classList.remove('streaming');
            const actions = aiWrapper.querySelector('.message-actions');
            if (actions) actions.querySelectorAll('button').forEach(btn => btn.disabled = false);
        }

        try {
            const chatResponse = await fetch('/chat/current');
            const chatData = await chatResponse.json();
            if (chatData.success && chatData.chat) {
                currentChatId = chatData.chat.id;
                updateChatTitleBar(chatData.chat.title, chatData.chat.tags || []);
            }
        } catch (e) { console.error("Failed to update chat info", e); }

        await loadChats();
    }
}

// =============================================================================
// NEW OPTIMISTIC UI HELPERS
// =============================================================================

function createPlaceholderUserMessage(text) {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper user user-placeholder';

    const msgDiv = document.createElement('div');
    msgDiv.className = 'message user';

    const contentContainer = document.createElement('div');
    contentContainer.className = 'message-content-container';
    contentContainer.textContent = text;

    const status = document.createElement('div');
    status.className = 'placeholder-status';
    status.textContent = 'Sending...';

    msgDiv.appendChild(contentContainer);
    msgDiv.appendChild(status);
    wrapper.appendChild(msgDiv);

    return wrapper;
}

function removePlaceholder() {
    if (placeholderUserWrapper) {
        placeholderUserWrapper.remove();
        placeholderUserWrapper = null;
    }
}

function startStreamingUI(aiWrapper, typingIndicator) {
    typingIndicator.classList.remove('show');
    aiWrapper.classList.remove('hidden');
    return true;
}

async function handleServerError(response, aiWrapper) {
    let errorMsg = 'An unexpected error occurred.';
    let errorType = 'unknown';
    let action = '';

    // 1. Attempt to extract detailed error information from the response body
    try {
        const errorData = await response.json();
        // The backend sends 'error' as the message in some routes,
        // or 'error_type'/'action' in others.
        errorMsg = errorData.error || errorData.message || errorMsg;
        errorType = errorData.error_type || errorData.error || errorType;
        action = errorData.action || '';
    } catch (e) {
        // If response is not JSON, fall back to status-based messages
        if (response.status === 503) {
            errorMsg = 'API is not available.';
        } else if (response.status === 500) {
            errorMsg = 'Internal Server Error.';
        } else if (response.status === 401 || response.status === 403) {
            errorMsg = 'Authentication failed.';
            errorType = 'auth_failed';
        }
    }

    // 2. Display the error using the global UI config error handler
    // This ensures the user actually sees what went wrong.
    showApiConfigError(errorMsg, errorType, action);

    // 3. Cleanup UI state
    removePlaceholder();

    // Only attempt to remove aiWrapper if it has actually been added to the DOM
    if (aiWrapper && aiWrapper.parentNode) {
        aiWrapper.remove();
    }

    finishStream();
}


function handleInlineError(data, aiMsgDiv, aiWrapper, streamStarted) {
    if (!streamStarted) aiWrapper.classList.remove('hidden');

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
    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
    <span class="api-error-title">${escapeHtml(info.title)}</span>
    </div>
    <div class="api-error-message">${escapeHtml(errorMessage)}</div>
    ${info.action ?`<div class="api-error-action">${escapeHtml(info.action)}</div>` : ''}
    </div>`;
}

function handleCatchError(err, aiMsgDiv, aiWrapper, streamStarted) {
    if (!streamStarted) aiWrapper.classList.remove('hidden');
    aiMsgDiv.innerHTML = `
    <div class="api-error-inline">
    <div class="api-error-header">
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <circle cx="12" cy="12" r="10"/>
    <line x1="12" y1="8" x2="12" y2="12"/>
    <line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
    <span class="api-error-title">Connection Error</span>
    </div>
    <div class="api-error-message">${escapeHtml(err.message)}</div>
    <div class="api-error-action">Could not reach the server. Please check your connection.</div>
    </div>
    `;
}

/**
 * Helper to wait for the typewriter to finish via Promise.
 */
function waitForTypewriter() {
    return new Promise(resolve => {
        const interval = setInterval(() => {
            if (!isTypewriterRunning) {
                clearInterval(interval);
                resolve();
            }
        }, 20);
    });
}

async function startTypewriterProcess(msgDiv, reasoning) {
    isTypewriterRunning = true;

    const typewriterEnabled = localStorage.getItem("typewriterEnabled") !== 'false';
    if (!typewriterEnabled) {
        // Safety flush if disabled mid-stream
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
            // Wait briefly for more data to avoid spinning CPU.
            await new Promise(resolve => setTimeout(resolve, 20));
        }
    }

    // Play completion sound using AudioContext (CSP safe)
    TypewriterAudioManager.play('completion');

    isTypewriterRunning = false;
}

async function stopGeneration(sent_from_command = false) {
    // 1. Abort local fetch request
    if (currentController) {
        currentController.abort();
        currentController = null;
    }

    // 2. Notify backend to stop generating
    if (currentStreamId) {
        if (!sent_from_command) {
            // Notify backend logic that user stopped it
            fetch('/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ role: "user", content: "/stop" })
            });
        }
        try {
            await fetch('/cancel', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: currentStreamId })
            });
        } catch (e) {
            // Ignore network errors during cancellation
        }
        currentStreamId = null;
    }

    // 3. Force drain typewriter queue immediately
    // This prevents the UI from "hanging" with partial text if stopped mid-stream
    typewriterQueue = [];
    isDataStreaming = false;

    // 4. Sync UI state
    await syncMessages();
    finishStream();
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
    // 1. Handle Reasoning Block
    let reasoningWrapper = msgDiv.querySelector('.reasoning-wrapper');

    if (reasoning) {
        if (reasoningWrapper) {
            // Update content
            const contentDiv = reasoningWrapper.querySelector('.reasoning-content');
            if (contentDiv) {
                contentDiv.innerHTML = escapeHtml(reasoning);
            }

            // NEW: If main content has started streaming, change "Thinking" to "Thoughts"
            if (content) {
                const label = reasoningWrapper.querySelector('.reasoning-label');
                if (label && label.textContent === 'Thinking') {
                    label.textContent = 'Thoughts';
                }
            }
        } else {
            // Create new block (Note: we use 'Thinking' as default for the initial creation)
            const expandByDefault = localStorage.getItem('reasoningExpandedByDefault') === 'true';
            const isCollapsed = !expandByDefault;
            const reasoningHtml = renderReasoningBlock(reasoning, isCollapsed, 'Thinking');

            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = reasoningHtml;
            const newBlock = tempDiv.firstElementChild;

            msgDiv.insertBefore(newBlock, msgDiv.firstChild);
            reasoningWrapper = newBlock;
        }
    }

    // 2. Handle Main Content
    let contentContainer = msgDiv.querySelector('.message-content-container');

    if (content) {
        if (contentContainer) {
            // CONTENT EXISTS: Update only the markdown inside the container
            contentContainer.innerHTML = renderMarkdown(content);
        } else {
            // CONTENT NEW: Create a stable wrapper for the main content
            contentContainer = document.createElement('div');
            contentContainer.className = 'message-content-container';
            contentContainer.innerHTML = renderMarkdown(content);

            // Insert it after the reasoning block if it exists, otherwise at the start
            if (reasoningWrapper) {
                msgDiv.insertBefore(contentContainer, reasoningWrapper.nextSibling);
            } else {
                msgDiv.insertBefore(contentContainer, msgDiv.firstChild);
            }
        }
    }

    // 3. Post-update updates (Highlighting/Fade)
    // These work on the existing DOM elements now
    highlightCode(msgDiv);

    const fadeEnabled = localStorage.getItem('typewriterFadeEnabled') === 'true';
    if (fadeEnabled && content) {
        applyFastFade(msgDiv);
    }
}


/**
 * Optimized fade effect: wraps the last N characters in a single span
 * with a CSS gradient mask.
 */
function applyFastFade(rootElement) {
    const fadeLength = 8;

    // Find the deepest last text node in the DOM tree
    let lastTextNode = findLastTextNode(rootElement);

    if (!lastTextNode) return;

    const textContent = lastTextNode.textContent;
    const textLen = textContent.length;

    // Determine how many characters to fade
    const fadeCount = Math.min(fadeLength, textLen);

    if (fadeCount <= 0) return;

    // Split the text node at the boundary
    // Example: "Hello World" (fade 5) -> Split at length-5
    const splitIndex = textLen - fadeCount;

    // If splitIndex is 0, we fade the whole node.
    // If splitIndex > 0, we need to separate the stable part from the fade part.

    if (splitIndex > 0) {
        // Split the node: "Hello " (stable) and "World" (fade)
        lastTextNode.splitText(splitIndex);
        // Now lastTextNode is the stable part. The fade part is lastTextNode.nextSibling.
        // We want to wrap the *next* sibling.
        const fadeNode = lastTextNode.nextSibling;
        if (fadeNode) {
            const span = document.createElement('span');
            span.className = 'typewriter-fade';
            // Wrap the fade text node in the span
            fadeNode.parentNode.insertBefore(span, fadeNode);
            span.appendChild(fadeNode);
        }
    } else {
        // We fade the whole node (content is shorter than fadeLength)
        // We wrap the current lastTextNode itself.
        const span = document.createElement('span');
        span.className = 'typewriter-fade';
        lastTextNode.parentNode.insertBefore(span, lastTextNode);
        span.appendChild(lastTextNode);
    }
}

/**
 * Helper to find the last text node in a DOM tree (depth-first).
 */
function findLastTextNode(node) {
    if (node.nodeType === Node.TEXT_NODE) {
        // Skip empty whitespace nodes if they are the *only* thing,
        // but usually the last text node has content in a streaming message.
        if (node.textContent.trim().length === 0) return null;
        return node;
    }

    // Iterate children backwards to find the last meaningful node
    for (let i = node.childNodes.length - 1; i >= 0; i--) {
        const child = node.childNodes[i];
        const result = findLastTextNode(child);
        if (result) return result;
    }

    return null;
}

function finishStream() {
    removePlaceholder();
    setInputState(false, false, false);
    isStreaming = false;
    streamFrozen = false;
    currentController = null;
    currentStreamId = null;
    typewriterQueue = [];
    displayedContent = '';
    isTypewriterRunning = false;
    inputField.focus();
}
