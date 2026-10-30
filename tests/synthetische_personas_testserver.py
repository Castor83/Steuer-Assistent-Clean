"""Startet eine lokale Web-Testinstanz mit vollständig isolierten Testprofilen."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
PERSONAS_DATEI = ROOT / "testDaten" / "synthetische_personas" / "personas.json"
FINANZDATEN_DATEI = ROOT / "testDaten" / "synthetische_personas" / "finanzdaten.json"


def _schreibe_json(pfad: Path, daten) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")


def _lade_finanzfaelle(personas: list[dict]) -> tuple[dict[str, list[dict]], str]:
    daten = json.loads(FINANZDATEN_DATEI.read_text(encoding="utf-8"))
    faelle = daten.get("faelle", [])
    if not isinstance(faelle, list):
        raise ValueError("Die synthetischen Finanzdaten enthalten keine Fallliste.")

    persona_index = {str(persona.get("id", "")): persona for persona in personas}
    finanzfaelle: dict[str, list[dict]] = {}
    alle_positions_ids: set[str] = set()
    for fall in faelle:
        if not isinstance(fall, dict):
            raise ValueError("Ein synthetischer Finanzfall ist ungültig.")
        persona_id = str(fall.get("persona_id", ""))
        if persona_id not in persona_index or persona_id in finanzfaelle:
            raise ValueError(f"Ungültige oder doppelte Persona in Finanzdaten: {persona_id!r}")
        steuerjahr = str(fall.get("steuerjahr", ""))
        persona = persona_index[persona_id]
        if steuerjahr != str(persona.get("steuerjahr", "")):
            raise ValueError(f"Abweichendes Steuerjahr in Finanzdaten für {persona_id}.")

        belegnamen = {
            str(beleg.get("dateiname", ""))
            for beleg in persona.get("belege", [])
            if isinstance(beleg, dict)
        }
        positionen_roh = fall.get("positionen", [])
        if not isinstance(positionen_roh, list):
            raise ValueError(f"Ungültige Finanzpositionen für {persona_id}.")
        positionen: list[dict] = []
        lokale_ids: set[str] = set()
        for position_roh in positionen_roh:
            if not isinstance(position_roh, dict):
                raise ValueError(f"Ungültige Finanzposition für {persona_id}.")
            position = deepcopy(position_roh)
            position_id = str(position.get("id", ""))
            if not position_id or position_id in alle_positions_ids:
                raise ValueError(f"Fehlende oder doppelte Finanzpositions-ID: {position_id!r}")
            if position.get("steuerjahr") not in (None, "", steuerjahr):
                raise ValueError(f"Abweichendes Steuerjahr in Finanzposition {position_id}.")
            if str(position.get("beleg", "")) not in belegnamen:
                raise ValueError(f"Unbekannter Beleg in Finanzposition {position_id}.")
            position["steuerjahr"] = steuerjahr
            position.setdefault("pruefstatus", "bestätigt")
            positionen.append(position)
            lokale_ids.add(position_id)
            alle_positions_ids.add(position_id)

        for position in positionen:
            bezug = position.get("in_summe_von")
            if bezug and bezug not in lokale_ids:
                raise ValueError(
                    f"Unbekannte Summenreferenz {bezug!r} in Finanzposition {position['id']}."
                )
        finanzfaelle[persona_id] = positionen

    fehlende = set(persona_index) - set(finanzfaelle)
    if fehlende:
        raise ValueError("Fehlende Finanzfälle: " + ", ".join(sorted(fehlende)))
    return finanzfaelle, str(daten.get("kennzeichnung", ""))


def bereite_testdaten_vor(arbeitsordner: Path) -> dict[str, int]:
    arbeitsordner = arbeitsordner.resolve()
    projektordner = ROOT.resolve()
    if arbeitsordner == projektordner or arbeitsordner.is_relative_to(projektordner):
        raise ValueError("Der isolierte Testordner muss außerhalb des Projekts liegen.")
    produktive_ordner = [(ROOT / name).resolve() for name in ("daten", "dokumente")]
    if any(arbeitsordner == pfad or arbeitsordner.is_relative_to(pfad) for pfad in produktive_ordner):
        raise ValueError("Der isolierte Testordner darf nicht in produktiven Datenordnern liegen.")

    index_datei = arbeitsordner / "daten" / "nutzer" / "index.json"
    if index_datei.exists():
        raise FileExistsError(f"Der Testordner wurde bereits vorbereitet: {arbeitsordner}")

    personas = json.loads(PERSONAS_DATEI.read_text(encoding="utf-8"))["personas"]
    finanzfaelle, finanzkennzeichnung = _lade_finanzfaelle(personas)
    nutzer = []
    beleganzahl = 0
    finanzpositionsanzahl = 0
    zeitpunkt = datetime.now().astimezone().isoformat(timespec="seconds")
    for persona in personas:
        nutzer_id = f"synthetisch-{persona['id']}"
        nutzer.append({"id": nutzer_id, "name": persona["name"], "angelegt_am": zeitpunkt})
        datenordner = arbeitsordner / "daten" / "nutzer" / nutzer_id
        eingang = arbeitsordner / "dokumente" / "nutzer" / nutzer_id / "eingang"
        (datenordner / "steuerjahre").mkdir(parents=True, exist_ok=True)
        (arbeitsordner / "dokumente" / "nutzer" / nutzer_id / "pruefen").mkdir(
            parents=True, exist_ok=True
        )
        eingang.mkdir(parents=True, exist_ok=True)

        profil = deepcopy(persona.get("profil", {}))
        profil.setdefault("version", 1)
        profil.setdefault("stand", zeitpunkt)
        profil.setdefault("steuererklaerung", {})
        profil["steuererklaerung"].setdefault(
            "naechstes_zu_bearbeitendes_steuerjahr", persona["steuerjahr"]
        )
        profil["steuererklaerung"].setdefault("status", "Synthetischer Testfall")
        _schreibe_json(datenordner / "steuerprofil.json", profil)
        _schreibe_json(
            datenordner / "einstellungen.json",
            {"eingangsordner": str(eingang.resolve())},
        )
        finanzpositionen = finanzfaelle[persona["id"]]
        _schreibe_json(
            datenordner / "finanzpositionen.json",
            {
                "version": 1,
                "kennzeichnung": finanzkennzeichnung,
                "positionen": finanzpositionen,
            },
        )
        finanzpositionsanzahl += len(finanzpositionen)

        register = {}
        for nummer, beleg in enumerate(persona.get("belege", []), 1):
            datei = eingang / beleg["dateiname"]
            datei.write_text(beleg["inhalt"], encoding="utf-8")
            kennung = f"{persona['id']}-{nummer:02d}"
            register[kennung] = {
                "id": kennung,
                "dateiname": beleg["dateiname"],
                "pfad": str(datei.resolve()),
                "dokumenttyp": beleg["erwarteter_typ"],
                "steuerjahr": beleg["erwartetes_jahr"],
                "grundlage": "Synthetische Dialogtest-Fixture",
                "ocr_status": "Synthetische Testdatei",
                "status": beleg["status"],
                "manuell": False,
                "pruefhinweise": [],
                "wertvorschlaege": deepcopy(beleg.get("wertvorschlaege", [])),
                "nutzerzuordnung": {
                    "status": "Bestätigt",
                    "bestaetigt": True,
                    "nutzer_id": nutzer_id,
                    "name": persona["name"],
                },
                "erkannt_am": zeitpunkt,
            }
            beleganzahl += 1
        _schreibe_json(datenordner / "dokumentregister.json", register)

    _schreibe_json(index_datei, {"version": 1, "nutzer": nutzer})
    _schreibe_json(
        arbeitsordner / "daten" / "anmeldung.json",
        {"version": 1, "sitzungsschluessel": "synthetischer-dialogtest-nicht-produktiv", "konten": []},
    )
    return {
        "personas": len(personas),
        "belege": beleganzahl,
        "finanzpositionen": finanzpositionsanzahl,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arbeitsordner", required=True, type=Path)
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()

    zusammenfassung = bereite_testdaten_vor(args.arbeitsordner)
    testwurzel = args.arbeitsordner.resolve()
    os.environ.pop("STEUER_ASSISTENT_HEIMNETZ", None)
    os.environ["STEUER_CHAT_BACKEND"] = "lmstudio"
    os.environ["STEUER_CHAT_FALLBACK_BACKEND"] = "gguf"
    os.environ["STEUER_GGUF_FALLBACK_QUANTISIERUNG"] = "Q4_K_M"
    os.environ["STEUER_EMBEDDING_BACKEND"] = "lmstudio"
    os.environ["STEUER_LMSTUDIO_URL"] = "http://127.0.0.1:1235/v1"
    os.environ["STEUER_LMSTUDIO_MODELL"] = "steuer-assistent-q5"
    os.environ["STEUER_LMSTUDIO_KONTEXT"] = "32768"
    os.environ["STEUER_LMSTUDIO_EMBEDDING_URL"] = "http://127.0.0.1:1236/v1"
    os.environ["STEUER_LMSTUDIO_EMBEDDING_MODELL"] = "qwen3-embedding-4b"
    os.environ["STEUER_VISION_BACKEND"] = "lmstudio"
    os.environ["STEUER_LMSTUDIO_VISION_URL"] = "http://127.0.0.1:1237/v1"

    sys.path.insert(0, str(ROOT / "app"))
    import authentifizierung
    import nutzerverwaltung

    nutzerverwaltung.NUTZER_DATEN = testwurzel / "daten" / "nutzer"
    nutzerverwaltung.NUTZER_DOKUMENTE = testwurzel / "dokumente" / "nutzer"
    nutzerverwaltung.NUTZER_INDEX = nutzerverwaltung.NUTZER_DATEN / "index.json"
    nutzerverwaltung.LEGACY_PROFIL = testwurzel / "daten" / "steuerprofil.json"
    nutzerverwaltung.LEGACY_REGISTER = testwurzel / "daten" / "dokumentregister.json"
    nutzerverwaltung.LEGACY_EINSTELLUNGEN = testwurzel / "daten" / "einstellungen.json"
    nutzerverwaltung.LEGACY_EINGANG = testwurzel / "dokumente" / "eingang"
    nutzerverwaltung._AKTIVER_NUTZER = None
    authentifizierung.KONFIGURATION = testwurzel / "daten" / "anmeldung.json"

    import web_ui

    web_ui.HEIMNETZ_MODUS = False
    web_ui.app.testing = False
    print(
        "SYNTHETISCHE TESTINSTANZ "
        f"personas={zusammenfassung['personas']} belege={zusammenfassung['belege']} "
        f"finanzpositionen={zusammenfassung['finanzpositionen']} "
        f"port={args.port}",
        flush=True,
    )
    web_ui.app.run(host="127.0.0.1", port=args.port, debug=False, threaded=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
