const CACHE_VERSION = 'trudnik-v15';
const CACHE_NAME = 'trudnik-v15';
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
// Navigation helpers
// ============================================================
function cacheNavigation(request, response) {
  // Никогда не кэшируем 3xx/4xx/5xx: иначе транзиентный 503 остаётся
  // в Cache API и повторно отдаётся после восстановления сети.
  if (!response.ok || response.status !== 200) return;
  const cloned = response.clone();
  const safeHeaders = new Headers(cloned.headers);
  safeHeaders.delete('Content-Security-Policy');
  const safeResponse = new Response(cloned.body, {
    status: cloned.status,
    statusText: cloned.statusText,
    headers: safeHeaders
  });
  caches.open(CACHE_NAME)
    .then(cache => cache.put(request, safeResponse))
    .catch(err => console.warn('SW: navigation cache put failed', err));
}

function offlineFallback() {
  return caches.match('/offline').then(cached => {
    if (cached && cached.ok) return cached;
    return new Response(
      '<!doctype html><html lang="ru"><head><meta charset="utf-8">' +
      '<meta name="viewport" content="width=device-width,initial-scale=1">' +
      '<title>Нет соединения — Трудник</title>' +
      '<style>body{font-family:system-ui,sans-serif;margin:0;display:flex;' +
      'min-height:100vh;align-items:center;justify-content:center;background:#fafafa;' +
      'color:#262626;text-align:center}p{color:#737373;font-size:14px}</style></head>' +
      '<body><main><h1>Нет соединения</h1>' +
      '<p>Не удалось загрузить страницу. Проверьте интернет и обновите страницу.</p>' +
      '<p><a href="/jobs">Повторить</a></p></main></body></html>',
      { status: 200, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
    );
  });
}

// ============================================================
// Fetch: strategy by request type
// ============================================================
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Cross-origin запросы (напр. Yandex SmartCaptcha, Яндекс.Карты) НЕ перехватываем:
  // Service Worker, переиздавая их через fetch(), оценивает их по connect-src страницы
  // (а не script-src), что ломает загрузку виджета капчи. Пусть браузер грузит их сам.
  if (url.origin !== self.location.origin) {
    return;
  }

  // --- Guard: never intercept non-GET requests except explicit XHR mutations
  // to /api/ or /admin/ (handled by Strategy 2 below).
  // Full-page form POSTs (login, register, logout, job actions, etc.) are
  // mode='navigate' with method POST. The Cache API cannot store POST requests,
  // so intercepting them throws "Failed to execute 'put' on 'Cache'" and breaks
  // auth flows. Let the browser handle them natively.
  if (request.method !== 'GET' &&
      !(url.pathname.startsWith('/api/') || url.pathname.startsWith('/admin/'))) {
    return;
  }

  // --- Strategy 1: Navigation (HTML pages) — Network-first, fallback to offline page ---
  // POST-навигации (login/register) не перехватываем — пусть браузер обрабатывает сам
  if (request.mode === 'navigate' && request.method === 'GET') {
    // Не перехватываем /admin — страница делает много долгих запросов к PostgREST,
    // которые превышают таймаут прокси Amvera. Пусть браузер обрабатывает напрямую.
    // Не перехватываем /logout — сервер возвращает 302 (редирект) с очисткой сессии,
    // Service Worker не должен кэшировать этот ответ, иначе браузер показывает
    // ошибку навигации из-за конфликта между SW fetch и Set-Cookie очисткой сессии.
    if (url.pathname.startsWith('/admin') || url.pathname.startsWith('/logout') || url.pathname.startsWith('/verify-email') || url.pathname.startsWith('/password-reset') || url.pathname.startsWith('/chat') || url.pathname.startsWith('/messenger') || url.pathname.startsWith('/my-applications') || url.pathname.startsWith('/profile') || url.pathname.startsWith('/notifications')
      // Формы с CSRF-токеном: кэшированная копия содержит протухший токен —
      // POST вернёт 400 после рестарта сервера/сессий. Не кэшируем.
      || url.pathname.startsWith('/login') || url.pathname.startsWith('/register')) {
      return;
    }
    event.respondWith(
      fetch(request)
        .then(response => {
          cacheNavigation(request, response);
          return response;
        })
        .catch(() => {
          // Сначала — валидный кэш (не 503/404 из старых версий).
          return caches.match(request).then(cached => {
            if (cached && cached.ok) {
              console.log('SW: Serving cached navigation for', request.url);
              return cached;
            }
            // Повторяем запрос без кэша: транзиентный сбой часто проходит сразу.
            return fetch(request, { cache: 'no-store' })
              .then(response => {
                cacheNavigation(request, response);
                // Сервер ответил ошибкой (например, 503 во время деплоя) —
                // показываем дружелюбную офлайн-страницу, а не сырой 503.
                return response.ok ? response : offlineFallback();
              })
              .catch(() => {
                console.log('SW: Network offline, serving offline page for', request.url);
                return offlineFallback();
              });
          });
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
            const safeHeaders = new Headers(cloned.headers);
            safeHeaders.delete('Content-Security-Policy');
            const safeResponse = new Response(cloned.body, {
                status: cloned.status,
                statusText: cloned.statusText,
                headers: safeHeaders
            });
            caches.open(CACHE_NAME + '-api').then(cache =>
              cache.put(request, safeResponse)
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
          const safeHeaders = new Headers(cloned.headers);
          safeHeaders.delete('Content-Security-Policy');
          const safeResponse = new Response(cloned.body, {
              status: cloned.status,
              statusText: cloned.statusText,
              headers: safeHeaders
          });
          caches.open(CACHE_NAME).then(cache =>
            cache.put(request, safeResponse)
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

// ============================================================
// Push Notifications (Web Push API)
// ============================================================

self.addEventListener('push', (event) => {
  let data = {};
  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data = {
        title: 'Trudnik',
        body: event.data.text(),
        icon: '/static/icons/icon-192x192.png',
        badge: '/static/icons/icon-72x72.png',
        data: { url: '/notifications' }
      };
    }
  }

  const options = {
    body: data.body || 'Новое уведомление',
    icon: data.icon || '/static/icons/icon-192x192.png',
    badge: data.badge || '/static/icons/icon-72x72.png',
    vibrate: [200, 100, 200],
    data: {
      url: data.url || '/notifications',
      notification_id: data.notification_id,
      type: data.type
    },
    actions: [
      { action: 'open', title: 'Открыть' },
      { action: 'close', title: 'Закрыть' }
    ],
    tag: data.tag || 'trudnik-notification',
    requireInteraction: data.require_interaction || false
  };

  event.waitUntil(
    self.registration.showNotification(
      data.title || 'Trudnik',
      options
    )
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  const urlToOpen = event.notification.data.url || '/notifications';

  event.waitUntil(
    clients.matchAll({
      type: 'window',
      includeUncontrolled: true
    }).then((clientList) => {
      for (const client of clientList) {
        if (client.url.includes(urlToOpen) && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(urlToOpen);
      }
    })
  );
});

self.addEventListener('pushsubscriptionchange', (event) => {
  event.waitUntil(
    self.registration.pushManager.subscribe(
      event.oldSubscription.options
    ).then((newSubscription) => {
      return fetch('/push/subscription', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': getCSRFToken()
        },
        body: JSON.stringify(newSubscription.toJSON())
      });
    })
  );
});

// Хранилище CSRF-токена в Service Worker (обновляется через postMessage из основного потока + IndexedDB)
let _csrfToken = '';

// Читаем csrfToken из IndexedDB при активации
self.addEventListener('activate', event => {
    event.waitUntil(
        new Promise((resolve) => {
            const req = indexedDB.open('TrudnikState', 1);
            req.onupgradeneeded = (e) => {
                e.target.result.createObjectStore('state');
            };
            req.onsuccess = (e) => {
                const tx = e.target.result.transaction('state', 'readonly');
                const getReq = tx.objectStore('state').get('csrfToken');
                getReq.onsuccess = () => {
                    _csrfToken = getReq.result || '';
                    resolve();
                };
                getReq.onerror = () => resolve();
            };
            req.onerror = () => resolve();
        })
    );
});

// Слушаем сообщения от страницы с обновлённым токеном (сохраняем в IndexedDB)
self.addEventListener('message', (event) => {
  if (event.data && (event.data.type === 'SET_CSRF_TOKEN' || event.data.type === 'UPDATE_CSRF_TOKEN')) {
    _csrfToken = event.data.token || '';
    // Сохраняем в IndexedDB
    const req = indexedDB.open('TrudnikState', 1);
    req.onsuccess = (e) => {
        const tx = e.target.result.transaction('state', 'readwrite');
        tx.objectStore('state').put(_csrfToken, 'csrfToken');
    };
  }
});

function getCSRFToken() {
  return _csrfToken;
}
