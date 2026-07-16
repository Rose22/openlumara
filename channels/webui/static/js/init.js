// =============================================================================
// Initialization
// =============================================================================

async function init() {
    requestNotificationPermission();
    document.addEventListener('click', () => {
        if (typeof notificationPermission !== 'undefined' && notificationPermission === 'default') {
            requestNotificationPermission();
        }
    }, { once: true });

    try {
        const savedFontSize = localStorage.getItem('fontSize');
        if (savedFontSize) {
            document.documentElement.style.setProperty('--font-size-base', `${savedFontSize}px`);
        }

        loadTheme();
        loadChats();
        initTagFilterState();

        window.addEventListener('resize', handleTitleBarResize);

        Object.entries(SOUND_DEFAULTS).forEach(([id, enabled]) => {
            const key = `${id}Enabled`;
            try {
                if (typeof localStorage !== 'undefined') {
                    const current = localStorage.getItem(key);
                    if (current === null) {
                        localStorage.setItem(key, String(enabled));
                    }
                }
            } catch (e) {
                console.warn('[Init] Storage unavailable, using runtime defaults');
            }
        });

        connectWebSocket();
    } catch (err) {
        console.error('Failed to initialize UI and polling:', err);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

init();
