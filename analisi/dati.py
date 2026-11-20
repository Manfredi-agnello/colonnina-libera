"""Lettura dell'archivio privato della zona hub e ricostruzione delle "letture".

Una LETTURA è: in questo istante questa presa era in questo stato.
L'archivio salva solo i cambi di stato (eventi), quindi le letture si
ricostruiscono così:
  - gli istanti di lettura sono i giri COMPLETI (registro cicli/) più gli
    istanti degli eventi;
  - lo stato in ogni istante è quello dell'ultimo evento precedente;
  - una presa conta come letta solo nei giorni in cui compare nella
    fotografia giornaliera (anagrafica/): così una colonnina rimossa non
    resta "viva" per sempre con l'ultimo stato noto.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class Dati:
    letture: pd.DataFrame      # id, ts (UTC), stato_raw
    anagrafica: pd.DataFrame   # una riga per presa: id, operatore, corrente, kw_max, ...
    cicli: pd.DataFrame        # ts, completo
    presenza: pd.DataFrame = None   # id, giorno (AAAA-MM-GG): in quali giorni ogni presa esisteva


def _leggi_csv(cartella: Path, schema: str) -> pd.DataFrame:
    file = sorted(cartella.glob(schema))
    if not file:
        return pd.DataFrame()
    return pd.concat([pd.read_csv(f, dtype=str) for f in file], ignore_index=True)


def carica(cartella: Path, quota_giro_completo: float = 0.95) -> Dati:
    cartella = Path(cartella)
    eventi = _leggi_csv(cartella / "eventi", "*/*.csv")
    cicli = _leggi_csv(cartella / "cicli", "*/*.csv")
    if eventi.empty or cicli.empty:
        raise ValueError(f"archivio vuoto o incompleto in {cartella}")

    eventi["ts"] = pd.to_datetime(eventi["ts"], utc=True)
    cicli["ts"] = pd.to_datetime(cicli["ts"], utc=True)
    for c in ("tutte_lette", "tutte_attese"):
        cicli[c] = cicli[c].astype(int)
    cicli["completo"] = cicli["tutte_lette"] >= quota_giro_completo * cicli["tutte_attese"]

    # Fotografie giornaliere: presenza per giorno + attributi (la più recente vince).
    foto = []
    for f in sorted((cartella / "anagrafica").glob("*/*.parquet")):
        df = pd.read_parquet(f)
        df["giorno"] = f.stem
        foto.append(df)
    foto = pd.concat(foto, ignore_index=True)
    presenza = foto[["id", "giorno"]].drop_duplicates()
    anagrafica = (foto.sort_values("giorno").groupby("id").tail(1)
                  .drop(columns=["giorno"]).reset_index(drop=True))

    # Istanti di lettura = giri completi ∪ istanti degli eventi.
    istanti = pd.concat([cicli.loc[cicli["completo"], "ts"], eventi["ts"]]).drop_duplicates()
    istanti = pd.DataFrame({"ts": istanti.sort_values().reset_index(drop=True)})
    istanti["giorno"] = istanti["ts"].dt.strftime("%Y-%m-%d")
    griglia = presenza.merge(istanti, on="giorno")

    # Stato = ultimo evento della stessa presa a quell'istante o prima.
    griglia = griglia.sort_values("ts")
    eventi = eventi.sort_values("ts")
    letture = pd.merge_asof(griglia, eventi, on="ts", by="id", direction="backward")
    letture = (letture.dropna(subset=["stato_raw"])[["id", "ts", "stato_raw"]]
               .sort_values(["id", "ts"]).reset_index(drop=True))
    return Dati(letture=letture, anagrafica=anagrafica,
                cicli=cicli[["ts", "completo"]].sort_values("ts").reset_index(drop=True),
                presenza=presenza.reset_index(drop=True))


def carica_ipotesi(percorso: Path) -> dict:
    return json.loads(Path(percorso).read_text(encoding="utf-8"))
