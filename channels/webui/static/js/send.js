// =============================================================================
// Stream Segment State
// =============================================================================

let streamSegments = [];
let segCounter = 0;
let activeTypewriterSegId = -1;
let streamingToolCalls = {};
let toolCallsContainer = null;
let placeholderUserWrapper = null;
let manuallyCollapsedReasoning = new Set();

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

        // Update token usage on every segment type transition (reasoning/content/tool_calls finished)
        updateTokenUsage();

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
    updateTokenUsage();
}

// =============================================================================
// Segment Rendering
// =============================================================================

function createSegmentElement(seg) {
    if (seg.type === 'reasoning') {
        const expandByDefault = localStorage.getItem('reasoningExpandedByDefault') === 'true';

        // Generate unique ID for this reasoning block
        const reasoningId = `reasoning-${seg.id}`;

        // Check if user manually collapsed this block
        const userCollapsed = manuallyCollapsedReasoning.has(reasoningId);
        const shouldCollapse = userCollapsed || !expandByDefault;

        const temp = document.createElement('div');
        temp.innerHTML = renderReasoningBlock(seg.text, shouldCollapse, 'Thinking');
        const el = temp.firstElementChild;
        el.classList.add('is-reasoning-active');
        el.dataset.reasoningId = reasoningId;
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

            // Only collapse if user hasn't manually expanded it
            const reasoningId = seg.el.dataset.reasoningId;
            if (!manuallyCollapsedReasoning.has(reasoningId)) {
                const expandByDefault = localStorage.getItem('reasoningExpandedByDefault') === 'true';
                if (!expandByDefault) {
                    seg.el.classList.add('collapsed');
                }
            }
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
                            // Signal that data streaming is complete so the typewriter can finish
                            isDataStreaming = false;
                            // Wait for typewriter to finish before finalizing
                            if (isTypewriterRunning) {
                                await waitForTypewriter();
                            }
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
                            // Clear processing indicators when content starts
                            clearProcessingIndicators();

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
                            // Clear processing indicators when reasoning starts
                            clearProcessingIndicators();

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

                    // Token usage updates (from API)
                    if (data.type === 'token_usage') {
                        updateTokenUsage();
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
        const reasoningId = wrapper.dataset.reasoningId;

        // Don't collapse if user manually expanded it during streaming
        if (manuallyCollapsedReasoning.has(reasoningId)) {
            // Keep it collapsed - user wanted it that way
            return;
        }

        // Check localStorage for default behavior
        const expandByDefault = localStorage.getItem('reasoningExpandedByDefault') === 'true';

        wrapper.classList.remove('is-reasoning-active');

        if (!expandByDefault) {
            wrapper.classList.add('collapsed');
        }
    });
}

/**
 * Finalize streaming UI - preserve the rendered content, just update state.
 */
async function finalizeStreamingUI(aiWrapper, aiMsgDiv) {
    removePlaceholder();

    // Remove active states
    collapseFinishedReasoning(aiMsgDiv);

    // Clear any remaining processing indicators
    clearProcessingIndicators();

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
    updateTokenUsage();
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

    const tcSeg = ensureToolCallsSegment();

    if (!tcSeg.el || !tcSeg.el.parentNode) {
        tcSeg.el = document.createElement('div');
        tcSeg.el.className = 'tool-calls-streaming-container';
        aiMsgDiv.appendChild(tcSeg.el);
    }

    toolCallsContainer = tcSeg.el;

    // Stop reasoning pulsing when tool calls start streaming
    const activeReasoning = aiMsgDiv.querySelectorAll('.reasoning-wrapper.is-reasoning-active');
    activeReasoning.forEach(wrapper => {
        wrapper.classList.remove('is-reasoning-active');
    });

    for (const tc of toolCalls) {
        const index = tc.index !== undefined ? tc.index : 0;
        const id = tc.id;
        const funcName = tc.function?.name;
        const funcArgs = tc.function?.arguments || '';

        // Initialize streaming tool call if needed
        if (!streamingToolCalls[index]) {
            streamingToolCalls[index] = {
                id: id || `tc-stream-${index}`,
                function: { name: funcName || '', arguments: '' },
                // Track per-key printed values like the CLI does
                _printedValues: {}
            };
        }

        if (id) streamingToolCalls[index].id = id;
        if (funcName) streamingToolCalls[index].function.name = funcName;

        // The backend sends accumulated arguments string
        // We just use it directly - no += accumulation needed
        streamingToolCalls[index].function.arguments = funcArgs;

        renderStreamingToolCall(index, streamingToolCalls[index], aiMsgDiv);
    }
}

/**
 * Parse accumulated JSON, handling incomplete JSON gracefully.
 */
function parseAccumulatedJson(argsStr) {
    if (!argsStr || !argsStr.trim()) {
        return { parsed: {}, raw: argsStr };
    }

    // Try complete JSON first
    try {
        const parsed = JSON.parse(argsStr);
        return { parsed, raw: argsStr, complete: true };
    } catch (e) {
        // Not complete - try json_repair style parsing
    }

    // Parse key-value pairs from incomplete JSON
    const result = {};

    // Match string keys and their values (strings, numbers, bools, null, arrays, objects)
    // This regex captures: "key": value where value can be many forms
    const keyValuePattern = /"([^"\\]*(?:\\.[^"\\]*)*)"\s*:\s*/g;
    let match;

    while ((match = keyValuePattern.exec(argsStr)) !== null) {
        const key = match[1];
        const valueStart = keyValuePattern.lastIndex;

        // Extract the value starting from valueStart
        const value = extractJsonValue(argsStr, valueStart);
        if (value !== null) {
            result[key] = value.parsed;
        }
    }

    return { parsed: result, raw: argsStr, complete: false };
}

/**
 * Extract a JSON value starting at a given position.
 * Returns { parsed: value, end: position after value }
 */
function extractJsonValue(str, start) {
    let i = start;

    // Skip whitespace
    while (i < str.length && /\s/.test(str[i])) i++;
    if (i >= str.length) return { parsed: null, end: i, incomplete: true };

    const c = str[i];

    // String
    if (c === '"') {
        let j = i + 1;
        while (j < str.length) {
            if (str[j] === '\\' && j + 1 < str.length) {
                j += 2;
                continue;
            }
            if (str[j] === '"') {
                // Complete string
                try {
                    return { parsed: JSON.parse(str.slice(i, j + 1)), end: j + 1 };
                } catch (e) {
                    return { parsed: str.slice(i + 1, j), end: j + 1 };
                }
            }
            j++;
        }
        // Incomplete string - return what we have
        return { parsed: str.slice(i + 1, j), end: j, incomplete: true };
    }

    // Array
    if (c === '[') {
        let depth = 1;
        let j = i + 1;
        let inString = false;

        while (j < str.length && depth > 0) {
            const ch = str[j];
            if (ch === '"' && str[j - 1] !== '\\') inString = !inString;
            else if (!inString) {
                if (ch === '[') depth++;
                else if (ch === ']') depth--;
            }
            j++;
        }

        const arrStr = str.slice(i, j);
        try {
            return { parsed: JSON.parse(arrStr), end: j };
        } catch (e) {
            // Try to parse incomplete array
            try {
                return { parsed: JSON.parse(arrStr + ']'), end: j };
            } catch (e2) {
                return { parsed: arrStr, end: j, incomplete: true };
            }
        }
    }

    // Object
    if (c === '{') {
        let depth = 1;
        let j = i + 1;
        let inString = false;

        while (j < str.length && depth > 0) {
            const ch = str[j];
            if (ch === '"' && str[j - 1] !== '\\') inString = !inString;
            else if (!inString) {
                if (ch === '{') depth++;
                else if (ch === '}') depth--;
            }
            j++;
        }

        const objStr = str.slice(i, j);
        try {
            return { parsed: JSON.parse(objStr), end: j };
        } catch (e) {
            try {
                return { parsed: JSON.parse(objStr + '}'), end: j };
            } catch (e2) {
                return { parsed: objStr, end: j, incomplete: true };
            }
        }
    }

    // Number
    if (c === '-' || /[0-9]/.test(c)) {
        let j = i;
        while (j < str.length && /[0-9.eE+-]/.test(str[j])) j++;
        const numStr = str.slice(i, j);
        const num = parseFloat(numStr);
        return { parsed: isNaN(num) ? numStr : num, end: j };
    }

    // Boolean
    if (str.slice(i, i + 4) === 'true') return { parsed: true, end: i + 4 };
    if (str.slice(i, i + 5) === 'false') return { parsed: false, end: i + 5 };

    // Null
    if (str.slice(i, i + 4) === 'null') return { parsed: null, end: i + 4 };

    // Unknown - scan until delimiter
    let j = i;
    while (j < str.length && !/[,}\]]/.test(str[j])) j++;
    return { parsed: str.slice(i, j).trim(), end: j, incomplete: true };
}

/**
 * Render or update a streaming tool call card.
 */
function renderStreamingToolCall(index, toolCall, aiMsgDiv) {
    const callId = toolCall.id || `stream-tc-${index}`;
    let cardEl = toolCallsContainer.querySelector(`[data-stream-tc-id="${callId}"]`);

    const funcName = toolCall.function?.name || 'Calling...';
    const rawArgs = toolCall.function?.arguments || '';

    // Track per-key printed values (like CLI does)
    const printedValues = toolCall._printedValues || {};

    // Parse the accumulated JSON
    const { parsed: argsDisplay, complete } = parseAccumulatedJson(rawArgs);

    if (!cardEl) {
        cardEl = document.createElement('div');
        cardEl.className = 'tool-call-card streaming';
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

    // Update arguments display
    const argsContainer = cardEl.querySelector('.tool-call-args');
    if (argsContainer) {
        const entries = Object.entries(argsDisplay);

        if (entries.length === 0 && !rawArgs) {
            argsContainer.innerHTML = `<div class="tool-call-no-args">No arguments</div>`;
        } else if (entries.length === 0) {
            // Still streaming, show raw with cursor
            argsContainer.innerHTML = `<div class="tool-call-args-streaming">
            <span class="tool-call-args-raw">${escapeHtml(rawArgs ? rawArgs.replace(/\\n/g, '\n') : '')}</span>
            </div>`;
        } else {
            let html = '';
            for (const [argName, argValue] of entries) {
                // Convert value to string for comparison
                let valStr;
                if (typeof argValue === 'object' && argValue !== null) {
                    valStr = JSON.stringify(argValue);
                } else {
                    valStr = String(argValue);
                }
                valStr = valStr.replace(/\\n/g, '\n');

                // Track per-key printed values like CLI does
                const previouslyPrinted = printedValues[argName] || '';

                // Determine what's new
                let displayVal;
                if (valStr.startsWith(previouslyPrinted)) {
                    // Accumulated mode: value grew, show only new part
                    displayVal = valStr;
                } else {
                    // Value changed completely (e.g., type change, array -> object)
                    displayVal = valStr;
                }

                // Store the full accumulated value for next comparison
                printedValues[argName] = valStr;

                html += `
                <div class="tool-call-arg-row">
                <span class="tool-call-arg-name">${escapeHtml(argName)}</span>
                <span class="tool-call-arg-value">${escapeHtml(displayVal)}</span>
                </div>`;
            }

            argsContainer.innerHTML = html;
        }
    }

    // Update arg count badge
    const argCountEl = cardEl.querySelector('.tool-call-arg-count');
    if (argCountEl) {
        const entries = Object.entries(argsDisplay);
        if (entries.length === 1) {
            const [argName, argValue] = entries[0];
            let displayValue = typeof argValue === 'object' ? JSON.stringify(argValue) : String(argValue);
            displayValue = displayValue.replace(/\\n/g, '\n');
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

    scrollToBottom();
}


/**
 * Parse partial/incomplete JSON for display.
 */
function parsePartialJson(str) {
    if (!str || !str.trim()) return {};

    // Try complete JSON first
    try {
        const parsed = JSON.parse(str);
        if (typeof parsed === 'object' && parsed !== null) {
            return parsed;
        }
        return { value: parsed };
    } catch (e) {
        // Not complete JSON - try partial parsing
    }

    const result = {};

    // Track brace/bracket depth for nested structures
    const extractValue = (start, s) => {
        let i = start;
        const firstChar = s[i];

        // Skip whitespace
        while (i < s.length && /\s/.test(s[i])) i++;
        if (i >= s.length) return { value: null, end: i };

        const c = s[i];

        // String
        if (c === '"') {
            let j = i + 1;
            while (j < s.length) {
                if (s[j] === '\\' && j + 1 < s.length) {
                    j += 2;
                    continue;
                }
                if (s[j] === '"') break;
                j++;
            }
            return { value: s.slice(i + 1, j), end: j + 1, incomplete: j >= s.length };
        }

        // Array
        if (c === '[') {
            let depth = 1;
            let j = i + 1;
            while (j < s.length && depth > 0) {
                if (s[j] === '[') depth++;
                else if (s[j] === ']') depth--;
                else if (s[j] === '"') {
                    j++;
                    while (j < s.length) {
                        if (s[j] === '\\' && j + 1 < s.length) { j += 2; continue; }
                        if (s[j] === '"') break;
                        j++;
                    }
                }
                j++;
            }
            const arrStr = s.slice(i, j);
            let parsedArr;
            try {
                parsedArr = JSON.parse(arrStr + (depth > 0 ? ']' : ''));
            } catch (e) {
                try {
                    parsedArr = JSON.parse(arrStr);
                } catch (e2) {
                    return { value: arrStr, end: j, incomplete: depth > 0 };
                }
            }
            return { value: parsedArr, end: j, incomplete: depth > 0 };
        }

        // Object
        if (c === '{') {
            let depth = 1;
            let j = i + 1;
            while (j < s.length && depth > 0) {
                if (s[j] === '{') depth++;
                else if (s[j] === '}') depth--;
                else if (s[j] === '"') {
                    j++;
                    while (j < s.length) {
                        if (s[j] === '\\' && j + 1 < s.length) { j += 2; continue; }
                        if (s[j] === '"') break;
                        j++;
                    }
                }
                j++;
            }
            const objStr = s.slice(i, j);
            let parsedObj;
            try {
                parsedObj = JSON.parse(objStr + (depth > 0 ? '}' : ''));
            } catch (e) {
                try {
                    parsedObj = JSON.parse(objStr);
                } catch (e2) {
                    return { value: objStr, end: j, incomplete: depth > 0 };
                }
            }
            return { value: parsedObj, end: j, incomplete: depth > 0 };
        }

        // Number
        if (c === '-' || /\d/.test(c)) {
            let j = i;
            while (j < s.length && /[\d.+-eE]/.test(s[j])) j++;
            const numStr = s.slice(i, j);
            const num = parseFloat(numStr);
            return { value: isNaN(num) ? numStr : num, end: j };
        }

        // Boolean/null
        if (s.slice(i, i + 4) === 'true') return { value: true, end: i + 4 };
        if (s.slice(i, i + 5) === 'false') return { value: false, end: i + 5 };
        if (s.slice(i, i + 4) === 'null') return { value: null, end: i + 4 };

        // Unknown - return rest as string
        let j = i;
        while (j < s.length && !/[,}\]]/.test(s[j])) j++;
        return { value: s.slice(i, j).trim(), end: j };
    };

    // Parse key-value pairs
    let i = 0;
    const s = str.trim();
    if (s[0] === '{') i = 1;

    while (i < s.length) {
        // Skip whitespace
        while (i < s.length && /\s/.test(s[i])) i++;
        if (i >= s.length) break;

        // Find key
        if (s[i] !== '"') { i++; continue; }
        let keyEnd = i + 1;
        while (keyEnd < s.length) {
            if (s[keyEnd] === '\\' && keyEnd + 1 < s.length) { keyEnd += 2; continue; }
            if (s[keyEnd] === '"') break;
            keyEnd++;
        }
        const key = s.slice(i + 1, keyEnd);
        i = keyEnd + 1;

        // Skip to colon
        while (i < s.length && s[i] !== ':') i++;
        if (i >= s.length) break;
        i++;

        // Skip whitespace
        while (i < s.length && /\s/.test(s[i])) i++;
        if (i >= s.length) break;

        // Extract value
        const valueResult = extractValue(i, s);
        if (key) {
            result[key] = valueResult.value;
        }
        i = valueResult.end;

        // Skip comma
        while (i < s.length && s[i] !== ',' && s[i] !== '}') i++;
        if (s[i] === ',') i++;
    }

    return result;
}

/**
    * Render arguments for a streaming tool call.
    */
function renderStreamingArgs(args, rawArgs, parseError) {
    const entries = Object.entries(args);

    if (entries.length === 0 && !rawArgs) {
        return `<div class="tool-call-no-args">No arguments</div>`;
    }

    if (entries.length === 0) {
        return `<div class="tool-call-args-streaming">
        <span class="tool-call-args-raw">${escapeHtml(rawArgs ? rawArgs.replace(/\\n/g, '\n') : '')}</span>
        </div>`;
    }

    let html = '';
    for (const [argName, argValue] of entries) {
        let displayValue;
        if (typeof argValue === 'object' && argValue !== null) {
            displayValue = JSON.stringify(argValue);
        } else {
            displayValue = String(argValue);
        }
        displayValue = displayValue.replace(/\\n/g, '\n');
        html += `
        <div class="tool-call-arg-row">
        <span class="tool-call-arg-name">${escapeHtml(argName)}</span>
        <span class="tool-call-arg-value">${escapeHtml(displayValue)}</span>
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
        // FIX: Only reset cards that are currently in the 'streaming' state.
        // If the card is already 'completed', leave it alone!
        if (card.classList.contains('streaming')) {
            card.classList.remove('streaming');
            const status = card.querySelector('.tool-call-status');
            if (status) {
                status.classList.remove('streaming');
                status.classList.add('pending');
                status.textContent = 'calling...';
            }
        }
    });

    finalToolCalls.forEach((tc) => {
        const finalId = tc.id || `tool-unknown`;
        const streamId = tc.id || (tc.index !== undefined ? `tc-stream-${tc.index}` : null);

        let card = null;
        if (streamId) {
            card = toolCallsContainer.querySelector(`[data-stream-tc-id="${streamId}"]`);
        }

        if (!card && tc.index !== undefined) {
            card = toolCallsContainer.querySelector(`[data-index="${tc.index}"]`);
        }

        if (card) {
            card.dataset.toolCallId = finalId;
        }
    });

    updateTokenUsage();
}


/**
 * Handle tool response during streaming.
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

        cardEl.classList.add('collapsed');

        const responseSection = cardEl.querySelector('.tool-response-section');
        const responseContent = cardEl.querySelector('.tool-response-content');
        if (responseSection && responseContent) {
            responseSection.style.display = 'block';
            responseContent.innerHTML = renderToolResponseContent(content);
        }

        // Ensure the processing result indicator is always at the bottom
        addProcessingIndicator(cardEl);

        scrollToBottom();
    }

    // Always update token usage when a tool response arrives, as execution consumes tokens
    updateTokenUsage();
}

/**
 * Add a "processing result..." indicator below a tool call card.
 */
function addProcessingIndicator(cardEl) {
    // Remove any existing processing indicator from the container first
    if (toolCallsContainer) {
        const existing = toolCallsContainer.querySelector('.tool-processing-indicator');
        if (existing) existing.remove();
    }

    const indicator = document.createElement('div');
    indicator.className = 'tool-processing-indicator';
    indicator.innerHTML = `
    <div class="tool-processing-content">
    <svg class="tool-processing-spinner" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <path d="M21 12a9 9 0 11-6.219-8.56"/>
    </svg>
    <span class="tool-processing-text">processing result...</span>
    </div>
    `;

    // Always append to the very end of the tool calls container
    if (toolCallsContainer) {
        toolCallsContainer.appendChild(indicator);
    }
}

/**
 * Remove all processing indicators from the streaming container.
 */
function clearProcessingIndicators() {
    if (!toolCallsContainer) return;

    const indicators = toolCallsContainer.querySelectorAll('.tool-processing-indicator');
    indicators.forEach(ind => ind.remove());
}

/**
 * Clear streaming tool call state.
 */
function clearStreamingToolCalls() {
    streamingToolCalls = {};
    toolCallsContainer = null;
    clearProcessingIndicators();
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
