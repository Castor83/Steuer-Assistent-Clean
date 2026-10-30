"""Zentrale Jahreslogik für die verlässlich unterstützten Veranlagungszeiträume."""

from __future__ import annotations

import re


UNTERSTUETZTE_STEUERJAHRE = (2023, 2024, 2025)

JAHRESDATEN = {
    2023: {
        "grundfreibetrag": 10_908,
        "arbeitnehmer_pauschbetrag": 1_230,
        "sparer_pauschbetrag": 1_000,
        "homeoffice_tag": 6,
        "homeoffice_maximum": 1_260,
        "entfernung_bis_20_km": 0.30,
        "entfernung_ab_21_km": 0.38,
        "abgabe_unberaten": "2. September 2024",
        "abgabe_beraten": "2. Juni 2025",
        "grundsteuer_system": "bisherige Einheitswerte (Übergangsrecht bis einschließlich 2024)",
        "spitzensteuersatz_grenze": 62_810,
        "rentenanteil_neuzugang": 82.5,
    },
    2024: {
        "grundfreibetrag": 11_784,
        "arbeitnehmer_pauschbetrag": 1_230,
        "sparer_pauschbetrag": 1_000,
        "homeoffice_tag": 6,
        "homeoffice_maximum": 1_260,
        "entfernung_bis_20_km": 0.30,
        "entfernung_ab_21_km": 0.38,
        "abgabe_unberaten": "31. Juli 2025",
        "abgabe_beraten": "30. April 2026",
        "grundsteuer_system": "bisherige Einheitswerte (Übergangsrecht bis einschließlich 2024)",
        "spitzensteuersatz_grenze": 66_761,
        "rentenanteil_neuzugang": 83.0,
    },
    2025: {
        "grundfreibetrag": 12_096,
        "arbeitnehmer_pauschbetrag": 1_230,
        "sparer_pauschbetrag": 1_000,
        "homeoffice_tag": 6,
        "homeoffice_maximum": 1_260,
        "entfernung_bis_20_km": 0.30,
        "entfernung_ab_21_km": 0.38,
        "abgabe_unberaten": "31. Juli 2026",
        "abgabe_beraten": "1. März 2027",
        "grundsteuer_system": "bayerisches Flächenmodell (neue Grundsteuer ab 2025)",
        "spitzensteuersatz_grenze": 68_481,
        "rentenanteil_neuzugang": 83.5,
    },
}


def steuerjahr_aus_text(text: str) -> int | None:
    """Liest ein ausdrücklich genanntes Steuerjahr aus einem Text."""
    text = text or ""
    jahre = [int(jahr) for jahr in re.findall(r"(?<!\d)(20\d{2})(?!\d)", text)]
    if jahre:
        return jahre[-1]

    # Im Gespräch wird ein Steuerjahr oft nur als "23", "24" oder "25"
    # geschrieben. Diese Kurzform gilt nur bei erkennbarem Steuerkontext und
    # nicht vor Einheiten wie Tage, Euro oder Kilometer.
    klein = text.casefold()
    steuerkontext = any(
        wort in klein
        for wort in (
            "steuer", "veranlag", "lohnsteuerbescheinigung", "grundsteuerbescheid",
            "grundabgabenbescheid", "gebührenbescheid", "bescheid", "erklärung",
            "erklaerung", "spend", "arbeitgeber", "arbeitskleidung", "arbeitsklamotten",
            "homeoffice", "arbeitsweg", "kindergarten", "tagesmutter", "handwerker",
            "vermiet",
        )
    )
    if not steuerkontext:
        return None
    kandidaten = []
    muster = (
        r"\b(?:steuerjahr|steuererklärung|steuererklaerung|erklärung|erklaerung|"
        r"lohnsteuerbescheinigung|grundsteuerbescheid|grundabgabenbescheid|gebührenbescheid)"
        r"\s*(?:für|fuer|von|aus)?\s*['’]?(23|24|25)\b",
        r"\b(?:für|fuer|von|aus|in)\s*['’]?(23|24|25)\b",
    )
    for ausdruck in muster:
        for treffer in re.finditer(ausdruck, klein):
            rest = klein[treffer.end():]
            naechstes_wort = re.match(r"\s*([a-zäöüß%]+)", rest)
            if naechstes_wort and naechstes_wort.group(1) in {
                "tag", "tage", "tagen", "euro", "eur", "km", "kilometer", "prozent", "%",
            }:
                continue
            kandidaten.append(2000 + int(treffer.group(1)))
    return kandidaten[-1] if kandidaten else None


def normalisiere_kurzes_steuerjahr(text: str) -> str:
    """Schreibt ein sicher erkanntes Kurzjahr direkt vierstellig aus."""
    jahr = steuerjahr_aus_text(text)
    if jahr is None or str(jahr) in (text or ""):
        return text
    kurz = str(jahr)[-2:]
    muster = re.compile(
        rf"\b(für|fuer|von|aus|in)\s*['’]?{kurz}\b",
        flags=re.IGNORECASE,
    )
    ersetzt, anzahl = muster.subn(lambda treffer: f"{treffer.group(1)} {jahr}", text, count=1)
    if anzahl:
        return ersetzt
    dokument_muster = re.compile(
        rf"\b(steuerjahr|steuererklärung|steuererklaerung|erklärung|erklaerung|"
        rf"lohnsteuerbescheinigung|grundsteuerbescheid|grundabgabenbescheid|gebührenbescheid)"
        rf"\s*['’]?{kurz}\b",
        flags=re.IGNORECASE,
    )
    return dokument_muster.sub(lambda treffer: f"{treffer.group(1)} {jahr}", text, count=1)


def bestimme_steuerjahr(
    frage: str,
    steuerjahr: int | str | None = None,
    steuerprofil: dict | None = None,
) -> int | None:
    """Priorität: konkrete Frage, danach ausdrücklich übergebene UI-Auswahl.

    Der Profilwert ist nur ein vorläufiger Vorschlag für den Dialog und darf
    eine allgemeine Fachfrage nicht stillschweigend auf ein Jahr festlegen.
    """
    aus_frage = steuerjahr_aus_text(frage)
    if aus_frage:
        return aus_frage
    try:
        auswahl = int(str(steuerjahr).strip())
    except (TypeError, ValueError):
        auswahl = None
    if auswahl in UNTERSTUETZTE_STEUERJAHRE:
        return auswahl
    return None


def quelle_passt_zum_steuerjahr(payload: dict, steuerjahr: int | None) -> bool:
    """Verhindert, dass spätere Jahreswerte in frühere Erklärungen gelangen."""
    if steuerjahr is None:
        return True
    gueltig_fuer = payload.get("gueltig_fuer")
    if isinstance(gueltig_fuer, list):
        return steuerjahr in {int(jahr) for jahr in gueltig_fuer if str(jahr).isdigit()}
    if payload.get("jahr_unabhaengig") is True:
        return True

    quellenjahr = str(payload.get("steuerjahr", ""))
    if steuerjahr not in UNTERSTUETZTE_STEUERJAHRE:
        # Außerhalb des neuen Pakets bleibt der bisherige Bestand nutzbar, aber
        # eine ausdrücklich datierte Quelle aus einem anderen Jahr wird nicht
        # als exakter Jahreswert behandelt.
        if quellenjahr.isdigit() and int(quellenjahr) == steuerjahr:
            return True
        return not payload.get("jahr_abhaengig", False)

    quelle_id = str(payload.get("quelle_id", ""))
    kategorie = str(payload.get("kategorie", ""))
    datei = str(payload.get("datei", ""))
    if quelle_id.startswith("elster_est_"):
        return str(steuerjahr) in quelle_id
    if payload.get("jahr_abhaengig") is True:
        return quellenjahr == str(steuerjahr)

    # Der Altbestand wurde überwiegend pauschal als 2026 markiert. Quellen mit
    # dieser Kennzeichnung werden für 2023–2025 nur verwendet, wenn sie später
    # ausdrücklich als jahresunabhängig geprüft wurden.
    markierung = f"{kategorie} {datei}".lower()
    if "2026" in markierung or quellenjahr == "2026":
        return False
    return True


def format_euro(wert: int) -> str:
    return f"{wert:,}".replace(",", ".") + " Euro"
