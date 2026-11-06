// -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (11-06-2026) harness:openlumara
/*
 * Custom-header gate (CSRF / model-rendered-request defense).
 *
 * The server refuses same-origin /api requests that lack the header
 * X-OpenLumara: 1 (see auth_middleware in server.py). Only javascript can
 * attach custom headers via fetch/XHR, and cross-origin fetches with custom
 * headers die at the CORS preflight this server never answers. So requests
 * fired through <img>, <form>, navigation, or a foreign site's script are
 * stopped at the gate, while our own frontends keep working.
 *
 * window.fetch is wrapped here so that module-provided frontends (most of
 * which call fetch directly) get the header automatically. This script must
 * stay loaded in <head> before every other script.
 */
(() => {
    const original_fetch = window.fetch.bind(window);

    window.fetch = function (input, init) {
        try {
            const raw_url = (typeof input === "string") ? input
                : (input && input.url) ? input.url : String(input);
            const url = new URL(raw_url, window.location.href);

            if (url.origin === window.location.origin && url.pathname.startsWith("/api")) {
                init = Object.assign({}, init);
                const base_headers = (init.headers !== undefined) ? init.headers
                    : (input instanceof Request ? input.headers : undefined);
                const headers = new Headers(base_headers);
                if (!headers.has("x-openlumara")) {
                    headers.set("x-openlumara", "1");
                }
                init.headers = headers;
            }
        } catch (e) {
            // unparseable input: send the request untouched; the server gate decides.
        }
        return original_fetch(input, init);
    };
})();
