"""Colonnine della Sicilia da Open Charge Map (OCM), terza fonte di confronto.

Serve per i dati FISSI e per le segnalazioni degli utenti ("rimossa", "non
funziona"), utili a capire le colonnine che compaiono in una sola fonte.

Chiave: obbligatoria e gratuita. Si legge dalla variabile d'ambiente OCM_CHIAVE
(su GitHub: segreto) oppure da config/ocm.local.json (escluso da Git).
Mai scriverla nel codice.

Licenze: i dati inseriti dagli utenti OCM sono CC BY 4.0; quelli importati da
altri fornitori hanno la licenza del fornitore. Ogni colonnina porta con sé il
nome del fornitore e la sua licenza, così si possono tenere solo quelle aperte.

Prova manuale:
    python -m raccolta.ocm            # scarica e salva stato/ocm.json
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from .osm import in_sicilia
from .pun import USER_AGENT

log = logging.getLogger("raccolta.ocm")

API = "https://api.openchargemap.io/v3"
RADICE = Path(__file__).resolve().parent.parent
FILE_OCM = RADICE / "stato" / "ocm.json"
FILE_CHIAVE = RADICE / "config" / "ocm.local.json"

# Tipi di presa OCM (ConnectionTypeID) -> nomi usati dalla PUN.
PRESE = {25: "IEC_62196_T2", 1036: "IEC_62196_T2", 33: "IEC_62196_T2_COMBO",
         2: "CHADEMO", 26: "IEC_62196_T3A", 28: "DOMESTIC_F", 27: "TESLA_S", 30: "TESLA_S"}


def leggi_chiave() -> str | None:
    chiave = os.environ.get("OCM_CHIAVE", "").strip()
    if not chiave and FILE_CHIAVE.exists():
        chiave = (json.loads(FILE_CHIAVE.read_text(encoding="utf-8")).get("chiave") or "").strip()
    return chiave if chiave and "QUI" not in chiave else None


def _get(percorso: str, parametri: dict, chiave: str):
    for prova in range(3):
        try:
            r = requests.get(f"{API}/{percorso}", params=parametri, timeout=120,
                             headers={"User-Agent": USER_AGENT, "X-API-Key": chiave})
            if r.status_code in (429, 502, 503, 504):
                log.warning("Open Charge Map occupato (%s), riprovo tra 60 s", r.status_code)
                time.sleep(60)
                continue
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            log.warning("Open Charge Map non raggiungibile: %s", e)
            time.sleep(30)
    raise RuntimeError(f"Open Charge Map non scaricato ({percorso})")


def _titoli(lista) -> dict:
    return {v["ID"]: v for v in (lista or []) if "ID" in v}


def normalizza(poi: dict, rif: dict) -> dict | None:
    """Punto OCM -> dizionario semplice, con stato, fornitore e licenza."""
    ind = poi.get("AddressInfo") or {}
    lat, lon = ind.get("Latitude"), ind.get("Longitude")
    if lat is None or lon is None:
        return None
    stato = rif["stati"].get(poi.get("StatusTypeID")) or {}
    fornitore = rif["fornitori"].get(poi.get("DataProviderID")) or {}
    licenza = (fornitore.get("License") or "").strip() or None
    operatore = (rif["operatori"].get(poi.get("OperatorID")) or {}).get("Title")
    if operatore and operatore.lower().startswith(("(unknown", "(business owner")):
        operatore = None
    prese = {}
    for c in poi.get("Connections") or []:
        std = PRESE.get(c.get("ConnectionTypeID"))
        if std:
            prese[std] = prese.get(std, 0) + (c.get("Quantity") or 1)
    commenti = sorted(poi.get("UserComments") or [], key=lambda c: c.get("DateCreated") or "", reverse=True)
    return {
        "id": f"ocm/{poi['ID']}",
        "lat": round(lat, 6), "lon": round(lon, 6),
        "operator": operatore,
        "name": ind.get("Title"),
        "stato": stato.get("Title"),
        "operativa": stato.get("IsOperational"),          # True / False / None (sconosciuto)
        "rimossa": poi.get("StatusTypeID") in (200, 210),  # 200 dismessa, 210 doppione
        "prese": prese or None,
        "posti": poi.get("NumberOfPoints"),
        "accesso": ind.get("AccessComments"),
        "costo": poi.get("UsageCost"),
        "verificata": poi.get("DateLastVerified"),
        "aggiornata": poi.get("DateLastStatusUpdate"),
        "fornitore": fornitore.get("Title"),
        "licenza": licenza,
        "ultimi_commenti": [{"data": (c.get("DateCreated") or "")[:10],
                             "tipo": (rif["commenti"].get(c.get("CommentTypeID")) or {}).get("Title"),
                             "esito": (rif["checkin"].get(c.get("CheckinStatusTypeID")) or {}).get("Title"),
                             "testo": (c.get("Comment") or "")[:300]} for c in commenti[:3]],
    }


def scarica(chiave: str) -> list[dict]:
    r = _get("referencedata/", {}, chiave)
    rif = {"stati": _titoli(r.get("StatusTypes")), "fornitori": _titoli(r.get("DataProviders")),
           "operatori": _titoli(r.get("Operators")), "commenti": _titoli(r.get("UserCommentTypes")),
           "checkin": _titoli(r.get("CheckinStatusTypes"))}
    punti = _get("poi/", {"output": "json", "countrycode": "IT", "maxresults": 5000,
                          "boundingbox": "(38.9,11.8),(35.2,15.7)",
                          "compact": "true", "verbose": "false", "includecomments": "true"}, chiave)
    return [c for c in (normalizza(p, rif) for p in punti) if c and in_sicilia(c["lat"], c["lon"])]


def salva(colonnine: list[dict], percorso: Path = FILE_OCM) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    tmp = percorso.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "scaricato": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fonte": "Open Charge Map (openchargemap.org); licenza indicata per ogni colonnina",
        "colonnine": colonnine,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(percorso)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.stdout.reconfigure(encoding="utf-8")
    chiave = leggi_chiave()
    if not chiave:
        print("Manca la chiave di Open Charge Map: vedi config/ocm.esempio.json")
        return 1
    colonnine = scarica(chiave)
    salva(colonnine)
    print(f"Open Charge Map: {len(colonnine)} colonnine salvate in {FILE_OCM.relative_to(RADICE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
