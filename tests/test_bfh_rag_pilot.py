import sys
import unittest
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

import bfh_rag_pilot


class BfhRagPilotTest(unittest.TestCase):
    def test_steuerrechtliche_norm_wird_erkannt(self):
        self.assertTrue(bfh_rag_pilot.ist_steuerlich_relevant({"normen": "EStG § 9"}))

    def test_reines_verfahrensfremdes_thema_wird_nicht_erkannt(self):
        zeile = {"normen": "BGB § 433", "titel": "Kaufvertrag", "text_leitsatz": "Zivilrecht"}
        self.assertFalse(bfh_rag_pilot.ist_steuerlich_relevant(zeile))

    def test_fgo_allein_reicht_nicht_fuer_alltagssteuer_pilot(self):
        zeile = {
            "normen": "FGO § 115 Abs 2",
            "titel": "Rechtsschutzbedürfnis einer Beschwerde",
            "text_leitsatz": "Die Beschwerde ist unzulässig.",
        }
        self.assertFalse(bfh_rag_pilot.ist_steuerlich_relevant(zeile))

    def test_stromsteuer_spezialfall_wird_nicht_ueber_wort_steuer_aufgenommen(self):
        zeile = {
            "normen": "StromStG § 9|FGO § 115",
            "titel": "Einschränkung des Versorgerstatus bei der Stromsteuer",
            "text_leitsatz": "Die Stromsteuerbegünstigung ist ausgeschlossen.",
        }
        self.assertFalse(bfh_rag_pilot.ist_steuerlich_relevant(zeile))

    def test_finanzamt_allein_reicht_nicht_fuer_prozessentscheidung(self):
        zeile = {
            "normen": "FGO § 96",
            "titel": "Bezugnahme auf einen Schriftsatz des Finanzamts",
            "text_leitsatz": "Das Gericht darf auf den Schriftsatz Bezug nehmen.",
        }
        self.assertFalse(bfh_rag_pilot.ist_steuerlich_relevant(zeile))

    def test_eintrag_kennzeichnet_historische_rechtsprechung(self):
        zeile = {
            "bfh_id": "TEST1",
            "aktenzeichen": "VI R 1/24",
            "ecli": "ECLI:DE:BFH:2024:TEST",
            "datum": "2024-01-02",
            "entscheidungsjahr": "2024",
            "titel": "Werbungskosten eines Arbeitnehmers",
            "text_leitsatz": "Die Voraussetzungen richten sich nach dem EStG.",
            "normen": "EStG § 9",
            "url_html": "https://www.bundesfinanzhof.de/test",
        }
        eintrag = bfh_rag_pilot.erstelle_eintrag(zeile)
        self.assertEqual("historische_bfh_rechtsprechung", eintrag["status"])
        self.assertTrue(eintrag["rechtsstand_separat_pruefen"])
        self.assertIn("VI R 1/24", eintrag["suchtext"])
        self.assertEqual(2024, eintrag["entscheidungsjahr"])
        self.assertEqual("Arbeitnehmer", eintrag["thema"])

    def test_punkt_id_ist_stabil(self):
        self.assertEqual(bfh_rag_pilot.punkt_id("ABC"), bfh_rag_pilot.punkt_id("ABC"))
        self.assertNotEqual(bfh_rag_pilot.punkt_id("ABC"), bfh_rag_pilot.punkt_id("ABD"))

    def test_pilot_collection_ist_versioniert(self):
        self.assertTrue(bfh_rag_pilot.COLLECTION.endswith("_v2"))

    def test_pilotfragen_decken_fuenf_alltagsbereiche_ab(self):
        self.assertEqual(5, len(bfh_rag_pilot.TESTFAELLE))
        gesamt = " ".join(frage for frage, _ in bfh_rag_pilot.TESTFAELLE).casefold()
        for wort in ("arbeitszimmer", "vermietung", "photovoltaik", "erbschaft", "kindergeld"):
            self.assertIn(wort, gesamt)

    def test_umsatzsteuer_hat_vorrangigen_themenkorb(self):
        zeile = {
            "normen": "UStG § 15|EStG § 9",
            "titel": "Vorsteuer bei einer vermieteten Anlage",
            "text_leitsatz": "Der Vorsteuerabzug ist zu prüfen.",
        }
        self.assertEqual("Umsatzsteuer", bfh_rag_pilot.bestimme_thema(zeile))


if __name__ == "__main__":
    unittest.main()
