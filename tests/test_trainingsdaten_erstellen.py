import json
import sys
import tempfile
import unittest
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

import trainingsdaten_erstellen as training


class TrainingsdatenErstellenTest(unittest.TestCase):
    def test_alle_quellen_erfuellen_die_freigaberegeln(self):
        beispiele = training.quellen_laden()
        self.assertGreaterEqual(len(beispiele), 107)
        self.assertEqual(len(beispiele), len({x["id"] for x in beispiele}))
        self.assertTrue(all(x["metadaten"]["status"] == "quellenbasiert_freigegeben" for x in beispiele))

    def test_ausgaben_sind_getrennt_und_dublettenfrei(self):
        beispiele = training.deterministische_reihenfolge(training.quellen_laden())
        ergaenzungen = training.deterministische_reihenfolge(training.ergaenzungen_laden())
        train, validation, test = beispiele[:-16] + ergaenzungen, beispiele[-16:-8], beispiele[-8:]
        self.assertEqual((len(beispiele) - 16 + 31, 8, 8), (len(train), len(validation), len(test)))
        mengen = [{x["id"] for x in split} for split in (train, validation, test)]
        self.assertFalse(mengen[0] & mengen[1])
        self.assertFalse(mengen[0] & mengen[2])
        self.assertFalse(mengen[1] & mengen[2])

    def test_themenausgleich_hat_31_amtlich_belegte_faelle(self):
        beispiele = training.ergaenzungen_laden()
        self.assertEqual(31, len(beispiele))
        themen = {x["thema"] for x in beispiele}
        self.assertEqual(
            {
                "Erbschaft und Schenkung",
                "Familie und Kinder",
                "Kapital und private Verkäufe",
                "Selbstständigkeit und Kleinunternehmen",
                "Umsatzsteuer",
            },
            themen,
        )

    def test_jsonl_ist_lesbar(self):
        beispiele = training.deterministische_reihenfolge(training.quellen_laden())[:3]
        with tempfile.TemporaryDirectory() as ordner:
            pfad = Path(ordner) / "probe.jsonl"
            training.jsonl_schreiben(pfad, beispiele)
            geladen = [json.loads(zeile) for zeile in pfad.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([x["id"] for x in beispiele], [x["id"] for x in geladen])
        self.assertTrue(all(len(x["messages"]) == 3 for x in geladen))


if __name__ == "__main__":
    unittest.main()
