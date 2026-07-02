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

    logContent.innerHTML = '';

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
    const btn = document.getElementById('log-autoscroll-btn');
    if (btn) {
        logAutoScroll = !logAutoScroll;
        btn.textContent = `Auto-scroll: ${logAutoScroll ? 'ON' : 'OFF'}`;
    }
}
