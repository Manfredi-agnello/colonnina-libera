"""Riepiloghi pubblici leggeri: "di solito è libera a quest'ora?" e "quanto spesso è guasta?".

Non salviamo lo storico: per ogni colonnina teniamo dei CONTATORI per fascia
oraria (48 fasce: 24 ore dei giorni feriali + 24 ore del fine settimana).
Ad ogni giro si aggiunge 1 osservazione alla fascia corrente.
Ogni giorno tutti i contatori vengono moltiplicati per DECADIMENTO, così i dati
vecchi pesano sempre meno ("memoria" di circa un mese: dopo 21 giorni un dato
pesa la metà). Il file resta sempre della stessa dimensione.

Occupazione: ha senso solo per colonnine "in tempo reale" il cui operatore
ha segnalato almeno una volta lo stato CHARGING (alcuni operatori dicono solo
se la colonnina funziona, mai se è occupata: vedi usage_semantics.py del
progetto originale).
"""
from __future__ import annotations

import gzip
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .modello import categoria

ROMA = ZoneInfo("Europe/Rome")
DECADIMENTO = 0.967          # per giorno: dimezzamento in ~21 giorni
MIN_OSSERVAZIONI_FASCIA = 3  # sotto questa soglia la fascia è "dato insufficiente"
FASCE = 48


def fascia(istante: datetime) -> int:
    locale = istante.astimezone(ROMA)
    return locale.hour + (24 if locale.weekday() >= 5 else 0)


class Profili:
    def __init__(self, percorso: Path):
        self.percorso = percorso
        if percorso.exists():
            d = json.loads(gzip.decompress(percorso.read_bytes()))
        else:
            d = {"giorno": None, "operatori_con_occupazione": [], "c": {}}
        self.giorno = d["giorno"]
        self.operatori_occ = set(d["operatori_con_occupazione"])
        # c[id] = [osservazioni[48], occupata[48], guasta[48]]
        self.c: dict[str, list[list[float]]] = d["c"]

    def _decadi_fino_a(self, oggi: date) -> None:
        if self.giorno is None:
            self.giorno = oggi.isoformat()
            return
        giorni = (oggi - date.fromisoformat(self.giorno)).days
        if giorni <= 0:
            return
        f = DECADIMENTO ** giorni
        for serie in self.c.values():
            for riga in serie:
                for i in range(FASCE):
                    riga[i] *= f
        self.giorno = oggi.isoformat()

    def aggiungi(self, colonnine: list[dict], istante: datetime) -> None:
        self._decadi_fino_a(istante.astimezone(ROMA).date())
        f = fascia(istante)
        for c in colonnine:
            if (c["stato_raw"] or "").upper() == "CHARGING" and c["operatore"]:
                self.operatori_occ.add(c["operatore"])
        for c in colonnine:
            if not c["tempo_reale"]:
                continue
            cat = categoria(c["stato_raw"])
            if cat not in ("libera", "occupata", "guasta"):
                continue        # stato sconosciuto/rimossa: non è un'osservazione utile
            serie = self.c.setdefault(c["id"], [[0.0] * FASCE for _ in range(3)])
            serie[0][f] += 1
            if cat == "occupata":
                serie[1][f] += 1
            elif cat == "guasta":
                serie[2][f] += 1

    def salva(self) -> None:
        d = {"giorno": self.giorno,
             "operatori_con_occupazione": sorted(self.operatori_occ),
             "c": {k: [[round(x, 3) for x in riga] for riga in v] for k, v in self.c.items()}}
        self.percorso.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.percorso.with_suffix(".tmp")
        tmp.write_bytes(gzip.compress(json.dumps(d, separators=(",", ":")).encode()))
        tmp.replace(self.percorso)

    def esporta_per_sito(self, colonnine: list[dict], cartella: Path) -> int:
        """profili.json: per colonnina, % di tempo occupata per fascia (null = dati
        insufficienti) e % di tempo guasta complessiva. Numeri interi 0-100."""
        operatore = {c["id"]: c["operatore"] for c in colonnine}
        out = {}
        for id_, (oss, occ, gua) in self.c.items():
            tot = sum(oss)
            if id_ not in operatore or tot < MIN_OSSERVAZIONI_FASCIA:
                continue
            voce = {"guasta_pct": round(100 * sum(gua) / tot)}
            if operatore[id_] in self.operatori_occ:
                voce["occupata_pct"] = [
                    round(100 * occ[i] / oss[i]) if oss[i] >= MIN_OSSERVAZIONI_FASCIA else None
                    for i in range(FASCE)]
            out[id_] = voce
        cartella.mkdir(parents=True, exist_ok=True)
        (cartella / "profili.json").write_text(
            json.dumps({"giorno": self.giorno, "decadimento_giornaliero": DECADIMENTO,
                        "fasce": "0-23 feriali, 24-47 sabato e domenica (ora italiana)",
                        "colonnine": out}, separators=(",", ":")),
            encoding="utf-8")
        (cartella / "operatori.json").write_text(
            json.dumps(self._affidabilita_operatori(operatore), ensure_ascii=False,
                       separators=(",", ":")), encoding="utf-8")
        return len(out)

    def _affidabilita_operatori(self, operatore: dict) -> list[dict]:
        """Per operatore: % del tempo osservato con prese fuori servizio (pesata sul
        tempo, non sul numero di prese) e se segnala l'occupazione."""
        tot: dict[str, list[float]] = {}
        for id_, (oss, _occ, gua) in self.c.items():
            op = operatore.get(id_)
            if not op:
                continue
            t = tot.setdefault(op, [0.0, 0.0, 0])
            t[0] += sum(oss)
            t[1] += sum(gua)
            t[2] += 1
        return sorted(({"operatore": op, "prese": n, "guasta_pct": round(100 * g / o, 1),
                        "segnala_occupazione": op in self.operatori_occ}
                       for op, (o, g, n) in tot.items() if o >= 50),
                      key=lambda v: (-v["prese"], v["operatore"]))
