marked.setOptions({
    breaks: true,
    gfm: true
});

/*
 * initializes Alpine and registers all the necessary stuff
 */
document.addEventListener('alpine:init', async () => {
    // these are all defined in js/stores/
    Alpine.store("system", SYSTEM_STORE);
    Alpine.store("ui", UI_STORE);
    Alpine.store("settings", SETTINGS_STORE);
    Alpine.store("chat", CHAT_STORE);
    Alpine.store('stream', STREAM_STORE);
    Alpine.store('theme', THEME_STORE);
    Alpine.store('audio', AUDIO_STORE);
    Alpine.store('upload', UPLOAD_STORE);

    // start the browser notification system
    Alpine.store('notifications', NOTIFY_STORE);
    await Alpine.store('notifications').init();

    // defined in directives/
    Alpine.directive('auto-scroll', autoScroll);
    Alpine.directive('md', markdownRender);

    self.notice = "Please wait, connecting to backend server..";
    await connectWebSocket();

    // register the service worker
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/sw.js');
    }

    // check if we're on a phone
    await Alpine.store('ui').init();

    // fetch any relevant system data (like system logs, max context, etc)
    await Alpine.store('system').loadData();

    // fetch current chat
    await Alpine.store('chat').load();

    // do the initial scroll to bottom
    requestAnimationFrame(() => {
        Alpine.store('ui').forceScrollToBottom();
    });

    await registerKeyboardShortcuts();

    // auto-close sidebar on resizing to below desktop size (mobile size)
    // window.addEventListener('resize', () => {
    //     if (window.innerWidth < 768 && Alpine.store('ui').sidebarOpen) {
    //         Alpine.store('ui').sidebarOpen = false;
    //     }
    //     else if (window.innerWidth > 768 && !Alpine.store('ui').sidebarOpen) {
    //         Alpine.store('ui').sidebarOpen = true;
    //     }
    // });
});
