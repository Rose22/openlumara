const CACHE_NAME = 'openlumara-v3.2.2';
const ASSETS = ['/', '/manifest.json'];

self.addEventListener('install', (e) => {
    e.waitUntil(caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS)));
});

self.addEventListener('activate', (e) => {
    e.waitUntil(caches.keys().then(keys => 
        Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    ));
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
