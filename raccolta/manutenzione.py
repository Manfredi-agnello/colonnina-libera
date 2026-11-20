"""Manutenzione mensile dell'archivio PRIVATO: cancella i dati grezzi più vecchi di
12 mesi e chiede la compattazione della storia Git.

Regole di sicurezza:
  - gira al massimo una volta al mese, dal giorno 3 (il report mensile del giorno 1
    deve aver già salvato il riassunto del mese);
  - un mese si cancella SOLO se esiste il suo riassunto permanente riassunti/AAAA-MM.json;
    se manca, ci si ferma lì (anche i mesi successivi restano) e lo si segnala;
  - prima di cancellare gli eventi si salva il "punto di ripartenza"
    (eventi/ripartenza/stato.csv): l'ultimo stato noto di ogni presa. L'archivio
    salva solo i CAMBI di stato, quindi senza questo file una colonnina che non
    cambia stato da mesi resterebbe "senza stato" nelle analisi.

La compattazione (storia Git ripartita da zero con i soli file attuali) la fa il
workflow quando trova il file .compatta: questo modulo non tocca Git.
Nei log (pubblici) stampa solo conteggi, mai dati delle colonnine.

    python -m raccolta.manutenzione --hub hub-dati [--oggi AAAA-MM-GG]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

MESI_DA_TENERE = 12
GIORNO_MINIMO = 3
CARTELLE_GREZZE = ("eventi", "cicli", "anagrafica")
FILE_RIPARTENZA = Path("eventi") / "ripartenza" / "stato.csv"


def _mese(giorno: str) -> str:
    return giorno[:7]


def limite(oggi: date, mesi: int = MESI_DA_TENERE) -> date:
    """Primo giorno da tenere: il 1° del mese di 12 mesi fa (es. 5/11/2027 -> 1/11/2026)."""
    totale = oggi.year * 12 + (oggi.month - 1) - mesi
    return date(totale // 12, totale % 12 + 1, 1)


def _file_vecchi(cartella: Path, primo_da_tenere: date) -> dict[str, list[Path]]:
    """{AAAA-MM: [file]} dei file giornalieri (AAAA-MM-GG.*) precedenti al limite.

    Si tiene UN GIORNO DI MARGINE (l'ultimo giorno del mese prima del limite): così le
    analisi del primo giorno rimasto vedono le letture della sera prima, e le ricariche
    in corso a mezzanotte non sembrano iniziare a mezzanotte. Il margine si cancella il
    mese dopo."""
    primo_da_tenere = primo_da_tenere - timedelta(days=1)
    per_mese: dict[str, list[Path]] = {}
    for sotto in CARTELLE_GREZZE:
        for f in (cartella / sotto).glob("[0-9][0-9][0-9][0-9]/*"):
            giorno = f.stem[:10]
            try:
                d = date.fromisoformat(giorno)
            except ValueError:
                continue
            if d < primo_da_tenere:
                per_mese.setdefault(_mese(giorno), []).append(f)
    return per_mese


def _aggiorna_ripartenza(cartella: Path, eventi_da_cancellare: list[Path]) -> None:
    """Ultimo stato noto di ogni presa, prendendo anche la ripartenza precedente."""
    p = cartella / FILE_RIPARTENZA
    pezzi = [pd.read_csv(f, dtype=str) for f in ([p] if p.exists() else []) + sorted(eventi_da_cancellare)]
    pezzi = [x for x in pezzi if not x.empty]
    if not pezzi:
        return
    tutti = pd.concat(pezzi, ignore_index=True)
    ultimo = tutti.sort_values("ts", kind="stable").groupby("id").tail(1).sort_values(["ts", "id"])
    p.parent.mkdir(parents=True, exist_ok=True)
    ultimo[["ts", "id", "stato_raw"]].to_csv(p, index=False)


def esegui(cartella: Path, oggi: date | None = None, mesi: int = MESI_DA_TENERE) -> dict:
    cartella = Path(cartella)
    oggi = oggi or datetime.now(timezone.utc).date()
    mese_attuale = oggi.isoformat()[:7]
    registro = cartella / "manutenzione.json"
    stato = json.loads(registro.read_text(encoding="utf-8")) if registro.exists() else {}
    if stato.get("ultimo_mese") == mese_attuale or oggi.day < GIORNO_MINIMO:
        return {"fatto": False}

    vecchi = _file_vecchi(cartella, limite(oggi, mesi))
    cancellati, senza_riassunto, n_file = [], [], 0
    for mese in sorted(vecchi):
        if not (cartella / "riassunti" / f"{mese}.json").exists():
            senza_riassunto = [m for m in sorted(vecchi) if m >= mese]
            break                          # ci si ferma: niente buchi nella sequenza degli eventi
        file = vecchi[mese]
        _aggiorna_ripartenza(cartella, [f for f in file if f.parent.parent.name == "eventi"])
        for f in file:
            f.unlink()
            n_file += 1
        cancellati.append(mese)
    for sotto in CARTELLE_GREZZE:          # cartelle degli anni rimaste vuote
        for anno in (cartella / sotto).glob("[0-9][0-9][0-9][0-9]"):
            if anno.is_dir() and not any(anno.iterdir()):
                anno.rmdir()

    stato = {"ultimo_mese": mese_attuale, "eseguita": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "tengo_dal": limite(oggi, mesi).isoformat(), "mesi_cancellati": cancellati,
             "mesi_senza_riassunto": senza_riassunto}
    registro.write_text(json.dumps(stato, indent=1), encoding="utf-8")
    (cartella / ".compatta").write_text(mese_attuale, encoding="utf-8")   # il workflow compatta la storia
    return {"fatto": True, "mesi_cancellati": cancellati, "file_cancellati": n_file,
            "mesi_senza_riassunto": senza_riassunto}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hub", default="hub-dati")
    ap.add_argument("--oggi", help="data da simulare (AAAA-MM-GG), solo per prove")
    args = ap.parse_args()
    r = esegui(Path(args.hub), date.fromisoformat(args.oggi) if args.oggi else None)
    if not r["fatto"]:
        print("manutenzione archivio: niente da fare questo mese")
    else:
        print(f"manutenzione archivio: {len(r['mesi_cancellati'])} mesi cancellati ({r['file_cancellati']} file), "
              f"{len(r['mesi_senza_riassunto'])} mesi tenuti perché manca il riassunto; compattazione richiesta")
    return 0


if __name__ == "__main__":
    sys.exit(main())
