"""Test con dati inventati dal risultato noto.

Si simula una mattina di giri ogni 5 minuti (10:00-11:55 UTC del 3 novembre
2026, cioè 11:00-12:55 ora italiana) e si scrive l'archivio con lo STESSO codice
usato dalla raccolta vera (raccolta.hub.aggiorna). Poi si controlla che le
analisi diano i numeri calcolati a mano.

Esecuzione:  python -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

RADICE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RADICE))

from analisi import calcoli, dati  # noqa: E402
from raccolta import hub  # noqa: E402

IPOTESI = json.loads((RADICE / "config" / "ipotesi_analisi.json").read_text(encoding="utf-8"))
HUB = {"lat": 38.0, "lon": 13.0, "raggio_km": 3}
INIZIO = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)


def presa(id_, corrente, kw, operatore="OP1"):
    return {"id": id_, "sito": id_, "lat": 38.001, "lon": 13.001, "stato_raw": "AVAILABLE",
            "tempo_reale": True, "operatore": operatore, "indirizzo": "Via Prova", "citta": "Palermo",
            "provincia": "PA", "regione": "Sicilia", "cap": "90100", "parcheggio": None,
            "servizi": [], "h24": True, "connettori": [{"standard": "X", "corrente": corrente, "kw": kw}],
            "kw_max": kw, "corrente": corrente, "tariffe_pun": None, "pubblicazione": "PUBLISHED"}


def stato_al_minuto(id_, m):
    """Copione della mattina (m = minuti dalle 10:00 UTC)."""
    if id_ == "DC50":       # in carica nelle letture da 10:05 a 10:40
        return "CHARGING" if 5 <= m <= 40 else "AVAILABLE"
    if id_ == "AC22":       # in carica in una sola lettura (10:20)
        return "CHARGING" if m == 20 else "AVAILABLE"
    if id_ == "GUASTA":     # sempre fuori servizio
        return "OUTOFORDER"
    if id_ == "HPC150":     # in carica da 10:50 a 11:40, ma 11:05-11:25 è un buco
        return "CHARGING" if 50 <= m <= 100 else "AVAILABLE"
    if id_ == "LUNGA":      # DC in carica tutta la mattina: oltre le 3 ore? no, 2 ore -> non lunga
        return "CHARGING"
    raise KeyError(id_)


PRESE = [presa("DC50", "DC", 50.0), presa("AC22", "AC_3_PHASE", 22.0), presa("GUASTA", "DC", 50.0),
         presa("HPC150", "DC", 150.0, "OP2"), presa("LUNGA", "DC", 50.0)]
BUCO = range(65, 90)    # giri falliti tra 11:05 e 11:25 (inclusi)


def costruisci_archivio(cartella: Path):
    for m in range(0, 120, 5):
        ts = (INIZIO + timedelta(minutes=m)).isoformat().replace("+00:00", "Z")
        if m in BUCO:
            # giro fallito: si registra il ciclo come incompleto, senza colonnine
            hub._accoda_csv(cartella / "cicli" / "2026" / "2026-11-03.csv",
                            ["ts", "zona_osservate", "tutte_lette", "tutte_attese"],
                            [[ts, 0, 0, len(PRESE)]])
            continue
        colonnine = []
        for p in PRESE:
            c = dict(p)
            c["corrente"] = "DC" if p["corrente"] == "DC" else "AC"
            c["stato_raw"] = stato_al_minuto(p["id"], m)
            colonnine.append(c)
        hub.aggiorna(colonnine, {p["id"] for p in PRESE}, ts, HUB, cartella)


class TestAnalisi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cartella = Path(cls.tmp.name)
        costruisci_archivio(cartella)
        cls.d = dati.carica(cartella)
        cls.dal = pd.Timestamp(INIZIO)
        cls.al = cls.dal + pd.Timedelta(hours=2)
        cls.s = calcoli.sessioni(cls.d.letture, cls.d.anagrafica, IPOTESI, cls.dal, cls.al).set_index("id")
        cls.tab = calcoli.tabella_oraria(cls.d.letture, cls.dal, cls.al,
                                         IPOTESI["sessioni"]["buco_massimo_min"])

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_sessione_dc_durata_e_kwh(self):
        s = self.s.loc["DC50"]
        # inizio a metà tra 10:00 e 10:05, fine a metà tra 10:40 e 10:45 -> 40 minuti
        self.assertEqual(s["inizio_locale"], "2026-11-03 11:02")
        self.assertAlmostEqual(s["durata_min"], 40.0)
        # 0,55 x 50 kW x 40/60 h = 18,33 kWh
        self.assertAlmostEqual(s["kwh_stimati"], 18.33, places=2)
        self.assertFalse(s["incerta"])
        self.assertEqual(s["classe"], "DC fino a 99 kW")

    def test_sessione_ac_una_lettura(self):
        s = self.s.loc["AC22"]
        self.assertAlmostEqual(s["durata_min"], 5.0)                  # da 10:17:30 a 10:22:30
        self.assertAlmostEqual(s["kwh_stimati"], round(7.4 * 5 / 60, 2))  # AC: 7,4 kW, non 22
        self.assertEqual(s["classe"], "AC")

    def test_sessione_attraverso_un_buco_e_incerta(self):
        s = self.s.loc["HPC150"]
        self.assertTrue(s["incerta"])
        self.assertEqual(s["classe"], "DC da 100 kW in su")
        # 10:47:30 -> 11:42:30 = 55 minuti
        self.assertAlmostEqual(s["durata_min"], 55.0)

    def test_sessione_tagliata_ai_bordi_e_incerta_e_con_tetto_kwh(self):
        s = self.s.loc["LUNGA"]
        self.assertTrue(s["incerta"])          # nessuna lettura prima: inizio sconosciuto
        self.assertFalse(s["lunga"])           # 1h55 < 3 ore
        self.assertLessEqual(s["kwh_stimati"], IPOTESI["energia"]["kwh_massimi_per_sessione"])

    def test_nessuna_sessione_per_la_presa_guasta(self):
        self.assertNotIn("GUASTA", self.s.index)

    def test_minuti_occupati_e_buco_non_osservato(self):
        t = self.tab.set_index(["id", "ora"])
        # 10-11 UTC = ore 11 italiane: DC50 occupata dalle 10:02:30 alle 10:42:30 = 40 minuti
        self.assertEqual(t.loc[("DC50", 11), "min_occupata"], 40)
        # 11-12 UTC = ore 12 italiane: buco 11:02:30-11:27:30 (letture 11:00 e 11:30 a 30 min > 15)
        #   -> l'intervallo 11:00-11:30 è tutto non osservato; osservati 30 minuti (11:30-11:55)
        #      più l'ultimo tratto fino a 11:55 (dopo l'ultima lettura: non osservato)
        self.assertEqual(t.loc[("GUASTA", 12), "min_osservati"], 25)
        self.assertEqual(t.loc[("GUASTA", 12), "min_guasta"], 25)

    def test_percentuali_e_affidabilita(self):
        op = calcoli.operatori_con_occupazione(self.d.letture, self.d.anagrafica)
        df = calcoli.arricchisci(self.tab, self.d.anagrafica, IPOTESI, op)
        p = calcoli.percentuali(df, ["id"]).set_index("id")
        self.assertEqual(p.loc["GUASTA", "guasto_pct"], 100.0)
        self.assertEqual(p.loc["GUASTA", "occupazione_pct"], 0.0)
        self.assertEqual(p.loc["DC50", "guasto_pct"], 0.0)


if __name__ == "__main__":
    unittest.main()
