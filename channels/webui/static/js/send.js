// =============================================================================
// Timing Statistics State
// =============================================================================
let currentTokensPerSecond = 0;
let promptProgress = null;
let totalPromptTokens = 0;
let totalGenTokens = 0;

// =============================================================================
// Main Send Function
// =============================================================================

async function send(providedContent = null) {
    const isRegenerate = providedContent !== null;
    const rawContent = providedContent !== null ? providedContent : inputField.value.trim();
    const message = typeof rawContent === 'string' ? rawContent : extractTextContent(rawContent);

    // block sending while a stream is ongoing
    if (isStreaming) return;

    // send commands using the non-streaming endpoint
    if (message.trim().startsWith('/') || message.trim().startsWith("STOP")) {
        clearInput();
        return sendCommand(message);
    }

    // allow send if typewriter is running but streaming has finished.
    // just skip the typing animations
    // makes you also able to skip by just pressing enter
    if (isTypewriterRunning) { await stopGeneration(); }

    // reject blank messages
    if (!message && !isRegenerate) return;

    if (!isRegenerate) {
        clearInput();
    }

    promptProcessingReceived = false;
    typewriterQueue = [];
    displayedContent = '';
    isTypewriterRunning = false;
    resetStreamState();

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

    currentController = new AbortController();

    // Update stop button to show streaming indicator when tokens start
    updateStopButtonState();

    let playedCompletionSound = false;

    let streamHadError = false;
    let streamStarted = false;

    const typewriterEnabled = localStorage.getItem("typewriterEnabled") === 'true';
    const typewriterSpeed = parseInt(localStorage.getItem("typewriterSpeed") ?? "30", 10);
    const useTypewriter = typewriterEnabled && typewriterSpeed > 0;
    const useStreamingSound = localStorage.getItem("tokenEnabled") === 'true';

    let progressBarFill = null;
    let progressTextPercent = null;
    let progressTextETA = null;

    scrollToBottom();

    // Send via WebSocket
    if (window.socket && window.socket.readyState === WebSocket.OPEN) {
        window.socket.send(JSON.stringify({
            type: 'user_message',
            content: payloadBody
        }));
    } else {
        // Socket not open — queue the message for later delivery
        safeSocketSend({
            type: 'user_message',
            content: payloadBody
        });
        // Show a brief notification that the message is queued
        showChatError('Message queued — will send when reconnected.');
    }
}

async function sendCommand(message) {
    try {
        if (message.startsWith("/stop") || message.startsWith("STOP")) {
            await stopGeneration(true);
        } else {
            // setInputState(true, true, true);

            const response = await fetch('/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({role: "user", content: message })
            });

            // setInputState(false, false, false);
        }
    } catch (err) {
        console.error('Command failed:', err);
    }
}

function renderStats(container, tps, genTokens) {
    // Format tokens per second
    const tpsText = tps > 0 ? tps.toFixed(2) : "0.00";

    container.innerHTML = `
    <div class="stat-badge">
    <span class="stat-value">${tpsText} t/s</span>
    </div>
    `;
}

// =============================================================================
// Optimistic UI Helpers
// =============================================================================

function createAiWrapper() {
    const aiWrapper = document.createElement('div');
    aiWrapper.className = 'message-wrapper ai hidden streaming';

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

    aiWrapper.classList.remove('hidden');

    window._currentAiWrapper = aiWrapper;
    window._currentAiMsgDiv = aiMsgDiv;
    window._currentUseTypewriter = localStorage.getItem("typewriterEnabled") === 'true';
    window._currentUseStreamingSound = localStorage.getItem("tokenEnabled") === 'true';

    if (fancyProcessingIndicator) {
        fancyProcessingIndicator.remove();
        fancyProcessingIndicator = null;
    }

    return aiWrapper;
}

function createPlaceholderUserMessage(text) {
    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper user user-placeholder animate-in';

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
