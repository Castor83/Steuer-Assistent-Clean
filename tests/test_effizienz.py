import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

import rag_assistent


class EffizienzTest(unittest.TestCase):
    def test_suchbegriffe_werden_nicht_durch_aufrufer_veraendert(self):
        vorher = rag_assistent.suchbegriffe("Werbungskosten Vermietung")
        veraendert = rag_assistent.suchbegriffe("Werbungskosten Vermietung")
        veraendert.clear()
        self.assertEqual(vorher, rag_assistent.suchbegriffe("Werbungskosten Vermietung"))

    def test_geaenderter_quelltext_hat_neue_suchbegriffe(self):
        rag_assistent.suchbegriffe("Werbungskosten Vermietung")
        neu = rag_assistent.suchbegriffe("Werbungskosten Vermietung Mietkaution")
        self.assertIn("mietkaution", neu)
        self.assertNotIn("mietkaution", rag_assistent.suchbegriffe("Werbungskosten Vermietung"))

    def test_standardantwort_ueberspringt_embedding_suche(self):
        with patch.object(
            rag_assistent.MODELL_RESSOURCEN,
            "embedding",
            side_effect=AssertionError("Embedding darf bei lexikalischem Treffer nicht laufen"),
        ):
            antwort, quellen = rag_assistent.beantworte(
                "Wo trage ich einen pauschal versteuerten Minijob ein?"
            )
        self.assertIn("nicht", antwort)
        self.assertTrue(quellen)
        self.assertTrue(all(q.payload.get("url", "").startswith("https://") for q in quellen))

    def test_langer_fall_wird_nicht_durch_beilaeufiges_stichwort_abgekuerzt(self):
        frage = (
            "Eine Rentnerin lebt überwiegend in Spanien und besitzt weiterhin eine regelmäßig "
            "genutzte Wohnung in Deutschland. Zu prüfen sind Wohnsitz, gewöhnlicher Aufenthalt "
            "und die unbeschränkte Steuerpflicht. "
            + "Weitere Angaben zum grenzüberschreitenden Sachverhalt. " * 12
            + "Ist sie in Deutschland unbeschränkt steuerpflichtig?"
        )
        self.assertGreater(len(frage), 500)
        with patch.object(
            rag_assistent,
            "quelle_aus_kategorie",
            side_effect=AssertionError("Keine Stichwort-Standardantwort verwenden"),
        ):
            self.assertIsNone(rag_assistent.schnelle_standardantwort(frage))

    def test_langer_fall_nutzt_nach_der_suche_keine_kurze_regelantwort(self):
        quelle = SimpleNamespace(
            payload={
                "kategorie": "Einkommensteuer",
                "quelle": "Amtliche Quelle",
                "paragraph": "§ 8 AO",
                "steuerjahr": "2026",
                "text": "Ein Wohnsitz setzt eine Wohnung unter Umständen voraus, die auf Beibehaltung schließen lassen.",
                "url": "https://www.gesetze-im-internet.de/ao_1977/__8.html",
            },
            score=1.0,
        )
        frage = (
            "Eine Rentnerin lebt überwiegend in Spanien und nutzt weiterhin ihre Wohnung in Deutschland. "
            + "Weitere Angaben zum grenzüberschreitenden Sachverhalt. " * 12
            + "Ist sie in Deutschland unbeschränkt steuerpflichtig?"
        )
        modellantwort = {"message": {"content": "Der gesamte Wohnsitzfall muss geprüft werden [1]."}}
        with (
            patch.object(rag_assistent, "suche_wissen", return_value=[quelle]),
            patch.object(rag_assistent, "ergaenze_spezialquelle", return_value=[quelle]),
            patch.object(rag_assistent.MODELL_RESSOURCEN, "chat", return_value=modellantwort),
        ):
            antwort, quellen = rag_assistent.beantworte(frage)
        self.assertIn("gesamte Wohnsitzfall", antwort)
        self.assertNotIn("Rentenfreibetrag", antwort)
        self.assertEqual([quelle], quellen)

    def test_rentenversicherungsbeitrag_wird_nicht_als_rentenbezug_beantwortet(self):
        antwort, quellen = rag_assistent.beantworte(
            "Sind Beiträge zur gesetzlichen Rentenversicherung steuerlich relevant?"
        )
        self.assertIn("Vorsorgeaufwendungen", antwort)
        self.assertNotIn("Rentenfreibetrag", antwort)
        self.assertTrue(quellen)

    def test_vorsorgeaufwendungen_ueberblick_nennt_kernversicherungen(self):
        antwort, quellen = rag_assistent.beantworte(
            "Welche Versicherungsbeiträge sind als Vorsorgeaufwendungen relevant?"
        )
        self.assertIn("Rentenversicherung", antwort)
        self.assertIn("Kranken-", antwort)
        self.assertTrue(quellen)

    def test_fachliteratur_beruecksichtigt_arbeitnehmer_pauschbetrag(self):
        antwort, quellen = rag_assistent.beantworte(
            "Ich habe berufliche Fachliteratur für 200 Euro gekauft und sonst keine Werbungskosten."
        )
        self.assertIn("1.230 Euro", antwort)
        self.assertIn("kein zusätzlicher Steuervorteil", antwort)
        self.assertEqual(2, len(quellen))

    def test_bearbeitungsdauer_verspricht_keine_feste_frist(self):
        antwort, quellen = rag_assistent.beantworte(
            "Wie lange dauert es normalerweise, bis ein Steuerbescheid ergeht?"
        )
        self.assertIn("keine allgemein feste", antwort)
        self.assertTrue(quellen)

    def test_sperrvermerk_vermeidet_kirchensteuer_nicht(self):
        antwort, quellen = rag_assistent.beantworte(
            "Kann ich mit einem Sperrvermerk die Kirchensteuer vollständig vermeiden?"
        )
        self.assertIn("nicht", antwort)
        self.assertIn("kein Weg", antwort)
        self.assertTrue(quellen)


if __name__ == "__main__":
    unittest.main()
