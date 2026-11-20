"""Test della cancellazione dei dati grezzi oltre 12 mesi (archivio inventato)."""
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from raccolta import manutenzione as m


def archivio(cartella: Path, giorni: list[str]):
    """Un file eventi/cicli/anagrafica per giorno; nell'evento la presa A cambia stato ogni giorno."""
    for i, g in enumerate(giorni):
        anno = g[:4]
        for sotto in ("eventi", "cicli", "anagrafica"):
            (cartella / sotto / anno).mkdir(parents=True, exist_ok=True)
        stato = "CHARGING" if i % 2 else "AVAILABLE"
        (cartella / "eventi" / anno / f"{g}.csv").write_text(
            f"ts,id,stato_raw\n{g}T10:00:00Z,A,{stato}\n" + (f"{g}T11:00:00Z,B,OUTOFORDER\n" if i == 0 else ""),
            encoding="utf-8")
        (cartella / "cicli" / anno / f"{g}.csv").write_text(
            f"ts,zona_osservate,tutte_lette,tutte_attese\n{g}T10:00:00Z,2,10,10\n", encoding="utf-8")
        pd.DataFrame({"id": ["A", "B"]}).to_parquet(cartella / "anagrafica" / anno / f"{g}.parquet")


def riassunto(cartella: Path, mese: str):
    (cartella / "riassunti").mkdir(exist_ok=True)
    (cartella / "riassunti" / f"{mese}.json").write_text("{}", encoding="utf-8")


class TestManutenzione(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.c = Path(self._tmp.name)
        archivio(self.c, ["2026-01-15", "2026-01-31", "2026-02-10", "2026-02-28", "2026-03-01"])

    def tearDown(self):
        self._tmp.cleanup()

    def file(self, sotto="eventi"):
        return sorted(f.stem for f in (self.c / sotto).glob("[0-9]*/*"))

    def test_limite(self):
        self.assertEqual(m.limite(date(2027, 11, 5)), date(2026, 11, 1))
        self.assertEqual(m.limite(date(2027, 1, 3)), date(2026, 1, 1))

    def test_non_cancella_senza_riassunto(self):
        riassunto(self.c, "2026-02")             # manca gennaio: ci si ferma subito
        r = m.esegui(self.c, date(2027, 3, 5))
        self.assertEqual(r["mesi_cancellati"], [])
        self.assertEqual(r["mesi_senza_riassunto"], ["2026-01", "2026-02"])
        self.assertEqual(len(self.file()), 5)

    def test_cancella_con_margine_e_ripartenza(self):
        riassunto(self.c, "2026-01")
        riassunto(self.c, "2026-02")
        r = m.esegui(self.c, date(2027, 3, 5))   # si tiene dal 1/3/2026, più il margine del 28/2
        self.assertEqual(r["mesi_cancellati"], ["2026-01", "2026-02"])
        for sotto in ("eventi", "cicli", "anagrafica"):
            self.assertEqual(self.file(sotto), ["2026-02-28", "2026-03-01"])
        rip = pd.read_csv(self.c / m.FILE_RIPARTENZA, dtype=str).set_index("id")
        self.assertEqual(rip.loc["A", "stato_raw"], "AVAILABLE")    # ultimo evento cancellato: 10/2 (i=2)
        self.assertEqual(rip.loc["B", "stato_raw"], "OUTOFORDER")   # non cambiava dal 15/1: resta
        self.assertTrue((self.c / ".compatta").exists())

    def test_una_volta_al_mese_e_dal_giorno_3(self):
        self.assertFalse(m.esegui(self.c, date(2027, 3, 2))["fatto"])   # troppo presto
        self.assertTrue(m.esegui(self.c, date(2027, 3, 3))["fatto"])
        self.assertFalse(m.esegui(self.c, date(2027, 3, 20))["fatto"])  # già fatto questo mese
        self.assertEqual(json.loads((self.c / "manutenzione.json").read_text())["ultimo_mese"], "2027-03")


if __name__ == "__main__":
    unittest.main()
