import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
QUELLEN = ROOT / "wissen" / "quellen"


class KatalogUndQuellenTest(unittest.TestCase):
    def test_alle_json_kataloge_sind_gueltig_und_haben_eindeutige_ids(self):
        for datei in sorted(TESTS.glob("*.json")):
            with self.subTest(datei=datei.name):
                daten = json.loads(datei.read_text(encoding="utf-8-sig"))
                self.assertIsInstance(daten, list)
                self.assertTrue(daten)
                ids = [eintrag.get("id") for eintrag in daten]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertTrue(all(isinstance(eintrag.get("frage"), str) and eintrag["frage"].strip() for eintrag in daten))

    def test_sollantwort_kataloge_sind_vollstaendig(self):
        for datei in sorted(TESTS.glob("neuer_testkatalog*.json")):
            daten = json.loads(datei.read_text(encoding="utf-8-sig"))
            with self.subTest(datei=datei.name):
                self.assertTrue(all(eintrag.get("erwartete_antwort") for eintrag in daten))
                self.assertTrue(all(isinstance(eintrag.get("ki_fallstricke", []), list) for eintrag in daten))

    def test_keine_versehentlichen_demokratiefragen_im_steuerkatalog(self):
        for datei in sorted(TESTS.glob("*.json")):
            text = datei.read_text(encoding="utf-8-sig").casefold()
            with self.subTest(datei=datei.name):
                self.assertNotIn("merkmal unserer demokratie", text)

    def test_steuerex_bleibt_getrennter_historischer_testbestand(self):
        datei = TESTS / "steuerex_haertetest_115.json"
        daten = json.loads(datei.read_text(encoding="utf-8"))
        self.assertEqual(len(daten), 115)
        self.assertTrue(all(eintrag["quelle"] == "SteuerEx Benchmark Dataset" for eintrag in daten))
        self.assertTrue(
            all(eintrag["quelle_url"] == "https://huggingface.co/datasets/windprak/SteuerEx" for eintrag in daten)
        )
        self.assertTrue(all(len(eintrag["quelle_sha256"]) == 64 for eintrag in daten))
        self.assertTrue(all(eintrag["lizenz"] == "CC BY-NC 4.0" for eintrag in daten))
        self.assertTrue(all(eintrag["aktualitaetspruefung_erforderlich"] is True for eintrag in daten))
        self.assertTrue(all(eintrag["erwartete_antwort"] is None for eintrag in daten))
        self.assertTrue(all(eintrag["automatische_fachbewertung"] is False for eintrag in daten))
        self.assertEqual(
            {eintrag["alltagsnaehe"] for eintrag in daten},
            {"eher_alltagsnah", "teilweise_alltagsnah", "spezialwissen"},
        )

    def test_amtliche_quellen_haben_alle_metadaten(self):
        erforderlich = {"titel", "herausgeber", "paragraph", "steuerjahr", "stand_abgerufen", "url", "kategorie", "inhalt"}
        dateien = sorted(QUELLEN.glob("*.json"))
        self.assertGreaterEqual(len(dateien), 90)
        for datei in dateien:
            with self.subTest(datei=datei.name):
                daten = json.loads(datei.read_text(encoding="utf-8"))
                self.assertFalse(erforderlich - daten.keys())
                self.assertTrue(all(str(daten[feld]).strip() for feld in erforderlich))
                self.assertTrue(str(daten["url"]).startswith("https://"))

    def test_elster_leitfaeden_sind_enthalten(self):
        namen = {datei.name for datei in QUELLEN.glob("elster_*.json")}
        self.assertIn("elster_belegabruf.json", namen)
        self.assertIn("elster_belege_steuererklaerung.json", namen)
        self.assertIn("elster_elektronische_steuererklaerung.json", namen)


if __name__ == "__main__":
    unittest.main()
