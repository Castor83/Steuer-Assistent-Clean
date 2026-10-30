"""Mischt neue Mehrschritt-Dialoge mit bewährten Pilot-09-Ausgleichsdaten."""

from __future__ import annotations

import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATEN = ROOT / "testDaten" / "umgangssprache_steuer_training"


def laden(name: str) -> list[dict]:
    return [
        json.loads(zeile)
        for zeile in (DATEN / name).read_text(encoding="utf-8").splitlines()
        if zeile.strip()
    ]


def schreiben(name: str, eintraege: list[dict]) -> None:
    with (DATEN / name).open("w", encoding="utf-8", newline="\n") as datei:
        for eintrag in eintraege:
            datei.write(json.dumps(eintrag, ensure_ascii=False) + "\n")


def erstellen() -> dict:
    neu_train = laden("mehrschritt_train.jsonl")
    alt_train = laden("ausgleich_train.jsonl")
    neu_validation = laden("mehrschritt_validation.jsonl")
    alt_validation = laden("ausgleich_validation.jsonl")
    train = neu_train + alt_train
    validation = neu_validation + alt_validation
    random.Random(2026082813).shuffle(train)
    random.Random(2026082814).shuffle(validation)
    schreiben("mehrschritt_rehearsal_train.jsonl", train)
    schreiben("mehrschritt_rehearsal_validation.jsonl", validation)
    manifest = {
        "train": len(train),
        "validation": len(validation),
        "neue_mehrschritt_train": len(neu_train),
        "bewaehrte_ausgleich_train": len(alt_train),
        "neue_mehrschritt_validation": len(neu_validation),
        "bewaehrte_ausgleich_validation": len(alt_validation),
        "kontrolle_unberuehrt": [
            "mehrschritt_control.jsonl",
            "praxis_kanonisierung_test.jsonl",
            "praxis_kanonisierung_kontrolle_02.jsonl",
            "praxis_kanonisierung_kontrolle_03.jsonl"
        ]
    }
    (DATEN / "mehrschritt_rehearsal_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    print(json.dumps(erstellen(), ensure_ascii=False, indent=2))
