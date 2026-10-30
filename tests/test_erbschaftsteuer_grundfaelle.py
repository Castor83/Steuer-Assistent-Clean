from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import rag_assistent


QUELLE = SimpleNamespace(payload={"kategorie": "Erbschaftsteuer"})


class ErbschaftsteuerGrundfaelleTest(unittest.TestCase):
    def test_25000_euro_ohne_verwandtschaft(self):
        antwort, quellen = rag_assistent.erbschaftsteuer_grundfall(
            "Wie hoch ist die Erbschaftsteuer bei 25000 Euro?", [QUELLE]
        )
        self.assertIn("750 Euro", antwort)
        self.assertIn("1.500 Euro", antwort)
        self.assertEqual(quellen, [QUELLE])

    def test_25000_euro_vom_grossvater(self):
        antwort, _ = rag_assistent.erbschaftsteuer_grundfall(
            "Für 25.000 Euro von meinem Großvater", [QUELLE]
        )
        self.assertIn("als Enkelkind", antwort)
        self.assertIn("200.000 Euro", antwort)
        self.assertIn("keine Erbschaftsteuer", antwort)
        self.assertNotIn("von deinem Enkelkind", antwort)

    def test_25000_euro_fuer_geschwister(self):
        antwort, _ = rag_assistent.erbschaftsteuer_grundfall(
            "Wie hoch ist die Erbschaftsteuer bei 25.000 Euro für Geschwister?", [QUELLE]
        )
        self.assertIn("750 Euro", antwort)

    def test_40000_euro_von_tante_hat_freibetrag_steuerklasse_ii(self):
        antwort, quellen = rag_assistent.erbschaftsteuer_grundfall(
            "Ich habe von meiner Tante 40.000 Euro geschenkt bekommen. Welchen Freibetrag kann ich geltend machen?",
            [QUELLE],
        )
        self.assertIn("20.000 Euro", antwort)
        self.assertIn("Steuerklasse II", antwort)
        self.assertEqual(quellen, [QUELLE])


if __name__ == "__main__":
    unittest.main()
