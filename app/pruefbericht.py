"""Erstellt eine datensparsame Abschlussübersicht für ein Steuerjahr."""

from __future__ import annotations

from datetime import datetime

from steuer_checkliste import erstelle_checkliste


def erstelle_pruefbericht(
    steuerjahr: str,
    bereiche: list[str],
    dokumente: list[dict],
    nutzer_name: str = "",
) -> dict:
    """Fasst Metadaten zusammen, ohne Dateipfade oder ausgelesenen Rohtext auszugeben."""
    checkliste = erstelle_checkliste(steuerjahr, bereiche, dokumente)
    passende_dokumente = [
        dokument
        for dokument in dokumente
        if str(dokument.get("steuerjahr", "")) in {steuerjahr, "Nicht erkannt", ""}
    ]
    werte = []
    for dokument in passende_dokumente:
        for wert in dokument.get("wertvorschlaege", []):
            if wert.get("status") != "Bestätigt":
                continue
            werte.append(
                {
                    "bezeichnung": str(wert.get("bezeichnung", "")),
                    "wert": str(wert.get("wert", "")),
                    "quelle": str(dokument.get("dateiname", "")),
                }
            )

    return {
        "nutzer_name": str(nutzer_name).strip(),
        "steuerjahr": steuerjahr,
        "erstellt_am": datetime.now().astimezone().isoformat(timespec="seconds"),
        "bereiche": bereiche,
        "zusammenfassung": {
            "dokumente": len(passende_dokumente),
            "gepruefte_dokumente": sum(d.get("status") == "Geprüft" for d in passende_dokumente),
            "offene_dokumente": sum(d.get("status") != "Geprüft" for d in passende_dokumente),
            "vorhandene_pruefpunkte": sum(p["status"] == "Vorhanden" for p in checkliste),
            "offene_pruefpunkte": sum(p["status"] != "Vorhanden" for p in checkliste),
            "bestaetigte_werte": len(werte),
        },
        "checkliste": checkliste,
        "bestaetigte_werte": werte,
        "dokumente": [
            {
                "dateiname": str(d.get("dateiname", "")),
                "dokumenttyp": str(d.get("dokumenttyp", "")),
                "steuerjahr": str(d.get("steuerjahr", "")),
                "status": str(d.get("status", "")),
            }
            for d in passende_dokumente
        ],
        "hinweis": "Diese Übersicht ist eine Vorbereitungshilfe und keine eingereichte Steuererklärung.",
    }
