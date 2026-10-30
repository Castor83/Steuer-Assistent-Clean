import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))
import mehrschritt_rehearsal_daten as rehearsal


class MehrschrittRehearsalDatenTest(unittest.TestCase):
    def test_mischung_haelt_kontrolldateien_unberuehrt(self):
        quelle = rehearsal.DATEN
        with tempfile.TemporaryDirectory() as ordner:
            ziel = Path(ordner)
            for name in (
                "mehrschritt_train.jsonl", "ausgleich_train.jsonl",
                "mehrschritt_validation.jsonl", "ausgleich_validation.jsonl",
            ):
                (ziel / name).write_bytes((quelle / name).read_bytes())
            with patch.object(rehearsal, "DATEN", ziel):
                manifest = rehearsal.erstellen()
        self.assertEqual(216, manifest["train"])
        self.assertEqual(28, manifest["validation"])
        self.assertEqual(144, manifest["neue_mehrschritt_train"])
        self.assertEqual(72, manifest["bewaehrte_ausgleich_train"])
        self.assertIn("mehrschritt_control.jsonl", manifest["kontrolle_unberuehrt"])


if __name__ == "__main__":
    unittest.main()
