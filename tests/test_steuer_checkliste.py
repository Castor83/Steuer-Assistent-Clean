from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from steuer_checkliste import erstelle_checkliste


class SteuerChecklisteTest(unittest.TestCase):
    def test_arbeitnehmerunterlage_fuer_richtiges_jahr_ist_vorhanden(self):
        dokumente = [
            {
                "dateiname": "lohnsteuer-2025.pdf",
                "dokumenttyp": "Elektronische Lohnsteuerbescheinigung",
                "steuerjahr": "2025",
                "status": "Zu prüfen",
            }
        ]
        punkte = erstelle_checkliste("2025", ["arbeitnehmer"], dokumente)
        lohn = next(punkt for punkt in punkte if punkt["id"] == "lohn")
        self.assertEqual("Vorhanden", lohn["status"])
        self.assertEqual(["lohnsteuer-2025.pdf"], lohn["dokumente"])

    def test_falsches_steuerjahr_gilt_nicht_als_vorhanden(self):
        dokumente = [
            {
                "dateiname": "lohnsteuer-2024.pdf",
                "dokumenttyp": "Elektronische Lohnsteuerbescheinigung",
                "steuerjahr": "2024",
                "status": "Geprüft",
            }
        ]
        punkte = erstelle_checkliste("2025", ["arbeitnehmer"], dokumente)
        lohn = next(punkt for punkt in punkte if punkt["id"] == "lohn")
        self.assertEqual("Noch nicht gefunden", lohn["status"])

    def test_nicht_erkanntes_jahr_bleibt_als_kandidat_sichtbar(self):
        dokumente = [
            {
                "dateiname": "versicherung.pdf",
                "dokumenttyp": "Kranken- und Pflegeversicherungsbescheinigung",
                "steuerjahr": "Nicht erkannt",
                "status": "Zu prüfen",
            }
        ]
        punkte = erstelle_checkliste("2025", [], dokumente)
        versicherung = next(punkt for punkt in punkte if punkt["id"] == "versicherung")
        self.assertEqual("Vorhanden", versicherung["status"])

    def test_ausgewaehlte_bereiche_werden_ergaenzt(self):
        punkte = erstelle_checkliste("2025", ["kinder", "vermietung", "grundsteuer"], [])
        ids = {punkt["id"] for punkt in punkte}
        self.assertIn("kinderbetreuung", ids)
        self.assertIn("mietvertrag", ids)
        self.assertIn("grundsteuermessbetrag", ids)

    def test_vier_kernthemen_haben_eigene_unterlagenbereiche(self):
        punkte = erstelle_checkliste(
            "2025", ["arbeitnehmer", "insolvenzgeld", "grundsteuer", "erbschaft"], []
        )
        ids = {punkt["id"] for punkt in punkte}
        self.assertTrue({
            "lohn", "insolvenzgeld_nachweis", "grundsteuer_basis",
            "grundsteuermessbetrag", "grundsteuerkommune", "erbschaft_erwerb",
            "erbschaft_nachlass", "erbschaft_bescheid",
        }.issubset(ids))

    def test_bayerischer_aequivalenzbetragsbescheid_erfuellt_grundsteuerbasis(self):
        dokumente = [{
            "dateiname": "aequivalenzbetrag-2025.pdf",
            "dokumenttyp": "Grundsteueräquivalenzbetragsbescheid",
            "steuerjahr": "2025",
            "status": "Geprüft",
        }]
        punkte = erstelle_checkliste("2025", ["grundsteuer"], dokumente)
        basis = next(punkt for punkt in punkte if punkt["id"] == "grundsteuer_basis")
        self.assertEqual("Vorhanden", basis["status"])

    def test_unbekannter_bereich_wird_ignoriert(self):
        punkte = erstelle_checkliste("2025", ["unbekannt"], [])
        self.assertEqual({"stammdaten", "versicherung"}, {punkt["id"] for punkt in punkte})


if __name__ == "__main__":
    unittest.main()
