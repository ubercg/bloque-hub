/* Minimal service worker for operations PWA: cache-first for same URL after first load. */
const CACHE = 'bloque-ops-v1';

self.addEventListener('install', (e) => {
  self.skipWaiting();
});

self.addEventListener('activate', (e) => {
  e.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (e) => {
  const u = new URL(e.request.url);
  if (u.pathname.indexOf('/operations/') !== 0 || e.request.method !== 'GET') return;
  e.respondWith(
    caches.open(CACHE).then((cache) =>
      fetch(e.request)
        .then((r) => {
          const clone = r.clone();
          cache.put(e.request, clone);
          return r;
        })
        .catch(() => cache.match(e.request))
    )
  );
});
