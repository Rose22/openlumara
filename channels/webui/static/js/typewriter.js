// =============================================================================
// Typewriter for Segments
// =============================================================================

let typewriterQueue = [];
let displayedContent = '';
let isTypewriterRunning = false;

async function startTypewriterProcessSegments(msgDiv) {
    isTypewriterRunning = true;
    // Update button state now that typewriter has started
    updateStopButtonState();

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
                    TypewriterAudioManager.play('typing');
                }
            }

            await new Promise(resolve => setTimeout(resolve, speed));
        } else {
            await new Promise(resolve => setTimeout(resolve, 20));
        }
    }

    TypewriterAudioManager.play('completion');
    isTypewriterRunning = false;
    // Update stop button state back to "Stop" when typewriter finishes
    updateStopButtonState();
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
