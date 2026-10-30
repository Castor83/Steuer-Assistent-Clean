"""Read-Only-Prüfung des Mein-ELSTER-DOM gegen das freigegebene Mapping."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

from mein_elster_browser import (  # noqa: E402
    START_URL,
    lade_browser_mapping,
    pruefe_entwurfkontext,
)


def _element_metadaten(locator, mapping: dict) -> dict:
    layout = mapping["layout_vertrag"]
    tag = locator.evaluate("element => element.tagName.toLowerCase()")
    typ = (locator.get_attribute("type") or "text").lower()
    sichtbar = locator.is_visible()
    aktiviert = locator.is_enabled()
    readonly = locator.get_attribute("readonly") is not None
    sicher = (
        tag in set(layout["erlaubte_tags"])
        and typ not in set(layout["verbotene_input_typen"])
        and sichtbar
        and aktiviert
        and not readonly
    )
    return {
        "tag": tag,
        "typ": typ,
        "sichtbar": sichtbar,
        "aktiviert": aktiviert,
        "readonly": readonly,
        "sicher": sicher,
    }


def _unbekannte_formularfelder(page, mapping: dict) -> list[dict]:
    """Erfasst nur Strukturdaten; `value` wird absichtlich nie gelesen."""
    elemente = page.locator("main input, main textarea, main select").evaluate_all(
        """elements => elements.map(element => {
          const explicit = element.id
            ? document.querySelector(`label[for="${CSS.escape(element.id)}"]`)
            : null;
          const wrapping = element.closest('label');
          return {
            tag: element.tagName.toLowerCase(),
            typ: (element.getAttribute('type') || 'text').toLowerCase(),
            label: (element.getAttribute('aria-label') || explicit?.innerText || wrapping?.innerText || '').trim(),
          };
        })"""
    )
    bekannte_labels = {
        str(label).strip().casefold()
        for regel in mapping["felder"].values()
        for label in regel["labels"]
    }
    unbekannt = []
    for element in elemente:
        label = str(element.get("label", "")).strip()
        normalisiert = label.casefold()
        if not normalisiert or not any(
            bekannt in normalisiert or normalisiert in bekannt
            for bekannt in bekannte_labels
        ):
            unbekannt.append(element)
    return unbekannt


def pruefe_block_layout_readonly(page, mapping: dict, block_id: str) -> dict:
    block = next(
        (block for block in mapping["abschnittsbloecke"] if block["id"] == block_id),
        None,
    )
    if block is None:
        raise ValueError(f"Unbekannter Abschnittsblock: {block_id}")

    try:
        sichtbarer_text = page.locator("body").inner_text()
        kontextfehler = pruefe_entwurfkontext(page.url, sichtbarer_text, mapping)
    except Exception as exc:
        kontextfehler = [f"Portalinhalt konnte nicht read-only geprüft werden: {exc}"]

    felder = []
    for feld_id in block["felder"]:
        regel = mapping["felder"][feld_id]
        treffer = []
        verwendetes_label = None
        for label in regel["labels"]:
            kandidaten = page.get_by_label(label, exact=False)
            if kandidaten.count() == 0:
                continue
            verwendetes_label = label
            treffer = [
                _element_metadaten(kandidaten.nth(index), mapping)
                for index in range(kandidaten.count())
            ]
            break
        sichere_treffer = [element for element in treffer if element["sicher"]]
        if len(sichere_treffer) == 1:
            status = "gefunden"
        elif len(sichere_treffer) > 1:
            status = "mehrdeutig"
        elif treffer:
            status = "unerwarteter_feldtyp_oder_zustand"
        else:
            status = "nicht_gefunden"
        felder.append({
            "feld_id": feld_id,
            "status": status,
            "verwendetes_label": verwendetes_label,
            "treffer": treffer,
        })

    adresse = urlparse(page.url)
    unbekannte_felder = _unbekannte_formularfelder(page, mapping)
    abweichungen = [feld for feld in felder if feld["status"] != "gefunden"]
    return {
        "format": "steuer-assistent-mein-elster-layoutaudit/v1",
        "modus": "read_only",
        "steuerwerte_gelesen": False,
        "steuerwerte_geaendert": False,
        "versendet": False,
        "steuerjahr": mapping["steuerjahr"],
        "layout_vertrag": mapping["layout_vertrag"]["version"],
        "portal": {
            "schema": adresse.scheme,
            "host": adresse.hostname,
            "pfad": adresse.path,
        },
        "block_id": block_id,
        "block_titel": block["titel"],
        "bestanden": not kontextfehler and not abweichungen and not unbekannte_felder,
        "kontextfehler": kontextfehler,
        "felder": felder,
        "unbekannte_formularfelder": unbekannte_felder,
    }


def _bericht_speichern(bericht: dict) -> Path:
    zeit = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    ziel = ROOT / "logs" / f"mein_elster_layoutaudit_{zeit}.json"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(json.dumps(bericht, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ziel


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--steuerjahr",
        choices=("2023", "2024", "2025"),
        default="2025",
        help="Steuerjahr des manuell geöffneten Entwurfs.",
    )
    parser.add_argument(
        "--block",
        default="stammdaten",
        help="ID des fachlichen Blocks; standardmäßig wird mit Stammdaten begonnen.",
    )
    args = parser.parse_args()
    mapping = lade_browser_mapping(args.steuerjahr)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=False)
        try:
            kontext = browser.new_context(locale="de-DE")
            seite = kontext.new_page()
            seite.goto(START_URL, wait_until="domcontentloaded")
            block = next(
                (block for block in mapping["abschnittsbloecke"] if block["id"] == args.block),
                None,
            )
            if block is None:
                raise ValueError(f"Unbekannter Abschnittsblock: {args.block}")
            print(
                "READ-ONLY: Melde dich selbst an und öffne einen noch nicht abgegebenen "
                f"ESt-{mapping['steuerjahr']}-Entwurf im Block ‚{block['titel']}‘. "
                "Es werden keine Feldwerte gelesen oder verändert. Drücke danach hier Enter."
            )
            input()
            seite = kontext.pages[-1]
            bericht = pruefe_block_layout_readonly(seite, mapping, args.block)
            ziel = _bericht_speichern(bericht)
            print(json.dumps({
                "bestanden": bericht["bestanden"],
                "block": bericht["block_titel"],
                "gefunden": sum(feld["status"] == "gefunden" for feld in bericht["felder"]),
                "abweichungen": sum(feld["status"] != "gefunden" for feld in bericht["felder"]),
                "unbekannte_formularfelder": len(bericht["unbekannte_formularfelder"]),
                "bericht": str(ziel),
            }, ensure_ascii=False, indent=2))
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
