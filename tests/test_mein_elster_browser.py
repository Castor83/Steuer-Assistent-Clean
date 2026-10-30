import json
from pathlib import Path
import sys
from time import perf_counter

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from mein_elster_browser import (
    erstelle_aktionsplan,
    erstelle_sicherheitskontext,
    fuelle_aktionsplan,
    gruppiere_aktionsplan,
    lade_browser_mapping,
    lade_eingabehilfe,
    pruefe_aktionsplan_vor_lauf,
    pruefe_entwurfkontext,
    pruefe_portalkontext,
    pruefe_versionsschranke,
)


def _eingabehilfe(**aenderungen):
    daten = {
        "format": "steuer-assistent-elster-eingabehilfe/v1",
        "steuerjahr": "2025",
        "versandfaehig": False,
        "felder": [
            {"lokale_feld_id": "arbeitsmittel", "wert": "250,00", "quelle": "Beleg"},
            {"lokale_feld_id": "bruttoarbeitslohn", "wert": "40000", "quelle": "LStB"},
            {"lokale_feld_id": "profil_name", "wert": "Max Beispiel", "quelle": "Profil"},
        ],
    }
    daten.update(aenderungen)
    return daten


def _oeffne_elster_testentwurf(seite, formular_html: str) -> None:
    seite.route(
        "https://www.elster.de/**",
        lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body=f"<main>Einkommensteuer 2025 – Entwurf{formular_html}</main>",
        ),
    )
    seite.goto("https://www.elster.de/eportal/interpreter/eingabe")


def _browser_aktion(feld_id: str, wert: str, **aenderungen) -> dict:
    mapping = lade_browser_mapping()
    regel = mapping["felder"][feld_id]
    block = next(
        block
        for block in mapping["abschnittsbloecke"]
        if feld_id in block["felder"]
    )
    aktion = {
        "feld_id": feld_id,
        "status": "bereit",
        "modus": regel["modus"],
        "vergleich": regel["vergleich"],
        "wert": wert,
        "labels": regel["labels"],
        "anlage": "Testanlage",
        "abschnitt": block["titel"],
        "block_id": block["id"],
        "block_titel": block["titel"],
    }
    aktion.update(aenderungen)
    return aktion


def test_browser_mapping_ist_auf_est_2025_und_sichere_modi_begrenzt():
    mapping = lade_browser_mapping()

    assert mapping["steuerjahr"] == "2025"
    assert mapping["layout_vertrag"]["version"] == "mein-elster-est2025-layout/v1"
    blockfelder = [
        feld_id
        for block in mapping["abschnittsbloecke"]
        for feld_id in block["felder"]
    ]
    assert len(blockfelder) == len(set(blockfelder))
    assert set(blockfelder) == set(mapping["felder"])
    assert {regel["modus"] for regel in mapping["felder"].values()} <= {
        "ausfuellen", "abgleich_edaten"
    }


def test_eingabehilfe_lehnt_versandfaehige_datei_ab(tmp_path):
    pfad = tmp_path / "eingabe.json"
    pfad.write_text(json.dumps(_eingabehilfe(versandfaehig=True)), encoding="utf-8")

    with pytest.raises(ValueError, match="versandfähig"):
        lade_eingabehilfe(pfad)


def test_aktionsplan_füllt_nur_sicher_zugeordnete_werte():
    plan = erstelle_aktionsplan(_eingabehilfe())
    status = {aktion["feld_id"]: aktion["status"] for aktion in plan}

    assert status["arbeitsmittel"] == "bereit"
    assert status["bruttoarbeitslohn"] == "nur_edaten_abgleich"
    assert status["profil_name"] == "offen_keine_eindeutige_zuordnung"
    assert any("profil_name" in fehler for fehler in pruefe_aktionsplan_vor_lauf(plan))


def test_edaten_benoetigen_explizite_freigabe():
    plan = erstelle_aktionsplan(_eingabehilfe(), edaten_ueberschreiben=True)
    brutto = next(aktion for aktion in plan if aktion["feld_id"] == "bruttoarbeitslohn")

    assert brutto["status"] == "bereit"


def test_portalkontext_verlangt_https_elster_und_est_2025():
    assert pruefe_portalkontext(
        "https://www.elster.de/eportal/interpreter/eingabe",
        "Einkommensteuererklärung 2025",
    ) == []
    assert pruefe_portalkontext(
        "https://beispiel.invalid/eportal",
        "Einkommensteuererklärung 2025",
    )
    assert pruefe_portalkontext(
        "https://www.elster.de/eportal/interpreter/eingabe",
        "Einkommensteuererklärung 2024",
    )


def test_entwurfkontext_blockiert_bereits_uebermittelte_erklaerung():
    assert pruefe_entwurfkontext(
        "https://www.elster.de/eportal/interpreter/eingabe",
        "Einkommensteuererklärung 2025 – Entwurf",
    ) == []
    fehler = pruefe_entwurfkontext(
        "https://www.elster.de/eportal/interpreter/eingabe",
        "Einkommensteuererklärung 2025 – Entwurf – erfolgreich übermittelt",
    )
    assert any("bereits übermittelt" in eintrag for eintrag in fehler)


def test_aktionsplan_wird_stabil_nach_logischem_block_gruppiert():
    plan = erstelle_aktionsplan(_eingabehilfe())
    gruppen = gruppiere_aktionsplan(plan)

    assert [gruppe["block_id"] for gruppe in gruppen] == [
        "werbungskosten",
        "lohnsteuer_edaten",
        "nicht_zugeordnet",
    ]


def test_playwright_fuellt_feld_ohne_formular_abzusenden():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
        except sync_api.Error as exc:
            pytest.skip(f"Lokaler Chrome-Kanal nicht verfügbar: {exc}")
        try:
            seite = browser.new_page()
            _oeffne_elster_testentwurf(
                seite,
                '<form><label for="arbeitsmittel">Aufwendungen für Arbeitsmittel</label>'
                '<input id="arbeitsmittel"><button type="submit">Versenden</button></form>'
            )
            bericht = fuelle_aktionsplan(
                seite,
                [_browser_aktion("arbeitsmittel", "250,00")],
                wirklich_ausfuellen=True,
            )

            assert seite.locator("#arbeitsmittel").input_value() == "250,00"
            assert bericht["ergebnisse"][0]["status"] == "ausgefuellt"
            assert bericht["ergebnisse"][0]["vergleich_status"] == "bestanden"
            assert bericht["bestanden"] is True
            assert bericht["versendet"] is False
            assert seite.url == "https://www.elster.de/eportal/interpreter/eingabe"
        finally:
            browser.close()


def test_soll_ist_abweichung_sperrt_den_naechsten_abschnitt():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
        except sync_api.Error as exc:
            pytest.skip(f"Lokaler Chrome-Kanal nicht verfügbar: {exc}")
        try:
            seite = browser.new_page()
            _oeffne_elster_testentwurf(
                seite,
                '<label for="arbeitsmittel">Aufwendungen für Arbeitsmittel</label>'
                '<input id="arbeitsmittel" onblur="this.value=\'251,00\'">'
                '<label for="fortbildung">Fortbildungskosten</label>'
                '<input id="fortbildung">'
            )
            bericht = fuelle_aktionsplan(
                seite,
                [
                    _browser_aktion("arbeitsmittel", "250,00 €"),
                    _browser_aktion("fortbildungskosten", "100,00 €"),
                ],
                wirklich_ausfuellen=True,
            )

            status = {eintrag["feld_id"]: eintrag["status"] for eintrag in bericht["ergebnisse"]}
            assert status["arbeitsmittel"] == "abweichung_soll_ist"
            assert status["fortbildungskosten"] == "blockiert_nach_abweichung"
            assert seite.locator("#fortbildung").input_value() == ""
            assert bericht["bestanden"] is False
            assert bericht["abgebrochen"] is True
            assert "250,00" not in json.dumps(bericht, ensure_ascii=False)
        finally:
            browser.close()


def test_bitgenauer_mismatch_stoppt_sofort_innerhalb_des_blocks():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
        except sync_api.Error as exc:
            pytest.skip(f"Lokaler Chrome-Kanal nicht verfügbar: {exc}")
        try:
            seite = browser.new_page()
            _oeffne_elster_testentwurf(
                seite,
                '<label for="arbeitsmittel">Aufwendungen für Arbeitsmittel</label>'
                '<input id="arbeitsmittel" onblur="this.value=this.value+\' \'">'
                '<label for="fortbildung">Fortbildungskosten</label>'
                '<input id="fortbildung">'
            )
            bericht = fuelle_aktionsplan(
                seite,
                [
                    _browser_aktion("arbeitsmittel", "250,00"),
                    _browser_aktion("fortbildungskosten", "100,00"),
                ],
                wirklich_ausfuellen=True,
            )

            status = {eintrag["feld_id"]: eintrag["status"] for eintrag in bericht["ergebnisse"]}
            assert status["arbeitsmittel"] == "abweichung_soll_ist"
            assert status["fortbildungskosten"] == "blockiert_nach_abweichung"
            assert seite.locator("#fortbildung").input_value() == ""
            assert bericht["abbruchgrund"] == "bitgenauer_soll_ist_mismatch"
            assert bericht["manuelle_pruefung_erforderlich"] is True
        finally:
            browser.close()


def test_unbekanntes_feld_sperrt_alle_interaktionen_vorab():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
        except sync_api.Error as exc:
            pytest.skip(f"Lokaler Chrome-Kanal nicht verfügbar: {exc}")
        try:
            seite = browser.new_page()
            seite.set_content(
                '<label for="arbeitsmittel">Aufwendungen für Arbeitsmittel</label>'
                '<input id="arbeitsmittel">'
            )
            bericht = fuelle_aktionsplan(
                seite,
                [
                    {
                        "feld_id": "arbeitsmittel",
                        "status": "bereit",
                        "wert": "250,00",
                        "labels": ["Aufwendungen für Arbeitsmittel"],
                    },
                    {
                        "feld_id": "unbekannt",
                        "status": "offen_keine_eindeutige_zuordnung",
                        "wert": None,
                        "labels": [],
                    },
                ],
                wirklich_ausfuellen=True,
            )

            assert seite.locator("#arbeitsmittel").input_value() == ""
            assert bericht["abbruchgrund"] == "unbekannte_oder_offene_felder_vor_interaktion"
            assert bericht["abgebrochen"] is True
        finally:
            browser.close()


def test_doppelte_feld_id_sperrt_den_lauf_vor_interaktion():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
        except sync_api.Error as exc:
            pytest.skip(f"Lokaler Chrome-Kanal nicht verfügbar: {exc}")
        try:
            seite = browser.new_page()
            seite.set_content(
                '<label for="arbeitsmittel">Aufwendungen für Arbeitsmittel</label>'
                '<input id="arbeitsmittel">'
            )
            bericht = fuelle_aktionsplan(
                seite,
                [
                    _browser_aktion("arbeitsmittel", "250,00"),
                    _browser_aktion("arbeitsmittel", "300,00"),
                ],
                wirklich_ausfuellen=True,
            )

            assert seite.locator("#arbeitsmittel").input_value() == ""
            assert {eintrag["status"] for eintrag in bericht["ergebnisse"]} == {
                "offen_doppelte_feld_id"
            }
            assert bericht["abbruchgrund"] == "unbekannte_oder_offene_felder_vor_interaktion"
        finally:
            browser.close()


def test_float_statt_string_zieht_notbremse_vor_dom_interaktion():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
        except sync_api.Error as exc:
            pytest.skip(f"Lokaler Chrome-Kanal nicht verfügbar: {exc}")
        try:
            seite = browser.new_page()
            seite.set_content(
                '<label for="arbeitsmittel">Aufwendungen für Arbeitsmittel</label>'
                '<input id="arbeitsmittel">'
            )
            aktion = _browser_aktion("arbeitsmittel", "250,00")
            aktion["wert"] = 250.0
            start = perf_counter()

            bericht = fuelle_aktionsplan(seite, [aktion], wirklich_ausfuellen=True)

            dauer = perf_counter() - start
            assert dauer < 1.0
            assert seite.locator("#arbeitsmittel").input_value() == ""
            assert bericht["ergebnisse"][0]["status"] == "offen_datentyp_mismatch"
            assert bericht["manuelle_pruefung_erforderlich"] is True
        finally:
            browser.close()


def test_unerwarteter_dom_feldtyp_stoppt_ohne_retry_verzoegerung():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
        except sync_api.Error as exc:
            pytest.skip(f"Lokaler Chrome-Kanal nicht verfügbar: {exc}")
        try:
            seite = browser.new_page()
            _oeffne_elster_testentwurf(
                seite,
                '<label for="arbeitsmittel">Aufwendungen für Arbeitsmittel</label>'
                '<select id="arbeitsmittel"><option value="">Bitte wählen</option></select>'
            )
            start = perf_counter()

            bericht = fuelle_aktionsplan(
                seite,
                [_browser_aktion("arbeitsmittel", "250,00")],
                wirklich_ausfuellen=True,
            )

            dauer = perf_counter() - start
            assert dauer < 2.0
            assert seite.locator("#arbeitsmittel").input_value() == ""
            assert bericht["ergebnisse"][0]["status"] == "layout_oder_versionsabweichung"
            assert bericht["abgebrochen"] is True
        finally:
            browser.close()


def test_layout_preflight_verhindert_teilbefuellung_des_abschnitts():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
        except sync_api.Error as exc:
            pytest.skip(f"Lokaler Chrome-Kanal nicht verfügbar: {exc}")
        try:
            seite = browser.new_page()
            _oeffne_elster_testentwurf(
                seite,
                '<label for="arbeitsmittel">Aufwendungen für Arbeitsmittel</label>'
                '<input id="arbeitsmittel">'
            )
            bericht = fuelle_aktionsplan(
                seite,
                [
                    _browser_aktion("arbeitsmittel", "250,00"),
                    _browser_aktion("fortbildungskosten", "100,00"),
                ],
                wirklich_ausfuellen=True,
            )

            status = {eintrag["feld_id"]: eintrag["status"] for eintrag in bericht["ergebnisse"]}
            assert seite.locator("#arbeitsmittel").input_value() == ""
            assert status["arbeitsmittel"] == "blockiert_vor_interaktion"
            assert status["fortbildungskosten"] == "layout_oder_versionsabweichung"
            assert bericht["abgebrochen"] is True
        finally:
            browser.close()


def test_versionsaenderung_wird_vor_interaktion_erkannt():
    sicherheitskontext = erstelle_sicherheitskontext()
    sicherheitskontext["mapping_sha256"] = "0" * 64

    _mapping, fehler = pruefe_versionsschranke(sicherheitskontext)

    assert any("mapping_sha256" in eintrag for eintrag in fehler)


def test_veralteter_mapping_hash_blockiert_playwright_fill():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
        except sync_api.Error as exc:
            pytest.skip(f"Lokaler Chrome-Kanal nicht verfügbar: {exc}")
        try:
            seite = browser.new_page()
            seite.route(
                "https://www.elster.de/**",
                lambda route: route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=(
                        "<main>Einkommensteuer 2025 – Entwurf"
                        '<label for="arbeitsmittel">Aufwendungen für Arbeitsmittel</label>'
                        '<input id="arbeitsmittel"></main>'
                    ),
                ),
            )
            seite.goto("https://www.elster.de/eportal/interpreter/eingabe")
            mapping = lade_browser_mapping()
            sicherheitskontext = erstelle_sicherheitskontext(mapping)
            sicherheitskontext["mapping_sha256"] = "0" * 64
            regel = mapping["felder"]["arbeitsmittel"]

            bericht = fuelle_aktionsplan(
                seite,
                [{
                    "feld_id": "arbeitsmittel",
                    "status": "bereit",
                    "modus": regel["modus"],
                    "vergleich": regel["vergleich"],
                    "wert": "250,00",
                    "labels": regel["labels"],
                    "anlage": "Anlage N",
                    "abschnitt": "Werbungskosten",
                    "block_id": "werbungskosten",
                    "block_titel": "Werbungskosten",
                }],
                wirklich_ausfuellen=True,
                sicherheitskontext=sicherheitskontext,
            )

            assert seite.locator("#arbeitsmittel").input_value() == ""
            assert bericht["ergebnisse"][0]["status"] == "blockiert_vor_interaktion"
            assert bericht["abbruchgrund"] == "abschnitt_vorpruefung_fehlgeschlagen"
            assert bericht["abgebrochen"] is True
        finally:
            browser.close()


def test_abschnittsschranken_und_bitgenaues_readback_bestehen_gemeinsam():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
        except sync_api.Error as exc:
            pytest.skip(f"Lokaler Chrome-Kanal nicht verfügbar: {exc}")
        try:
            seite = browser.new_page()
            seite.route(
                "https://www.elster.de/**",
                lambda route: route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=(
                        "<main>Einkommensteuer 2025 – Entwurf"
                        '<label for="arbeitsmittel">Aufwendungen für Arbeitsmittel</label>'
                        '<input id="arbeitsmittel"></main>'
                    ),
                ),
            )
            seite.goto("https://www.elster.de/eportal/interpreter/eingabe")
            mapping = lade_browser_mapping()
            regel = mapping["felder"]["arbeitsmittel"]
            bericht = fuelle_aktionsplan(
                seite,
                [{
                    "feld_id": "arbeitsmittel",
                    "status": "bereit",
                    "modus": regel["modus"],
                    "vergleich": regel["vergleich"],
                    "wert": "250,00",
                    "labels": regel["labels"],
                    "anlage": "Anlage N",
                    "abschnitt": "Werbungskosten",
                    "block_id": "werbungskosten",
                    "block_titel": "Werbungskosten",
                }],
                wirklich_ausfuellen=True,
                sicherheitskontext=erstelle_sicherheitskontext(mapping),
            )

            assert bericht["bestanden"] is True
            assert bericht["abschnitte"][0]["vorpruefung"] == "bestanden"
            assert bericht["abschnitte"][0]["nachpruefung"] == "bestanden"
            assert bericht["ergebnisse"][0]["vergleichsart"] == "bitgenau_utf8"
            assert bericht["ergebnisse"][0]["vergleich_status"] == "bestanden"
        finally:
            browser.close()
