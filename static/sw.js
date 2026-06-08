const CACHE_VERSION = 'trudnik-v3';
const CACHE_NAME = 'trudnik-v3';
const PRECACHE_URLS = [
  '/',
  '/offline',
  '/static/manifest.json',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-512x512.png',
  '/static/default-avatar.png'
];

// ============================================================
// Install: precache critical shell resources
// ============================================================
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      // Use addAll with individual catch so one failure doesn't block all
      return Promise.allSettled(
        PRECACHE_URLS.map(url =>
          cache.add(url).catch(err =>
            console.warn('SW: Failed to precache', url, err)
          )
        )
      );
    })
  );
  self.skipWaiting();
});

// ============================================================
// Activate: clean old caches, take control immediately
// ============================================================
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames =>
      Promise.all(
        cacheNames
          .filter(name => name !== CACHE_NAME && name.startsWith('trudnik-'))
          .map(name => {
            console.log('SW: Deleting old cache', name);
            return caches.delete(name);
          })
      )
    ).then(() => self.clients.claim())
  );
});

// ============================================================
// Fetch: strategy by request type
// ============================================================
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // --- Strategy 1: Navigation (HTML pages) — Network-first, fallback to offline page ---
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then(response => {
          // Cache the successful navigation response
          const cloned = response.clone();
          caches.open(CACHE_NAME).then(cache =>
            cache.put(request, cloned)
          );
          return response;
        })
        .catch(() => {
          // Try to serve from cache, fallback to offline page
          return caches.match(request).then(cached =>
            cached || caches.match('/offline')
          );
        })
    );
    return;
  }

  // --- Strategy 2: API requests — Network-first, cache fallback ---
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/admin/')) {
    event.respondWith(
      fetch(request)
        .then(response => {
          // Only cache successful GET responses
          if (request.method === 'GET' && response.ok) {
            const cloned = response.clone();
            caches.open(CACHE_NAME + '-api').then(cache =>
              cache.put(request, cloned)
            );
          }
          return response;
        })
        .catch(() => {
          // For GET requests, try cache; for mutations (POST/PUT/DELETE), just fail
          if (request.method === 'GET') {
            return caches.match(request).then(cachedResponse =>
              cachedResponse || new Response(
                JSON.stringify({ error: 'offline', message: 'Нет соединения с сервером' }),
                { status: 503, headers: { 'Content-Type': 'application/json' } }
              )
            );
          }
          return new Response(
            JSON.stringify({ error: 'offline', message: 'Операция недоступна без интернета' }),
            { status: 503, headers: { 'Content-Type': 'application/json' } }
          );
        })
    );
    return;
  }

  // --- Strategy 3: Static assets — Cache-first (Cache Falling Back to Network) ---
  event.respondWith(
    caches.match(request).then(cachedResponse => {
      if (cachedResponse) {
        return cachedResponse;
      }
      // Not in cache: fetch from network and cache for next time
      return fetch(request).then(response => {
        // Only cache same-origin static assets
        if (url.origin === self.location.origin && response.ok) {
          const cloned = response.clone();
          caches.open(CACHE_NAME).then(cache =>
            cache.put(request, cloned)
          );
        }
        return response;
      }).catch(() => {
        // For images, return a placeholder
        if (request.destination === 'image') {
          return caches.match('/static/default-avatar.png');
        }
        // For other static assets, just fail
        return new Response('Offline: resource not available', { status: 408 });
      });
    })
  );
});

// ============================================================
// Message handling: notify clients about updates
// ============================================================
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});
