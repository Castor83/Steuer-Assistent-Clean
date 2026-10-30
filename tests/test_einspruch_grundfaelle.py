import sys
import unittest
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

import rag_assistent


class EinspruchGrundfaelleTest(unittest.TestCase):
    def test_telefonischer_einspruch_reicht_nicht(self):
        ergebnis = rag_assistent.neu_abgesicherte_grundfaelle(
            "Ist es möglich, dass Felix den Einspruch telefonisch einlegt?",
            [],
        )
        self.assertIsNotNone(ergebnis)
        antwort, quellen = ergebnis
        self.assertTrue(quellen)
        self.assertIn("Nein", antwort)
        self.assertIn("§ 357", antwort)
        self.assertIn("Telefonat genügt aber nicht", antwort)

    def test_schlichte_aenderung_als_alternative(self):
        ergebnis = rag_assistent.neu_abgesicherte_grundfaelle(
            "Welche andere Möglichkeit außer eines Einspruchs hat Felix, um gegen den Bescheid vorzugehen?",
            [],
        )
        self.assertIsNotNone(ergebnis)
        antwort, quellen = ergebnis
        self.assertTrue(quellen)
        self.assertIn("schlichte Änderung", antwort)
        self.assertIn("§ 172", antwort)
        self.assertIn("Änderungspunkt", antwort)


if __name__ == "__main__":
    unittest.main()
