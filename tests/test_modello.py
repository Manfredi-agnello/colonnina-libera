"""Test della lettura degli orari PUN (dati inventati)."""
import unittest

from raccolta.modello import _orari


class TestOrari(unittest.TestCase):
    def test_orari_settimanali(self):
        o = {"regular_hours": [{"weekday": 2, "period_begin": "08:30", "period_end": "20:00"},
                               {"weekday": 1, "period_begin": "08:30:00", "period_end": "20:00"},
                               {"weekday": 9, "period_begin": "08:00", "period_end": "09:00"},   # giorno non valido
                               {"weekday": 3, "period_begin": None, "period_end": "20:00"}]}     # incompleto
        self.assertEqual(_orari(o), [[1, "08:30", "20:00"], [2, "08:30", "20:00"]])

    def test_sempre_aperta_o_senza_orari(self):
        self.assertIsNone(_orari({"twentyfourseven": True, "regular_hours": [{"weekday": 1}]}))
        self.assertIsNone(_orari({"twentyfourseven": False}))
        self.assertIsNone(_orari({}))


if __name__ == "__main__":
    unittest.main()
