from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from steuerakte import erstelle_steuerakte, erstelle_steuerakten, plausibilitaet_pruefen


class SteuerakteTest(unittest.TestCase):
    def setUp(self):
        self.profil = {
            "person": {"angestellter": True, "wohnt_im_standardobjekt": True},
            "grundabgaben_standardobjekt": {
                "nutzung": "teilweise selbst genutzt und teilweise vermietet"
            },
        }

    def test_akten_fuer_2023_2024_und_2025_werden_getrennt_erstellt(self):
        dokumente = [
            {
                "dateiname": "lohn-2024.pdf",
                "dokumenttyp": "Elektronische Lohnsteuerbescheinigung",
                "steuerjahr": "2024",
                "status": "Geprüft",
                "nutzerzuordnung": {"status": "Erkannt"},
                "wertvorschlaege": [],
            }
        ]
        akten = erstelle_steuerakten(self.profil, dokumente)
        self.assertEqual(["2023", "2024", "2025"], [akte["steuerjahr"] for akte in akten])
        self.assertEqual(0, akten[0]["zusammenfassung"]["dokumente"])
        self.assertEqual(1, akten[1]["zusammenfassung"]["dokumente"])
        self.assertEqual(0, akten[2]["zusammenfassung"]["dokumente"])

    def test_unplausibler_bruttolohn_mit_beitraegen_wird_markiert(self):
        dokument = {
            "dateiname": "lohn-2025.pdf",
            "dokumenttyp": "Elektronische Lohnsteuerbescheinigung",
            "steuerjahr": "2025",
            "status": "Zu prüfen",
            "nutzerzuordnung": {"status": "Erkannt"},
            "wertvorschlaege": [
                {"id": "steuerklasse", "wert": "1", "status": "Bestätigt"},
                {"id": "bruttoarbeitslohn", "wert": "0,00 €", "status": "Zu prüfen"},
                {"id": "rentenversicherung", "wert": "210,00 €", "status": "Zu prüfen"},
            ],
        }
        warnungen = plausibilitaet_pruefen("2025", [dokument])
        codes = {warnung["code"] for warnung in warnungen}
        self.assertIn("brutto_null_mit_beitraegen", codes)
        self.assertIn("lohnwert_fehlt_lohnsteuer", codes)

    def test_falsches_jahr_im_dateinamen_wird_erkannt(self):
        dokument = {
            "dateiname": "lohnsteuer-2024.pdf",
            "dokumenttyp": "Elektronische Lohnsteuerbescheinigung",
            "steuerjahr": "2025",
            "status": "Geprüft",
            "nutzerzuordnung": {"status": "Erkannt"},
            "wertvorschlaege": [],
        }
        codes = {w["code"] for w in plausibilitaet_pruefen("2025", [dokument])}
        self.assertIn("jahr_dateiname", codes)

    def test_akte_zeigt_status_und_naechste_schritte(self):
        akte = erstelle_steuerakte("2023", ["arbeitnehmer"], [])
        self.assertEqual("Noch nicht begonnen", akte["status"])
        self.assertEqual(0, akte["fortschritt_prozent"])
        self.assertTrue(any("Lohnsteuerbescheinigung" in schritt for schritt in akte["naechste_schritte"]))

    def test_dokument_ohne_jahr_erfuellt_keine_jahrescheckliste(self):
        dokument = {
            "dateiname": "lohnsteuer.pdf",
            "dokumenttyp": "Elektronische Lohnsteuerbescheinigung",
            "steuerjahr": "Nicht erkannt",
            "status": "Zu prüfen",
            "nutzerzuordnung": {"status": "Erkannt"},
            "wertvorschlaege": [],
        }
        akte = erstelle_steuerakte("2024", ["arbeitnehmer"], [dokument])
        self.assertEqual(0, akte["fortschritt_prozent"])
        self.assertEqual(0, akte["zusammenfassung"]["dokumente"])
        self.assertEqual(1, akte["zusammenfassung"]["unzugeordnete_dokumente"])


if __name__ == "__main__":
    unittest.main()
