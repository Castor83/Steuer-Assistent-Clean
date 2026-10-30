"""Erzeugt den getrennten SteuerEx-Härtetest aus dem unveränderten Download.

Der Katalog enthält bewusst keine erfundenen Sollantworten. Die Kennzeichnungen
zur Alltagsnähe sind eine grobe Vorauswahl nach Steuerart und kein Fachurteil.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUELLE = ROOT / "testDaten" / "Benchmark-Datensatz" / "benchmark-questions.json"
ZIEL = ROOT / "tests" / "steuerex_haertetest_115.json"
QUELLEN_URL = "https://huggingface.co/datasets/windprak/SteuerEx"
QUELLEN_SHA256 = "0d29e2817fd5d516049a18791c23744e00b56ceadb55f438dc2d3f94ba979a3a"

EHER_ALLTAGSNAH = {"Einkommensteuer", "Erbschaftsteuer", "Abgabenordnung"}
TEILWEISE_ALLTAGSNAH = {"Umsatzsteuer", "Internationales Steuerrecht"}


def pruefungsjahre(semester: str) -> tuple[int, int]:
    """Wandelt z. B. SS23 bzw. WS23/24 in vollständige Kalenderjahre um."""
    treffer = re.fullmatch(r"(SS|WS)(\d{2})(?:/(\d{2}))?", semester)
    if not treffer:
        raise ValueError(f"Unbekanntes Semesterformat: {semester}")
    erstes = 2000 + int(treffer.group(2))
    zweites = 2000 + int(treffer.group(3)) if treffer.group(3) else erstes
    return erstes, zweites


def altersklasse(bis_jahr: int) -> str:
    if bis_jahr <= 2020:
        return "2016–2020"
    if bis_jahr <= 2022:
        return "2021–2022"
    return "2023–2024"


def alltagskennzeichnung(kategorie: str) -> tuple[str, str, str]:
    if kategorie in EHER_ALLTAGSNAH:
        return (
            "eher_alltagsnah",
            "Privatpersonen",
            "Die Steuerart kann typische private Steuerfälle oder den Umgang mit dem Finanzamt betreffen.",
        )
    if kategorie in TEILWEISE_ALLTAGSNAH:
        return (
            "teilweise_alltagsnah",
            "Privatpersonen und Selbstständige",
            "Einzelne Fälle sind alltagsnah; viele Aufgaben setzen jedoch unternehmerisches Spezialwissen voraus.",
        )
    return (
        "spezialwissen",
        "Unternehmen und steuerliche Fachpraxis",
        "Die Steuerart betrifft überwiegend Unternehmen, Gesellschaften oder Umwandlungen.",
    )


def konvertiere(eintrag: dict) -> dict:
    von_jahr, bis_jahr = pruefungsjahre(eintrag["year"])
    alltagsnaehe, zielgruppe, begruendung = alltagskennzeichnung(eintrag["category"])
    return {
        "id": int(eintrag["id"]),
        "kategorie": eintrag["category"],
        "frage": eintrag["question"].strip(),
        "steuerex_pruefung": eintrag["exam"],
        "steuerex_semester": eintrag["year"],
        "steuerex_titel": eintrag["title"],
        "max_punkte": eintrag["max_score"],
        "pruefungsjahr_von": von_jahr,
        "pruefungsjahr_bis": bis_jahr,
        "altersklasse": altersklasse(bis_jahr),
        "alltagsnaehe": alltagsnaehe,
        "zielgruppe": zielgruppe,
        "alltagsnaehe_begruendung": begruendung,
        "aktualitaetsstatus": "historischer_pruefungsfall",
        "aktualitaetspruefung_erforderlich": True,
        "erwartete_antwort": None,
        "automatische_fachbewertung": False,
        "bewertungshinweis": (
            "Der veröffentlichte Datensatz enthält keine Musterlösung. Antworten dürfen vorerst nur "
            "strukturell geprüft und müssen für eine fachliche Bewertung manuell beurteilt werden."
        ),
        "quelle": "SteuerEx Benchmark Dataset",
        "quelle_datei": "testDaten/Benchmark-Datensatz/benchmark-questions.json",
        "quelle_url": QUELLEN_URL,
        "quelle_sha256": QUELLEN_SHA256,
        "paper": "https://arxiv.org/abs/2602.11081",
        "lizenz": "CC BY-NC 4.0",
        "nutzungsstatus": "nur_nichtkommerzieller_testbestand",
    }


def main() -> None:
    quell_bytes = QUELLE.read_bytes()
    ist_sha256 = hashlib.sha256(quell_bytes).hexdigest()
    if ist_sha256 != QUELLEN_SHA256:
        raise ValueError(
            "Die lokale SteuerEx-Datei weicht von der geprüften Originalfassung ab: "
            f"{ist_sha256}"
        )
    roh = json.loads(quell_bytes.decode("utf-8-sig"))
    if len(roh) != 115:
        raise ValueError(f"Erwartet wurden 115 SteuerEx-Fragen, gefunden wurden {len(roh)}.")
    katalog = [konvertiere(eintrag) for eintrag in roh]
    ids = [eintrag["id"] for eintrag in katalog]
    if len(ids) != len(set(ids)):
        raise ValueError("Der SteuerEx-Download enthält doppelte IDs.")
    ZIEL.write_text(json.dumps(katalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Erstellt: {ZIEL}")
    print(f"Fragen: {len(katalog)}")
    print("Alltagsnähe:", dict(sorted(Counter(x["alltagsnaehe"] for x in katalog).items())))
    print("Altersklassen:", dict(sorted(Counter(x["altersklasse"] for x in katalog).items())))


if __name__ == "__main__":
    main()
