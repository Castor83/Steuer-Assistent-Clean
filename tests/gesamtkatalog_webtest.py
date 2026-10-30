"""Führt den rekonstruierten Gesamtkatalog gegen die lokale Weboberfläche aus."""

from __future__ import annotations

import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


STANDARD_KATALOG = Path(__file__).with_name("gesamtkatalog_105.json")
ENDPUNKT = "http://127.0.0.1:8765/api/frage"
UNSICHER = "Das kann ich anhand der vorhandenen Informationen nicht sicher beantworten"


def hat_fremdschrift(text: str) -> bool:
    return any("CJK" in unicodedata.name(zeichen, "") for zeichen in text)


def frage_stellen(frage: str) -> dict:
    anfrage = Request(
        ENDPUNKT,
        data=json.dumps({"frage": frage}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urlopen(anfrage, timeout=180) as antwort:
        return json.load(antwort)


def bewerte(daten: dict) -> str:
    antwort = str(daten.get("antwort", "")).strip()
    if not antwort:
        return "LEER"
    if UNSICHER in antwort:
        return "WISSEN_FEHLT"
    if hat_fremdschrift(antwort):
        return "SPRACHFEHLER"
    if not daten.get("quellen"):
        return "OHNE_QUELLE"
    return "ANTWORT_MIT_QUELLE"


def main() -> int:
    katalog = Path(sys.argv[1]) if len(sys.argv) > 1 else STANDARD_KATALOG
    faelle = json.loads(katalog.read_text(encoding="utf-8"))
    if len(sys.argv) > 2:
        ausgewaehlte_ids = {int(wert) for wert in sys.argv[2].split(",")}
        faelle = [fall for fall in faelle if fall["id"] in ausgewaehlte_ids]
    ergebnisse = []
    for fall in faelle:
        try:
            daten = frage_stellen(fall["frage"])
            status = bewerte(daten)
            eintrag = {
                "id": fall["id"],
                "kategorie": fall["kategorie"],
                "status": status,
                "quellen": len(daten.get("quellen", [])),
            }
        except (HTTPError, URLError, TimeoutError, ValueError) as fehler:
            eintrag = {
                "id": fall["id"],
                "kategorie": fall["kategorie"],
                "status": "TECHNISCHER_FEHLER",
                "fehler": str(fehler),
            }
        ergebnisse.append(eintrag)
        print(json.dumps(eintrag, ensure_ascii=False), flush=True)

    zaehler = Counter(eintrag["status"] for eintrag in ergebnisse)
    print("ZUSAMMENFASSUNG", json.dumps(dict(sorted(zaehler.items())), ensure_ascii=False))
    return 0 if set(zaehler) == {"ANTWORT_MIT_QUELLE"} else 1


if __name__ == "__main__":
    sys.exit(main())
