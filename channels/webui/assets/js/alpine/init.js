/*
 * initializes Alpine and registers all the necessary stuff
 */
document.addEventListener('alpine:init', () => {
    // defined in data.js
    Alpine.data('main', getMainData);

    // defined in stores.js (stores stream-related data)
    Alpine.store('stream', STREAM_STORE);

    // defined in directives.js
    Alpine.directive('auto-scroll', autoScroll);
});
