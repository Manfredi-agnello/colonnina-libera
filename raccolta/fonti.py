"""Altre fonti (OpenStreetMap e Open Charge Map) per il sito.

Ogni giro (operazione veloce, < 1 s):
  - abbina i siti PUN di live.json con le colonnine OSM e OCM salvate in stato/;
  - scrive nel sito DUE file SEPARATI, ognuno con la sua licenza:
      osm.json  © contributori di OpenStreetMap, ODbL
      ocm.json  Open Charge Map, CC BY 4.0
    (tenerli separati evita di mescolare dati con licenze diverse: vedi METODO.md).

Una volta al giorno (se possibile) riscarica le due fonti. Se un download
fallisce si tiene la copia precedente e si riprova dopo un'ora: il sito non si
ferma mai per colpa delle fonti secondarie.

Uso (nel workflow, dopo il giro PUN):
    python -m raccolta.fonti --stato stato --sito out/sito
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import ocm, osm
from .incrocio import abbina, distanza_m

log = logging.getLogger("raccolta.fonti")

ORE_VALIDITA = 24          # le fonti fisse si riscaricano una volta al giorno
ORE_TRA_TENTATIVI = 1      # dopo un errore si riprova al più tra un'ora
ABBINATA = ("confermata", "probabile")
LONTANO_DA_PUN_M = 400     # oltre questa distanza da ogni sito PUN, una colonnina è "fuori PUN"
TEMPI_VELOCI = {"tentativi": 2, "attesa": 5, "timeout": 75}   # il giro ha pochi minuti

CAMPI_OSM = ["name", "opening_hours", "capacity", "fee", "charge", "access", "parking_fee",
             "maxstay", "covered", "level", "check_date"]
CAMPI_OCM = ["link", "posti", "costo", "accesso", "verificata", "stato", "ultimi_commenti"]


def adesso() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _leggi(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _da_aggiornare(dati: dict | None, tentativo: Path) -> bool:
    """Vero se la copia manca o ha più di 24 ore, e non si è appena fallito."""
    if dati and adesso() - datetime.fromisoformat(dati["scaricato"]) < timedelta(hours=ORE_VALIDITA):
        return False
    t = _leggi(tentativo)
    if t and adesso() - datetime.fromisoformat(t["ts"]) < timedelta(hours=ORE_TRA_TENTATIVI):
        return False
    return True


def aggiorna_download(stato: Path, errori: list[str]) -> None:
    tentativo = stato / "fonti_ultimo_tentativo.json"
    file_osm, file_ocm = stato / "osm.json", stato / "ocm.json"
    fallito = False
    if _da_aggiornare(_leggi(file_osm), tentativo):
        try:
            osm.salva(osm.scarica(**TEMPI_VELOCI), file_osm)
            log.info("OpenStreetMap aggiornato")
        except Exception as e:  # noqa: BLE001
            errori.append(f"OpenStreetMap non aggiornato, uso la copia precedente: {e}")
            fallito = True
    chiave = ocm.leggi_chiave()
    if chiave and _da_aggiornare(_leggi(file_ocm), tentativo):
        try:
            ocm.salva(ocm.scarica(chiave, **TEMPI_VELOCI), file_ocm)
            log.info("Open Charge Map aggiornato")
        except Exception as e:  # noqa: BLE001 - nel messaggio non c'è mai la chiave
            errori.append(f"Open Charge Map non aggiornato, uso la copia precedente: {type(e).__name__}")
            fallito = True
    if fallito:
        tentativo.write_text(json.dumps({"ts": adesso().isoformat()}), encoding="utf-8")


def _scegli(c: dict, campi: list[str]) -> dict:
    return {k: c[k] for k in campi if c.get(k) not in (None, "", [])}


def prepara(siti: list[dict], col_osm: list[dict], col_ocm: list[dict]) -> tuple[dict, dict]:
    """Ritorna (per_osm, per_ocm): {"per_sito": {id_sito: dati}, "fuori_pun": [...]}."""
    r_osm, solo_osm = abbina(siti, col_osm)
    r_ocm, solo_ocm = abbina(siti, col_ocm)
    per_osm = {r["sito"]["id"]: {"id": r["osm"]["id"], **_scegli(r["osm"], CAMPI_OSM)}
               for r in r_osm if r["esito"] in ABBINATA}
    per_ocm = {r["sito"]["id"]: {"id": r["osm"]["id"], **_scegli(r["osm"], CAMPI_OCM)}
               for r in r_ocm if r["esito"] in ABBINATA}

    # Fuori dalla PUN: solo se ci sono ENTRAMBE le fonti, l'accesso non è privato
    # e Open Charge Map non la dà per rimossa o non funzionante.
    def lontana(c):
        return all(distanza_m(c["lat"], c["lon"], s["lat"], s["lon"]) > LONTANO_DA_PUN_M for s in siti)
    cand_osm = [c for c in solo_osm if c.get("access") not in ("private", "no") and lontana(c)]
    cand_ocm = [c for c in solo_ocm if not c.get("rimossa") and c.get("operativa") is not False and lontana(c)]
    come_siti = [{**c, "operatore": c.get("operator") or c.get("brand") or c.get("network")} for c in cand_osm]
    righe, _ = abbina(come_siti, cand_ocm)
    fuori_osm, fuori_ocm = [], []
    for r in righe:
        if r["esito"] not in ABBINATA:
            continue
        o, m = r["sito"], r["osm"]
        chiave = f"f-{o['id']}"
        fuori_osm.append({"chiave": chiave, "id": o["id"], "lat": o["lat"], "lon": o["lon"],
                          "operatore": o["operatore"], "prese": o.get("prese"), **_scegli(o, CAMPI_OSM)})
        fuori_ocm.append({"chiave": chiave, "id": m["id"], "operatore": m.get("operator"),
                          "prese": m.get("prese"), **_scegli(m, CAMPI_OCM)})
    return ({"per_sito": per_osm, "fuori_pun": fuori_osm},
            {"per_sito": per_ocm, "fuori_pun": fuori_ocm})


def _scrivi(percorso: Path, dati: dict) -> None:
    tmp = percorso.with_suffix(".tmp")
    tmp.write_text(json.dumps(dati, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(percorso)


def scrivi_per_sito(stato: Path, cartella_sito: Path) -> dict:
    live = _leggi(cartella_sito / "live.json")
    if not live:
        raise RuntimeError("live.json mancante: prima va fatto il giro PUN")
    dati_osm, dati_ocm = _leggi(stato / "osm.json"), _leggi(stato / "ocm.json")
    per_osm, per_ocm = prepara(live["siti"], (dati_osm or {}).get("colonnine", []),
                               (dati_ocm or {}).get("colonnine", []))
    if dati_osm:
        _scrivi(cartella_sito / "osm.json", {
            "fonte": "OpenStreetMap", "licenza": "ODbL 1.0",
            "attribuzione": "© contributori di OpenStreetMap",
            "link_licenza": "https://www.openstreetmap.org/copyright",
            "scaricato": dati_osm["scaricato"], **per_osm})
    if dati_ocm:
        _scrivi(cartella_sito / "ocm.json", {
            "fonte": "Open Charge Map", "licenza": "CC BY 4.0",
            "attribuzione": "Open Charge Map e i suoi contributori",
            "link_licenza": "https://creativecommons.org/licenses/by/4.0/deed.it",
            "scaricato": dati_ocm["scaricato"], **per_ocm})
    return {"osm": len(per_osm["per_sito"]), "ocm": len(per_ocm["per_sito"]),
            "fuori_pun": len(per_osm["fuori_pun"])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stato", default="stato")
    ap.add_argument("--sito", default="out/sito")
    ap.add_argument("--senza-download", action="store_true", help="usa solo le copie già salvate")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    stato, sito = Path(args.stato), Path(args.sito)
    errori: list[str] = []
    if not args.senza_download:
        aggiorna_download(stato, errori)
    for e in errori:
        log.warning(e)
    n = scrivi_per_sito(stato, sito)
    log.info("altre fonti: %s siti con dati OSM, %s con dati OCM, %s colonnine fuori PUN",
             n["osm"], n["ocm"], n["fuori_pun"])
    return 0   # mai "fallito": le fonti secondarie non devono fermare il sito


if __name__ == "__main__":
    sys.exit(main())
