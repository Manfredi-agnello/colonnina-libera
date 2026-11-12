"""Pagina HTML del report privato: un solo file, nessuna risorsa esterna,
si apre con un doppio clic anche senza internet."""
from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import calcoli

CSS = """
:root{--sf:#f7f7f4;--card:#fff;--tx:#1d1f1c;--tx2:#5b5f57;--bd:#dcddd6;--ac:#0f7b5f;--heat:15,123,95}
@media (prefers-color-scheme:dark){:root{--sf:#151714;--card:#1d201c;--tx:#ecede8;--tx2:#a6aa9f;--bd:#353932;--ac:#4cc79f;--heat:76,199,159}}
*{box-sizing:border-box}body{margin:0;background:var(--sf);color:var(--tx);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}
h1{font-size:1.6rem;margin:0 0 4px}h2{font-size:1.15rem;margin:36px 0 12px}
.sub{color:var(--tx2);margin:0 0 20px}.avviso{border-left:4px solid var(--ac);background:var(--card);padding:10px 14px;border-radius:6px}
.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}
.kpi div{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:14px}
.kpi b{display:block;font-size:1.5rem;font-variant-numeric:tabular-nums}.kpi span{color:var(--tx2);font-size:.9rem}
.scroll{overflow-x:auto;background:var(--card);border:1px solid var(--bd);border-radius:10px}
table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums;font-size:.92rem}
th,td{padding:6px 10px;text-align:right;border-bottom:1px solid var(--bd);white-space:nowrap}
th:first-child,td:first-child{text-align:left}th{color:var(--tx2);font-weight:600}
.heat td{text-align:center;padding:6px 4px;min-width:34px}.na{color:var(--tx2)}
ul{padding-left:20px}code{font-size:.9em}
"""


def _tabella(df: pd.DataFrame, intestazioni: list[str]) -> str:
    testa = "".join(f"<th>{html.escape(h)}</th>" for h in intestazioni)
    righe = "".join("<tr>" + "".join(f"<td>{html.escape(_fmt(v))}</td>" for v in r) + "</tr>"
                    for r in df.itertuples(index=False))
    return f'<div class="scroll"><table><thead><tr>{testa}</tr></thead><tbody>{righe}</tbody></table></div>'


def _fmt(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return "–"
    if isinstance(v, float):
        return f"{v:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(v)


def _mappa_calore(tab: pd.DataFrame, giorni: list[str]) -> str:
    p = calcoli.percentuali(tab, ["giorno_settimana", "ora"])
    griglia = p.pivot(index="giorno_settimana", columns="ora", values="occupazione_pct")
    massimo = max(float(griglia.max().max() or 0), 1.0)
    testa = "<th>giorno</th>" + "".join(f"<th>{h}</th>" for h in range(24))
    righe = ""
    for g in range(7):
        celle = ""
        for h in range(24):
            v = griglia.loc[g, h] if g in griglia.index and h in griglia.columns else float("nan")
            if pd.isna(v):
                celle += '<td class="na">–</td>'
            else:
                a = 0.08 + 0.8 * v / massimo
                celle += (f'<td style="background:rgba(var(--heat),{a:.2f})" '
                          f'title="{giorni[g]} ore {h}: {v:.0f}%">{v:.0f}</td>')
        righe += f"<tr><td>{giorni[g]}</td>{celle}</tr>"
    return (f'<div class="scroll"><table class="heat"><thead><tr>{testa}</tr></thead>'
            f"<tbody>{righe}</tbody></table></div>")


def scrivi_report(percorso: Path, *, nome, primo, ultimo, tab, sessioni, kwh, ipotesi,
                  anagrafica, op_occupazione, giorni) -> None:
    n_giorni = (ultimo - primo).days + 1
    prese = anagrafica[anagrafica["id"].isin(tab["id"].unique())] if not tab.empty else anagrafica
    minuti_tot = len(tab) * 60
    copertura = 100 * (tab["min_osservati"].sum() + tab["min_altro"].sum()) / minuti_tot if minuti_tot else 0
    valide = sessioni[sessioni["valida"]] if not sessioni.empty else sessioni
    kwh_tot = float(valide["kwh_stimati"].sum()) if not valide.empty else 0.0
    occ_media = calcoli.percentuali(tab.assign(tutte=1), ["tutte"])["occupazione_pct"].iloc[0] \
        if not tab.empty else float("nan")
    kwh_occ = calcoli.kwh_da_occupazione(tab.assign(tutte=1), ipotesi["energia"], ["tutte"])
    kwh_occ_giorno = float(kwh_occ["kwh_estrapolati"].sum()) / n_giorni if not tab.empty else 0.0
    occ_giorno = calcoli.kwh_da_occupazione(tab, ipotesi["energia"], ["data"]).set_index("data")

    # per classe e per operatore
    def riepilogo(per: str) -> pd.DataFrame:
        p = calcoli.percentuali(tab, [per])
        n = tab.drop_duplicates("id").groupby(per)["id"].nunique().rename("prese")
        if not valide.empty:
            sv = valide.groupby(per).agg(sessioni=("id", "size"),
                                         durata_media_min=("durata_min", "mean"),
                                         kwh=("kwh_stimati", "sum"))
        else:
            sv = pd.DataFrame(columns=["sessioni", "durata_media_min", "kwh"])
        ko = calcoli.kwh_da_occupazione(tab, ipotesi["energia"], [per]).set_index(per)
        out = p.set_index(per).join(n).join(sv).join(ko).fillna(
            {"sessioni": 0, "kwh": 0}).reset_index()
        out["kwh_giorno_occ"] = out["kwh_estrapolati"] / n_giorni
        out["kwh_presa_giorno_occ"] = out["kwh_giorno_occ"] / out["prese"]
        out["sessioni"] = out["sessioni"].astype(int)
        return out[[per, "prese", "occupazione_pct", "guasto_pct", "sessioni",
                    "durata_media_min", "kwh", "kwh_giorno_occ", "kwh_presa_giorno_occ"]
                   ].sort_values("prese", ascending=False)

    intest = ["prese", "occupazione %", "fuori servizio %", "sessioni", "durata media (min)",
              "kWh dalle sessioni (minimo)", "kWh/giorno da occupazione", "kWh/giorno per presa"]
    per_classe = riepilogo("classe")
    per_operatore = riepilogo("operatore")
    giornaliero = (kwh.groupby("data")[["sessioni", "kwh_stimati"]].sum()
                   if not kwh.empty else pd.DataFrame(columns=["sessioni", "kwh_stimati"]))
    giornaliero = occ_giorno[["kwh_estrapolati"]].join(giornaliero, how="left").fillna(
        {"sessioni": 0, "kwh_stimati": 0}).reset_index()
    copertura_g = tab.groupby("data").apply(
        lambda g: 100 * (g["min_osservati"].sum() + g["min_altro"].sum()) / (len(g) * 60),
        include_groups=False).rename("copertura")
    giornaliero = giornaliero.join(copertura_g, on="data")
    giornaliero["sessioni"] = giornaliero["sessioni"].astype(int)
    giornaliero = giornaliero[["data", "copertura", "kwh_estrapolati", "sessioni", "kwh_stimati"]]
    e, s = ipotesi["energia"], ipotesi["sessioni"]
    non_misurabili = sorted(set(prese["operatore"].dropna()) - op_occupazione)

    pagina = f"""<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Zona hub {html.escape(nome)}</title><style>{CSS}</style></head><body><main>
<h1>Zona hub · report {html.escape(nome)}</h1>
<p class="sub">Periodo {primo:%d/%m/%Y} – {ultimo:%d/%m/%Y} ({n_giorni} giorni) · generato il {datetime.now():%d/%m/%Y %H:%M}</p>
<p class="avviso"><b>Documento privato.</b> Dati PUN (MASE/GSE) rielaborati: non ufficiali, senza garanzia di completezza o correttezza. Le stime di energia dipendono dalle ipotesi in fondo alla pagina.</p>

<h2>In sintesi</h2>
<div class="kpi">
<div><b>{len(prese)}</b><span>prese nella zona</span></div>
<div><b>{_fmt(copertura)}%</b><span>tempo coperto dalla raccolta</span></div>
<div><b>{_fmt(occ_media)}%</b><span>occupazione media</span></div>
<div><b>{_fmt(kwh_occ_giorno)}</b><span>kWh al giorno stimati dall'occupazione (stima principale)</span></div>
<div><b>{len(valide)}</b><span>sessioni viste ({int(valide['incerta'].sum()) if not valide.empty else 0} incerte)</span></div>
<div><b>{_fmt(kwh_tot / n_giorni)}</b><span>kWh al giorno dalle sessioni viste (minimo)</span></div>
</div>
<p class="sub">Le due stime di energia coincidono quando la raccolta copre tutto il tempo. Con molti buchi
la stima dalle sessioni è solo un minimo; quella dall'occupazione applica la quota di tempo in carica
misurata nelle ore osservate a tutte le ore del periodo.</p>

<h2>Quando sono occupate (% del tempo, tutte le prese)</h2>
{_mappa_calore(tab, giorni) if not tab.empty else '<p>Nessun dato.</p>'}

<h2>Per classe di potenza</h2>
{_tabella(per_classe, ['classe'] + intest)}

<h2>Per operatore</h2>
{_tabella(per_operatore, ['operatore'] + intest)}

<h2>Giorno per giorno</h2>
{_tabella(giornaliero, ['data', 'tempo coperto %', 'kWh da occupazione', 'sessioni viste', 'kWh dalle sessioni (minimo)'])}

<h2>Ipotesi usate</h2>
<ul>
<li><b>Energia DC</b>: {e['dc_frazione_potenza_nominale'] * 100:.0f}% della potenza nominale della presa × durata.</li>
<li><b>Energia AC</b>: il minore tra la potenza della presa e {_fmt(float(e['ac_kw_auto']))} kW × durata.</li>
<li><b>Tetto</b>: al massimo {e['kwh_massimi_per_sessione']} kWh per sessione.</li>
<li><b>Sessioni scartate</b>: sotto {s['durata_minima_min']} minuti. <b>Segnalate come lunghe</b>: oltre {s['durata_lunga_dc_ore']} ore in DC, {s['durata_lunga_ac_ore']} ore in AC.</li>
<li><b>Buchi</b>: tra due letture distanti più di {s['buco_massimo_min']} minuti il tempo è "non osservato"; le sessioni che lo attraversano sono "incerte" (durata = valore minimo).</li>
<li><b>Classi</b>: AC · DC fino a {ipotesi['classi_potenza']['dc_hpc_da_kw'] - 1} kW · DC da {ipotesi['classi_potenza']['dc_hpc_da_kw']} kW in su.</li>
</ul>

<h2>Limiti</h2>
<ul>
<li>Le letture sono ogni ~5 minuti: ricariche più brevi possono sfuggire, e inizio/fine sono stimati a metà tra due letture.</li>
<li>Occupazione misurata solo per gli operatori che segnalano lo stato "in carica".{' Esclusi: ' + html.escape(', '.join(non_misurabili)) + '.' if non_misurabili else ''}</li>
<li>"Fuori servizio" è lo stato dichiarato dall'operatore alla PUN: può includere colonnine non collegate o in manutenzione.</li>
<li><b>In AC "occupata" non vuol dire "sta caricando"</b>: molte auto restano collegate dopo aver finito la ricarica (soste lunghe, notte). Per le prese AC le stime di energia sono quindi probabilmente <b>per eccesso</b>. In DC il problema è minore: le soste dopo la ricarica di solito si pagano.</li>
</ul>
<p class="sub">Dettagli nei CSV della stessa cartella e in METODO.md.</p>
</main></body></html>"""
    percorso.write_text(pagina, encoding="utf-8")
