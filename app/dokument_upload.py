"""Sicherer Dokumentupload für die lokale Heimnetz-Oberfläche."""

from __future__ import annotations

from pathlib import Path
import re
from uuid import uuid4

from werkzeug.utils import secure_filename


MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ERLAUBTE_ENDUNGEN = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".csv"}


def ziel_liegt_auf_c(zielordner: Path) -> bool:
    """Uploads sind auf ausdrücklichen Nutzerwunsch ausschließlich auf C: erlaubt."""
    return zielordner.drive.casefold() == "c:"


def _dateiinhalt_passt(endung: str, anfang: bytes, daten: bytes) -> bool:
    if endung == ".pdf":
        return anfang.startswith(b"%PDF-")
    if endung == ".png":
        return anfang.startswith(b"\x89PNG\r\n\x1a\n")
    if endung in {".jpg", ".jpeg"}:
        return anfang.startswith(b"\xff\xd8\xff")
    if endung == ".webp":
        return len(anfang) >= 12 and anfang[:4] == b"RIFF" and anfang[8:12] == b"WEBP"
    if endung in {".txt", ".csv"}:
        if b"\x00" in daten:
            return False
        try:
            daten.decode("utf-8")
        except UnicodeDecodeError:
            try:
                daten.decode("cp1252")
            except UnicodeDecodeError:
                return False
        return True
    return False


def speichere_upload(zielordner: Path, dateiname: str, stream) -> Path:
    """Validiert Namen, Größe, Signatur und Ziel und schreibt atomar."""
    try:
        zielordner = zielordner.resolve(strict=True)
    except OSError as fehler:
        raise ValueError("Der lokale Eingangsordner wurde nicht gefunden.") from fehler
    if not zielordner.is_dir():
        raise ValueError("Der lokale Eingangsordner ist ungültig.")
    if not ziel_liegt_auf_c(zielordner):
        raise ValueError("Dokumentuploads sind ausschließlich in einen Eingangsordner auf Laufwerk C: erlaubt.")

    original = Path(str(dateiname or "")).name
    endung = Path(original).suffix.lower()
    if endung not in ERLAUBTE_ENDUNGEN:
        raise ValueError("Erlaubt sind PDF, PNG, JPG, WEBP, TXT und CSV.")
    basis = secure_filename(Path(original).stem).replace("_", "-").strip("._-") or "dokument"
    basis = re.sub(r"[-_]{2,}", "-", basis)[:90]

    daten = stream.read(MAX_UPLOAD_BYTES + 1)
    if not daten:
        raise ValueError("Die ausgewählte Datei ist leer.")
    if len(daten) > MAX_UPLOAD_BYTES:
        raise ValueError("Die Datei ist größer als 25 MB.")
    if not _dateiinhalt_passt(endung, daten[:16], daten):
        raise ValueError("Dateiendung und Dateiinhalt passen nicht zusammen oder das Format ist ungültig.")

    ziel = zielordner / f"{basis}{endung}"
    if ziel.exists():
        ziel = zielordner / f"{basis}-{uuid4().hex[:8]}{endung}"
    temp = zielordner / f".{uuid4().hex}.upload"
    try:
        temp.write_bytes(daten)
        temp.replace(ziel)
    except OSError as fehler:
        temp.unlink(missing_ok=True)
        raise ValueError("Die Datei konnte nicht sicher im Eingangsordner gespeichert werden.") from fehler
    return ziel
