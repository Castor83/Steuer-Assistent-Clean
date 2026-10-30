"""Nicht schreibende OCR-/Kanonisierungsabnahme an einem echten Dokument."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from ordner_ueberwacher import erkenne_dokumenttyp, extrahiere_wertvorschlaege, lies_ocr_text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dokument", default=str(ROOT / "dokumente/eingang/20260909_160930.jpg"))
    parser.add_argument("--ausgabe", default=str(ROOT / "tests/ergebnisse/reale_ocr_abnahme.json"))
    args = parser.parse_args()
    dokument = Path(args.dokument).resolve()
    start = time.perf_counter()
    text, ocr_status = lies_ocr_text(dokument)
    dokumenttyp, grundlage, _, steuerjahr = erkenne_dokumenttyp(dokument)
    werte = extrahiere_wertvorschlaege(dokumenttyp, text, dokument)
    bericht = {
        "dokument": str(dokument),
        "sekunden": time.perf_counter() - start,
        "ocr_status": ocr_status,
        "textzeichen": len(text),
        "dokumenttyp": dokumenttyp,
        "grundlage": grundlage,
        "steuerjahr": steuerjahr,
        "wertvorschlaege": len(werte),
        "freigegeben": bool(text.strip()) and "konnte" not in ocr_status.lower(),
    }
    ziel = Path(args.ausgabe)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(json.dumps(bericht, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(bericht, ensure_ascii=False, indent=2))
    return 0 if bericht["freigegeben"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
