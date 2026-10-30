import json
import sys
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import mehrschritt_dialoge_300


def normalisiere(text: str) -> str:
    text = "".join(
        zeichen
        for zeichen in unicodedata.normalize("NFKD", str(text).casefold())
        if not unicodedata.combining(zeichen)
    )
    return " ".join(text.split())


def laden(split: str) -> list[dict]:
    pfad = mehrschritt_dialoge_300.ZIEL / f"dialoge_300_{split}.jsonl"
    return [json.loads(zeile) for zeile in pfad.read_text(encoding="utf-8").splitlines()]


def test_genau_300_dialoge_und_gepruefte_splits():
    manifest = mehrschritt_dialoge_300.erstellen()
    assert manifest["gesamt"] == 300
    assert (manifest["train"], manifest["validation"], manifest["control"]) == (220, 40, 40)
    assert manifest["fachlich_geprueft"] is True

    splits = {name: laden(name) for name in ("train", "validation", "control")}
    assert sum(map(len, splits.values())) == 300

    ids = [eintrag["id"] for eintraege in splits.values() for eintrag in eintraege]
    assert len(ids) == len(set(ids)) == 300

    basis_nach_split = {
        name: {eintrag["metadaten"]["basisfall"] for eintrag in eintraege}
        for name, eintraege in splits.items()
    }
    assert not (basis_nach_split["train"] & basis_nach_split["validation"])
    assert not (basis_nach_split["train"] & basis_nach_split["control"])
    assert not (basis_nach_split["validation"] & basis_nach_split["control"])
    assert {name: len(basen) for name, basen in basis_nach_split.items()} == {
        "train": 22,
        "validation": 4,
        "control": 4,
    }


def test_jeder_dialog_bewahrt_seine_geprueften_details():
    for split in ("train", "validation", "control"):
        for eintrag in laden(split):
            assert len(eintrag["messages"]) == 5
            assert [nachricht["role"] for nachricht in eintrag["messages"]] == [
                "system",
                "user",
                "assistant",
                "user",
                "assistant",
            ]
            assert eintrag["metadaten"]["fachlich_geprueft"] is True
            assert eintrag["metadaten"]["split"] == split
            ziel = normalisiere(eintrag["messages"][-1]["content"])
            for detailgruppe in eintrag["detailregeln"]:
                assert any(normalisiere(detail) in ziel for detail in detailgruppe), (
                    eintrag["id"],
                    detailgruppe,
                    ziel,
                )


def test_zehn_sprachvarianten_je_grundfall_sind_unterschiedlich():
    gruppen: dict[str, list[str]] = {}
    for split in ("train", "validation", "control"):
        for eintrag in laden(split):
            basis = eintrag["metadaten"]["basisfall"]
            gruppen.setdefault(basis, []).append(eintrag["messages"][-2]["content"])

    assert len(gruppen) == 30
    for varianten in gruppen.values():
        assert len(varianten) == 10
        assert len(set(varianten)) == 10
