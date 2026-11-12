"""Server per vedere il sito sul proprio computer, senza cache del browser.

Uso:  python strumenti/server_locale.py      poi apri http://localhost:8080
(prima copia i dati: cp out/sito/*.json sito/dati/)
"""
import functools
import http.server
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent.parent / "sito"


class SenzaCache(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".mjs": "text/javascript", ".js": "text/javascript",
                      ".webmanifest": "application/manifest+json", ".woff2": "font/woff2"}

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


if __name__ == "__main__":
    gestore = functools.partial(SenzaCache, directory=str(CARTELLA))
    http.server.ThreadingHTTPServer(("127.0.0.1", 8080), gestore).serve_forever()
