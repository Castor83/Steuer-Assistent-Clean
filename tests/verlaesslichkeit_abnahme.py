"""Unabhängige Abnahme für Antwort, Rückfrage und sichere Ablehnung.

Der Katalog ist absichtlich kein Pytest-Modul. Während der Konsolidierung dient
er als unveränderte Baseline. Erst wenn alle Fälle bestehen, wird er zum
verbindlichen Regressionstest.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import rag_assistent


KATALOG = Path(__file__).with_name("verlaesslichkeit_abnahme.json")


def _entscheidung(text: str, quellen: list) -> str:
    klein = text.casefold().strip()
    if not quellen and (
        "keine steuerliche behauptung" in klein
        or "nicht beantworten" in klein
        or "weder im geprüften" in klein
    ):
        return "ABLEHNUNG"
    if "?" in text:
        return "RUECKFRAGE"
    return "ANTWORT"


def pruefe_fall(fall: dict) -> dict:
    antwort, quellen = rag_assistent.beantworte(
        fall["frage"], steuerjahr=fall.get("steuerjahr"), steuerprofil={}
    )
    klein = antwort.casefold()
    fehler = []
    entscheidung = _entscheidung(antwort, quellen)
    if entscheidung != fall["erwartet"]:
        fehler.append(f"Entscheidung {entscheidung} statt {fall['erwartet']}")
    for begriff in fall.get("muss", []):
        if begriff.casefold() not in klein:
            fehler.append(f"fehlt: {begriff}")
    if fall.get("muss_eines") and not any(
        begriff.casefold() in klein for begriff in fall["muss_eines"]
    ):
        fehler.append("keiner der erwarteten Begriffe vorhanden")
    for begriff in fall.get("darf_nicht", []):
        if begriff.casefold() in klein:
            fehler.append(f"unzulässig: {begriff}")
    return {
        "id": fall["id"],
        "bestanden": not fehler,
        "entscheidung": entscheidung,
        "fehler": fehler,
        "antwort": antwort,
        "quellen": [quelle.payload.get("datei", "") for quelle in quellen],
    }


def main() -> int:
    katalog = json.loads(KATALOG.read_text(encoding="utf-8"))
    ergebnisse = [pruefe_fall(fall) for fall in katalog]
    for ergebnis in ergebnisse:
        status = "BESTANDEN" if ergebnis["bestanden"] else "FEHLER"
        print(f"{status:9} {ergebnis['id']}: {', '.join(ergebnis['fehler'])}")
    bestanden = sum(ergebnis["bestanden"] for ergebnis in ergebnisse)
    print(f"\nZUSAMMENFASSUNG {bestanden}/{len(ergebnisse)} bestanden")
    ausgabe = ROOT / "tests" / "ergebnisse" / "verlaesslichkeit_baseline.json"
    ausgabe.parent.mkdir(parents=True, exist_ok=True)
    ausgabe.write_text(
        json.dumps(ergebnisse, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"BERICHT {ausgabe}")
    return 0 if bestanden == len(ergebnisse) else 1


if __name__ == "__main__":
    raise SystemExit(main())
