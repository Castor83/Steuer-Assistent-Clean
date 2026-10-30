from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import rag_assistent


QUELLE = SimpleNamespace(payload={"text": "Die Entfernungspauschale beträgt 0,38 Euro."})
HEIZKOSTEN_QUELLE = SimpleNamespace(
    payload={"kategorie": "Haushaltsnahe Dienstleistungen und Nebenkosten"}
)
PFLICHT_QUELLE = SimpleNamespace(payload={"kategorie": "Steuererklärungspflicht"})
FRIST_QUELLE = SimpleNamespace(payload={"kategorie": "Steuererklärungsfrist"})
FREIWILLIG_QUELLE = SimpleNamespace(payload={"kategorie": "Freiwillige Steuererklärung"})
WERBUNGSKOSTEN_QUELLE = SimpleNamespace(
    payload={"text": "Werbungskosten sind Aufwendungen zur Erwerbung, Sicherung und Erhaltung der Einnahmen."}
)
HANDWERKER_QUELLE = SimpleNamespace(
    payload={"kategorie": "Haushaltsnahe Dienstleistungen und Nebenkosten"}
)
SPENDEN_QUELLE = SimpleNamespace(payload={"kategorie": "Spenden"})
BELEGE_QUELLE = SimpleNamespace(payload={"kategorie": "Belege und Unterlagen"})
STEUER_ID_QUELLE = SimpleNamespace(payload={"kategorie": "Steuer-Identifikationsnummer"})
AUFBEWAHRUNG_QUELLE = SimpleNamespace(payload={"kategorie": "Belegaufbewahrung"})
EHE_QUELLE = SimpleNamespace(payload={"kategorie": "Steuerklassen und Ehe"})
KINDER_QUELLE = SimpleNamespace(payload={"kategorie": "Kinder und Kindergeld"})
KRANKHEIT_QUELLE = SimpleNamespace(payload={"paragraph": "§ 33 EStG"})
PFLEGE_QUELLE = SimpleNamespace(payload={"paragraph": "§ 33b Abs. 6 EStG"})
RENOVIERUNG_QUELLE = SimpleNamespace(
    payload={"kategorie": "Renovierung und Abschreibung bei Vermietung"}
)
AFA_QUELLE = SimpleNamespace(payload={"paragraph": "§ 7 Abs. 1 und 4 EStG"})


class EntfernungspauschaleGrundfallTest(unittest.TestCase):
    def test_kilometerfrage_erklaert_ansetzen_statt_zahlen(self):
        antwort, quellen = rag_assistent.entfernungspauschale_grundfall(
            "Ab wie vielen Kilometern bekomme ich Pendlerpauschale?", [QUELLE]
        )
        self.assertIn("jeden vollen Kilometer", antwort)
        self.assertIn("0,38 Euro", antwort)
        self.assertIn("bis 2025", antwort)
        self.assertIn("Du zahlst nichts", antwort)
        self.assertIn("keine direkte Auszahlung", antwort)
        self.assertEqual(quellen, [QUELLE])

    def test_e_bike_berechnung_2026(self):
        antwort, quellen = rag_assistent.neuer_testkatalog_grundfall(
            "Ich fahre 2026 an 150 Tagen mit meinem privaten E-Bike (Zulassung bis 25 km/h) "
            "zu meiner 32 km entfernten Arbeitsstätte. Wie hoch ist meine Entfernungspauschale?",
            [],
        )
        self.assertIn("1.824 Euro", antwort)
        self.assertIn("0,38 Euro", antwort)
        self.assertIn("594 Euro", antwort)
        self.assertTrue(quellen)

    def test_wegeunfall_ist_zusaetzlich_abziehbar(self):
        antwort, quellen = rag_assistent.neuer_testkatalog_grundfall(
            "Ich hatte auf dem Weg zur Arbeit einen Autounfall. Kann ich die Reparaturkosten "
            "trotz der Entfernungspauschale zusätzlich absetzen?",
            [],
        )
        self.assertTrue(antwort.startswith("Ja."))
        self.assertIn("zusätzlich", antwort)
        self.assertTrue(quellen)

    def test_dauerhafte_versetzung_ist_keine_dienstreise(self):
        antwort, quellen = rag_assistent.neuer_testkatalog_grundfall(
            "Mein Arbeitgeber hat mich dauerhaft an einen anderen Standort versetzt. Kann ich "
            "die Fahrten dorthin unbegrenzt als Dienstreise abrechnen?",
            [],
        )
        self.assertTrue(antwort.startswith("Nein."))
        self.assertIn("ersten Tätigkeitsstätte", antwort)
        self.assertTrue(quellen)

    def test_mitfahrer_erhaelt_entfernungspauschale(self):
        antwort, quellen = rag_assistent.neuer_testkatalog_grundfall(
            "Ich bin Mitfahrer einer Fahrgemeinschaft. Darf ich die Entfernungspauschale eintragen?",
            [],
        )
        self.assertTrue(antwort.startswith("Ja."))
        self.assertIn("4.500 Euro", antwort)
        self.assertTrue(quellen)

    def test_heizkosten_trennt_energie_und_arbeitskosten(self):
        antwort, quellen = rag_assistent.heizkosten_grundfall(
            "Kann ich Heizkosten steuerlich absetzen?", [HEIZKOSTEN_QUELLE]
        )
        self.assertIn("Reine Heizkosten", antwort)
        self.assertIn("Arbeitskosten", antwort)
        self.assertIn("Als Mieter", antwort)
        self.assertIn("Als Eigentümer", antwort)
        self.assertEqual(quellen, [HEIZKOSTEN_QUELLE])

    def test_steuererklaerungspflicht_beginnt_mit_meistens_nein(self):
        antwort, quellen = rag_assistent.steuererklaerungspflicht_grundfall(
            "Muss ich überhaupt eine Steuererklärung abgeben?", [PFLICHT_QUELLE]
        )
        self.assertTrue(antwort.startswith("Meistens nein"))
        self.assertIn("mehrere Arbeitgeber", antwort)
        self.assertIn("410 Euro", antwort)
        self.assertEqual(quellen, [PFLICHT_QUELLE])

    def test_steuererklaerungsfrist_fuer_2025(self):
        antwort, quellen = rag_assistent.steuererklaerungsfrist_grundfall(
            "Bis wann muss die Steuererklärung beim Finanzamt sein?", [FRIST_QUELLE]
        )
        self.assertIn("31. Juli 2026", antwort)
        self.assertIn("28. Februar 2027", antwort)
        self.assertEqual(quellen, [FRIST_QUELLE])

    def test_freiwillige_steuererklaerung_rueckwirkend(self):
        antwort, quellen = rag_assistent.freiwillige_steuererklaerung_grundfall(
            "Kann ich die Steuererklärung auch rückwirkend machen?", [FREIWILLIG_QUELLE]
        )
        self.assertTrue(antwort.startswith("Ja."))
        self.assertIn("vier Jahre", antwort)
        self.assertIn("31. Dezember 2026", antwort)
        self.assertEqual(quellen, [FREIWILLIG_QUELLE])

    def test_werbungskosten_keine_falsche_5000_euro_grenze(self):
        antwort, quellen = rag_assistent.werbungskosten_grundfall(
            "Was sind Werbungskosten und was kann ich alles absetzen?", [WERBUNGSKOSTEN_QUELLE]
        )
        self.assertIn("direkt mit deinem Beruf", antwort)
        self.assertIn("4.500 Euro", antwort)
        self.assertNotIn("5.000 Euro", antwort)
        self.assertEqual(quellen, [WERBUNGSKOSTEN_QUELLE])

    def test_werbungskosten_beispiele_trennt_homeoffice(self):
        antwort, quellen = rag_assistent.werbungskosten_beispiele_grundfall(
            "Zählen Fahrtkosten, Homeoffice oder Fortbildungen dazu?", [WERBUNGSKOSTEN_QUELLE]
        )
        self.assertIn("Fahrtkosten", antwort)
        self.assertIn("Fortbildungen", antwort)
        self.assertIn("Homeoffice gelten eigene Regeln", antwort)
        self.assertEqual(quellen, [WERBUNGSKOSTEN_QUELLE])

    def test_handwerker_und_spenden_trennt_kostenarten(self):
        antwort, quellen = rag_assistent.handwerker_und_spenden_grundfall(
            "Kann ich Handwerkerrechnungen oder Spenden angeben?", [HANDWERKER_QUELLE, SPENDEN_QUELLE]
        )
        self.assertIn("Arbeits-, Fahrt- und Maschinenkosten", antwort)
        self.assertIn("Materialkosten zählen nicht", antwort)
        self.assertIn("steuerbegünstigte Organisation", antwort)
        self.assertEqual(quellen, [HANDWERKER_QUELLE, SPENDEN_QUELLE])

    def test_handwerker_und_haushaltsnahe_dienstleistungen_unterscheidet(self):
        antwort, quellen = rag_assistent.handwerker_und_spenden_grundfall(
            "Was ist der Unterschied zwischen Handwerkerleistungen und haushaltsnahen Dienstleistungen?",
            [HANDWERKER_QUELLE],
        )
        self.assertIn("Reparatur oder Wartung", antwort)
        self.assertIn("Reinigung, Gartenpflege oder Pflege", antwort)
        self.assertIn("4.000 Euro", antwort)
        self.assertEqual(quellen, [HANDWERKER_QUELLE])

    def test_nebenkostenabrechnung_trennt_arbeits_und_energiekosten(self):
        antwort, quellen = rag_assistent.nebenkostenabrechnung_grundfall(
            "Kann ich die Nebenkostenabrechnung meines Vermieters absetzen?",
            [HANDWERKER_QUELLE],
        )
        self.assertTrue(antwort.startswith("Teilweise."))
        self.assertIn("Arbeitskosten", antwort)
        self.assertIn("Energie-, Brennstoff- und Materialkosten", antwort)
        self.assertEqual(quellen, [HANDWERKER_QUELLE])

    def test_steuerklasse_nach_hochzeit_automatisch_iv(self):
        antwort, quellen = rag_assistent.ehe_und_splitting_grundfall(
            "Ändert sich meine Steuerklasse nach der Hochzeit automatisch?", [EHE_QUELLE]
        )
        self.assertTrue(antwort.startswith("Ja, normalerweise automatisch"))
        self.assertIn("Steuerklasse IV", antwort)
        self.assertEqual(quellen, [EHE_QUELLE])

    def test_ehegattensplitting_verspricht_keinen_sicheren_vorteil(self):
        antwort, quellen = rag_assistent.ehe_und_splitting_grundfall(
            "Wie funktioniert das Ehegattensplitting bei der Steuer?", [EHE_QUELLE]
        )
        self.assertIn("nicht automatisch immer günstiger", antwort)
        self.assertEqual(quellen, [EHE_QUELLE])

    def test_kinderbetreuungskosten_mit_rechnung_und_ueberweisung(self):
        antwort, quellen = rag_assistent.kinderbetreuungskosten_grundfall(
            "Was kann ich bei den Betreuungskosten für mein Kind absetzen?", [KINDER_QUELLE]
        )
        self.assertIn("80 Prozent", antwort)
        self.assertIn("4.800 Euro", antwort)
        self.assertEqual(quellen, [KINDER_QUELLE])

    def test_krankheitskosten_mit_zumutbarer_belastung(self):
        antwort, quellen = rag_assistent.krankheits_und_pflegekosten_grundfall(
            "Kann ich Krankheitskosten oder Medikamente von der Steuer absetzen?", [KRANKHEIT_QUELLE]
        )
        self.assertIn("zumutbaren Belastung", antwort)
        self.assertEqual(quellen, [KRANKHEIT_QUELLE])

    def test_pflege_pauschbetrag_und_eigenanteil(self):
        antwort, quellen = rag_assistent.krankheits_und_pflegekosten_grundfall(
            "Sind Pflegekosten für Angehörige absetzbar?", [PFLEGE_QUELLE, KRANKHEIT_QUELLE]
        )
        self.assertIn("Pflege-Pauschbetrag", antwort)
        self.assertEqual(quellen, [PFLEGE_QUELLE, KRANKHEIT_QUELLE])

    def test_belege_nicht_unaufgefordert_einreichen(self):
        antwort, quellen = rag_assistent.belege_grundfall(
            "Welche Belege und Dokumente brauche ich?", [BELEGE_QUELLE]
        )
        self.assertIn("Lohnsteuer- oder Rentenbescheinigungen", antwort)
        self.assertIn("nicht sofort ans Finanzamt schicken", antwort)
        self.assertEqual(quellen, [BELEGE_QUELLE])

    def test_steuer_id_beim_bzst_anfordern(self):
        antwort, quellen = rag_assistent.steuer_id_grundfall(
            "Wo finde ich meine Steuer-Identifikationsnummer?", [STEUER_ID_QUELLE]
        )
        self.assertIn("Lohnsteuerbescheinigung", antwort)
        self.assertIn("Einkommensteuerbescheid", antwort)
        self.assertIn("Bundeszentralamt für Steuern", antwort)
        self.assertEqual(quellen, [STEUER_ID_QUELLE])

    def test_private_rechnungen_nicht_pauschal_sechs_jahre(self):
        antwort, quellen = rag_assistent.belegaufbewahrung_grundfall(
            "Wie lange muss ich Rechnungen aufbewahren?", [AUFBEWAHRUNG_QUELLE]
        )
        self.assertIn("keine allgemeine Sechs-Jahres-Regel", antwort)
        self.assertIn("sehr hohen Einkünften", antwort)
        self.assertEqual(quellen, [AUFBEWAHRUNG_QUELLE])

    def test_renovierung_und_afa_bei_vermietung_getrennt(self):
        antwort, quellen = rag_assistent.renovierung_und_afa_bei_vermietung_grundfall(
            "Wie setzen Vermieter Renovierungskosten oder Abschreibungen ab?",
            [RENOVIERUNG_QUELLE, AFA_QUELLE],
        )
        self.assertIn("normale Reparaturen", antwort)
        self.assertIn("15 Prozent", antwort)
        self.assertIn("Gebäudeanteil", antwort)
        self.assertEqual(quellen, [RENOVIERUNG_QUELLE, AFA_QUELLE])

    def test_unsichere_themen_werden_nicht_frei_beantwortet(self):
        self.assertEqual(
            rag_assistent.noch_nicht_abgesicherter_bereich(
                "Wie funktioniert die Verlustverrechnung bei Wertpapieren?"
            ),
            "Kapitaleinkünfte und Wertpapiere",
        )
        self.assertIsNone(
            rag_assistent.noch_nicht_abgesicherter_bereich(
                "Was ist die Entfernungspauschale?"
            )
        )
        self.assertEqual(
            rag_assistent.noch_nicht_abgesicherter_bereich(
                "Wie funktioniert das Ehegattensplitting bei der Steuer?"
            ),
            "Steuerklassen und Ehe",
        )
        self.assertEqual(
            rag_assistent.noch_nicht_abgesicherter_bereich(
                "Wie werden Einnahmen aus einer Photovoltaikanlage behandelt?"
            ),
            "Photovoltaikanlagen",
        )


if __name__ == "__main__":
    unittest.main()
