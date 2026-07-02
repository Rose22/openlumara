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

function showNotification(content, timeout=null) {
    if (notificationPermission !== 'granted') return;
    if (!('Notification' in window)) return;

    const notification = new Notification(`OpenLumara`, {
        body: content,
        icon: '📢',
        tag: 'openlumara',
        renotify: true
    });

    notification.onclick = () => {
        window.focus();
        notification.close();
    };

    if (timeout) {
        setTimeout(() => notification.close(), timeout);
    }
}
