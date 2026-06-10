// =============================================================================
// Browser Notifications
// =============================================================================

function requestNotificationPermission() {
    if (!('Notification' in window)) {
        console.log('Browser notifications not supported');
        return;
    }

    if (Notification.permission === 'default') {
        Notification.requestPermission().then(permission => {
            notificationPermission = permission;
        }).catch(err => {
            console.error('Failed to request notification permission:', err);
        });
    } else {
        notificationPermission = Notification.permission;
    }
}

function showAnnouncementNotification(content, type) {
    if (notificationPermission !== 'granted') return;
    if (!('Notification' in window)) return;

    // Determine notification options based on type
    const typeSettings = {
        schedule: { icon: '📢', tag: 'announce-info' },
        warning: { icon: '⚠️', tag: 'announce-warning' },
        error: { icon: '❌', tag: 'announce-error' },
        success: { icon: '✅', tag: 'announce-success' },
        info: { icon: 'ℹ️', tag: 'announce-info' }
    };

    const settings = typeSettings[type] || typeSettings.info;

    const notification = new Notification(`System ${type.charAt(0).toUpperCase() + type.slice(1)}`, {
        body: content,
        icon: settings.icon,
        tag: settings.tag,
        renotify: true
    });

    notification.onclick = () => {
        window.focus();
        notification.close();
    };

    // Auto-close after 5 seconds
    setTimeout(() => notification.close(), 5000);
}
