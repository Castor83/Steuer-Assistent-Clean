import json
import unittest
from pathlib import Path


KATALOG = Path(__file__).with_name("bfh_pilot_katalog_30.json")


class BfhKatalogTest(unittest.TestCase):
    def test_katalog_hat_30_eindeutige_faelle(self):
        faelle = json.loads(KATALOG.read_text(encoding="utf-8"))
        self.assertEqual(30, len(faelle))
        self.assertEqual(30, len({fall["id"] for fall in faelle}))

    def test_katalog_ist_ausgewogen(self):
        faelle = json.loads(KATALOG.read_text(encoding="utf-8"))
        self.assertEqual(15, sum(fall["erwartet"] == "treffer" for fall in faelle))
        self.assertEqual(15, sum(fall["erwartet"] == "kein_treffer" for fall in faelle))

    def test_positive_faelle_haben_aktenzeichen(self):
        faelle = json.loads(KATALOG.read_text(encoding="utf-8"))
        self.assertTrue(all(fall.get("aktenzeichen") for fall in faelle if fall["erwartet"] == "treffer"))


if __name__ == "__main__":
    unittest.main()
