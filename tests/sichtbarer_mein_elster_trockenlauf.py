"""Sichtbarer, rein lokaler Mein-ELSTER-Sandboxlauf ohne Versandmöglichkeit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from mein_elster_browser import (  # noqa: E402
    erstelle_aktionsplan,
    erstelle_sicherheitskontext,
    fuelle_aktionsplan,
    lade_browser_mapping,
    lade_eingabehilfe,
    pruefe_aktionsplan_vor_lauf,
)


SANDBOX_URL = "https://www.elster.de/eportal/interpreter/eingabe"


def sandbox_html(steuerjahr: str) -> str:
    return f"""<!doctype html>
<html lang="de">
<head><meta charset="utf-8"><title>Lokale Mein-ELSTER-Sandbox</title></head>
<body style="font:16px system-ui;max-width:760px;margin:40px auto;background:#f5f7fa;color:#17202a">
  <main style="background:white;padding:28px;border-radius:12px;box-shadow:0 4px 20px #0002">
    <p style="color:#9b1c1c;font-weight:700">LOKALE SANDBOX – KEINE ÜBERMITTLUNG</p>
    <h1>Einkommensteuer {steuerjahr} – Entwurf</h1>
    <h2>Werbungskosten</h2>
    <form id="steuerformular">
      <p><label for="arbeitsmittel">Aufwendungen für Arbeitsmittel</label><br>
      <input id="arbeitsmittel" style="padding:8px;width:260px"></p>
      <p><label for="fortbildung">Fortbildungskosten</label><br>
      <input id="fortbildung" style="padding:8px;width:260px"></p>
      <button type="submit" disabled>Prüfen und versenden (deaktiviert)</button>
    </form>
    <p id="status">Sandbox bereit.</p>
  </main>
  <script>
    window.__submitCount = 0;
    document.querySelector('form').addEventListener('submit', event => {{
      event.preventDefault();
      window.__submitCount += 1;
    }});
  </script>
</body>
</html>"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steuerjahr", choices=("2023", "2024", "2025"), default="2025")
    parser.add_argument("--eingabe", type=Path)
    parser.add_argument("--sichtbar-sekunden", type=float, default=8.0)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    beispiel = args.eingabe or ROOT / "tests" / "elster" / args.steuerjahr / "mein_elster_sandbox.json"
    ergebnis = ROOT / "tests" / "ergebnisse" / f"mein_elster_sichtbarer_trockenlauf_{args.steuerjahr}.json"
    bildschirm = ROOT / "tests" / "ergebnisse" / f"mein_elster_sichtbarer_trockenlauf_{args.steuerjahr}.png"
    eingabehilfe = lade_eingabehilfe(beispiel)
    if str(eingabehilfe["steuerjahr"]) != args.steuerjahr:
        raise ValueError("Beispieldaten und gewähltes Steuerjahr stimmen nicht überein.")
    mapping = lade_browser_mapping(args.steuerjahr)
    aktionen = erstelle_aktionsplan(eingabehilfe, mapping=mapping)
    planfehler = pruefe_aktionsplan_vor_lauf(aktionen)
    if planfehler:
        raise RuntimeError("Sandbox-Aktionsplan gesperrt: " + "; ".join(planfehler))

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=args.headless)
        try:
            seite = browser.new_page(locale="de-DE")
            seite.route(
                "https://www.elster.de/**",
                lambda route: route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=sandbox_html(args.steuerjahr),
                ),
            )
            seite.goto(SANDBOX_URL, wait_until="domcontentloaded")
            bericht = fuelle_aktionsplan(
                seite,
                aktionen,
                wirklich_ausfuellen=True,
                sicherheitskontext=erstelle_sicherheitskontext(mapping),
            )
            submit_count = seite.evaluate("window.__submitCount")
            bericht.update({
                "sandbox": True,
                "portalzugriff": False,
                "submit_ereignisse": submit_count,
            })
            if submit_count != 0 or bericht["versendet"] is not False:
                raise RuntimeError("Versandschranke des Sandboxlaufs wurde verletzt.")
            if not bericht["bestanden"]:
                raise RuntimeError(f"Sandboxlauf abgebrochen: {bericht.get('abbruchgrund')}")

            ergebnis.parent.mkdir(parents=True, exist_ok=True)
            ergebnis.write_text(
                json.dumps(bericht, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            seite.screenshot(path=str(bildschirm), full_page=True)
            print(json.dumps({
                "bestanden": bericht["bestanden"],
                "felder": len(bericht["ergebnisse"]),
                "vorpruefung": bericht["abschnitte"][0]["vorpruefung"],
                "nachpruefung": bericht["abschnitte"][0]["nachpruefung"],
                "submit_ereignisse": submit_count,
                "steuerjahr": args.steuerjahr,
                "bericht": str(ergebnis),
                "screenshot": str(bildschirm),
            }, ensure_ascii=False, indent=2))
            if not args.headless and args.sichtbar_sekunden > 0:
                seite.wait_for_timeout(args.sichtbar_sekunden * 1000)
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
