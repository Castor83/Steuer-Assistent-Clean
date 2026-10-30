"""Trennt die 14 Kernfälle in sichere, jahresgenaue Verfahrensstufen."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from elster_mapping import lade_mapping


ROOT = Path(__file__).resolve().parent.parent

VERFAHREN = {
    "est_2025_anlage_n": {
        "reihenfolge": 1,
        "bezeichnung": "ESt 2025 – Anlage N / Lohnsteuer",
        "system": "ERiC",
    },
    "est_2025_anlage_v": {
        "reihenfolge": 2,
        "bezeichnung": "ESt 2025 – Anlage V / AfA",
        "system": "ERiC",
    },
    "est_2025_aussergewoehnliche_belastungen": {
        "reihenfolge": 2,
        "bezeichnung": "ESt 2025 – Außergewöhnliche Belastungen",
        "system": "ERiC",
    },
    "est_2025_einkommensersatzleistungen": {
        "reihenfolge": 3,
        "bezeichnung": "ESt 2025 – Insolvenzgeld/Progressionsvorbehalt",
        "system": "ERiC",
    },
    "insolvenzgeld_bundesagentur": {
        "reihenfolge": 3,
        "bezeichnung": "Insolvenzgeldantrag",
        "system": "Bundesagentur für Arbeit",
    },
    "erbschaftsteuer_erklaerung": {
        "reihenfolge": 4,
        "bezeichnung": "Erbschaftsteuererklärung",
        "system": "separate Steuerdatenart",
    },
    "erbschaftsteuer_anzeige": {
        "reihenfolge": 4,
        "bezeichnung": "Anzeige nach § 30 ErbStG",
        "system": "separates Meldeverfahren",
    },
    "grundsteuer_bayern": {
        "reihenfolge": 5,
        "bezeichnung": "Bayerische Grundsteuererklärung",
        "system": "separate Landesdatenart",
    },
    "grundsteuer_rechtsbehelf_bayern": {
        "reihenfolge": 5,
        "bezeichnung": "Bayerischer Grundsteuer-Rechtsbehelf",
        "system": "kein Einkommensteuerformular",
    },
}


def validiere_verfahrensrouting(mapping: dict | None = None) -> dict:
    mapping = lade_mapping() if mapping is None else mapping
    fehler = []
    ids = []
    for fall in mapping.get("faelle", []):
        fall_id = str(fall.get("id", ""))
        ids.append(fall_id)
        schluessel = fall.get("verfahrensschluessel")
        if schluessel not in VERFAHREN:
            fehler.append(f"{fall_id}: unbekannter Verfahrensschlüssel {schluessel!r}.")
        if fall.get("prioritaet") not in {1, 2, 3, 4, 5}:
            fehler.append(f"{fall_id}: ungültige Priorität.")
        elif schluessel in VERFAHREN and fall["prioritaet"] != VERFAHREN[schluessel]["reihenfolge"]:
            fehler.append(f"{fall_id}: Priorität widerspricht dem Verfahrensplan.")
        if fall.get("eric_relevanz") is None:
            fehler.append(f"{fall_id}: ERiC-Relevanz fehlt.")
    if len(ids) != 14 or len(set(ids)) != 14:
        fehler.append("Das Routing muss genau 14 eindeutige Kernfälle umfassen.")
    return {"bestanden": not fehler, "faelle": len(ids), "fehler": fehler}


def erstelle_verfahrensplan(mapping: dict | None = None) -> dict:
    mapping = lade_mapping() if mapping is None else mapping
    routing = validiere_verfahrensrouting(mapping)
    if not routing["bestanden"]:
        raise ValueError("Ungültiges Verfahrensrouting: " + "; ".join(routing["fehler"]))

    gruppen = []
    for schluessel, meta in sorted(
        VERFAHREN.items(), key=lambda eintrag: (eintrag[1]["reihenfolge"], eintrag[0])
    ):
        faelle = [
            {
                "id": fall["id"],
                "thema": fall["thema"],
                "formularbereich": fall["formularbereich"],
                "eric_relevanz": fall["eric_relevanz"],
                "mapping_status": (
                    "offen_bis_amtliches_schema"
                    if fall["eric_relevanz"] in {"schema_mapping", "separate_datenart"}
                    else "kein_direktes_schema_mapping"
                ),
            }
            for fall in mapping["faelle"]
            if fall["verfahrensschluessel"] == schluessel
        ]
        if not faelle:
            continue
        gruppen.append({
            "verfahrensschluessel": schluessel,
            "reihenfolge": meta["reihenfolge"],
            "bezeichnung": meta["bezeichnung"],
            "system": meta["system"],
            "versandfaehig": False,
            "faelle": faelle,
        })

    est_schluessel = {
        "est_2025_anlage_n",
        "est_2025_anlage_v",
        "est_2025_aussergewoehnliche_belastungen",
        "est_2025_einkommensersatzleistungen",
    }
    est_faelle = sum(
        len(gruppe["faelle"])
        for gruppe in gruppen
        if gruppe["verfahrensschluessel"] in est_schluessel
    )
    return {
        "format": "steuer-assistent-elster-verfahrensplan/v1",
        "steuerjahr": mapping["steuerjahr"],
        "amtliches_schema_validiert": False,
        "versandfaehig": False,
        "kernfaelle": routing["faelle"],
        "est_2025_kernfaelle": est_faelle,
        "gruppen": gruppen,
        "naechste_freigabestufe": {
            "umfang": "ESt 2025 – Anlage N, Anlage V und außergewöhnliche Belastungen",
            "faelle": sum(len(g["faelle"]) for g in gruppen if g["reihenfolge"] <= 2),
            "status": "gesperrt_bis_eric_sdk_und_xsd_validiert",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ausgabe", type=Path, help="Optionaler JSON-Berichtspfad.")
    args = parser.parse_args()
    plan = erstelle_verfahrensplan()
    if args.ausgabe:
        ziel = args.ausgabe if args.ausgabe.is_absolute() else ROOT / args.ausgabe
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
