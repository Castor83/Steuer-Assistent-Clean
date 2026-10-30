"""Validiert und verwaltet besonders sensible Steuerstammdaten."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from threading import Lock

from geschuetzte_daten import geschuetzt_lesen, geschuetzt_schreiben


DATEINAME = "stammdaten_geschuetzt.bin"
FELDER = {
    "steuer_id": "Steuer-Identifikationsnummer",
    "steuernummer": "Steuernummer",
    "iban": "IBAN für Erstattungen",
}
_SPERRE = Lock()


def _ziffern(wert: str) -> str:
    return re.sub(r"\D", "", str(wert))


def _iban_pruefen(wert: str) -> str:
    iban = re.sub(r"\s", "", str(wert)).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", iban):
        raise ValueError("Bitte gib eine vollständige IBAN ein.")
    umgestellt = iban[4:] + iban[:4]
    ziffern = "".join(str(ord(zeichen) - 55) if zeichen.isalpha() else zeichen for zeichen in umgestellt)
    if int(ziffern) % 97 != 1:
        raise ValueError("Die Prüfziffern der IBAN stimmen nicht.")
    return iban


def wert_pruefen(feld: str, wert: str) -> str:
    if feld == "steuer_id":
        ziffern = _ziffern(wert)
        if len(ziffern) != 11:
            raise ValueError("Die Steuer-ID muss genau 11 Ziffern enthalten.")
        return ziffern
    if feld == "steuernummer":
        ziffern = _ziffern(wert)
        if not 10 <= len(ziffern) <= 13:
            raise ValueError("Die Steuernummer muss 10 bis 13 Ziffern enthalten.")
        return ziffern
    if feld == "iban":
        return _iban_pruefen(wert)
    raise ValueError("Unbekanntes Stammdatenfeld.")


def lade_stammdaten(datei: Path) -> dict:
    daten = geschuetzt_lesen(datei, {"version": 1, "werte": {}})
    if not isinstance(daten, dict) or not isinstance(daten.get("werte"), dict):
        raise ValueError("Die geschützten Stammdaten haben ein ungültiges Format.")
    return dict(daten["werte"])


def speichere_stammdaten(datei: Path, werte: dict, loeschen: list[str] | None = None) -> dict:
    if not isinstance(werte, dict):
        raise ValueError("Die Stammdaten sind ungültig.")
    updates = {feld: wert_pruefen(str(feld), str(wert)) for feld, wert in werte.items() if str(wert).strip()}
    zu_loeschen = [str(feld) for feld in loeschen or []]
    if any(feld not in FELDER for feld in zu_loeschen):
        raise ValueError("Unbekanntes Stammdatenfeld.")
    with _SPERRE:
        aktuell = lade_stammdaten(datei)
        aktuell.update(updates)
        for feld in zu_loeschen:
            aktuell.pop(feld, None)
        geschuetzt_schreiben(
            datei,
            {
                "version": 1,
                "geaendert_am": datetime.now().astimezone().isoformat(timespec="seconds"),
                "werte": aktuell,
            },
        )
    return aktuell


def _maskieren(feld: str, wert: str) -> str:
    if feld == "iban":
        return f"{wert[:2]}•• •••• •••• •••• ••{wert[-4:]}"
    sichtbar = 3 if feld == "steuer_id" else 4
    return "•" * max(0, len(wert) - sichtbar) + wert[-sichtbar:]


def stammdaten_status(datei: Path) -> dict:
    werte = lade_stammdaten(datei)
    return {
        feld: {
            "bezeichnung": bezeichnung,
            "vorhanden": bool(werte.get(feld)),
            "maskiert": _maskieren(feld, str(werte[feld])) if werte.get(feld) else "",
        }
        for feld, bezeichnung in FELDER.items()
    }
