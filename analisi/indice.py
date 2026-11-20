"""Pagina iniziale del repository privato (README.md): elenco dei report e confronto tra
tutti i mesi, letto dai riassunti permanenti (riassunti/AAAA-MM.json).

    python -m analisi.indice --hub hub-dati

I riassunti restano anche quando i dati grezzi vengono cancellati (dopo 12 mesi),
quindi questa pagina mostra sempre tutta la storia.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .report_md import BLU, fmt, grafico_barre, mese_breve, nome_mese


def riassunti(hub: Path) -> dict[str, dict]:
    out = {}
    for f in sorted((hub / "riassunti").glob("*.json")):
        try:
            out[f.stem] = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
    return out


def scrivi_indice(hub: Path) -> Path:
    hub = Path(hub)
    tutti = riassunti(hub)
    righe = []
    for chiave in sorted(tutti, reverse=True):
        s = tutti[chiave]["sintesi"]
        link = f"report/mensili/{chiave}/" if (hub / "report" / "mensili" / chiave).exists() else None
        nome = f"[{nome_mese(chiave)}]({link})" if link else nome_mese(chiave)
        righe.append(f"| {nome} | {s['prese']} | {fmt(s['occupazione_media_pct'], 1, '%')} | "
                     f"{fmt(s['fuori_servizio_medio_pct'], 1, '%')} | {fmt(s['kwh_giorno_da_occupazione'], 0)} | "
                     f"{s['sessioni']} | {len(tutti[chiave]['colonnine_nuove'])} / {len(tutti[chiave]['colonnine_rimosse'])} | "
                     f"{fmt(s['copertura_pct'], 0, '%')} |")
    cronologia = sorted(tutti)
    if cronologia:
        (hub / "report").mkdir(exist_ok=True)
        (hub / "report" / "andamento.svg").write_text(grafico_barre(
            [mese_breve(c) for c in cronologia],
            [tutti[c]["sintesi"]["kwh_giorno_da_occupazione"] for c in cronologia],
            "kWh al giorno nella zona, mese per mese (stima dall'occupazione)", BLU), encoding="utf-8")
    richiesta = sorted((hub / "report" / "su-richiesta").glob("*/README.md"), reverse=True)
    testo = f"""# Archivio della zona

Archivio **privato** dello stato delle colonnine di ricarica nella zona scelta, scritto in automatico ogni
5 minuti circa. Pagina aggiornata il {datetime.now(timezone.utc):%d/%m/%Y}.

- **Dati grezzi** (`eventi/`, `cicli/`, `anagrafica/`): conservati **12 mesi**, poi cancellati in automatico.
- **Riassunti mensili** (`riassunti/`) e **report** (`report/`): conservati **per sempre**.
- Un nuovo report mensile arriva il **1° di ogni mese**. Per un periodo a scelta: scheda **Actions** →
  **report** → **Run workflow**, scegli le date (anche dall'app GitHub sul telefono).

## Mese per mese
{"![Andamento](report/andamento.svg)" if cronologia else ""}

| Mese | Prese | Occupazione | Fuori servizio | kWh/giorno | Sessioni viste | Nuove / sparite | Tempo coperto |
|---|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(righe) if righe else "| _ancora nessun mese completo_ | | | | | | | |"}

## Report su richiesta
{chr(10).join(f"- [{p.parent.name.replace('_', ' → ')}](report/su-richiesta/{p.parent.name}/)" for p in richiesta) or "_Nessuno._"}

_Dati PUN (MASE/GSE) rielaborati: non ufficiali. Come sono calcolati i numeri: METODO.md nel repository del sito._
"""
    (hub / "README.md").write_text(testo, encoding="utf-8")
    return hub / "README.md"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hub", default="hub-dati")
    args = ap.parse_args()
    print(f"Indice scritto: {scrivi_indice(Path(args.hub))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
