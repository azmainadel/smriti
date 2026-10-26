// Smriti service worker: receives the Android share sheet (Web Share Target) and keeps
// the app shell available offline. Data always comes fresh from the API.
const SHELL = "smriti-shell-v1";
const SHARE = "smriti-share";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL).then((c) => c.addAll(["/", "/manifest.webmanifest", "/icon.svg"])));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== SHELL && k !== SHARE).map((k) => caches.delete(k)))),
  );
  self.clients.claim();
});

async function receiveShare(request) {
  const form = await request.formData();
  const params = new URLSearchParams();
  for (const key of ["title", "text", "url"]) {
    const value = form.get(key);
    if (value) params.set(key, value);
  }
  const files = form.getAll("files").filter((f) => f && typeof f !== "string" && f.size);
  if (files.length) {
    // The page cannot read this request, so stash files where /share can pick them up.
    const cache = await caches.open(SHARE);
    await Promise.all(
      files.map((f, i) =>
        cache.put(`/shared/${i}/${encodeURIComponent(f.name)}`, new Response(f, { headers: { "content-type": f.type } })),
      ),
    );
    params.set("files", String(files.length));
  }
  return Response.redirect(`/share?${params}`, 303);
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method === "POST" && url.pathname === "/share-target") {
    event.respondWith(receiveShare(event.request));
    return;
  }
  // Navigations: network first, shell fallback when offline.
  if (event.request.mode === "navigate" && url.origin === self.location.origin) {
    event.respondWith(fetch(event.request).catch(() => caches.match("/")));
  }
});
