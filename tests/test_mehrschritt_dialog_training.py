import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

import mehrschritt_dialog_training as daten


class MehrschrittDialogTrainingTest(unittest.TestCase):
    def test_umfang_und_getrennte_basisfaelle(self):
        with tempfile.TemporaryDirectory() as ordner, patch.object(daten, "ZIEL", Path(ordner)):
            manifest = daten.erstellen()
        self.assertEqual(24, manifest["basisfaelle"])
        self.assertEqual({"train": 144, "validation": 24, "control": 24}, {
            name: manifest[name] for name in ("train", "validation", "control")
        })
        mengen = [set(manifest["basis_ids"][name]) for name in ("train", "validation", "control")]
        self.assertFalse(mengen[0] & mengen[1])
        self.assertFalse(mengen[0] & mengen[2])
        self.assertFalse(mengen[1] & mengen[2])

    def test_alle_beispiele_sind_mehrschrittig_und_fachlich_markiert(self):
        with tempfile.TemporaryDirectory() as ordner, patch.object(daten, "ZIEL", Path(ordner)):
            daten.erstellen()
            eintraege = []
            for name in ("train", "validation", "control"):
                pfad = Path(ordner) / f"mehrschritt_{name}.jsonl"
                eintraege.extend(json.loads(x) for x in pfad.read_text(encoding="utf-8").splitlines())
        self.assertEqual(192, len(eintraege))
        self.assertTrue(all(len(x["messages"]) == 5 for x in eintraege))
        self.assertTrue(all(x["metadaten"]["fachlich_geprueft"] for x in eintraege))
        self.assertTrue(all(x["detailregeln"] for x in eintraege))
        folgefragen = [x["messages"][-2]["content"] for x in eintraege]
        self.assertFalse(any(".?" in text or "??" in text for text in folgefragen))

    def test_varianten_eines_basisfalls_sind_eindeutig(self):
        for eid, _vorher, _assistent, folge, _ziel, _regeln in daten.FAELLE:
            varianten = {daten.variante(folge, nummer) for nummer in range(8)}
            self.assertEqual(8, len(varianten), eid)


if __name__ == "__main__":
    unittest.main()
