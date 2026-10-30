import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

import authentifizierung


class AuthentifizierungTest(unittest.TestCase):
    def test_konten_werden_gehasht_gespeichert_und_nach_rollen_geprueft(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(
            authentifizierung, "KONFIGURATION", Path(temp) / "anmeldung.json"
        ):
            authentifizierung.konto_speichern("Claudia", "beispiel", "nutzer")
            authentifizierung.konto_speichern("Alex", "verwaltung", "admin")
            inhalt = authentifizierung.KONFIGURATION.read_text(encoding="utf-8")
            self.assertNotIn("beispiel", inhalt)
            self.assertNotIn("verwaltung", inhalt)
            self.assertEqual("nutzer", authentifizierung.konto_pruefen("claudia", "beispiel")["rolle"])
            self.assertEqual("admin", authentifizierung.konto_pruefen("Alex", "verwaltung")["rolle"])
            self.assertIsNone(authentifizierung.konto_pruefen("Alex", "falsch"))
            self.assertTrue(authentifizierung.ist_eingerichtet())

    def test_erneutes_speichern_ersetzt_nur_das_gewaehlte_konto(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(
            authentifizierung, "KONFIGURATION", Path(temp) / "anmeldung.json"
        ):
            authentifizierung.konto_speichern("Eins", "alt", "nutzer")
            authentifizierung.konto_speichern("Zwei", "bleibt", "admin")
            authentifizierung.konto_speichern("EINS", "neu", "nutzer")
            self.assertIsNone(authentifizierung.konto_pruefen("Eins", "alt"))
            self.assertIsNotNone(authentifizierung.konto_pruefen("eins", "neu"))
            self.assertIsNotNone(authentifizierung.konto_pruefen("Zwei", "bleibt"))


if __name__ == "__main__":
    unittest.main()
