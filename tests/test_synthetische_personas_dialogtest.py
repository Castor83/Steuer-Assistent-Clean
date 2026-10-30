"""Gezielte Tests fuer den Live-Dialogtest-Laeufer."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.error import URLError

import pytest
import synthetische_personas_dialogtest as dialogtest

from synthetische_personas_dialogtest import (
    Sitzung,
    baue_kontextnachricht,
    fuehre_dialogtest_aus,
    lade_testfaelle,
    mechanische_pruefung,
    vorpruefungsstatus,
)
from synthetische_personas_testserver import bereite_testdaten_vor


def test_lade_testfaelle_liefert_alle_57_dialogschritte() -> None:
    faelle = lade_testfaelle()

    assert len(faelle) == 57
    assert {fall["persona_id"] for fall in faelle} == {
        "leer_2025",
        "arbeitnehmerin_2025",
        "ehepaar_2025",
        "selbststaendig_2025",
        "gewerbe_2025",
        "investor_2025",
        "vermietung_2024",
        "insolvenzgeld_2023",
    }
    assert sum(bool(fall["originalfrage"]) for fall in faelle) == 11


def test_kontextnachricht_kennzeichnet_synthetische_daten_und_offene_werte() -> None:
    fall = next(f for f in lade_testfaelle() if f["persona_id"] == "investor_2025")

    nachricht = baue_kontextnachricht(fall)

    assert "ausschließlich synthetischer Testfall" in nachricht
    assert "nicht einreichen" in nachricht.lower()
    assert "offen" in nachricht.lower()


def test_mechanische_pruefung_findet_leere_antwort_und_fehlende_quelle() -> None:
    gruende = mechanische_pruefung(
        antwort="",
        quellen=[],
        quellen_erforderlich=True,
    )

    assert "Antwort ist leer" in gruende
    assert "Erforderliche Quelle fehlt" in gruende


def test_mechanische_pruefung_akzeptiert_antwort_mit_quelle() -> None:
    gruende = mechanische_pruefung(
        antwort="Eine vorsichtige, verständliche Antwort [1].",
        quellen=[{"titel": "Amtliche Quelle"}],
        quellen_erforderlich=True,
    )

    assert gruende == []


def test_vorpruefung_bezeichnet_fachlich_unbewertete_antwort_nur_als_technisch_ok() -> None:
    assert vorpruefungsstatus([]) == "TECHNISCH_OK"
    assert vorpruefungsstatus(["Quelle fehlt"]) == "PRUEFEN"


def test_unbekannte_personaauswahl_wird_nicht_als_nulltest_akzeptiert() -> None:
    with pytest.raises(ValueError, match="Keine Dialogschritte"):
        fuehre_dialogtest_aus(
            basis_url="http://127.0.0.1:1",
            modus="kontext",
            nur_personas={"gibt-es-nicht"},
        )


def test_unbekannter_testmodus_wird_abgewiesen() -> None:
    with pytest.raises(ValueError, match="Unbekannter Dialogtest-Modus"):
        fuehre_dialogtest_aus(
            basis_url="http://127.0.0.1:1",
            modus="tippfehler",
        )


def test_nutzerwahl_prueft_cookie_profil_und_isolierten_eingangsordner(monkeypatch) -> None:
    sitzung = Sitzung("http://test.invalid")

    def fake_anfrage(pfad: str, payload=None) -> dict:
        if pfad == "/api/nutzer" and payload is None:
            return {
                "nutzer": [
                    {
                        "id": "synthetisch-arbeitnehmerin_2025",
                        "name": "Testperson Alma Beispiel",
                    }
                ],
                "aktiv": {
                    "id": "synthetisch-arbeitnehmerin_2025",
                    "name": "Testperson Alma Beispiel",
                },
            }
        if pfad == "/api/nutzer/wechseln":
            assert payload == {"nutzer_id": "synthetisch-arbeitnehmerin_2025"}
            return {
                "nutzer": {
                    "id": "synthetisch-arbeitnehmerin_2025",
                    "name": "Testperson Alma Beispiel",
                }
            }
        if pfad == "/api/steuerprofil":
            return {
                "steuerjahr_vorschlag": "2025",
                "steuerjahr_status": "Synthetischer Testfall",
            }
        if pfad == "/api/eingangsordner":
            return {
                "pfad": r"C:\Temp\dialogtest\dokumente\nutzer\synthetisch-arbeitnehmerin_2025\eingang"
            }
        raise AssertionError(pfad)

    monkeypatch.setattr(sitzung, "anfrage", fake_anfrage)

    nachweis = sitzung.nutzer_waehlen(
        "Testperson Alma Beispiel",
        persona_id="arbeitnehmerin_2025",
        steuerjahr="2025",
    )

    assert nachweis["nutzer_id"] == "synthetisch-arbeitnehmerin_2025"
    assert nachweis["cookie_aktiv_bestaetigt"] is True
    assert nachweis["profil_steuerjahr_bestaetigt"] is True
    assert nachweis["eingangsordner_bestaetigt"] is True


def test_nutzerwahl_verwirft_falsches_cookie_profil(monkeypatch) -> None:
    sitzung = Sitzung("http://test.invalid")
    aufrufe = 0

    def fake_anfrage(pfad: str, payload=None) -> dict:
        nonlocal aufrufe
        if pfad == "/api/nutzer" and aufrufe == 0:
            aufrufe += 1
            return {
                "nutzer": [
                    {
                        "id": "synthetisch-arbeitnehmerin_2025",
                        "name": "Testperson Alma Beispiel",
                    }
                ],
                "aktiv": None,
            }
        if pfad == "/api/nutzer/wechseln":
            return {
                "nutzer": {
                    "id": "synthetisch-arbeitnehmerin_2025",
                    "name": "Testperson Alma Beispiel",
                }
            }
        if pfad == "/api/nutzer":
            return {
                "nutzer": [],
                "aktiv": {
                    "id": "synthetisch-investor_2025",
                    "name": "Testperson Alex Anlage",
                },
            }
        raise AssertionError(pfad)

    monkeypatch.setattr(sitzung, "anfrage", fake_anfrage)

    with pytest.raises(RuntimeError, match="Cookie.*falsche Nutzerprofil"):
        sitzung.nutzer_waehlen(
            "Testperson Alma Beispiel",
            persona_id="arbeitnehmerin_2025",
            steuerjahr="2025",
        )


def test_testserver_bereitet_profile_belege_und_finanzpositionen_vor(tmp_path) -> None:
    zusammenfassung = bereite_testdaten_vor(tmp_path)

    assert zusammenfassung == {"personas": 8, "belege": 23, "finanzpositionen": 30}
    index = (tmp_path / "daten" / "nutzer" / "index.json").read_text(encoding="utf-8")
    assert index.count('"id"') >= 8
    assert len(list((tmp_path / "dokumente" / "nutzer").glob("*/eingang/TEST-*"))) == 23

    erwartete_anzahlen = {
        "leer_2025": 0,
        "arbeitnehmerin_2025": 6,
        "ehepaar_2025": 5,
        "selbststaendig_2025": 4,
        "gewerbe_2025": 4,
        "investor_2025": 5,
        "vermietung_2024": 3,
        "insolvenzgeld_2023": 3,
    }
    erwartete_ids = {
        "leer_2025": [],
        "arbeitnehmerin_2025": [
            "alma_lohn",
            "alma_lohnsteuer",
            "alma_versicherung",
            "alma_arbeitsmittel",
            "alma_pendeln",
            "alma_homeoffice",
        ],
        "ehepaar_2025": [
            "mara_lohn",
            "mara_lohnsteuer",
            "jan_lohn",
            "jan_lohnsteuer",
            "paar_betreuung",
        ],
        "selbststaendig_2025": ["rio_einnahmen", "rio_ausgaben", "rio_software", "rio_ust"],
        "gewerbe_2025": ["kim_einnahmen", "kim_ausgaben", "kim_drucker", "kim_ust"],
        "investor_2025": [
            "alex_kapital",
            "alex_ausland",
            "alex_krypto_kauf",
            "alex_krypto_verkauf",
            "alex_krypto_gebuehr",
        ],
        "vermietung_2024": ["ben_miete", "ben_zinsen", "ben_grundsteuer"],
        "insolvenzgeld_2023": ["nia_lohn", "nia_rente", "nia_insolvenz"],
    }
    erwartete_jahre = {
        "leer_2025": "2025",
        "arbeitnehmerin_2025": "2025",
        "ehepaar_2025": "2025",
        "selbststaendig_2025": "2025",
        "gewerbe_2025": "2025",
        "investor_2025": "2025",
        "vermietung_2024": "2024",
        "insolvenzgeld_2023": "2023",
    }
    alle_ids: list[str] = []
    for persona_id, anzahl in erwartete_anzahlen.items():
        nutzer_id = f"synthetisch-{persona_id}"
        datei = tmp_path / "daten" / "nutzer" / nutzer_id / "finanzpositionen.json"
        daten = json.loads(datei.read_text(encoding="utf-8"))
        assert daten["kennzeichnung"].startswith("AUSSCHLIESSLICH SYNTHETISCHE TESTDATEN")
        assert len(daten["positionen"]) == anzahl
        assert [position["id"] for position in daten["positionen"]] == erwartete_ids[persona_id]
        assert all(
            position["steuerjahr"] == erwartete_jahre[persona_id]
            for position in daten["positionen"]
        )
        assert all(position["pruefstatus"] for position in daten["positionen"])
        belegnamen = {
            pfad.name
            for pfad in (tmp_path / "dokumente" / "nutzer" / nutzer_id / "eingang").iterdir()
        }
        positions_ids = {position["id"] for position in daten["positionen"]}
        assert all(position.get("beleg") in belegnamen for position in daten["positionen"])
        assert all(
            position.get("in_summe_von") in positions_ids
            for position in daten["positionen"]
            if position.get("in_summe_von")
        )
        alle_ids.extend(position["id"] for position in daten["positionen"])

    assert len(alle_ids) == len(set(alle_ids)) == 30
    alma = json.loads(
        (
            tmp_path
            / "daten"
            / "nutzer"
            / "synthetisch-arbeitnehmerin_2025"
            / "finanzpositionen.json"
        ).read_text(encoding="utf-8")
    )["positionen"]
    assert next(position for position in alma if position["id"] == "alma_lohn")[
        "pruefstatus"
    ] == "bestätigt"
    assert next(position for position in alma if position["id"] == "alma_homeoffice")[
        "pruefstatus"
    ] == "offen"


def test_fallkontextmodus_sendet_alle_57_schritte_ohne_kontextvorrede(monkeypatch) -> None:
    fragen: list[str] = []
    erste_verlaeufe: list[list[dict]] = []

    class FakeSitzung:
        def __init__(self, basis_url: str) -> None:
            self.fragenzahl = 0

        def anfrage(self, pfad: str, payload=None) -> dict:
            assert pfad == "/api/status"
            return {"bereit": True}

        def nutzer_waehlen(self, name: str, *, persona_id: str, steuerjahr: str) -> dict:
            return {
                "persona_id": persona_id,
                "nutzer_id": f"synthetisch-{persona_id}",
                "cookie_aktiv_bestaetigt": True,
                "profil_steuerjahr_bestaetigt": True,
                "eingangsordner_bestaetigt": True,
            }

        def frage(self, frage: str, verlauf: list[dict], steuerjahr: str) -> dict:
            if self.fragenzahl == 0:
                erste_verlaeufe.append(list(verlauf))
            self.fragenzahl += 1
            fragen.append(frage)
            return {"antwort": "Synthetische Testantwort", "quellen": [{"titel": "Testquelle"}]}

    monkeypatch.setattr(dialogtest, "Sitzung", FakeSitzung)

    bericht = fuehre_dialogtest_aus(
        basis_url="http://test.invalid",
        modus="fallkontext",
    )

    assert bericht["anzahl_dialogschritte"] == 57
    assert bericht["kontextantworten"] == []
    assert fragen == [fall["frage"] for fall in lade_testfaelle()]
    assert erste_verlaeufe == [[]] * 8


def test_testserver_verweigert_den_projektordner_als_testziel() -> None:
    projektordner = Path(__file__).resolve().parents[1]

    with pytest.raises(ValueError, match="außerhalb des Projekts"):
        bereite_testdaten_vor(projektordner)


def test_spaeter_kontextfehler_bewahrt_bisherige_dialogergebnisse(monkeypatch) -> None:
    class FakeSitzung:
        def __init__(self, basis_url: str) -> None:
            self.nutzer = ""

        def anfrage(self, pfad: str, payload=None) -> dict:
            return {"bereit": True}

        def nutzer_waehlen(self, name: str, *, persona_id: str, steuerjahr: str) -> dict:
            self.nutzer = name
            return {
                "nutzer_id": f"synthetisch-{persona_id}",
                "cookie_aktiv_bestaetigt": True,
                "profil_steuerjahr_bestaetigt": True,
                "eingangsordner_bestaetigt": True,
            }

        def frage(self, frage: str, verlauf: list[dict], steuerjahr: str) -> dict:
            if self.nutzer == "Testperson Nia Probe" and "synthetischer Testfall" in frage:
                raise URLError("absichtlicher Testfehler")
            return {"antwort": "Synthetische Testantwort", "quellen": [{"titel": "Testquelle"}]}

    monkeypatch.setattr(dialogtest, "Sitzung", FakeSitzung)

    bericht = fuehre_dialogtest_aus(
        basis_url="http://test.invalid",
        modus="kontext",
    )

    assert bericht["ergebnisse"]
    assert bericht["persona_fehler"] == [
        {
            "persona_id": "insolvenzgeld_2023",
            "fehler": "<urlopen error absichtlicher Testfehler>",
        }
    ]
