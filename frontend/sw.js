// DiabeCare service worker. It only keeps a copy of the empty page shell so the app opens (with a short
// "no internet" notice) when the phone is offline. It never stores API answers or health data: every
// request other than opening the page goes straight to the network.
const CACHE = 'diabecare-shell-v1';

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.add('./')).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', e => {
  const r = e.request;
  if (r.method !== 'GET' || r.mode !== 'navigate') return;          // API calls, files, images: not touched
  e.respondWith(
    fetch(r).then(res => {
      if (res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put('./', copy)); }
      return res;
    }).catch(() => caches.match('./').then(hit => hit || new Response(
      'You are offline. Please connect to the internet and try again.', { status: 503, headers: { 'Content-Type': 'text/plain' } })))
  );
});
