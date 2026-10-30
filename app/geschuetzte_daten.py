"""Kontogebundene Verschlüsselung kleiner lokaler Steuerdatensätze."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import win32crypt


ENTROPIE = b"Steuer-Assistent/geschuetzte-Daten/v1"
DPAPI_OHNE_DIALOG = 0x1


def geschuetzt_schreiben(datei: Path, daten) -> None:
    """Schreibt nur DPAPI-Chiffretext und ersetzt die Zieldatei atomar."""
    datei.parent.mkdir(parents=True, exist_ok=True)
    klartext = json.dumps(daten, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    chiffriert = win32crypt.CryptProtectData(
        klartext,
        "Steuer-Assistent",
        ENTROPIE,
        None,
        None,
        DPAPI_OHNE_DIALOG,
    )
    temp = datei.with_name(f".{datei.name}.{uuid4().hex}.tmp")
    try:
        temp.write_bytes(chiffriert)
        temp.replace(datei)
    except OSError:
        temp.unlink(missing_ok=True)
        raise


def geschuetzt_lesen(datei: Path, standard):
    if not datei.is_file():
        return standard
    try:
        _beschreibung, klartext = win32crypt.CryptUnprotectData(
            datei.read_bytes(),
            ENTROPIE,
            None,
            None,
            DPAPI_OHNE_DIALOG,
        )
        return json.loads(klartext.decode("utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        raise ValueError("Die geschützten Steuerdaten konnten mit diesem Windows-Konto nicht gelesen werden.")
