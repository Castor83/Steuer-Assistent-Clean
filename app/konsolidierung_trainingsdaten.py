"""Mischt die bisher besten, testgetrennten Trainingschargen ausgewogen."""

from __future__ import annotations

import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATEN = ROOT / "testDaten" / "umgangssprache_steuer_training"
QUELLEN = (
    ("praxisdialog_train.jsonl", 48),
    ("hardcases_train.jsonl", 36),
    ("kurzfolge_train.jsonl", 36),
    ("detailtreue_train.jsonl", 36),
    ("ausgleich_train.jsonl", 36),
)
VALIDIERUNG = (
    "praxisdialog_validation.jsonl",
    "hardcases_validation.jsonl",
    "kurzfolge_validation.jsonl",
    "detailtreue_validation.jsonl",
    "ausgleich_validation.jsonl",
)


def laden(name: str) -> list[dict]:
    return [json.loads(x) for x in (DATEN / name).read_text(encoding="utf-8").splitlines() if x.strip()]


def schreiben(name: str, eintraege: list[dict]) -> None:
    with (DATEN / name).open("w", encoding="utf-8", newline="\n") as datei:
        for eintrag in eintraege:
            datei.write(json.dumps(eintrag, ensure_ascii=False) + "\n")


def erstellen() -> dict:
    zufall = random.Random(20260827)
    train = []
    aufteilung = {}
    for name, anzahl in QUELLEN:
        quelle = laden(name)
        zufall.shuffle(quelle)
        auswahl = quelle[: min(anzahl, len(quelle))]
        train.extend(auswahl)
        aufteilung[name] = len(auswahl)
    zufall.shuffle(train)

    validation = []
    for name in VALIDIERUNG:
        validation.extend(laden(name))
    # Doppelte IDs oder versehentlich identische Nachrichten werden entfernt.
    eindeutig = {}
    for eintrag in validation:
        schluessel = json.dumps(eintrag.get("messages", []), ensure_ascii=False, sort_keys=True)
        eindeutig.setdefault(schluessel, eintrag)
    validation = list(eindeutig.values())
    zufall.shuffle(validation)

    schreiben("konsolidierung_train.jsonl", train)
    schreiben("konsolidierung_validation.jsonl", validation)
    return {"train": len(train), "validation": len(validation), "aufteilung": aufteilung}


if __name__ == "__main__":
    print(json.dumps(erstellen(), ensure_ascii=False, indent=2))
