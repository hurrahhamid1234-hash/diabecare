"""Adds the "install as app" files to DiabeCare. Run once from the project folder:  python add_pwa.py"""
import math
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:
    sys.exit("Pillow is missing. Run:  pip install pillow   and then run this again.")

FRONT = Path(__file__).resolve().parent / "frontend"
if not (FRONT / "index.html").exists():
    sys.exit("Cannot find frontend\\index.html. Put add_pwa.py in the diabecare project folder (next to the app and frontend folders).")

MANIFEST = '''{
  "name": "DiabeCare",
  "short_name": "DiabeCare",
  "description": "Diabetes health records, risk estimate and health assistant (educational prototype)",
  "start_url": "./",
  "scope": "./",
  "display": "standalone",
  "orientation": "portrait",
  "background_color": "#f3f6f9",
  "theme_color": "#1f3a5f",
  "icons": [
    { "src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any" },
    { "src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any" },
    { "src": "icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable" }
  ]
}
'''

SW = '''// DiabeCare service worker. It only keeps a copy of the empty page shell so the app opens (with a short
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
'''

HEAD_TAGS = '''<title>DiabeCare</title>
<link rel="manifest" href="manifest.json">
<meta name="theme-color" content="#1f3a5f">
<link rel="icon" type="image/png" href="icon-192.png">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="DiabeCare">'''

INSTALL_BUTTON = '<button class="link hidden" id="install" style="margin-left:auto">Install app</button>\n  <button class="link hidden" id="logout">Log out</button>'

INSTALL_JS = '''
/* ---------- install as an app ---------- */
let installEvent = null;
window.addEventListener('beforeinstallprompt', e => { e.preventDefault(); installEvent = e; $('#install').classList.remove('hidden'); });
$('#install').onclick = async () => { if (!installEvent) return; installEvent.prompt(); await installEvent.userChoice.catch(() => {}); installEvent = null; $('#install').classList.add('hidden'); };
window.addEventListener('appinstalled', () => $('#install').classList.add('hidden'));
if ('serviceWorker' in navigator) window.addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
</script>
</body>'''


def icon(size, maskable):
    S = size * 4
    NAVY, TEAL, W = (31, 58, 95), (42, 127, 142), (255, 255, 255)
    if maskable:
        im = Image.new("RGB", (S, S), NAVY)
    else:
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if not maskable:
        d.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.22), fill=NAVY)
    k = 0.52 if maskable else 0.62
    cx, cy = S / 2, S * 0.56
    r = S * k * 0.30
    top = (cx, cy - S * k * 0.52)
    ang = math.asin(r / (cy - top[1]))
    d.polygon([top, (cx - r * math.cos(ang), cy - r * math.sin(ang)), (cx + r * math.cos(ang), cy - r * math.sin(ang))], fill=W)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=W)
    p, t = r * 0.55, r * 0.17
    plus = NAVY if maskable else TEAL
    d.rectangle([cx - t, cy - p + r * 0.12, cx + t, cy + p + r * 0.12], fill=plus)
    d.rectangle([cx - p, cy - t + r * 0.12, cx + p, cy + t + r * 0.12], fill=plus)
    return im.resize((size, size), Image.LANCZOS)


(FRONT / "manifest.json").write_text(MANIFEST, encoding="utf-8")
(FRONT / "sw.js").write_text(SW, encoding="utf-8")
for name, size, maskable in [("icon-192.png", 192, False), ("icon-512.png", 512, False),
                             ("icon-maskable-512.png", 512, True), ("apple-touch-icon.png", 180, True)]:
    icon(size, maskable).save(FRONT / name)
print("Created manifest.json, sw.js and 4 icons in frontend\\")

page = FRONT / "index.html"
s = page.read_text(encoding="utf-8")
if 'rel="manifest"' in s:
    print("index.html already has the install support. Nothing to change.")
else:
    pairs = [("<title>DiabeCare</title>", HEAD_TAGS),
             ('<button class="link hidden" id="logout">Log out</button>', INSTALL_BUTTON),
             ("</script>\n</body>", INSTALL_JS)]
    for old, new in pairs:
        if s.count(old) != 1:
            sys.exit(f"index.html is different from what I expected (could not find: {old[:40]}). Nothing was changed in index.html. Tell Claude.")
        s = s.replace(old, new)
    page.write_text(s, encoding="utf-8")
    print("Updated frontend\\index.html")
print("Done. Now run:  git add .   then   git commit -m \"Installable app\"   then   git push")