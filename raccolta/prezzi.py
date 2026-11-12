"""Prezzi: controllo del file prezzi/prezzi.csv (compilato a mano) e file pubblico per il sito.

Controllo manuale (da lanciare dopo ogni modifica):
    python -m raccolta.prezzi

I prezzi vanno scritti IVA INCLUSA (come li mostra l'app dell'operatore).

Il file si può modificare con Excel: va bene sia il punto e virgola (;) sia la
virgola (,) come separatore, e sia 0,59 sia 0.59 come numero.
"""
from __future__ import annotations

import csv
import io
import json
import sys
from datetime import date
from pathlib import Path

RADICE = Path(__file__).resolve().parent.parent
FILE_PREZZI = RADICE / "prezzi" / "prezzi.csv"
COLONNE = ["operatore", "tipo", "prezzo_kwh", "costo_minuto", "costo_avvio",
           "id_colonnina", "data_rilevazione", "fonte", "note"]
TIPI = {"AC", "DC", "HPC"}


def _numero(testo: str, nome: str, errori: list, riga: int, obbligatorio=False):
    t = (testo or "").strip().replace("€", "").replace(",", ".")
    if not t:
        if obbligatorio:
            errori.append(f"riga {riga}: manca {nome}")
        return None
    try:
        v = float(t)
    except ValueError:
        errori.append(f"riga {riga}: {nome} '{testo}' non è un numero")
        return None
    if v < 0 or v > 5:
        errori.append(f"riga {riga}: {nome} {v} fuori scala (atteso tra 0 e 5 euro)")
    return v


def leggi(percorso: Path = FILE_PREZZI) -> tuple[list[dict], list[str]]:
    """Ritorna (righe valide, errori). Le righe con errori vengono scartate."""
    testo = percorso.read_text(encoding="utf-8-sig")
    separatore = ";" if testo.splitlines()[0].count(";") >= testo.splitlines()[0].count(",") else ","
    lettore = csv.DictReader(io.StringIO(testo), delimiter=separatore)
    mancanti = [c for c in COLONNE if c not in (lettore.fieldnames or [])]
    if mancanti:
        return [], [f"intestazione: mancano le colonne {', '.join(mancanti)}"]
    righe, errori = [], []
    for n, r in enumerate(lettore, start=2):
        if not any((v or "").strip() for v in r.values()):
            continue                                            # riga vuota
        e: list[str] = []
        operatore = (r["operatore"] or "").strip()
        tipo = (r["tipo"] or "").strip().upper()
        if not operatore:
            e.append(f"riga {n}: manca l'operatore")
        if tipo not in TIPI:
            e.append(f"riga {n}: tipo '{r['tipo']}' non valido (usa AC, DC o HPC)")
        kwh = _numero(r["prezzo_kwh"], "prezzo_kwh", e, n, obbligatorio=True)
        minuto = _numero(r["costo_minuto"], "costo_minuto", e, n)
        avvio = _numero(r["costo_avvio"], "costo_avvio", e, n)
        try:
            giorno = date.fromisoformat((r["data_rilevazione"] or "").strip())
            if giorno > date.today():
                e.append(f"riga {n}: data_rilevazione nel futuro")
        except ValueError:
            e.append(f"riga {n}: data_rilevazione '{r['data_rilevazione']}' non valida (usa AAAA-MM-GG)")
            giorno = None
        if not (r["fonte"] or "").strip():
            e.append(f"riga {n}: manca la fonte (es. 'app Enel X Way')")
        if e:
            errori.extend(e)
            continue
        righe.append({"operatore": operatore, "tipo": tipo, "prezzo_kwh": kwh,
                      "costo_minuto": minuto, "costo_avvio": avvio,
                      "id_colonnina": (r["id_colonnina"] or "").strip() or None,
                      "data_rilevazione": giorno.isoformat(), "fonte": r["fonte"].strip(),
                      "note": (r["note"] or "").strip() or None})
    return righe, errori


def tariffe_pun(colonnine: list[dict]) -> list[dict]:
    """Tariffe pubblicate dagli operatori sulla PUN, una riga per operatore/tipo/prezzo."""
    viste = {}
    for c in colonnine:
        for tipo, voci in (c.get("tariffe_pun") or {}).items():
            if voci.get("energy") is None:
                continue
            chiave = (c["operatore"], tipo.upper(), voci["energy"])
            v = viste.setdefault(chiave, {"operatore": c["operatore"], "tipo": tipo.upper(),
                                          "prezzo_kwh": voci["energy"],
                                          "costo_minuto": voci.get("time"),
                                          "costo_avvio": voci.get("activation"),
                                          "fonte": "PUN", "colonnine": 0})
            v["colonnine"] += 1
    return sorted(viste.values(), key=lambda v: (v["operatore"] or "", v["tipo"], v["prezzo_kwh"]))


def scrivi_per_sito(colonnine: list[dict], cartella: Path) -> list[str]:
    """prezzi.json per il sito. Ritorna gli errori del file manuale (righe scartate)."""
    manuali, errori = leggi() if FILE_PREZZI.exists() else ([], [])
    ultima = max((r["data_rilevazione"] for r in manuali), default=None)
    cartella.mkdir(parents=True, exist_ok=True)
    (cartella / "prezzi.json").write_text(json.dumps({
        "ultima_verifica_manuale": ultima,
        "rilevati_a_mano": manuali,
        "pubblicati_su_pun": tariffe_pun(colonnine),
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return errori


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")   # lettere accentate corrette anche su Windows
    righe, errori = leggi()
    print(f"{FILE_PREZZI.name}: {len(righe)} righe valide, {len(errori)} errori")
    for e in errori:
        print("  -", e)
    return 1 if errori else 0


if __name__ == "__main__":
    sys.exit(main())
