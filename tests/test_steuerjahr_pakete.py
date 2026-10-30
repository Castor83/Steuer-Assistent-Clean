import json
from pathlib import Path
import sys
import unittest


PROJEKT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJEKT / "app"))

import rag_assistent
from steuerjahr_pakete import (
    JAHRESDATEN,
    bestimme_steuerjahr,
    normalisiere_kurzes_steuerjahr,
    quelle_passt_zum_steuerjahr,
)
from wissen_import_quellen import lade_quellen


class SteuerjahrPaketeTest(unittest.TestCase):
    def test_alle_drei_jahre_haben_vier_profilquellen(self):
        for jahr in (2023, 2024, 2025):
            dateien = list((PROJEKT / "wissen" / "quellen").glob(f"steuerjahr_{jahr}_*.json"))
            self.assertEqual(4, len(dateien), jahr)
            kategorien = set()
            for datei in dateien:
                daten = json.loads(datei.read_text(encoding="utf-8"))
                self.assertEqual(jahr, daten["steuerjahr"])
                self.assertEqual([jahr], daten["gueltig_fuer"])
                self.assertTrue(daten["jahr_abhaengig"])
                kategorien.add(daten["kategorie"].rsplit(" ", 1)[-1])
            self.assertTrue(dateien)

    def test_importer_akzeptiert_alle_jahresquellen(self):
        namen = {datei.name for datei, _ in lade_quellen()}
        for jahr in (2023, 2024, 2025):
            self.assertIn(f"steuerjahr_{jahr}_arbeitnehmer.json", namen)
            self.assertIn(f"steuerjahr_{jahr}_vermietung_eigenheim.json", namen)
            self.assertIn(f"steuerjahr_{jahr}_fristen.json", namen)
            self.assertIn(f"steuerjahr_{jahr}_grundsteuer_bayern.json", namen)

    def test_fragejahr_hat_vorrang_vor_ui_und_profil(self):
        profil = {"steuererklaerung": {"naechstes_zu_bearbeitendes_steuerjahr": "2023"}}
        self.assertEqual(2024, bestimme_steuerjahr("Was gilt 2024?", "2025", profil))
        self.assertEqual(2025, bestimme_steuerjahr("Was gilt?", "2025", profil))
        self.assertIsNone(bestimme_steuerjahr("Was gilt?", None, profil))
        self.assertEqual(2026, bestimme_steuerjahr("Was gilt 2026?", "2023", profil))

    def test_umgangssprachliche_zweistellige_steuerjahre(self):
        self.assertEqual(2024, bestimme_steuerjahr("Die Steuererklärung für 24", None, None))
        self.assertEqual(2025, bestimme_steuerjahr("Grundsteuerbescheid 25 aus Fürth", None, None))
        self.assertEqual(2023, bestimme_steuerjahr("In 23 war ich 140 Tage bei der Arbeit für die Steuer", None, None))
        self.assertEqual(2024, bestimme_steuerjahr("Hab in 24 150 Euro gespendet", None, None))
        self.assertEqual(2025, bestimme_steuerjahr("Arbeitgeber schrieb mir für 25 Arbeitskleidung vor", None, None))

    def test_zweistellige_zahl_ohne_jahreskontext_bleibt_unangetastet(self):
        self.assertIsNone(bestimme_steuerjahr("Kann ich 24 Tage Homeoffice angeben?", None, None))
        self.assertIsNone(bestimme_steuerjahr("Die Rechnung beträgt 24 Euro", None, None))

    def test_sicheres_kurzjahr_wird_im_text_ersetzt(self):
        self.assertEqual(
            "Ich habe in 2024 150 Euro gespendet",
            normalisiere_kurzes_steuerjahr("Ich habe in 24 150 Euro gespendet"),
        )
        self.assertEqual(
            "Arbeitgeber schrieb für 2025 Arbeitskleidung vor",
            normalisiere_kurzes_steuerjahr("Arbeitgeber schrieb für 25 Arbeitskleidung vor"),
        )

    def test_2026_altquelle_wird_fuer_2023_bis_2025_gesperrt(self):
        altquelle = {"steuerjahr": 2026, "kategorie": "Arbeitgeberleistungen 2026"}
        for jahr in (2023, 2024, 2025):
            self.assertFalse(quelle_passt_zum_steuerjahr(altquelle, jahr))
        self.assertTrue(quelle_passt_zum_steuerjahr(altquelle, None))
        self.assertTrue(quelle_passt_zum_steuerjahr(altquelle, 2026))

    def test_jahresquelle_gilt_nur_fuer_ihr_jahr(self):
        quelle = {"jahr_abhaengig": True, "gueltig_fuer": [2024], "steuerjahr": 2024}
        self.assertFalse(quelle_passt_zum_steuerjahr(quelle, 2023))
        self.assertTrue(quelle_passt_zum_steuerjahr(quelle, 2024))
        self.assertFalse(quelle_passt_zum_steuerjahr(quelle, 2025))

    def test_grundfreibetraege_werden_jahrgenau_beantwortet(self):
        erwartet = {2023: "10.908", 2024: "11.784", 2025: "12.096"}
        for jahr, betrag in erwartet.items():
            antwort, quellen = rag_assistent.beantworte(
                "Wie hoch ist der Grundfreibetrag?",
                steuerjahr=jahr,
                steuerprofil={},
            )
            self.assertIn(str(jahr), antwort)
            self.assertIn(betrag, antwort)
            self.assertTrue(
                quelle_passt_zum_steuerjahr(quellen[0].payload, jahr)
            )

    def test_homeoffice_und_entfernung_sind_fuer_alle_jahre_geprueft(self):
        for jahr in JAHRESDATEN:
            homeoffice, _ = rag_assistent.beantworte(
                "Wie hoch ist die Homeoffice-Pauschale pro Tag und maximal?",
                steuerjahr=jahr,
                steuerprofil={},
            )
            entfernung, _ = rag_assistent.beantworte(
                "Wie hoch ist die Entfernungspauschale je Kilometer?",
                steuerjahr=jahr,
                steuerprofil={},
            )
            self.assertIn("6 Euro", homeoffice)
            self.assertIn("1.260 Euro", homeoffice)
            self.assertIn("0,30 Euro", entfernung)
            self.assertIn("0,38 Euro", entfernung)

    def test_alltagsfrage_zum_e_bike_fragt_nach_nutzungsart(self):
        for jahr in (2023, 2024, 2025):
            antwort, quellen = rag_assistent.beantworte(
                "Kann ich ein E-Bike steuerlich absetzten?",
                steuerjahr=jahr,
                steuerprofil={"person": {"hausbesitzer": True}},
            )
            self.assertIn("privaten Kauf", antwort)
            self.assertIn("Arbeitsweg", antwort)
            self.assertIn("Dienstfahrrad", antwort)
            self.assertNotIn("Dreifamilienhaus", antwort)
            self.assertNotIn("Fahrradweg", antwort)
            self.assertFalse(quellen)

    def test_pflichtfrage_wird_nicht_durch_fristeintrag_im_verlauf_umgelenkt(self):
        profil = {
            "person": {"angestellter": True},
            "grundabgaben_standardobjekt": {
                "nutzung": "teilweise selbst genutzt und teilweise vermietet"
            },
        }
        antwort, quellen = rag_assistent.beantworte(
            "Vorheriger Gesprächskontext:\n"
            "Letzte Nutzerangabe: Was bringt mir die Steuererklärung überhaupt?\n"
            "Letzte Assistentenantwort: Für Beträge und Fristen gibt es keine Garantie.\n"
            "Aktuelle Ergänzung: Muss ich eine Steuererklärung machen?",
            steuerjahr=2023,
            steuerprofil=profil,
        )
        self.assertIn("Abgabepflicht", antwort)
        self.assertIn("Vermietung", antwort)
        self.assertIn("410 Euro", antwort)
        self.assertNotIn("2. September 2024", antwort)
        self.assertIn("§ 46", quellen[0].payload["paragraph"])

    def test_nutzen_der_steuererklaerung_verspricht_keine_erstattung(self):
        antwort, _ = rag_assistent.beantworte(
            "Was bringt mir die Steuererklärung überhaupt?",
            steuerjahr=2023,
            steuerprofil={"person": {"angestellter": True}},
        )
        self.assertIn("Erstattung", antwort)
        self.assertIn("Nachzahlung", antwort)
        self.assertIn("nicht garantiert", antwort)

    def test_vermietungs_werbungskosten_enthalten_keinen_erfundenen_mietausfall(self):
        profil = {
            "person": {"angestellter": True, "hausbesitzer": True},
            "grundabgaben_standardobjekt": {
                "gebaeudeart": "Dreifamilienhaus",
                "nutzung": "teilweise selbst genutzt und teilweise vermietet",
            },
        }
        antwort, quellen = rag_assistent.beantworte(
            "Vorheriger Gesprächskontext:\n"
            "Letzte Nutzerangabe: Muss ich eine Steuererklärung machen?\n"
            "Letzte Assistentenantwort: Dafür sind die Vermietungseinkünfte wichtig.\n"
            "Aktuelle Ergänzung: Was kann ich absetzen? (Werbungskosten)",
            steuerjahr=2023,
            steuerprofil=profil,
        )
        self.assertIn("Darlehenszinsen", antwort)
        self.assertIn("nicht die Tilgung", antwort)
        self.assertIn("Grundsteuer", antwort)
        self.assertIn("Mietausfall ist selbst keine Ausgabe", antwort)
        self.assertIn("nicht automatisch", antwort)
        self.assertIn("selbst genutzte Anteil", antwort)
        self.assertNotIn("Minderertrag", antwort)
        self.assertEqual(2023, quellen[0].payload["steuerjahr"])

    def test_komplettsanierung_im_leerstand_wird_nicht_pauschal_sofort_abgezogen(self):
        profil = {
            "person": {"angestellter": True, "hausbesitzer": True},
            "grundabgaben_standardobjekt": {
                "gebaeudeart": "Dreifamilienhaus",
                "nutzung": "teilweise selbst genutzt und teilweise vermietet",
            },
        }
        for jahr in (2023, 2024, 2025):
            antwort, quellen = rag_assistent.beantworte(
                "Was passiert, wenn ich im Leerstand eine Wohnung komplett saniere?",
                steuerjahr=jahr,
                steuerprofil=profil,
            )
            self.assertIn("nachweisbar wieder vermieten", antwort)
            self.assertIn("Leerstand allein genügt", antwort)
            self.assertIn("weniger als drei Jahren", antwort)
            self.assertIn("15 Prozent", antwort)
            self.assertIn("zwei bis fünf Jahre", antwort)
            self.assertIn("AfA", antwort)
            self.assertIn("Wann hast du das Haus gekauft", antwort)
            self.assertEqual(jahr, quellen[0].payload["steuerjahr"])
            self.assertEqual("§ 82b EStDV", quellen[1].payload["paragraph"])

    def test_entfernungspauschale_wird_im_dialog_mit_tagen_berechnet(self):
        antwort, quellen = rag_assistent.beantworte(
            "Vorheriger Gesprächskontext:\n"
            "Letzte Nutzerangabe: 15 Kilometer einfach zur Arbeit.\n"
            "Letzte Assistentenantwort: Das ist die Entfernungspauschale. Wie viele Tage?\n"
            "Aktuelle Ergänzung: Das waren 120 Tage.",
            steuerjahr=2023,
            steuerprofil={},
        )
        self.assertIn("540 Euro", antwort)
        self.assertIn("120 Arbeitstage", antwort)
        self.assertIn("15 Kilometer", antwort)
        self.assertEqual(2023, quellen[0].payload["steuerjahr"])

    def test_fristeinordnung_ist_jahrgenau(self):
        erwartet = {
            2023: ("2. September 2024", "2. Juni 2025"),
            2024: ("31. Juli 2025", "30. April 2026"),
            2025: ("31. Juli 2026", "1. März 2027"),
        }
        for jahr, termine in erwartet.items():
            antwort, quellen = rag_assistent.beantworte(
                "Bis wann musste ich die Steuererklärung abgeben?",
                steuerjahr=jahr,
                steuerprofil={},
            )
            self.assertTrue(all(termin in antwort for termin in termine))
            self.assertEqual(jahr, quellen[0].payload["steuerjahr"])

    def test_elster_suche_verwendet_den_passenden_leitfaden(self):
        for jahr in (2023, 2024, 2025):
            treffer = rag_assistent.suche_elster_leitfaden(
                "Wo trage ich Werbungskosten in Anlage N ein?",
                steuerjahr=jahr,
                limit=1,
            )
            self.assertEqual(1, len(treffer))
            self.assertEqual(jahr, treffer[0].payload["steuerjahr"])
            self.assertIn(str(jahr), treffer[0].payload["quelle_id"])


if __name__ == "__main__":
    unittest.main()
