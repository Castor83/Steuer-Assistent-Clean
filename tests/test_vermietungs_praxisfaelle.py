from pathlib import Path
import sys
import unittest


PROJEKT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJEKT / "app"))

import rag_assistent


PROFIL = {
    "person": {"angestellter": True, "hausbesitzer": True},
    "grundabgaben_standardobjekt": {
        "gebaeudeart": "Dreifamilienhaus",
        "nutzung": "teilweise selbst genutzt und teilweise vermietet",
    },
}


def antwort(frage: str, jahr: int = 2023):
    return rag_assistent.beantworte(
        frage,
        steuerjahr=jahr,
        steuerprofil=PROFIL,
    )


class VermietungsPraxisfaelleTest(unittest.TestCase):
    def test_gartenkosten_werden_nach_nutzung_und_umlagen_getrennt(self):
        text, _ = antwort("Kann ich den Garten der Mietwohnung auch absetzen?")
        self.assertIn("anteilig abziehbar", text)
        self.assertIn("gemeinsam genutzten Garten", text)
        self.assertIn("Zahlungen der Mieter", text)
        self.assertNotIn("Privatvergnügen", text)

    def test_heizungsaustausch_behandelt_vermieteten_statt_eigenen_anteil(self):
        text, _ = antwort("Zählt der Austausch einer alten Heizung als Erhaltungsaufwand?")
        self.assertIn("regelmäßig Erhaltungsaufwand", text)
        self.assertIn("vermietete Anteil", text)
        self.assertIn("zwei bis fünf Jahre", text)
        self.assertIn("15-Prozent-Regel", text)
        self.assertNotIn("gilt dies nur für deinen Teil", text)

    def test_unbezahlte_miete_ist_noch_keine_einnahme(self):
        text, quellen = antwort("Was ist, wenn mein Mieter die Miete schuldig bleibt (Mietnomade)?")
        self.assertIn("nicht als Einnahme", text)
        self.assertIn("Zuflussprinzip", text)
        self.assertIn("Zahlungsjahr", text)
        self.assertNotIn("ausstehende Miete direkt als steuerpflichtige Einnahme", text)
        self.assertIn("§ 11", quellen[0].payload["paragraph"])

    def test_kaution_wird_erst_bei_endgueltiger_verrechnung_einnahme(self):
        text, quellen = antwort("Muss ich die Kaution des Mieters versteuern?")
        self.assertIn("Nicht schon beim Erhalt", text)
        self.assertIn("rückzahlbare Sicherheit", text)
        self.assertIn("verrechneten Teil", text)
        self.assertIn("getrennt als Werbungskosten", text)
        self.assertIn(2023, quellen[0].payload["gueltig_fuer"])

    def test_angehoerigenmiete_enthaelt_alle_drei_bereiche(self):
        text, _ = antwort("Wie viel Miete muss ich von Verwandten verlangen, damit das Amt nicht meckert?")
        self.assertIn("mindestens 66 Prozent", text)
        self.assertIn("mindestens 50, aber weniger als 66 Prozent", text)
        self.assertIn("weniger als 50 Prozent", text)
        self.assertIn("Totalüberschussprognose", text)
        self.assertIn("Bruttomiete", text)

    def test_verkauf_mischt_selbstnutzung_nicht_mit_vermieteten_wohnungen(self):
        text, _ = antwort("Wann ist der Verkauf meines Mietshauses steuerfrei?")
        self.assertIn("mehr als zehn Jahre", text)
        self.assertIn("Selbstnutzung", text)
        self.assertIn("nur deinen selbst bewohnten Gebäudeteil", text)
        self.assertIn("vermieteten Wohnungen", text)

    def test_zehnjahresfrist_und_selbstnutzung_werden_nicht_umgekehrt(self):
        text, _ = antwort("Gilt die 10-Jahres-Frist auch, wenn ich selbst darin gewohnt habe?")
        self.assertIn("schon innerhalb der zehn Jahre steuerfrei", text)
        self.assertIn("Nach Ablauf der zehn Jahre", text)
        self.assertNotIn("musst du die Steuern zwar bezahlen", text)

    def test_kaufnebenkosten_gebaeudeanteil_wirkt_ueber_afa(self):
        text, _ = antwort("Kann ich die Kaufnebendokumente (Notar, Grundbuch, Makler) sofort absetzen?")
        self.assertIn("Anschaffungsnebenkosten", text)
        self.assertIn("AfA-Bemessungsgrundlage", text)
        self.assertIn("Grund und Boden", text)
        self.assertIn("Grundschuld", text)
        self.assertNotIn("erst dann steuerlich berücksichtigt, wenn das Haus später verkauft", text)

    def test_drei_objekt_grenze_ist_keine_steuerfreigrenze(self):
        text, _ = antwort('Was ist die "3-Objekt-Grenze" beim Immobilienverkauf?')
        self.assertIn("keine Steuerfreigrenze", text)
        self.assertIn("mehr als drei Objekte", text)
        self.assertIn("fünf Jahren", text)
        self.assertIn("auch die ersten drei", text)
        self.assertNotIn("zwei Freibeträge", text)

    def test_kernregeln_funktionieren_auch_fuer_2024_und_2025(self):
        for jahr in (2024, 2025):
            mietausfall, _ = antwort("Mein Mieter zahlt die Miete nicht", jahr)
            verkauf, _ = antwort("Ist der Hausverkauf nach zehn Jahren steuerfrei?", jahr)
            self.assertIn("Zuflussprinzip", mietausfall)
            self.assertIn("mehr als zehn Jahre", verkauf)


if __name__ == "__main__":
    unittest.main()
