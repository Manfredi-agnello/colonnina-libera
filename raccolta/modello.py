"""Trasforma un record grezzo della PUN in un dizionario semplice e stabile.

Qui si decide quali campi teniamo (solo quelli utili) e come si chiamano.
"""
from __future__ import annotations

import math

# Stati grezzi della PUN raggruppati in categorie comprensibili per il sito.
CATEGORIA_STATO = {
    "AVAILABLE": "libera",
    "CHARGING": "occupata",
    "RESERVED": "occupata",
    "OUTOFORDER": "guasta",
    "INOPERATIVE": "guasta",
    "BLOCKED": "guasta",
    "UNKNOWN": "sconosciuto",
    "PLANNED": "in_arrivo",
    "REMOVED": "rimossa",
}


def categoria(stato_raw: str | None) -> str:
    return CATEGORIA_STATO.get((stato_raw or "").upper(), "sconosciuto")


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _testo(v):
    s = str(v).strip() if v is not None else ""
    return s or None


def _tariffe(rec: dict) -> dict | None:
    """Tariffe pubblicate sulla PUN (presenti solo per poche colonnine)."""
    t = rec.get("punTariffsDetails") or {}
    out = {}
    for chiave, nome in (("acTariff", "ac"), ("dcTariff", "dc"), ("hpcTariff", "hpc")):
        v = t.get(chiave) or {}
        voci = {k: v[k] for k in ("energy", "time", "parking", "activation")
                if v.get(k) is not None}
        if voci:
            out[nome] = voci
    return out or None


def normalizza(rec: dict) -> dict | None:
    """Record PUN -> dizionario. None se mancano id o coordinate."""
    loc = rec.get("location") or {}
    coord = rec.get("coordinates") or loc.get("coordinates") or {}
    lat, lon = _num(coord.get("latitude")), _num(coord.get("longitude"))
    id_evse = _testo(rec.get("evse_id"))
    if not id_evse or lat is None or lon is None:
        return None

    connettori = []
    for c in rec.get("connectors") or []:
        kw = _num(c.get("max_electric_power"))
        connettori.append({
            "standard": _testo(c.get("standard")),
            "corrente": _testo(c.get("power_type")),
            "kw": round(kw / 1000, 1) if kw else None,
        })
    potenze = [c["kw"] for c in connettori if c["kw"]]
    correnti = {(c["corrente"] or "").upper() for c in connettori}
    orari = loc.get("opening_times") or {}

    return {
        "id": id_evse,
        "sito": _testo(rec.get("locationId") or loc.get("_id")),
        "lat": round(lat, 6),
        "lon": round(lon, 6),
        "stato_raw": _testo(rec.get("status")),
        "tempo_reale": bool(rec.get("realTime")),
        "operatore": _testo(rec.get("businessName")),
        "indirizzo": _testo(loc.get("address")),
        "citta": _testo(loc.get("city")),
        "provincia": _testo(loc.get("state")),
        "regione": _testo(loc.get("region")),
        "cap": _testo(loc.get("postal_code")),
        "parcheggio": _testo(loc.get("parking_type")),
        "servizi": list(loc.get("facilities") or []),
        "h24": bool(orari.get("twentyfourseven", False)),
        "connettori": connettori,
        "kw_max": max(potenze) if potenze else None,
        "corrente": "DC" if "DC" in "".join(correnti) else ("AC" if correnti - {""} else None),
        "tariffe_pun": _tariffe(rec),
        "pubblicazione": _testo(rec.get("publicationStatus")),
    }


def distanza_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distanza in linea d'aria (formula dell'emisenoverso)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
