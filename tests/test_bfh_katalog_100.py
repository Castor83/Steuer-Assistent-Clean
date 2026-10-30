import json
import unittest
from pathlib import Path


KATALOG = Path(__file__).with_name("bfh_pilot_katalog_100.json")


class BfhKatalog100Test(unittest.TestCase):
    def test_katalog_hat_100_ausgewogene_faelle(self):
        faelle = json.loads(KATALOG.read_text(encoding="utf-8"))
        self.assertEqual(100, len(faelle))
        self.assertEqual(50, sum(x["erwartet"] == "treffer" for x in faelle))
        self.assertEqual(50, sum(x["erwartet"] == "kein_treffer" for x in faelle))
        self.assertEqual(100, len({x["id"] for x in faelle}))

    def test_negative_faelle_stammen_aus_vorhandenen_katalogen(self):
        faelle = json.loads(KATALOG.read_text(encoding="utf-8"))
        negative = [x for x in faelle if x["erwartet"] == "kein_treffer"]
        self.assertTrue(all(x["herkunft"] == "vorhandener_fragenkatalog" for x in negative))
        self.assertTrue(all(x.get("quelle_datei") for x in negative))


if __name__ == "__main__":
    unittest.main()
