"""Test delle regole per le altre fonti sul sito (dati inventati)."""
import unittest

from raccolta.fonti import prepara

SITO = {"id": "s1", "lat": 38.1000, "lon": 13.3000, "operatore": "Enel X Way",
        "punti": [{"id": "IT*ENX*E1"}]}


class TestPrepara(unittest.TestCase):
    def test_dati_per_sito_e_campi_scelti(self):
        osm = [{"id": "node/1", "lat": 38.1001, "lon": 13.3, "operator": "Enel X",
                "opening_hours": "24/7", "capacity": "2", "website": "x"}]
        ocm = [{"id": "ocm/9", "lat": 38.1001, "lon": 13.3, "operator": "Enel X", "link": "L",
                "ultimi_commenti": [{"data": "2026-01-01", "testo": "ok"}], "rimossa": False}]
        per_osm, per_ocm = prepara([SITO], osm, ocm)
        self.assertEqual(per_osm["per_sito"]["s1"], {"id": "node/1", "opening_hours": "24/7", "capacity": "2"})
        self.assertEqual(per_ocm["per_sito"]["s1"]["link"], "L")

    def test_fuori_pun_solo_se_entrambe_le_fonti(self):
        lontano = {"lat": 37.5, "lon": 14.0}
        osm = [{"id": "node/2", **lontano, "operator": "Lidl"},                       # anche in OCM: sì
               {"id": "node/3", "lat": 37.0, "lon": 14.5, "operator": "Lidl"},          # solo OSM: no
               {"id": "node/4", "lat": 36.9, "lon": 14.7, "access": "private"}]         # privata: no
        ocm = [{"id": "ocm/2", **lontano, "operator": "Lidl", "operativa": True},
               {"id": "ocm/4", "lat": 36.9, "lon": 14.7},
               {"id": "ocm/5", "lat": 36.5, "lon": 15.0, "rimossa": True}]
        per_osm, per_ocm = prepara([SITO], osm, ocm)
        self.assertEqual([c["id"] for c in per_osm["fuori_pun"]], ["node/2"])
        self.assertEqual([c["id"] for c in per_ocm["fuori_pun"]], ["ocm/2"])
        self.assertEqual(per_osm["fuori_pun"][0]["chiave"], per_ocm["fuori_pun"][0]["chiave"])

    def test_vicino_alla_pun_non_e_fuori(self):
        # A 200 m da un sito PUN: probabilmente la stessa colonnina, non va mostrata come "fuori".
        osm = [{"id": "node/5", "lat": 38.1018, "lon": 13.3, "operator": "Duferco"}]
        ocm = [{"id": "ocm/6", "lat": 38.1018, "lon": 13.3, "operator": "Duferco"}]
        per_osm, _ = prepara([SITO], osm, ocm)
        self.assertEqual(per_osm["fuori_pun"], [])


if __name__ == "__main__":
    unittest.main()
