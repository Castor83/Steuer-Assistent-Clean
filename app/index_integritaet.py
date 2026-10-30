"""Prüft den lokalen Quellenkarten-Index ohne ihn zu verändern."""

from __future__ import annotations

import argparse
import json

from qdrant_client import QdrantClient

from wissen_import_quellen import (
    QDRANT_ORDNER,
    pruefe_index_integritaet,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Gibt den Prüfbericht als JSON aus.")
    args = parser.parse_args()
    client = QdrantClient(path=QDRANT_ORDNER)
    try:
        ergebnis = pruefe_index_integritaet(client)
    finally:
        client.close()
    if args.json:
        print(json.dumps(ergebnis, ensure_ascii=False, indent=2))
    else:
        status = "BESTANDEN" if ergebnis["bestanden"] else "FEHLGESCHLAGEN"
        print(
            f"INDEX-INTEGRITÄT {status}: "
            f"{ergebnis['erwartete_quellkarten']} Karten, "
            f"{ergebnis['erwartete_chunks']} erwartete Chunks, "
            f"{ergebnis['vorhandene_quellenpunkte']} Vektorpunkte."
        )
    return 0 if ergebnis["bestanden"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
