import sys
import unittest
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

from pruefbericht import erstelle_pruefbericht


class PruefberichtTest(unittest.TestCase):
    def test_bericht_enthaelt_keine_dateipfade_und_nur_bestaetigte_werte(self):
        dokumente = [
            {
                "dateiname": "lohn.pdf",
                "pfad": r"C:\\privat\\lohn.pdf",
                "dokumenttyp": "Elektronische Lohnsteuerbescheinigung",
                "steuerjahr": "2025",
                "status": "Geprüft",
                "wertvorschlaege": [
                    {"bezeichnung": "Steuerklasse", "wert": "1", "status": "Bestätigt"},
                    {"bezeichnung": "Kinderfreibetrag", "wert": "0,5", "status": "Zu prüfen"},
                ],
            }
        ]
        bericht = erstelle_pruefbericht("2025", ["arbeitnehmer"], dokumente)
        self.assertEqual(1, bericht["zusammenfassung"]["bestaetigte_werte"])
        self.assertEqual("Steuerklasse", bericht["bestaetigte_werte"][0]["bezeichnung"])
        self.assertNotIn("pfad", str(bericht).lower())
        self.assertNotIn("C:\\privat", str(bericht))

    def test_falsches_steuerjahr_wird_nicht_einbezogen(self):
        dokumente = [{"dateiname": "alt.pdf", "dokumenttyp": "Rentenbezugsmitteilung", "steuerjahr": "2024", "status": "Geprüft"}]
        bericht = erstelle_pruefbericht("2025", ["rente"], dokumente)
        self.assertEqual(0, bericht["zusammenfassung"]["dokumente"])

    def test_bericht_traegt_nutzername_und_steuerjahr(self):
        bericht = erstelle_pruefbericht("2024", [], [], "Alex Beispiel")
        self.assertEqual("Alex Beispiel", bericht["nutzer_name"])
        self.assertEqual("2024", bericht["steuerjahr"])
        self.assertEqual([], bericht["dokumente"])


if __name__ == "__main__":
    unittest.main()
