"""Un giro di raccolta. Uso:

    python -m raccolta --stato stato --sito out/sito [--hub hub-dati] [--ripeti 12 --intervallo 300]

--stato  cartella con i file che servono tra un giro e l'altro (elenco colonnine,
         contatori, registro errori). Su GitHub vive nel branch "stato".
--sito   cartella dove scrivere i file pubblici per il sito (live.json, profili.json, stato.json).
--hub    cartella dell'archivio PRIVATO della zona hub (facoltativa).

Codice di uscita 1 se il giro non ha prodotto dati: GitHub Actions lo segna
come fallito e ti manda un'email.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import hub, sito
from .modello import normalizza
from .profili import Profili
from .pun import ErrorePUN, SessionePUN

RADICE = Path(__file__).resolve().parent.parent
AREA = json.loads((RADICE / "config" / "area.json").read_text(encoding="utf-8"))
ORE_VALIDITA_ELENCO = 24
MAX_RIGHE_REGISTRO = 500

log = logging.getLogger("raccolta")


def adesso() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def registra_errore(stato: Path, messaggio: str) -> None:
    """Registro errori pubblico: contiene solo messaggi tecnici, mai dati della zona hub."""
    p = stato / "registro_errori.jsonl"
    righe = p.read_text(encoding="utf-8").splitlines() if p.exists() else []
    righe.append(json.dumps({"ts": adesso().isoformat(), "errore": messaggio}, ensure_ascii=False))
    p.write_text("\n".join(righe[-MAX_RIGHE_REGISTRO:]) + "\n", encoding="utf-8")
    log.error(messaggio)


def nell_area(rec: dict) -> bool:
    loc = rec.get("location") or {}
    cap = str(loc.get("postal_code") or "").strip()
    if cap.isdigit() and len(cap) == 5:
        return AREA["cap_min"] <= cap <= AREA["cap_max"]
    return str(loc.get("region") or "").strip().lower() in AREA["regioni"]


def elenco_colonnine(pun: SessionePUN, stato: Path) -> list[str]:
    """Id delle colonnine dell'area. Rifatto al massimo una volta ogni 24 ore.

    L'età si legge DENTRO il file (campo "aggiornato"), non dalla data del file:
    su GitHub ogni download rimette la data del file a "adesso" e l'elenco
    sembrerebbe sempre nuovo (era il difetto del progetto originale).
    """
    p = stato / "elenco_colonnine.json"
    if p.exists():
        d = json.loads(p.read_text(encoding="utf-8"))
        eta = adesso() - datetime.fromisoformat(d["aggiornato"])
        if eta < timedelta(hours=ORE_VALIDITA_ELENCO):
            return d["id"]
    try:
        la0, la1, lo0, lo1 = AREA["bbox"]
        nel_rettangolo = sorted({
            v["evse_id"] for v in pun.elenco_nazionale()
            if v.get("evse_id") and (v.get("coordinates") or {}).get("latitude") is not None
            and la0 <= float(v["coordinates"]["latitude"]) <= la1
            and lo0 <= float(v["coordinates"]["longitude"]) <= lo1})
        # Il rettangolo comprende anche un pezzo di Calabria: teniamo solo la regione giusta.
        record, errori = pun.dettagli(nel_rettangolo)
        if errori:
            raise ErrorePUN(f"elenco incompleto: {errori[0]}")
        ids = sorted(r["evse_id"] for r in record if nell_area(r))
    except ErrorePUN as e:
        if p.exists():
            registra_errore(stato, f"aggiornamento elenco fallito, uso quello vecchio: {e}")
            return json.loads(p.read_text(encoding="utf-8"))["id"]
        raise
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"aggiornato": adesso().isoformat(), "area": AREA["nome"],
                             "id": ids}, indent=0), encoding="utf-8")
    log.info("elenco colonnine aggiornato: %s nel rettangolo, %s in %s",
             len(nel_rettangolo), len(ids), AREA["nome"])
    return ids


def un_giro(args) -> bool:
    t0 = time.time()
    stato, cartella_sito = Path(args.stato), Path(args.sito)
    stato.mkdir(parents=True, exist_ok=True)
    pun = SessionePUN()
    try:
        ids = elenco_colonnine(pun, stato)
    except ErrorePUN as e:
        registra_errore(stato, f"impossibile ottenere l'elenco delle colonnine: {e}")
        return False

    istante = adesso()
    ts = istante.isoformat().replace("+00:00", "Z")
    record, errori = pun.dettagli(ids)
    for e in errori:
        registra_errore(stato, f"gruppo di colonnine non letto: {e}")
    colonnine = [c for c in map(normalizza, record) if c]
    if not colonnine:
        registra_errore(stato, "nessuna colonnina letta in questo giro")
        return False

    conteggi = sito.scrivi_live(colonnine, ts, cartella_sito)
    profili = Profili(stato / "profili.json.gz")
    profili.aggiungi(colonnine, istante)
    profili.salva()
    n_profili = profili.esporta_per_sito(colonnine, cartella_sito)

    hub_ok = None
    if args.hub:
        cfg = hub.leggi_configurazione()
        if cfg is None:
            registra_errore(stato, "archivio hub richiesto ma coordinate non configurate")
            hub_ok = False
        else:
            try:
                hub.aggiorna(colonnine, set(ids), ts, cfg, Path(args.hub))
                hub_ok = True
            except Exception as e:  # noqa: BLE001 - nel log solo il tipo, mai i dati
                registra_errore(stato, f"archivio hub: {type(e).__name__}")
                hub_ok = False

    durata = round(time.time() - t0, 1)
    sito.scrivi_stato_raccolta({
        "aggiornato": ts,
        "durata_s": durata,
        "colonnine_attese": len(ids),
        "colonnine_lette": len(colonnine),
        "siti": conteggi["siti"],
        "richieste_pun": pun.richieste,
        "tentativi_ripetuti": pun.tentativi_ripetuti,
        "errori": len(errori),
    }, cartella_sito)
    log.info("giro %s: %s/%s colonnine, %s siti, %s profili, %s richieste, %.1fs%s",
             ts, len(colonnine), len(ids), conteggi["siti"], n_profili, pun.richieste, durata,
             "" if hub_ok is None else f", archivio hub {'ok' if hub_ok else 'ERRORE'}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stato", default="stato")
    ap.add_argument("--sito", default="out/sito")
    ap.add_argument("--hub", default=None)
    ap.add_argument("--ripeti", type=int, default=1, help="numero di giri (default 1)")
    ap.add_argument("--intervallo", type=int, default=300, help="secondi tra i giri")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%H:%M:%S")
    for name in ("botocore", "boto3", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)

    ok_tutti = True
    for i in range(args.ripeti):
        t0 = time.time()
        ok_tutti &= un_giro(args)
        if i < args.ripeti - 1:
            time.sleep(max(1, args.intervallo - (time.time() - t0)))
    return 0 if ok_tutti else 1


if __name__ == "__main__":
    sys.exit(main())
