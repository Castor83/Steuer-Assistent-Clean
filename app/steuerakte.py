"""Jahresakten und vorsichtige Plausibilitaetspruefungen fuer 2023 bis 2025."""

from __future__ import annotations

import re

from steuer_checkliste import erstelle_checkliste
from steuerprofil import empfohlene_bereiche


STEUERAKTEN_JAHRE = ("2023", "2024", "2025")


def _zahl(wert: object) -> float | None:
    text = str(wert or "").replace("€", "").replace(" ", "")
    treffer = re.search(r"-?\d[\d.]*,\d{1,2}|-?\d+(?:[.]\d+)?", text)
    if not treffer:
        return None
    roh = treffer.group(0)
    if "," in roh:
        roh = roh.replace(".", "").replace(",", ".")
    try:
        return float(roh)
    except ValueError:
        return None


def _werte_nach_id(dokument: dict) -> dict[str, list[dict]]:
    ergebnis: dict[str, list[dict]] = {}
    for wert in dokument.get("wertvorschlaege", []):
        if not isinstance(wert, dict):
            continue
        kennung = str(wert.get("id", "")).strip()
        if kennung:
            ergebnis.setdefault(kennung, []).append(wert)
    return ergebnis


def _warnung(code: str, stufe: str, text: str, dateiname: str = "") -> dict:
    return {"code": code, "stufe": stufe, "text": text, "dokument": dateiname}


def plausibilitaet_pruefen(steuerjahr: str, dokumente: list[dict]) -> list[dict]:
    """Prueft nur sicher erkennbare Widersprueche und offene Kontrollen."""
    warnungen: list[dict] = []
    passende = [d for d in dokumente if str(d.get("steuerjahr", "")) == steuerjahr]

    for dokument in passende:
        dateiname = str(dokument.get("dateiname", "Unbenanntes Dokument"))
        status = str(dokument.get("status", ""))
        if status == "Unklar":
            warnungen.append(_warnung("dokument_unklar", "kritisch", "Dokumenttyp oder Inhalt ist noch unklar.", dateiname))
        elif status != "Geprüft":
            warnungen.append(_warnung("dokument_offen", "pruefen", "Dokument wurde noch nicht abschließend geprüft.", dateiname))

        zuordnung = dokument.get("nutzerzuordnung", {}) if isinstance(dokument.get("nutzerzuordnung"), dict) else {}
        personenstatus = str(zuordnung.get("status", ""))
        if personenstatus == "Anderer Nutzer erkannt":
            warnungen.append(_warnung("falscher_nutzer", "kritisch", "Im Dokument wurde ein anderer Nutzername erkannt.", dateiname))
        elif not zuordnung.get("bestaetigt") and personenstatus not in {"Erkannt", "Bestätigt"}:
            warnungen.append(_warnung("nutzer_offen", "pruefen", "Die Person im Dokument ist noch nicht sicher bestätigt.", dateiname))

        dateijahre = set(re.findall(r"\b(?:19|20)\d{2}\b", dateiname))
        if len(dateijahre) == 1 and steuerjahr not in dateijahre:
            gefunden = next(iter(dateijahre))
            warnungen.append(_warnung("jahr_dateiname", "kritisch", f"Der Dateiname nennt {gefunden}, zugeordnet ist aber {steuerjahr}.", dateiname))

        if dokument.get("dokumenttyp") != "Elektronische Lohnsteuerbescheinigung":
            continue

        werte = _werte_nach_id(dokument)
        for kennung, bezeichnung in (
            ("steuerklasse", "Steuerklasse"),
            ("bruttoarbeitslohn", "Bruttoarbeitslohn"),
            ("lohnsteuer", "einbehaltene Lohnsteuer"),
        ):
            if kennung not in werte:
                warnungen.append(_warnung("lohnwert_fehlt_" + kennung, "pruefen", f"{bezeichnung} wurde nicht sicher erkannt und muss am Original geprüft werden.", dateiname))

        offene_werte = sum(
            str(wert.get("status", "")) == "Zu prüfen"
            for gruppe in werte.values()
            for wert in gruppe
        )
        if offene_werte:
            warnungen.append(_warnung("werte_offen", "pruefen", f"{offene_werte} erkannte Werte warten noch auf Bestätigung.", dateiname))

        steuerklasse = next((str(w.get("wert", "")) for w in werte.get("steuerklasse", []) if str(w.get("wert", "")).strip()), "")
        if steuerklasse and not re.fullmatch(r"[1-6]", steuerklasse.strip()):
            warnungen.append(_warnung("steuerklasse_unplausibel", "kritisch", f"Die erkannte Steuerklasse „{steuerklasse}“ ist nicht plausibel.", dateiname))

        zeitraeume = [str(w.get("wert", "")) for w in werte.get("beschaeftigungszeitraum", [])]
        if zeitraeume and any(steuerjahr not in zeitraum for zeitraum in zeitraeume):
            warnungen.append(_warnung("zeitraum_falsches_jahr", "kritisch", f"Der erkannte Bescheinigungszeitraum passt nicht vollständig zum Steuerjahr {steuerjahr}.", dateiname))

        brutto = next((_zahl(w.get("wert")) for w in werte.get("bruttoarbeitslohn", []) if _zahl(w.get("wert")) is not None), None)
        lohnsteuer = next((_zahl(w.get("wert")) for w in werte.get("lohnsteuer", []) if _zahl(w.get("wert")) is not None), None)
        beitrags_ids = ("rentenversicherung", "krankenversicherung", "pflegeversicherung", "arbeitslosenversicherung")
        beitraege = [
            zahl
            for kennung in beitrags_ids
            for wert in werte.get(kennung, [])
            if (zahl := _zahl(wert.get("wert"))) is not None
        ]
        if brutto == 0 and any(betrag > 0 for betrag in beitraege):
            warnungen.append(_warnung("brutto_null_mit_beitraegen", "kritisch", "Bruttoarbeitslohn ist 0 Euro, zugleich wurden positive Sozialversicherungsbeiträge erkannt.", dateiname))
        if brutto is not None and lohnsteuer is not None and lohnsteuer > brutto:
            warnungen.append(_warnung("lohnsteuer_ueber_brutto", "kritisch", "Die erkannte Lohnsteuer ist höher als der Bruttoarbeitslohn.", dateiname))
        if brutto is not None and brutto >= 0 and sum(beitraege) > brutto:
            warnungen.append(_warnung("beitraege_ueber_brutto", "kritisch", "Die erkannten Sozialversicherungsbeiträge sind zusammen höher als der Bruttoarbeitslohn.", dateiname))

    lohndokumente = [d for d in passende if d.get("dokumenttyp") == "Elektronische Lohnsteuerbescheinigung"]
    if len(lohndokumente) > 1:
        warnungen.append(
            _warnung(
                "mehrere_lohnbescheinigungen",
                "hinweis",
                "Mehrere Lohnsteuerbescheinigungen gefunden: Arbeitgeber und Beschäftigungszeiträume auf Überschneidungen prüfen.",
            )
        )
    return warnungen


def erstelle_steuerakte(steuerjahr: str, bereiche: list[str], dokumente: list[dict]) -> dict:
    passende = [d for d in dokumente if str(d.get("steuerjahr", "")) == steuerjahr]
    unzugeordnet = [d for d in dokumente if str(d.get("steuerjahr", "")) in {"", "Nicht erkannt"}]
    # Ein Dokument ohne sicher erkanntes Jahr bleibt ein Pruefkandidat. Es darf
    # nicht gleichzeitig die Checklisten mehrerer Steuerjahre erfuellen.
    checkliste = erstelle_checkliste(steuerjahr, bereiche, passende)
    warnungen = plausibilitaet_pruefen(steuerjahr, dokumente)
    vorhanden = sum(punkt["status"] == "Vorhanden" for punkt in checkliste)
    gesamt = len(checkliste)
    fortschritt = round(vorhanden * 100 / gesamt) if gesamt else 0
    kritische = sum(w["stufe"] == "kritisch" for w in warnungen)
    pruefen = sum(w["stufe"] == "pruefen" for w in warnungen)
    bestaetigte_werte = sum(
        wert.get("status") == "Bestätigt"
        for dokument in passende
        for wert in dokument.get("wertvorschlaege", [])
    )

    if kritische:
        status = "Widerspruch prüfen"
    elif not passende:
        status = "Noch nicht begonnen"
    elif fortschritt == 100 and not pruefen:
        status = "Bereit zur Abschlussprüfung"
    else:
        status = "In Bearbeitung"

    naechste_schritte = [w["text"] for w in warnungen if w["stufe"] in {"kritisch", "pruefen"}]
    naechste_schritte.extend(
        f"Noch benötigt: {punkt['bezeichnung']}"
        for punkt in checkliste
        if punkt["status"] != "Vorhanden"
    )
    return {
        "steuerjahr": steuerjahr,
        "status": status,
        "fortschritt_prozent": fortschritt,
        "bereiche": list(bereiche),
        "zusammenfassung": {
            "dokumente": len(passende),
            "gepruefte_dokumente": sum(d.get("status") == "Geprüft" for d in passende),
            "pruefpunkte": gesamt,
            "vorhandene_pruefpunkte": vorhanden,
            "fehlende_pruefpunkte": gesamt - vorhanden,
            "bestaetigte_werte": bestaetigte_werte,
            "kritische_warnungen": kritische,
            "offene_pruefungen": pruefen,
            "unzugeordnete_dokumente": len(unzugeordnet),
        },
        "warnungen": warnungen,
        "naechste_schritte": list(dict.fromkeys(naechste_schritte))[:6],
        "checkliste": checkliste,
    }


def erstelle_steuerakten(profil: dict, dokumente: list[dict]) -> list[dict]:
    bereiche = empfohlene_bereiche(profil)
    return [erstelle_steuerakte(jahr, bereiche, dokumente) for jahr in STEUERAKTEN_JAHRE]
