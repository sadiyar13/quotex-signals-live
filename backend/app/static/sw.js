// Service Worker for Android PWA Live Signal Companion
const CACHE_NAME = 'forex-signals-pwa-v2';
const STATIC_ASSETS = [
  '/',
  '/dashboard',
  '/static/manifest.json',
  '/static/icon.svg',
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(STATIC_ASSETS).catch(() => {});
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.map(k => {
          if (k !== CACHE_NAME) return caches.delete(k);
        })
      );
    })
  );
  self.clients.claim();
});

// Network-first policy for dynamic live API data
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  // Live market API calls: always network
  if (url.pathname.startsWith('/api') || url.pathname.startsWith('/ws')) {
    event.respondWith(fetch(event.request));
    return;
  }

  // Static files: network first, cache fallback
  event.respondWith(
    fetch(event.request)
      .then(response => {
        if (response && response.status === 200) {
          const respClone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, respClone));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});
