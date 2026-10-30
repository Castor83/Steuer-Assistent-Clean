"""Sammelt fehlgeschlagene Schritte aus den echten Gesprächschargen 04 bis 06."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ERGEBNISSE = ROOT / "tests" / "ergebnisse"
QUELLEN = (
    "praxisdialog_charge_04_bestand.json",
    "praxisdialog_charge_05_jahr2024.json",
    "praxisdialog_charge_06_jahr2025.json",
)
ZIEL_JSON = ERGEBNISSE / "praxisdialog_chargen_04_06_fehlerkatalog.json"
ZIEL_MD = ERGEBNISSE / "praxisdialog_chargen_04_06_fehlerkatalog.md"


def fehlerklasse(eintrag: dict) -> str:
    szenario = str(eintrag.get("szenario", "")).casefold()
    if "laptop" in szenario:
        return "Verlorener Gegenstand im Gesprächskontext und falsche allgemeine Quelle"
    if "steuerklasse" in szenario:
        return "Fehlende feste Jahresregel für die Lohnsteuerbescheinigung"
    return "Sonstige Fehlformulierung"


def sammeln() -> dict:
    beobachtungen: list[dict] = []
    gruppen: dict[str, list[dict]] = defaultdict(list)
    schritte = 0
    bestanden = 0

    for name in QUELLEN:
        bericht = json.loads((ERGEBNISSE / name).read_text(encoding="utf-8"))
        schritte += int(bericht.get("anzahl", 0))
        bestanden += int(bericht.get("bestanden", 0))
        for eintrag in bericht.get("ergebnisse", []):
            if eintrag.get("status") == "BESTANDEN":
                continue
            klasse = fehlerklasse(eintrag)
            beobachtung = {
                "charge": name,
                "steuerjahr": bericht.get("steuerjahr"),
                "szenario": eintrag.get("szenario"),
                "schritt": eintrag.get("schritt"),
                "frage": eintrag.get("frage"),
                "antwort": eintrag.get("antwort"),
                "gruende": eintrag.get("gruende", []),
                "fehlerklasse": klasse,
            }
            beobachtungen.append(beobachtung)
            gruppen[klasse].append(beobachtung)

    payload = {
        "chargen": list(QUELLEN),
        "gespraechsschritte": schritte,
        "bestanden": bestanden,
        "fehlgeschlagen": len(beobachtungen),
        "fehlerklassen": [
            {"name": name, "beobachtungen": len(eintraege)}
            for name, eintraege in sorted(gruppen.items())
        ],
        "beobachtungen": beobachtungen,
    }
    ZIEL_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    zeilen = [
        "# Fehlerkatalog der Praxisdialog-Chargen 04 bis 06",
        "",
        f"Geprüfte Gesprächsschritte: {schritte}",
        f"Bestanden: {bestanden}",
        f"Fehlgeschlagen: {len(beobachtungen)}",
        "",
    ]
    for name, eintraege in sorted(gruppen.items()):
        zeilen.extend((f"## {name}", ""))
        for eintrag in eintraege:
            zeilen.append(
                f"- {eintrag['charge']} · Steuerjahr {eintrag['steuerjahr']} · "
                f"{eintrag['szenario']} Schritt {eintrag['schritt']}: "
                + "; ".join(eintrag["gruende"])
            )
        zeilen.append("")
    ZIEL_MD.write_text("\n".join(zeilen), encoding="utf-8")
    return payload


if __name__ == "__main__":
    print(json.dumps(sammeln(), ensure_ascii=False, indent=2))
