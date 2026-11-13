"""Abbinamento tra i siti della PUN e le colonnine di OpenStreetMap.

Due punti di fonti diverse sono la "stessa colonnina" se sono vicini e l'operatore
non è in contrasto. Non si indovina: i casi incerti restano "dubbi" e si
controllano a mano.

Esiti per ogni sito PUN:
  confermata  entro 50 m e stesso operatore
  probabile   entro 50 m ma operatore non indicato in OSM,
              oppure entro 150 m con lo stesso operatore
  probabile_lontana  tra 50 e 150 m, operatore non indicato in OSM (da controllare)
  dubbia      entro 150 m ma operatore diverso
  solo_pun    nessuna colonnina OSM entro 150 m
Le colonnine OSM non abbinate sono "solo_osm" (forse mancano nella PUN).
"""
from __future__ import annotations

import math
import re

VICINO_M = 50
LONTANO_M = 150

# Parole che non distinguono un operatore dall'altro.
PAROLE_VUOTE = {
    "srl", "srls", "spa", "sas", "snc", "s", "r", "l", "p", "a", "gmbh", "inc", "ltd",
    "italia", "italy", "italiana", "societa", "società", "benefit", "socio", "unico",
    "mobility", "emobility", "e", "the", "on", "road", "of", "di", "del", "della",
    "energia", "energy", "charging", "charge", "ricarica", "way", "x", "group",
    "stations", "station", "services", "service", "sales", "marketplace", "vendita",
}
# Marchi commerciali per codice operatore (la parte "IT*XXX" dell'id della presa).
# Solo casi verificati: nella PUN "ENX" e "ENEL X WAY ITALIA SRL" hanno lo stesso
# codice IT*ENX; "BEC" e "Plenitude On The Road" hanno IT*PLN (Be Charge è il vecchio
# nome della rete Plenitude, gruppo Eni); IT*GES è DriWe (Go Electric Stations).
MARCHI = {"ENX": {"enel"}, "PLN": {"plenitude", "becharge", "eni"}, "GES": {"driwe"},
          "EWI": {"ewiva"}}
# Stesso operatore scritto in modi diversi (solo casi certi).
SINONIMI = {"enelx": "enel", "becharge": "becharge", "freetox": "freetox"}


def codice_operatore(sito: dict) -> str | None:
    """'IT*ENX*E...' -> 'ENX'; 'ITGESE123' -> 'GES'. None se non riconoscibile."""
    for p in sito.get("punti") or []:
        m = re.match(r"^[A-Z]{2}\*?([A-Z0-9]{3})", p.get("id") or "")
        if m:
            return m.group(1)
    return None


def parole_operatore(nome: str | None) -> set[str]:
    if not nome:
        return set()
    n = re.sub(r"\([^)]*\)", " ", nome.lower()).replace("&", " ")   # toglie "(Italy)", "(IT)"
    n = re.sub(r"\be[\.\-]?(mobility|moving)\b", " ", n)
    compatto = re.sub(r"[^a-z0-9]", "", n)
    if compatto in SINONIMI:
        return {SINONIMI[compatto]}
    parole = {p for p in re.split(r"[^a-z0-9àèéìòù]+", n) if p and p not in PAROLE_VUOTE}
    return {SINONIMI.get(p, p) for p in parole if len(p) >= 2}


def stesso_operatore(pun: str | None, osm: dict, extra: set[str] | None = None) -> bool | None:
    """True/False, oppure None se OSM non indica l'operatore.
    extra: altre parole che identificano lo stesso operatore (marchi, altri nomi PUN)."""
    nomi_osm = [osm.get(k) for k in ("operator", "brand", "network") if osm.get(k)]
    if not nomi_osm:
        return None
    p = parole_operatore(pun) | (extra or set())
    if not p:
        return None
    return any(p & parole_operatore(n) for n in nomi_osm)


def distanza_m(lat1, lon1, lat2, lon2) -> float:
    r = 6_371_000
    f1, f2 = math.radians(lat1), math.radians(lat2)
    df, dl = f2 - f1, math.radians(lon2 - lon1)
    a = math.sin(df / 2) ** 2 + math.cos(f1) * math.cos(f2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _griglia(osm: list[dict]) -> dict:
    """Indice per celle di ~1 km, per non confrontare ogni punto con tutti."""
    g: dict = {}
    for i, c in enumerate(osm):
        g.setdefault((round(c["lat"] * 100), round(c["lon"] * 100)), []).append(i)
    return g


def _vicini(g, osm, lat, lon):
    cy, cx = round(lat * 100), round(lon * 100)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            yield from g.get((cy + dy, cx + dx), [])


def esito(dist: float, stesso: bool | None) -> str:
    if dist <= VICINO_M and stesso:
        return "confermata"
    if (dist <= VICINO_M and stesso is None) or (dist <= LONTANO_M and stesso):
        return "probabile"
    if dist <= LONTANO_M and stesso is None:
        return "probabile_lontana"
    return "dubbia"


def abbina(siti: list[dict], osm: list[dict]) -> tuple[list[dict], list[dict]]:
    """Ritorna (una riga per sito PUN, colonnine OSM non abbinate).

    Abbinamento uno a uno: si accoppiano prima le coppie migliori (stesso
    operatore, poi più vicine); un punto OSM già usato non si riusa.
    """
    g = _griglia(osm)
    # Tutti i nomi PUN con lo stesso codice operatore valgono come sinonimi.
    per_codice: dict = {}
    for s in siti:
        cod = codice_operatore(s)
        if cod:
            per_codice.setdefault(cod, set()).update(parole_operatore(s.get("operatore")))
    coppie = []
    for i, s in enumerate(siti):
        cod = codice_operatore(s)
        extra = per_codice.get(cod, set()) | MARCHI.get(cod, set())
        for j in _vicini(g, osm, s["lat"], s["lon"]):
            d = distanza_m(s["lat"], s["lon"], osm[j]["lat"], osm[j]["lon"])
            if d <= LONTANO_M:
                stesso = stesso_operatore(s.get("operatore"), osm[j], extra)
                priorita = {True: 0, None: 1, False: 2}[stesso]
                coppie.append((priorita, d, i, j, stesso))
    coppie.sort()
    usati_pun, usati_osm, scelte = set(), set(), {}
    for priorita, d, i, j, stesso in coppie:
        if i in usati_pun or j in usati_osm:
            continue
        usati_pun.add(i); usati_osm.add(j)
        scelte[i] = (j, d, stesso)

    righe = []
    for i, s in enumerate(siti):
        if i in scelte:
            j, d, stesso = scelte[i]
            righe.append({"sito": s, "osm": osm[j], "distanza_m": round(d),
                          "stesso_operatore": stesso, "esito": esito(d, stesso)})
        else:
            righe.append({"sito": s, "osm": None, "distanza_m": None,
                          "stesso_operatore": None, "esito": "solo_pun"})
    sola_osm = [c for j, c in enumerate(osm) if j not in usati_osm]
    return righe, sola_osm
