from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import ordner_ueberwacher
from ordner_ueberwacher import (
    automatische_vision_noetig,
    DateiStand,
    dokument_aktualisieren,
    dokument_nutzer_bestaetigen,
    dokumentuebersicht,
    erkannte_daten_uebernehmen,
    erkenne_dokumenttyp,
    erkenne_steuer_id,
    erkenne_nutzerzuordnung,
    extrahiere_wertvorschlaege,
    lies_ocr_text,
    pruefhinweise,
    persoenliche_steuerdaten,
    speichere_erkennung,
    steuer_id_automatisch_uebernehmen,
    vision_wertvorschlaege_uebernehmen,
    wertvorschlag_aktualisieren,
)


class DokumenterkennungTest(unittest.TestCase):
    def test_steuer_id_wird_nur_mit_kontext_und_gueltiger_pruefziffer_erkannt(self):
        self.assertEqual(
            "12345678903",
            erkenne_steuer_id("Identifikationsnummer: 12 345 678 903"),
        )
        self.assertIsNone(erkenne_steuer_id("Identifikationsnummer: 12 345 678 901"))
        self.assertIsNone(erkenne_steuer_id("Zahlungsreferenz 12345678903"))

    def test_erkannte_steuer_id_wird_bestaetigt_und_nicht_im_register_gespeichert(self):
        with tempfile.TemporaryDirectory() as temp:
            basis = Path(temp)
            bild = basis / "lohn.jpg"
            bild.write_bytes(b"bild")
            stand = bild.stat()
            register = basis / "register.json"
            nutzer = {"id": "n1", "name": "Test Person"}
            with (
                patch.object(ordner_ueberwacher, "DOKUMENTREGISTER", register),
                patch.object(ordner_ueberwacher.nutzerverwaltung, "dokumentregister_datei", return_value=None),
                patch.object(ordner_ueberwacher.nutzerverwaltung, "aktiver_nutzer", return_value=nutzer),
                patch.object(ordner_ueberwacher.nutzerverwaltung, "datenordner", return_value=basis),
                patch.object(ordner_ueberwacher, "lade_stammdaten", return_value={}),
                patch.object(ordner_ueberwacher, "speichere_stammdaten") as speichern,
            ):
                eintrag = speichere_erkennung(
                    bild,
                    DateiStand(stand.st_size, stand.st_mtime_ns),
                    "Elektronische Lohnsteuerbescheinigung",
                    "Dokumentinhalt",
                    "OCR lokal ausgefuehrt",
                    "2025",
                    nutzerzuordnung={
                        "status": "Erkannt",
                        "erkannter_nutzer_id": "n1",
                        "bestaetigt": False,
                    },
                )
                aktualisiert = steuer_id_automatisch_uebernehmen(
                    eintrag["id"],
                    "Steuer-ID: 12345678903",
                )
            speichern.assert_called_once_with(
                basis / ordner_ueberwacher.STAMMDATEN_DATEINAME,
                {"steuer_id": "12345678903"},
            )
            self.assertIn("erkannt, bestätigt", aktualisiert["steuer_id_status"])
            self.assertNotIn("12345678903", register.read_text(encoding="utf-8"))

    def test_steuer_id_einer_nicht_zugeordneten_person_wird_nicht_gespeichert(self):
        with tempfile.TemporaryDirectory() as temp:
            basis = Path(temp)
            bild = basis / "fremd.jpg"
            bild.write_bytes(b"bild")
            stand = bild.stat()
            register = basis / "register.json"
            with (
                patch.object(ordner_ueberwacher, "DOKUMENTREGISTER", register),
                patch.object(ordner_ueberwacher.nutzerverwaltung, "dokumentregister_datei", return_value=None),
                patch.object(
                    ordner_ueberwacher.nutzerverwaltung,
                    "aktiver_nutzer",
                    return_value={"id": "n1", "name": "Test Person"},
                ),
                patch.object(ordner_ueberwacher, "speichere_stammdaten") as speichern,
            ):
                eintrag = speichere_erkennung(
                    bild,
                    DateiStand(stand.st_size, stand.st_mtime_ns),
                    "Elektronische Lohnsteuerbescheinigung",
                    "Dokumentinhalt",
                    "OCR lokal ausgefuehrt",
                    "2025",
                    nutzerzuordnung={"status": "Anderer Nutzer erkannt", "bestaetigt": False},
                )
                aktualisiert = steuer_id_automatisch_uebernehmen(
                    eintrag["id"],
                    "Identifikationsnummer 12345678903",
                )
            speichern.assert_not_called()
            self.assertIn("noch nicht eindeutig", aktualisiert["steuer_id_status"])

    def test_schwache_bild_ocr_loest_automatische_vision_einmalig_aus(self):
        datei = Path("schlecht.jpg")
        self.assertTrue(
            automatische_vision_noetig(
                datei,
                "kaum lesbar",
                "OCR lokal ausgefuehrt",
                "Unbekannte Unterlage",
                [],
            )
        )
        self.assertFalse(
            automatische_vision_noetig(
                datei,
                "kaum lesbar",
                "OCR lokal ausgefuehrt",
                "Unbekannte Unterlage",
                [],
                {"vision_automatisch_versucht_am": "2026-09-12T10:00:00+02:00"},
            )
        )

    def test_gut_lesbares_erkanntes_bild_braucht_keine_vision(self):
        text = " ".join(f"dokumentwort{nummer}" for nummer in range(140))
        self.assertFalse(
            automatische_vision_noetig(
                Path("lesbar.jpg"),
                text,
                "OCR lokal ausgefuehrt",
                "Elektronische Lohnsteuerbescheinigung",
                [],
            )
        )

    def test_ocr_wiederholung_bewahrt_vision_typ_und_bestaetigten_wert(self):
        with tempfile.TemporaryDirectory() as temp:
            basis = Path(temp)
            bild = basis / "notiz.jpg"
            bild.write_bytes(b"bild")
            stand = bild.stat()
            register = basis / "register.json"
            kennung = ordner_ueberwacher.dokument_id(bild)
            register.write_text(
                json.dumps(
                    {
                        kennung: {
                            "id": kennung,
                            "dokumenttyp": "Notiz – Versicherungen",
                            "grundlage": "Lokale Bildprüfung (Vorschlag)",
                            "vision_status": "Automatisch geprüft.",
                            "vision_automatisch_versucht_am": "2026-09-12T10:00:00+02:00",
                            "wertvorschlaege": [
                                {
                                    "id": "wohnflaeche",
                                    "wert": "120 m²",
                                    "status": "Bestätigt",
                                }
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(ordner_ueberwacher, "DOKUMENTREGISTER", register),
                patch.object(ordner_ueberwacher.nutzerverwaltung, "dokumentregister_datei", return_value=None),
            ):
                eintrag = speichere_erkennung(
                    bild,
                    DateiStand(stand.st_size, stand.st_mtime_ns),
                    "Unbekannte Unterlage",
                    "Dateiname und Dokumentinhalt nicht eindeutig",
                    "OCR lokal ausgefuehrt",
                    "Nicht erkannt",
                    [],
                )
        self.assertEqual("Notiz – Versicherungen", eintrag["dokumenttyp"])
        self.assertEqual("Lokale Bildprüfung (Vorschlag)", eintrag["grundlage"])
        self.assertEqual("Bestätigt", eintrag["wertvorschlaege"][0]["status"])
        self.assertEqual("Automatisch geprüft.", eintrag["vision_status"])

    def test_vollstaendiger_nutzername_wird_auch_umgekehrt_erkannt(self):
        aktiv = {"id": "n1", "name": "Max Mustermann"}
        with (
            patch.object(ordner_ueberwacher.nutzerverwaltung, "aktiver_nutzer", return_value=aktiv),
            patch.object(ordner_ueberwacher.nutzerverwaltung, "nutzer_auflisten", return_value=[aktiv]),
        ):
            zuordnung = erkenne_nutzerzuordnung(
                "Elektronische Lohnsteuerbescheinigung\nName, Vorname: Mustermann, Max"
            )
        self.assertEqual("Erkannt", zuordnung["status"])
        self.assertEqual("Max Mustermann", zuordnung["erkannter_name"])

    def test_name_eines_anderen_nutzers_wird_als_abweichung_markiert(self):
        aktiv = {"id": "n1", "name": "Max Mustermann"}
        andere = {"id": "n2", "name": "Erika Beispiel"}
        with (
            patch.object(ordner_ueberwacher.nutzerverwaltung, "aktiver_nutzer", return_value=aktiv),
            patch.object(
                ordner_ueberwacher.nutzerverwaltung,
                "nutzer_auflisten",
                return_value=[aktiv, andere],
            ),
        ):
            zuordnung = erkenne_nutzerzuordnung("Steuerpflichtige Person: Erika Beispiel")
        self.assertEqual("Anderer Nutzer erkannt", zuordnung["status"])
        self.assertIn("Erika Beispiel", zuordnung["hinweis"])

    def test_nutzerzuordnung_kann_manuell_bestaetigt_werden(self):
        aktiv = {"id": "n1", "name": "Max Mustermann"}
        with tempfile.TemporaryDirectory() as temp:
            basis = Path(temp)
            datei = self._textdatei(basis, "beleg.txt", "Rechnung")
            stand = datei.stat()
            register = basis / "register.json"
            with (
                patch.object(ordner_ueberwacher, "DOKUMENTREGISTER", register),
                patch.object(ordner_ueberwacher.nutzerverwaltung, "aktiver_nutzer", return_value=aktiv),
                patch.object(ordner_ueberwacher.nutzerverwaltung, "dokumentregister_datei", return_value=None),
            ):
                eintrag = speichere_erkennung(
                    datei,
                    DateiStand(stand.st_size, stand.st_mtime_ns),
                    "Sonstige Rechnung",
                    "Dokumentinhalt",
                    "Text lokal eingelesen",
                    "2025",
                    nutzerzuordnung={"status": "Nicht erkannt", "bestaetigt": False},
                )
                bestaetigt = dokument_nutzer_bestaetigen(eintrag["id"])
        self.assertTrue(bestaetigt["nutzerzuordnung"]["bestaetigt"])
        self.assertEqual("Max Mustermann", bestaetigt["nutzerzuordnung"]["erkannter_name"])

    def test_unveraenderte_datei_muss_nicht_erneut_per_ocr_gelesen_werden(self):
        with tempfile.TemporaryDirectory() as temp:
            basis = Path(temp)
            datei = basis / "lohn.pdf"
            datei.write_bytes(b"beispiel")
            stat = datei.stat()
            stand = ordner_ueberwacher.DateiStand(stat.st_size, stat.st_mtime_ns)
            register = basis / "register.json"
            eintrag = {
                ordner_ueberwacher.dokument_id(datei): {
                    "groesse": stand.groesse,
                    "geaendert_ns": stand.geaendert_ns,
                    "dokumenttyp": "Elektronische Lohnsteuerbescheinigung",
                }
            }
            register.write_text(json.dumps(eintrag), encoding="utf-8")
            with patch.object(ordner_ueberwacher, "DOKUMENTREGISTER", register):
                self.assertTrue(ordner_ueberwacher.ist_unveraendert_registriert(datei, stand))
                geaendert = ordner_ueberwacher.DateiStand(stand.groesse + 1, stand.geaendert_ns)
                self.assertFalse(ordner_ueberwacher.ist_unveraendert_registriert(datei, geaendert))

    def test_erneute_erkennung_nutzt_manuell_bestaetigten_typ_fuer_werte(self):
        with tempfile.TemporaryDirectory() as temp:
            basis = Path(temp)
            datei = self._textdatei(basis, "alt.txt", "Wohnfläche 55 qm")
            stand = datei.stat()
            register = basis / "register.json"
            kennung = ordner_ueberwacher.dokument_id(datei)
            register.write_text(
                json.dumps(
                    {
                        kennung: {
                            "id": kennung,
                            "dateiname": datei.name,
                            "pfad": str(datei.resolve()),
                            "dokumenttyp": "Historische Grundstücks- und Gebäudedaten",
                            "steuerjahr": "Nicht erkannt",
                            "status": "Zu prüfen",
                            "manuell": True,
                        }
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(ordner_ueberwacher, "DOKUMENTREGISTER", register),
                patch.object(ordner_ueberwacher.nutzerverwaltung, "dokumentregister_datei", return_value=None),
                patch("builtins.print"),
            ):
                ordner_ueberwacher.ausgabe_neue_datei(
                    datei,
                    DateiStand(stand.st_size, stand.st_mtime_ns),
                )
                eintrag = json.loads(register.read_text(encoding="utf-8"))[kennung]
        self.assertEqual("Historische Grundstücks- und Gebäudedaten", eintrag["dokumenttyp"])
        self.assertEqual("55 m²", eintrag["wertvorschlaege"][0]["wert"])

    def _textdatei(self, ordner: str, name: str, inhalt: str) -> Path:
        datei = Path(ordner) / name
        datei.write_text(inhalt, encoding="utf-8")
        return datei

    def test_textdatei_wird_inhaltlich_lokal_gelesen(self):
        with tempfile.TemporaryDirectory() as temp:
            datei = self._textdatei(temp, "scan.txt", "Elektronische Lohnsteuerbescheinigung 2025")
            text, status = lies_ocr_text(datei)
            self.assertIn("Lohnsteuerbescheinigung", text)
            self.assertEqual("Text lokal eingelesen", status)

    def test_rentenbezugsmitteilung(self):
        with tempfile.TemporaryDirectory() as temp:
            datei = self._textdatei(temp, "dokument.txt", "Mitteilung zur Vorlage beim Finanzamt – Rentenbezug")
            self.assertEqual("Rentenbezugsmitteilung", erkenne_dokumenttyp(datei)[0])

    def test_insolvenzgeldbescheinigung(self):
        with tempfile.TemporaryDirectory() as temp:
            datei = self._textdatei(
                temp,
                "insolvenzgeld.txt",
                "Bescheinigung für Insolvenzgeld 2025 – Agentur für Arbeit",
            )
            dokumenttyp, _, _, steuerjahr = erkenne_dokumenttyp(datei)
            self.assertEqual("Insolvenzgeldbescheinigung", dokumenttyp)
            self.assertEqual("2025", steuerjahr)
            hinweise = pruefhinweise(dokumenttyp)
            self.assertTrue(any("Dreimonatszeitraum" in hinweis for hinweis in hinweise))
            self.assertTrue(any("Progressionsvorbehalt" in hinweis for hinweis in hinweise))

    def test_leistungsnachweis_mit_insolvenzgeld_ist_keine_arbeitslosengeldbescheinigung(self):
        with tempfile.TemporaryDirectory() as temp:
            datei = self._textdatei(
                temp,
                "leistungsnachweis.txt",
                "Leistungsnachweis der Agentur für Arbeit, Leistungsart Insolvenzgeld, Kalenderjahr 2024",
            )
            dokumenttyp, _, _, steuerjahr = erkenne_dokumenttyp(datei)
        self.assertEqual("Insolvenzgeldbescheinigung", dokumenttyp)
        self.assertEqual("2024", steuerjahr)

    def test_lohnsteuer_ueberschrift_schlaegt_beilaufiges_kurzarbeitergeld(self):
        with tempfile.TemporaryDirectory() as temp:
            datei = self._textdatei(
                temp,
                "beleg.txt",
                "Ausdruck der elektronischen Lohnsteuerbescheinigung 2025\nZeile Kurzarbeitergeld 0,00",
            )
            dokumenttyp, _, _, steuerjahr = erkenne_dokumenttyp(datei)
        self.assertEqual("Elektronische Lohnsteuerbescheinigung", dokumenttyp)
        self.assertEqual("2025", steuerjahr)

    def test_ocr_getrennte_lohnsteuer_ueberschrift_schlaegt_kurzarbeitergeld(self):
        with tempfile.TemporaryDirectory() as temp:
            datei = self._textdatei(
                temp,
                "foto.txt",
                "Lohnste der elektronischen\nuerbescheinigung für 2025\n"
                "15a Saison-Kurzarbeitergeld",
            )
            dokumenttyp, _, _, steuerjahr = erkenne_dokumenttyp(datei)
        self.assertEqual("Elektronische Lohnsteuerbescheinigung", dokumenttyp)
        self.assertEqual("2025", steuerjahr)

    def test_anlage_vorsorgeaufwand_schlaegt_beilaeufige_lohnsteuerreferenz(self):
        with tempfile.TemporaryDirectory() as temp:
            datei = self._textdatei(
                temp,
                "vorsorge.txt",
                "2010AnlVor241 Angaben zu Vorsorgeaufwendungen\n"
                "Beiträge zur Altersvorsorge laut Nr. 23 der Lohnsteuerbescheinigung",
            )
            dokumenttyp, _, _, steuerjahr = erkenne_dokumenttyp(datei)
        self.assertEqual("Anlage Vorsorgeaufwand", dokumenttyp)
        self.assertEqual("2010", steuerjahr)

    def test_anlage_vorsorgeaufwand_laesst_fehlendes_jahr_im_bildkopf_nachlesen(self):
        with tempfile.TemporaryDirectory() as temp:
            datei = Path(temp) / "vorsorge.jpg"
            datei.write_bytes(b"testbild")
            with (
                patch.object(
                    ordner_ueberwacher,
                    "lies_ocr_text",
                    return_value=(
                        "Vorsorgeaufwendungen Private Kranken- und Pflegeversicherung "
                        "laut Lohnsteuerbescheinigung",
                        "OCR lokal ausgefuehrt",
                    ),
                ),
                patch.object(
                    ordner_ueberwacher,
                    "_jahr_aus_bildkopf",
                    return_value="2010",
                ) as bildkopf,
            ):
                dokumenttyp, _, _, steuerjahr = erkenne_dokumenttyp(datei)
        self.assertEqual("Anlage Vorsorgeaufwand", dokumenttyp)
        self.assertEqual("2010", steuerjahr)
        bildkopf.assert_called_once_with(datei)

    def test_historische_anlage_v_wird_nicht_dem_steuerjahr_2010_zugeordnet(self):
        with tempfile.TemporaryDirectory() as temp:
            datei = self._textdatei(
                temp,
                "alte_unterlage.txt",
                "Einkommensteuer 2010 Anlage V Anschaffungskosten Haus Anteil Grund und Boden",
            )
            dokumenttyp, _, _, steuerjahr = erkenne_dokumenttyp(datei)
        self.assertEqual("Historische Grundstücks- und Gebäudedaten", dokumenttyp)
        self.assertEqual("Nicht erkannt", steuerjahr)

    def test_historischer_einkommensteuer_hauptvordruck_wird_getrennt_erkannt(self):
        with tempfile.TemporaryDirectory() as temp:
            datei = self._textdatei(
                temp,
                "formular.txt",
                "2010ESt1A011 Erklärung zur Festsetzung der Einkommensteuer "
                "Allgemeine Angaben steuerpflichtige Person",
            )
            dokumenttyp, _, _, steuerjahr = erkenne_dokumenttyp(datei)
        self.assertEqual("Historische Einkommensteuererklärung", dokumenttyp)
        self.assertEqual("Nicht erkannt", steuerjahr)

    def test_wohnraummietvertrag_wird_trotz_zusatztext_erkannt(self):
        with tempfile.TemporaryDirectory() as temp:
            datei = self._textdatei(
                temp,
                "foto.txt",
                "Wohnraummietvertrag Vermieter vermietet dem Mieter eine Wohnung mit 55 m2",
            )
            dokumenttyp, _, _, _ = erkenne_dokumenttyp(datei)
        self.assertEqual("Mietvertrag", dokumenttyp)

    def test_handschriftliche_steuer_notizen_werden_vorsichtig_unterschieden(self):
        with tempfile.TemporaryDirectory() as temp:
            versicherung = self._textdatei(
                temp, "versicherung.txt", "Haftpflicht Versicherung Beitrag 53,84 Euro monatlich"
            )
            insolvenzgeld = self._textdatei(
                temp, "leistung.txt", "Insolvenzgeld 01.11.24 bis 31.12.24"
            )
            vermietung = self._textdatei(
                temp,
                "haus.txt",
                "Anlage V Vermietung und Verpachtung Anschaffungskosten 2% linear abschreibbar",
            )
            self.assertEqual("Notiz – Versicherungen", erkenne_dokumenttyp(versicherung)[0])
            self.assertEqual("Notiz – Insolvenzgeld", erkenne_dokumenttyp(insolvenzgeld)[0])
            self.assertEqual("Notiz – Vermietung", erkenne_dokumenttyp(vermietung)[0])

    def test_darlehensbescheinigung_nimmt_den_bescheinigten_zeitraum(self):
        with tempfile.TemporaryDirectory() as temp:
            datei = self._textdatei(
                temp,
                "brief.txt",
                "Saldenmitteilung und Zins- und Kostenbescheinigung vom 15.01.2026 "
                "für Zeitraum 01.01.2025 bis 31.12.2025",
            )
            dokumenttyp, _, _, steuerjahr = erkenne_dokumenttyp(datei)
        self.assertEqual("Darlehenszinsbescheinigung", dokumenttyp)
        self.assertEqual("2025", steuerjahr)

    def test_schornsteinfegerrechnung_und_gesamtbetrag(self):
        with tempfile.TemporaryDirectory() as temp:
            datei = self._textdatei(
                temp,
                "beleg.txt",
                "Rechnung Schornsteinfeger\nRechnungsdatum 12.03.2025\nGesamt EUR 215,54",
            )
            dokumenttyp, _, _, steuerjahr, text = erkenne_dokumenttyp(datei, mit_text=True)
            werte = extrahiere_wertvorschlaege(dokumenttyp, text)
        self.assertEqual("Schornsteinfegerrechnung", dokumenttyp)
        self.assertEqual("2025", steuerjahr)
        self.assertEqual("215,54 €", {wert["id"]: wert["wert"] for wert in werte}["rechnungsbetrag"])

    def test_gebaeudestammdaten_bleiben_unbestaetigte_vorschlaege(self):
        text = "Grundstücksfläche 780 qm\nWohnfläche 261,5 m2\nBaujahr 1960\nWohneinheiten 3"
        werte = extrahiere_wertvorschlaege("Gebäudeversicherungsunterlage", text)
        nach_id = {wert["id"]: wert for wert in werte}
        self.assertEqual("780 m²", nach_id["grundstuecksflaeche"]["wert"])
        self.assertEqual("261,5 m²", nach_id["wohnflaeche"]["wert"])
        self.assertEqual("1960", nach_id["baujahr"]["wert"])
        self.assertEqual("3", nach_id["wohneinheiten"]["wert"])
        self.assertTrue(all(wert["status"] == "Zu prüfen" for wert in werte))

    def test_historische_anschaffungswerte_werden_nur_vorgeschlagen(self):
        text = "Anschaffungskosten 200.000,00\nAnteil Grund und Boden 50.000,00\nGebäudewert 150.000,00"
        werte = extrahiere_wertvorschlaege("Historische Grundstücks- und Gebäudedaten", text)
        nach_id = {wert["id"]: wert for wert in werte}
        self.assertEqual("200.000,00 €", nach_id["anschaffungskosten"]["wert"])
        self.assertEqual("50.000,00 €", nach_id["grund_und_boden"]["wert"])
        self.assertEqual("150.000,00 €", nach_id["gebaeudewert"]["wert"])
        self.assertTrue(all(wert["status"] == "Zu prüfen" for wert in werte))

    def test_grundsteuerbescheide_werden_unterschieden(self):
        with tempfile.TemporaryDirectory() as temp:
            wert = self._textdatei(temp, "wert.txt", "Bescheid über den Grundsteuerwert")
            mess = self._textdatei(temp, "mess.txt", "Bescheid über den Grundsteuermessbetrag")
            kommune = self._textdatei(temp, "kommune.txt", "Grundsteuerbescheid 2026 Hebesatz Grundsteuer")
            self.assertEqual("Grundsteuerwertbescheid", erkenne_dokumenttyp(wert)[0])
            self.assertEqual("Grundsteuermessbescheid", erkenne_dokumenttyp(mess)[0])
            self.assertEqual("Kommunaler Grundsteuerbescheid", erkenne_dokumenttyp(kommune)[0])

    def test_kapitalertrag_und_kinderbetreuung(self):
        with tempfile.TemporaryDirectory() as temp:
            kapital = self._textdatei(temp, "bank.txt", "Jahressteuerbescheinigung Kapitalertragsteuer")
            kind = self._textdatei(temp, "kita.txt", "Abrechnung Kinderbetreuung Kindertagesstätte")
            self.assertEqual("Kapitalertragsteuerbescheinigung", erkenne_dokumenttyp(kapital)[0])
            self.assertEqual("Kinderbetreuungskosten", erkenne_dokumenttyp(kind)[0])

    def test_unbekanntes_dokument_bleibt_unbekannt(self):
        with tempfile.TemporaryDirectory() as temp:
            datei = self._textdatei(temp, "notiz.txt", "Private Einkaufsliste ohne Steuerbezug")
            self.assertEqual("Unbekannte Unterlage", erkenne_dokumenttyp(datei)[0])

    def test_spezifische_pruefhinweise(self):
        hinweise = pruefhinweise("Kommunaler Grundsteuerbescheid")
        self.assertTrue(any("Hebesatz" in hinweis for hinweis in hinweise))

    def test_lohnsteuer_pruefhinweis_nennt_steuerklasse(self):
        hinweise = pruefhinweise("Elektronische Lohnsteuerbescheinigung")
        self.assertTrue(any("Steuerklasse" in hinweis for hinweis in hinweise))

    def test_mehrseitiges_pdf_wird_vollstaendig_gelesen(self):
        import pymupdf

        with tempfile.TemporaryDirectory() as temp:
            datei = Path(temp) / "mehrseitig.pdf"
            dokument = pymupdf.open()
            for nummer in range(4):
                seite = dokument.new_page()
                text = "Allgemeine Unterlagenseite mit ausreichend Text zur direkten Auswertung."
                if nummer == 3:
                    text = "Rentenbezugsmitteilung zur Vorlage beim Finanzamt für das aktuelle Steuerjahr."
                seite.insert_text((72, 72), text)
            dokument.save(datei)
            dokument.close()

            text, status = lies_ocr_text(datei)
            self.assertIn("Rentenbezugsmitteilung", text)
            self.assertIn("vollständig ausgewertet (4 Seite(n))", status)
            self.assertEqual("Rentenbezugsmitteilung", erkenne_dokumenttyp(datei)[0])

    def test_pdf_sicherheitsgrenze_wird_gemeldet(self):
        import pymupdf

        with tempfile.TemporaryDirectory() as temp:
            datei = Path(temp) / "lang.pdf"
            dokument = pymupdf.open()
            for nummer in range(3):
                seite = dokument.new_page()
                seite.insert_text((72, 72), f"Ausreichend langer Text auf Dokumentseite {nummer + 1} zur Prüfung.")
            dokument.save(datei)
            dokument.close()

            with patch.object(ordner_ueberwacher, "PDF_SEITEN_LIMIT", 2):
                text, status = lies_ocr_text(datei)
            self.assertNotIn("Dokumentseite 3", text)
            self.assertIn("Sicherheitsgrenze von 2 Seiten", status)
            self.assertIn("Dokument hat 3 Seiten", status)

    def test_erkennung_wird_als_metadaten_registriert(self):
        with tempfile.TemporaryDirectory() as temp:
            basis = Path(temp)
            datei = self._textdatei(basis, "lohnsteuer_2025.txt", "Elektronische Lohnsteuerbescheinigung 2025")
            stand = datei.stat()
            register = basis / "register.json"
            with (
                patch.object(ordner_ueberwacher, "DOKUMENTREGISTER", register),
                patch.object(ordner_ueberwacher, "aktueller_eingang", return_value=basis),
            ):
                typ, grundlage, ocr, jahr = erkenne_dokumenttyp(datei)
                eintrag = speichere_erkennung(
                    datei,
                    DateiStand(stand.st_size, stand.st_mtime_ns),
                    typ,
                    grundlage,
                    ocr,
                    jahr,
                )
                uebersicht = dokumentuebersicht()
            self.assertEqual("Elektronische Lohnsteuerbescheinigung", eintrag["dokumenttyp"])
            self.assertEqual("2025", eintrag["steuerjahr"])
            self.assertNotIn("Elektronische Lohnsteuerbescheinigung 2025", register.read_text(encoding="utf-8"))
            self.assertEqual(1, len(uebersicht))

    def test_manuelle_korrektur_wird_gespeichert(self):
        with tempfile.TemporaryDirectory() as temp:
            basis = Path(temp)
            datei = self._textdatei(basis, "unbekannt.txt", "Nicht eindeutig")
            stand = datei.stat()
            register = basis / "register.json"
            with patch.object(ordner_ueberwacher, "DOKUMENTREGISTER", register):
                eintrag = speichere_erkennung(
                    datei,
                    DateiStand(stand.st_size, stand.st_mtime_ns),
                    "Unbekannte Unterlage",
                    "Nicht eindeutig",
                    "Text lokal eingelesen",
                    "Nicht erkannt",
                )
                korrigiert = dokument_aktualisieren(
                    eintrag["id"],
                    "Geprüft",
                    "Spendenbescheinigung",
                    "2025",
                )
            self.assertEqual("Spendenbescheinigung", korrigiert["dokumenttyp"])
            self.assertEqual("2025", korrigiert["steuerjahr"])
            self.assertEqual("Geprüft", korrigiert["status"])
            self.assertTrue(korrigiert["manuell"])

    def test_lokale_bildpruefung_uebernimmt_klar_erkannten_typ(self):
        with tempfile.TemporaryDirectory() as temp:
            basis = Path(temp)
            bild = basis / "notiz.jpg"
            bild.write_bytes(b"bild")
            stand = bild.stat()
            register = basis / "register.json"
            with (
                patch.object(ordner_ueberwacher, "DOKUMENTREGISTER", register),
                patch.object(ordner_ueberwacher.nutzerverwaltung, "dokumentregister_datei", return_value=None),
            ):
                eintrag = speichere_erkennung(
                    bild,
                    DateiStand(stand.st_size, stand.st_mtime_ns),
                    "Unbekannte Unterlage",
                    "Nicht eindeutig",
                    "OCR lokal ausgefuehrt",
                    "Nicht erkannt",
                )
                aktualisiert = vision_wertvorschlaege_uebernehmen(
                    eintrag["id"],
                    "Dokumentart: Notiz – Versicherungen\nRechnungsbetrag: 53,84 Euro",
                )
            self.assertEqual("Notiz – Versicherungen", aktualisiert["dokumenttyp"])
            self.assertEqual("Lokale Bildprüfung", aktualisiert["grundlage"])
            self.assertEqual("Geprüft", aktualisiert["status"])
            self.assertFalse(aktualisiert["manuell"])
            self.assertIn("nicht als amtlichen Nachweis", " ".join(aktualisiert["pruefhinweise"]))

    def test_lohnsteuerwerte_werden_nur_als_vorschlag_extrahiert(self):
        text = (
            "Bruttoarbeitslohn 45.000,00\n"
            "Einbehaltene Lohnsteuer 6.500,00\n"
            "Solidaritätszuschlag 120,00\n"
        )
        werte = extrahiere_wertvorschlaege("Elektronische Lohnsteuerbescheinigung", text)
        self.assertEqual(
            {"bruttoarbeitslohn": "45.000,00 €", "lohnsteuer": "6.500,00 €", "solidaritaetszuschlag": "120,00 €"},
            {wert["id"]: wert["wert"] for wert in werte},
        )
        self.assertTrue(all(wert["status"] == "Zu prüfen" for wert in werte))

    def test_wertvorschlag_kann_bestaetigt_werden(self):
        with tempfile.TemporaryDirectory() as temp:
            basis = Path(temp)
            datei = self._textdatei(basis, "lohn.txt", "Elektronische Lohnsteuerbescheinigung")
            stand = datei.stat()
            register = basis / "register.json"
            werte = [{"id": "lohnsteuer", "bezeichnung": "Lohnsteuer", "wert": "1.000,00 €", "status": "Zu prüfen"}]
            with patch.object(ordner_ueberwacher, "DOKUMENTREGISTER", register):
                eintrag = speichere_erkennung(
                    datei,
                    DateiStand(stand.st_size, stand.st_mtime_ns),
                    "Elektronische Lohnsteuerbescheinigung",
                    "Dokumentinhalt",
                    "Text lokal eingelesen",
                    "2025",
                    werte,
                )
                aktualisiert = wertvorschlag_aktualisieren(eintrag["id"], "lohnsteuer", "Bestätigt")
            self.assertEqual("Bestätigt", aktualisiert["wertvorschlaege"][0]["status"])

    def test_vision_ueberschreibt_keinen_bestaetigten_gebaeudewert(self):
        with tempfile.TemporaryDirectory() as temp:
            basis = Path(temp)
            datei = basis / "haus.jpg"
            datei.write_bytes(b"bild")
            stand = datei.stat()
            register = basis / "register.json"
            werte = [{
                "id": "wohnflaeche", "bezeichnung": "Wohnfläche",
                "wert": "120 m²", "art": "Gebäudestammdatum", "status": "Bestätigt",
            }]
            with patch.object(ordner_ueberwacher, "DOKUMENTREGISTER", register):
                eintrag = speichere_erkennung(
                    datei, DateiStand(stand.st_size, stand.st_mtime_ns),
                    "Gebäudeversicherungsunterlage", "Dokumentinhalt",
                    "Bild lokal geprüft", "2025", werte,
                )
                aktualisiert = vision_wertvorschlaege_uebernehmen(
                    eintrag["id"], "Wohnfläche: 180 m2\nBaujahr: 1960"
                )
        nach_id = {wert["id"]: wert for wert in aktualisiert["wertvorschlaege"]}
        self.assertEqual("120 m²", nach_id["wohnflaeche"]["wert"])
        self.assertEqual("Bestätigt", nach_id["wohnflaeche"]["status"])
        self.assertEqual("1960", nach_id["baujahr"]["wert"])
        self.assertEqual("Bestätigt", nach_id["baujahr"]["status"])

    def test_erkannte_daten_werden_automatisch_uebernommen(self):
        with tempfile.TemporaryDirectory() as temp:
            basis = Path(temp)
            datei = self._textdatei(basis, "lohn.txt", "Lohnsteuerbescheinigung")
            stand = datei.stat()
            register = basis / "register.json"
            with (
                patch.object(ordner_ueberwacher, "DOKUMENTREGISTER", register),
                patch.object(ordner_ueberwacher.nutzerverwaltung, "dokumentregister_datei", return_value=None),
            ):
                eintrag = speichere_erkennung(
                    datei,
                    DateiStand(stand.st_size, stand.st_mtime_ns),
                    "Elektronische Lohnsteuerbescheinigung",
                    "Dokumentinhalt",
                    "Text lokal eingelesen",
                    "2025",
                    [{"id": "lohnsteuer", "bezeichnung": "Lohnsteuer", "wert": "1.000,00 €", "status": "Zu prüfen"}],
                    {"status": "Erkannt", "bestaetigt": False},
                )
            self.assertEqual("Geprüft", eintrag["status"])
            self.assertEqual("Bestätigt", eintrag["wertvorschlaege"][0]["status"])
            self.assertEqual("Bestätigt", eintrag["nutzerzuordnung"]["status"])
            self.assertTrue(eintrag["nutzerzuordnung"]["bestaetigt"])

    def test_nicht_erkanntes_dokument_bleibt_zur_pruefung_offen(self):
        with tempfile.TemporaryDirectory() as temp:
            basis = Path(temp)
            datei = self._textdatei(basis, "unklar.txt", "Nicht lesbar")
            stand = datei.stat()
            register = basis / "register.json"
            with (
                patch.object(ordner_ueberwacher, "DOKUMENTREGISTER", register),
                patch.object(ordner_ueberwacher.nutzerverwaltung, "dokumentregister_datei", return_value=None),
            ):
                eintrag = speichere_erkennung(
                    datei,
                    DateiStand(stand.st_size, stand.st_mtime_ns),
                    "Unbekannte Unterlage",
                    "Nicht eindeutig",
                    "Nicht erkannt",
                    "Nicht erkannt",
                )
            self.assertEqual("Unklar", eintrag["status"])

    def test_bestehende_erkannte_daten_werden_nachtraeglich_uebernommen(self):
        with tempfile.TemporaryDirectory() as temp:
            register = Path(temp) / "register.json"
            register.write_text(
                json.dumps(
                    {
                        "bekannt": {
                            "dokumenttyp": "Sonstige Rechnung",
                            "status": "Zu prüfen",
                            "wertvorschlaege": [
                                {"id": "betrag", "wert": "10,00 €", "status": "Zu prüfen"},
                                {"id": "falsch", "wert": "20,00 €", "status": "Verworfen"},
                            ],
                            "nutzerzuordnung": {"status": "Erkannt", "bestaetigt": False},
                        },
                        "unbekannt": {
                            "dokumenttyp": "Unbekannte Unterlage",
                            "status": "Zu prüfen",
                            "wertvorschlaege": [],
                        },
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with (
                patch.object(ordner_ueberwacher, "DOKUMENTREGISTER", register),
                patch.object(ordner_ueberwacher.nutzerverwaltung, "dokumentregister_datei", return_value=None),
            ):
                zaehler = erkannte_daten_uebernehmen()
            daten = json.loads(register.read_text(encoding="utf-8"))
            self.assertEqual({"dokumente": 2, "werte": 1, "zuordnungen": 1}, zaehler)
            self.assertEqual("Geprüft", daten["bekannt"]["status"])
            self.assertEqual("Bestätigt", daten["bekannt"]["wertvorschlaege"][0]["status"])
            self.assertEqual("Verworfen", daten["bekannt"]["wertvorschlaege"][1]["status"])
            self.assertEqual("Bestätigt", daten["bekannt"]["nutzerzuordnung"]["status"])
            self.assertEqual("Unklar", daten["unbekannt"]["status"])

    def test_persoenliche_lohnsteuermerkmale_werden_vorgeschlagen(self):
        text = (
            "Steuerklasse / Faktor: 4 / 0,9876\n"
            "Zahl der Kinderfreibeträge: 1,0\n"
            "Kirchensteuermerkmal: EV\n"
            "Bescheinigungszeitraum: 01.01.2025 bis 31.12.2025\n"
            "Großbuchstaben: U, S\n"
        )
        werte = extrahiere_wertvorschlaege("Elektronische Lohnsteuerbescheinigung", text)
        merkmale = {wert["id"]: wert["wert"] for wert in werte if wert.get("art") == "Merkmal"}
        self.assertEqual("4", merkmale["steuerklasse"])
        self.assertEqual("0,9876", merkmale["faktor"])
        self.assertEqual("1,0", merkmale["kinderfreibetrag"])
        self.assertEqual("EV", merkmale["kirchensteuermerkmal"])
        self.assertEqual("01.01.2025 BIS 31.12.2025", merkmale["beschaeftigungszeitraum"])
        self.assertEqual("U, S", merkmale["grossbuchstaben"])

    def test_ocr_mehrzeile_erkennt_steuerklasse_und_ignoriert_fremde_tabellenziffer(self):
        text = (
            "Steuerklasse / Faktor\n"
            "1\n\n"
            "1: Bescheinigungszeitraum |01.01.-31.12.2025\n"
            "Zahl der Kinderfreibeträge 5]\n"
            "0,0 125.\n"
        )
        werte = extrahiere_wertvorschlaege("Elektronische Lohnsteuerbescheinigung", text)
        merkmale = {wert["id"]: wert["wert"] for wert in werte if wert.get("art") == "Merkmal"}
        self.assertEqual("1", merkmale["steuerklasse"])
        self.assertEqual("0,0", merkmale["kinderfreibetrag"])
        self.assertEqual(
            "01.01.2025 BIS 31.12.2025",
            merkmale["beschaeftigungszeitraum"],
        )

    @patch.object(
        ordner_ueberwacher,
        "_betragsvorschlaege_aus_bild",
        return_value=[
            {
                "id": "krankenversicherung",
                "bezeichnung": "Arbeitnehmerbeitrag Krankenversicherung",
                "wert": "200,00 €",
                "art": "Betrag",
                "status": "Zu prüfen",
                "grundlage": "Getrennte lokale Tabellen-OCR",
            }
        ],
    )
    def test_bildtabellen_ocr_ergaenzt_nur_noch_nicht_gelesene_betraege(self, bild_ocr):
        werte = extrahiere_wertvorschlaege(
            "Elektronische Lohnsteuerbescheinigung",
            "Bruttoarbeitslohn 0,00",
            Path("foto.jpg"),
        )
        nach_id = {wert["id"]: wert for wert in werte}
        self.assertEqual("0,00 €", nach_id["bruttoarbeitslohn"]["wert"])
        self.assertEqual("200,00 €", nach_id["krankenversicherung"]["wert"])
        self.assertEqual("Getrennte lokale Tabellen-OCR", nach_id["krankenversicherung"]["grundlage"])
        bild_ocr.assert_called_once_with(Path("foto.jpg"))

    def test_dokumentuebersicht_blendet_doppelten_registereintrag_desselben_belegs_aus(self):
        with tempfile.TemporaryDirectory() as temp:
            basis = Path(temp)
            datei = self._textdatei(basis, "lohn.txt", "Elektronische Lohnsteuerbescheinigung")
            stand = datei.stat()
            register = basis / "register.json"
            gemeinsam = {
                "dateiname": datei.name,
                "pfad": str(datei.resolve()),
                "dokumenttyp": "Elektronische Lohnsteuerbescheinigung",
                "steuerjahr": "2025",
                "groesse": stand.st_size,
                "geaendert_ns": stand.st_mtime_ns,
            }
            register.write_text(
                json.dumps(
                    {
                        "alt": {**gemeinsam, "id": "alt", "erkannt_am": "2026-01-01T00:00:00+01:00"},
                        "neu": {
                            **gemeinsam,
                            "id": "neu",
                            "erkannt_am": "2026-01-02T00:00:00+01:00",
                            "nutzerzuordnung": {"status": "Erkannt"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(ordner_ueberwacher, "DOKUMENTREGISTER", register),
                patch.object(ordner_ueberwacher, "aktueller_eingang", return_value=basis),
                patch.object(ordner_ueberwacher.nutzerverwaltung, "dokumentregister_datei", return_value=None),
            ):
                uebersicht = dokumentuebersicht()
        self.assertEqual(1, len(uebersicht))
        self.assertEqual("neu", uebersicht[0]["id"])

    def test_persoenliche_daten_werden_nach_steuerjahr_gefiltert(self):
        with tempfile.TemporaryDirectory() as temp:
            basis = Path(temp)
            register = basis / "register.json"
            datei = self._textdatei(basis, "lohn-2025.txt", "Elektronische Lohnsteuerbescheinigung")
            stand = datei.stat()
            werte = [{"id": "steuerklasse", "bezeichnung": "Steuerklasse", "wert": "1", "art": "Merkmal", "status": "Zu prüfen"}]
            with (
                patch.object(ordner_ueberwacher, "DOKUMENTREGISTER", register),
                patch.object(ordner_ueberwacher, "aktueller_eingang", return_value=basis),
            ):
                speichere_erkennung(
                    datei,
                    DateiStand(stand.st_size, stand.st_mtime_ns),
                    "Elektronische Lohnsteuerbescheinigung",
                    "Dokumentinhalt",
                    "Text lokal eingelesen",
                    "2025",
                    werte,
                )
                passend = persoenliche_steuerdaten("2025")
                unpassend = persoenliche_steuerdaten("2024")
            self.assertEqual(1, len(passend))
            self.assertEqual("Steuerklasse", passend[0]["bezeichnung"])
            self.assertEqual([], unpassend)

    def test_notizangaben_bleiben_erhalten_und_werden_nicht_zu_steuerdaten(self):
        with tempfile.TemporaryDirectory() as temp:
            basis = Path(temp)
            register = basis / "register.json"
            datei = self._textdatei(basis, "notiz.txt", "Insolvenzgeld 01.11.2024 bis 31.12.2024")
            stand = datei.stat()
            with (
                patch.object(ordner_ueberwacher, "DOKUMENTREGISTER", register),
                patch.object(ordner_ueberwacher, "aktueller_eingang", return_value=basis),
                patch.object(ordner_ueberwacher.nutzerverwaltung, "dokumentregister_datei", return_value=None),
            ):
                eintrag = speichere_erkennung(
                    datei,
                    DateiStand(stand.st_size, stand.st_mtime_ns),
                    "Notiz – Insolvenzgeld",
                    "Dokumentinhalt",
                    "Text lokal eingelesen",
                    "2024",
                    [],
                )
                daten = json.loads(register.read_text(encoding="utf-8"))
                daten[eintrag["id"]]["notiz_angaben"] = [
                    {
                        "bezeichnung": "Steuerklasse nur als Sicherheitstest",
                        "wert": "1",
                        "status": "Bestätigt",
                        "verwendung": "ELSTER",
                    }
                ]
                daten[eintrag["id"]]["notiz_geprueft_am"] = "2026-09-12"
                register.write_text(json.dumps(daten), encoding="utf-8")
                erneut = speichere_erkennung(
                    datei,
                    DateiStand(stand.st_size, stand.st_mtime_ns),
                    "Notiz – Insolvenzgeld",
                    "Dokumentinhalt",
                    "Text lokal eingelesen",
                    "2024",
                    [],
                )
                steuerdaten = persoenliche_steuerdaten("2024")
        self.assertEqual("Aus Notiz übernommen", erneut["notiz_angaben"][0]["status"])
        self.assertEqual(
            "Nur Information – Originalnachweis erforderlich",
            erneut["notiz_angaben"][0]["verwendung"],
        )
        self.assertEqual("2026-09-12", erneut["notiz_geprueft_am"])
        self.assertEqual([], steuerdaten)


if __name__ == "__main__":
    unittest.main()
