import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


APP_DIR = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

import nutzerverwaltung
import web_ui


class NutzerverwaltungTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.patches = [
            patch.object(nutzerverwaltung, "NUTZER_DATEN", root / "daten" / "nutzer"),
            patch.object(nutzerverwaltung, "NUTZER_DOKUMENTE", root / "dokumente" / "nutzer"),
            patch.object(nutzerverwaltung, "NUTZER_INDEX", root / "daten" / "nutzer" / "index.json"),
            patch.object(nutzerverwaltung, "LEGACY_PROFIL", root / "daten" / "steuerprofil.json"),
            patch.object(nutzerverwaltung, "LEGACY_REGISTER", root / "daten" / "dokumentregister.json"),
            patch.object(nutzerverwaltung, "LEGACY_EINSTELLUNGEN", root / "daten" / "einstellungen.json"),
            patch.object(nutzerverwaltung, "LEGACY_EINGANG", root / "dokumente" / "eingang"),
        ]
        for p in self.patches:
            p.start()
        nutzerverwaltung.aktiven_nutzer_setzen(None)
        self.root = root

    def tearDown(self):
        nutzerverwaltung.aktiven_nutzer_setzen(None)
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def test_nutzer_erhalten_getrennte_zufaellige_ordner(self):
        anna, _ = nutzerverwaltung.nutzer_anlegen("Anna Beispiel")
        annas_profil = nutzerverwaltung.profil_datei()
        bert, _ = nutzerverwaltung.nutzer_anlegen("Bert Beispiel")
        berts_profil = nutzerverwaltung.profil_datei()

        self.assertNotEqual(anna["id"], bert["id"])
        self.assertNotIn("Anna", str(annas_profil))
        self.assertNotEqual(annas_profil, berts_profil)
        self.assertTrue((nutzerverwaltung.datenordner() / "steuerjahre").is_dir())
        self.assertTrue(nutzerverwaltung.standard_eingang().is_dir())

    def test_erster_nutzer_bekommt_altbestand_als_kopie(self):
        nutzerverwaltung.LEGACY_PROFIL.parent.mkdir(parents=True)
        nutzerverwaltung.LEGACY_PROFIL.write_text(
            json.dumps({"person": {"angestellter": True}}), encoding="utf-8"
        )
        nutzerverwaltung.LEGACY_EINGANG.mkdir(parents=True)
        altdatei = nutzerverwaltung.LEGACY_EINGANG / "lohnsteuer-2023.txt"
        altdatei.write_text("Altbestand", encoding="utf-8")
        nutzerverwaltung.LEGACY_REGISTER.write_text(
            json.dumps({"abc": {"id": "abc", "pfad": str(altdatei)}}), encoding="utf-8"
        )

        _nutzer, migriert = nutzerverwaltung.nutzer_anlegen("Erster Nutzer")

        self.assertTrue(migriert)
        self.assertTrue(nutzerverwaltung.profil_datei().is_file())
        neue_datei = nutzerverwaltung.standard_eingang() / altdatei.name
        self.assertEqual("Altbestand", neue_datei.read_text(encoding="utf-8"))
        self.assertTrue(altdatei.is_file(), "Der Altbestand darf nicht verschoben werden.")
        register = json.loads(nutzerverwaltung.dokumentregister_datei().read_text(encoding="utf-8"))
        self.assertEqual(str(neue_datei.resolve()), register["abc"]["pfad"])

    def test_ungueltige_und_doppelte_namen_werden_abgelehnt(self):
        with self.assertRaises(ValueError):
            nutzerverwaltung.nutzer_anlegen("A")
        nutzerverwaltung.nutzer_anlegen("Alex")
        with self.assertRaises(ValueError):
            nutzerverwaltung.nutzer_anlegen(" alex ")

    def test_web_api_verlangt_auswahl_und_bindet_cookie_an_nutzer(self):
        bisher_testing = web_ui.app.config["TESTING"]
        web_ui.app.config["TESTING"] = False
        try:
            ohne_auswahl = web_ui.app.test_client()
            self.assertEqual(428, ohne_auswahl.get("/api/steuerprofil").status_code)

            browser = web_ui.app.test_client()
            erstellt = browser.post("/api/nutzer", json={"name": "Cookie Nutzer"})
            self.assertEqual(201, erstellt.status_code)
            self.assertIn("steuer_assistent_nutzer=", erstellt.headers.get("Set-Cookie", ""))
            self.assertEqual(200, browser.get("/api/steuerprofil").status_code)

            zweiter_browser = web_ui.app.test_client()
            self.assertEqual(428, zweiter_browser.get("/api/steuerprofil").status_code)
        finally:
            web_ui.app.config["TESTING"] = bisher_testing


if __name__ == "__main__":
    unittest.main()
