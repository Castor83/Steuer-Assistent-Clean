import sys
import unittest
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

import training_kandidaten_filtern as filtermodul


class TrainingKandidatenFilterTest(unittest.TestCase):
    def test_alltagsnahe_steuerfrage_wird_angenommen(self):
        roh = {
            "conversations": [
                {"role": "user", "content": "Kann ich die Kosten meines Homeoffice als Werbungskosten in der Einkommensteuererklärung absetzen?"},
                {"role": "assistant", "content": "Die Voraussetzungen richten sich nach § 4 Abs. 5 EStG. Für Arbeitnehmer kommen je nach Nutzung Werbungskosten in Betracht; der konkrete Rechtsstand muss geprüft werden."},
            ]
        }
        eintrag, grund = filtermodul.kandidat("waterfall", 1, roh)
        self.assertEqual("akzeptiert", grund)
        self.assertEqual("Arbeitnehmer und Werbungskosten", eintrag["thema"])
        self.assertTrue(eintrag["rechtsstand_pruefen"])
        self.assertTrue(eintrag["nicht_fuer_qdrant"])

    def test_allgemeine_rechtsfrage_wird_abgelehnt(self):
        roh = {
            "conversations": [
                {"role": "user", "content": "Welches Gericht ist für einen gewöhnlichen Kaufvertrag zuständig?"},
                {"role": "assistant", "content": "Für einen Kaufvertrag richtet sich die Zuständigkeit nach dem Zivilprozessrecht und dem Wohnort der Parteien."},
            ]
        }
        eintrag, grund = filtermodul.kandidat("waterfall", 2, roh)
        self.assertIsNone(eintrag)
        self.assertEqual("keine_steuerfrage", grund)

    def test_ki_ausweichantwort_wird_abgelehnt(self):
        roh = {
            "conversations": [
                {"role": "user", "content": "Wie lege ich Einspruch gegen meinen Einkommensteuerbescheid ein?"},
                {"role": "assistant", "content": "Als KI-Sprachmodell kann ich keine Steuerberatung leisten und kann diese Steuerfrage deshalb nicht beantworten."},
            ]
        }
        eintrag, grund = filtermodul.kandidat("waterfall", 3, roh)
        self.assertIsNone(eintrag)
        self.assertEqual("nicht_verwendbare_antwort", grund)

    def test_mehrteiliger_dialog_bleibt_erhalten(self):
        roh = {
            "id": "abc",
            "conversation": [
                {"role": "user", "content": "Warum erkennt das Finanzamt meine Werbungskosten nicht an?"},
                {"role": "assistant", "content": "Werbungskosten werden nach § 9 EStG geprüft. Entscheidend sind beruflicher Anlass und Nachweise."},
                {"role": "user", "content": "Kann ich dagegen mit einem Einspruch vorgehen?"},
                {"role": "assistant", "content": "Gegen einen Steuerbescheid ist nach § 355 AO grundsätzlich innerhalb eines Monats Einspruch möglich."},
            ],
        }
        eintrag, grund = filtermodul.kandidat("openlegal", 4, roh)
        self.assertEqual("akzeptiert", grund)
        self.assertEqual(4, len(eintrag["messages"]))

    def test_strenge_menge_schliesst_jahreszahlen_und_betraege_aus(self):
        basis = {
            "quelle": "waterfall",
            "merkmale": {"erkannte_jahre": [], "paragraphen": ["§ 9"]},
            "messages": [
                {"role": "user", "content": "Was sind Werbungskosten?"},
                {"role": "assistant", "content": "Werbungskosten richten sich nach § 9 EStG und setzen einen beruflichen Zusammenhang voraus."},
            ],
        }
        self.assertTrue(filtermodul.ist_strenger_sprachkandidat(basis))
        mit_betrag = {**basis, "messages": [*basis["messages"][:-1], {"role": "assistant", "content": "Es gelten 1.000 Euro nach § 9 EStG."}]}
        self.assertFalse(filtermodul.ist_strenger_sprachkandidat(mit_betrag))
        mit_jahr = {**basis, "merkmale": {"erkannte_jahre": [2025], "paragraphen": ["§ 9"]}}
        self.assertFalse(filtermodul.ist_strenger_sprachkandidat(mit_jahr))

    def test_strenge_menge_schliesst_openlegal_ohne_fundstelle_aus(self):
        eintrag = {
            "quelle": "openlegal",
            "merkmale": {"erkannte_jahre": [], "paragraphen": ["§ 9"]},
            "messages": [
                {"role": "user", "content": "Wie entschied das Gericht zu meinen Werbungskosten?"},
                {"role": "assistant", "content": "Das Gericht wandte § 9 EStG auf die Werbungskosten an."},
            ],
        }
        self.assertFalse(filtermodul.ist_strenger_sprachkandidat(eintrag))

    def test_strenge_menge_schliesst_riskante_versprechen_aus(self):
        eintrag = {
            "quelle": "waterfall",
            "merkmale": {"erkannte_jahre": [], "paragraphen": ["§ 23"]},
            "messages": [
                {"role": "user", "content": "Wie plane ich eine Grundstücksübertragung?"},
                {"role": "assistant", "content": "Mit § 23 EStG lässt sich sicherstellen, dass keine Steuer entsteht."},
            ],
        }
        self.assertFalse(filtermodul.ist_strenger_sprachkandidat(eintrag))

    def test_strenge_menge_schliesst_ungeprueftes_gesetzeszitat_aus(self):
        eintrag = {
            "quelle": "waterfall",
            "merkmale": {"erkannte_jahre": [], "paragraphen": ["§ 26"]},
            "messages": [
                {"role": "user", "content": "Wann ist eine Zusammenveranlagung möglich?"},
                {"role": "assistant", "content": "Zitat aus dem § 26 EStG: Ehegatten werden immer gemeinsam besteuert."},
            ],
        }
        self.assertFalse(filtermodul.ist_strenger_sprachkandidat(eintrag))

    def test_strenge_menge_beachtet_manuelle_fachsperre(self):
        eintrag = {
            "id": "waterfall-96688",
            "quelle": "waterfall",
            "merkmale": {"erkannte_jahre": [], "paragraphen": ["§ 50c"]},
            "messages": [
                {"role": "user", "content": "Wie lange gilt die Bescheinigung?"},
                {"role": "assistant", "content": "Die Geltung richtet sich nach § 50c EStG."},
            ],
        }
        self.assertFalse(filtermodul.ist_strenger_sprachkandidat(eintrag))

    def test_charge_02_sperrt_nicht_freigegebene_faelle(self):
        basis = {
            "quelle": "waterfall",
            "merkmale": {"erkannte_jahre": [], "paragraphen": ["§ 10"]},
            "messages": [
                {"role": "user", "content": "Welche Vorschrift gilt?"},
                {"role": "assistant", "content": "Die Einordnung richtet sich nach § 10 EStG."},
            ],
        }
        gesperrt = {
            "waterfall-228040",
            "waterfall-143940",
            "waterfall-228042",
            "waterfall-475024",
            "waterfall-441861",
            "waterfall-437580",
            "waterfall-136569",
            "waterfall-18046",
            "waterfall-127698",
        }
        for kandidat_id in gesperrt:
            with self.subTest(kandidat_id=kandidat_id):
                self.assertFalse(
                    filtermodul.ist_strenger_sprachkandidat({**basis, "id": kandidat_id})
                )

    def test_charge_02_vorsorgefall_bleibt_wegen_ausnahmen_gesperrt(self):
        eintrag = {
            "id": "waterfall-441861",
            "quelle": "waterfall",
            "merkmale": {"erkannte_jahre": [], "paragraphen": ["§ 10"]},
            "messages": [
                {"role": "user", "content": "Wie werden Vorsorgebeiträge eingeordnet?"},
                {"role": "assistant", "content": "Vorsorgeaufwendungen gehören nach § 10 EStG zu den Sonderausgaben."},
            ],
        }
        self.assertFalse(filtermodul.ist_strenger_sprachkandidat(eintrag))


if __name__ == "__main__":
    unittest.main()
