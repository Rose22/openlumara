// =============================================================================
// Cleanup Function
// =============================================================================

function cleanup() {
    if (pollIntervalId) {
        clearInterval(pollIntervalId);
        pollIntervalId = null;
    }
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
    hideConnectionStatus();
}

window.addEventListener('beforeunload', cleanup);

// =============================================================================
// Service Worker Registration
// =============================================================================

if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js')
        .then(reg => console.log('Service Worker registered'))
        .catch(err => console.log('Service Worker registration failed:', err));
    });
}


// =============================================================================
// Main Initialization
// =============================================================================

updateConnectionStatus('connecting');

async function init() {
    try {
        await checkConnection();

        // Load current chat from backend if available
        if (isConnected) {
            await restoreCurrentChat();
        }
    } catch (err) {
        isConnected = false;
        updateConnectionStatus('disconnected');
        scheduleReconnect();
    }

    loadTheme();
    loadChats();
    initTagFilterState();
    requestNotificationPermission();

    window.addEventListener('resize', handleTitleBarResize);

    pollIntervalId = setInterval(() => {
        if (isConnected) {
            pollMessages();
        }
    }, CONFIG.POLL_INTERVAL);
}

init();
