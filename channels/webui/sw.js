const CACHE_NAME = 'openlumara-v{{VERSION}}';

// Assets to precache (these get versioned by the backend)
const PRECACHE_ASSETS = [
    '/',
    '/manifest.json',
    '/icon-192.png',
    '/icon-512.png',
    '/sw.js?v={{VERSION}}', // Self-reference with version
];

self.addEventListener('install', (event) => {
    console.log('[SW] Installing service worker with cache:', CACHE_NAME);
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => {
                console.log('[SW] Precaching assets:', PRECACHE_ASSETS);
                return cache.addAll(PRECACHE_ASSETS);
            })
            .then(() => {
                console.log('[SW] Skipping waiting to activate immediately');
                return self.skipWaiting();
            })
            .catch((err) => {
                console.error('[SW] Install failed:', err);
            })
    );
});

self.addEventListener('activate', (event) => {
    console.log('[SW] Activating service worker');
    event.waitUntil(
        Promise.all([
            // Clean up old caches
            caches.keys().then((keys) => {
                return Promise.all(
                    keys
                        .filter((key) => key !== CACHE_NAME)
                        .map((key) => {
                            console.log('[SW] Deleting old cache:', key);
                            return caches.delete(key);
                        })
                );
            }),
            // Take control of all open clients
            self.clients.claim()
        ])
    );
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    
    // Only handle same-origin requests
    if (url.origin !== location.origin) return;

    // Navigation requests: Network First
    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request)
                .catch(() => {
                    console.log('[SW] Network failed, serving from cache');
                    return caches.match(event.request);
                })
        );
        return;
    }

    // All other requests: Cache First, then Network
    event.respondWith(
        caches.match(event.request)
            .then((cached) => {
                const fetchPromise = fetch(event.request)
                    .then((networkResponse) => {
                        // Update cache with fresh response
                        if (networkResponse.ok) {
                            const responseClone = networkResponse.clone();
                            caches.open(CACHE_NAME).then((cache) => {
                                cache.put(event.request, responseClone);
                            });
                        }
                        return networkResponse;
                    })
                    .catch(() => {
                        console.log('[SW] Network failed for:', url.pathname);
                        return null;
                    });

                // Return cached if available, otherwise wait for network
                return cached || fetchPromise;
            })
    );
});

// Handle messages from client
self.addEventListener('message', (event) => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
});

