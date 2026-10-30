import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import ordner_ueberwacher


class EingangsordnerTest(unittest.TestCase):
    def test_vorhandener_ordner_wird_gespeichert_und_gelesen(self):
        with tempfile.TemporaryDirectory() as temp:
            basis = Path(temp)
            ziel = basis / "Steuerbelege"
            ziel.mkdir()
            einstellungen = basis / "einstellungen.json"
            with patch.object(ordner_ueberwacher, "EINSTELLUNGEN", einstellungen):
                gespeichert = ordner_ueberwacher.setze_eingang(str(ziel))
                self.assertEqual(ziel.resolve(), gespeichert)
                self.assertEqual(ziel.resolve(), ordner_ueberwacher.aktueller_eingang())
                self.assertEqual(str(ziel.resolve()), json.loads(einstellungen.read_text(encoding="utf-8"))["eingangsordner"])

    def test_unbekannter_ordner_wird_abgelehnt(self):
        with tempfile.TemporaryDirectory() as temp:
            unbekannt = Path(temp) / "nicht-vorhanden"
            with self.assertRaisesRegex(ValueError, "nicht gefunden"):
                ordner_ueberwacher.setze_eingang(str(unbekannt))

    def test_relativpfad_wird_abgelehnt(self):
        with self.assertRaisesRegex(ValueError, "vollständigen Ordnerpfad"):
            ordner_ueberwacher.setze_eingang("meine-belege")


if __name__ == "__main__":
    unittest.main()
