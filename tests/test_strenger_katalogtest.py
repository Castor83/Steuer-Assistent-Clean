import json
import sys
import tempfile
from pathlib import Path
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parent))

from strenger_katalogtest import bewerte_fall, lade_faelle, pruefe_sollantwort, zahlenfakten


class StrengerKatalogtestTest(unittest.TestCase):
    def test_ja_nein_passt(self):
        ergebnis = pruefe_sollantwort(
            "Darf ich das?", "Ja, die Kosten sind Werbungskosten.",
            "Ja. Die Kosten können als Werbungskosten abgezogen werden.",
        )
        self.assertEqual("BESTANDEN", ergebnis["status"])

    def test_ja_nein_widerspruch(self):
        ergebnis = pruefe_sollantwort("Darf ich das?", "Nein, das ist ausgeschlossen.", "Ja, das ist möglich.")
        self.assertEqual("FACHLICH_PRUEFEN", ergebnis["status"])
        self.assertIn("Ja/Nein", ergebnis["gruende"][0])

    def test_fehlender_betrag_wird_erkannt(self):
        ergebnis = pruefe_sollantwort(
            "Wie hoch?", "Der Freibetrag beträgt 500.000 Euro innerhalb von 10 Jahren.",
            "Der Freibetrag beträgt 400.000 Euro innerhalb von zehn Jahren.",
        )
        self.assertEqual(["500000 euro", "10 jahre"], ergebnis["fehlende_zahlen"])

    def test_deutsche_zahlen_werden_normalisiert(self):
        self.assertEqual(
            ["1230 euro", "0.3 euro", "38 prozent", "10 tage"],
            zahlenfakten("1.230 Euro, 0,30 €, 38 % und 10 Tage"),
        )

    def test_ohne_quelle_ist_basisfehler(self):
        fall = {"frage": "Test?", "erwartete_antwort": "Ja."}
        ergebnis = bewerte_fall(fall, {"antwort": "Ja.", "quellen": []})
        self.assertEqual("OHNE_QUELLE", ergebnis["status"])

    def test_ohne_sollantwort_nur_strukturell(self):
        fall = {"frage": "Test?"}
        ergebnis = bewerte_fall(fall, {"antwort": "Eine belegte Antwort.", "quellen": [{"titel": "Quelle"}]})
        self.assertEqual("NUR_STRUKTURELL_BESTANDEN", ergebnis["status"])

    def test_flektierte_fachbegriffe_werden_akzeptiert(self):
        ergebnis = pruefe_sollantwort(
            "Darf ich zweimal fahren?",
            "Nein. Die Fahrten sind pro Arbeitstag auf einen Kalendertag beschränkt.",
            "Nein. Auch bei zwei Fahrten zählt nur eine einzige Anfahrt am selben Tag.",
        )
        self.assertEqual("BESTANDEN", ergebnis["status"])

    def test_katalog_mit_benannter_fragenliste_wird_geladen(self):
        with tempfile.TemporaryDirectory() as ordner:
            pfad = Path(ordner) / "fragen.json"
            pfad.write_text(
                json.dumps({"steuerfragen": [{"id": 1, "kategorie": "Test", "frage": "Test?"}]}),
                encoding="utf-8",
            )
            faelle = lade_faelle([pfad])
        self.assertEqual(1, len(faelle))
        self.assertEqual("Test?", faelle[0][1]["frage"])


if __name__ == "__main__":
    unittest.main()
