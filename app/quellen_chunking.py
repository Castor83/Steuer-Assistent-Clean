"""Gemeinsame Segmentierung und Suchmetadaten fuer amtliche Quellenkarten."""

from __future__ import annotations

import re
from pathlib import Path


UNTERSTUETZTE_SUCHJAHRE = (2023, 2024, 2025, 2026)


def _saetze(text: str) -> list[str]:
    """Zerlegt redaktionelle Karten in kurze, in sich geschlossene Regeln."""
    text = " ".join(str(text or "").split())
    if not text:
        return []
    # Die Karten sind redaktionell als vollstaendige Saetze gepflegt. Ein Split
    # erfolgt nur vor einem wahrscheinlichen neuen Satz; gaengige Abkuerzungen
    # und Dezimalzahlen bleiben dadurch zusammen.
    teile = re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ§])", text)
    ergebnis: list[str] = []
    for teil in teile:
        teil = teil.strip()
        if not teil:
            continue
        if ergebnis and (
            len(teil) < 45
            or re.search(r"\b(?:z|u|d|bzw)\.$", ergebnis[-1], re.I)
            or re.search(r"\b\d{1,2}\.$", ergebnis[-1])
        ):
            ergebnis[-1] += " " + teil
        else:
            ergebnis.append(teil)
    return ergebnis


def segmentiere_quellentext(text: str, maximale_laenge: int = 760) -> list[str]:
    """Erzeugt regelnahe Chunks ohne verschiedene Steuerfragen zu vermischen."""
    ergebnis: list[str] = []
    for satz in _saetze(text):
        if len(satz) <= maximale_laenge:
            ergebnis.append(satz)
            continue
        # Sehr lange Saetze werden bevorzugt an Semikola getrennt. Bleibt ein
        # Teil zu lang, erfolgt ein wortweiser, verlustfreier Split.
        teile = [teil.strip() for teil in re.split(r"(?<=;)\s+", satz) if teil.strip()]
        for teil in teile:
            while len(teil) > maximale_laenge:
                grenze = teil.rfind(" ", 0, maximale_laenge + 1)
                if grenze < maximale_laenge // 2:
                    grenze = maximale_laenge
                ergebnis.append(teil[:grenze].strip())
                teil = teil[grenze:].strip()
            if teil:
                ergebnis.append(teil)
    return ergebnis


def suchjahre(quelle: dict) -> list[int]:
    """Normalisiert heterogene Jahresangaben fuer Qdrant-Payloadfilter."""
    gueltig = quelle.get("gueltig_fuer")
    if isinstance(gueltig, list):
        return sorted({int(jahr) for jahr in gueltig if str(jahr).isdigit()})
    if quelle.get("jahr_unabhaengig") is True:
        return list(UNTERSTUETZTE_SUCHJAHRE)
    wert = str(quelle.get("steuerjahr", ""))
    jahre = [int(jahr) for jahr in re.findall(r"20\d{2}", wert)]
    if len(jahre) == 2 and "-" in wert:
        return list(range(jahre[0], jahre[1] + 1))
    return jahre[:1]


def bundesland(quelle: dict) -> str | None:
    """Liest oder erkennt eine eindeutige laenderspezifische Quellenkarte."""
    explizit = str(quelle.get("bundesland", "")).strip()
    if explizit:
        return explizit
    kopf = " ".join(str(quelle.get(feld, "")) for feld in ("titel", "kategorie"))
    if re.search(r"\b(?:Bayern|bayerisch\w*)\b", kopf, re.I):
        return "Bayern"
    return None


def fristtyp(text: str) -> str | None:
    """Kennzeichnet Fristregeln getrennt von materiellen Zeiträumen."""
    norm = " ".join(str(text or "").lower().split())
    if re.search(r"(?:\b10\b|zehn)\s+jahr", norm):
        return "materieller_zeitraum"
    if (
        re.search(r"(?:zwei|2|drei|3)\s+monate", norm)
        and any(wort in norm for wort in (
            "antrag", "beantrag", "anzeig", "meld", "kenntnis", "frist",
        ))
    ) or (
        "einspruch" in norm
        and any(wort in norm for wort in ("monat", "frist", "bekanntgabe"))
    ):
        return "verfahrensfrist"
    return None


def quellenkarten_payloads(datei: Path, quelle: dict) -> list[dict]:
    """Erzeugt identische Payloads fuer lokalen und vektoriellen Abruf."""
    chunks = segmentiere_quellentext(quelle.get("inhalt", ""))
    land = bundesland(quelle)
    jahre = suchjahre(quelle)
    payloads: list[dict] = []
    for nummer, chunk in enumerate(chunks, start=1):
        payload = {
            "text": chunk,
            "quelle": quelle.get("titel", datei.stem),
            "herausgeber": quelle.get("herausgeber", ""),
            "paragraph": quelle.get("paragraph", ""),
            "steuerjahr": quelle.get("steuerjahr", "unbekannt"),
            "stand_abgerufen": quelle.get("stand_abgerufen", ""),
            "url": quelle.get("url", ""),
            "kategorie": quelle.get("kategorie", "Amtliche Quellenkarte"),
            "datei": datei.name,
            "quellenart": "quellenkarte",
            "chunk": nummer,
            "chunk_anzahl": len(chunks),
            "suchjahre": jahre,
        }
        for feld in (
            "jahr_abhaengig", "jahr_unabhaengig", "gueltig_fuer", "gesetz",
            "rechtsgebiet",
        ):
            if feld in quelle:
                payload[feld] = quelle[feld]
        if land:
            payload["bundesland"] = land
        zeittyp = fristtyp(chunk)
        if zeittyp:
            payload["fristtyp"] = zeittyp
        payloads.append(payload)
    return payloads


def embedding_text(payload: dict) -> str:
    """Bindet Norm, Land und Titel unmittelbar an den eingebetteten Regeltext."""
    teile = [
        payload.get("quelle", ""), payload.get("paragraph", ""),
        payload.get("kategorie", ""), payload.get("gesetz", ""),
        payload.get("bundesland", ""), payload.get("text", ""),
    ]
    return "\n".join(str(teil) for teil in teile if str(teil).strip())
