"""Unveränderte Praxischarge auswerten, ohne Antworten zu optimieren."""

from __future__ import annotations

from collections import Counter
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import sys
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import rag_assistent


KATALOG = Path(__file__).with_name("praxischarge_50.json")


def normalisiere(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(z for z in text if not unicodedata.combining(z))
    return " ".join(re.findall(r"[a-z0-9]+", text))


def vorhandene_fragen() -> list[str]:
    fragen = []
    for pfad in (ROOT / "tests").glob("*.json"):
        if pfad == KATALOG:
            continue
        try:
            daten = json.loads(pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        stapel = [daten]
        while stapel:
            wert = stapel.pop()
            if isinstance(wert, dict):
                if isinstance(wert.get("frage"), str):
                    fragen.append(wert["frage"])
                stapel.extend(wert.values())
            elif isinstance(wert, list):
                stapel.extend(wert)
    return fragen


def pruefe_unabhaengigkeit(faelle: list[dict]) -> list[str]:
    fehler = []
    bestand = [normalisiere(frage) for frage in vorhandene_fragen()]
    chargenfragen = [normalisiere(fall["frage"]) for fall in faelle]
    if len(set(chargenfragen)) != len(chargenfragen):
        fehler.append("Die Charge enthält doppelte Fragen.")
    for fall, frage in zip(faelle, chargenfragen):
        aehnlichkeit = max(
            (SequenceMatcher(None, frage, alt).ratio() for alt in bestand),
            default=0.0,
        )
        if aehnlichkeit >= 0.92:
            fehler.append(f"{fall['id']}: zu ähnlich zum Altbestand ({aehnlichkeit:.3f})")
    return fehler


def pruefe_fall(fall: dict) -> dict:
    ergebnis = rag_assistent.beantworte_mit_status(
        fall["frage"], steuerjahr=fall["steuerjahr"], steuerprofil={}
    )
    text = ergebnis.text.casefold()
    fehler = []
    if ergebnis.status.value != fall["erwartet"]:
        fehler.append(f"Status {ergebnis.status.value} statt {fall['erwartet']}")
    if fall.get("muss_eines") and not any(
        wort.casefold() in text for wort in fall["muss_eines"]
    ):
        fehler.append("keines der erwarteten Merkmale vorhanden")
    for wort in fall.get("darf_nicht", []):
        if wort.casefold() in text:
            fehler.append(f"unzulässig: {wort}")
    if ergebnis.status.value == "ANTWORT" and not ergebnis.quellen:
        fehler.append("Fachantwort ohne Quelle")
    if ergebnis.status.value != "ANTWORT" and ergebnis.quellen:
        fehler.append("Rückfrage/Ablehnung mit Fachquellen")
    return {
        "id": fall["id"], "thema": fall["thema"],
        "erwartet": fall["erwartet"], "status": ergebnis.status.value,
        "bestanden": not fehler, "fehler": fehler,
        "antwort": ergebnis.text,
        "quellen": [q.payload.get("datei") or q.payload.get("url", "") for q in ergebnis.quellen],
    }


def main() -> int:
    faelle = json.loads(KATALOG.read_text(encoding="utf-8"))
    strukturfehler = []
    if len(faelle) != 50:
        strukturfehler.append(f"Erwartet 50 Fälle, gefunden {len(faelle)}")
    verteilung = Counter(fall["erwartet"] for fall in faelle)
    if verteilung != Counter({"ANTWORT": 20, "RUECKFRAGE": 20, "ABLEHNUNG": 10}):
        strukturfehler.append(f"Falsche Statusverteilung: {dict(verteilung)}")
    strukturfehler.extend(pruefe_unabhaengigkeit(faelle))
    if strukturfehler:
        print("\n".join(f"STRUKTURFEHLER {fehler}" for fehler in strukturfehler))
        return 2

    ergebnisse = []
    for fall in faelle:
        ergebnis = pruefe_fall(fall)
        ergebnisse.append(ergebnis)
        print(f"{fall['id']}: {'BESTANDEN' if ergebnis['bestanden'] else 'FEHLER'}", flush=True)
    ausgabe = ROOT / "tests" / "ergebnisse" / "praxischarge_50_aktuell.json"
    ausgabe.write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=2), encoding="utf-8")
    bestanden = sum(fall["bestanden"] for fall in ergebnisse)
    status = Counter(fall["status"] for fall in ergebnisse)
    print(f"UNABHÄNGIGKEIT bestanden; Verteilung {dict(verteilung)}")
    print(f"ERGEBNIS {bestanden}/50 bestanden; Ausgaben {dict(status)}")
    print(f"BERICHT {ausgabe}")
    for fall in ergebnisse:
        if not fall["bestanden"]:
            print(f"FEHLER {fall['id']} {fall['thema']}: {', '.join(fall['fehler'])}")
    return 0 if bestanden == 50 else 1


if __name__ == "__main__":
    raise SystemExit(main())
