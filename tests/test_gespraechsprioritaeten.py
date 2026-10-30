import sys
import unittest
from pathlib import Path


PROJEKT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJEKT / "app"))

import rag_assistent
import web_ui


PROFIL = {
    "wohnsitz": {"stadt": "Erlangen", "bundesland": "Bayern"},
    "grundabgaben_standardobjekt": {
        "stadt": "Erlangen",
        "bundesland": "Bayern",
        "gebaeudeart": "Dreifamilienhaus",
        "nutzung": "teilweise selbst genutzt und teilweise vermietet",
    },
}


class GespraechsprioritaetenTest(unittest.TestCase):
    def test_themenanker_bleibt_ueber_sechs_nutzerbeitraege_erhalten(self):
        verlauf = [
            {"rolle": "nutzer", "text": "Es geht um die bayerische Grundsteuer meiner Garage."},
            {"rolle": "assistent", "text": "Für Garagen gelten besondere Flächenregeln."},
        ]
        for nummer in range(1, 6):
            verlauf.extend(
                [
                    {"rolle": "nutzer", "text": f"Zwischenangabe {nummer}"},
                    {"rolle": "assistent", "text": "Verstanden."},
                ]
            )

        frage = web_ui.frage_mit_gespraechskontext(
            "Und was ist mit dem kleinen Schuppen daneben?", verlauf
        )

        self.assertIn("bayerische Grundsteuer meiner Garage", frage)
        self.assertIn("Aktuelle Ergänzung: Und was ist mit dem kleinen Schuppen", frage)

    def test_bayern_folge_geht_nicht_in_allgemeine_gebaeuderegel(self):
        frage = (
            "Vorheriger Gesprächskontext:\n"
            "Letzte Nutzerangabe: Bei der bayerischen Grundsteuer habe ich die Garage am Wohnhaus eingeordnet.\n"
            "Letzte Assistentenantwort: Für Garagen gelten besondere Flächenregeln.\n"
            "Aktuelle Ergänzung: Und was ist mit dem kleinen Schuppen daneben?"
        )
        antwort, quellen = rag_assistent.beantworte(
            frage,
            aktuelle_nachricht="Und was ist mit dem kleinen Schuppen daneben?",
            steuerprofil=PROFIL,
            steuerjahr="2023",
        )

        self.assertIn("bayerische Flächenmodell", antwort)
        self.assertIn("30 Quadratmeter", antwort)
        self.assertIn("Erlangen", antwort)
        self.assertNotIn("AfA", antwort)
        self.assertIn("Bayern", quellen[0].payload["kategorie"])

    def test_feste_jahresauswahl_schlaegt_altes_jahr_im_verlauf(self):
        frage = (
            "Vorheriger Gesprächskontext:\n"
            "Letzte Assistentenantwort: Seit 2025 gilt die neue Grundsteuer.\n"
            "Aktuelle Ergänzung: Wie hoch war der Grundfreibetrag?"
        )
        antwort, quellen = rag_assistent.beantworte(
            frage,
            aktuelle_nachricht="Wie hoch war der Grundfreibetrag?",
            steuerprofil=PROFIL,
            steuerjahr="2023",
        )

        self.assertIn("10.908 Euro", antwort)
        self.assertNotIn("12.096 Euro", antwort)
        self.assertEqual(2023, quellen[0].payload["steuerjahr"])

    def test_plattformmeldung_ist_keine_automatische_steuerpflicht(self):
        frage = (
            "Vorheriger Gesprächskontext:\n"
            "Letzte Nutzerangabe: Kleinanzeigen kann meine 30 Verkäufe an das Finanzamt melden.\n"
            "Letzte Assistentenantwort: Die Meldeschwelle ist keine Steuerfreigrenze.\n"
            "Aktuelle Ergänzung: Heißt das, ich muss jetzt automatisch Steuern zahlen?"
        )
        antwort, _ = rag_assistent.beantworte(
            frage,
            aktuelle_nachricht="Heißt das, ich muss jetzt automatisch Steuern zahlen?",
            steuerprofil=PROFIL,
            steuerjahr="2023",
        )

        self.assertTrue(antwort.startswith("Nein."))
        self.assertIn("nur, wann Daten übermittelt", antwort)
        self.assertIn("keine Steuerfreigrenze", antwort)
        self.assertIn("getrennt", antwort)

    def test_schenkungsanzeige_bleibt_von_steuer_getrennt(self):
        frage = (
            "Vorheriger Gesprächskontext:\n"
            "Letzte Nutzerangabe: Meine Mutter hat mir 20.000 Euro geschenkt.\n"
            "Letzte Assistentenantwort: Wegen des Freibetrags fällt voraussichtlich keine Steuer an.\n"
            "Aktuelle Ergänzung: Muss ich das trotzdem irgendwo melden?"
        )
        antwort, _ = rag_assistent.beantworte(
            frage,
            aktuelle_nachricht="Muss ich das trotzdem irgendwo melden?",
            steuerprofil=PROFIL,
            steuerjahr="2023",
        )

        self.assertIn("drei Monaten", antwort)
        self.assertIn("Schenkungsteuerfinanzamt", antwort)
        self.assertIn("von der Steuerpflicht zu trennen", antwort)
        self.assertIn("keine Schenkungsteuer", antwort)


if __name__ == "__main__":
    unittest.main()
