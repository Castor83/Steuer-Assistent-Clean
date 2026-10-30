from pathlib import Path
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import rag_assistent
from gespraechsverstaendnis import interpretationsblock


class DummyQuelle:
    def __init__(self, kategorie: str):
        self.payload = {
            "kategorie": kategorie,
            "quelle": kategorie,
            "paragraph": "Prüfquelle",
            "steuerjahr": "2026",
            "url": "https://example.invalid",
            "text": "Geprüfter Inhalt",
        }


class RohrbruchGespraechTest(unittest.TestCase):
    def setUp(self):
        self.profil = {
            "person": {"hausbesitzer": True},
            "grundabgaben_standardobjekt": {
                "gebaeudeart": "Dreifamilienhaus",
                "nutzung": "teilweise selbst genutzt und teilweise vermietet",
            },
        }

    @patch.object(rag_assistent, "quelle_aus_kategorie")
    @patch.object(rag_assistent, "quelle_aus_datei")
    def test_rohrbruch_wird_fuer_gemischte_nutzung_getrennt_erklaert(self, datei, quelle):
        datei.side_effect = lambda name: DummyQuelle(name)
        quelle.side_effect = lambda kategorie: DummyQuelle(kategorie)
        antwort, quellen = rag_assistent.rohrbruch_grundfall(
            "Sind Sanierungsarbeiten zum Beheben eines Rohrbruchs steuerlich relevant?",
            [],
            self.profil,
        )
        self.assertIn("teilweise selbst genutzten", antwort)
        self.assertIn("Selbst genutzter Teil", antwort)
        self.assertIn("Vermieteter Teil", antwort)
        self.assertIn("gemeinsame Leitung", antwort)
        self.assertEqual(3, len(quellen))
        self.assertEqual("estg_35a_nebenkosten_mieter.json", quellen[0].payload["kategorie"])
        self.assertEqual("bmf_renovierung_afa_vermietung.json", quellen[1].payload["kategorie"])
        self.assertEqual("esth_21_werbungskosten_vermietung.json", quellen[2].payload["kategorie"])

    @patch.object(rag_assistent, "quelle_aus_kategorie")
    @patch.object(rag_assistent, "quelle_aus_datei")
    def test_eigentuemernachtrag_wird_als_bekannte_angabe_bestaetigt(self, datei, quelle):
        datei.side_effect = lambda name: DummyQuelle(name)
        quelle.side_effect = lambda kategorie: DummyQuelle(kategorie)
        antwort, _ = rag_assistent.rohrbruch_grundfall(
            "Vorherige Frage: Ist ein Rohrbruch steuerlich relevant?\n"
            "Aktuelle Ergänzung: Ich bin der Eigentümer",
            [],
            self.profil,
        )
        self.assertIn("Eigentümerstellung ist bereits im Profil gespeichert", antwort)
        self.assertIn("nur noch wichtig", antwort)
        self.assertNotIn("1.200 Euro", antwort)

    @patch.object(rag_assistent, "quelle_aus_kategorie")
    @patch.object(rag_assistent, "quelle_aus_datei")
    def test_gemeinsame_leitung_fuehrt_zum_naechsten_schritt(self, datei, quelle):
        datei.side_effect = lambda name: DummyQuelle(name)
        quelle.side_effect = lambda kategorie: DummyQuelle(kategorie)
        antwort, quellen = rag_assistent.rohrbruch_grundfall(
            "Vorheriger Gesprächskontext: Rohrbruch im Dreifamilienhaus.\n"
            "Aktuelle Ergänzung: Eine gemeinsame Leitung",
            [],
            self.profil,
        )
        self.assertIn("Okay", antwort)
        self.assertIn("Arbeits- und Materialkosten", antwort)
        self.assertNotIn("1.200 Euro", antwort)
        self.assertEqual(1, len(quellen))

    @patch.object(rag_assistent, "quelle_aus_kategorie")
    @patch.object(rag_assistent, "quelle_aus_datei")
    def test_getrennte_rechnung_fuehrt_zur_versicherungsfrage(self, datei, quelle):
        datei.side_effect = lambda name: DummyQuelle(name)
        quelle.side_effect = lambda kategorie: DummyQuelle(kategorie)
        antwort, quellen = rag_assistent.rohrbruch_grundfall(
            "Vorheriger Gesprächskontext: Rohrbruch an gemeinsamer Leitung.\n"
            "Letzte Assistentenantwort: Sind Arbeits- und Materialkosten getrennt ausgewiesen?\n"
            "Aktuelle Ergänzung: ja",
            [],
            self.profil,
        )
        self.assertIn("Prima", antwort)
        self.assertIn("Gebäudeversicherung", antwort)
        self.assertNotIn("Mietvertrag", antwort)
        self.assertEqual(2, len(quellen))

    @patch.object(rag_assistent, "quelle_aus_kategorie")
    @patch.object(rag_assistent, "quelle_aus_datei")
    def test_eigene_wohnung_bleibt_im_rohrbruchkontext(self, datei, quelle):
        datei.side_effect = lambda name: DummyQuelle(name)
        quelle.side_effect = lambda kategorie: DummyQuelle(kategorie)
        antwort, quellen = rag_assistent.rohrbruch_grundfall(
            "Vorheriger Gesprächskontext: Sanierungsarbeiten nach einem Rohrbruch.\n"
            "Aktuelle Ergänzung: meine Wohnung",
            [],
            self.profil,
            2023,
        )
        self.assertIn("selbst genutzte Wohnung", antwort)
        self.assertIn("nicht um Gebäude-AfA", antwort)
        self.assertIn("Gebäudeversicherung", antwort)
        self.assertEqual(1, len(quellen))

    @patch.object(rag_assistent, "quelle_aus_kategorie")
    @patch.object(rag_assistent, "quelle_aus_datei")
    def test_versicherungserstattung_wird_als_folge_beantwortet(self, datei, quelle):
        datei.side_effect = lambda name: DummyQuelle(name)
        quelle.side_effect = lambda kategorie: DummyQuelle(kategorie)
        antwort, quellen = rag_assistent.rohrbruch_grundfall(
            "Vorheriger Gesprächskontext: Rohrbruch in meiner selbst genutzten Wohnung.\n"
            "Aktuelle Ergänzung: Wenn das alles über die Gebäudeversicherung gelaufen ist auch",
            [],
            self.profil,
            2023,
        )
        self.assertIn("vollständig erstatteten Betrag", antwort)
        self.assertIn("Selbstbehalt", antwort)
        self.assertIn("tatsächlich selbst bezahlte", antwort)
        self.assertEqual(1, len(quellen))

    @patch.object(rag_assistent, "quelle_aus_kategorie")
    @patch.object(rag_assistent, "quelle_aus_datei")
    def test_kurze_angabe_einer_teilweisen_erstattung_wird_fortgefuehrt(self, datei, quelle):
        datei.side_effect = lambda name: DummyQuelle(name)
        quelle.side_effect = lambda kategorie: DummyQuelle(kategorie)
        antwort, quellen = rag_assistent.rohrbruch_grundfall(
            "Vorheriger Gesprächskontext: Rohrbruch in meiner selbst genutzten Wohnung. "
            "Die Gebäudeversicherung wurde gefragt.\n"
            "Aktuelle Ergänzung: ja aber nur die Hälfte",
            [],
            self.profil,
            2023,
        )
        self.assertIn("nur einen Teil", antwort)
        self.assertIn("tatsächlich selbst bezahlt", antwort)
        self.assertIn("Arbeits-, Fahrt- und Maschinenkosten", antwort)
        self.assertNotIn("Das kann ich", antwort)
        self.assertEqual(1, len(quellen))

    @patch.object(rag_assistent, "quelle_aus_kategorie")
    @patch.object(rag_assistent, "quelle_aus_datei")
    def test_sicherer_versicherungshinweis_verdraengt_teilantwort_nicht(self, datei, quelle):
        datei.side_effect = lambda name: DummyQuelle(name)
        quelle.side_effect = lambda kategorie: DummyQuelle(kategorie)
        antwort, _ = rag_assistent.rohrbruch_grundfall(
            "Vorheriger Gesprächskontext: Rohrbruch in meiner selbst genutzten Wohnung.\n"
            "Aktuelle Ergänzung: ja aber nur die Hälfte\n"
            "Sichere Hinweise aus dem Gespräch:\n"
            "- Die Versicherung hat nur die Hälfte der Rechnung übernommen; "
            "der übrige Teil wurde selbst getragen.",
            [],
            self.profil,
            2023,
        )
        self.assertTrue(antwort.startswith("Okay, dann hat die Gebäudeversicherung nur einen Teil"))
        self.assertNotIn("vollständig erstatteten Betrag", antwort)

    @patch.object(rag_assistent, "quelle_aus_kategorie")
    @patch.object(rag_assistent, "quelle_aus_datei")
    def test_eigenanteil_und_versicherung_in_einer_nachricht_werden_vollstaendig_verstanden(self, datei, quelle):
        datei.side_effect = lambda name: DummyQuelle(name)
        quelle.side_effect = lambda kategorie: DummyQuelle(kategorie)
        antwort, quellen = rag_assistent.rohrbruch_grundfall(
            "Die Versicherung hat den Rohrbruch bezahlt, nur 500 Euro musste ich "
            "für meine eigene Wohnung selber übernehmen. Bringt mir das bei der Steuer was?",
            [],
            self.profil,
            2023,
        )
        self.assertIn("500 Euro", antwort)
        self.assertIn("selbst bezahlter Anteil", antwort)
        self.assertIn("Arbeits-, Fahrt- und Maschinenkosten", antwort)
        self.assertNotIn("Hat die Gebäudeversicherung", antwort)
        self.assertEqual(1, len(quellen))

    def test_gesamte_antwortlogik_priorisiert_rohrbruch_vor_afa(self):
        antwort, _ = rag_assistent.beantworte(
            "Vorheriger Gesprächskontext:\n"
            "Letzte Nutzerangabe: Sanierungsarbeiten nach einem Rohrbruch\n"
            "Letzte Assistentenantwort: Bei einer Verbesserung kann Abschreibung zu prüfen sein.\n"
            "Aktuelle Ergänzung: meine Wohnung",
            steuerprofil=self.profil,
            steuerjahr="2023",
        )
        self.assertIn("selbst genutzte Wohnung", antwort)
        self.assertIn("nicht um Gebäude-AfA", antwort)

    def test_alltagssprache_fuehrt_direkt_zur_eigenen_wohnung(self):
        alltag = "Bei mir in der Bude ist ein Rohr geplatzt, kann ich das absetzen?"
        antwort, _ = rag_assistent.beantworte(
            alltag + interpretationsblock(alltag),
            steuerprofil=self.profil,
            steuerjahr="2023",
        )
        self.assertIn("selbst genutzte Wohnung", antwort)
        self.assertIn("Gebäudeversicherung", antwort)

    def test_alltagssprache_erkennt_vermietete_wohnung(self):
        alltag = "Das Rohr war bei den Mietern kaputt, bringt mir das steuerlich was?"
        antwort, _ = rag_assistent.beantworte(
            alltag + interpretationsblock(alltag),
            steuerprofil=self.profil,
            steuerjahr="2023",
        )
        self.assertIn("vermietete Wohnung", antwort)
        self.assertIn("Selbstbehalt", antwort)


if __name__ == "__main__":
    unittest.main()
