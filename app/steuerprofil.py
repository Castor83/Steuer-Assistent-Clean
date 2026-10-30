"""Lädt bestätigte Profildaten und leitet daraus vorsichtige Arbeitsbereiche ab."""

from __future__ import annotations

import json
from pathlib import Path

import nutzerverwaltung


PROJEKTORDNER = Path(__file__).resolve().parents[1]
STEUERPROFIL_DATEI = PROJEKTORDNER / "daten" / "steuerprofil.json"


def lade_steuerprofil() -> dict:
    """Lädt nur ausdrücklich gespeicherte Profildaten; Fehler bleiben folgenlos."""
    datei = nutzerverwaltung.profil_datei() or STEUERPROFIL_DATEI
    try:
        daten = json.loads(datei.read_text(encoding="utf-8"))
        return daten if isinstance(daten, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def empfohlene_bereiche(profil: dict) -> list[str]:
    """Aktiviert nur Bereiche, die aus bestätigten Profilangaben folgen."""
    person = profil.get("person", {})
    objekt = profil.get("grundabgaben_standardobjekt", {})
    bereiche: list[str] = []

    if person.get("angestellter") is True:
        bereiche.append("arbeitnehmer")
    if "vermietet" in str(objekt.get("nutzung", "")).lower():
        bereiche.append("vermietung")
    if person.get("wohnt_im_standardobjekt") is True:
        bereiche.append("haushalt")
    if objekt:
        bereiche.append("grundsteuer")
    return bereiche


def profil_uebersicht(profil: dict) -> dict:
    """Erstellt eine kurze, nicht spekulierende Anzeige für die Oberfläche."""
    person = profil.get("person", {})
    objekt = profil.get("grundabgaben_standardobjekt", {})
    wohnsitz = profil.get("wohnsitz", {})
    steuererklaerung = profil.get("steuererklaerung", {})
    angaben: list[str] = []
    offen: list[str] = []

    if person.get("angestellter") is True:
        angaben.append("Angestellter")
    if person.get("hausbesitzer") is True and person.get("wohnt_im_standardobjekt") is True:
        angaben.append("Hausbesitzer, der im Standardobjekt wohnt")

    adresse = " ".join(
        teil for teil in (str(wohnsitz.get("strasse", "")).strip(), str(wohnsitz.get("hausnummer", "")).strip()) if teil
    )
    ort = " ".join(
        teil for teil in (str(wohnsitz.get("postleitzahl", "")).strip(), str(wohnsitz.get("stadt", "")).strip()) if teil
    )
    if adresse and ort:
        angaben.append(f"Wohnsitz und Standardobjekt: {adresse}, {ort}")
    if objekt.get("gebaeudeart"):
        angaben.append(str(objekt["gebaeudeart"]))
    if objekt.get("nutzung"):
        angaben.append(str(objekt["nutzung"]).capitalize())

    if objekt.get("anzahl_selbstgenutzte_wohneinheiten") == "noch nicht angegeben":
        offen.append("Anzahl der selbst genutzten Wohneinheiten")
    if objekt.get("anzahl_vermietete_wohneinheiten") == "noch nicht angegeben":
        offen.append("Anzahl der vermieteten Wohneinheiten")

    return {
        "gespeichert": bool(profil),
        "angaben": angaben,
        "empfohlene_bereiche": empfohlene_bereiche(profil),
        "offene_angaben": offen,
        "stand": str(profil.get("stand", "")),
        "version": profil.get("version", 1),
        "steuerjahr_vorschlag": str(
            steuererklaerung.get("naechstes_zu_bearbeitendes_steuerjahr", "")
        ),
        "steuerjahr_status": str(steuererklaerung.get("status", "")),
    }
