import json
from pathlib import Path
import sys
import unittest

PROJEKT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJEKT / "app"))

import rag_assistent


class SteuerjahrFachkatalogTest(unittest.TestCase):
    def test_alle_36_profilfragen(self):
        katalog = json.loads(
            (PROJEKT / "tests" / "steuerjahrpakete_2023_2025_36.json").read_text(encoding="utf-8")
        )
        self.assertEqual(36, len(katalog))
        for fall in katalog:
            with self.subTest(id=fall["id"], steuerjahr=fall["steuerjahr"]):
                antwort, quellen = rag_assistent.beantworte(
                    fall["frage"],
                    steuerjahr=fall["steuerjahr"],
                    steuerprofil={},
                )
                for fragment in fall["erwartete_fragmente"]:
                    self.assertIn(fragment, antwort)
                self.assertTrue(quellen)
                self.assertTrue(
                    all(
                        str(quelle.payload.get("steuerjahr")) == str(fall["steuerjahr"])
                        for quelle in quellen
                    )
                )


if __name__ == "__main__":
    unittest.main()

