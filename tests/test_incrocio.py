"""Test dell'abbinamento PUN–OpenStreetMap e del filtro Sicilia (dati inventati)."""
import unittest

from raccolta.incrocio import abbina, parole_operatore, stesso_operatore
from raccolta.osm import da_risposta, in_sicilia

# 0,0001 gradi di latitudine sono circa 11 m.
def sito(id_, lat, lon, operatore):
    return {"id": id_, "lat": lat, "lon": lon, "operatore": operatore, "punti": []}


class TestOperatori(unittest.TestCase):
    def test_stesso_operatore_scritto_diverso(self):
        self.assertTrue(stesso_operatore("ENEL X WAY ITALIA SRL", {"operator": "Enel X"}))
        self.assertTrue(stesso_operatore("A2A E.MOBILITY S.R.L.", {"operator": "A2A"}))
        self.assertTrue(stesso_operatore("Tesla Italia Srl.", {"brand": "Tesla"}))

    def test_operatori_diversi(self):
        self.assertFalse(stesso_operatore("ENEL X WAY ITALIA SRL", {"operator": "Duferco Mobility"}))
        # "Mobility" da solo non basta per dire che sono uguali
        self.assertFalse(stesso_operatore("DUFERCO MOBILITY SRL", {"operator": "A2A E.Mobility"}))

    def test_operatore_non_indicato(self):
        self.assertIsNone(stesso_operatore("ENEL X WAY ITALIA SRL", {"name": "Colonnina"}))
        self.assertEqual(parole_operatore(None), set())


class TestAbbinamento(unittest.TestCase):
    def test_esiti(self):
        siti = [sito("vicina", 38.1000, 13.3000, "Enel X Way"),
                sito("senza_op", 38.2000, 13.3000, "Enel X Way"),
                sito("altro_op", 38.3000, 13.3000, "Enel X Way"),
                sito("lontana_stesso", 38.4000, 13.3000, "A2A"),
                sito("sola", 38.5000, 13.3000, "Enel X Way")]
        osm = [{"id": "node/1", "lat": 38.1002, "lon": 13.3000, "operator": "Enel X"},     # ~22 m
               {"id": "node/2", "lat": 38.2003, "lon": 13.3000},                           # ~33 m
               {"id": "node/3", "lat": 38.3002, "lon": 13.3000, "operator": "Be Charge"},  # ~22 m
               {"id": "node/4", "lat": 38.4010, "lon": 13.3000, "operator": "A2A"},        # ~111 m
               {"id": "node/5", "lat": 37.5000, "lon": 14.0000, "operator": "Privato"}]
        righe, sola_osm = abbina(siti, osm)
        esiti = {r["sito"]["id"]: r["esito"] for r in righe}
        self.assertEqual(esiti, {"vicina": "confermata", "senza_op": "probabile", "altro_op": "dubbia",
                                 "lontana_stesso": "probabile", "sola": "solo_pun"})
        self.assertEqual([c["id"] for c in sola_osm], ["node/5"])

    def test_uno_a_uno_preferisce_stesso_operatore(self):
        # Due siti PUN vicini allo stesso punto OSM: vince quello dello stesso operatore,
        # anche se un po' più lontano.
        siti = [sito("altro", 38.1000, 13.3000, "Duferco"), sito("giusto", 38.1003, 13.3000, "Enel X Way")]
        osm = [{"id": "node/1", "lat": 38.1001, "lon": 13.3000, "operator": "Enel X"}]
        righe, sola_osm = abbina(siti, osm)
        esiti = {r["sito"]["id"]: r["esito"] for r in righe}
        self.assertEqual(esiti, {"altro": "solo_pun", "giusto": "confermata"})
        self.assertEqual(sola_osm, [])


class TestCodiceOperatore(unittest.TestCase):
    def test_sigla_pun_riconosciuta_dal_codice(self):
        # "ENX" da solo non dice nulla, ma il codice IT*ENX è quello di Enel X Way.
        s = {"id": "a", "lat": 38.1, "lon": 13.3, "operatore": "ENX",
             "punti": [{"id": "IT*ENX*E12345*1"}]}
        osm = [{"id": "node/1", "lat": 38.1001, "lon": 13.3, "operator": "Enel X Way"}]
        righe, _ = abbina([s], osm)
        self.assertEqual(righe[0]["esito"], "confermata")

    def test_codice(self):
        from raccolta.incrocio import codice_operatore
        self.assertEqual(codice_operatore({"punti": [{"id": "IT*PLN*E1"}]}), "PLN")
        self.assertEqual(codice_operatore({"punti": [{"id": "ITGESE2376"}]}), "GES")
        self.assertIsNone(codice_operatore({"punti": []}))


class TestOsm(unittest.TestCase):
    def test_filtro_sicilia(self):
        self.assertTrue(in_sicilia(38.19, 15.55))    # Messina
        self.assertFalse(in_sicilia(38.11, 15.65))   # Reggio Calabria
        self.assertFalse(in_sicilia(35.90, 14.51))   # Malta
        self.assertTrue(in_sicilia(35.50, 12.60))    # Lampedusa

    def test_lettura_risposta(self):
        risposta = {"elements": [
            {"type": "node", "id": 1, "lat": 38.12, "lon": 13.36,
             "tags": {"amenity": "charging_station", "operator": "Enel X", "socket:type2": "2",
                      "socket:type2_combo": "yes", "opening_hours": "24/7"}},
            {"type": "way", "id": 2, "center": {"lat": 38.11, "lon": 15.65}, "tags": {}},   # Calabria
            {"type": "node", "id": 3, "tags": {}}]}                                          # senza coordinate
        c = da_risposta(risposta)
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]["id"], "node/1")
        self.assertEqual(c[0]["prese"], {"IEC_62196_T2": 2, "IEC_62196_T2_COMBO": 1})
        self.assertEqual(c[0]["opening_hours"], "24/7")


if __name__ == "__main__":
    unittest.main()
