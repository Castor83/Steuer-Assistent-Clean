"""Verschlüsselte, jahresgetrennte Werte aus bewusster Nutzereingabe."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from threading import Lock
from uuid import uuid4

from geschuetzte_daten import geschuetzt_lesen, geschuetzt_schreiben


DATEINAME = "steuerwerte_geschuetzt.bin"
KATALOG = {
    "entfernung_km": {"bezeichnung": "Einfache Entfernung zur ersten Tätigkeitsstätte", "art": "zahl", "einheit": "km"},
    "arbeitstage": {"bezeichnung": "Arbeitstage mit Fahrt zur ersten Tätigkeitsstätte", "art": "zahl", "einheit": "Tage"},
    "homeoffice_tage": {"bezeichnung": "Tage im Homeoffice", "art": "zahl", "einheit": "Tage"},
    "arbeitsmittel": {"bezeichnung": "Beruflich veranlasste Arbeitsmittel", "art": "betrag", "einheit": "€"},
    "fortbildungskosten": {"bezeichnung": "Fortbildungskosten", "art": "betrag", "einheit": "€"},
    "handwerker_arbeitskosten": {"bezeichnung": "Begünstigte Handwerker-Arbeitskosten im eigenen Haushalt", "art": "betrag", "einheit": "€"},
    "haushaltsnahe_dienstleistungen": {"bezeichnung": "Haushaltsnahe Dienstleistungen", "art": "betrag", "einheit": "€"},
    "mieteinnahmen": {"bezeichnung": "Mieteinnahmen", "art": "betrag", "einheit": "€"},
    "schuldzinsen_vermietung": {"bezeichnung": "Darlehenszinsen für den vermieteten Anteil", "art": "betrag", "einheit": "€"},
    "grundsteuer_vermietung": {"bezeichnung": "Grundsteuer für den vermieteten Anteil", "art": "betrag", "einheit": "€"},
    "reparaturkosten_vermietung": {"bezeichnung": "Reparaturkosten für den vermieteten Anteil", "art": "betrag", "einheit": "€"},
}
_SPERRE = Lock()


def _wert_pruefen(feld_id: str, wert: str) -> str:
    meta = KATALOG.get(feld_id)
    if meta is None:
        raise ValueError("Unbekanntes Steuerfeld.")
    text = str(wert).strip().replace("€", "").replace(" ", "")
    if meta["art"] == "zahl":
        if not re.fullmatch(r"\d{1,6}", text):
            raise ValueError("Bitte gib eine nichtnegative ganze Zahl ein.")
        return str(int(text))
    text = text.replace(".", "").replace(",", ".")
    try:
        betrag = Decimal(text)
    except InvalidOperation as fehler:
        raise ValueError("Bitte gib einen gültigen Betrag ein.") from fehler
    if betrag < 0 or betrag > Decimal("999999999.99"):
        raise ValueError("Der Betrag liegt außerhalb des zulässigen Bereichs.")
    deutsch = f"{betrag.quantize(Decimal('0.01')):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{deutsch} €"


def _quelle_pruefen(quelle: str) -> str:
    quelle = " ".join(str(quelle).strip().split())
    if len(quelle) < 3:
        raise ValueError("Bitte nenne eine kurze Quelle, zum Beispiel Rechnung oder eigene Aufstellung.")
    if len(quelle) > 120 or re.search(r"[\x00-\x1f\x7f]", quelle):
        raise ValueError("Die Quellenangabe ist ungültig oder zu lang.")
    return quelle


def _lesen(datei: Path) -> list[dict]:
    daten = geschuetzt_lesen(datei, {"version": 1, "werte": []})
    if not isinstance(daten, dict) or not isinstance(daten.get("werte"), list):
        raise ValueError("Die geschützten Jahreswerte haben ein ungültiges Format.")
    return [dict(wert) for wert in daten["werte"] if isinstance(wert, dict)]


def _schreiben(datei: Path, werte: list[dict]) -> None:
    geschuetzt_schreiben(datei, {"version": 1, "werte": werte})


def katalog_liste() -> list[dict]:
    return [{"id": feld_id, **meta} for feld_id, meta in KATALOG.items()]


def werte_laden(datei: Path, steuerjahr: str) -> list[dict]:
    return [wert for wert in _lesen(datei) if str(wert.get("steuerjahr")) == steuerjahr]


def wert_speichern(datei: Path, steuerjahr: str, feld_id: str, wert: str, quelle: str) -> dict:
    if steuerjahr not in {"2023", "2024", "2025"}:
        raise ValueError("Manuelle Steuerwerte werden derzeit für 2023, 2024 und 2025 geführt.")
    jetzt = datetime.now().astimezone().isoformat(timespec="seconds")
    neu = {
        "id": uuid4().hex,
        "steuerjahr": steuerjahr,
        "feld_id": feld_id,
        "bezeichnung": KATALOG.get(feld_id, {}).get("bezeichnung", ""),
        "wert": _wert_pruefen(feld_id, wert),
        "quelle": _quelle_pruefen(quelle),
        "status": "Zu prüfen",
        "geaendert_am": jetzt,
    }
    with _SPERRE:
        werte = _lesen(datei)
        vorhanden = next((w for w in werte if w.get("steuerjahr") == steuerjahr and w.get("feld_id") == feld_id), None)
        if vorhanden:
            vorhanden.update({**neu, "id": vorhanden["id"]})
            neu = vorhanden
        else:
            werte.append(neu)
        _schreiben(datei, werte)
    return dict(neu)


def wert_status_setzen(datei: Path, kennung: str, status: str) -> dict:
    if status not in {"Zu prüfen", "Bestätigt"}:
        raise ValueError("Unbekannter Wertstatus.")
    with _SPERRE:
        werte = _lesen(datei)
        eintrag = next((w for w in werte if w.get("id") == kennung), None)
        if eintrag is None:
            raise ValueError("Der manuelle Steuerwert wurde nicht gefunden.")
        eintrag["status"] = status
        eintrag["geaendert_am"] = datetime.now().astimezone().isoformat(timespec="seconds")
        _schreiben(datei, werte)
    return dict(eintrag)


def wert_loeschen(datei: Path, kennung: str) -> None:
    with _SPERRE:
        werte = _lesen(datei)
        neue = [wert for wert in werte if wert.get("id") != kennung]
        if len(neue) == len(werte):
            raise ValueError("Der manuelle Steuerwert wurde nicht gefunden.")
        _schreiben(datei, neue)
