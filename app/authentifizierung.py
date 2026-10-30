"""Lokale Konten und Sitzungen für den geschützten Heimnetzbetrieb."""

from __future__ import annotations

import argparse
import getpass
import hashlib
import hmac
import json
import secrets
from pathlib import Path


PROJEKTORDNER = Path(__file__).resolve().parents[1]
KONFIGURATION = PROJEKTORDNER / "daten" / "anmeldung.json"
ITERATIONEN = 600_000
ROLLEN = {"nutzer", "admin"}


def _lesen() -> dict:
    try:
        daten = json.loads(KONFIGURATION.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return daten if isinstance(daten, dict) else {}


def _schreiben(daten: dict) -> None:
    KONFIGURATION.parent.mkdir(parents=True, exist_ok=True)
    temporaer = KONFIGURATION.with_suffix(".tmp")
    temporaer.write_text(json.dumps(daten, indent=2), encoding="utf-8")
    temporaer.replace(KONFIGURATION)


def ist_eingerichtet() -> bool:
    daten = _lesen()
    return bool(daten.get("sitzungsschluessel") and daten.get("konten"))


def konto_speichern(username: str, passwort: str, rolle: str = "nutzer") -> None:
    username = " ".join(username.strip().split())
    if not username or len(username) > 80:
        raise ValueError("Der Benutzername ist ungültig.")
    if not passwort or len(passwort) > 200:
        raise ValueError("Das Kennwort ist ungültig.")
    if rolle not in ROLLEN:
        raise ValueError("Die Rolle ist ungültig.")
    daten = _lesen()
    salt = secrets.token_bytes(16)
    schluessel = hashlib.pbkdf2_hmac("sha256", passwort.encode("utf-8"), salt, ITERATIONEN)
    konten = [
        konto for konto in daten.get("konten", [])
        if str(konto.get("username", "")).casefold() != username.casefold()
    ]
    konten.append(
        {
            "username": username,
            "rolle": rolle,
            "verfahren": "pbkdf2-sha256",
            "iterationen": ITERATIONEN,
            "salt": salt.hex(),
            "passwort_hash": schluessel.hex(),
        }
    )
    _schreiben(
        {
            "version": 1,
            "sitzungsschluessel": daten.get("sitzungsschluessel") or secrets.token_hex(32),
            "konten": konten,
        }
    )


def konto_pruefen(username: str, passwort: str) -> dict | None:
    for konto in _lesen().get("konten", []):
        if str(konto.get("username", "")).casefold() != username.strip().casefold():
            continue
        try:
            salt = bytes.fromhex(str(konto["salt"]))
            erwartet = bytes.fromhex(str(konto["passwort_hash"]))
            iterationen = int(konto.get("iterationen", ITERATIONEN))
        except (KeyError, TypeError, ValueError):
            return None
        erhalten = hashlib.pbkdf2_hmac("sha256", passwort.encode("utf-8"), salt, iterationen)
        if hmac.compare_digest(erwartet, erhalten):
            return {"username": str(konto["username"]), "rolle": str(konto.get("rolle", "nutzer"))}
        return None
    # Gleicher Rechenaufwand auch bei unbekanntem Namen erschwert Kontenabfragen.
    hashlib.pbkdf2_hmac("sha256", passwort.encode("utf-8"), b"0" * 16, ITERATIONEN)
    return None


def sitzungsschluessel() -> str:
    daten = _lesen()
    schluessel = str(daten.get("sitzungsschluessel", ""))
    if not schluessel:
        schluessel = secrets.token_hex(32)
        daten["sitzungsschluessel"] = schluessel
        _schreiben(daten)
    return schluessel


def _interaktiv() -> int:
    username = input("Benutzername: ").strip()
    rolle = input("Rolle (nutzer/admin): ").strip().lower() or "nutzer"
    erstes = getpass.getpass("Neues Kennwort: ")
    zweites = getpass.getpass("Kennwort wiederholen: ")
    if erstes != zweites:
        print("Die Kennwörter stimmen nicht überein.")
        return 1
    try:
        konto_speichern(username, erstes, rolle)
    except ValueError as fehler:
        print(fehler)
        return 1
    print("Das Heimnetz-Konto wurde gespeichert.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--konto-setzen", action="store_true")
    argumente = parser.parse_args()
    if argumente.konto_setzen:
        return _interaktiv()
    parser.error("Bitte --konto-setzen angeben.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
