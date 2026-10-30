"""Prüft den vorhandenen Beleg über die laufende lokale Web-Anwendung."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener


ERGEBNISORDNER = Path(__file__).resolve().parent / "ergebnisse"


def anfrage(opener, basis: str, pfad: str, payload: dict | None = None) -> dict:
    daten = None
    methode = "GET"
    header = {}
    if payload is not None:
        daten = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        methode = "POST"
        header["Content-Type"] = "application/json; charset=utf-8"
    request = Request(basis.rstrip("/") + pfad, data=daten, headers=header, method=methode)
    with opener.open(request, timeout=60) as response:
        return json.load(response)


def pruefung(name: str, bedingung: bool, ist=None) -> dict:
    return {"pruefung": name, "status": "BESTANDEN" if bedingung else "PRUEFEN", "ist": ist}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--basis-url", default="http://127.0.0.1:8765")
    parser.add_argument("--nutzer", default="Alex Beispiel")
    parser.add_argument("--ausgabe", type=Path)
    args = parser.parse_args()

    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    nutzerdaten = anfrage(opener, args.basis_url, "/api/nutzer")
    nutzer = next((n for n in nutzerdaten.get("nutzer", []) if n.get("name") == args.nutzer), None)
    if nutzer is None:
        print(f"NICHT GETESTET: Nutzer nicht gefunden: {args.nutzer}")
        return 2
    anfrage(opener, args.basis_url, "/api/nutzer/wechseln", {"nutzer_id": nutzer["id"]})

    dokumente = anfrage(opener, args.basis_url, "/api/dokumente").get("dokumente", [])
    werte_2025 = anfrage(opener, args.basis_url, "/api/persoenliche-steuerdaten?steuerjahr=2025").get("werte", [])
    werte_2023 = anfrage(opener, args.basis_url, "/api/persoenliche-steuerdaten?steuerjahr=2023").get("werte", [])
    bericht_2023 = anfrage(
        opener,
        args.basis_url,
        "/api/pruefbericht",
        {"steuerjahr": "2023", "bereiche": ["arbeitnehmer"]},
    )
    merkmale = {wert.get("id"): wert.get("wert") for wert in werte_2025}
    dokument = dokumente[0] if len(dokumente) == 1 else {}
    dokumentwerte = {
        wert.get("id"): wert.get("wert")
        for wert in dokument.get("wertvorschlaege", [])
    }
    ergebnisse = [
        pruefung("Beleg nur einmal sichtbar", len(dokumente) == 1, len(dokumente)),
        pruefung("Dokumenttyp", dokument.get("dokumenttyp") == "Elektronische Lohnsteuerbescheinigung", dokument.get("dokumenttyp")),
        pruefung("Steuerjahr 2025", dokument.get("steuerjahr") == "2025", dokument.get("steuerjahr")),
        pruefung("Nutzername erkannt", dokument.get("nutzerzuordnung", {}).get("status") == "Erkannt", dokument.get("nutzerzuordnung", {}).get("status")),
        pruefung("Steuerklasse I", merkmale.get("steuerklasse") == "1", merkmale.get("steuerklasse")),
        pruefung("Kinderfreibetrag 0,0", merkmale.get("kinderfreibetrag") == "0,0", merkmale.get("kinderfreibetrag")),
        pruefung("Bescheinigungszeitraum", merkmale.get("beschaeftigungszeitraum") == "01.01.2025 BIS 31.12.2025", merkmale.get("beschaeftigungszeitraum")),
        pruefung("Bruttoarbeitslohn", dokumentwerte.get("bruttoarbeitslohn") == "0,00 €", dokumentwerte.get("bruttoarbeitslohn")),
        pruefung(
            "Uneindeutige Nullfelder nicht geraten",
            not {"lohnsteuer", "solidaritaetszuschlag", "kirchensteuer"}.intersection(dokumentwerte),
            {kennung: dokumentwerte.get(kennung) for kennung in ("lohnsteuer", "solidaritaetszuschlag", "kirchensteuer") if kennung in dokumentwerte},
        ),
        pruefung("Rentenversicherungsbeitrag", dokumentwerte.get("rentenversicherung") == "210,00 €", dokumentwerte.get("rentenversicherung")),
        pruefung("Krankenversicherungsbeitrag", dokumentwerte.get("krankenversicherung") == "200,00 €", dokumentwerte.get("krankenversicherung")),
        pruefung("Arbeitslosenversicherungsbeitrag", dokumentwerte.get("arbeitslosenversicherung") == "30,00 €", dokumentwerte.get("arbeitslosenversicherung")),
        pruefung("Pflegeversicherungsbeitrag doppelt erkannt", dokumentwerte.get("pflegeversicherung") == "50,00 €", dokumentwerte.get("pflegeversicherung")),
        pruefung("Keine 2025-Werte in 2023", not werte_2023, len(werte_2023)),
        pruefung("Kein 2025-Beleg im Prüfbericht 2023", bericht_2023.get("zusammenfassung", {}).get("dokumente") == 0, bericht_2023.get("zusammenfassung", {}).get("dokumente")),
        pruefung("Werte bleiben unbestätigt", bool(werte_2025) and all(w.get("status") == "Zu prüfen" for w in werte_2025), [w.get("status") for w in werte_2025]),
    ]
    payload = {
        "erstellt_am": datetime.now().astimezone().isoformat(timespec="seconds"),
        "nutzer": args.nutzer,
        "bestanden": sum(e["status"] == "BESTANDEN" for e in ergebnisse),
        "anzahl": len(ergebnisse),
        "ergebnisse": ergebnisse,
    }
    zeit = datetime.now().strftime("%Y%m%d_%H%M%S")
    ausgabe = args.ausgabe or ERGEBNISORDNER / f"dokument_webtest_{zeit}.json"
    ausgabe.parent.mkdir(parents=True, exist_ok=True)
    ausgabe.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    for ergebnis in ergebnisse:
        print(f"{ergebnis['status']} {ergebnis['pruefung']}")
    print(f"ERGEBNIS {ausgabe}")
    print(f"ZUSAMMENFASSUNG {payload['bestanden']}/{payload['anzahl']} bestanden")
    return 0 if payload["bestanden"] == payload["anzahl"] else 1


if __name__ == "__main__":
    sys.exit(main())
