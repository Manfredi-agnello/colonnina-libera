"""Colonnine della Sicilia da OpenStreetMap (OSM), tramite il servizio Overpass.

Serve solo per i dati FISSI (posizione, operatore, prese, orari, accesso):
lo stato in tempo reale resta quello della PUN.

Rispetto della fonte (regole di overpass-api.de): una sola richiesta al giorno,
circa 1 MB, user agent che dichiara il progetto, attesa lunga se il server
risponde "troppe richieste" (429) o "occupato" (504).

Licenza: dati © contributori di OpenStreetMap, ODbL. Il file prodotto resta
SEPARATO dai dati PUN (vedi METODO.md, "Incrocio delle fonti").

Prova manuale:
    python -m raccolta.osm            # scarica e salva stato/osm.json
"""
from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from .pun import USER_AGENT

log = logging.getLogger("raccolta.osm")

SERVER = ["https://overpass-api.de/api/interpreter",
          "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
          "https://overpass.private.coffee/api/interpreter"]
# Rettangolo attorno alla Sicilia (lo stesso di config/area.json): è la richiesta più
# leggera per il server. Il rettangolo comprende anche Malta e un pezzo di Calabria,
# che vengono tolti da in_sicilia().
QUERY = """[out:json][timeout:120];
nwr["amenity"="charging_station"](35.2,11.8,38.9,15.7);
out center tags;"""


def in_sicilia(lat: float, lon: float) -> bool:
    """Toglie dal rettangolo Malta e la costa calabra dello Stretto."""
    if 35.75 < lat < 36.10 and 14.15 < lon < 14.60:          # Malta e Gozo
        return False
    if lat > 37.90:                                          # Stretto di Messina
        confine = 15.645 if lat >= 38.23 else 15.60
        if lon > confine:
            return False
    return True

RADICE = Path(__file__).resolve().parent.parent
FILE_OSM = RADICE / "stato" / "osm.json"

# Prese: tag OSM -> nomi usati dalla PUN (così si possono confrontare).
PRESE = {
    "socket:type2": "IEC_62196_T2",
    "socket:type2_cable": "IEC_62196_T2",
    "socket:type2_combo": "IEC_62196_T2_COMBO",
    "socket:chademo": "CHADEMO",
    "socket:type3a": "IEC_62196_T3A",
    "socket:schuko": "DOMESTIC_F",
    "socket:tesla_supercharger": "TESLA_S",
}
TAG_UTILI = ["name", "operator", "brand", "network", "access", "opening_hours", "fee",
             "charge", "capacity", "ref", "check_date", "start_date", "parking:fee",
             "maxstay", "description", "website", "level", "covered"]


def _numero(v):
    try:
        return int(str(v).split(";")[0].strip())
    except (TypeError, ValueError):
        return None


def normalizza(el: dict) -> dict | None:
    """Elemento Overpass -> dizionario semplice. None se senza coordinate."""
    if el["type"] == "node":
        lat, lon = el.get("lat"), el.get("lon")
    else:
        c = el.get("center") or {}
        lat, lon = c.get("lat"), c.get("lon")
    if lat is None or lon is None:
        return None
    tag = el.get("tags") or {}
    prese = {}
    for chiave, standard in PRESE.items():
        n = _numero(tag.get(chiave))
        if tag.get(chiave) == "yes":
            n = n or 1
        if n:
            prese[standard] = prese.get(standard, 0) + n
    return {
        "id": f"{el['type']}/{el['id']}",
        "lat": round(lat, 6), "lon": round(lon, 6),
        "prese": prese or None,
        **{k.replace(":", "_"): tag[k] for k in TAG_UTILI if tag.get(k)},
    }


def da_risposta(risposta: dict) -> list[dict]:
    """Risposta JSON di Overpass -> colonnine normalizzate, solo in Sicilia."""
    return [c for c in map(normalizza, risposta.get("elements", []))
            if c and in_sicilia(c["lat"], c["lon"])]


def scarica(tentativi: int = 3, attesa: int = 60, timeout: int = 180) -> list[dict]:
    """Scarica le colonnine OSM della Sicilia. Solleva un'eccezione se fallisce."""
    ultimo_errore = None
    for prova in range(tentativi):
        server = SERVER[prova % len(SERVER)]
        try:
            r = requests.post(server, data={"data": QUERY}, timeout=timeout,
                              headers={"User-Agent": USER_AGENT})
            if r.status_code in (429, 502, 503, 504):
                ultimo_errore = f"{server}: HTTP {r.status_code}"
                log.warning("Overpass occupato (%s), riprovo con un altro server", r.status_code)
                time.sleep(attesa)
                continue
            r.raise_for_status()
            return da_risposta(r.json())
        except (requests.RequestException, ValueError) as e:
            ultimo_errore = f"{server}: {e}"
            log.warning("Overpass non raggiungibile: %s", e)
            time.sleep(attesa // 2)
    raise RuntimeError(f"OpenStreetMap non scaricato: {ultimo_errore}")


def salva(colonnine: list[dict], percorso: Path = FILE_OSM) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    tmp = percorso.with_suffix(".tmp")
    tmp.write_text(json.dumps({
        "scaricato": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "licenza": "© contributori di OpenStreetMap, ODbL 1.0 (openstreetmap.org/copyright)",
        "colonnine": colonnine,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(percorso)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.stdout.reconfigure(encoding="utf-8")
    colonnine = scarica()
    salva(colonnine)
    print(f"OpenStreetMap: {len(colonnine)} colonnine salvate in {FILE_OSM.relative_to(RADICE)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
