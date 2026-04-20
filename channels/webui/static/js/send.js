// =============================================================================
// Stream Segment State
// =============================================================================

let streamSegments = [];
let segCounter = 0;
let activeTypewriterSegId = -1;
let streamingToolCalls = {};
let toolCallsContainer = null;
let placeholderUserWrapper = null;

function resetStreamState() {
    streamSegments = [];
    segCounter = 0;
    activeTypewriterSegId = -1;
    clearStreamingToolCalls();
}

function appendStreamText(type, text, typewriterEnabled = true) {
    const last = streamSegments[streamSegments.length - 1];

    if (last && last.type === type) {
        last.text += text;
        if (type === 'content' && !typewriterEnabled) {
            last.displayed = last.text;
        }
    } else {
        // Finalize previous content segment
        if (last && last.type === 'content') {
            last.displayed = last.text;
            if (last.el) last.el.innerHTML = renderMarkdown(last.text);
            typewriterQueue = [];
        }

        const newSeg = {
            type,
            text,
            id: segCounter++,
            el: null,
            displayed: type === 'content' && !typewriterEnabled ? text : ''
        };

        if (type === 'content' && typewriterEnabled) {
            activeTypewriterSegId = newSeg.id;
        }

        streamSegments.push(newSeg);
    }
}

function ensureToolCallsSegment() {
    const last = streamSegments[streamSegments.length - 1];
    if (last && last.type === 'tool_calls') return last;

    if (last && last.type === 'content') {
        last.displayed = last.text;
        if (last.el) last.el.innerHTML = renderMarkdown(last.text);
        typewriterQueue = [];
    }

    const seg = { type: 'tool_calls', text: '', id: segCounter++, el: null };
    streamSegments.push(seg);
    return seg;
}

function finalizeAllContent() {
    for (const seg of streamSegments) {
        if (seg.type === 'content' && seg.displayed !== seg.text) {
            seg.displayed = seg.text;
            if (seg.el) seg.el.innerHTML = renderMarkdown(seg.text);
        }
    }
    typewriterQueue = [];
}

// =============================================================================
// Segment Rendering
// =============================================================================

function createSegmentElement(seg) {
    if (seg.type === 'reasoning') {
        const expandByDefault = localStorage.getItem('reasoningExpandedByDefault') === 'true';
        const temp = document.createElement('div');
        temp.innerHTML = renderReasoningBlock(seg.text, !expandByDefault, 'Thinking');
        const el = temp.firstElementChild;
        el.classList.add('is-reasoning-active');
        return el;
    }

    if (seg.type === 'content') {
        const el = document.createElement('div');
        el.className = 'message-content-container';
        return el;
    }

    if (seg.type === 'tool_calls') {
        const el = document.createElement('div');
        el.className = 'tool-calls-streaming-container';
        return el;
    }

    return document.createElement('div');
}

function renderStreamSegments(msgDiv, onlyUpdateLast = false) {
    for (let i = 0; i < streamSegments.length; i++) {
        const seg = streamSegments[i];

        if (!seg.el || !seg.el.parentNode) {
            seg.el = createSegmentElement(seg);
            msgDiv.appendChild(seg.el);
        }

        if (!onlyUpdateLast || i === streamSegments.length - 1) {
            updateSegmentContent(seg, i);
        }
    }

    highlightCode(msgDiv);
    scrollToBottomDelayed();
}

function updateSegmentContent(seg, index) {
    if (seg.type === 'reasoning') {
        const contentDiv = seg.el.querySelector('.reasoning-content');
        if (contentDiv) contentDiv.textContent = seg.text;

        const isLast = (index === streamSegments.length - 1);
        const nextSeg = isLast ? null : streamSegments[index + 1];
        const label = seg.el.querySelector('.reasoning-label');

        if (label) {
            const stillActive = isLast || (nextSeg && nextSeg.type === 'reasoning');
            label.textContent = stillActive ? 'Thinking' : 'Thoughts';
        }

        if (!isLast) {
            seg.el.classList.remove('is-reasoning-active');
            seg.el.classList.add('collapsed');
        }
        return;
    }

    if (seg.type === 'content') {
        const textToDisplay = seg.displayed !== undefined ? seg.displayed : seg.text;
        seg.el.innerHTML = renderMarkdown(textToDisplay);
    }
}

// =============================================================================
// Main Send Function
// =============================================================================

async function send(providedContent = null) {
    if (isStreaming) return;

    const isRegenerate = providedContent !== null;
    const rawContent = providedContent !== null ? providedContent : inputField.value.trim();
    const message = typeof rawContent === 'string' ? rawContent : extractTextContent(rawContent);

    if (!message && !isRegenerate) return;

    typewriterQueue = [];
    displayedContent = '';
    isTypewriterRunning = false;
    resetStreamState();

    if (!isRegenerate) {
        clearInput();
        if (message.trim().startsWith('/') || message.trim().startsWith("STOP")) {
            return sendCommand(message);
        }
    }

    if (!isRegenerate) {
        placeholderUserWrapper = createPlaceholderUserMessage(message);
        chat.insertBefore(placeholderUserWrapper, typing);
    }

    // Check API status
    try {
        const statusResponse = await fetch('/api/status', { signal: AbortSignal.timeout(5000) });
        if (statusResponse.ok) {
            const statusData = await statusResponse.json();
            if (!statusData.connected) {
                removePlaceholder();
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

    // Build payload
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

    setInputState(true, true, true);
    isStreaming = true;
    isDataStreaming = true;
    currentController = new AbortController();

    // Create AI wrapper
    const aiWrapper = document.createElement('div');
    aiWrapper.className = 'message-wrapper ai hidden streaming';
    aiWrapper.dataset.index = 'streaming';

    const aiMsgDiv = document.createElement('div');
    aiMsgDiv.className = 'message ai';
    aiWrapper.appendChild(aiMsgDiv);

    const aiActions = createActionButtons('assistant', 'streaming', '', true);
    aiWrapper.appendChild(aiActions);

    let streamHadError = false;
    let streamStarted = false;

    const typewriterEnabled = localStorage.getItem("typewriterEnabled") !== 'false';
    const typewriterSpeed = parseInt(localStorage.getItem("typewriterSpeed") ?? "30", 10);
    const useTypewriter = typewriterEnabled && typewriterSpeed > 0;

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

        if (window.upload_queue) {
            window.upload_queue.wrappers.forEach(w => w.remove());
            window.upload_queue.files = [];
            window.upload_queue.wrappers = [];
            window.updateUploadQueueUI();
        }

        chat.insertBefore(aiWrapper, typing);

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
                if (!line.startsWith('data: ')) continue;

                try {
                    const data = JSON.parse(line.slice(6));

                    // Handle metadata
                    if (data._meta) {
                        const { type: metaType } = data._meta;

                        if (metaType === 'commit') {
                            // Backend has finalized - preserve our UI, just sync indices
                            finalizeAllContent();
                            collapseFinishedReasoning(aiMsgDiv);
                            await finalizeStreamingUI(aiWrapper, aiMsgDiv);
                            return;
                        }

                        if (metaType === 'cancelled') {
                            aiWrapper.classList.remove('hidden');
                            aiMsgDiv.innerHTML = '<span style="color:#f88;">[Cancelled]</span>';
                            finishStream();
                            return;
                        }

                        if (metaType === 'error') {
                            handleInlineError(data, aiMsgDiv, aiWrapper, streamStarted);
                            finishStream();
                            return;
                        }
                    }

                    if (data.id) currentStreamId = data.id;

                    // Content streaming
                    if (data.type === 'content' || data.token) {
                        if (!streamStarted) {
                            removePlaceholder();
                            startStreamingUI(aiWrapper, typing);
                            streamStarted = true;
                        }
                        const token = data.content || data.token || '';
                        if (token) {
                            appendStreamText('content', token, useTypewriter);
                            if (useTypewriter) {
                                const activeSeg = streamSegments.find(s => s.id === activeTypewriterSegId);
                                if (activeSeg && activeSeg.type === 'content') {
                                    for (const char of token) {
                                        typewriterQueue.push({ segId: activeSeg.id, char });
                                    }
                                    if (!isTypewriterRunning) startTypewriterProcessSegments(aiMsgDiv);
                                }
                            } else {
                                renderStreamSegments(aiMsgDiv);
                            }
                        }
                    }

                    // Reasoning streaming
                    if (data.type === 'reasoning') {
                        const token = data.content || '';
                        if (token) {
                            if (!streamStarted) {
                                removePlaceholder();
                                startStreamingUI(aiWrapper, typing);
                                streamStarted = true;
                            }
                            appendStreamText('reasoning', token);
                            renderStreamSegments(aiMsgDiv);
                        }
                    }

                    // Tool call delta
                    if (data.type === 'tool_call_delta') {
                        if (!streamStarted) {
                            removePlaceholder();
                            startStreamingUI(aiWrapper, typing);
                            streamStarted = true;
                        }
                        ensureToolCallsSegment();
                        handleToolCallDelta(data, aiMsgDiv, aiWrapper);
                    }

                    // Tool response
                    if (data.type === 'tool') {
                        handleToolResponse(data, aiMsgDiv);
                    }

                    // Complete tool calls
                    if (data.type === 'tool_calls') {
                        const toolCalls = data.content || [];
                        finalizeStreamingToolCalls(toolCalls, aiMsgDiv);
                    }

                } catch (e) {
                    console.error("Error parsing stream line:", e, line);
                }
            }
        }
    } catch (err) {
        removePlaceholder();
        if (err.name !== 'AbortError') {
            streamHadError = true;
            typewriterQueue = [];
            handleCatchError(err, aiMsgDiv, aiWrapper, streamStarted);
        }
    } finally {
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

        // Only finalize if not already done via commit
        if (isStreaming) {
            finalizeAllContent();
            collapseFinishedReasoning(aiMsgDiv);
            await finalizeStreamingUI(aiWrapper, aiMsgDiv);
        }

        // Update chat info
        try {
            const chatResponse = await fetch('/chat/current');
            const chatData = await chatResponse.json();
            if (chatData.success && chatData.chat) {
                currentChatId = chatData.chat.id;
                updateChatTitleBar(chatData.chat.title, chatData.chat.tags || []);
            }
        } catch (e) {
            console.error("Failed to update chat info", e);
        }

        await loadChats();
    }
}

/**
 * Collapse reasoning blocks that are no longer active.
 */
function collapseFinishedReasoning(msgDiv) {
    const wrappers = msgDiv.querySelectorAll('.reasoning-wrapper');
    wrappers.forEach(wrapper => {
        wrapper.classList.remove('is-reasoning-active');
        wrapper.classList.add('collapsed');
    });
}

/**
 * Finalize streaming UI - preserve the rendered content, just update state.
 */
async function finalizeStreamingUI(aiWrapper, aiMsgDiv) {
    removePlaceholder();

    // Remove active states
    collapseFinishedReasoning(aiMsgDiv);

    // Enable buttons
    aiWrapper.classList.remove('streaming', 'hidden');
    const actions = aiWrapper.querySelector('.message-actions');
    if (actions) {
        actions.querySelectorAll('button').forEach(btn => btn.disabled = false);
    }

    // Clear streaming state
    clearStreamingToolCalls();

    // Reset stream state AFTER UI is finalized
    resetStreamState();

    setInputState(false, false, false);
    isStreaming = false;
    streamFrozen = false;
    currentController = null;
    currentStreamId = null;
    typewriterQueue = [];
    displayedContent = '';
    isTypewriterRunning = false;
    inputField.focus();

    // Sync to get proper indices, but don't re-render
    await syncIndicesOnly();
}

/**
 * Sync only message indices without re-rendering content.
 */
async function syncIndicesOnly() {
    try {
        const response = await fetch('/messages');
        const data = await response.json();
        const messages = data.messages || [];

        lastMessageIndex = messages.length;

        // Update indices on streaming wrappers
        const streamingWrappers = chat.querySelectorAll('.message-wrapper[data-index="streaming"]');
        streamingWrappers.forEach(wrapper => {
            wrapper.dataset.index = lastMessageIndex - 1;
        });

        updateTokenUsage();
    } catch (err) {
        console.error('Index sync failed:', err);
    }
}

function finishStream() {
    removePlaceholder();
    clearStreamingToolCalls();
    resetStreamState();
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

// =============================================================================
// Typewriter for Segments
// =============================================================================

let typewriterQueue = [];
let displayedContent = '';
let isTypewriterRunning = false;

async function startTypewriterProcessSegments(msgDiv) {
    isTypewriterRunning = true;

    const typewriterEnabled = localStorage.getItem("typewriterEnabled") !== 'false';
    if (!typewriterEnabled) {
        typewriterQueue = [];
        isTypewriterRunning = false;
        return;
    }

    const speed = parseInt(localStorage.getItem("typewriterSpeed") ?? "30", 10);

    while (typewriterQueue.length > 0 || isDataStreaming) {
        if (typewriterQueue.length > 0) {
            const item = typewriterQueue.shift();
            const seg = streamSegments.find(s => s.id === item.segId);

            if (seg && seg.type === 'content') {
                seg.displayed = (seg.displayed || '') + item.char;
                renderStreamSegments(msgDiv, true);
                scrollToBottomDelayed();

                if (item.char.trim() !== '') {
                    TypewriterAudioManager.play('typewriter');
                }
            }

            await new Promise(resolve => setTimeout(resolve, speed));
        } else {
            await new Promise(resolve => setTimeout(resolve, 20));
        }
    }

    TypewriterAudioManager.play('completion');
    isTypewriterRunning = false;
}

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


// =============================================================================
// Optimistic UI Helpers
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

// =============================================================================
// Error Handlers
// =============================================================================

async function handleServerError(response, aiWrapper) {
    let errorMsg = 'An unexpected error occurred.';
    let errorType = 'unknown';
    let action = '';

    try {
        const errorData = await response.json();
        errorMsg = errorData.error || errorData.message || errorMsg;
        errorType = errorData.error_type || errorData.error || errorType;
        action = errorData.action || '';
    } catch (e) {
        if (response.status === 503) {
            errorMsg = 'API is not available.';
        } else if (response.status === 500) {
            errorMsg = 'Internal Server Error.';
        } else if (response.status === 401 || response.status === 403) {
            errorMsg = 'Authentication failed.';
            errorType = 'auth_failed';
        }
    }

    showApiConfigError(errorMsg, errorType, action);
    removePlaceholder();

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
    ${info.action ? `<div class="api-error-action">${escapeHtml(info.action)}</div>` : ''}
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
    </div>`;
}

// =============================================================================
// Stop Generation
// =============================================================================

async function stopGeneration(sent_from_command = false) {
    // Abort local fetch
    if (currentController) {
        currentController.abort();
        currentController = null;
    }

    // Notify backend
    if (currentStreamId) {
        if (!sent_from_command) {
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

    // Force drain typewriter
    typewriterQueue = [];
    isDataStreaming = false;

    // Finalize all content segments so nothing is hidden
    finalizeAllContent();

    // Sync UI
    await syncMessages();
    finishStream();
}

// =============================================================================
// Tool Call Streaming Handlers
// =============================================================================

/**
 * Handle incoming tool_call_delta tokens during streaming.
 */
function handleToolCallDelta(data, aiMsgDiv, aiWrapper) {
    const toolCalls = data.tool_calls;
    if (!toolCalls || toolCalls.length === 0) return;

    // Ensure tool_calls container element exists in the segment
    const tcSeg = ensureToolCallsSegment();

    // Create container element if needed
    if (!tcSeg.el || !tcSeg.el.parentNode) {
        tcSeg.el = document.createElement('div');
        tcSeg.el.className = 'tool-calls-streaming-container';
        aiMsgDiv.appendChild(tcSeg.el);
    }

    toolCallsContainer = tcSeg.el;

    for (const tc of toolCalls) {
        const index = tc.index !== undefined ? tc.index : 0;
        const id = tc.id;
        const funcName = tc.function?.name;
        const funcArgs = tc.function?.arguments || '';

        // Initialize or update streaming tool call
        if (!streamingToolCalls[index]) {
            streamingToolCalls[index] = {
                id: id || `tc-stream-${index}`,
                function: { name: funcName || '', arguments: '' }
            };
        }

        if (id) streamingToolCalls[index].id = id;
        if (funcName) streamingToolCalls[index].function.name = funcName;
        if (funcArgs) streamingToolCalls[index].function.arguments += funcArgs;

        renderStreamingToolCall(index, streamingToolCalls[index], aiMsgDiv);
    }
}

/**
 * Render or update a streaming tool call card.
 */
function renderStreamingToolCall(index, toolCall, aiMsgDiv) {
    const callId = toolCall.id || `stream-tc-${index}`;
    let cardEl = toolCallsContainer.querySelector(`[data-stream-tc-id="${callId}"]`);

    const funcName = toolCall.function?.name || 'Calling...';
    const rawArgs = toolCall.function?.arguments || '{}';

    let argsDisplay = {};
    let parseError = false;
    try {
        argsDisplay = parsePartialJson(rawArgs);
    } catch (e) {
        parseError = true;
        argsDisplay = { _raw: rawArgs };
    }

    if (!cardEl) {
        cardEl = document.createElement('div');
        cardEl.className = 'tool-call-card streaming collapsed';
        cardEl.dataset.streamTcId = callId;
        cardEl.dataset.index = index;

        cardEl.innerHTML = `
        <div class="tool-call-header" onclick="toggleToolCard(this)">
        <svg class="tool-call-toggle" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="9 18 15 12 9 6"></polyline>
        </svg>
        <svg class="tool-call-icon" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
        </svg>
        <span class="tool-call-name">${escapeHtml(funcName)}</span>
        <span class="tool-call-arg-count"></span>
        <span class="tool-call-status streaming">
        <span class="streaming-dots"><span>.</span><span>.</span><span>.</span></span>
        </span>
        </div>
        <div class="tool-call-body">
        <div class="tool-call-section">
        <div class="tool-call-section-title">Arguments</div>
        <div class="tool-call-args"></div>
        </div>
        <div class="tool-call-section tool-response-section" style="display: none;">
        <div class="tool-call-section-title">Response</div>
        <div class="tool-response-content"></div>
        </div>
        </div>`;

        // Insert in index order
        const existingCards = toolCallsContainer.querySelectorAll('.tool-call-card');
        let inserted = false;
        for (const existing of existingCards) {
            if (parseInt(existing.dataset.index) > index) {
                toolCallsContainer.insertBefore(cardEl, existing);
                inserted = true;
                break;
            }
        }
        if (!inserted) toolCallsContainer.appendChild(cardEl);
    } else {
        const nameEl = cardEl.querySelector('.tool-call-name');
        if (nameEl && funcName && funcName !== 'Calling...') {
            nameEl.textContent = funcName;
        }
    }

    // Update arguments
    const argsContainer = cardEl.querySelector('.tool-call-args');
    if (argsContainer) {
        argsContainer.innerHTML = renderStreamingArgs(argsDisplay, rawArgs, parseError);
    }

    // Update arg count badge
    const argCountEl = cardEl.querySelector('.tool-call-arg-count');
    if (argCountEl) {
        const entries = Object.entries(argsDisplay).filter(([k]) => k !== '_raw');
        if (entries.length === 1) {
            const [argName, argValue] = entries[0];
            let displayValue = typeof argValue === 'object' ? JSON.stringify(argValue) : String(argValue);
            if (displayValue.length > 50) displayValue = displayValue.substring(0, 50) + '...';
            argCountEl.className = 'tool-call-arg-count inline';
            argCountEl.innerHTML = `<span class="tool-call-inline-arg">${escapeHtml(displayValue)}</span>`;
        } else if (entries.length > 1) {
            argCountEl.className = 'tool-call-arg-count';
            argCountEl.textContent = entries.length;
        } else {
            argCountEl.innerHTML = '';
        }
    }
}

/**
 * Parse partial/incomplete JSON for display.
 */
function parsePartialJson(str) {
    if (!str || !str.trim()) return {};
    try {
        return JSON.parse(str);
    } catch (e) {
        // Continue to recovery
    }

    let result = {};
    const keyValueRegex = /"([^"]+)"\s*:\s*("[^"]*"|[\d.]+|true|false|null|\[[^\]]*\]|\{[^}]*\})/g;
    let match;
    while ((match = keyValueRegex.exec(str)) !== null) {
        const key = match[1];
        let value = match[2];
        try {
            result[key] = JSON.parse(value);
        } catch (e) {
            result[key] = value;
        }
    }
    return result;
}

/**
    * Render arguments for a streaming tool call.
    */
function renderStreamingArgs(args, rawArgs, parseError) {
    const entries = Object.entries(args).filter(([k]) => k !== '_raw');

    if (entries.length === 0) {
        return `<div class="tool-call-args-streaming">
        <span class="tool-call-args-raw">${escapeHtml(rawArgs)}</span>
        <span class="streaming-cursor">▌</span>
        </div>`;
    }

    let html = '';
    for (const [argName, argValue] of entries) {
        let displayValue = typeof argValue === 'object' ? JSON.stringify(argValue) : String(argValue);
        html += `
        <div class="tool-call-arg-row">
        <span class="tool-call-arg-name">${escapeHtml(argName)}</span>
        <span class="tool-call-arg-value">${escapeHtml(displayValue)}</span>
        </div>`;
    }

    if (parseError && rawArgs.length > 0) {
        html += `<div class="tool-call-arg-row partial">
        <span class="tool-call-arg-name">...</span>
        <span class="tool-call-arg-value streaming">${escapeHtml(rawArgs.slice(-50))}<span class="streaming-cursor">▌</span></span>
        </div>`;
    }

    return html;
}

/**
    * Finalize streaming tool calls when complete tool_calls token arrives.
    */
function finalizeStreamingToolCalls(finalToolCalls, aiMsgDiv) {
    if (!toolCallsContainer) return;

    const cards = toolCallsContainer.querySelectorAll('.tool-call-card');
    cards.forEach(card => {
        card.classList.remove('streaming');
        const status = card.querySelector('.tool-call-status');
        if (status) {
            status.classList.remove('streaming');
            status.classList.add('pending');
            status.textContent = 'calling...';
        }
    });

    // Update IDs to match final tool calls
    finalToolCalls.forEach((tc, idx) => {
        const finalId = tc.id || `tool-${idx}`;
        const card = toolCallsContainer.querySelector(`[data-stream-tc-id]`);
        if (card) {
            card.dataset.toolCallId = finalId;
        }
    });
}

/**
    * Handle tool during streaming.
    */
function handleToolResponse(data, aiMsgDiv) {
    const toolCallId = data.tool_call_id;
    const content = data.content || '';

    let cardEl = null;
    if (toolCallsContainer) {
        cardEl = toolCallsContainer.querySelector(`[data-tool-call-id="${toolCallId}"]`);
        if (!cardEl) {
            cardEl = toolCallsContainer.querySelector(`[data-stream-tc-id="${toolCallId}"]`);
        }
    }

    if (cardEl) {
        const status = cardEl.querySelector('.tool-call-status');
        if (status) {
            status.classList.remove('streaming', 'pending');
            status.classList.add('completed');
            status.textContent = 'done';
        }

        const responseSection = cardEl.querySelector('.tool-response-section');
        const responseContent = cardEl.querySelector('.tool-response-content');
        if (responseSection && responseContent) {
            responseSection.style.display = 'block';
            responseContent.innerHTML = renderToolResponseContent(content);
        }
    }
}

/**
    * Clear streaming tool call state.
    */
function clearStreamingToolCalls() {
    streamingToolCalls = {};
    toolCallsContainer = null;
}

// =============================================================================
// Utility: Apply Fast Fade Effect
// =============================================================================

function applyFastFade(rootElement) {
    // Modified to be non-destructive. Instead of splitting text nodes (which breaks on next innerHTML update),
    // we just apply a class that can be handled via CSS.
    rootElement.classList.add('typewriter-fade-active');
    setTimeout(() => {
        rootElement.classList.remove('typewriter-fade-active');
    }, 500);
}

function findLastTextNode(node) {
    if (node.nodeType === Node.TEXT_NODE) {
        if (node.textContent.trim().length === 0) return null;
        return node;
    }

    for (let i = node.childNodes.length - 1; i >= 0; i--) {
        const child = node.childNodes[i];
        const result = findLastTextNode(child);
        if (result) return result;
    }
    return null;
}
