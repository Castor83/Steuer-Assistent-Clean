from io import BytesIO
from pathlib import Path
import tempfile
import unittest


import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from dokument_upload import MAX_UPLOAD_BYTES, speichere_upload, ziel_liegt_auf_c


class DokumentUploadTest(unittest.TestCase):
    def test_laufwerkserlaubnis_ist_auf_c_begrenzt(self):
        self.assertTrue(ziel_liegt_auf_c(Path(r"C:\Steuer-Assistent")))
        self.assertFalse(ziel_liegt_auf_c(Path(r"D:\Steuer-Assistent")))

    def test_gueltiges_pdf_wird_mit_sicherem_namen_gespeichert(self):
        with tempfile.TemporaryDirectory() as temp:
            ziel = Path(temp)
            datei = speichere_upload(ziel, r"..\..\Lohn 2023.pdf", BytesIO(b"%PDF-1.4\n%%EOF"))
            self.assertEqual(ziel.resolve(), datei.parent)
            self.assertEqual("Lohn-2023.pdf", datei.name)
            self.assertEqual(b"%PDF-1.4\n%%EOF", datei.read_bytes())

    def test_falsche_endung_und_getarnter_inhalt_werden_abgelehnt(self):
        with tempfile.TemporaryDirectory() as temp:
            ziel = Path(temp)
            with self.assertRaisesRegex(ValueError, "Erlaubt"):
                speichere_upload(ziel, "beleg.exe", BytesIO(b"MZ"))
            with self.assertRaisesRegex(ValueError, "Dateiendung"):
                speichere_upload(ziel, "beleg.pdf", BytesIO(b"MZ executable"))

    def test_zu_grosse_datei_wird_abgelehnt(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(ValueError, "25 MB"):
                speichere_upload(Path(temp), "gross.pdf", BytesIO(b"%PDF-" + b"0" * MAX_UPLOAD_BYTES))


if __name__ == "__main__":
    unittest.main()
