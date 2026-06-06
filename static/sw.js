const CACHE_NAME = 'trudnik-v2';
const STATIC_ASSETS = [
    '/',
    '/static/manifest.json',
    '/static/icons/icon-48x48.png',
    '/static/icons/icon-72x72.png',
    '/static/icons/icon-96x96.png',
    '/static/icons/icon-144x144.png',
    '/static/icons/icon-168x168.png',
    '/static/icons/icon-192x192.png',
    '/static/icons/icon-512x512.png',
    '/offline'
];

// Install: pre-cache critical static assets
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(cache => {
            return Promise.allSettled(
                STATIC_ASSETS.map(url => cache.add(url).catch(() => {}))
            );
        }).then(() => self.skipWaiting())
    );
});

// Activate: clean up old caches
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys => {
            return Promise.all(
                keys.filter(key => key !== CACHE_NAME).map(key => caches.delete(key))
            );
        }).then(() => self.clients.claim())
    );
});

// Fetch: network-first for HTML, cache-first for static assets
self.addEventListener('fetch', event => {
    const { request } = event;
    const url = new URL(request.url);

    // Only handle GET requests from our origin
    if (request.method !== 'GET' || url.origin !== self.location.origin) {
        return;
    }

    // HTML pages: network-first, fallback to cache, then offline page
    if (request.mode === 'navigate' || request.headers.get('Accept')?.includes('text/html')) {
        event.respondWith(
            fetch(request)
                .then(response => {
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
                    return response;
                })
                .catch(() => {
                    return caches.match(request).then(cached => {
                        return cached || caches.match('/offline');
                    });
                })
        );
        return;
    }

    // Static assets (images, CSS, JS, fonts): cache-first
    event.respondWith(
        caches.match(request).then(cached => {
            return cached || fetch(request).then(response => {
                const clone = response.clone();
                caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
                return response;
            });
        })
    );
});