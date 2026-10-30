"""Vertrag fuer den umfangreichen Dialogtest der synthetischen Personas."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PERSONAS_DATEI = ROOT / "testDaten" / "synthetische_personas" / "personas.json"
DIALOGMATRIX_DATEI = ROOT / "testDaten" / "synthetische_personas" / "dialogtests.json"


def lade_json(pfad: Path) -> dict:
    return json.loads(pfad.read_text(encoding="utf-8"))


def test_dialogmatrix_deckt_alle_personas_umfangreich_ab() -> None:
    personas = lade_json(PERSONAS_DATEI)["personas"]
    matrix = lade_json(DIALOGMATRIX_DATEI)
    dialoge = matrix["personas"]

    assert matrix["kennzeichnung"] == "AUSSCHLIESSLICH SYNTHETISCHE TESTDATEN – NICHT EINREICHEN"
    assert {eintrag["persona_id"] for eintrag in dialoge} == {persona["id"] for persona in personas}
    assert all(len(eintrag["dialoge"]) >= 5 for eintrag in dialoge)
    assert sum(len(eintrag["dialoge"]) for eintrag in dialoge) >= 50


def test_alle_originalfragen_sind_genau_einmal_enthalten() -> None:
    personas = lade_json(PERSONAS_DATEI)["personas"]
    matrix = lade_json(DIALOGMATRIX_DATEI)

    erwartet = {
        (persona["id"], frage)
        for persona in personas
        for frage in persona.get("testfragen", [])
    }
    tatsaechlich = [
        (eintrag["persona_id"], schritt["frage"])
        for eintrag in matrix["personas"]
        for schritt in eintrag["dialoge"]
        if schritt.get("originalfrage")
    ]

    assert len(tatsaechlich) == len(set(tatsaechlich))
    assert set(tatsaechlich) == erwartet


def test_jeder_dialogschritt_hat_eine_pruefbare_erwartung() -> None:
    matrix = lade_json(DIALOGMATRIX_DATEI)
    ids: list[str] = []

    for eintrag in matrix["personas"]:
        assert eintrag["gesicherter_kontext"].strip()
        for schritt in eintrag["dialoge"]:
            ids.append(schritt["id"])
            assert schritt["frage"].strip()
            assert schritt["erwartung"].strip()
            assert isinstance(schritt["quellen_erforderlich"], bool)
            assert schritt["kategorien"]

    assert len(ids) == len(set(ids))


def test_investorpruefung_haelt_krypto_und_ausland_offen() -> None:
    matrix = lade_json(DIALOGMATRIX_DATEI)
    investor = next(e for e in matrix["personas"] if e["persona_id"] == "investor_2025")
    relevante_schritte = {
        schritt["id"]: schritt for schritt in investor["dialoge"] if schritt["id"] in {"I3", "I4", "I5", "I6", "I7"}
    }

    assert set(relevante_schritte) == {"I3", "I4", "I5", "I6", "I7"}
    assert all("offen_halten" in schritt["kategorien"] for schritt in relevante_schritte.values())


def test_dialogmatrix_enthaelt_explizite_personentrennung() -> None:
    matrix = lade_json(DIALOGMATRIX_DATEI)
    trennung = [
        schritt
        for eintrag in matrix["personas"]
        for schritt in eintrag["dialoge"]
        if "personentrennung" in schritt["kategorien"]
    ]

    assert len(trennung) >= 2
