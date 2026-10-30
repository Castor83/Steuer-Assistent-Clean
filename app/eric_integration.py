"""Inventarisiert ein lokales ERiC-Paket und sperrt ungeprüfte Aktivierungen."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parent.parent
ERIC_HOME_ENV = "STEUER_ASSISTENT_ERIC_HOME"
DEFAULT_ERIC_HOME = ROOT / "vendor" / "eric"
LOCK_SCHEMA = "steuer-assistent-eric-package-lock/v1"
OFFICIAL_MANIFEST_SCHEMA = "steuer-assistent-eric-official-package/v1"
DEFAULT_OFFICIAL_MANIFEST = ROOT / "wissen" / "elster" / "eric_44_2_4_manifest.json"
DEFAULT_OFFICIAL_PACKAGE = ROOT / "daten" / "eric" / "44.2.4.0"
AMTLICHE_ENTWICKLERINFO = "https://www.elster.de/eportal/infoseite/entwickler"
RUNTIME_NAMEN = {
    "ericapi.dll",
    "ericapi64.dll",
    "libericapi.so",
    "libericapi.dylib",
}


def _sha256(pfad: Path) -> str:
    digest = sha256()
    with pfad.open("rb") as datei:
        for block in iter(lambda: datei.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _innerhalb(pfad: Path, wurzel: Path) -> bool:
    try:
        pfad.relative_to(wurzel)
        return True
    except ValueError:
        return False


def _paketdateien(wurzel: Path) -> list[Path]:
    kandidaten = []
    for pfad in wurzel.rglob("*"):
        if not pfad.is_file():
            continue
        aufgeloest = pfad.resolve()
        if not _innerhalb(aufgeloest, wurzel):
            continue
        kandidaten.append(aufgeloest)
    return sorted(kandidaten, key=lambda p: p.relative_to(wurzel).as_posix().lower())


def _xsd_metadaten(pfad: Path) -> dict:
    try:
        wurzel = ET.parse(pfad).getroot()
    except (ET.ParseError, OSError) as exc:
        return {"lesbar": False, "fehler": str(exc), "zielnamensraum": None}
    schema_tag = "{http://www.w3.org/2001/XMLSchema}schema"
    if wurzel.tag != schema_tag:
        return {
            "lesbar": False,
            "fehler": "Wurzelelement ist kein W3C-XML-Schema.",
            "zielnamensraum": None,
        }
    return {
        "lesbar": True,
        "fehler": None,
        "zielnamensraum": wurzel.attrib.get("targetNamespace"),
    }


def eric_pfad(paket_pfad: str | Path | None = None) -> Path:
    roh = paket_pfad or os.environ.get(ERIC_HOME_ENV) or DEFAULT_ERIC_HOME
    return Path(roh).expanduser().resolve()


def inventarisiere_eric_paket(
    paket_pfad: str | Path | None = None,
    steuerjahr: int = 2025,
) -> dict:
    wurzel = eric_pfad(paket_pfad)
    if not wurzel.is_dir():
        return {
            "bestanden": False,
            "aktivierbar": False,
            "steuerjahr": steuerjahr,
            "paket_pfad": str(wurzel),
            "xsd_dateien": 0,
            "runtime_bibliotheken": 0,
            "dateien": [],
            "fehler": ["ERiC-Paketordner nicht gefunden."],
        }

    dateien = []
    xsd_fehler = []
    for pfad in _paketdateien(wurzel):
        relativ = pfad.relative_to(wurzel).as_posix()
        if pfad.suffix.lower() == ".xsd":
            art = "xsd"
        elif pfad.name.lower() in RUNTIME_NAMEN:
            art = "runtime"
        else:
            art = "sonstig"
        eintrag = {
            "pfad": relativ,
            "art": art,
            "groesse": pfad.stat().st_size,
            "sha256": _sha256(pfad),
        }
        if art == "xsd":
            eintrag["xsd"] = _xsd_metadaten(pfad)
            if not eintrag["xsd"]["lesbar"]:
                xsd_fehler.append(f"{relativ}: {eintrag['xsd']['fehler']}")
        dateien.append(eintrag)

    xsd_anzahl = sum(eintrag["art"] == "xsd" for eintrag in dateien)
    runtime_anzahl = sum(eintrag["art"] == "runtime" for eintrag in dateien)
    fehler = list(xsd_fehler)
    if not xsd_anzahl:
        fehler.append("Keine XSD-Datei im Paket gefunden.")
    if not runtime_anzahl:
        fehler.append("Keine unterstützte ERiC-Laufzeitbibliothek gefunden.")
    return {
        "bestanden": not fehler,
        "aktivierbar": False,
        "steuerjahr": steuerjahr,
        "paket_pfad": str(wurzel),
        "xsd_dateien": xsd_anzahl,
        "runtime_bibliotheken": runtime_anzahl,
        "dateien": dateien,
        "fehler": fehler,
    }


def erzeuge_lock_entwurf(inventar: dict) -> dict:
    """Erzeugt einen nicht freigegebenen Prüfsummenentwurf für die Sichtprüfung."""
    return {
        "schema": LOCK_SCHEMA,
        "status": "entwurf",
        "manuell_geprueft": False,
        "steuerjahr": inventar["steuerjahr"],
        "paket_version": None,
        "bezugsquelle": AMTLICHE_ENTWICKLERINFO,
        "dateien": [
            {
                "pfad": eintrag["pfad"],
                "art": eintrag["art"],
                "sha256": eintrag["sha256"],
            }
            for eintrag in inventar["dateien"]
        ],
    }


def _amtliche_bezugsquelle(url: object) -> bool:
    try:
        host = (urlparse(str(url)).hostname or "").lower()
    except ValueError:
        return False
    return host == "elster.de" or host.endswith(".elster.de")


def validiere_offizielles_eric_paket(
    paket_pfad: str | Path = DEFAULT_OFFICIAL_PACKAGE,
    manifest: str | Path | dict = DEFAULT_OFFICIAL_MANIFEST,
) -> dict:
    """Prüft die lokal abgelegten Originalpakete, ohne Versand freizugeben."""
    basis = Path(paket_pfad).expanduser().resolve()
    if isinstance(manifest, dict):
        daten = manifest
    else:
        manifest_pfad = Path(manifest).expanduser().resolve()
        try:
            daten = json.loads(manifest_pfad.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            return {
                "bestanden": False,
                "lokal_validiert": False,
                "versandfaehig": False,
                "fehler": [f"ERiC-Manifest nicht lesbar: {exc}"],
            }

    fehler = []
    if daten.get("schema") != OFFICIAL_MANIFEST_SCHEMA:
        fehler.append("Unbekanntes Format des offiziellen ERiC-Manifests.")
    if not basis.is_dir():
        fehler.append("Lokaler ERiC-Paketordner nicht gefunden.")

    eintraege = [*daten.get("originalpakete", []), *daten.get("pruefdateien", [])]
    gesehen = set()
    for eintrag in eintraege:
        relativ = str(eintrag.get("pfad") or "")
        erwartet = str(eintrag.get("sha256") or "").lower()
        if not relativ or not erwartet:
            fehler.append("Manifesteintrag ohne Pfad oder SHA-256-Prüfsumme.")
            continue
        if relativ in gesehen:
            fehler.append(f"Doppelter Manifestpfad: {relativ}")
            continue
        gesehen.add(relativ)
        pfad = (basis / relativ).resolve()
        if not _innerhalb(pfad, basis):
            fehler.append(f"Manifestpfad verlässt den Paketordner: {relativ}")
            continue
        if not pfad.is_file():
            fehler.append(f"ERiC-Datei fehlt: {relativ}")
            continue
        groesse = eintrag.get("groesse")
        if groesse is not None and pfad.stat().st_size != groesse:
            fehler.append(f"Dateigröße weicht ab: {relativ}")
        if _sha256(pfad).lower() != erwartet:
            fehler.append(f"Prüfsumme weicht ab: {relativ}")

    jahre = daten.get("einkommensteuer_schemajahre")
    if jahre != [2023, 2024, 2025]:
        fehler.append("Das Manifest muss die ESt-Schemajahre 2023 bis 2025 ausweisen.")

    bestanden = not fehler
    return {
        "bestanden": bestanden,
        "lokal_validiert": bestanden,
        "versandfaehig": False,
        "release": daten.get("release"),
        "dokumentation": daten.get("dokumentation"),
        "einkommensteuer_schemajahre": jahre or [],
        "gepruefte_dateien": len(eintraege),
        "blocker": [
            "Eigene produktbezogene Hersteller-ID fehlt.",
            "Fachliches ERiC-XML-Mapping ist noch nicht freigegeben.",
            "Jede Übermittlung bleibt bis zu einem gesonderten Versandtest gesperrt.",
        ],
        "fehler": fehler,
    }


def validiere_eric_lock(inventar: dict, lock: dict) -> dict:
    fehler = list(inventar.get("fehler", []))
    if lock.get("schema") != LOCK_SCHEMA:
        fehler.append("Unbekanntes Lockdatei-Format.")
    if lock.get("status") != "freigegeben" or lock.get("manuell_geprueft") is not True:
        fehler.append("Lockdatei wurde noch nicht manuell freigegeben.")
    if lock.get("steuerjahr") != inventar.get("steuerjahr"):
        fehler.append("Steuerjahr von Paket und Lockdatei stimmt nicht überein.")
    if not str(lock.get("paket_version") or "").strip():
        fehler.append("Die geprüfte ERiC-Paketversion fehlt.")
    if not _amtliche_bezugsquelle(lock.get("bezugsquelle")):
        fehler.append("Bezugsquelle ist keine amtliche ELSTER-Domain.")

    ist = {eintrag["pfad"]: eintrag["sha256"] for eintrag in inventar.get("dateien", [])}
    soll = {
        str(eintrag.get("pfad")): str(eintrag.get("sha256"))
        for eintrag in lock.get("dateien", [])
        if eintrag.get("pfad")
    }
    if set(ist) != set(soll):
        fehlend = sorted(set(soll) - set(ist))
        unerwartet = sorted(set(ist) - set(soll))
        if fehlend:
            fehler.append(f"Gesperrte Paketdateien fehlen: {', '.join(fehlend)}")
        if unerwartet:
            fehler.append(f"Nicht freigegebene Paketdateien vorhanden: {', '.join(unerwartet)}")
    abweichend = sorted(pfad for pfad in set(ist) & set(soll) if ist[pfad] != soll[pfad])
    if abweichend:
        fehler.append(f"Prüfsummen abweichend: {', '.join(abweichend)}")

    return {
        "bestanden": not fehler,
        "aktivierbar": not fehler,
        "steuerjahr": inventar.get("steuerjahr"),
        "paket_version": lock.get("paket_version"),
        "xsd_dateien": inventar.get("xsd_dateien", 0),
        "runtime_bibliotheken": inventar.get("runtime_bibliotheken", 0),
        "fehler": fehler,
    }


def pruefe_eric_integration(
    paket_pfad: str | Path | None = None,
    lock_pfad: str | Path | None = None,
    steuerjahr: int = 2025,
) -> dict:
    inventar = inventarisiere_eric_paket(paket_pfad, steuerjahr)
    if lock_pfad is None:
        return {
            **inventar,
            "aktivierbar": False,
            "fehler": inventar["fehler"] + ["Freigegebene Lockdatei fehlt."],
        }
    pfad = Path(lock_pfad).expanduser().resolve()
    if not pfad.is_file():
        return {
            **inventar,
            "aktivierbar": False,
            "fehler": inventar["fehler"] + ["Lockdatei nicht gefunden."],
        }
    try:
        lock = json.loads(pfad.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {
            **inventar,
            "aktivierbar": False,
            "fehler": inventar["fehler"] + [f"Lockdatei nicht lesbar: {exc}"],
        }
    return validiere_eric_lock(inventar, lock)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paket", type=Path, help=f"ERiC-Paketpfad; alternativ {ERIC_HOME_ENV}.")
    parser.add_argument("--lock", type=Path, help="Manuell geprüfte Paket-Lockdatei.")
    parser.add_argument("--steuerjahr", type=int, default=2025)
    parser.add_argument("--lock-entwurf", type=Path, help="Schreibt einen nicht freigegebenen Lockentwurf.")
    parser.add_argument(
        "--offizielles-manifest",
        type=Path,
        help="Prüft Originalpakete und ausgewählte ERiC-Dateien gegen dieses Manifest.",
    )
    parser.add_argument(
        "--offizielles-paket",
        type=Path,
        default=DEFAULT_OFFICIAL_PACKAGE,
        help="Basisordner der abgelegten offiziellen ERiC-Pakete.",
    )
    args = parser.parse_args()

    if args.offizielles_manifest:
        ergebnis = validiere_offizielles_eric_paket(
            args.offizielles_paket,
            args.offizielles_manifest,
        )
        print(json.dumps(ergebnis, ensure_ascii=False, indent=2))
        return 0 if ergebnis["lokal_validiert"] else 1

    inventar = inventarisiere_eric_paket(args.paket, args.steuerjahr)
    if args.lock_entwurf:
        ziel = args.lock_entwurf.resolve()
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text(
            json.dumps(erzeuge_lock_entwurf(inventar), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    ergebnis = pruefe_eric_integration(args.paket, args.lock, args.steuerjahr)
    print(json.dumps(ergebnis, ensure_ascii=False, indent=2))
    return 0 if ergebnis["aktivierbar"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
