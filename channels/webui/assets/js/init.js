marked.setOptions({
    breaks: true,
    gfm: true
});

document.body.classList.toggle('no-frosted', localStorage.getItem('frostedGlassEnabled') === 'false');

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

    // command palette (Ctrl+K), see components/command_palette.js
    Alpine.store('palette', PALETTE);

    // user-rebindable keyboard shortcuts (localStorage-backed)
    Alpine.store('keyboard', KEYBOARD_STORE);
    Alpine.store('keyboard').init();

    // start the browser notification system
    Alpine.store('notifications', NOTIFY_STORE);
    await Alpine.store('notifications').init();

    // defined in directives/
    
    // pass Alpine's cleanup hook through, otherwise the teardown fn returned by
    // autoScroll() is ignored and scroll listeners + MutationObservers leak per element.
    // the effect hook re-syncs the streaming height ratchet on every morph, which
    // is also when the element first lands in the DOM (setup runs on a placeholder)
    Alpine.directive('auto-scroll', (el, modifiers, { cleanup, effect }) => {
        effect(() => autoscrollSyncStreaming(el));
        cleanup(autoScroll(el));
    });
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

    // clones a command palette icon (see the #cmd-icons sprite) into the row,
    // re-resolving whenever the expression changes
    Alpine.directive('cmd-icon', (el, { expression }, { evaluate }) => {
        el.replaceChildren();

        const sprite = document.getElementById('cmd-icons');
        const src = sprite && sprite.querySelector(`[data-cmdi="${evaluate(expression)}"]`);
        const fallback = sprite && sprite.querySelector('[data-cmdi="sparkle"]');

        if (src || fallback) el.appendChild((src ?? fallback).firstElementChild.cloneNode(true));
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
