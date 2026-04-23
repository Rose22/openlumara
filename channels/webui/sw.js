const CACHE_NAME = 'openlumara-v2.9.0';
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

    e.respondWith(
        caches.match(e.request).then(r => r || fetch(e.request))
    );
});
