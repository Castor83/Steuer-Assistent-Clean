import sys
from pathlib import Path
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from dialog_assistent import dialogantwort, lade_steuerprofil


class DialogAssistentTest(unittest.TestCase):
    def test_alltagssprache_startet_die_steuererklaerung(self):
        antwort = dialogantwort("Ich will meine Steuer machen")
        self.assertIsNotNone(antwort)
        self.assertIn("Soll ich mit der Checkliste", antwort)

    def test_tippfehler_startet_die_steuererklaerung(self):
        antwort = dialogantwort("Ich möchte mit der Steuererklerung anfangen")
        self.assertIsNotNone(antwort)
        self.assertIn("vorläufig 2023", antwort)

    def test_grundsteuer_fachfrage_wird_nicht_als_dialogstart_behandelt(self):
        antwort = dialogantwort(
            "Ich habe Einspruch gegen den Grundsteuerwertbescheid eingelegt. Muss ich trotzdem bezahlen?",
            [],
            r"C:\\Steuer-Unterlagen",
        )
        self.assertIsNone(antwort)

    def test_start_der_einkommensteuererklaerung(self):
        antwort = dialogantwort("Ich möchte meine Einkommensteuererklärung machen.")
        self.assertIn("dokumente\\eingang", antwort)
        self.assertIn("vorläufig 2023", antwort)
        self.assertIn("Soll ich mit der Checkliste", antwort)
        self.assertIn("Angestellter", antwort)
        self.assertIn("teilweise Vermietung", antwort)
        self.assertIn("erst im passenden Abschnitt", antwort)

    def test_vorgemerktes_steuerjahr_wird_nach_bestaetigung_verwendet(self):
        start = dialogantwort("Ich möchte meine Einkommensteuererklärung machen.")
        antwort = dialogantwort("ja", [{"rolle": "assistent", "text": start}])
        self.assertIn("Alles klar: 2023", antwort)
        self.assertIn("Arbeitnehmer", antwort)
        self.assertIn("Vermietung", antwort)

    def test_folgeantwort_nutzt_dialogkontext(self):
        start = dialogantwort("Ich möchte meine Steuererklärung vorbereiten.")
        antwort = dialogantwort(
            "2025, Arbeitnehmer mit zwei Kindern",
            [{"rolle": "assistent", "text": start}],
        )
        self.assertIn("2025", antwort)
        self.assertIn("Arbeitnehmer", antwort)
        self.assertIn("Kinder", antwort)
        self.assertIn("Vermietung", antwort)
        self.assertIn("Grundsteuer und Grundabgaben", antwort)
        self.assertIn("Unterlagen sind im Ordner", antwort)

    def test_normale_fachfrage_bleibt_unberuehrt(self):
        self.assertIsNone(dialogantwort("Wie hoch ist der Arbeitnehmer-Pauschbetrag?"))

    def test_geltend_machen_wird_nicht_als_dialogstart_behandelt(self):
        self.assertIsNone(
            dialogantwort(
                "Kann ich den Sparer-Pauschbetrag über die Steuererklärung geltend machen?"
            )
        )

    def test_geschaeftsmaessige_hilfe_bleibt_fachfrage(self):
        self.assertIsNone(
            dialogantwort(
                "Darf ein Freund meine Steuererklärung geschäftsmäßig erstellen und einreichen?"
            )
        )

    def test_start_der_grundsteuerpruefung(self):
        antwort = dialogantwort("Ich möchte meine Grundsteuer prüfen.")
        self.assertIn("Kernthema", antwort)
        self.assertIn("Grundsteuermessbescheid", antwort)
        self.assertIn("Grundbesitzabgabenbescheid", antwort)
        self.assertIn("dokumente\\eingang", antwort)
        self.assertIn("Erlangen", antwort)
        self.assertIn("Bayern", antwort)
        self.assertIn("Beispielstraße 1", antwort)
        self.assertIn("00000", antwort)
        self.assertIn("Standardobjekt", antwort)

    def test_bestaetigter_wohnsitz_wird_geladen(self):
        profil = lade_steuerprofil()
        self.assertEqual("Erlangen", profil["wohnsitz"]["stadt"])
        self.assertEqual("Bayern", profil["wohnsitz"]["bundesland"])
        self.assertEqual("Deutschland", profil["wohnsitz"]["land"])
        self.assertEqual("Beispielstraße", profil["wohnsitz"]["strasse"])
        self.assertEqual("1", profil["wohnsitz"]["hausnummer"])
        self.assertEqual("00000", profil["wohnsitz"]["postleitzahl"])
        self.assertTrue(profil["grundabgaben_standardobjekt"]["ist_wohnsitz"])
        self.assertEqual(
            "Dreifamilienhaus",
            profil["grundabgaben_standardobjekt"]["gebaeudeart"],
        )
        self.assertTrue(profil["person"]["hausbesitzer"])
        self.assertTrue(profil["person"]["wohnt_im_standardobjekt"])
        self.assertEqual(
            "teilweise selbst genutzt und teilweise vermietet",
            profil["grundabgaben_standardobjekt"]["nutzung"],
        )
        self.assertEqual(
            "noch nicht angegeben",
            profil["grundabgaben_standardobjekt"]["anzahl_selbstgenutzte_wohneinheiten"],
        )
        self.assertEqual(
            "noch nicht angegeben",
            profil["grundabgaben_standardobjekt"]["anzahl_vermietete_wohneinheiten"],
        )

    def test_grundsteuerdialog_ohne_wohnsitz_bleibt_allgemein(self):
        antwort = dialogantwort(
            "Ich möchte meine Grundsteuer prüfen.",
            steuerprofil={},
        )
        self.assertIn("In welchem Bundesland", antwort)

    def test_start_der_grundabgabenpruefung(self):
        antwort = dialogantwort("Ich brauche Hilfe bei den Grundabgaben.")
        self.assertIn("Grundsteuer und kommunale Grundabgaben", antwort)
        self.assertIn("Gemeinde", antwort)

    def test_grundsteuer_folgeantwort_nutzt_bundesland_und_vorhaben(self):
        start = dialogantwort("Ich brauche Hilfe mit der Grundsteuer.")
        antwort = dialogantwort(
            "Das Grundstück liegt in Bayern. Ich möchte den Bescheid prüfen.",
            [{"rolle": "assistent", "text": start}],
        )
        self.assertIn("Bayern", antwort)
        self.assertIn("Bescheidprüfung", antwort)
        self.assertIn("Grundsteuer-Unterlagen sind im Ordner", antwort)

    def test_grundsteuer_unterlagen_im_ordner(self):
        antwort = dialogantwort("Grundsteuer-Unterlagen sind im Ordner")
        self.assertIn("Grundsteuerwertbescheid", antwort)
        self.assertIn("Grundsteuermessbescheid", antwort)
        self.assertIn("Grundsteuerbescheid der Gemeinde", antwort)

    def test_frage_nach_grundsteuer_dokumenten_bekommt_sofort_checkliste(self):
        antwort = dialogantwort("Welche Dokumente brauche ich für die Grundsteuer?")
        self.assertIn("Grundsteuermess", antwort)
        self.assertIn("Aktenzeichen", antwort)
        self.assertIn("Flurstück", antwort)
        self.assertIn("Eigentumsanteilen", antwort)
        self.assertIn("Wohn- und Nutzflächen", antwort)
        self.assertIn("In welchem Bundesland", antwort)
        self.assertNotIn("nicht sicher beantworten", antwort)

    def test_frage_nach_lohnsteuer_dokumenten_bekommt_sofort_checkliste(self):
        antwort = dialogantwort("Welche Dokumente brauche ich für die Lohnsteuer?")
        self.assertIn("Lohnsteuerbescheinigung", antwort)
        self.assertIn("Lohnersatzleistungen", antwort)
        self.assertIn("beruflichen Ausgaben", antwort)
        self.assertIn("haushaltsnahe Dienstleistungen", antwort)
        self.assertIn("Für welches Steuerjahr", antwort)
        self.assertNotIn("nicht sicher beantworten", antwort)

    def test_dialog_nennt_geaenderten_eingangsordner(self):
        antwort = dialogantwort(
            "Ich möchte meine Einkommensteuererklärung machen.",
            eingangsordner=r"D:\Steuerunterlagen",
        )
        self.assertIn(r"D:\Steuerunterlagen", antwort)


if __name__ == "__main__":
    unittest.main()
