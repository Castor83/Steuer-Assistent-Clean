import sys
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, patch
from zipfile import ZipFile


APP_DIR = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

import web_ui


class WebUiTest(unittest.TestCase):
    def setUp(self):
        web_ui.app.config["TESTING"] = True
        self.client = web_ui.app.test_client()
        self.ueberwacher_patcher = patch.object(
            web_ui, "starte_ordnerueberwacher", return_value=MagicMock()
        )
        self.ueberwacher_patcher.start()
        self.addCleanup(self.ueberwacher_patcher.stop)

    def test_status_endpoint(self):
        antwort = self.client.get("/api/status")
        self.assertEqual(200, antwort.status_code)
        self.assertTrue(antwort.get_json()["bereit"])
        self.assertIsInstance(antwort.get_json()["bfh_testmodus"], bool)
        self.assertEqual("lmstudio", antwort.get_json()["modell_backend"])
        self.assertEqual("lmstudio", antwort.get_json()["embedding_backend"])

    @patch.object(web_ui, "starte_ordnerueberwacher")
    def test_status_startet_ordnerueberwachung_nicht(self, starten):
        self.assertEqual(200, self.client.get("/api/status").status_code)
        starten.assert_not_called()

    @patch.object(web_ui, "dokumentuebersicht", return_value=[])
    @patch.object(web_ui, "starte_ordnerueberwacher")
    def test_dokumentbereich_startet_ordnerueberwachung_erstmals(
        self, starten, _dokumente
    ):
        starten.return_value = MagicMock()
        self.assertEqual(200, self.client.get("/api/dokumente").status_code)
        starten.assert_called_once_with()
        starten.return_value.wait.assert_called_once_with(timeout=5)

    def test_oberflaeche_kennzeichnet_kritische_aktionen_mit_nutzerziel(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="upload-ziel"', html)
        self.assertIn('id="stammdaten-ziel"', html)
        self.assertIn('id="manuell-ziel"', html)
        self.assertIn('id="bericht-ziel"', html)
        self.assertIn("AKTIVES PROFIL", html)

    @patch.object(web_ui.authentifizierung, "ist_eingerichtet", return_value=True)
    @patch.object(
        web_ui.authentifizierung,
        "konto_pruefen",
        return_value={"username": "Testnutzer", "rolle": "nutzer"},
    )
    def test_heimnetzmodus_verlangt_anmeldung(self, _konto, _eingerichtet):
        web_ui.app.config["TESTING"] = False
        web_ui.ANMELDEVERSUCHE.clear()
        profil = {"id": "profil-test", "name": "Testnutzer"}
        try:
            with (
                patch.object(web_ui, "HEIMNETZ_MODUS", True),
                patch.object(web_ui.nutzerverwaltung, "nutzer_auflisten", return_value=[profil]),
                patch.object(web_ui.nutzerverwaltung, "nutzer_finden", return_value=profil),
                patch.object(web_ui.nutzerverwaltung, "aktiven_nutzer_setzen", return_value=profil),
            ):
                self.assertEqual(302, self.client.get("/").status_code)
                self.assertEqual(401, self.client.get("/api/nutzer").status_code)
                self.assertEqual(200, self.client.get("/api/status").status_code)
                anmeldung = self.client.post(
                    "/anmelden", data={"username": "Testnutzer", "passwort": "test"}
                )
                self.assertEqual(302, anmeldung.status_code)
                self.assertEqual(200, self.client.get("/").status_code)
                self.assertEqual(200, self.client.get("/api/nutzer").status_code)
                fremd = self.client.post(
                    "/api/nutzer/wechseln", json={"nutzer_id": "fremdes-profil"}
                )
                self.assertEqual(403, fremd.status_code)
                self.assertEqual(302, self.client.post("/abmelden").status_code)
                self.assertEqual(302, self.client.get("/").status_code)
        finally:
            web_ui.ANMELDEVERSUCHE.clear()
            web_ui.app.config["TESTING"] = True

    @patch.object(web_ui.authentifizierung, "ist_eingerichtet", return_value=True)
    @patch.object(web_ui.authentifizierung, "konto_pruefen", return_value=None)
    def test_falsche_heimnetzdaten_werden_abgelehnt(self, _konto, _eingerichtet):
        web_ui.app.config["TESTING"] = False
        web_ui.ANMELDEVERSUCHE.clear()
        try:
            with patch.object(web_ui, "HEIMNETZ_MODUS", True):
                antwort = self.client.post(
                    "/anmelden", data={"username": "niemand", "passwort": "falsch"}
                )
                self.assertEqual(200, antwort.status_code)
                self.assertIn("nicht richtig", antwort.get_data(as_text=True))
                self.assertEqual(302, self.client.get("/").status_code)
        finally:
            web_ui.ANMELDEVERSUCHE.clear()
            web_ui.app.config["TESTING"] = True

    def test_steuerprofil_empfiehlt_passende_bereiche(self):
        antwort = self.client.get("/api/steuerprofil")
        self.assertEqual(200, antwort.status_code)
        daten = antwort.get_json()
        self.assertTrue(daten["gespeichert"])
        self.assertEqual(
            ["arbeitnehmer", "vermietung", "haushalt", "grundsteuer"],
            daten["empfohlene_bereiche"],
        )
        self.assertIn("Angestellter", daten["angaben"])

    @patch.object(web_ui, "dokumentuebersicht", return_value=[])
    @patch.object(
        web_ui,
        "lade_steuerprofil",
        return_value={"person": {"angestellter": True}},
    )
    @patch.object(web_ui, "ordnerueberwachung_sicherstellen")
    def test_steuerakten_api_liefert_2023_bis_2025(
        self, ueberwachung, _profil, _dokumente
    ):
        antwort = self.client.get("/api/steuerakten")
        self.assertEqual(200, antwort.status_code)
        akten = antwort.get_json()["akten"]
        self.assertEqual(["2023", "2024", "2025"], [akte["steuerjahr"] for akte in akten])
        self.assertTrue(all("zusammenfassung" in akte for akte in akten))
        ueberwachung.assert_called_once_with(warten=True)

    def test_kurze_folgeangabe_wird_mit_letzter_nutzerfrage_verbunden(self):
        frage = web_ui.frage_mit_gespraechskontext(
            "Ich bin der Eigentümer",
            [
                {
                    "rolle": "nutzer",
                    "text": "Sind Sanierungsarbeiten nach einem Rohrbruch steuerlich relevant?",
                },
                {"rolle": "assistent", "text": "Das hängt von der Nutzung ab."},
            ],
        )
        self.assertIn("Rohrbruch", frage)
        self.assertIn("Aktuelle Ergänzung: Ich bin der Eigentümer", frage)

    def test_neue_kurze_fachfrage_bleibt_unveraendert(self):
        frage = web_ui.frage_mit_gespraechskontext(
            "Wie hoch ist der Pauschbetrag?",
            [{"rolle": "nutzer", "text": "Was gilt bei Vermietung?"}],
        )
        self.assertEqual("Wie hoch ist der Pauschbetrag?", frage)

    def test_und_was_ist_mit_bleibt_im_gespraechskontext(self):
        frage = web_ui.frage_mit_gespraechskontext(
            "Und was ist mit den Müllgebühren?",
            [
                {
                    "rolle": "nutzer",
                    "text": "Wie behandle ich die Grundsteuer beim teilweise vermieteten Haus?",
                },
                {"rolle": "assistent", "text": "Die Grundsteuer wird aufgeteilt."},
            ],
        )
        self.assertIn("Vorheriger Gesprächskontext", frage)
        self.assertIn("teilweise vermieteten Haus", frage)
        self.assertIn("Aktuelle Ergänzung: Und was ist mit den Müllgebühren?", frage)

    def test_und_warum_bleibt_im_gespraechskontext(self):
        frage = web_ui.frage_mit_gespraechskontext(
            "Und warum soll ich das für 2023 prüfen?",
            [
                {
                    "rolle": "nutzer",
                    "text": "Wo steht die Steuerklasse auf meiner Lohnsteuerbescheinigung?",
                },
                {"rolle": "assistent", "text": "Sie steht oben im Kopfbereich."},
            ],
        )
        self.assertIn("Lohnsteuerbescheinigung", frage)
        self.assertIn("Aktuelle Ergänzung: Und warum", frage)

    def test_heisst_das_bleibt_im_gespraechskontext(self):
        frage = web_ui.frage_mit_gespraechskontext(
            "Heißt das, dass ich bei 30 Verkäufen automatisch Steuern zahlen muss?",
            [
                {"rolle": "nutzer", "text": "Ab wann meldet Kleinanzeigen meine Verkäufe?"},
                {"rolle": "assistent", "text": "Die Plattform kann Daten melden."},
            ],
        )
        self.assertIn("Kleinanzeigen", frage)
        self.assertIn("Aktuelle Ergänzung: Heißt das", frage)

    def test_trotzdem_bezahlen_behaelt_einspruchskontext(self):
        frage = web_ui.frage_mit_gespraechskontext(
            "Muss ich die Grundsteuer in der Zeit trotzdem erst mal bezahlen?",
            [
                {
                    "rolle": "nutzer",
                    "text": "Wie lange kann ich gegen den Grundsteuerwertbescheid Einspruch einlegen?",
                },
                {"rolle": "assistent", "text": "Die Frist beträgt einen Monat."},
            ],
        )
        self.assertIn("Einspruch", frage)
        self.assertIn("Aktuelle Ergänzung", frage)

    @patch.object(web_ui, "lade_steuerprofil", return_value={"person": {"hausbesitzer": True}})
    @patch.object(web_ui, "dialogantwort", return_value=None)
    @patch.object(web_ui, "beantworte", return_value=("Kontextantwort", []))
    def test_frage_endpoint_uebergibt_verlauf_und_profil(
        self, beantworten, _dialog, _profil
    ):
        antwort = self.client.post(
            "/api/frage",
            json={
                "frage": "Ich bin der Eigentümer",
                "steuerjahr": "2024",
                "verlauf": [
                    {
                        "rolle": "nutzer",
                        "text": "Ist die Reparatur eines Rohrbruchs steuerlich relevant?",
                    },
                    {"rolle": "assistent", "text": "Das hängt vom Fall ab."},
                ],
            },
        )
        self.assertEqual(200, antwort.status_code)
        fachfrage = beantworten.call_args.args[0]
        self.assertIn("Vorheriger Gesprächskontext", fachfrage)
        self.assertIn("Rohrbruchs", fachfrage)
        self.assertEqual(
            {"person": {"hausbesitzer": True}},
            beantworten.call_args.kwargs["steuerprofil"],
        )
        self.assertEqual("Ich bin der Eigentümer", beantworten.call_args.kwargs["aktuelle_nachricht"])
        self.assertEqual(2, len(beantworten.call_args.kwargs["gespraech"]))
        self.assertEqual("2024", beantworten.call_args.kwargs["steuerjahr"])

    def test_frage_endpoint_lehnt_ungueltiges_steuerjahr_ab(self):
        antwort = self.client.post(
            "/api/frage", json={"frage": "Test", "steuerjahr": "24"}
        )
        self.assertEqual(400, antwort.status_code)
        self.assertIn("vierstelliges Steuerjahr", antwort.get_json()["fehler"])

    def test_kurze_antwort_auf_assistentenfrage_wird_als_folge_erkannt(self):
        frage = web_ui.frage_mit_gespraechskontext(
            "Eine gemeinsame Leitung",
            [
                {"rolle": "nutzer", "text": "Ich bin der Eigentümer"},
                {
                    "rolle": "assistent",
                    "text": "War deine Wohnung, eine vermietete Wohnung oder eine gemeinsame Leitung betroffen?",
                },
            ],
        )
        self.assertIn("Letzte Assistentenantwort", frage)
        self.assertIn("Aktuelle Ergänzung: Eine gemeinsame Leitung", frage)

    def test_versicherungsfolge_behaelt_die_rohrbruchfrage_im_kontext(self):
        frage = web_ui.frage_mit_gespraechskontext(
            "Wenn das alles über die Gebäudeversicherung gelaufen ist auch",
            [
                {
                    "rolle": "nutzer",
                    "text": "Sind Sanierungsarbeiten nach einem Rohrbruch steuerlich relevant?",
                },
                {"rolle": "assistent", "text": "Welcher Gebäudeteil war betroffen?"},
                {"rolle": "nutzer", "text": "meine Wohnung"},
                {"rolle": "assistent", "text": "Hat die Versicherung die Kosten übernommen?"},
            ],
        )
        self.assertIn("Frühere Nutzerangabe", frage)
        self.assertIn("Rohrbruch", frage)
        self.assertIn("Aktuelle Ergänzung", frage)

    def test_alltagssprache_und_tippfehler_erhalten_interpretationshilfe(self):
        frage = web_ui.frage_mit_gespraechskontext(
            "Die Versicherrung hats komplett bezahlt",
            [
                {"rolle": "nutzer", "text": "Bei mir ist ein Rohr geplatzt"},
                {"rolle": "assistent", "text": "Hat eine Versicherung etwas übernommen?"},
            ],
        )
        self.assertIn("Aktuelle Ergänzung", frage)
        self.assertIn("Interpretationshilfe", frage)
        self.assertIn("Gebäudeversicherung", frage)
        self.assertIn("Rohr geplatzt", frage)

    def test_alleinstehendes_bei_mir_verliert_interpretationshilfe_nicht(self):
        frage = web_ui.frage_mit_gespraechskontext(
            "Bei mir in der Bude ist ein Rohr geplatzt, kann ich das absetzen?",
            [],
        )
        self.assertIn("Interpretationshilfe", frage)
        self.assertIn("selbst genutzte eigene Wohnung", frage)
        self.assertIn("Rohrbruch", frage)

    def test_halbe_versicherungserstattung_wird_im_gespraech_verstanden(self):
        frage = web_ui.frage_mit_gespraechskontext(
            "ja aber nur die haelfte",
            [
                {
                    "rolle": "assistent",
                    "text": "Hat eine Versicherung etwas von der Rechnung übernommen?",
                }
            ],
        )
        self.assertIn("Versicherung", frage)
        self.assertIn("selbst getragen", frage)
        self.assertNotIn("Formuliere", frage)

    def test_grundabgabenort_bleibt_als_sicherer_hinweis_erhalten(self):
        frage = web_ui.frage_mit_gespraechskontext(
            "grundabgaben erlangen mit strassenreinigung und grundsteuer",
            [],
        )
        self.assertIn("Grundabgabenbescheid", frage)
        self.assertIn("Erlangen", frage)

    def test_schreibzugriffe_weisen_fremde_formularanfragen_ab(self):
        antwort = self.client.post(
            "/api/frage",
            data='{"frage":"Test"}',
            content_type="text/plain",
        )
        self.assertEqual(415, antwort.status_code)

    @patch.object(web_ui, "aktueller_eingang", return_value=Path(r"C:\Steuern"))
    @patch.object(web_ui, "dialogantwort", return_value=None)
    @patch.object(web_ui, "beantworte", return_value=("Geprüfte Antwort", []))
    def test_langer_steuerfall_bis_10000_zeichen_wird_angenommen(
        self, beantworten, _dialog, _eingang
    ):
        antwort = self.client.post("/api/frage", json={"frage": "A" * 8_000})
        self.assertEqual(200, antwort.status_code)
        beantworten.assert_called_once()

    def test_extrem_lange_frage_wird_abgelehnt(self):
        antwort = self.client.post("/api/frage", json={"frage": "A" * 10_001})
        self.assertEqual(400, antwort.status_code)
        self.assertIn("10.000", antwort.get_json()["fehler"])

    def test_pruefbericht_lehnt_ungueltiges_jahr_ab(self):
        antwort = self.client.post("/api/pruefbericht", json={"steuerjahr": "26", "bereiche": []})
        self.assertEqual(400, antwort.status_code)
        self.assertIn("gültiges", antwort.get_json()["fehler"])

    @patch.object(web_ui, "dokumentuebersicht", return_value=[])
    def test_pruefbericht_antwortet_ohne_dokumente(self, _uebersicht):
        antwort = self.client.post(
            "/api/pruefbericht",
            json={"steuerjahr": "2025", "bereiche": ["arbeitnehmer"]},
        )
        self.assertEqual(200, antwort.status_code)
        daten = antwort.get_json()
        self.assertEqual("2025", daten["steuerjahr"])
        self.assertEqual(0, daten["zusammenfassung"]["dokumente"])
        self.assertNotIn("pfad", str(daten).lower())

    def test_elster_export_lehnt_nicht_unterstuetztes_jahr_ab(self):
        antwort = self.client.post(
            "/api/elster-export",
            json={"steuerjahr": "2026", "bereiche": []},
        )
        self.assertEqual(400, antwort.status_code)
        self.assertIn("2023, 2024 und 2025", antwort.get_json()["fehler"])

    @patch.object(web_ui.nutzerverwaltung, "datenordner", return_value=Path("."))
    @patch.object(web_ui, "werte_laden", return_value=[])
    @patch.object(web_ui, "lade_stammdaten", return_value={})
    @patch.object(web_ui, "dokumentuebersicht", return_value=[])
    @patch.object(
        web_ui,
        "lade_steuerprofil",
        return_value={
            "quelle": "vom Nutzer bestätigt",
            "wohnsitz": {"postleitzahl": "00000", "stadt": "Erlangen"},
        },
    )
    def test_elster_vorschau_zeigt_felder_und_offene_punkte(
        self, _profil, _dokumente, _stammdaten, _werte, _datenordner
    ):
        antwort = self.client.post(
            "/api/elster-vorschau",
            json={"steuerjahr": "2024", "bereiche": ["vermietung"]},
        )
        self.assertEqual(200, antwort.status_code)
        daten = antwort.get_json()
        self.assertEqual("2024", daten["steuerjahr"])
        self.assertGreaterEqual(daten["zusammenfassung"]["exportierbare_felder"], 1)
        self.assertGreaterEqual(daten["zusammenfassung"]["offene_punkte"], 1)
        self.assertIn("Anlage V", daten["empfohlene_formulare"])

    @patch.object(web_ui.nutzerverwaltung, "datenordner", return_value=Path("."))
    @patch.object(web_ui, "werte_laden", return_value=[])
    @patch.object(web_ui, "lade_stammdaten", return_value={})
    @patch.object(web_ui, "dokumentuebersicht", return_value=[])
    @patch.object(
        web_ui,
        "lade_steuerprofil",
        return_value={
            "quelle": "vom Nutzer bestätigt",
            "wohnsitz": {"postleitzahl": "00000", "stadt": "Erlangen"},
        },
    )
    def test_elster_export_liefert_zip_mit_eingabehilfe(
        self, _profil, _dokumente, _stammdaten, _werte, _datenordner
    ):
        antwort = self.client.post(
            "/api/elster-export",
            json={"steuerjahr": "2023", "bereiche": ["arbeitnehmer"]},
        )
        self.assertEqual(200, antwort.status_code)
        self.assertEqual("application/zip", antwort.mimetype)
        self.assertIn("elster-eingabehilfe-2023.zip", antwort.headers["Content-Disposition"])
        with ZipFile(BytesIO(antwort.data)) as archiv:
            self.assertIn("elster-eingabehilfe-2023.json", archiv.namelist())
            self.assertIn("BITTE-LESEN.txt", archiv.namelist())

    def test_stammdaten_api_liefert_nur_maskierte_werte(self):
        with tempfile.TemporaryDirectory() as temp:
            datei = Path(temp) / "stammdaten.bin"
            with patch.object(web_ui, "_stammdaten_datei", return_value=datei):
                speichern = self.client.post(
                    "/api/stammdaten",
                    json={"werte": {"steuer_id": "12345678901"}, "loeschen": []},
                )
                lesen = self.client.get("/api/stammdaten")
            self.assertEqual(200, speichern.status_code)
            self.assertEqual(200, lesen.status_code)
            antworttext = lesen.get_data(as_text=True)
            self.assertNotIn("12345678901", antworttext)
            self.assertTrue(lesen.get_json()["felder"]["steuer_id"]["vorhanden"])
            self.assertNotIn(b"12345678901", datei.read_bytes())

    def test_manuelle_werte_api_erfordert_bestaetigung(self):
        with tempfile.TemporaryDirectory() as temp:
            datei = Path(temp) / "steuerwerte.bin"
            with patch.object(web_ui, "_steuerwerte_datei", return_value=datei):
                speichern = self.client.post(
                    "/api/manuelle-werte",
                    json={
                        "steuerjahr": "2024",
                        "feld_id": "homeoffice_tage",
                        "wert": "42",
                        "quelle": "Eigene Aufstellung",
                    },
                )
                kennung = speichern.get_json()["wert"]["id"]
                bestaetigen = self.client.post(
                    f"/api/manuelle-werte/{kennung}/status",
                    json={"status": "Bestätigt"},
                )
                lesen = self.client.get("/api/manuelle-werte?steuerjahr=2024")
            self.assertEqual(201, speichern.status_code)
            self.assertEqual("Zu prüfen", speichern.get_json()["wert"]["status"])
            self.assertEqual(200, bestaetigen.status_code)
            self.assertEqual("Bestätigt", lesen.get_json()["werte"][0]["status"])

    def test_dokumentupload_speichert_geprueft_im_eingangsordner(self):
        with tempfile.TemporaryDirectory() as temp:
            ziel = Path(temp)
            with patch.object(web_ui, "aktueller_eingang", return_value=ziel):
                antwort = self.client.post(
                    "/api/dokumente/upload",
                    data={"datei": (BytesIO(b"%PDF-1.4\n%%EOF"), "Lohn 2023.pdf")},
                    content_type="multipart/form-data",
                )
            self.assertEqual(201, antwort.status_code)
            self.assertEqual("Lohn-2023.pdf", antwort.get_json()["dateiname"])
            self.assertTrue((ziel / "Lohn-2023.pdf").is_file())

    def test_dokumentupload_lehnt_getarnte_datei_ab(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(web_ui, "aktueller_eingang", return_value=Path(temp)):
                antwort = self.client.post(
                    "/api/dokumente/upload",
                    data={"datei": (BytesIO(b"MZ executable"), "beleg.pdf")},
                    content_type="multipart/form-data",
                )
            self.assertEqual(400, antwort.status_code)
            self.assertIn("Dateiendung", antwort.get_json()["fehler"])

    @patch.object(web_ui, "dokumentuebersicht")
    def test_registriertes_dokument_kann_geschuetzt_angesehen_werden(self, uebersicht):
        with tempfile.TemporaryDirectory() as temp:
            datei = Path(temp) / "beleg.pdf"
            datei.write_bytes(b"%PDF-1.4\nTest\n%%EOF")
            uebersicht.return_value = [{
                "id": "dok-1",
                "pfad": str(datei),
                "dokumenttyp": "Unbekannte Unterlage",
            }]
            antwort = self.client.get("/api/dokumente/dok-1/vorschau")
            self.assertEqual(200, antwort.status_code)
            self.assertEqual("application/pdf", antwort.mimetype)
            self.assertEqual("no-store", antwort.headers["Cache-Control"])
            self.assertEqual("SAMEORIGIN", antwort.headers["X-Frame-Options"])
            self.assertIn(b"%PDF-1.4", antwort.data)
            antwort.close()

    @patch.object(web_ui, "dokumentuebersicht", return_value=[])
    def test_vorschau_gibt_keinen_beliebigen_dateipfad_frei(self, _uebersicht):
        antwort = self.client.get("/api/dokumente/nicht-registriert/vorschau")
        self.assertEqual(404, antwort.status_code)

    @patch.object(web_ui, "dokumentuebersicht")
    def test_nicht_anzeigbarer_dateityp_wird_abgelehnt(self, uebersicht):
        with tempfile.TemporaryDirectory() as temp:
            datei = Path(temp) / "intern.bin"
            datei.write_bytes(b"nicht anzeigen")
            uebersicht.return_value = [{"id": "dok-2", "pfad": str(datei)}]
            antwort = self.client.get("/api/dokumente/dok-2/vorschau")
        self.assertEqual(415, antwort.status_code)

    @patch.object(web_ui, "vision_wertvorschlaege_uebernehmen")
    @patch.object(web_ui.MODELL_RESSOURCEN, "vision_chat")
    @patch.object(web_ui, "dokumentuebersicht")
    def test_foto_genauer_pruefen_uebernimmt_erkannte_werte(
        self, uebersicht, vision, uebernehmen
    ):
        with tempfile.TemporaryDirectory() as temp:
            bild = Path(temp) / "haus.jpg"
            bild.write_bytes(b"bild")
            uebersicht.return_value = [{"id": "dok-1", "pfad": str(bild)}]
            vision.return_value = {"message": {"content": "Wohnfläche: 120 m2"}}
            uebernehmen.return_value = {
                "id": "dok-1",
                "wertvorschlaege": [{"id": "wohnflaeche", "status": "Bestätigt"}],
                "vision_status": "Lokale Bildprüfung abgeschlossen: 1 Wert erkannt und übernommen.",
            }
            antwort = self.client.post("/api/dokumente/dok-1/vision", json={})
        self.assertEqual(200, antwort.status_code)
        self.assertEqual("Bestätigt", antwort.get_json()["dokument"]["wertvorschlaege"][0]["status"])
        self.assertIn("Dokumentart:", vision.call_args.args[1][0]["content"])
        uebernehmen.assert_called_once_with("dok-1", "Wohnfläche: 120 m2")

    def test_oberflaeche_erklaert_automatische_lokale_foto_pruefung(self):
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("Fotos werden bei Bedarf automatisch genauer geprüft.", html)
        self.assertIn("Foto automatisch genauer geprüft.", html)
        self.assertIn("Steuer-ID: erkannt und bestätigt", html)
        self.assertNotIn("Handschrift/Fotos genauer prüfen", html)
        self.assertIn("status notiz", html)
        self.assertIn("function erfasstBlock", html)
        self.assertIn("function notizAngabenBlock", html)
        self.assertIn("Aus handschriftlicher Notiz übernommen", html)
        self.assertIn("nicht automatisch an ELSTER", html)
        self.assertIn("Keine sicheren Einzelwerte ausgelesen", html)
        self.assertIn("Nicht eindeutig erkannt – bitte prüfen", html)
        self.assertIn("Erkennung ergänzen", html)
        self.assertIn("Übernommen", html)
        self.assertIn("object-fit:contain", html)
        self.assertIn("Klicken für Originalgröße", html)
        self.assertIn("function inlineVorschau", html)
        self.assertIn("function dokumentVorschauUrl", html)
        self.assertIn("doc-preview-details", html)
        self.assertIn("if(details.open) vorschauQuelleLaden(medium)", html)
        self.assertIn("dataset.src", html)
        self.assertIn("loading='lazy'", html)
        self.assertIn("doc-layout", html)
        self.assertIn("doc-inline-preview", html)
        self.assertIn("letzteDokumentSignatur", html)
        self.assertIn("Vorschau", html)
        self.assertIn("/vorschau", html)

    @patch.object(web_ui, "setze_eingang")
    @patch.object(web_ui, "lokalen_ordner_auswaehlen", return_value=r"C:\\Steuern")
    def test_ordner_kann_per_dialog_ausgewaehlt_werden(self, _dialog, setzen):
        setzen.return_value = Path(r"C:\\Steuern")
        antwort = self.client.post("/api/eingangsordner/auswaehlen", json={})
        self.assertEqual(200, antwort.status_code)
        setzen.assert_called_once_with(r"C:\\Steuern")

    @patch.object(web_ui.os, "startfile", create=True)
    @patch.object(web_ui, "aktueller_eingang", return_value=Path(r"C:\\Steuern"))
    def test_eingangsordner_kann_geoeffnet_werden(self, _eingang, startfile):
        antwort = self.client.post("/api/eingangsordner/oeffnen", json={})
        self.assertEqual(200, antwort.status_code)
        startfile.assert_called_once_with(str(Path(r"C:\\Steuern")))


if __name__ == "__main__":
    unittest.main()
