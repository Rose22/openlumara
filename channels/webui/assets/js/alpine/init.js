/*
 * initializes Alpine and registers all the necessary stuff
 */
document.addEventListener('alpine:init', () => {
    // defined in main.js
    Alpine.data('main', getMainData);

    // defined in js/chat/stream.js (stores stream-related data)
    Alpine.store('stream', STREAM_STORE);
    // defined in js/theming.js
    Alpine.store('theme', THEME_STORE);
    // defined in js/modals/settings/audio.js
    Alpine.store('audio', AUDIO_STORE);

    // defined in directives.js
    Alpine.directive('auto-scroll', autoScroll);
});
