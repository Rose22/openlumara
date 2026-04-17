// =============================================================================
// Cleanup Function
// =============================================================================

function cleanup() {
    if (pollIntervalId) {
        clearInterval(pollIntervalId);
        pollIntervalId = null;
    }
    if (apiStatusIntervalId) {
        clearInterval(apiStatusIntervalId);
        apiStatusIntervalId = null;
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
// Initialization
// =============================================================================

// Don't set initial connection status - let it be determined by checkConnection()

async function init() {
    requestNotificationPermission();

    // The first time the user clicks anywhere,
    // we attempt to request notification permission.
    document.addEventListener('click', () => {
        if (typeof notificationPermission !== 'undefined' && notificationPermission === 'default') {
            requestNotificationPermission();
        }
    }, { once: true });

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

    // Apply saved font size on load
    const savedFontSize = localStorage.getItem('fontSize');
    if (savedFontSize) {
        document.documentElement.style.setProperty('--font-size-base', `${savedFontSize}px`);
    }

    loadTheme();
    loadChats();
    initTagFilterState();

    window.addEventListener('resize', handleTitleBarResize);

    // Message polling
    pollIntervalId = setInterval(() => {
        if (isConnected) {
            pollMessages();
        }
    }, CONFIG.POLL_INTERVAL);

    // Periodic API status check
    apiStatusIntervalId = setInterval(() => {
        if (isConnected) {
            checkApiStatus();
        }
    }, CONFIG.API_STATUS_INTERVAL);
}

init();
