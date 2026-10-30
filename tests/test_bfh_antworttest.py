import sys
import unittest
from pathlib import Path


TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))

import bfh_antworttest


class BfhAntwortkatalogTest(unittest.TestCase):
    def test_katalog_enthaelt_15_urteile_und_5_kontrollfragen(self):
        faelle = bfh_antworttest.lade_testfaelle()
        self.assertEqual(20, len(faelle))
        self.assertEqual(15, sum(fall["erwartet"] == "treffer" for fall in faelle))
        self.assertEqual(5, sum(fall["erwartet"] == "kein_treffer" for fall in faelle))

    def test_vollstaendige_bfh_antwort_wird_angenommen(self):
        fall = {"erwartet": "treffer", "aktenzeichen": "XI R 8/21"}
        daten = {
            "antwort": (
                "Ergänzende BFH-Rechtsprechung (historischer Einzelfall): Der Bundesfinanzhof "
                "entschied unter XI R 8/21. Der amtliche Leitsatz folgt. Das Urteil ersetzt nicht "
                "die Prüfung des aktuellen Gesetzesstands."
            ),
            "quellen": [{
                "titel": "BFH, XI R 8/21",
                "url": "https://www.bundesfinanzhof.de/de/entscheidung/123/",
            }],
        }
        self.assertEqual([], bfh_antworttest.pruefe_antwort(fall, daten))

    def test_bfh_hinweis_in_kontrollantwort_wird_abgelehnt(self):
        fall = {"erwartet": "kein_treffer"}
        daten = {
            "antwort": "Ergänzende BFH-Rechtsprechung (historischer Einzelfall)",
            "quellen": [],
        }
        self.assertTrue(bfh_antworttest.pruefe_antwort(fall, daten))


if __name__ == "__main__":
    unittest.main()
