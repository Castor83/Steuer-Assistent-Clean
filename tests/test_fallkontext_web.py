"""Endpunkttests für die requestgebundene Übergabe des Fallkontexts."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import nutzerverwaltung  # noqa: E402
import web_ui  # noqa: E402


def _nutzerdateien(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    nutzerdaten = tmp_path / "daten" / "nutzer"
    nutzerdokumente = tmp_path / "dokumente" / "nutzer"
    index = nutzerdaten / "index.json"
    index.parent.mkdir(parents=True)
    index.write_text(
        json.dumps(
            {
                "version": 1,
                "nutzer": [
                    {"id": "nutzer-a", "name": "Alma"},
                    {"id": "nutzer-b", "name": "Berta"},
                ],
            }
        ),
        encoding="utf-8",
    )
    for nutzer_id, betrag, ort in (
        ("nutzer-a", "42000.00", "A-Stadt"),
        ("nutzer-b", "99000.00", "B-Stadt"),
    ):
        datenordner = nutzerdaten / nutzer_id
        eingang = nutzerdokumente / nutzer_id / "eingang"
        datenordner.mkdir(parents=True)
        eingang.mkdir(parents=True)
        (datenordner / "steuerprofil.json").write_text(
            json.dumps(
                {
                    "person": {"angestellter": True},
                    "wohnsitz": {"stadt": ort},
                    "steuererklaerung": {
                        "naechstes_zu_bearbeitendes_steuerjahr": "2025"
                    },
                }
            ),
            encoding="utf-8",
        )
        (datenordner / "dokumentregister.json").write_text("{}", encoding="utf-8")
        (datenordner / "einstellungen.json").write_text(
            json.dumps({"eingangsordner": str(eingang)}), encoding="utf-8"
        )
        (datenordner / "finanzpositionen.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "positionen": [
                        {
                            "id": f"{nutzer_id}-lohn",
                            "steuerjahr": "2025",
                            "art": "bruttoarbeitslohn",
                            "betrag_eur": betrag,
                            "pruefstatus": "bestätigt",
                            "wertart": "jahressumme",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    monkeypatch.setattr(nutzerverwaltung, "NUTZER_DATEN", nutzerdaten)
    monkeypatch.setattr(nutzerverwaltung, "NUTZER_DOKUMENTE", nutzerdokumente)
    monkeypatch.setattr(nutzerverwaltung, "NUTZER_INDEX", index)
    monkeypatch.setattr(nutzerverwaltung, "_AKTIVER_NUTZER", "nutzer-b")


def test_frage_endpoint_beantwortet_falldaten_aus_cookie_nutzer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _nutzerdateien(tmp_path, monkeypatch)
    monkeypatch.setattr(web_ui, "dialogantwort", Mock(side_effect=AssertionError("nicht aufrufen")))
    monkeypatch.setattr(web_ui, "beantworte", Mock(side_effect=AssertionError("nicht aufrufen")))
    web_ui.app.config["TESTING"] = True
    client = web_ui.app.test_client()
    client.set_cookie(web_ui.NUTZER_COOKIE, "nutzer-a")

    antwort = client.post(
        "/api/frage",
        json={
            "frage": "Welche Lohnwerte hast du für Alma?",
            "steuerjahr": "2025",
            "verlauf": [],
        },
    )

    assert antwort.status_code == 200
    payload = antwort.get_json()
    assert "42.000,00 Euro" in payload["antwort"]
    assert "99.000" not in payload["antwort"]
    assert payload["quellen"] == []


def test_frage_endpoint_reicht_fallkontext_und_vollprofil_an_fachdialog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _nutzerdateien(tmp_path, monkeypatch)
    dialog = Mock(return_value=None)
    fachdialog = Mock(return_value=("Gemischte Antwort [1].", []))
    monkeypatch.setattr(web_ui, "dialogantwort", dialog)
    monkeypatch.setattr(web_ui, "beantworte", fachdialog)
    web_ui.app.config["TESTING"] = True
    client = web_ui.app.test_client()
    client.set_cookie(web_ui.NUTZER_COOKIE, "nutzer-a")

    antwort = client.post(
        "/api/frage",
        json={
            "frage": "Wie wird mein Arbeitslohn steuerlich behandelt?",
            "steuerjahr": "2025",
            "verlauf": [{"rolle": "nutzer", "text": "Es geht um 2025."}],
        },
    )

    assert antwort.status_code == 200
    assert dialog.call_args.kwargs["steuerprofil"]["wohnsitz"]["stadt"] == "A-Stadt"
    assert "nutzer-a" in dialog.call_args.args[2]
    kwargs = fachdialog.call_args.kwargs
    assert kwargs["steuerprofil"]["wohnsitz"]["stadt"] == "A-Stadt"
    assert kwargs["fallkontext"]["werte"][0]["betrag_eur"] == "42000.00"
    assert kwargs["fallkontext"]["nutzer_name"] == "Alma"
