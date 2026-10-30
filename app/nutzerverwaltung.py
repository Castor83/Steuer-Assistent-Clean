"""Lokale Nutzertrennung fuer persoenliche Steuerdaten.

Die gemeinsame Rechts- und Wissensbasis bleibt unveraendert. Profile,
Dokumentregister und Eingangsordner liegen dagegen je Nutzer getrennt.
"""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
import shutil
from threading import Lock
from uuid import uuid4


PROJEKTORDNER = Path(__file__).resolve().parents[1]
NUTZER_DATEN = PROJEKTORDNER / "daten" / "nutzer"
NUTZER_DOKUMENTE = PROJEKTORDNER / "dokumente" / "nutzer"
NUTZER_INDEX = NUTZER_DATEN / "index.json"
LEGACY_PROFIL = PROJEKTORDNER / "daten" / "steuerprofil.json"
LEGACY_REGISTER = PROJEKTORDNER / "daten" / "dokumentregister.json"
LEGACY_EINSTELLUNGEN = PROJEKTORDNER / "daten" / "einstellungen.json"
LEGACY_EINGANG = PROJEKTORDNER / "dokumente" / "eingang"

_SPERRE = Lock()
_AKTIVER_NUTZER: str | None = None


def _json_lesen(datei: Path, standard):
    try:
        return json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return standard


def _json_schreiben(datei: Path, daten) -> None:
    datei.parent.mkdir(parents=True, exist_ok=True)
    temp = datei.with_name(f".{datei.name}.{uuid4().hex}.tmp")
    temp.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(datei)


def _index_lesen() -> dict:
    daten = _json_lesen(NUTZER_INDEX, {})
    if not isinstance(daten, dict) or not isinstance(daten.get("nutzer"), list):
        return {"version": 1, "nutzer": []}
    return {"version": 1, "nutzer": [n for n in daten["nutzer"] if isinstance(n, dict)]}


def name_pruefen(name: str) -> str:
    name = " ".join(str(name).strip().split())
    if len(name) < 2:
        raise ValueError("Bitte gib einen Namen mit mindestens zwei Zeichen ein.")
    if len(name) > 80:
        raise ValueError("Der Name darf höchstens 80 Zeichen lang sein.")
    if re.search(r"[\x00-\x1f\x7f]", name):
        raise ValueError("Der Name enthält unzulässige Steuerzeichen.")
    return name


def nutzer_auflisten() -> list[dict]:
    with _SPERRE:
        return [dict(n) for n in _index_lesen()["nutzer"]]


def nutzer_finden(nutzer_id: str | None) -> dict | None:
    if not nutzer_id:
        return None
    return next((n for n in nutzer_auflisten() if n.get("id") == nutzer_id), None)


def aktiven_nutzer_setzen(nutzer_id: str | None) -> dict | None:
    global _AKTIVER_NUTZER
    if nutzer_id is None:
        _AKTIVER_NUTZER = None
        return None
    nutzer = nutzer_finden(nutzer_id)
    if nutzer is None:
        raise ValueError("Dieser Nutzer wurde nicht gefunden.")
    _AKTIVER_NUTZER = str(nutzer["id"])
    return nutzer


def aktiver_nutzer() -> dict | None:
    return nutzer_finden(_AKTIVER_NUTZER)


def datenordner(nutzer_id: str | None = None) -> Path:
    kennung = nutzer_id or _AKTIVER_NUTZER
    if nutzer_finden(kennung) is None:
        raise ValueError("Es ist kein gültiger Nutzer ausgewählt.")
    return NUTZER_DATEN / str(kennung)


def dokumentordner(nutzer_id: str | None = None) -> Path:
    kennung = nutzer_id or _AKTIVER_NUTZER
    if nutzer_finden(kennung) is None:
        raise ValueError("Es ist kein gültiger Nutzer ausgewählt.")
    return NUTZER_DOKUMENTE / str(kennung)


def profil_datei() -> Path | None:
    return datenordner() / "steuerprofil.json" if aktiver_nutzer() else None


def einstellungen_datei() -> Path | None:
    return datenordner() / "einstellungen.json" if aktiver_nutzer() else None


def dokumentregister_datei() -> Path | None:
    return datenordner() / "dokumentregister.json" if aktiver_nutzer() else None


def standard_eingang() -> Path | None:
    return dokumentordner() / "eingang" if aktiver_nutzer() else None


def pruefordner() -> Path | None:
    return dokumentordner() / "pruefen" if aktiver_nutzer() else None


def _legacy_eingang_ermitteln() -> Path:
    daten = _json_lesen(LEGACY_EINSTELLUNGEN, {})
    try:
        pfad = Path(str(daten.get("eingangsordner", ""))).expanduser()
        if pfad.is_absolute() and pfad.exists() and pfad.is_dir():
            return pfad.resolve()
    except (OSError, TypeError, ValueError):
        pass
    return LEGACY_EINGANG.resolve()


def _legacy_daten_kopieren(nutzer_id: str) -> bool:
    """Kopiert Altbestand in den ersten Nutzer, ohne die Quelle anzutasten."""
    ziel_daten = NUTZER_DATEN / nutzer_id
    ziel_eingang = NUTZER_DOKUMENTE / nutzer_id / "eingang"
    migriert = False

    if LEGACY_PROFIL.is_file():
        shutil.copy2(LEGACY_PROFIL, ziel_daten / "steuerprofil.json")
        migriert = True

    quell_eingang = _legacy_eingang_ermitteln()
    if quell_eingang.exists() and quell_eingang.is_dir():
        for quelle in quell_eingang.rglob("*"):
            if quelle.is_file():
                relativ = quelle.relative_to(quell_eingang)
                ziel = ziel_eingang / relativ
                ziel.parent.mkdir(parents=True, exist_ok=True)
                if not ziel.exists():
                    shutil.copy2(quelle, ziel)
                    migriert = True

    register = _json_lesen(LEGACY_REGISTER, {})
    if isinstance(register, dict) and register:
        kopie = {}
        for kennung, eintrag in register.items():
            if not isinstance(eintrag, dict):
                continue
            neu = dict(eintrag)
            try:
                altpfad = Path(str(neu.get("pfad", ""))).resolve()
                relativ = altpfad.relative_to(quell_eingang)
                neu["pfad"] = str((ziel_eingang / relativ).resolve())
            except (OSError, ValueError):
                # Externe Verweise bleiben als Verweis erhalten; nichts wird geloescht.
                pass
            kopie[str(kennung)] = neu
        _json_schreiben(ziel_daten / "dokumentregister.json", kopie)
        migriert = True

    _json_schreiben(
        ziel_daten / "einstellungen.json",
        {"eingangsordner": str(ziel_eingang.resolve())},
    )
    return migriert


def nutzer_anlegen(name: str) -> tuple[dict, bool]:
    name = name_pruefen(name)
    with _SPERRE:
        index = _index_lesen()
        if any(str(n.get("name", "")).casefold() == name.casefold() for n in index["nutzer"]):
            raise ValueError("Ein Nutzer mit diesem Namen ist bereits vorhanden.")
        erster_nutzer = not index["nutzer"]
        nutzer = {
            "id": uuid4().hex,
            "name": name,
            "angelegt_am": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        (NUTZER_DATEN / nutzer["id"] / "steuerjahre").mkdir(parents=True, exist_ok=True)
        (NUTZER_DOKUMENTE / nutzer["id"] / "eingang").mkdir(parents=True, exist_ok=True)
        (NUTZER_DOKUMENTE / nutzer["id"] / "pruefen").mkdir(parents=True, exist_ok=True)
        migriert = _legacy_daten_kopieren(nutzer["id"]) if erster_nutzer else False
        if not erster_nutzer:
            _json_schreiben(
                NUTZER_DATEN / nutzer["id"] / "einstellungen.json",
                {"eingangsordner": str((NUTZER_DOKUMENTE / nutzer["id"] / "eingang").resolve())},
            )
            _json_schreiben(NUTZER_DATEN / nutzer["id"] / "dokumentregister.json", {})
        index["nutzer"].append(nutzer)
        _json_schreiben(NUTZER_INDEX, index)

    aktiven_nutzer_setzen(nutzer["id"])
    return dict(nutzer), migriert
