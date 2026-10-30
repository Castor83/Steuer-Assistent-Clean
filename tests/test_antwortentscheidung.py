from pathlib import Path
import sys
import unittest
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from antwortentscheidung import Antwortstatus, pruefe_sachverhalt, strukturiere_ausgabe
from rag_assistent import _fehlende_zustaendigkeitsrollen


class SachverhaltspruefungTests(unittest.TestCase):
    def test_allgemeine_arbeitswegfrage_fragt_entfernung_und_tage_nach(self):
        ergebnis = pruefe_sachverhalt("Kann ich meinen Arbeitsweg absetzen?")
        self.assertEqual(Antwortstatus.RUECKFRAGE, ergebnis.status)
        self.assertIn("einfache Strecke", ergebnis.text)
        self.assertIn("Arbeitstagen", ergebnis.text)

    def test_arbeitswegfrage_fragt_nur_die_fehlende_angabe_nach(self):
        ohne_tage = pruefe_sachverhalt("Kann ich meinen Arbeitsweg von 15 km absetzen?")
        self.assertEqual(Antwortstatus.RUECKFRAGE, ohne_tage.status)
        self.assertIn("Arbeitstagen", ohne_tage.text)
        ohne_entfernung = pruefe_sachverhalt("Kann ich meinen Arbeitsweg an 180 Arbeitstagen absetzen?")
        self.assertEqual(Antwortstatus.RUECKFRAGE, ohne_entfernung.status)
        self.assertIn("Kilometer", ohne_entfernung.text)

    def test_unaufgeloester_bezug_fuehrt_zur_rueckfrage(self):
        ergebnis = pruefe_sachverhalt("Kann ich das absetzen?")
        self.assertEqual(Antwortstatus.RUECKFRAGE, ergebnis.status)
        self.assertIn("Sachverhalt", ergebnis.fehlende_angaben)

    def test_grundsteuerverfahren_braucht_rolle_und_bundesland(self):
        ergebnis = pruefe_sachverhalt("Muss ich eine Grundsteuererklärung machen?")
        self.assertEqual(Antwortstatus.RUECKFRAGE, ergebnis.status)
        self.assertEqual(("Eigentümerstatus", "Bundesland"), ergebnis.fehlende_angaben)

    def test_mieterangabe_reicht_fuer_die_zustaendigkeitspruefung(self):
        ergebnis = pruefe_sachverhalt(
            "Ich bin Mieter. Muss ich die Grundsteuererklärung abgeben?"
        )
        self.assertEqual(Antwortstatus.ANTWORT, ergebnis.status)

    def test_bescheidfrage_ist_keine_erklaerungsfrage(self):
        ergebnis = pruefe_sachverhalt(
            "Ist der Grundsteuerwertbescheid schon die Rechnung?"
        )
        self.assertEqual(Antwortstatus.ANTWORT, ergebnis.status)

    def test_pipelineausgaenge_sind_explizit(self):
        self.assertEqual(
            Antwortstatus.RUECKFRAGE,
            strukturiere_ausgabe("Welche Angabe fehlt?", []).status,
        )
        self.assertEqual(
            Antwortstatus.ABLEHNUNG,
            strukturiere_ausgabe("Dafür fehlt Evidenz.", []).status,
        )

    def test_zustaendigkeitsantwort_darf_die_gegenrolle_nicht_auslassen(self):
        quelle = SimpleNamespace(payload={
            "text": "Mieter sind nicht zuständig; zuständig sind Eigentümer."
        })
        fehlend = _fehlende_zustaendigkeitsrollen(
            "Muss ich das als Mieter abgeben?",
            "Nein, als Mieter nicht [1].",
            [quelle],
        )
        self.assertEqual(["eigentumer"], fehlend)

    def test_allgemeine_lueckenklassen_fuehren_zur_rueckfrage(self):
        fragen = (
            "Kann ich diesen Rechnungsbetrag steuerlich berücksichtigen?",
            "Mein Arbeitgeber hat etwas gezahlt. Ist das steuerfrei?",
            "Wie viel Steuer bekomme ich zurück?",
            "Darf ich die Fahrt absetzen?",
            "Ich arbeite zuhause. Welche Kosten zählen?",
            "Am Mietshaus wurde etwas repariert. Ist das sofort abziehbar?",
            "Welche Anlage brauche ich dafür?",
            "Kannst du prüfen, ob mein Bescheid stimmt?",
            "Ich habe die Erklärung noch nicht abgegeben. Bin ich zu spät?",
        )
        for frage in fragen:
            with self.subTest(frage=frage):
                self.assertEqual(
                    Antwortstatus.RUECKFRAGE,
                    pruefe_sachverhalt(frage).status,
                )

    def test_fiktive_sachverhalte_werden_vor_retrieval_abgelehnt(self):
        for frage in (
            "Muss eine Zeitmaschine Umsatzsteuer anmelden?",
            "Welche Steuerklasse hat ein Roboter ohne Arbeitgeber?",
            "Kann ich eine Reise in ein erfundenes Land absetzen?",
        ):
            with self.subTest(frage=frage):
                self.assertEqual(
                    Antwortstatus.ABLEHNUNG,
                    pruefe_sachverhalt(frage).status,
                )


if __name__ == "__main__":
    unittest.main()
