import sys
import unittest
from collections import Counter
from pathlib import Path


TRAINING = Path(__file__).resolve().parents[1] / "training"
sys.path.insert(0, str(TRAINING))

import stichprobe_erstellen as stichprobe


class SprachstichprobeTest(unittest.TestCase):
    def test_stichprobe_ist_geschichtet_und_eindeutig(self):
        auswahl = stichprobe.stichprobe_ziehen(stichprobe.laden())
        self.assertEqual(120, len(auswahl))
        self.assertEqual(120, len({x["id"] for x in auswahl}))
        verteilung = Counter((x["thema"], x["metadaten"]["stil"]) for x in auswahl)
        self.assertEqual({3}, set(verteilung.values()))
        self.assertEqual(40, len(verteilung))

    def test_stichprobe_enthaelt_keine_fachantworten(self):
        auswahl = stichprobe.stichprobe_ziehen(stichprobe.laden())
        self.assertTrue(all(not x["metadaten"]["fachantwort_enthalten"] for x in auswahl))
        self.assertTrue(all(len(x["messages"]) == 3 for x in auswahl))


if __name__ == "__main__":
    unittest.main()
