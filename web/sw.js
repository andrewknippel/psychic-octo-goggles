"use strict";

// Minimal service worker: makes the app installable and usable offline (the
// shell loads from cache; data.json is always fetched fresh so quotes are
// never served stale), and routes notification clicks to the Fidelity ticket.
//
// Note: this does NOT implement background web push. Buy-alert notifications
// are fired by app.js while the app/tab is open (see notifyNewBuyAlerts). True
// push-when-closed would require a push service + server with VAPID keys.

const CACHE = "dip-buy-radar-v1";
const SHELL = [
  ".",
  "index.html",
  "styles.css",
  "app.js",
  "manifest.webmanifest",
  "icon-192.png",
  "icon-512.png",
  "apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // Always go to the network for data.json — quotes must never be stale.
  if (url.pathname.endsWith("data.json")) return;

  // Cache-first for the app shell, with a network fallback that also warms
  // the cache for next time.
  event.respondWith(
    caches.match(req).then((cached) =>
      cached ||
      fetch(req).then((resp) => {
        if (resp.ok && url.origin === self.location.origin) {
          const copy = resp.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy));
        }
        return resp;
      }).catch(() => cached)
    )
  );
});

// Focus/open the Fidelity ticket when a buy-alert notification is clicked.
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = event.notification.data && event.notification.data.url;
  if (url) event.waitUntil(self.clients.openWindow(url));
});
