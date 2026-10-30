import sys
import unittest
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

from elster_leitfaden_aktualisieren import extrahiere_abschnitte, pruefe_vollstaendigkeit


class ElsterLeitfadenTest(unittest.TestCase):
    def test_ueberschriften_und_inhalte_werden_getrennt(self):
        langer_text = " ".join(f"Inhalt-{nummer}" for nummer in range(18_000))
        html = f"""
        <html><body><h2>Anleitung zur Einkommensteuererklärung 2025</h2>
        <h3>Hauptvordruck</h3><p>{langer_text}</p>
        <h3>Anlage N</h3><p>{langer_text}</p>
        <h3>Anlage Kind</h3><p>{langer_text}</p>
        <h3>Anlage KAP</h3><p>{langer_text}</p>
        <h3>Anlage V</h3><p>{langer_text}</p>
        <h3>Anlage Vorsorgeaufwand</h3><p>{langer_text}</p>
        <h3>Anlage Sonderausgaben</h3><p>{langer_text}</p>
        <h3>Außergewöhnliche Belastungen</h3><p>{langer_text}</p>
        </body></html>
        """
        abschnitte = extrahiere_abschnitte(html)
        pruefe_vollstaendigkeit(abschnitte)
        self.assertGreaterEqual(len(abschnitte), 100)
        self.assertTrue(any("Anlage N" in eintrag["abschnitt"] for eintrag in abschnitte))


if __name__ == "__main__":
    unittest.main()
