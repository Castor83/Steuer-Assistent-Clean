import sys
import unittest
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

import rag_assistent


class KatalogKorrekturenArbeitsplatzKapitalTest(unittest.TestCase):
    FAELLE = (
        (
            "Darf ich Parkgebühren, die mir am Arbeitsplatz auf einem öffentlichen Parkplatz entstehen, neben der Entfernungspauschale als Werbungskosten geltend machen?",
            ("Nein", "abgegolten"),
        ),
        (
            "Ich nutze ein abgeschlossenes Zimmer in meiner Wohnung zu 85 % beruflich und zu 15 % privat (Gästebett). Kann ich die Raumkosten anteilig als häusliches Arbeitszimmer absetzen?",
            ("Nein", "weniger als 10 Prozent"),
        ),
        (
            "Ich teile mir mit meiner Ehefrau ein häusliches Arbeitszimmer, das den Mittelpunkt unserer jeweiligen beruflichen Tätigkeiten bildet. Gilt die Jahrespauschale von 1.260 Euro für uns gemeinsam?",
            ("personenbezogen", "2.520 Euro"),
        ),
        (
            "Ich habe mir für mein Homeoffice im Jahr 2026 eine Designer-Schreibtischlampe für 1.200 Euro netto gekauft. Kann ich diese sofort im selben Jahr als Werbungskosten abziehen?",
            ("800 Euro", "13 Jahre"),
        ),
        (
            "Kann ich die Kosten für schnelles Internet zu Hause (Monatsabo) in der Steuererklärung angeben, wenn ich keine Einzelnachweise über die berufliche Nutzung besitze?",
            ("20 Prozent", "20 Euro pro Monat"),
        ),
        (
            "Darf ich die Maklergebühren für die Suche nach einer Mietwohnung am neuen Arbeitsort als Werbungskosten geltend machen?",
            ("Ja", "Wohneigentum"),
        ),
        (
            "Ich habe meiner Hausbank im Jahr 2026 keinen Freistellungsauftrag erteilt. Kann ich den Sparer-Pauschbetrag von 1.000 Euro nachträglich über die Steuererklärung geltend machen?",
            ("Ja", "Anlage KAP"),
        ),
        (
            "Ich habe Verluste aus dem Verkauf von ETFs erzielt. Kann ich diese in der Anlage KAP mit meinen Dividendenerträgen bei derselben Bank verrechnen lassen?",
            ("Ja", "allgemeinen Verlustverrechnungstopf"),
        ),
    )

    def test_korrigierte_katalogfaelle(self):
        for frage, erwartete_teile in self.FAELLE:
            with self.subTest(frage=frage):
                ergebnis = rag_assistent.neuer_testkatalog_grundfall(frage, [])
                self.assertIsNotNone(ergebnis)
                antwort, quellen = ergebnis
                self.assertTrue(quellen)
                for teil in erwartete_teile:
                    self.assertIn(teil, antwort)


if __name__ == "__main__":
    unittest.main()
