const CACHE_NAME = 'openlumara-{{VERSION}}';

// Assets to precache (these get versioned by the backend)
const ASSETS_TO_CACHE = [
    {{FILE_LIST}},
    '/manifest.json',
    '/icon-192.png',
    '/icon-512.png',
    '/sw.js?v={{VERSION}}', // Self-reference with version
];

console.log('Service Worker loaded: {{VERSION}}');

self.addEventListener('install', (event) => {
  console.log('Installing Service Worker...');
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
    .then(() => {
      console.log('Service Worker activated');
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
