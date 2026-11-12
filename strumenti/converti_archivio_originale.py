"""Converte l'archivio del progetto originale (PalermoHub/evcharginglogsicilia,
fotografie complete della Sicilia) nel formato dell'archivio privato della zona hub.

Serve una volta sola, per avere subito dati storici da analizzare.
ATTENZIONE: l'archivio originale copre solo circa il 20% del tempo (vedi report).

Uso:
    python strumenti/converti_archivio_originale.py --originale originale/data --uscita hub-storico
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import duckdb
import pandas as pd

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

from raccolta import hub  # noqa: E402
from raccolta.modello import distanza_km  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--originale", default="originale/data")
    ap.add_argument("--uscita", default="hub-storico")
    args = ap.parse_args()
    cfg = hub.leggi_configurazione()
    if cfg is None:
        print("coordinate dell'hub non configurate (config/hub.local.json)")
        return 1
    uscita = Path(args.uscita)
    if uscita.exists() and any(uscita.iterdir()):
        print(f"{uscita} non è vuota: cancellala prima di riconvertire")
        return 1

    sorgente = f"{Path(args.originale).as_posix()}/**/*.parquet"
    con = duckdb.connect()
    # Margine di sicurezza sul rettangolo, poi distanza esatta in Python.
    gradi = cfg["raggio_km"] / 111 * 1.5
    righe = con.execute(f"""
        select ts, id_evse as id, stato_raw, cpo as operatore, corrente,
               potenza_w / 1000.0 as kw_max, real_time as tempo_reale, lat, lon,
               indirizzo, citta, cap, standard_connettore, n_connettori
        from read_parquet('{sorgente}', hive_partitioning = true)
        where lat between ? and ? and lon between ? and ?
    """, [cfg["lat"] - gradi, cfg["lat"] + gradi, cfg["lon"] - gradi * 1.3, cfg["lon"] + gradi * 1.3]).df()
    righe = righe[[distanza_km(cfg["lat"], cfg["lon"], la, lo) <= cfg["raggio_km"]
                   for la, lo in zip(righe["lat"], righe["lon"])]]
    giri = con.execute(f"""select ts, count(*) as n from read_parquet('{sorgente}', hive_partitioning = true)
                           group by ts order by ts""").df()

    righe["ts"] = pd.to_datetime(righe["ts"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    giri["ts"] = pd.to_datetime(giri["ts"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    righe = righe.sort_values(["id", "ts"])
    attese = int(giri["n"].max())

    # eventi = righe in cui lo stato cambia rispetto alla lettura precedente della stessa presa
    prima = righe.groupby("id")["stato_raw"].shift()
    eventi = righe[prima.isna() | (prima != righe["stato_raw"])]
    for giorno, g in eventi.groupby(eventi["ts"].str[:10]):
        hub._accoda_csv(uscita / "eventi" / giorno[:4] / f"{giorno}.csv", ["ts", "id", "stato_raw"],
                        g.sort_values(["ts", "id"])[["ts", "id", "stato_raw"]].values.tolist())

    zona = righe.groupby("ts").size()
    giri["zona"] = giri["ts"].map(zona).fillna(0).astype(int)
    for giorno, g in giri.groupby(giri["ts"].str[:10]):
        hub._accoda_csv(uscita / "cicli" / giorno[:4] / f"{giorno}.csv",
                        ["ts", "zona_osservate", "tutte_lette", "tutte_attese"],
                        [[t, z, n, attese] for t, z, n in zip(g["ts"], g["zona"], g["n"])])

    righe["giorno"] = righe["ts"].str[:10]
    prima_del_giorno = righe[righe["ts"] == righe.groupby("giorno")["ts"].transform("min")]
    for giorno, g in prima_del_giorno.groupby("giorno"):
        p = uscita / "anagrafica" / giorno[:4] / f"{giorno}.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        g = g.drop(columns=["giorno"]).copy()
        g["distanza_km"] = [round(distanza_km(cfg["lat"], cfg["lon"], la, lo), 3)
                            for la, lo in zip(g["lat"], g["lon"])]
        g.to_parquet(p, index=False, compression="zstd")
    # Le prese possono comparire anche dopo il primo giro del giorno: le aggiungiamo.
    for giorno, g in righe.groupby("giorno"):
        p = uscita / "anagrafica" / giorno[:4] / f"{giorno}.parquet"
        esistenti = pd.read_parquet(p)
        nuove = g[~g["id"].isin(esistenti["id"])].drop_duplicates("id").drop(columns=["giorno"])
        if not nuove.empty:
            nuove = nuove.assign(distanza_km=[round(distanza_km(cfg["lat"], cfg["lon"], la, lo), 3)
                                              for la, lo in zip(nuove["lat"], nuove["lon"])])
            pd.concat([esistenti, nuove], ignore_index=True).to_parquet(p, index=False, compression="zstd")

    print(f"convertiti {len(giri)} giri, {righe['id'].nunique()} prese, {len(eventi)} eventi -> {uscita}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
