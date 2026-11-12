"""Misura quanto coincidono PUN e OpenStreetMap (non cambia il sito).

    python strumenti/confronta_osm.py

Legge sito/dati/live.json (PUN) e stato/osm.json oppure stato/osm_grezzo.json,
stampa i numeri e scrive out/incrocio_osm.csv per i controlli a mano.
"""
from __future__ import annotations

import csv
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
from raccolta.incrocio import abbina, distanza_m, parole_operatore  # noqa: E402
from raccolta.osm import FILE_OSM, da_risposta  # noqa: E402


def carica_osm() -> list[dict]:
    if FILE_OSM.exists():
        return json.loads(FILE_OSM.read_text(encoding="utf-8"))["colonnine"]
    grezzo = RADICE / "stato" / "osm_grezzo.json"
    return da_risposta(json.loads(grezzo.read_text(encoding="utf-8")))


def ha_ccs_pun(sito):
    return any(std == "IEC_62196_T2_COMBO" for p in sito["punti"] for std, _ in p["connettori"])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    siti = json.loads((RADICE / "sito/dati/live.json").read_text(encoding="utf-8"))["siti"]
    osm = carica_osm()
    righe, sola_osm = abbina(siti, osm)

    print(f"Siti PUN: {len(siti)}   Colonnine OSM in Sicilia: {len(osm)}\n")
    conta = Counter(r["esito"] for r in righe)
    nomi = {"confermata": "confermata (≤50 m, stesso operatore)",
            "probabile": "probabile (≤50 m senza operatore OSM, o ≤150 m stesso operatore)",
            "probabile_lontana": "da controllare (50–150 m, operatore OSM non indicato)",
            "dubbia": "dubbia (≤150 m, operatore diverso)",
            "solo_pun": "solo PUN (niente in OSM entro 150 m)"}
    for k, testo in nomi.items():
        print(f"  {conta[k]:5d}  {conta[k] / len(siti):5.1%}  {testo}")

    dist = [r["distanza_m"] for r in righe if r["osm"]]
    if dist:
        dist.sort()
        print(f"\nDistanza tra le due posizioni (siti abbinati): mediana {statistics.median(dist):.0f} m, "
              f"9 su 10 entro {dist[int(len(dist) * 0.9)]} m, oltre 30 m: {sum(d > 30 for d in dist)}")

    # Prese: CCS presente in entrambe le fonti?
    confronto = Counter()
    for r in righe:
        if r["esito"] in ("confermata", "probabile") and r["osm"].get("prese"):
            confronto[(ha_ccs_pun(r["sito"]), "IEC_62196_T2_COMBO" in r["osm"]["prese"])] += 1
    if confronto:
        print("\nPresa rapida CCS (solo siti abbinati con prese indicate in OSM):")
        print(f"  d'accordo: {confronto[(True, True)] + confronto[(False, False)]}   "
              f"solo PUN: {confronto[(True, False)]}   solo OSM: {confronto[(False, True)]}")

    print(f"\nColonnine OSM senza corrispondenza nella PUN: {len(sola_osm)}")
    accesso = Counter((c.get("access") or "non indicato") for c in sola_osm)
    print("  per accesso: " + ", ".join(f"{k} {v}" for k, v in accesso.most_common()))
    vicine = sum(any(distanza_m(c["lat"], c["lon"], s["lat"], s["lon"]) < 400 for s in siti) for c in sola_osm)
    print(f"  di cui con un sito PUN entro 400 m (forse la stessa, spostata o doppia): {vicine}")
    op = Counter((c.get("operator") or c.get("brand") or c.get("network") or "non indicato") for c in sola_osm)
    print("  operatori più frequenti: " + ", ".join(f"{k} {v}" for k, v in op.most_common(12)))

    uscita = RADICE / "out" / "incrocio_osm.csv"
    uscita.parent.mkdir(exist_ok=True)
    with uscita.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["esito", "distanza_m", "operatore_pun", "indirizzo_pun", "citta", "operatore_osm",
                    "nome_osm", "accesso_osm", "id_osm", "lat", "lon", "mappa"])
        for r in righe:
            s, o = r["sito"], r["osm"] or {}
            w.writerow([r["esito"], r["distanza_m"], s.get("operatore"), s.get("indirizzo"), s.get("citta"),
                        o.get("operator") or o.get("brand") or o.get("network"), o.get("name"), o.get("access"),
                        o.get("id"), s["lat"], s["lon"],
                        f"https://www.openstreetmap.org/?mlat={s['lat']}&mlon={s['lon']}#map=19/{s['lat']}/{s['lon']}"])
        for o in sola_osm:
            w.writerow(["solo_osm", None, None, None, None, o.get("operator") or o.get("brand") or o.get("network"),
                        o.get("name"), o.get("access"), o["id"], o["lat"], o["lon"],
                        f"https://www.openstreetmap.org/{o['id']}"])
    print(f"\nDettaglio per i controlli: {uscita.relative_to(RADICE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
