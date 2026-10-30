import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

import rag_assistent


class BfhIntegrationTest(unittest.TestCase):
    def test_testschalter_ist_standardmaessig_aus(self):
        with patch.object(
            rag_assistent,
            "bfh_datenbank_client",
            side_effect=AssertionError("BFH-Datenbank darf nicht geöffnet werden"),
        ):
            self.assertEqual([], rag_assistent.suche_bfh_rechtsprechung("Kindergeld", aktiviert=False))

    def test_bfh_thema_wird_bestimmt(self):
        self.assertEqual(
            "Erbschaft und Schenkung",
            rag_assistent.bestimme_bfh_thema("Wie wird ein Grundstück bei einer Erbschaft bewertet?"),
        )
        self.assertEqual(
            "Umsatzsteuer",
            rag_assistent.bestimme_bfh_thema("Ist bei der Photovoltaikanlage ein Vorsteuerabzug möglich?"),
        )

    def test_unpassender_werbungskostenfall_wird_beim_arbeitszimmer_abgelehnt(self):
        payload = {
            "titel": "Rechtsverfolgungskosten als Werbungskosten",
            "leitsatz": "Aufwendungen können nach § 9 EStG abziehbar sein.",
            "normen": "EStG § 9",
        }
        self.assertFalse(
            rag_assistent.bfh_treffer_passt(
                "Kann ich mein häusliches Arbeitszimmer als Werbungskosten abziehen?",
                payload,
            )
        )

    def test_passender_kindergeld_ausbildungsfall_wird_angenommen(self):
        payload = {
            "titel": "Kindergeld bei erstmaliger Berufsausbildung",
            "leitsatz": "Mehrere Ausbildungsabschnitte können zusammengehören.",
            "normen": "EStG § 32",
        }
        self.assertTrue(
            rag_assistent.bfh_treffer_passt(
                "Wann gibt es Kindergeld für ein volljähriges Kind in Ausbildung?",
                payload,
            )
        )

    def test_standardantwort_ruft_bfh_suche_nicht_auf(self):
        quelle = SimpleNamespace(payload={"kategorie": "Minijob"}, score=1.0)
        with (
            patch.object(rag_assistent, "quelle_aus_kategorie", return_value=quelle),
            patch.object(
                rag_assistent,
                "suche_bfh_rechtsprechung",
                side_effect=AssertionError("Schnelle Standardantwort braucht kein BFH"),
            ),
        ):
            antwort, _ = rag_assistent.beantworte(
                "Wo trage ich einen pauschal versteuerten Minijob ein?",
                bfh_testmodus=True,
            )
        self.assertIn("nicht", antwort)

    def test_konkreter_mieterstromfall_kommt_vor_allgemeiner_vorsteuerantwort(self):
        gesetz = SimpleNamespace(
            payload={
                "quelle": "UStG", "kategorie": "Umsatzsteuer", "text": "§ 15 UStG Vorsteuerabzug",
                "url": "https://www.gesetze-im-internet.de/ustg_1980/__15.html",
            },
            score=1.0,
        )
        urteil = SimpleNamespace(
            payload={
                "quelle": "BFH, XI R 8/21",
                "aktenzeichen": "XI R 8/21",
                "datum": "2024-07-17",
                "titel": "Vorsteuerabzug bei Lieferung von Mieterstrom",
                "leitsatz": "Die getrennte Stromlieferung kann eine selbständige Leistung sein.",
                "url": "https://www.bundesfinanzhof.de/de/entscheidung/entscheidungen-online/",
            },
            score=0.7,
        )
        with (
            patch.object(rag_assistent, "suche_bfh_rechtsprechung", return_value=[urteil]),
            patch.object(rag_assistent, "suche_wissen", return_value=[gesetz]),
            patch.object(rag_assistent, "ergaenze_spezialquelle", return_value=[gesetz]),
        ):
            antwort, quellen = rag_assistent.beantworte(
                "Besteht Vorsteuerabzug, wenn Strom getrennt von der Wohnraumvermietung an Mieter geliefert wird?",
                bfh_testmodus=True,
            )
        self.assertIn("XI R 8/21", antwort)
        self.assertIn("historischer Einzelfall", antwort)
        self.assertEqual([gesetz, urteil], quellen)

    def test_langer_fall_haengt_bfh_deterministisch_nach_modellantwort_an(self):
        gesetz = SimpleNamespace(
            payload={
                "quelle": "Amtlicher Gesetzestext",
                "paragraph": "§ 32 EStG",
                "steuerjahr": 2026,
                "text": "Kinder in Ausbildung können unter den gesetzlichen Voraussetzungen berücksichtigt werden.",
                "kategorie": "Kinder und Kindergeld",
                "url": "https://www.gesetze-im-internet.de/estg/__32.html",
            },
            score=1.0,
        )
        urteil = SimpleNamespace(
            payload={
                "quelle": "BFH, III R 10/22, Entscheidung vom 2023-10-12",
                "paragraph": "EStG § 32",
                "steuerjahr": 2023,
                "text": "Kindergeld bei mehreren Ausbildungsabschnitten.",
                "kategorie": "BFH-Rechtsprechung – Familie und Kindergeld",
                "rechtsprechung": True,
                "aktenzeichen": "III R 10/22",
                "datum": "2023-10-12",
                "titel": "Kindergeld bei mehreren Ausbildungsabschnitten",
                "leitsatz": "Der enge zeitliche Zusammenhang muss zwischen den Ausbildungsabschnitten bestehen.",
                "url": "https://www.bundesfinanzhof.de/de/entscheidung/entscheidungen-online/",
            },
            score=0.55,
        )
        frage = (
            "Ein volljähriges Kind absolviert nach einem Freiwilligendienst einen weiteren "
            "Ausbildungsabschnitt. Zu prüfen ist der Kindergeldanspruch. "
            + "Der konkrete zeitliche und sachliche Zusammenhang soll vollständig gewürdigt werden. " * 8
        )
        with (
            patch.object(rag_assistent, "suche_wissen", return_value=[gesetz]),
            patch.object(rag_assistent, "ergaenze_spezialquelle", return_value=[gesetz]),
            patch.object(rag_assistent, "quelle_aus_kategorie", return_value=None),
            patch.object(rag_assistent, "suche_bfh_rechtsprechung", return_value=[urteil]),
            patch.object(
                rag_assistent.MODELL_RESSOURCEN,
                "chat",
                side_effect=AssertionError("BFH-Leitsatz darf nicht vom Sprachmodell ausgelegt werden"),
            ),
        ):
            antwort, quellen = rag_assistent.beantworte(frage, bfh_testmodus=True)
        self.assertIn("abschließende Einordnung", antwort)
        self.assertIn("nicht aus", antwort)
        self.assertIn("Ergänzende BFH-Rechtsprechung", antwort)
        self.assertIn("Bundesfinanzhof", antwort)
        self.assertIn("III R 10/22", antwort)
        self.assertIn("aktuellen Gesetzesstands", antwort)
        self.assertEqual([gesetz, urteil], quellen)

    def test_passender_bfh_fall_kommt_vor_sicherheitssperre_fuer_kurze_frage(self):
        gesetz = SimpleNamespace(
            payload={
                "quelle": "Gesetz", "kategorie": "Kinder", "text": "Allgemeine Regel",
                "url": "https://www.gesetze-im-internet.de/estg/__32.html",
            },
            score=1.0,
        )
        urteil = SimpleNamespace(
            payload={
                "quelle": "BFH, III R 10/22",
                "aktenzeichen": "III R 10/22",
                "datum": "2023-10-12",
                "titel": "Freiwilligendienst zwischen Ausbildungsabschnitten",
                "leitsatz": "Der Zusammenhang muss zwischen den Ausbildungsabschnitten bestehen.",
                "url": "https://www.bundesfinanzhof.de/de/entscheidung/entscheidungen-online/",
            },
            score=0.55,
        )
        with (
            patch.object(rag_assistent, "schnelle_standardantwort", return_value=None),
            patch.object(rag_assistent, "suche_wissen", return_value=[gesetz]),
            patch.object(rag_assistent, "ergaenze_spezialquelle", return_value=[gesetz]),
            patch.object(rag_assistent, "quelle_aus_kategorie", return_value=None),
            patch.object(rag_assistent, "suche_bfh_rechtsprechung", return_value=[urteil]),
            patch.object(
                rag_assistent.MODELL_RESSOURCEN,
                "chat",
                side_effect=AssertionError("Kein Modell zur Auslegung des BFH-Falls"),
            ),
        ):
            antwort, quellen = rag_assistent.beantworte(
                "Gilt ein Freiwilligendienst zwischen Ausbildungsabschnitten für Kindergeld?",
                bfh_testmodus=True,
            )
        self.assertIn("III R 10/22", antwort)
        self.assertNotIn("noch nicht", antwort)
        self.assertEqual([gesetz, urteil], quellen)


if __name__ == "__main__":
    unittest.main()
