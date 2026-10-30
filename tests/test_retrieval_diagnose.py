from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from retrieval_diagnose import RetrievalTreffer, vereinige_treffer


class RetrievalDiagnoseTests(unittest.TestCase):
    def test_doppelfund_wird_vereinigt_und_markiert(self):
        payload = {"url": "https://amtlich.test/x", "paragraph": "§ 1", "text": "Text"}
        lexikalisch = RetrievalTreffer(payload, .7, "lexikal", 3.1)
        semantisch = RetrievalTreffer(payload, .8, "semantisch", .8)
        ergebnis = vereinige_treffer([lexikalisch], [semantisch])
        self.assertEqual(1, len(ergebnis))
        self.assertEqual("lexikal+semantisch", ergebnis[0].trefferart)
        self.assertEqual(.8, ergebnis[0].score)


if __name__ == "__main__":
    unittest.main()
