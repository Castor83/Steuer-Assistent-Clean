"""Verifiziert den freigegebenen RAG-Golden-Master ohne Modellaufruf."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

from wissen_import_quellen import erwartete_index_payloads, lade_quellen


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tests" / "golden_master" / "golden_master_rag_v1.json"


def _sha256(pfad: Path) -> str:
    return sha256(pfad.read_bytes()).hexdigest()


def pruefe_golden_master(require_reports: bool = False) -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    fehler = []
    for gruppe, pruefsummen in (
        ("katalog_pruefsumme", manifest["katalog_pruefsummen"]),
        ("implementierungs_pruefsumme", manifest["implementierungs_pruefsummen"]),
    ):
        for relativ, erwartet in pruefsummen.items():
            pfad = ROOT / relativ
            vorhanden = _sha256(pfad) if pfad.is_file() else None
            if vorhanden != erwartet:
                fehler.append({
                    "typ": gruppe,
                    "pfad": relativ,
                    "erwartet": erwartet,
                    "vorhanden": vorhanden,
                })

    quellen = lade_quellen()
    payloads = erwartete_index_payloads(quellen)
    erwartete_karten = manifest["index"]["quellenkarten"]
    erwartete_chunks = manifest["index"]["regelchunks"]
    if len(quellen) != erwartete_karten:
        fehler.append({
            "typ": "quellenkarten_anzahl",
            "erwartet": erwartete_karten,
            "vorhanden": len(quellen),
        })
    if len(payloads) != erwartete_chunks:
        fehler.append({
            "typ": "regelchunk_anzahl",
            "erwartet": erwartete_chunks,
            "vorhanden": len(payloads),
        })
    kanonisch = json.dumps(
        payloads,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    sollzustand_hash = sha256(kanonisch).hexdigest()
    erwarteter_sollzustand_hash = manifest["index"]["sollzustand_sha256"]
    if sollzustand_hash != erwarteter_sollzustand_hash:
        fehler.append({
            "typ": "index_sollzustand_pruefsumme",
            "erwartet": erwarteter_sollzustand_hash,
            "vorhanden": sollzustand_hash,
        })

    bericht_status = []
    for relativ, erwartet in manifest["abnahmeberichte"].items():
        pfad = ROOT / relativ
        vorhanden = _sha256(pfad) if pfad.is_file() else None
        bericht_status.append({
            "pfad": relativ,
            "vorhanden": pfad.is_file(),
            "pruefsumme_ok": vorhanden == erwartet if vorhanden else None,
        })
        if require_reports and vorhanden != erwartet:
            fehler.append({
                "typ": "abnahmebericht_pruefsumme",
                "pfad": relativ,
                "erwartet": erwartet,
                "vorhanden": vorhanden,
            })

    return {
        "bestanden": not fehler,
        "golden_master_id": manifest["id"],
        "quellenkarten": len(quellen),
        "regelchunks": len(payloads),
        "index_sollzustand_sha256": sollzustand_hash,
        "abnahmeberichte": bericht_status,
        "fehler": fehler,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-reports",
        action="store_true",
        help="Verlangt zusätzlich die unveränderten lokalen Abnahmeberichte.",
    )
    args = parser.parse_args()
    ergebnis = pruefe_golden_master(require_reports=args.require_reports)
    print(json.dumps(ergebnis, ensure_ascii=False, indent=2))
    return 0 if ergebnis["bestanden"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
