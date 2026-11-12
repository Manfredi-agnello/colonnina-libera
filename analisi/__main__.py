"""Report della zona hub (PRIVATO). Uso:

    python -m analisi --hub hub-dati                        # ultima settimana completa (lun-dom)
    python -m analisi --hub hub-dati --dal 2026-11-02 --al 2026-11-08
    python -m analisi --hub hub-dati --tutto                # tutto l'archivio

Crea una cartella in report/ con:
  sessioni.csv, occupazione_oraria.csv, kwh_giornalieri.csv, affidabilita.csv, report.html
I CSV usano ; come separatore e la virgola nei decimali: si aprono con un
doppio clic in Excel italiano.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from . import calcoli, dati
from .report_html import scrivi_report

RADICE = Path(__file__).resolve().parent.parent
GIORNI = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]


def _csv(df: pd.DataFrame, percorso: Path) -> None:
    df.to_csv(percorso, sep=";", decimal=",", index=False, encoding="utf-8-sig")


def periodo(args, d: dati.Dati) -> tuple[date, date, str]:
    if args.tutto:
        primo = d.cicli["ts"].min().tz_convert(calcoli.ROMA).date()
        ultimo = d.cicli["ts"].max().tz_convert(calcoli.ROMA).date()
        return primo, ultimo, f"{primo}_{ultimo}"
    if args.dal and args.al:
        dal, al = date.fromisoformat(args.dal), date.fromisoformat(args.al)
        return dal, al, f"{dal}_{al}"
    oggi = date.today()
    lunedi = oggi - timedelta(days=oggi.weekday() + 7)          # lunedì della settimana scorsa
    anno, sett, _ = lunedi.isocalendar()
    return lunedi, lunedi + timedelta(days=6), f"{anno}-S{sett:02d}"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hub", default="hub-dati", help="cartella dell'archivio privato")
    ap.add_argument("--dal", help="primo giorno incluso (AAAA-MM-GG, ora italiana)")
    ap.add_argument("--al", help="ultimo giorno incluso (AAAA-MM-GG, ora italiana)")
    ap.add_argument("--tutto", action="store_true", help="tutto l'archivio")
    ap.add_argument("--uscita", default=None, help="cartella del report (default: report/<periodo>)")
    ap.add_argument("--ipotesi", default=str(RADICE / "config" / "ipotesi_analisi.json"))
    args = ap.parse_args()

    ipotesi = dati.carica_ipotesi(Path(args.ipotesi))
    d = dati.carica(Path(args.hub), ipotesi["giro_completo_quota"])
    primo, ultimo, nome = periodo(args, d)
    dal = pd.Timestamp(primo.isoformat(), tz=calcoli.ROMA).tz_convert("UTC")
    al = pd.Timestamp((ultimo + timedelta(days=1)).isoformat(), tz=calcoli.ROMA).tz_convert("UTC")
    uscita = Path(args.uscita or RADICE / "report" / nome)
    uscita.mkdir(parents=True, exist_ok=True)

    buco = ipotesi["sessioni"]["buco_massimo_min"]
    tab = calcoli.tabella_oraria(d.letture, dal, al, buco)
    op_occ = calcoli.operatori_con_occupazione(d.letture, d.anagrafica)
    tab = calcoli.arricchisci(tab, d.anagrafica, ipotesi, op_occ)
    s = calcoli.sessioni(d.letture, d.anagrafica, ipotesi, dal, al)

    # 1. sessioni
    colonne_s = ["inizio_locale", "fine_locale", "durata_min", "id", "operatore", "corrente",
                 "classe", "kw_max", "kwh_stimati", "valida", "breve", "lunga", "incerta"]
    _csv(s[colonne_s] if not s.empty else pd.DataFrame(columns=colonne_s), uscita / "sessioni.csv")

    # 2. occupazione per giorno della settimana × ora × classe (+ "tutte")
    occ = pd.concat([calcoli.percentuali(tab, ["giorno_settimana", "ora", "classe"]),
                     calcoli.percentuali(tab.assign(classe="tutte"), ["giorno_settimana", "ora", "classe"])])
    occ["giorno"] = occ["giorno_settimana"].map(lambda i: GIORNI[i])
    occ = occ.sort_values(["classe", "giorno_settimana", "ora"])
    _csv(occ[["classe", "giorno", "ora", "occupazione_pct", "guasto_pct", "ore_osservate"]],
         uscita / "occupazione_oraria.csv")

    # 3. kWh per giorno, operatore e classe
    if not s.empty:
        v = s[s["valida"]].copy()
        v["data"] = v["inizio_locale"].str[:10]
        kwh = v.groupby(["data", "operatore", "classe"]).agg(
            sessioni=("id", "size"), sessioni_incerte=("incerta", "sum"),
            ore_ricarica=("durata_min", lambda x: round(x.sum() / 60, 1)),
            kwh_stimati=("kwh_stimati", "sum")).reset_index()
        kwh["kwh_stimati"] = kwh["kwh_stimati"].round(1)
    else:
        kwh = pd.DataFrame(columns=["data", "operatore", "classe", "sessioni",
                                    "sessioni_incerte", "ore_ricarica", "kwh_stimati"])
    _csv(kwh, uscita / "kwh_giornalieri.csv")

    # 4. affidabilità e uso per presa
    per_presa = calcoli.percentuali(tab, ["id", "operatore", "classe", "kw_max"])
    dist = d.anagrafica.set_index("id").get("distanza_km")
    if dist is not None:
        per_presa["distanza_km"] = per_presa["id"].map(dist)
    _csv(per_presa.sort_values(["operatore", "id"]), uscita / "affidabilita.csv")

    scrivi_report(uscita / "report.html", nome=nome, primo=primo, ultimo=ultimo,
                  tab=tab, sessioni=s, kwh=kwh, ipotesi=ipotesi, anagrafica=d.anagrafica,
                  op_occupazione=op_occ, giorni=GIORNI)
    print(f"Report scritto in {uscita}")
    print(f"  periodo {primo} - {ultimo}, sessioni valide: "
          f"{int(s['valida'].sum()) if not s.empty else 0}, "
          f"kWh stimati: {kwh['kwh_stimati'].sum():.0f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
