"""Test della lettura dei dati Open Charge Map (dati inventati, nessuna rete)."""
import os
import unittest
from unittest import mock

from raccolta import ocm

RIF = {"stati": {50: {"Title": "Operational", "IsOperational": True},
                 200: {"Title": "Removed (Decomissioned)", "IsOperational": False}},
       "fornitori": {1: {"Title": "Open Charge Map Contributors", "License": "Licensed under CC BY 4.0"}},
       "operatori": {1: {"Title": "(Unknown Operator)"}, 80: {"Title": "Enel X"}},
       "commenti": {10: {"Title": "General Comment"}},
       "checkin": {10: {"Title": "Charged Successfully"}}}


class TestOcm(unittest.TestCase):
    def test_normalizza(self):
        poi = {"ID": 123, "DataProviderID": 1, "OperatorID": 80, "StatusTypeID": 200,
               "AddressInfo": {"Latitude": 38.12, "Longitude": 13.36, "Title": "Piazza"},
               "Connections": [{"ConnectionTypeID": 33, "Quantity": 2}, {"ConnectionTypeID": 25}],
               "UserComments": [{"DateCreated": "2026-01-01T10:00:00Z", "CommentTypeID": 10,
                                 "CheckinStatusTypeID": 10, "Comment": "ok"},
                                {"DateCreated": "2026-03-01T10:00:00Z", "CommentTypeID": 10, "Comment": "rimossa"}]}
        c = ocm.normalizza(poi, RIF)
        self.assertEqual(c["id"], "ocm/123")
        self.assertEqual(c["operator"], "Enel X")
        self.assertTrue(c["rimossa"])
        self.assertFalse(c["operativa"])
        self.assertEqual(c["prese"], {"IEC_62196_T2_COMBO": 2, "IEC_62196_T2": 1})
        self.assertEqual(c["licenza"], "Licensed under CC BY 4.0")
        self.assertEqual(c["ultimi_commenti"][0]["testo"], "rimossa")   # il più recente prima

    def test_operatore_sconosciuto_diventa_vuoto(self):
        poi = {"ID": 1, "OperatorID": 1, "AddressInfo": {"Latitude": 38, "Longitude": 13}}
        self.assertIsNone(ocm.normalizza(poi, RIF)["operator"])

    def test_chiave_segnaposto_ignorata(self):
        with mock.patch.dict(os.environ, {"OCM_CHIAVE": "LA-TUA-CHIAVE-QUI"}):
            self.assertIsNone(ocm.leggi_chiave())
        with mock.patch.dict(os.environ, {"OCM_CHIAVE": "abc123"}):
            self.assertEqual(ocm.leggi_chiave(), "abc123")


if __name__ == "__main__":
    unittest.main()
