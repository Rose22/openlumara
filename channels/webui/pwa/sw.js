/* -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-11-10) harness:openlumara
   PWA service worker, rewritten from scratch.

   The old worker precached the whole webui and answered every request
   cache-first: edited files - the webui's own js/css and module assets
   served under /ext-assets/ - could stay stale across any number of
   reloads, spawning the ?v= bump ritual (see the meditation module's
   warnings). This app is a local tool: it is inert without its server,
   so there is nothing worth serving offline and no reason to ever keep
   a private copy of anything.

   The entire policy is now: every same-origin GET goes through the
   browser's HTTP cache WITH forced revalidation ({ cache: 'no-cache' }
   in fetch semantics - read the cache, but always ask the server
   first). Changed files answer with their new bytes, unchanged ones
   with a cheap 304. Anything cross-origin streams through untouched;
   non-GET requests (the /api/ calls) are never intercepted.

   pwa.py still templates this file ({{VERSION}}/{{FILE_LIST}} get
   substituted) but nothing here uses them - the worker is content-
   agnostic now, so it never needs a version bump. */

self.addEventListener('install', function () {
    // take over immediately; no waiting for every tab to close
    self.skipWaiting();
});

self.addEventListener('activate', function (event) {
    event.waitUntil(
        // drop every cache left behind by the old cache-first workers,
        // then claim the open pages so the new policy covers them right
        // away (init.js reloads once on that handover)
        caches.keys()
            .then(function (names) {
                return Promise.all(names.map(function (n) { return caches.delete(n); }));
            })
            .then(function () {
                return self.clients.claim();
            })
    );
});

self.addEventListener('fetch', function (event) {
    var req = event.request;
    if (req.method !== 'GET') return;
    var url;
    try {
        url = new URL(req.url);
    } catch (e) {
        return;
    }
    // cross-origin resources belong to whoever serves them; their own
    // headers decide caching, and forcing modes here breaks opaque
    // responses. same-origin is where our stale files live.
    if (url.origin !== self.location.origin) return;
    event.respondWith(fetch(req, { cache: 'no-cache' }));
});
