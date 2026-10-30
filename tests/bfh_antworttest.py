"""Prüft fertige Chatantworten über die lokale HTTP-Oberfläche."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KATALOG = Path(__file__).with_name("bfh_pilot_katalog_30.json")
BERICHT = PROJECT_ROOT / "testDaten" / "bfh_rag_pilot" / "bfh_antworttest_20.json"
NEGATIVE_IDS = {16, 17, 18, 20, 30}


def lade_testfaelle() -> list[dict]:
    katalog = json.loads(KATALOG.read_text(encoding="utf-8"))
    return [
        fall for fall in katalog
        if fall["erwartet"] == "treffer" or fall["id"] in NEGATIVE_IDS
    ]


def pruefe_antwort(fall: dict, daten: dict) -> list[str]:
    fehler = []
    antwort = str(daten.get("antwort", ""))
    quellen = daten.get("quellen", [])
    gesamter_quellentext = " ".join(
        " ".join(str(quelle.get(feld, "")) for feld in ("titel", "paragraph", "url"))
        for quelle in quellen
        if isinstance(quelle, dict)
    )

    if not antwort.strip():
        fehler.append("Antwort fehlt")
    if fall["erwartet"] == "treffer":
        aktenzeichen = fall["aktenzeichen"]
        erwartete_teile = (
            aktenzeichen,
            "Bundesfinanzhof",
            "historischer Einzelfall",
            "amtliche Leitsatz",
            "aktuellen Gesetzesstands",
        )
        for teil in erwartete_teile:
            if teil not in antwort:
                fehler.append(f"Antwort enthält nicht: {teil}")
        if aktenzeichen not in gesamter_quellentext:
            fehler.append("Aktenzeichen fehlt in den Quellen")
        if "bundesfinanzhof.de" not in gesamter_quellentext:
            fehler.append("BFH-Link fehlt")
        if "Bundesfinanzgericht" in antwort:
            fehler.append("falsche Gerichtsbezeichnung")
    else:
        verbotene_teile = (
            "Ergänzende BFH-Rechtsprechung",
            "historischer Einzelfall",
            "Bundesfinanzhof entschied",
        )
        for teil in verbotene_teile:
            if teil in antwort:
                fehler.append(f"unerwarteter BFH-Hinweis: {teil}")
        if "bundesfinanzhof.de" in gesamter_quellentext:
            fehler.append("unerwartete BFH-Quelle")
    return fehler


def sende_frage(url: str, frage: str, timeout: float) -> tuple[dict, float]:
    inhalt = json.dumps({"frage": frage, "verlauf": []}, ensure_ascii=False).encode("utf-8")
    anfrage = Request(url, data=inhalt, headers={"Content-Type": "application/json"})
    start = time.perf_counter()
    with urlopen(anfrage, timeout=timeout) as antwort:
        daten = json.loads(antwort.read().decode("utf-8"))
    return daten, round(time.perf_counter() - start, 3)


def main() -> int:
    parser = argparse.ArgumentParser(description="BFH-End-to-End-Antworttest")
    parser.add_argument("--url", default="http://127.0.0.1:8765/api/frage")
    parser.add_argument("--bericht", type=Path, default=BERICHT)
    parser.add_argument("--timeout", type=float, default=90.0)
    argumente = parser.parse_args()

    ergebnisse = []
    try:
        for fall in lade_testfaelle():
            daten, dauer = sende_frage(argumente.url, fall["frage"], argumente.timeout)
            fehler = pruefe_antwort(fall, daten)
            ergebnisse.append({
                **fall,
                "dauer_sekunden": dauer,
                "antwort": daten.get("antwort", ""),
                "quellen": daten.get("quellen", []),
                "bestanden": not fehler,
                "fehler": fehler,
            })
            status = "OK" if not fehler else "FEHLER"
            print(f"{status} {fall['id']:02d} ({dauer:.3f}s): {fall['frage']}")
    except (HTTPError, URLError, TimeoutError) as fehler:
        print(f"Die lokale BFH-Testoberfläche ist nicht erreichbar: {fehler}")
        return 2

    zusammenfassung = {
        "zeitpunkt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "gesamt": len(ergebnisse),
        "bestanden": sum(fall["bestanden"] for fall in ergebnisse),
        "fehlgeschlagen": sum(not fall["bestanden"] for fall in ergebnisse),
        "bfh_antworten": sum(fall["erwartet"] == "treffer" for fall in ergebnisse),
        "kontrollantworten": sum(fall["erwartet"] == "kein_treffer" for fall in ergebnisse),
        "gesamtdauer_sekunden": round(sum(fall["dauer_sekunden"] for fall in ergebnisse), 3),
    }
    argumente.bericht.write_text(
        json.dumps({"zusammenfassung": zusammenfassung, "faelle": ergebnisse}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(zusammenfassung, ensure_ascii=False, indent=2))
    return 0 if zusammenfassung["fehlgeschlagen"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
