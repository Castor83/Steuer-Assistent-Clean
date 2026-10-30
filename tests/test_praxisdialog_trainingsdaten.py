import json
import re
import sys
import unittest
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

import praxisdialog_trainingsdaten as praxisdaten


class PraxisdialogTrainingsdatenTest(unittest.TestCase):
    def test_getrennte_basisfaelle(self):
        train_ids = {x[0] for i, x in enumerate(praxisdaten.EINZELFAELLE) if i % 8 != 7}
        validation_ids = {x[0] for i, x in enumerate(praxisdaten.EINZELFAELLE) if i % 8 == 7}
        self.assertFalse(train_ids & validation_ids)

    def test_jahre_der_rohfrage_bleiben_im_ziel(self):
        for eid, roh, ziel in praxisdaten.EINZELFAELLE:
            self.assertEqual(
                set(re.findall(r"\b(?:19|20)\d{2}\b", roh)),
                set(re.findall(r"\b(?:19|20)\d{2}\b", ziel)),
                eid,
            )

    def test_praxistest_wird_nicht_als_training_verwendet(self):
        testdatei = praxisdaten.ZIEL / "praxis_kanonisierung_test.jsonl"
        testfragen = {
            json.loads(zeile)["messages"][-2]["content"].casefold().strip()
            for zeile in testdatei.read_text(encoding="utf-8").splitlines()
        }
        trainingsfragen = {
            praxisdaten.variante(roh, nummer).casefold().strip()
            for _, roh, _ in praxisdaten.EINZELFAELLE
            for nummer in range(24)
        }
        self.assertFalse(testfragen & trainingsfragen)

    def test_varianten_sind_je_basisfall_eindeutig(self):
        for eid, roh, _ in praxisdaten.EINZELFAELLE:
            varianten = {praxisdaten.variante(roh, nummer) for nummer in range(24)}
            self.assertEqual(24, len(varianten), eid)


if __name__ == "__main__":
    unittest.main()
