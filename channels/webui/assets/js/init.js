marked.setOptions({
    breaks: true,
    gfm: true
});

document.body.classList.toggle('no-frosted', localStorage.getItem('frostedGlassEnabled') === 'false');

/*
 * initializes Alpine and registers all the necessary stuff
 */
document.addEventListener('alpine:init', async () => {
    /*
     * the chat header floats over the message scrollbox (window.css runs
     * #messages under it) so its frost blurs the bubbles passing behind.
     * a resize observer feeds the header's live height into
     * --header-height, driving the overlap, the scroll padding and the
     * pinned pill's stick offset - collapse to zero included. without JS
     * the 0px fallback keeps the old flush layout.
     */
    const chatHeader = document.querySelector('header');

    if (chatHeader) {
        const pushHeaderHeight = () => {
            const h = chatHeader.offsetHeight;
            document.documentElement.style.setProperty('--header-height', `${h}px`);
            // releases the header's min-height once its content is gone,
            // so the collapse-to-zero state still works (see header.css)
            document.body.classList.toggle('header-empty', h === 0);
        };

        pushHeaderHeight();
        new ResizeObserver(pushHeaderHeight).observe(chatHeader);
    }

    // these are all defined in js/stores/
    Alpine.store("system", SYSTEM_STORE);
    Alpine.store("ui", UI_STORE);
    Alpine.store("settings", SETTINGS_STORE);
    Alpine.store("chat", CHAT_STORE);
    Alpine.store('stream', STREAM_STORE);
    Alpine.store('theme', THEME_STORE);
    Alpine.store('audio', AUDIO_STORE);
    Alpine.store('background', BACKGROUND_STORE);
    Alpine.store('upload', UPLOAD_STORE);
    Alpine.store('htmlPreview', HTML_PREVIEW_STORE);

    // command palette (Ctrl+K), see components/command_palette.js
    Alpine.store('palette', PALETTE);

    // load the audio settings from localStorage into the store, then push
    // them into the AudioManager (must run before any sound can play)
    Alpine.store('audio').init();

    // restore the background image from IndexedDB and apply its layer
    Alpine.store('background').init();

    // user-rebindable keyboard shortcuts (localStorage-backed)
    Alpine.store('keyboard', KEYBOARD_STORE);
    Alpine.store('keyboard').init();

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

    // keeps a scroll container at its tallest-so-far height while the
    // expression is true (capped by its CSS max-height), releasing it back
    // to content height once false (see directives/height_ratchet.js)
    Alpine.directive('height-ratchet', (el, { expression }, { evaluateLater, effect, cleanup }) =>
        heightRatchet(el, evaluateLater(expression), effect, cleanup));

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

    // background update check so the settings gear can badge before the
    // modal is ever opened; delayed so it never competes with page load
    // (each repo check does its own git fetch)
    if (!window.ADMIN_SETTINGS_DISABLED && SYSTEM_STORE.autoCheckEnabled()) {
        setTimeout(() => Alpine.store('system').checkForUpdates(), 4000);
    }

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
