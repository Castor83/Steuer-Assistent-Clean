"""Erzeugt aus einem lokalen SteuerEx-Testbericht die Server-Einreichung.

Das Ausgabeformat besteht ausschließlich aus Frage-ID und Modellantwort. Es
enthält weder Quellenmetadaten noch lokale Pfade oder andere Projektdaten.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Erzeugt eine SteuerEx-Einreichungsdatei.")
    parser.add_argument("bericht", type=Path)
    parser.add_argument("ausgabe", type=Path)
    argumente = parser.parse_args()

    bericht = json.loads(argumente.bericht.read_text(encoding="utf-8"))
    ergebnisse = bericht.get("ergebnisse", [])
    if len(ergebnisse) != 115:
        raise ValueError(f"Erwartet wurden 115 Antworten, gefunden wurden {len(ergebnisse)}.")

    einreichung: dict[str, str] = {}
    for eintrag in ergebnisse:
        kennung = str(eintrag["id"])
        antwort = str(eintrag.get("antwort", "")).strip()
        if not antwort:
            raise ValueError(f"Antwort {kennung} ist leer.")
        if kennung in einreichung:
            raise ValueError(f"Doppelte Frage-ID: {kennung}")
        einreichung[kennung] = antwort

    erwartete_ids = {str(kennung) for kennung in range(1001, 1116)}
    if set(einreichung) != erwartete_ids:
        fehlend = sorted(erwartete_ids - set(einreichung))
        unerwartet = sorted(set(einreichung) - erwartete_ids)
        raise ValueError(f"IDs stimmen nicht. Fehlend: {fehlend}; unerwartet: {unerwartet}")

    argumente.ausgabe.parent.mkdir(parents=True, exist_ok=True)
    argumente.ausgabe.write_text(
        json.dumps(einreichung, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Einreichungsdatei erstellt: {argumente.ausgabe}")
    print(f"Antworten: {len(einreichung)}")


if __name__ == "__main__":
    main()
