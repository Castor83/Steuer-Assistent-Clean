"""Erstellt eine sichere ELSTER-Eingabehilfe, aber keine versandfertige Erklärung.

Mein ELSTER bietet für die Einkommensteuer keinen allgemeinen Dateiimport. Der
Export ordnet deshalb ausschließlich bestätigte lokale Angaben den passenden
Formularbereichen zu. Die Struktur kann später als Vorstufe für eine offizielle
ERiC-Anbindung verwendet werden.
"""

from __future__ import annotations

import csv
from datetime import datetime
from io import BytesIO, StringIO
import json
from zipfile import ZIP_DEFLATED, ZipFile

from steuerakte import plausibilitaet_pruefen


SCHEMA_VERSION = "steuer-assistent-elster-eingabehilfe/v1"
AMTLICHE_ENTWICKLERINFO = "https://www.elster.de/eportal/infoseite/entwickler"
AMTLICHE_IMPORTINFO = "https://www.elster.de/eportal/helpGlobal?themaGlobal=anleitung_zur_importfunktion_eop"


FELD_ZUORDNUNG = {
    "steuerklasse": ("Anlage N", "Lohnsteuerbescheinigung", "Steuerklasse"),
    "kinderfreibetrag": ("Anlage N", "Lohnsteuerbescheinigung", "Zahl der Kinderfreibeträge"),
    "beschaeftigungszeitraum": ("Anlage N", "Lohnsteuerbescheinigung", "Bescheinigungszeitraum"),
    "bruttoarbeitslohn": ("Anlage N", "Arbeitslohn", "Bruttoarbeitslohn"),
    "lohnsteuer": ("Anlage N", "Steuerabzugsbeträge", "Einbehaltene Lohnsteuer"),
    "solidaritaetszuschlag": ("Anlage N", "Steuerabzugsbeträge", "Solidaritätszuschlag"),
    "kirchensteuer": ("Anlage N", "Steuerabzugsbeträge", "Kirchensteuer"),
    "rentenversicherung": ("Anlage Vorsorgeaufwand", "Altersvorsorgeaufwendungen", "Arbeitnehmerbeitrag zur gesetzlichen Rentenversicherung"),
    "krankenversicherung": ("Anlage Vorsorgeaufwand", "Kranken- und Pflegeversicherung", "Arbeitnehmerbeitrag Krankenversicherung"),
    "pflegeversicherung": ("Anlage Vorsorgeaufwand", "Kranken- und Pflegeversicherung", "Arbeitnehmerbeitrag Pflegeversicherung"),
    "arbeitslosenversicherung": ("Anlage Vorsorgeaufwand", "Weitere sonstige Vorsorgeaufwendungen", "Arbeitnehmerbeitrag Arbeitslosenversicherung"),
    "entfernung_km": ("Anlage N", "Wege zwischen Wohnung und erster Tätigkeitsstätte", "Einfache Entfernung"),
    "arbeitstage": ("Anlage N", "Wege zwischen Wohnung und erster Tätigkeitsstätte", "Arbeitstage mit Fahrt"),
    "homeoffice_tage": ("Anlage N", "Werbungskosten", "Tage für die Homeoffice-Pauschale"),
    "arbeitsmittel": ("Anlage N", "Werbungskosten", "Arbeitsmittel"),
    "fortbildungskosten": ("Anlage N", "Werbungskosten", "Fortbildungskosten"),
    "handwerker_arbeitskosten": ("Anlage Haushaltsnahe Aufwendungen", "Handwerkerleistungen", "Begünstigte Arbeits-, Fahrt- und Maschinenkosten"),
    "haushaltsnahe_dienstleistungen": ("Anlage Haushaltsnahe Aufwendungen", "Haushaltsnahe Dienstleistungen", "Begünstigte Aufwendungen"),
    "mieteinnahmen": ("Anlage V", "Einnahmen", "Mieteinnahmen"),
    "schuldzinsen_vermietung": ("Anlage V", "Werbungskosten", "Schuldzinsen für den vermieteten Anteil"),
    "grundsteuer_vermietung": ("Anlage V", "Werbungskosten", "Grundsteuer für den vermieteten Anteil"),
    "reparaturkosten_vermietung": ("Anlage V", "Werbungskosten", "Erhaltungsaufwendungen für den vermieteten Anteil"),
}

STAMMDATEN_ZUORDNUNG = {
    "steuer_id": ("Hauptvordruck", "Person A", "Steuer-Identifikationsnummer"),
    "steuernummer": ("Hauptvordruck", "Allgemeine Angaben", "Steuernummer"),
    "iban": ("Hauptvordruck", "Bankverbindung", "IBAN"),
}


ANLAGEN_NACH_BEREICH = {
    "arbeitnehmer": ["Anlage N", "Anlage Vorsorgeaufwand"],
    "kinder": ["Anlage Kind"],
    "vermietung": ["Anlage V"],
    "rente": ["Anlage R", "Anlage Vorsorgeaufwand"],
    "selbststaendig": ["Anlage S beziehungsweise G", "Anlage EÜR, falls erforderlich"],
    "kapital": ["Anlage KAP, falls erforderlich"],
    "haushalt": ["Anlage Haushaltsnahe Aufwendungen"],
    "grundsteuer": ["Anlage V für den vermieteten Anteil; kein eigener Einkommensteuer-Vordruck für den selbst genutzten Anteil"],
}


def _feld(anlage: str, abschnitt: str, bezeichnung: str, wert: str, quelle: str, feld_id: str) -> dict:
    return {
        "anlage": anlage,
        "abschnitt": abschnitt,
        "feld": bezeichnung,
        "wert": str(wert),
        "quelle": str(quelle),
        "lokale_feld_id": feld_id,
        "uebernahme": "manuell prüfen und in Mein ELSTER eintragen",
    }


def _profilfelder(profil: dict, nutzer_name: str) -> list[dict]:
    if str(profil.get("quelle", "")).lower() != "vom nutzer bestätigt":
        return []
    felder = []
    if nutzer_name.strip():
        felder.append(_feld("Hauptvordruck", "Person A", "Vollständiger Name", nutzer_name.strip(), "Nutzerprofil", "profil_name"))
    wohnsitz = profil.get("wohnsitz", {}) if isinstance(profil.get("wohnsitz"), dict) else {}
    zuordnung = (
        ("strasse", "Straße"),
        ("hausnummer", "Hausnummer"),
        ("postleitzahl", "Postleitzahl"),
        ("stadt", "Wohnort"),
        ("land", "Staat"),
    )
    for schluessel, bezeichnung in zuordnung:
        wert = str(wohnsitz.get(schluessel, "")).strip()
        if wert:
            felder.append(_feld("Hauptvordruck", "Anschrift", bezeichnung, wert, "bestätigtes Nutzerprofil", f"profil_{schluessel}"))
    return felder


def erstelle_elster_eingabehilfe(
    steuerjahr: str,
    bereiche: list[str],
    dokumente: list[dict],
    profil: dict,
    nutzer_name: str = "",
    stammdaten: dict | None = None,
    manuelle_werte: list[dict] | None = None,
) -> dict:
    """Erstellt eine jahresgetrennte, datensparsame Eingabehilfe."""
    passende = [d for d in dokumente if str(d.get("steuerjahr", "")) == steuerjahr]
    felder = _profilfelder(profil, nutzer_name)
    stammdaten = stammdaten or {}
    for feld_id, ziel in STAMMDATEN_ZUORDNUNG.items():
        if stammdaten.get(feld_id):
            felder.append(_feld(ziel[0], ziel[1], ziel[2], str(stammdaten[feld_id]), "Windows-geschützte Stammdaten", f"stammdaten_{feld_id}"))
    nicht_zugeordnet = []
    unbestaetigt = 0
    for dokument in passende:
        for wert in dokument.get("wertvorschlaege", []):
            if wert.get("status") != "Bestätigt":
                unbestaetigt += 1
                continue
            wert_id = str(wert.get("id", "")).strip()
            ziel = FELD_ZUORDNUNG.get(wert_id)
            if ziel is None:
                nicht_zugeordnet.append(
                    {
                        "bezeichnung": str(wert.get("bezeichnung", wert_id)),
                        "wert": str(wert.get("wert", "")),
                        "quelle": str(dokument.get("dateiname", "")),
                        "grund": "Für dieses bestätigte Merkmal ist noch kein sicherer ELSTER-Formularbereich hinterlegt.",
                    }
                )
                continue
            felder.append(
                _feld(
                    ziel[0],
                    ziel[1],
                    ziel[2],
                    str(wert.get("wert", "")),
                    str(dokument.get("dateiname", "")),
                    wert_id,
                )
            )

    unbestaetigt_manuell = 0
    bestaetigt_manuell = 0
    for wert in manuelle_werte or []:
        if str(wert.get("steuerjahr", "")) != steuerjahr:
            continue
        if wert.get("status") != "Bestätigt":
            unbestaetigt_manuell += 1
            continue
        feld_id = str(wert.get("feld_id", ""))
        ziel = FELD_ZUORDNUNG.get(feld_id)
        if ziel is None:
            nicht_zugeordnet.append({"bezeichnung": str(wert.get("bezeichnung", feld_id)), "wert": str(wert.get("wert", "")), "quelle": str(wert.get("quelle", "manuelle Eingabe")), "grund": "Für diesen manuellen Wert ist noch kein sicherer ELSTER-Formularbereich hinterlegt."})
            continue
        felder.append(_feld(ziel[0], ziel[1], ziel[2], str(wert.get("wert", "")), f"Manuelle Eingabe: {wert.get('quelle', '')}", feld_id))
        bestaetigt_manuell += 1

    anlagen = ["Hauptvordruck"]
    for bereich in bereiche:
        for anlage in ANLAGEN_NACH_BEREICH.get(str(bereich), []):
            if anlage not in anlagen:
                anlagen.append(anlage)

    warnungen = plausibilitaet_pruefen(steuerjahr, dokumente)
    offene_punkte = []
    if unbestaetigt:
        offene_punkte.append(f"{unbestaetigt} erkannte Dokumentwerte sind noch nicht bestätigt.")
    if unbestaetigt_manuell:
        offene_punkte.append(f"{unbestaetigt_manuell} manuell eingetragene Werte sind noch nicht bestätigt.")
    if nicht_zugeordnet:
        offene_punkte.append(f"{len(nicht_zugeordnet)} bestätigte Werte sind noch keinem ELSTER-Bereich sicher zugeordnet.")
    kritische = [w for w in warnungen if w.get("stufe") == "kritisch"]
    if kritische:
        offene_punkte.append(f"{len(kritische)} kritische Plausibilitätswarnungen müssen zuerst geklärt werden.")
    if not any(f["lokale_feld_id"] == "profil_name" for f in felder):
        offene_punkte.append("Der vollständige Name fehlt im bestätigten Nutzerprofil.")
    if not any(f["lokale_feld_id"] == "profil_postleitzahl" for f in felder):
        offene_punkte.append("Die bestätigte Anschrift ist noch unvollständig.")
    fehlende_stammdaten = [bezeichnung for feld_id, bezeichnung in (("steuer_id", "Steuer-ID"), ("steuernummer", "Steuernummer"), ("iban", "Bankverbindung")) if not stammdaten.get(feld_id)]
    if fehlende_stammdaten:
        offene_punkte.append(f"In den geschützten Stammdaten fehlen noch: {', '.join(fehlende_stammdaten)}.")
    offene_punkte.append("Alle Stammdaten und Beträge müssen in Mein ELSTER noch einmal kontrolliert werden.")

    profilfelder = sum(str(f.get("lokale_feld_id", "")).startswith("profil_") for f in felder)
    stammdatenfelder = sum(str(f.get("lokale_feld_id", "")).startswith("stammdaten_") for f in felder)
    dokumentfelder = len(felder) - profilfelder - stammdatenfelder - bestaetigt_manuell

    return {
        "format": SCHEMA_VERSION,
        "nutzer_name": nutzer_name.strip(),
        "steuerjahr": steuerjahr,
        "erstellt_am": datetime.now().astimezone().isoformat(timespec="seconds"),
        "exportart": "ELSTER-Eingabehilfe",
        "versandfaehig": False,
        "direkt_in_mein_elster_importierbar": False,
        "status": "Vorbereitung – vor Übernahme vollständig prüfen",
        "zusammenfassung": {
            "exportierbare_felder": len(felder),
            "profilfelder": profilfelder,
            "stammdatenfelder": stammdatenfelder,
            "bestaetigte_dokumentwerte": dokumentfelder,
            "bestaetigte_manuelle_werte": bestaetigt_manuell,
            "unbestaetigte_dokumentwerte": unbestaetigt,
            "unbestaetigte_manuelle_werte": unbestaetigt_manuell,
            "nicht_zugeordnete_bestaetigte_werte": len(nicht_zugeordnet),
            "kritische_warnungen": len(kritische),
            "offene_punkte": len(offene_punkte),
        },
        "empfohlene_formulare": anlagen,
        "felder": felder,
        "nicht_zugeordnete_bestaetigte_werte": nicht_zugeordnet,
        "plausibilitaetswarnungen": warnungen,
        "offene_punkte": offene_punkte,
        "hinweise": [
            "Die Einkommensteuererklärung unterstützt in Mein ELSTER keinen allgemeinen CSV- oder XML-Dateiimport.",
            "Nur bestätigte Dokumentwerte werden ausgegeben; unbestätigte OCR-Werte bleiben gesperrt.",
            "Elektronisch vom Arbeitgeber oder Versicherer übermittelte eDaten können bereits in Mein ELSTER vorliegen und sind dort abzugleichen.",
            "Eine spätere direkte Übermittlung erfordert die amtliche ERiC-Bibliothek, jahresgenaue Schemata und eine Herstellerregistrierung.",
        ],
        "amtliche_informationen": {
            "ERiC_und_Entwicklerregistrierung": AMTLICHE_ENTWICKLERINFO,
            "Formulare_mit_Importfunktion": AMTLICHE_IMPORTINFO,
        },
    }


def _csv_text(eingabehilfe: dict) -> str:
    ausgabe = StringIO(newline="")
    writer = csv.writer(ausgabe, delimiter=";", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(["Nutzer", "Steuerjahr", "Anlage", "Abschnitt", "Feld", "Wert", "Quelle", "Hinweis"])
    for feld in eingabehilfe["felder"]:
        writer.writerow(
            [
                eingabehilfe.get("nutzer_name", ""),
                eingabehilfe["steuerjahr"],
                feld["anlage"],
                feld["abschnitt"],
                feld["feld"],
                feld["wert"],
                feld["quelle"],
                feld["uebernahme"],
            ]
        )
    return "\ufeff" + ausgabe.getvalue()


def _readme_text(eingabehilfe: dict) -> str:
    return f"""ELSTER-Eingabehilfe
Nutzer: {eingabehilfe.get('nutzer_name') or 'nicht angegeben'}
Steuerjahr: {eingabehilfe['steuerjahr']}

Diese ZIP-Datei ist eine Vorbereitungshilfe. Sie ist keine Steuererklärung,
nicht direkt in Mein ELSTER importierbar und nicht versandfähig.

Inhalt:
- JSON: strukturierte, später für eine ERiC-Anbindung nutzbare Daten
- CSV: lesbare Tabelle zur kontrollierten manuellen Übernahme

Es wurden ausschließlich bestätigte Werte ausgegeben. Prüfe jeden Wert am
Originalbeleg und anschließend noch einmal in Mein ELSTER. Elektronisch
übermittelte eDaten können dort bereits vorausgefüllt sein.

Achtung: In den JSON- und CSV-Dateien liegen die für den Export ausgewählten
Stammdaten im Klartext vor. Bewahre die ZIP-Datei deshalb geschützt auf.

Amtliche Informationen:
{AMTLICHE_ENTWICKLERINFO}
{AMTLICHE_IMPORTINFO}
"""


def erstelle_elster_export_zip(eingabehilfe: dict) -> bytes:
    """Packt JSON, lesbare CSV und Erläuterung ohne lokale Dateipfade."""
    jahr = eingabehilfe["steuerjahr"]
    puffer = BytesIO()
    with ZipFile(puffer, "w", compression=ZIP_DEFLATED) as archiv:
        archiv.writestr(
            f"elster-eingabehilfe-{jahr}.json",
            json.dumps(eingabehilfe, ensure_ascii=False, indent=2) + "\n",
        )
        archiv.writestr(f"elster-eingabehilfe-{jahr}.csv", _csv_text(eingabehilfe))
        archiv.writestr("BITTE-LESEN.txt", _readme_text(eingabehilfe))
    return puffer.getvalue()
