"""Archivio PRIVATO della zona hub. Scrive solo in una cartella che, su GitHub,
è un repository privato separato. Questo modulo non stampa mai dati nei log
(i log di GitHub Actions di un repository pubblico sono visibili a tutti).

Struttura della cartella:
  cicli/AAAA/AAAA-MM-GG.csv     una riga per ogni giro: ts, colonnine osservate, colonnine attese
                                (serve a sapere quando la raccolta ha avuto buchi)
  eventi/AAAA/AAAA-MM-GG.csv    una riga SOLO quando una colonnina cambia stato: ts, id, stato_raw
  anagrafica/AAAA/AAAA-MM-GG.parquet  fotografia completa (tutti i campi), una al giorno
  ultimo_stato.json             stato più recente di ogni colonnina (per trovare i cambi)

Gestite da altri programmi:
  riassunti/AAAA-MM.json, report/, README.md   report mensili (workflow "report"), permanenti
  eventi/ripartenza/stato.csv, manutenzione.json  cancellazione oltre 12 mesi (raccolta/manutenzione.py)

Date e orari in UTC (ora italiana = UTC+1 d'inverno, UTC+2 d'estate).
I file CSV crescono solo in coda: Git li comprime molto bene.
"""
from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import pandas as pd

from .modello import distanza_km

RADICE = Path(__file__).resolve().parent.parent


def leggi_configurazione() -> dict | None:
    """Coordinate dell'hub: dai segreti (variabili d'ambiente) o da config/hub.local.json."""
    if os.environ.get("HUB_LAT") and os.environ.get("HUB_LON"):
        return {"lat": float(os.environ["HUB_LAT"]), "lon": float(os.environ["HUB_LON"]),
                "raggio_km": float(os.environ.get("HUB_RAGGIO_KM") or 3)}
    locale = RADICE / "config" / "hub.local.json"
    if locale.exists():
        d = json.loads(locale.read_text(encoding="utf-8"))
        return {"lat": float(d["lat"]), "lon": float(d["lon"]),
                "raggio_km": float(d.get("raggio_km", 3))}
    return None


def _accoda_csv(percorso: Path, intestazione: list[str], righe: list[list]) -> None:
    nuovo = not percorso.exists()
    percorso.parent.mkdir(parents=True, exist_ok=True)
    with percorso.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if nuovo:
            w.writerow(intestazione)
        w.writerows(righe)


def aggiorna(colonnine: list[dict], attese_ids: set[str], ts: str,
             cfg: dict, cartella: Path) -> None:
    """colonnine = quelle lette in questo giro; attese_ids = tutte quelle che
    avremmo dovuto leggere (per capire se il giro è stato completo)."""
    vicine = [c for c in colonnine
              if distanza_km(cfg["lat"], cfg["lon"], c["lat"], c["lon"]) <= cfg["raggio_km"]]
    giorno = ts[:10]
    anno = ts[:4]

    # 1. stato precedente -> eventi (solo i cambi)
    p_ultimo = cartella / "ultimo_stato.json"
    ultimo = json.loads(p_ultimo.read_text(encoding="utf-8")) if p_ultimo.exists() else {}
    eventi = []
    for c in sorted(vicine, key=lambda x: x["id"]):
        if ultimo.get(c["id"]) != c["stato_raw"]:
            eventi.append([ts, c["id"], c["stato_raw"]])
            ultimo[c["id"]] = c["stato_raw"]
    if eventi:
        _accoda_csv(cartella / "eventi" / anno / f"{giorno}.csv",
                    ["ts", "id", "stato_raw"], eventi)

    # 2. registro del giro (anche quando non cambia niente: distingue "nessun cambio" da "nessun dato")
    letti = {c["id"] for c in colonnine}
    _accoda_csv(cartella / "cicli" / anno / f"{giorno}.csv",
                ["ts", "zona_osservate", "tutte_lette", "tutte_attese"],
                [[ts, len(vicine), len(letti), len(attese_ids)]])

    # 3. fotografia completa: la prima del giorno
    p_foto = cartella / "anagrafica" / anno / f"{giorno}.parquet"
    if not p_foto.exists() and vicine:
        p_foto.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(vicine)
        df.insert(0, "ts", ts)
        for col in ("connettori", "servizi", "tariffe_pun", "orari"):
            if col not in df:
                continue
            df[col] = df[col].map(lambda v: json.dumps(v, ensure_ascii=False) if v else None)
        df["distanza_km"] = [round(distanza_km(cfg["lat"], cfg["lon"], la, lo), 3)
                             for la, lo in zip(df.lat, df.lon)]
        df.to_parquet(p_foto, index=False, compression="zstd")

    tmp = p_ultimo.with_suffix(".tmp")
    tmp.write_text(json.dumps(ultimo, ensure_ascii=False, indent=0, sort_keys=True),
                   encoding="utf-8")
    tmp.replace(p_ultimo)
