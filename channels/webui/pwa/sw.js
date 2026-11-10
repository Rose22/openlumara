const CACHE_NAME = 'openlumara-{{VERSION}}';

const ASSETS_TO_CACHE = JSON.parse('{{FILE_LIST}}').concat([
    '/manifest.json',
    '/icon-192.png',
    '/icon-512.png',
    '/sw.js?v={{VERSION}}', // Self-reference with version
]);

console.log('Service Worker loaded: {{VERSION}}');

self.addEventListener('install', (event) => {
  console.log('Installing Service Worker...');

  // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-22) harness:openlumara status:reviewed
  // activate as soon as install finishes instead of waiting for every tab
  // of the app to close. without this, a new webui build parks in the
  // "waiting" state indefinitely while the old worker keeps serving its
  // old cache-first assets - the "only a force refresh picks up updates"
  // bug. (init.js reloads the page once when the new worker takes over.)
  self.skipWaiting();

  event.waitUntil(
    caches.open(CACHE_NAME)
      .then((cache) => {
        console.log(`Caching ${ASSETS_TO_CACHE.length} assets...`);

        return Promise.all(
          ASSETS_TO_CACHE.map((url) => {
            return fetch(url).then((response) => {
              if (!response.ok) {
                console.error(`Failed to fetch ${url}: ${response.status}`);
                return null;
              }
              console.log(`Cached: ${url}`);
              return cache.put(url, response);
            }).catch((err) => {
              console.error(`Error fetching ${url}:`, err.message);
              return null;
            });
          })
        ).then(() => {
          console.log('Service Worker installed successfully');
        });
      })
      .catch((err) => {
        console.error('Installation failed:', err);
      })
  );
});

self.addEventListener('activate', (event) => {
  console.log('Activating Service Worker...');
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      console.log(`Found ${cacheNames.length} cache(s):`, cacheNames);

      const cachesToDelete = cacheNames.filter((name) => name !== CACHE_NAME);
      console.log(`Deleting ${cachesToDelete.length} old cache(s):`, cachesToDelete);

      return Promise.all(
        cachesToDelete.map((name) => caches.delete(name))
      );
    })
    .then(() => self.clients.claim())
    .then(() => {
      // -- AI GENERATED CODE (Qwen3.8 Flash Next) :: (2026-10-22) harness:openlumara status:reviewed
      // claim() takes control of already-open pages right after the old
      // caches are deleted, so the fresh cache serves them immediately
      // (this is what fires controllerchange in init.js).
      console.log('Service Worker activated and clients claimed');
    })
    .catch((err) => {
      console.error('Activation failed:', err);
    })
  );
});

self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request)
      .then((response) => {
        if (response) {
          // console.log(`Cache hit: ${event.request.url}`);
          return response;
        }
        // console.log(`Cache miss, fetching: ${event.request.url}`);
        return fetch(event.request);
      })
      .catch((err) => {
        console.error(`Fetch failed for ${event.request.url}:`, err);
      })
  );
});
