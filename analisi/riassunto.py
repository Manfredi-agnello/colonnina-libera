"""Riassunto di un periodo dell'archivio privato, come dizionario JSON.

È la base sia del report mensile (Markdown con grafici) sia del file permanente
riassunti/AAAA-MM.json, che resta anche dopo la cancellazione dei dati grezzi
(oltre 12 mesi): così si possono confrontare i mesi tra anni diversi.

Contiene solo numeri aggregati sulle colonnine (nessun dato personale).
"""
from __future__ import annotations

import math
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from . import calcoli

VERSIONE = 1   # cambia se cambia il formato del file

# Stesso operatore scritto in modi diversi nella PUN (verificato dal codice delle prese:
# IT*ENX, IT*PLN, IT*GES). Stessi nomi del sito (sito/js/comune.js).
NOMI_OPERATORI = {
    "ENEL X WAY ITALIA SRL": "Enel X Way", "ENX": "Enel X Way",
    "BEC": "Plenitude (Be Charge)", "Plenitude On The Road S.r.l.": "Plenitude (Be Charge)",
    "Go Electric Stations SRLS": "DriWe", "UnoEnergy DriWe spa": "DriWe",
    "EWIVA SRL": "Ewiva", "Eurospin Sicilia S.p.a. a Socio Unico": "Eurospin",
    "Enerhub Srl": "Enerhub", "DUFERCO MOBILITY SRL": "Duferco", "A2A E.MOBILITY S.R.L.": "A2A",
    "Tesla Italia Srl.": "Tesla", "UAU srl": "UAU", "Repower Vendita Italia SpA": "Repower",
}


def nome_operatore(n):
    return NOMI_OPERATORI.get(n, n) if isinstance(n, str) else n


def _num(v, cifre=1):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else round(f, cifre)


def _valore(v):
    if isinstance(v, (float, np.floating)):
        return _num(v)
    if isinstance(v, np.integer):
        return int(v)
    return v


def _righe(df: pd.DataFrame) -> list[dict]:
    return [{k: _valore(v) for k, v in r.items()} for r in df.to_dict("records")]


def calcola(*, primo: date, ultimo: date, tab: pd.DataFrame, sessioni: pd.DataFrame,
            kwh: pd.DataFrame, ipotesi: dict, anagrafica: pd.DataFrame, op_occupazione: set,
            presenza: pd.DataFrame | None) -> dict:
    n_giorni = (ultimo - primo).days + 1
    ids = set(tab["id"].unique()) if not tab.empty else set()
    prese = anagrafica[anagrafica["id"].isin(ids)]
    minuti_tot = len(tab) * 60
    copertura = 100 * (tab["min_osservati"].sum() + tab["min_altro"].sum()) / minuti_tot if minuti_tot else None
    valide = sessioni[sessioni["valida"]] if not sessioni.empty else sessioni
    kwh_sess = float(valide["kwh_stimati"].sum()) if not valide.empty else 0.0
    if tab.empty:
        occ_media = guasto_medio = kwh_occ_giorno = None
    else:
        tutte = calcoli.percentuali(tab.assign(tutte=1), ["tutte"]).iloc[0]
        occ_media, guasto_medio = tutte["occupazione_pct"], tutte["guasto_pct"]
        ko = calcoli.kwh_da_occupazione(tab.assign(tutte=1), ipotesi["energia"], ["tutte"])
        kwh_occ_giorno = float(ko["kwh_estrapolati"].sum()) / n_giorni

    # Occupazione per ora: giorni feriali (lun-ven) e fine settimana, per classe e in totale.
    def orario(df):
        out = {}
        for nome, giorni in (("feriali", [0, 1, 2, 3, 4]), ("fine_settimana", [5, 6])):
            p = calcoli.percentuali(df[df["giorno_settimana"].isin(giorni)], ["ora"]).set_index("ora")
            out[nome] = [_num(p["occupazione_pct"].get(h)) if h in p.index else None for h in range(24)]
        return out
    occupazione_oraria = {"tutte": orario(tab)} if not tab.empty else {}
    if not tab.empty:
        for classe, g in tab.groupby("classe"):
            occupazione_oraria[classe] = orario(g)

    def riepilogo(per: str) -> list[dict]:
        if tab.empty:
            return []
        if per == "operatore":   # righe dello stesso operatore unite
            return riepilogo_su(tab.assign(operatore=tab["operatore"].map(nome_operatore)),
                                valide.assign(operatore=valide["operatore"].map(nome_operatore))
                                if not valide.empty else valide, per)
        return riepilogo_su(tab, valide, per)

    def riepilogo_su(tab, valide, per: str) -> list[dict]:
        p = calcoli.percentuali(tab, [per]).set_index(per)
        n = tab.drop_duplicates("id").groupby(per)["id"].nunique().rename("prese")
        sv = (valide.groupby(per).agg(sessioni=("id", "size"), durata_media_min=("durata_min", "mean"),
                                      kwh_sessioni=("kwh_stimati", "sum"))
              if not valide.empty else pd.DataFrame(columns=["sessioni", "durata_media_min", "kwh_sessioni"]))
        ko = calcoli.kwh_da_occupazione(tab, ipotesi["energia"], [per]).set_index(per)
        out = p.join(n).join(sv).join(ko).fillna({"sessioni": 0, "kwh_sessioni": 0}).reset_index()
        out["kwh_giorno_occupazione"] = out["kwh_estrapolati"] / n_giorni
        out["sessioni"] = out["sessioni"].astype(int)
        out["prese"] = out["prese"].astype(int)
        out = out.rename(columns={per: "nome"})[["nome", "prese", "occupazione_pct", "guasto_pct", "sessioni",
                                                 "durata_media_min", "kwh_sessioni", "kwh_giorno_occupazione"]]
        return _righe(out.sort_values("prese", ascending=False))

    giornaliero = []
    if not tab.empty:
        occ_g = calcoli.kwh_da_occupazione(tab, ipotesi["energia"], ["data"]).set_index("data")
        sess_g = (kwh.groupby("data")[["sessioni", "kwh_stimati"]].sum() if not kwh.empty
                  else pd.DataFrame(columns=["sessioni", "kwh_stimati"]))
        cop_g = tab.groupby("data").apply(
            lambda g: 100 * (g["min_osservati"].sum() + g["min_altro"].sum()) / (len(g) * 60),
            include_groups=False)
        for d in occ_g.index:
            giornaliero.append({"data": str(d), "copertura_pct": _num(cop_g.get(d)),
                                "kwh_occupazione": _num(occ_g.loc[d, "kwh_estrapolati"]),
                                "sessioni": int(sess_g["sessioni"].get(d, 0)),
                                "kwh_sessioni": _num(sess_g["kwh_stimati"].get(d, 0))})

    # Colonnine comparse o sparite: confronto tra la prima e l'ultima fotografia del periodo.
    nuove, rimosse = [], []
    if presenza is not None and not presenza.empty:
        nel = presenza[(presenza["giorno"] >= primo.isoformat()) & (presenza["giorno"] <= ultimo.isoformat())]
        if not nel.empty:
            all_inizio = set(nel.loc[nel["giorno"] == nel["giorno"].min(), "id"])
            alla_fine = set(nel.loc[nel["giorno"] == nel["giorno"].max(), "id"])
            info = anagrafica.set_index("id")

            def descr(i):
                r = info.loc[i] if i in info.index else pd.Series(dtype=object)
                return {"id": i, "operatore": nome_operatore(r.get("operatore")), "indirizzo": r.get("indirizzo"),
                        "corrente": r.get("corrente"), "kw_max": _num(r.get("kw_max"), 0),
                        "distanza_km": _num(r.get("distanza_km"), 2)}
            nuove = [descr(i) for i in sorted(alla_fine - all_inizio)]
            rimosse = [descr(i) for i in sorted(all_inizio - alla_fine)]

    return {
        "versione": VERSIONE,
        "periodo": {"dal": primo.isoformat(), "al": ultimo.isoformat(), "giorni": n_giorni},
        "generato": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sintesi": {
            "prese": int(len(prese)),
            "prese_per_classe": {k: int(v) for k, v in tab.drop_duplicates("id")["classe"].value_counts().items()}
            if not tab.empty else {},
            "copertura_pct": _num(copertura),
            "occupazione_media_pct": _num(occ_media),
            "fuori_servizio_medio_pct": _num(guasto_medio),
            "kwh_giorno_da_occupazione": _num(kwh_occ_giorno),
            "sessioni": int(len(valide)),
            "sessioni_incerte": int(valide["incerta"].sum()) if not valide.empty else 0,
            "kwh_giorno_da_sessioni": _num(kwh_sess / n_giorni),
        },
        "occupazione_oraria": occupazione_oraria,
        "per_classe": riepilogo("classe"),
        "per_operatore": riepilogo("operatore"),
        "giornaliero": giornaliero,
        "colonnine_nuove": nuove,
        "colonnine_rimosse": rimosse,
        "operatori_senza_occupazione": sorted({nome_operatore(o) for o in set(prese["operatore"].dropna()) - op_occupazione}),
        "ipotesi": ipotesi,
    }
