"""File pubblici per il sito: stato attuale delle colonnine e stato della raccolta.

live.json viene SOVRASCRITTO ad ogni giro e pubblicato direttamente sul sito:
non entra nella storia di Git, quindi non fa crescere il repository.
"""
from __future__ import annotations

import json
from pathlib import Path

from .modello import categoria


def _scrivi_json(percorso: Path, dati) -> None:
    percorso.parent.mkdir(parents=True, exist_ok=True)
    tmp = percorso.with_suffix(".tmp")
    tmp.write_text(json.dumps(dati, ensure_ascii=False, separators=(",", ":")),
                   encoding="utf-8")
    tmp.replace(percorso)   # scrittura "atomica": il sito non legge mai un file a metà


def scrivi_live(colonnine: list[dict], aggiornato: str, cartella: Path) -> dict:
    """Raggruppa le colonnine per sito (stesso indirizzo/parcheggio) e scrive live.json."""
    siti: dict[str, dict] = {}
    for c in colonnine:
        chiave = c["sito"] or f'{c["lat"]:.5f},{c["lon"]:.5f}'
        s = siti.setdefault(chiave, {
            "id": chiave,
            "lat": c["lat"], "lon": c["lon"],
            "operatore": c["operatore"], "indirizzo": c["indirizzo"],
            "citta": c["citta"], "provincia": c["provincia"],
            "parcheggio": c["parcheggio"], "servizi": c["servizi"],
            "h24": c["h24"], "punti": [],
        })
        s["punti"].append({
            "id": c["id"],
            "stato": categoria(c["stato_raw"]),
            "tempo_reale": c["tempo_reale"],
            "kw": c["kw_max"],
            "corrente": c["corrente"],
            "connettori": [[k["standard"], k["kw"]] for k in c["connettori"]],
            **({"tariffe_pun": c["tariffe_pun"]} if c["tariffe_pun"] else {}),
        })
    elenco = [s for s in siti.values()
              if any(p["stato"] != "rimossa" for p in s["punti"])]
    _scrivi_json(cartella / "live.json", {"aggiornato": aggiornato, "siti": elenco})
    return {"siti": len(elenco), "punti": sum(len(s["punti"]) for s in elenco)}


def scrivi_stato_raccolta(info: dict, cartella: Path) -> None:
    """stato.json: usato dal badge "ultimo aggiornamento" del sito.
    "aggiornato" = ora dei dati mostrati sulla mappa."""
    _scrivi_json(cartella / "stato.json", {**info, "ultimo_tentativo": info["aggiornato"],
                                           "esito_ultimo_tentativo": "ok"})


def aggiorna_tentativo(cartella: Path, ts: str, esito: str) -> None:
    """Giro fallito: si annota il tentativo ma "aggiornato" resta quello dei dati vecchi."""
    p = cartella / "stato.json"
    info = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"aggiornato": None}
    info.update({"ultimo_tentativo": ts, "esito_ultimo_tentativo": esito})
    _scrivi_json(p, info)
