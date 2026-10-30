from io import BytesIO
import json
from pathlib import Path
import sys
import unittest
from zipfile import ZipFile


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from elster_export import erstelle_elster_eingabehilfe, erstelle_elster_export_zip


class ElsterExportTest(unittest.TestCase):
    def setUp(self):
        self.profil = {
            "quelle": "vom Nutzer bestätigt",
            "wohnsitz": {
                "strasse": "Beispielstraße",
                "hausnummer": "1",
                "postleitzahl": "00000",
                "stadt": "Erlangen",
                "land": "Deutschland",
            },
        }

    def test_nur_bestaetigte_werte_des_richtigen_jahres_werden_exportiert(self):
        dokumente = [
            {
                "dateiname": "lohn-2025.pdf",
                "dokumenttyp": "Elektronische Lohnsteuerbescheinigung",
                "steuerjahr": "2025",
                "status": "Geprüft",
                "wertvorschlaege": [
                    {"id": "bruttoarbeitslohn", "bezeichnung": "Brutto", "wert": "40.000,00 €", "status": "Bestätigt"},
                    {"id": "lohnsteuer", "bezeichnung": "Lohnsteuer", "wert": "5.000,00 €", "status": "Zu prüfen"},
                ],
            },
            {
                "dateiname": "lohn-2024.pdf",
                "steuerjahr": "2024",
                "status": "Geprüft",
                "wertvorschlaege": [
                    {"id": "bruttoarbeitslohn", "bezeichnung": "Brutto", "wert": "30.000,00 €", "status": "Bestätigt"}
                ],
            },
        ]
        export = erstelle_elster_eingabehilfe("2025", ["arbeitnehmer"], dokumente, self.profil, "Alex Beispiel")
        werte = [feld["wert"] for feld in export["felder"]]
        self.assertIn("40.000,00 €", werte)
        self.assertNotIn("5.000,00 €", werte)
        self.assertNotIn("30.000,00 €", werte)
        self.assertFalse(export["versandfaehig"])
        self.assertFalse(export["direkt_in_mein_elster_importierbar"])
        self.assertEqual(1, export["zusammenfassung"]["bestaetigte_dokumentwerte"])
        self.assertEqual(1, export["zusammenfassung"]["unbestaetigte_dokumentwerte"])
        self.assertGreaterEqual(export["zusammenfassung"]["profilfelder"], 1)

    def test_unbekanntes_bestaetigtes_feld_wird_nicht_falsch_zugeordnet(self):
        dokument = {
            "dateiname": "beleg.pdf",
            "steuerjahr": "2023",
            "status": "Geprüft",
            "wertvorschlaege": [
                {"id": "unbekannt", "bezeichnung": "Sonderwert", "wert": "123", "status": "Bestätigt"}
            ],
        }
        export = erstelle_elster_eingabehilfe("2023", [], [dokument], self.profil, "Alex Beispiel")
        self.assertEqual(1, len(export["nicht_zugeordnete_bestaetigte_werte"]))
        self.assertFalse(any(feld["wert"] == "123" for feld in export["felder"]))

    def test_zip_enthaelt_json_csv_und_deutlichen_hinweis(self):
        export = erstelle_elster_eingabehilfe("2024", ["vermietung"], [], self.profil, "Alex Beispiel")
        self.assertEqual("Alex Beispiel", export["nutzer_name"])
        daten = erstelle_elster_export_zip(export)
        with ZipFile(BytesIO(daten)) as archiv:
            self.assertEqual(
                {"elster-eingabehilfe-2024.json", "elster-eingabehilfe-2024.csv", "BITTE-LESEN.txt"},
                set(archiv.namelist()),
            )
            json_daten = json.loads(archiv.read("elster-eingabehilfe-2024.json"))
            self.assertEqual("2024", json_daten["steuerjahr"])
            self.assertIn("nicht direkt", archiv.read("BITTE-LESEN.txt").decode("utf-8"))
            self.assertIn("Nutzer: Alex Beispiel", archiv.read("BITTE-LESEN.txt").decode("utf-8"))

    def test_geschuetzte_stammdaten_und_bestaetigte_manuelle_werte_werden_zugeordnet(self):
        manuell = [
            {
                "steuerjahr": "2023",
                "feld_id": "arbeitsmittel",
                "bezeichnung": "Arbeitsmittel",
                "wert": "250,00 €",
                "quelle": "Rechnung Schreibtisch",
                "status": "Bestätigt",
            },
            {
                "steuerjahr": "2023",
                "feld_id": "fortbildungskosten",
                "wert": "100,00 €",
                "quelle": "Kursrechnung",
                "status": "Zu prüfen",
            },
        ]
        export = erstelle_elster_eingabehilfe(
            "2023",
            ["arbeitnehmer"],
            [],
            self.profil,
            "Alex Beispiel",
            {"steuer_id": "12345678901", "iban": "DE89370400440532013000"},
            manuell,
        )
        ids = {feld["lokale_feld_id"] for feld in export["felder"]}
        self.assertIn("stammdaten_steuer_id", ids)
        self.assertIn("stammdaten_iban", ids)
        self.assertIn("arbeitsmittel", ids)
        self.assertNotIn("fortbildungskosten", ids)
        self.assertEqual(1, export["zusammenfassung"]["bestaetigte_manuelle_werte"])
        self.assertEqual(1, export["zusammenfassung"]["unbestaetigte_manuelle_werte"])


if __name__ == "__main__":
    unittest.main()
