"""Lesende OCR-Stichprobe über die vorhandenen realen Dokumentarten."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from ordner_ueberwacher import erkenne_dokumenttyp


PFLICHTTYPEN = (
    "Elektronische Lohnsteuerbescheinigung",
    "Insolvenzgeldbescheinigung",
    "Mietvertrag",
    "Schornsteinfegerrechnung",
    "Gebäudeversicherungsunterlage",
    "Darlehenszinsbescheinigung",
    "Historische Grundstücks- und Gebäudedaten",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ausgabe",
        default=str(ROOT / "tests/ergebnisse/reale_ocr_stichprobe.json"),
    )
    args = parser.parse_args()
    register = json.loads((ROOT / "daten/dokumentregister.json").read_text(encoding="utf-8"))
    eintraege = list(register.values())
    ergebnisse = []
    for solltyp in PFLICHTTYPEN:
        kandidaten = [e for e in eintraege if e.get("dokumenttyp") == solltyp]
        vorhandene = [
            e for e in kandidaten if Path(str(e.get("pfad", ""))).is_file()
        ]
        start = time.perf_counter()
        if not vorhandene:
            ergebnisse.append({"solltyp": solltyp, "bestanden": False, "fehler": "Kein vorhandener Beleg"})
            continue
        pruefungen = []
        for vorhanden in vorhandene:
            ist, grundlage, ocr_status, steuerjahr = erkenne_dokumenttyp(Path(vorhanden["pfad"]))
            historisch_ok = solltyp != "Historische Grundstücks- und Gebäudedaten" or steuerjahr == "Nicht erkannt"
            pruefungen.append((vorhanden, ist, grundlage, ocr_status, steuerjahr, historisch_ok))
            if ist == solltyp and historisch_ok and "konnte" not in ocr_status.lower():
                break
        vorhanden, ist, grundlage, ocr_status, steuerjahr, historisch_ok = pruefungen[-1]
        ergebnisse.append({
            "dateiname": vorhanden["dateiname"],
            "solltyp": solltyp,
            "isttyp": ist,
            "grundlage": grundlage,
            "ocr_status": ocr_status,
            "steuerjahr": steuerjahr,
            "sekunden": round(time.perf_counter() - start, 3),
            "gepruefte_kandidaten": len(pruefungen),
            "bestanden": ist == solltyp and historisch_ok and "konnte" not in ocr_status.lower(),
        })
    bericht = {
        "anzahl": len(ergebnisse),
        "bestanden": sum(e["bestanden"] for e in ergebnisse),
        "vollstaendig_bestanden": all(e["bestanden"] for e in ergebnisse),
        "ergebnisse": ergebnisse,
    }
    ziel = Path(args.ausgabe)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(json.dumps(bericht, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(bericht, ensure_ascii=False, indent=2))
    return 0 if bericht["vollstaendig_bestanden"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
