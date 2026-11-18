"""Test del controllo di prezzi.csv (file temporanei, dati inventati)."""
import tempfile
import unittest
from pathlib import Path

from raccolta.prezzi import leggi

INTESTAZIONE = "operatore;tipo;prezzo_kwh;costo_minuto;costo_avvio;id_colonnina;data_rilevazione;fonte;note\n"


def prova(righe: str):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "prezzi.csv"
        p.write_text(INTESTAZIONE + righe, encoding="utf-8")
        return leggi(p)


class TestPrezzi(unittest.TestCase):
    def test_riga_valida_con_virgola_decimale(self):
        r, e = prova("Enel;AC;0,69;;;;2026-11-18;sito ufficiale;di notte 0,61\n")
        self.assertEqual(e, [])
        self.assertEqual(r[0]["prezzo_kwh"], 0.69)
        self.assertEqual(r[0]["note"], "di notte 0,61")

    def test_separatore_nelle_note(self):
        r, e = prova("Enel;AC;0,69;;;;2026-11-18;sito ufficiale;dalle 7; di notte 0,61\n")
        self.assertEqual(r, [])
        self.assertIn("troppe colonne", e[0])

    def test_errori_comuni(self):
        r, e = prova("Enel;XX;9;;;;18/11/2026;;\n")
        self.assertEqual(r, [])
        testo = " ".join(e)
        for atteso in ("tipo", "fuori scala", "data_rilevazione", "fonte"):
            self.assertIn(atteso, testo)


if __name__ == "__main__":
    unittest.main()
