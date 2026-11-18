// Service worker: conserva una copia del sito per farlo funzionare anche con poca rete.
// - pagine, stili, script, librerie: copia locale, aggiornata in background;
// - dati (dati/*.json): sempre prima dalla rete, la copia solo se la rete manca;
// - mappa (OpenFreeMap): non viene toccata, ci pensa la cache normale del browser.
// Cambia VERSIONE quando modifichi i file del sito, così i telefoni scaricano quelli nuovi.

const VERSIONE = "v5";
const BASE = [
  "./", "index.html", "prezzi.html", "affidabilita.html", "info.html", "privacy.html", "note-legali.html",
  "css/stile.css", "css/mappa.css",
  "js/comune.js", "js/mappa.js", "js/prezzi.js", "js/affidabilita.js",
  "vendor/maplibre/maplibre-gl.mjs", "vendor/maplibre/maplibre-gl-worker.mjs",
  "vendor/maplibre/maplibre-gl-shared.mjs", "vendor/maplibre/maplibre-gl.css",
  "vendor/fraunces/fraunces-latin-wght-normal.woff2",
  "manifest.webmanifest", "icone/icona.svg", "icone/icona-192.png",
];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSIONE).then(c => c.addAll(BASE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(chiavi => Promise.all(chiavi.filter(k => k !== VERSIONE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;

  if (url.pathname.includes("/dati/")) {
    // dati: rete prima, copia di riserva
    e.respondWith(fetch(e.request).then(r => {
      const copia = r.clone();
      caches.open(VERSIONE).then(c => c.put(e.request, copia));
      return r;
    }).catch(() => caches.match(e.request)));
    return;
  }
  // resto del sito: copia locale subito, aggiornamento in background
  e.respondWith(caches.match(e.request, { ignoreSearch: true }).then(salvata => {
    const rete = fetch(e.request).then(r => {
      if (r.ok) { const copia = r.clone(); caches.open(VERSIONE).then(c => c.put(e.request, copia)); }
      return r;
    }).catch(() => salvata);
    return salvata || rete;
  }));
});
