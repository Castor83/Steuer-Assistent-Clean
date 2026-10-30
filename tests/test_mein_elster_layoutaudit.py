import json
from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from mein_elster_browser import lade_browser_mapping
from mein_elster_layoutaudit import pruefe_block_layout_readonly


def _oeffne_testentwurf(seite, feld_html: str) -> None:
    seite.route(
        "https://www.elster.de/**",
        lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body=f"<main>Einkommensteuer 2025 – Entwurf{feld_html}</main>",
        ),
    )
    seite.goto("https://www.elster.de/eportal/interpreter/eingabe")


def test_layoutaudit_liest_keine_steuerwerte_und_aendert_nichts():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
        except sync_api.Error as exc:
            pytest.skip(f"Lokaler Chrome-Kanal nicht verfügbar: {exc}")
        try:
            seite = browser.new_page()
            _oeffne_testentwurf(
                seite,
                '<label for="arbeitsmittel">Aufwendungen für Arbeitsmittel</label>'
                '<input id="arbeitsmittel" value="GEHEIMER-STEUERWERT">'
            )

            bericht = pruefe_block_layout_readonly(
                seite,
                lade_browser_mapping(),
                "werbungskosten",
            )

            assert seite.locator("#arbeitsmittel").input_value() == "GEHEIMER-STEUERWERT"
            assert bericht["steuerwerte_gelesen"] is False
            assert bericht["steuerwerte_geaendert"] is False
            assert "GEHEIMER-STEUERWERT" not in json.dumps(bericht, ensure_ascii=False)
        finally:
            browser.close()


def test_layoutaudit_markiert_unerwarteten_dom_typ():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
        except sync_api.Error as exc:
            pytest.skip(f"Lokaler Chrome-Kanal nicht verfügbar: {exc}")
        try:
            seite = browser.new_page()
            _oeffne_testentwurf(
                seite,
                '<label for="arbeitsmittel">Aufwendungen für Arbeitsmittel</label>'
                '<select id="arbeitsmittel"><option>250,00</option></select>'
            )

            bericht = pruefe_block_layout_readonly(
                seite,
                lade_browser_mapping(),
                "werbungskosten",
            )
            arbeitsmittel = next(
                feld for feld in bericht["felder"] if feld["feld_id"] == "arbeitsmittel"
            )

            assert arbeitsmittel["status"] == "unerwarteter_feldtyp_oder_zustand"
            assert arbeitsmittel["treffer"][0]["tag"] == "select"
            assert bericht["bestanden"] is False
        finally:
            browser.close()
