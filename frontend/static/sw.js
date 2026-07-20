/**
 * HOLO-RTLS Service Worker
 * Caches static assets for offline access (read-only shell).
 * Skips caching for auth endpoints and SSE streams.
 */
const CACHE_NAME = 'holo-rtls-v17';
const STATIC_ASSETS = [
  '/static/css/dashboard-theme.css',
  '/static/css/dashboard.css',
  '/static/css/shell.css',
  '/static/css/auth.css',
  '/static/js/api.js',
  '/static/js/dashboard.js',
  '/static/js/visualization/coordinate-service.js',
  '/static/js/visualization/tracker-canvas-layer.js',
  '/static/js/visualization/map2d.js',
  '/static/js/visualization/map3d.js',
  '/static/assets/floor-plan-placeholder.png',
  '/static/manifest.json',
];

// ── Install: cache static assets ─────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(STATIC_ASSETS).catch(err => {
        console.warn('[SW] Failed to cache some assets:', err);
      });
    })
  );
  self.skipWaiting();
});

// ── Activate: clean up old caches ────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

// ── Fetch: network-first for HTML, cache-first for static assets ───────────────
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Never cache SSE streams or API mutations
  if (
    url.pathname.startsWith('/api/stream') ||
    url.pathname.startsWith('/api/auth/login') ||
    url.pathname.startsWith('/api/auth/refresh') ||
    url.pathname.startsWith('/api/auth/register') ||
    request.method !== 'GET'
  ) {
    return; // Let the request go through without SW interception
  }

  // Static assets → cache-first
  if (
    url.pathname.startsWith('/static/') ||
    url.pathname.endsWith('.css') ||
    url.pathname.endsWith('.js') ||
    url.pathname.endsWith('.png') ||
    url.pathname.endsWith('.svg') ||
    url.pathname.endsWith('.woff2')
  ) {
    event.respondWith(
      caches.match(request).then(cached => {
        if (cached) return cached;
        return fetch(request).then(response => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
          }
          return response;
        });
      })
    );
    return;
  }

  // HTML pages → network-first with cache fallback
  if (request.headers.get('accept')?.includes('text/html')) {
    event.respondWith(
      fetch(request)
        .then(response => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then(cache => cache.put(request, clone));
          }
          return response;
        })
        .catch(() => caches.match(request).then(cached => {
          if (cached) return cached;
          return new Response(
            '<!DOCTYPE html><html><body style="font-family:system-ui;background:#1c1c1e;color:#f5f5f7;padding:2rem"><h1>Offline</h1><p>Reconnect to load this page.</p></body></html>',
            { status: 503, headers: { 'Content-Type': 'text/html; charset=utf-8' } }
          );
        }))
    );
    return;
  }

  // API GET requests → network-first
  event.respondWith(
    fetch(request).catch(() => caches.match(request))
  );
});

// ── Push notifications (placeholder for future alert push) ────────────────────
self.addEventListener('push', event => {
  if (!event.data) return;
  const data = event.data.json();
  event.waitUntil(
    self.registration.showNotification(data.title || 'HOLO-RTLS Alert', {
      body: data.body || 'New alert triggered',
      icon: '/static/assets/icon-192.png',
      badge: '/static/assets/icon-192.png',
      tag: 'holo-alert',
      data: data.url || '/alerts',
      vibrate: [200, 100, 200],
      requireInteraction: true,
    })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    self.clients.openWindow(event.notification.data || '/alerts')
  );
});
