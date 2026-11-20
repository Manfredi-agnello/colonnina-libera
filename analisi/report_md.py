"""Report in Markdown con grafici SVG, leggibile direttamente su GitHub (anche dall'app
per telefono) nel repository privato. Nasce dal riassunto (analisi/riassunto.py).

Nella cartella del report:
  README.md       la pagina del report (GitHub la mostra aprendo la cartella)
  ore.svg         occupazione per ora (feriali / fine settimana)
  giorni.svg      energia stimata giorno per giorno
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

MESI = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
        "agosto", "settembre", "ottobre", "novembre", "dicembre"]
BLU, TERRA, GRIGIO, TESTO = "#0b4f7c", "#c0623b", "#c9ccd1", "#1f2328"


def mese_breve(chiave: str) -> str:
    a, m = chiave.split("-")
    return f"{MESI[int(m)][:3]} {a[2:]}"


def nome_mese(chiave: str) -> str:
    a, m = chiave.split("-")
    return f"{MESI[int(m)]} {a}"


def fmt(v, cifre=1, suffisso="") -> str:
    if v is None:
        return "–"
    testo = f"{v:,.{cifre}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return testo + suffisso


def _svg(larghezza, altezza, corpo) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{larghezza}" height="{altezza}" '
            f'viewBox="0 0 {larghezza} {altezza}" font-family="Arial, sans-serif" font-size="12">'
            f'<rect width="100%" height="100%" fill="#ffffff"/>{corpo}</svg>')


def grafico_ore(orario: dict) -> str:
    """Due serie (feriali, fine settimana) di 24 valori in %."""
    L, A, sx, dx, su, giu = 720, 260, 40, 12, 28, 30
    w, h = L - sx - dx, A - su - giu
    vals = [v for k in ("feriali", "fine_settimana") for v in orario.get(k, []) if v is not None]
    massimo = max(10, *(vals or [10]))
    massimo = (int(massimo / 10) + 1) * 10
    x = lambda i: sx + w * i / 23
    y = lambda v: su + h * (1 - v / massimo)
    parti = []
    for t in range(0, massimo + 1, max(10, massimo // 5 // 10 * 10 or 10)):
        parti.append(f'<line x1="{sx}" x2="{L - dx}" y1="{y(t):.1f}" y2="{y(t):.1f}" stroke="#eceef1"/>'
                     f'<text x="{sx - 6}" y="{y(t) + 4:.1f}" text-anchor="end" fill="#57606a">{t}%</text>')
    for o in range(0, 24, 3):
        parti.append(f'<text x="{x(o):.1f}" y="{A - 10}" text-anchor="middle" fill="#57606a">{o}</text>')
    for chiave, colore, etichetta, pos in (("feriali", BLU, "lun–ven", 0), ("fine_settimana", TERRA, "sab–dom", 1)):
        serie = orario.get(chiave) or []
        punti = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(serie) if v is not None)
        if punti:
            parti.append(f'<polyline points="{punti}" fill="none" stroke="{colore}" stroke-width="2.5"/>')
        parti.append(f'<rect x="{sx + 10 + pos * 90}" y="8" width="14" height="4" fill="{colore}"/>'
                     f'<text x="{sx + 28 + pos * 90}" y="14" fill="{TESTO}">{etichetta}</text>')
    parti.append(f'<text x="{L - dx}" y="14" text-anchor="end" fill="#57606a">% del tempo occupata, per ora (ora italiana)</text>')
    return _svg(L, A, "".join(parti))


def grafico_barre(etichette: list[str], valori: list, titolo: str, colore=BLU) -> str:
    L, A, sx, dx, su, giu = 720, 240, 46, 12, 28, 40
    w, h = L - sx - dx, A - su - giu
    vv = [v or 0 for v in valori]
    massimo = max(1.0, *vv) if vv else 1.0
    passo = min(60, w / max(1, len(vv)))   # barre larghe al massimo 60 px
    parti = [f'<text x="{sx}" y="16" fill="{TESTO}">{titolo}</text>',
             f'<text x="{sx - 6}" y="{su + 4}" text-anchor="end" fill="#57606a">{fmt(massimo, 0)}</text>',
             f'<line x1="{sx}" x2="{L - dx}" y1="{su + h}" y2="{su + h}" stroke="{GRIGIO}"/>']
    ogni = max(1, len(vv) // 10)
    for i, v in enumerate(vv):
        alt = h * v / massimo
        parti.append(f'<rect x="{sx + i * passo + 1:.1f}" y="{su + h - alt:.1f}" width="{max(1, passo - 2):.1f}" '
                     f'height="{alt:.1f}" fill="{colore if valori[i] is not None else GRIGIO}"/>')
        if i % ogni == 0:
            parti.append(f'<text x="{sx + i * passo + passo / 2:.1f}" y="{A - 22}" text-anchor="middle" '
                         f'fill="#57606a">{etichette[i]}</text>')
    return _svg(L, A, "".join(parti))


def _tabella(righe: list[dict], colonne: list[tuple[str, str, int]]) -> str:
    if not righe:
        return "_Nessun dato._\n"
    testa = "| " + " | ".join(t for _, t, _ in colonne) + " |\n|" + "|".join(
        "---" if c is None else "---:" for _, _, c in colonne) + "|\n"
    corpo = "".join("| " + " | ".join(
        str(r.get(k) if r.get(k) is not None else "–") if c is None else fmt(r.get(k), c)
        for k, _, c in colonne) + " |\n" for r in righe)
    return testa + corpo


COLONNE_RIEPILOGO = [("nome", "", None), ("prese", "prese", 0), ("occupazione_pct", "occupazione %", 1),
                     ("guasto_pct", "fuori servizio %", 1), ("sessioni", "sessioni viste", 0),
                     ("durata_media_min", "durata media (min)", 0),
                     ("kwh_giorno_occupazione", "kWh/giorno (stima principale)", 1)]


def _confronto(r: dict, altro: dict | None, etichetta: str) -> str:
    if not altro:
        return ""
    a, b = r["sintesi"], altro["sintesi"]

    def delta(k, cifre=1, suff=""):
        if a.get(k) is None or b.get(k) is None:
            return "–"
        d = a[k] - b[k]
        return ("+" if d > 0 else "") + fmt(d, cifre, suff)
    return (f"\n**Rispetto {etichetta}:** occupazione {delta('occupazione_media_pct', 1, ' punti')}, "
            f"fuori servizio {delta('fuori_servizio_medio_pct', 1, ' punti')}, "
            f"energia {delta('kwh_giorno_da_occupazione', 0, ' kWh/giorno')}, prese {delta('prese', 0)}.\n")


def scrivi(cartella: Path, r: dict, titolo: str, precedente: dict | None = None,
           anno_prima: dict | None = None) -> None:
    cartella.mkdir(parents=True, exist_ok=True)
    s = r["sintesi"]
    p = r["periodo"]
    (cartella / "ore.svg").write_text(grafico_ore((r["occupazione_oraria"] or {}).get("tutte", {})), encoding="utf-8")
    g = r["giornaliero"]
    (cartella / "giorni.svg").write_text(grafico_barre(
        [x["data"][8:10] for x in g], [x["kwh_occupazione"] for x in g],
        "kWh al giorno stimati dall'occupazione (tutte le prese della zona)"), encoding="utf-8")
    dal, al = date.fromisoformat(p["dal"]), date.fromisoformat(p["al"])
    classi = ", ".join(f"{k} {v}" for k, v in sorted(s["prese_per_classe"].items()))

    def elenco(lista):
        if not lista:
            return "_Nessuna._\n"
        return "".join(f"- {c.get('operatore') or '?'} · {c.get('indirizzo') or c['id']} · "
                       f"{c.get('corrente') or ''} {fmt(c.get('kw_max'), 0)} kW · a {fmt(c.get('distanza_km'), 1)} km\n"
                       for c in lista)

    testo = f"""# {titolo}

> **Documento privato.** Dati PUN (MASE/GSE) rielaborati: non ufficiali, senza garanzia di completezza o
> correttezza. Periodo {dal:%d/%m/%Y} – {al:%d/%m/%Y} ({p['giorni']} giorni), generato il {r['generato'][:10]}.

## In sintesi

| | |
|---|---:|
| Prese nella zona | **{s['prese']}** ({classi or '–'}) |
| Tempo coperto dalla raccolta | {fmt(s['copertura_pct'], 1, '%')} |
| Occupazione media | **{fmt(s['occupazione_media_pct'], 1, '%')}** |
| Fuori servizio (media) | {fmt(s['fuori_servizio_medio_pct'], 1, '%')} |
| Energia al giorno, stima principale (dall'occupazione) | **{fmt(s['kwh_giorno_da_occupazione'], 0, ' kWh')}** |
| Sessioni di ricarica viste | {s['sessioni']} ({s['sessioni_incerte']} incerte) |
| Energia al giorno dalle sessioni viste (minimo) | {fmt(s['kwh_giorno_da_sessioni'], 0, ' kWh')} |
{_confronto(r, precedente, "al mese precedente")}{_confronto(r, anno_prima, "allo stesso mese dell'anno prima")}
## Quando sono occupate

![Occupazione per ora](ore.svg)

## Giorno per giorno

![Energia per giorno](giorni.svg)

## Per classe di potenza

{_tabella(r['per_classe'], COLONNE_RIEPILOGO)}
## Per operatore

{_tabella(r['per_operatore'], COLONNE_RIEPILOGO)}
## Colonnine nuove nel periodo

{elenco(r['colonnine_nuove'])}
## Colonnine sparite nel periodo

{elenco(r['colonnine_rimosse'])}
## Come leggere i numeri

- **Stima principale dell'energia**: quota di tempo "in carica" misurata nelle ore osservate, applicata a
  tutte le ore, × potenza effettiva (DC {round(r['ipotesi']['energia']['dc_frazione_potenza_nominale'] * 100)}% della
  nominale, AC al massimo {r['ipotesi']['energia']['ac_kw_auto']} kW). Le sessioni viste sono un **minimo**.
- **In AC "occupata" non vuol dire "sta caricando"**: molte auto restano collegate dopo la ricarica, quindi
  per le prese AC l'energia è probabilmente **sovrastimata**.
- Operatori senza dato di occupazione: {', '.join(r['operatori_senza_occupazione']) or 'nessuno'}.
- Dettagli del metodo: METODO.md nel repository del sito. Dati completi: `riassunto.json` e i CSV in questa cartella.
"""
    (cartella / "README.md").write_text(testo, encoding="utf-8")
    (cartella / "riassunto.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
