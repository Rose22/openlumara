marked.setOptions({
    breaks: true,
    gfm: true
});

/*
 * initializes Alpine and registers all the necessary stuff
 */
document.addEventListener('alpine:init', async () => {
    // these are all defined in js/stores/
    Alpine.store("ui", UI_STORE);
    Alpine.store("settings", SETTINGS_STORE);
    Alpine.store("chat", CHAT_STORE);
    Alpine.store('stream', STREAM_STORE);
    Alpine.store('theme', THEME_STORE);
    Alpine.store('audio', AUDIO_STORE);

    // defined in directives/
    Alpine.directive('auto-scroll', autoScroll);

    self.notice = "Please wait, connecting to backend server..";
    await connectWebSocket();

    // fetch current chat
    Alpine.store('chat').load();
});
