"""Calcoli della zona hub. Ogni funzione è documentata in METODO.md.

Regola di base (usata ovunque): tra due letture consecutive della stessa presa,
il cambio di stato si considera avvenuto A METÀ. In pratica ogni minuto prende
lo stato della lettura più vicina nel tempo. Se due letture distano più di
`buco_massimo_min`, il tempo in mezzo è "non osservato" e non entra nei conti.
"""
from __future__ import annotations

from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from raccolta.modello import categoria

ROMA = ZoneInfo("Europe/Rome")
EPOCA = pd.Timestamp("1970-01-01", tz="UTC")

# Codici per la griglia al minuto.
NON_OSSERVATO, LIBERA, OCCUPATA, GUASTA, ALTRO = 0, 1, 2, 3, 4
CODICE = {"libera": LIBERA, "occupata": OCCUPATA, "guasta": GUASTA}


def codice_stato(stato_raw: pd.Series) -> np.ndarray:
    return stato_raw.map(lambda s: CODICE.get(categoria(s), ALTRO)).to_numpy(np.int8)


def classe_potenza(corrente, kw, soglia_hpc: float) -> str:
    if corrente == "DC":
        if kw is not None and not pd.isna(kw) and kw >= soglia_hpc:
            return f"DC da {soglia_hpc:g} kW in su"
        return f"DC fino a {soglia_hpc - 1:g} kW"
    return "AC" if corrente == "AC" else "sconosciuta"


# ── griglia al minuto → tabella oraria ─────────────────────────────────────

def tabella_oraria(letture: pd.DataFrame, dal: pd.Timestamp, al: pd.Timestamp,
                   buco_massimo_min: float) -> pd.DataFrame:
    """Per ogni presa e ogni ora (ora italiana) del periodo [dal, al):
    minuti osservati in ciascuno stato. Colonne:
    id, inizio_ora (ora italiana), data, ora, giorno_settimana (0=lunedì),
    min_libera, min_occupata, min_guasta, min_altro, min_osservati."""
    m0 = int(dal.timestamp() // 60)
    m1 = int(al.timestamp() // 60)
    centri = np.arange(m0, m1, dtype=np.float64) + 0.5          # centro di ogni minuto
    ore = pd.date_range(dal, al, freq="h", inclusive="left", tz="UTC")
    ora_di_minuto = (np.arange(m0, m1) - m0) // 60
    n_ore = len(ore)

    righe = []
    for id_, g in letture.groupby("id", sort=False):
        t = (g["ts"] - EPOCA).dt.total_seconds().to_numpy(np.float64) / 60.0
        s = codice_stato(g["stato_raw"])
        succ = np.searchsorted(t, centri, side="right")
        prec = succ - 1
        valido = (prec >= 0) & (succ < len(t))
        pi, si = np.clip(prec, 0, len(t) - 1), np.clip(succ, 0, len(t) - 1)
        valido &= (t[si] - t[pi]) <= buco_massimo_min
        piu_vicino = np.where(centri - t[pi] <= t[si] - centri, pi, si)
        codici = np.where(valido, s[piu_vicino], NON_OSSERVATO)
        conteggi = np.bincount(ora_di_minuto * 5 + codici, minlength=n_ore * 5).reshape(n_ore, 5)
        righe.append(pd.DataFrame({
            "id": id_, "inizio_utc": ore,
            "min_libera": conteggi[:, LIBERA], "min_occupata": conteggi[:, OCCUPATA],
            "min_guasta": conteggi[:, GUASTA], "min_altro": conteggi[:, ALTRO]}))
    if not righe:
        return pd.DataFrame()
    t = pd.concat(righe, ignore_index=True)
    t["min_osservati"] = t[["min_libera", "min_occupata", "min_guasta"]].sum(axis=1)
    locale = t["inizio_utc"].dt.tz_convert(ROMA)
    t["data"] = locale.dt.strftime("%Y-%m-%d")
    t["ora"] = locale.dt.hour
    t["giorno_settimana"] = locale.dt.day_of_week
    return t.drop(columns="inizio_utc")


# ── sessioni ───────────────────────────────────────────────────────────────

def sessioni(letture: pd.DataFrame, anagrafica: pd.DataFrame, ipotesi: dict,
             dal: pd.Timestamp, al: pd.Timestamp) -> pd.DataFrame:
    """Una riga per ricarica: sequenza di letture consecutive "occupata".
    Inizio e fine a metà tra l'ultima lettura diversa e la prima "occupata"
    (e viceversa). Tiene le sessioni che INIZIANO nel periodo [dal, al)."""
    p = ipotesi["sessioni"]
    buco = pd.Timedelta(minutes=p["buco_massimo_min"])
    attr = anagrafica.set_index("id")
    out = []
    for id_, g in letture.groupby("id", sort=False):
        t = g["ts"].to_numpy()
        occ = codice_stato(g["stato_raw"]) == OCCUPATA
        if not occ.any():
            continue
        # inizi/fine delle sequenze di True
        bordi = np.diff(np.concatenate([[0], occ.astype(np.int8), [0]]))
        for i, j in zip(np.flatnonzero(bordi == 1), np.flatnonzero(bordi == -1) - 1):
            incerta = False
            if i > 0 and t[i] - t[i - 1] <= buco:
                inizio = t[i - 1] + (t[i] - t[i - 1]) / 2
            else:
                inizio, incerta = t[i], True
            if j + 1 < len(t) and t[j + 1] - t[j] <= buco:
                fine = t[j] + (t[j + 1] - t[j]) / 2
            else:
                fine, incerta = t[j], True
            # I buchi dentro la sessione non contano: la durata è solo il tempo
            # osservato, quindi per le sessioni incerte è un valore MINIMO.
            salti = np.diff(t[i:j + 1])
            grandi = salti[salti > buco]
            non_osservato = pd.Timedelta(grandi.sum()) if len(grandi) else pd.Timedelta(0)
            if len(grandi):
                incerta = True
            durata = (pd.Timedelta(fine - inizio) - non_osservato) / pd.Timedelta(minutes=1)
            out.append((id_, pd.Timestamp(inizio), pd.Timestamp(fine), incerta, durata))
    if not out:
        return pd.DataFrame()
    s = pd.DataFrame(out, columns=["id", "inizio", "fine", "incerta", "durata_min"])
    s["inizio"] = s["inizio"].dt.tz_localize("UTC") if s["inizio"].dt.tz is None else s["inizio"]
    s["fine"] = s["fine"].dt.tz_localize("UTC") if s["fine"].dt.tz is None else s["fine"]
    s = s[(s["inizio"] >= dal) & (s["inizio"] < al)].copy()
    s["durata_min"] = s["durata_min"].round(1)

    s = s.join(attr[["operatore", "corrente", "kw_max"]], on="id")
    soglia = ipotesi["classi_potenza"]["dc_hpc_da_kw"]
    s["classe"] = [classe_potenza(c, k, soglia) for c, k in zip(s["corrente"], s["kw_max"])]
    # "breve" solo per le sessioni certe: per le incerte la durata è un minimo,
    # e scartarle farebbe sparire ricariche vere viste in una sola lettura.
    s["breve"] = ~s["incerta"] & (s["durata_min"] < p["durata_minima_min"])
    lunga_ore = np.where(s["corrente"] == "DC", p["durata_lunga_dc_ore"], p["durata_lunga_ac_ore"])
    s["lunga"] = s["durata_min"] > lunga_ore * 60
    s["valida"] = ~s["breve"]
    s["kwh_stimati"] = kwh_stimati(s, ipotesi["energia"])
    s["inizio_locale"] = s["inizio"].dt.tz_convert(ROMA).dt.strftime("%Y-%m-%d %H:%M")
    s["fine_locale"] = s["fine"].dt.tz_convert(ROMA).dt.strftime("%Y-%m-%d %H:%M")
    return s.sort_values("inizio").reset_index(drop=True)


def potenza_effettiva_kw(corrente, kw_max, energia: dict) -> float:
    if kw_max is None or pd.isna(kw_max):
        return float("nan")
    if corrente == "DC":
        return energia["dc_frazione_potenza_nominale"] * kw_max
    return min(kw_max, energia["ac_kw_auto"])


def kwh_stimati(s: pd.DataFrame, energia: dict) -> pd.Series:
    """kWh = durata (ore) × potenza effettiva, con un tetto per sessione.
    Le sessioni troppo brevi valgono 0."""
    kw = [potenza_effettiva_kw(c, k, energia) for c, k in zip(s["corrente"], s["kw_max"])]
    kwh = (s["durata_min"] / 60 * pd.Series(kw, index=s.index)).clip(
        upper=energia["kwh_massimi_per_sessione"])
    return kwh.where(s["valida"], 0.0).round(2)


# ── aggregazioni ───────────────────────────────────────────────────────────

def operatori_con_occupazione(letture: pd.DataFrame, anagrafica: pd.DataFrame) -> set:
    """Operatori che hanno segnalato almeno una volta "in carica": solo per loro
    l'occupazione è misurabile (gli altri dicono solo se la presa funziona)."""
    occ = letture.loc[codice_stato(letture["stato_raw"]) == OCCUPATA, "id"].unique()
    return set(anagrafica.loc[anagrafica["id"].isin(occ), "operatore"].dropna())


def arricchisci(tab: pd.DataFrame, anagrafica: pd.DataFrame, ipotesi: dict,
                op_occupazione: set) -> pd.DataFrame:
    a = anagrafica[["id", "operatore", "corrente", "kw_max", "tempo_reale"]].copy()
    soglia = ipotesi["classi_potenza"]["dc_hpc_da_kw"]
    a["classe"] = [classe_potenza(c, k, soglia) for c, k in zip(a["corrente"], a["kw_max"])]
    a["occupazione_misurabile"] = a["tempo_reale"].fillna(False).astype(bool) & \
        a["operatore"].isin(op_occupazione)
    return tab.merge(a, on="id", how="left")


def kwh_da_occupazione(df: pd.DataFrame, energia: dict, per: list[str]) -> pd.DataFrame:
    """Seconda stima dell'energia, che regge i buchi della raccolta.
    Per ogni presa: kWh nel tempo osservato = minuti occupati × potenza effettiva;
    poi si riporta all'intero periodo dividendo per la quota di tempo osservato.
    Esempio: 10 kWh in 6 ore osservate su 24 -> 40 kWh nella giornata."""
    d = df[df["occupazione_misurabile"]].copy()
    kw = [potenza_effettiva_kw(c, k, energia) for c, k in zip(d["corrente"], d["kw_max"])]
    d["kwh_osservati"] = d["min_occupata"] / 60 * pd.Series(kw, index=d.index)
    d["min_totali"] = 60
    chiavi = per + ([] if "id" in per else ["id"])
    g = d.groupby(chiavi, dropna=False)[["kwh_osservati", "min_osservati", "min_totali"]].sum()
    g["kwh_estrapolati"] = g["kwh_osservati"] * g["min_totali"] / g["min_osservati"].where(g["min_osservati"] > 0)
    return g.groupby(level=per, dropna=False)[["kwh_osservati", "kwh_estrapolati"]].sum().reset_index()


def percentuali(df: pd.DataFrame, per: list[str]) -> pd.DataFrame:
    """Somma i minuti per gruppo e calcola le percentuali sul tempo osservato.
    occupazione_pct usa solo le prese con occupazione misurabile."""
    g = df.groupby(per, dropna=False)
    out = g[["min_osservati", "min_guasta"]].sum()
    mis = df[df["occupazione_misurabile"]].groupby(per, dropna=False)[
        ["min_osservati", "min_occupata"]].sum().rename(
        columns={"min_osservati": "min_osservati_misurabili"})
    out = out.join(mis, how="left").fillna(0)
    out["occupazione_pct"] = (100 * out["min_occupata"] / out["min_osservati_misurabili"]).round(1)
    out["guasto_pct"] = (100 * out["min_guasta"] / out["min_osservati"]).round(1)
    out["ore_osservate"] = (out["min_osservati"] / 60).round(1)
    return out.reset_index()[per + ["occupazione_pct", "guasto_pct", "ore_osservate"]]
