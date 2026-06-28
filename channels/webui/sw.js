const CACHE_NAME = 'openlumara-v7.5.9';
const ASSETS = ['/', '/manifest.json', '/icon-192.png', '/icon-512.png'];

self.addEventListener('install', (e) => {
    // Precaching assets to ensure the browser recognizes this as an installable PWA
    e.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(ASSETS);
        }).then(() => {
            // Force the waiting service worker to become the active service worker.
            return self.skipWaiting();
        })
    );
});

self.addEventListener('activate', (e) => {
    // Immediately take control of all open clients (tabs/windows).
    e.waitUntil(
        Promise.all([
            // 1. Clean up old caches
            caches.keys().then(keys =>
            Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
            ),
            // 2. Claim clients
            self.clients.claim()
        ])
    );
});

self.addEventListener('fetch', (e) => {
    if (new URL(e.request.url).origin !== location.origin) return;

    // 1. NAVIGATION (The HTML/Page itself) -> NETWORK FIRST
    // This ensures that if you turn on 'require_login', the very next
    // page load hits the server and sees the redirect.
    if (e.request.mode === 'navigate') {
        e.respondWith(
            fetch(e.request).catch(() => caches.match(e.request))
        );
        return;
    }

    // 2. ASSETS (JS, CSS, Images) -> CACHE FIRST
    // This keeps your UI snappy. Once the user is in, the buttons,
    // styles, and scripts load instantly from the disk.
    e.respondWith(
        caches.match(e.request).then(r => r || fetch(e.request))
    );
});
