from pathlib import Path
import tempfile
import unittest


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from manuelle_steuerwerte import wert_loeschen, wert_speichern, wert_status_setzen, werte_laden
from stammdaten import lade_stammdaten, speichere_stammdaten, stammdaten_status


class GeschuetzteSteuerdatenTest(unittest.TestCase):
    def test_stammdaten_sind_verschluesselt_und_nur_maskiert_abrufbar(self):
        with tempfile.TemporaryDirectory() as temp:
            datei = Path(temp) / "stamm.bin"
            werte = speichere_stammdaten(
                datei,
                {
                    "steuer_id": "12 345 678 901",
                    "steuernummer": "123/456/78901",
                    "iban": "DE89 3704 0044 0532 0130 00",
                },
            )
            self.assertEqual("12345678901", werte["steuer_id"])
            self.assertNotIn(b"12345678901", datei.read_bytes())
            self.assertEqual(werte, lade_stammdaten(datei))
            status = stammdaten_status(datei)
            self.assertNotIn("12345678901", str(status))
            self.assertTrue(status["iban"]["vorhanden"])
            self.assertTrue(status["iban"]["maskiert"].endswith("3000"))

    def test_ungueltige_iban_wird_abgelehnt(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "Prüfziffern"):
                speichere_stammdaten(Path(temp) / "stamm.bin", {"iban": "DE00 3704 0044 0532 0130 00"})

    def test_manueller_wert_muss_bestaetigt_werden_und_bleibt_verschluesselt(self):
        with tempfile.TemporaryDirectory() as temp:
            datei = Path(temp) / "werte.bin"
            wert = wert_speichern(datei, "2023", "arbeitsmittel", "1.234,50", "Rechnung Büro")
            self.assertEqual("Zu prüfen", wert["status"])
            self.assertNotIn(b"1.234,50", datei.read_bytes())
            bestaetigt = wert_status_setzen(datei, wert["id"], "Bestätigt")
            self.assertEqual("Bestätigt", bestaetigt["status"])
            self.assertEqual(1, len(werte_laden(datei, "2023")))
            wert_loeschen(datei, wert["id"])
            self.assertEqual([], werte_laden(datei, "2023"))


if __name__ == "__main__":
    unittest.main()
