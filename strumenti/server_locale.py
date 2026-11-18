"""Server per vedere il sito sul proprio computer, senza cache del browser.

Uso:  python strumenti/server_locale.py          poi apri http://localhost:8080
      python strumenti/server_locale.py --rete   anche dal telefono, sulla stessa rete Wi-Fi
(prima copia i dati: cp out/sito/*.json sito/dati/)

Con --rete il sito è visibile a tutti i dispositivi della tua rete Wi-Fi (non da
Internet). Windows può chiedere il permesso al firewall: scegli solo "Reti private".
Usalo a casa, non su Wi-Fi pubblici, e chiudilo (Ctrl+C) quando hai finito.
Limite: senza HTTPS il telefono non concede la posizione ("Vicino a me") e non
installa il sito come app; tutto il resto si può provare.
"""
import argparse
import functools
import http.server
import socket
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent.parent / "sito"


class SenzaCache(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map,
                      ".mjs": "text/javascript", ".js": "text/javascript",
                      ".webmanifest": "application/manifest+json", ".woff2": "font/woff2"}

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def ip_locale() -> str:
    """Indirizzo del computer nella rete di casa (nessun dato viene inviato fuori)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("192.168.1.1", 80))   # UDP: serve solo a scegliere la scheda di rete
            return s.getsockname()[0]
        except OSError:
            return "IP-DEL-COMPUTER"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rete", action="store_true", help="rendi il sito visibile ai dispositivi della rete Wi-Fi")
    ap.add_argument("--porta", type=int, default=8080)
    args = ap.parse_args()
    indirizzo = "0.0.0.0" if args.rete else "127.0.0.1"
    gestore = functools.partial(SenzaCache, directory=str(CARTELLA))
    print(f"Sito su http://localhost:{args.porta}")
    if args.rete:
        print(f"Dal telefono (stessa Wi-Fi): http://{ip_locale()}:{args.porta}   - Ctrl+C per chiudere")
    http.server.ThreadingHTTPServer((indirizzo, args.porta), gestore).serve_forever()
