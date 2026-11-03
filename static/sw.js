// Service worker of the finance app.
// Pages always come fresh from the server (they contain personal data and form tokens);
// they are never cached. Only static files (styles, icons, offline page) are cached,
// so the app starts quickly and shows a notice instead of an error page when offline.

const CACHE = "finanzen-v1";
const OFFLINE_PAGE = "/static/offline.html";
const PRECACHE = [
  OFFLINE_PAGE,
  "/static/style.css",
  "/static/icons/icon-192.png",
  "/static/icons/favicon-32.png",
];

self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== location.origin) return;

  // Pages: network only; without a connection show the offline page
  if (request.mode === "navigate") {
    event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_PAGE)));
    return;
  }

  // Static files: fresh from the network, the cached copy as fallback when offline
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      fetch(request)
        .then(response => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(CACHE).then(cache => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => caches.match(request))
    );
  }
});
