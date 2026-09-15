// Service worker for Gimme a W.
//
// This app is scores: a cached page is a wrong page. So nothing here ever
// serves stale HTML -- navigations go to the network every time, and the cache
// exists for two things only. Build assets under /_next/static/ carry a content
// hash in their name, so a hit is always the right file and can be served from
// disk. And when the network is gone, a navigation falls back to one offline
// page rather than the browser's error screen.
//
// Having a fetch handler at all is also what makes the app installable: without
// one Chrome will not offer "Install app", and the home-screen icons never get
// a chance to appear.

const VERSION = "v1";
const SHELL = `shell-${VERSION}`;
const ASSETS = `assets-${VERSION}`;
const OFFLINE = "/offline.html";

// Kept small on purpose: the offline page and the art it shows.
const PRECACHE = [OFFLINE, "/logo.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(SHELL)
      .then((cache) => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== SHELL && k !== ASSETS).map((k) => caches.delete(k))),
      )
      .then(() => self.clients.claim()),
  );
});

/** Hashed build output: the name changes whenever the bytes do, so a hit is safe. */
function immutable(url) {
  return url.pathname.startsWith("/_next/static/");
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match(OFFLINE).then((r) => r ?? Response.error())),
    );
    return;
  }

  if (immutable(url)) {
    event.respondWith(
      caches.match(request).then(
        (hit) =>
          hit ??
          fetch(request).then((response) => {
            if (response.ok) {
              const copy = response.clone();
              caches.open(ASSETS).then((cache) => cache.put(request, copy));
            }
            return response;
          }),
      ),
    );
    return;
  }

  // The precached art: still network-first, because the logo can change, but the
  // cached copy is there when the network is not -- which is the one moment the
  // offline page needs it.
  if (PRECACHE.includes(url.pathname)) {
    event.respondWith(
      fetch(request).catch(() => caches.match(request).then((r) => r ?? Response.error())),
    );
    return;
  }

  // Everything else -- data, images, the manifest -- stays on the network.
});
