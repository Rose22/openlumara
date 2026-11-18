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
    Alpine.store('htmlPreview', HTML_PREVIEW_STORE);

    // start the browser notification system
    Alpine.store('notifications', NOTIFY_STORE);
    await Alpine.store('notifications').init();

    // defined in directives/
    
    // pass Alpine's cleanup hook through, otherwise the teardown fn returned by
    // autoScroll() is ignored and scroll listeners + MutationObservers leak per element
    Alpine.directive('auto-scroll', (el, modifiers, { cleanup }) => cleanup(autoScroll(el)));
    Alpine.directive('md', markdownRender);

    // x-text / x-html variants that fade newly streamed content in
    // (reasoning, tool call args, tool responses)
    Alpine.directive('fade-text', Alpine.skipDuringClone(fadeTextRender));
    Alpine.directive('fade-html', Alpine.skipDuringClone((el, d, c) => fadeTextRender(el, d, c, true)));

    // toggles .boxed when an element's content overflows its max-height,
    // so tool call values only get the soft background when they scroll
    Alpine.directive('box', (el, modifiers, { cleanup }) => cleanup(boxIfScrolls(el)));
    Alpine.directive('stream-grow', Alpine.skipDuringClone((el, modifiers, { cleanup }) => cleanup(streamGrow(el))));

    // watches a flow marker outside a pinned turn for the pinned-prompt feature
    Alpine.directive('prompt-marker', (el, { expression }, { evaluateLater, cleanup }) => {
        const run = evaluateLater(expression);
        cleanup(promptMarker(el, (intersecting) => run(() => {}, { scope: { intersecting } })));
    });

    self.notice = "Please wait, connecting to backend server..";
    await connectWebSocket();

    // register the service worker
    if ('serviceWorker' in navigator) {
        // updateViaCache 'none': always revalidate sw.js itself, so an
        // update check can never be answered from the HTTP cache
        navigator.serviceWorker.register('/sw.js', { updateViaCache: 'none' });

        if (navigator.serviceWorker.controller) {
            let swReloadDone = false;
            navigator.serviceWorker.addEventListener('controllerchange', () => {
                if (swReloadDone) { return; }
                swReloadDone = true;
                console.log('Service worker updated: reloading for fresh assets..');
                window.location.reload();
            });
        }
    }

    // check if we're on a phone
    await Alpine.store('ui').init();

    // fetch any relevant system data (like system logs, max context, etc)
    await Alpine.store('system').loadData();

    // fetch current chat
    try {
        await Alpine.store('chat').load();

        // do the initial scroll to bottom, masked so the top of the chat is
        // never painted first
        await Alpine.store('chat').anchorToBottom();
    } finally {
        // never leave the chat hidden, whatever happened above
        document.getElementById('messages')?.classList.remove('anchor-hidden');
    }

    document.getElementById('user-input')?.focus();

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
