from pathlib import Path
import sys
from types import SimpleNamespace
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import rag_assistent


EHE_QUELLE = SimpleNamespace(payload={"kategorie": "Steuerklassen und Ehe"})


class SteuerExAntwortfokusTest(unittest.TestCase):
    def test_erbschaftsteuerklasse_wird_nicht_als_lohnsteuerklasse_beantwortet(self):
        frage = (
            "Ein Sohn erbt von seiner Mutter einen Geldbetrag. Sein steuerpflichtiger Erwerb "
            "nach § 10 ErbStG steht fest. Welche Steuerklasse findet auf den geerbten "
            "Betrag Anwendung und wie hoch ist der Steuersatz?"
        )
        self.assertIsNone(rag_assistent.ehe_und_splitting_grundfall(frage, [EHE_QUELLE]))

    def test_lottoantwort_beantwortet_auch_den_spieleinsatz_ohne_fremden_namen(self):
        frage = (
            "Felicitas hat in einem rein auf Glück basierenden Lottospiel gewonnen. "
            "Sind die Einnahmen aus dem Lotteriegewinn steuerpflichtig und kann der "
            "Spieleinsatz als Erwerbsaufwendungen abgezogen werden?"
        )
        antwort, quellen = rag_assistent.eindeutige_langfallantwort(frage)
        self.assertIn("nicht steuerbar", antwort)
        self.assertIn("Spieleinsatz", antwort)
        self.assertNotIn("Justus", antwort)
        self.assertEqual(1, len(quellen))

    def test_studienfrage_mit_lotto_vorgeschichte_beantwortet_das_studium(self):
        frage = (
            "Felicitas ist unbeschränkt einkommensteuerpflichtig und gewann im Lottospiel. "
            "Danach begann sie direkt nach dem Abitur ohne Berufsausbildung ein Bachelorstudium. "
            "Wie werden die Aufwendungen im Zusammenhang mit dem Bachelorstudium "
            "einkommensteuerlich behandelt?"
        )
        antwort, quellen = rag_assistent.eindeutige_langfallantwort(frage)
        self.assertIn("Erststudium", antwort)
        self.assertIn("Sonderausgaben", antwort)
        self.assertNotIn("Lotteriegewinn unterliegt", antwort)
        self.assertEqual(1, len(quellen))


if __name__ == "__main__":
    unittest.main()
