"""Confronto a tre fonti: PUN, OpenStreetMap, Open Charge Map (non cambia il sito).

    python strumenti/confronta_fonti.py

Legge sito/dati/live.json, stato/osm.json (o osm_grezzo.json), stato/ocm.json.
Stampa i numeri e scrive out/colonnine_fuori_pun.csv per i controlli a mano.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))
from raccolta.incrocio import abbina, distanza_m  # noqa: E402
from raccolta.ocm import FILE_OCM  # noqa: E402
from strumenti.confronta_osm import carica_osm  # noqa: E402

ABBINATA = ("confermata", "probabile")


def nome_op(c):
    return c.get("operator") or c.get("brand") or c.get("network")


def vicino_pun(c, siti, metri=400):
    return min((distanza_m(c["lat"], c["lon"], s["lat"], s["lon"]) for s in siti), default=1e9) < metri


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    siti = json.loads((RADICE / "sito/dati/live.json").read_text(encoding="utf-8"))["siti"]
    osm = carica_osm()
    ocm = json.loads(FILE_OCM.read_text(encoding="utf-8"))["colonnine"]
    print(f"PUN {len(siti)} siti · OpenStreetMap {len(osm)} · Open Charge Map {len(ocm)}\n")

    r_osm, solo_osm = abbina(siti, osm)
    r_ocm, solo_ocm = abbina(siti, ocm)
    for nome, righe in (("OpenStreetMap", r_osm), ("Open Charge Map", r_ocm)):
        c = Counter(r["esito"] for r in righe)
        print(f"PUN vs {nome}: confermate {c['confermata']}, probabili {c['probabile']}, "
              f"da controllare {c['probabile_lontana']}, dubbie {c['dubbia']}, assenti {c['solo_pun']}")

    fonti = Counter()
    for a, b in zip(r_osm, r_ocm):
        fonti[1 + (a["esito"] in ABBINATA) + (b["esito"] in ABBINATA)] += 1
    print("\nSiti PUN presenti in quante fonti: " +
          ", ".join(f"{k} fonte/i: {v} ({v / len(siti):.0%})" for k, v in sorted(fonti.items())))

    # Le colonnine che NON sono nella PUN: le altre due fonti sono d'accordo?
    lontane_osm = [c for c in solo_osm if not vicino_pun(c, siti)]
    lontane_ocm = [c for c in solo_ocm if not vicino_pun(c, siti)]
    come_siti = [{**c, "operatore": nome_op(c)} for c in lontane_osm]
    incrocio, solo_ocm_lontane = abbina(come_siti, lontane_ocm)
    print(f"\nFuori dalla PUN (nessun sito PUN entro 400 m): OpenStreetMap {len(lontane_osm)}, "
          f"Open Charge Map {len(lontane_ocm)}")
    entrambe = [r for r in incrocio if r["osm"]]
    print(f"  presenti in ENTRAMBE le altre fonti: {len(entrambe)}")
    print(f"  solo OpenStreetMap: {len(incrocio) - len(entrambe)}   solo Open Charge Map: {len(solo_ocm_lontane)}")

    righe_csv = []
    for r in incrocio:
        o, m = r["sito"], r["osm"] or {}
        righe_csv.append(["OSM+OCM" if m else "solo OSM", nome_op(o), o.get("name"), m.get("stato"),
                          (m.get("verificata") or "")[:10], o.get("access"), o["id"], m.get("id"), o["lat"], o["lon"]])
    for m in solo_ocm_lontane:
        righe_csv.append(["solo OCM", m.get("operator"), m.get("name"), m.get("stato"),
                          (m.get("verificata") or "")[:10], None, None, m["id"], m["lat"], m["lon"]])
    print("\n  Dettaglio (fonti · operatore · stato OCM · ultima verifica OCM):")
    for x in sorted(righe_csv, key=lambda x: x[0]):
        print(f"   {x[0]:9s} {str(x[1])[:28]:28s} {str(x[3] or '-')[:26]:26s} {x[4] or '-'}")

    uscita = RADICE / "out" / "colonnine_fuori_pun.csv"
    uscita.parent.mkdir(exist_ok=True)
    with uscita.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["fonti", "operatore", "nome", "stato_ocm", "verificata_ocm", "accesso_osm",
                    "id_osm", "id_ocm", "lat", "lon", "mappa"])
        for x in righe_csv:
            w.writerow(x + [f"https://www.openstreetmap.org/?mlat={x[8]}&mlon={x[9]}#map=18/{x[8]}/{x[9]}"])
    print(f"\nDettaglio per i controlli: {uscita.relative_to(RADICE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
