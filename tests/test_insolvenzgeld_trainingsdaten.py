import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import insolvenzgeld_trainingsdaten


def test_insolvenzgeld_paket_ist_getrennt_und_enthaelt_keine_fachantworten():
    manifest = insolvenzgeld_trainingsdaten.erstellen()
    ziel = ROOT / "testDaten" / "umgangssprache_steuer_training" / "insolvenzgeld_arbeitnehmer"
    assert manifest["train_gesamt"] == 256
    assert manifest["zusaetzliche_trainingsanker"] == 96
    assert manifest["validation"] == 24
    assert manifest["control"] == 24
    assert manifest["hard_control"] == 8
    assert manifest["fachantworten_enthalten"] is False

    sammlungen = {}
    for split in ("train", "validation", "control"):
        pfad = ziel / f"insolvenzgeld_{split}.jsonl"
        sammlungen[split] = [json.loads(zeile) for zeile in pfad.read_text(encoding="utf-8").splitlines()]
        assert all(eintrag["messages"][-1]["role"] == "assistant" for eintrag in sammlungen[split])

    ids = {
        split: {
            eintrag["metadaten"]["basisfall"]
            for eintrag in daten
            if eintrag["id"].startswith("insolvenzgeld-")
        }
        for split, daten in sammlungen.items()
    }
    assert ids["train"].isdisjoint(ids["validation"])
    assert ids["train"].isdisjoint(ids["control"])
    assert ids["validation"].isdisjoint(ids["control"])

    hard_control = [
        json.loads(zeile)
        for zeile in (ziel / "insolvenzgeld_hard_control.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(hard_control) == 8
    assert all(eintrag.get("detailregeln") for eintrag in hard_control)


def test_typischer_tippfehler_wird_auf_insolvenzgeld_kanonisiert():
    ziel = ROOT / "testDaten" / "umgangssprache_steuer_training" / "insolvenzgeld_arbeitnehmer"
    daten = [
        json.loads(zeile)
        for zeile in (ziel / "insolvenzgeld_train.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    treffer = [
        eintrag
        for eintrag in daten
        if "insolvebtsgeld" in eintrag["messages"][-2]["content"].casefold()
    ]
    assert treffer
    assert all("Insolvenzgeld" in eintrag["messages"][-1]["content"] for eintrag in treffer)
