"""Vorsichtige Interpretationshilfen fuer Alltagssprache und Tippfehler.

Die Originalnachricht bleibt immer erhalten. Die Hinweise erweitern nur die Suche
und feste Dialogregeln; sie ersetzen keine vom Nutzer gemachte Angabe.
"""

from __future__ import annotations

from difflib import SequenceMatcher
import re
import unicodedata


def normalisiere(text: str) -> str:
    return "".join(
        zeichen
        for zeichen in unicodedata.normalize("NFKD", str(text).lower())
        if not unicodedata.combining(zeichen)
    ).replace("ß", "ss")


def normalisiere_mit_tippfehlern(text: str) -> str:
    """Korrigiert nur eine kleine, kontrollierte Liste häufiger Fachwortfehler."""
    normal = normalisiere(text)
    ersetzungen = {
        "steuererklerung": "steuererklarung",
        "steuererklahrung": "steuererklarung",
        "steurerklarung": "steuererklarung",
        "grundsteur": "grundsteuer",
        "grundstuer": "grundsteuer",
        "versicherrung": "versicherung",
        "versichrung": "versicherung",
        "sanirung": "sanierung",
        "wohnnung": "wohnung",
        "vermiettung": "vermietung",
    }
    for falsch, richtig in ersetzungen.items():
        normal = re.sub(rf"\b{falsch}\b", richtig, normal)
    return normal


def _woerter(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", normalisiere(text))


def _aehnliches_wort(text: str, *ziele: str, schwelle: float = 0.78) -> bool:
    for wort in _woerter(text):
        if len(wort) < 5:
            continue
        for ziel in ziele:
            if wort == ziel or SequenceMatcher(None, wort, ziel).ratio() >= schwelle:
                return True
    return False


def alltagssprache_hinweise(text: str) -> list[str]:
    """Leitet nur bei klaren Signalen wenige kanonische Bedeutungen ab."""
    normal = normalisiere_mit_tippfehlern(text)
    hinweise: list[str] = []

    rohrschaden = (
        _aehnliches_wort(normal, "rohrbruch", "wasserrohrbruch")
        or bool(re.search(r"\brohr\w*\b.{0,35}\b(?:kaputt|geplatzt|leck|gebrochen|bruch)\b", normal))
        or bool(re.search(r"\bwasser(?:schaden|rohrschaden)\b", normal))
    )
    if rohrschaden:
        hinweise.append("Thema: Reparatur nach einem Rohrbruch oder vergleichbaren Wasserschaden.")

    eigene_wohnung = (
        bool(re.search(r"\b(?:mein\w*|unser\w*|eigene\w*)\s+(?:wohnung|bude|haus)\b", normal))
        or bool(re.search(r"\bbei\s+(?:mir|uns)\s+(?:drin|in\s+der\s+(?:wohnung|bude)|im\s+haus)\b", normal))
        or "ich wohne da selbst" in normal
    )
    if eigene_wohnung:
        hinweise.append("Betroffener Bereich: die selbst genutzte eigene Wohnung oder das eigene Haus.")

    vermieteter_bereich = (
        bool(re.search(r"\bbei\s+(?:dem|den|meinem|meinen)\s+mieter", normal))
        or bool(re.search(r"\b(?:mieterwohnung|vermietete\w*\s+wohnung)\b", normal))
    )
    if vermieteter_bereich:
        hinweise.append("Betroffener Bereich: eine vermietete Wohnung.")

    versicherung = _aehnliches_wort(
        normal, "versicherung", "gebaudeversicherung", "wohngebaudeversicherung"
    )
    kosten_uebernommen = bool(
        re.search(r"\b(?:zahl\w*|bezahl\w*|erstatt\w*|ubernomm\w*|ubernehm\w*|regulier\w*|gelaufen)\b", normal)
    ) or "ging uber" in normal or "lief uber" in normal
    if versicherung and kosten_uebernommen:
        hinweise.append("Die Gebäudeversicherung hat die Kosten möglicherweise bezahlt, übernommen oder erstattet.")

    if bool(re.search(r"\b(?:selbstbehalt|eigenanteil|selber\s+gezahlt|selbst\s+gezahlt)\b", normal)):
        hinweise.append("Es geht um einen selbst getragenen Eigenanteil oder Selbstbehalt.")

    steuerfrage = (
        bool(re.search(r"\b(?:absetz\w*|steuerlich|finanzamt|steuererklar\w*|steuer\s+sparen)\b", normal))
        or "was wieder" in normal
        or "krieg ich was" in normal
        or "bringt mir das bei der steuer" in normal
    )
    if steuerfrage:
        hinweise.append("Frageziel: steuerliche Berücksichtigung in der Einkommensteuererklärung.")

    if bool(
        re.search(
            r"\b(?:von\s+zuhause|zu\s+hause|daheim)\s+(?:gearbeitet|am\s+arbeiten)\b",
            normal,
        )
    ):
        hinweise.append("Thema: berufliche Tätigkeit im Homeoffice.")
    if bool(re.search(r"\b(?:weg|fahrt)\s+zur\s+arbeit\b|\bpendel\w*\b", normal)):
        hinweise.append("Thema: Arbeitsweg beziehungsweise Entfernungspauschale.")
    if bool(
        re.search(
            r"\b\d+(?:[,.]\d+)?\s*(?:km|kilometer)\s+einfach\b",
            normal,
        )
    ):
        hinweise.append(
            "Thema: Arbeitsweg beziehungsweise Entfernungspauschale. Die genannte "
            "Kilometerzahl ist die einfache Entfernung zwischen Wohnung und "
            "erster Tätigkeitsstätte. Das Wort ‚einfach‘ bedeutet hier nicht, dass nur die "
            "Hin- oder nur die Rückfahrt stattgefunden hat; die Entfernung darf nicht halbiert werden."
        )

    # Reihenfolge erhalten und doppelte Hinweise vermeiden.
    return list(dict.fromkeys(hinweise))


def interpretationsblock(text: str) -> str:
    hinweise = alltagssprache_hinweise(text)
    if not hinweise:
        return ""
    return (
        "\nInterpretationshilfe aus der Alltagssprache (bei Widerspruch gilt die Originalnachricht):\n- "
        + "\n- ".join(hinweise)
    )


def _grundabgabenort(text: str) -> str | None:
    muster = re.compile(
        r"\bgrundabgaben(?:bescheid)?\s+([a-zäöüß-]+)\b",
        flags=re.IGNORECASE,
    )
    treffer = muster.search(str(text))
    if not treffer:
        return None
    ort = treffer.group(1)
    keine_orte = {
        "aus", "mit", "fur", "fuer", "vom", "von", "des", "der", "die", "das",
        "grundsteuer", "strassenreinigung", "abwasser", "abwassergebuhren", "mull", "gebuhren",
    }
    return None if normalisiere(ort) in keine_orte else ort


def grundabgabenort(text: str) -> str | None:
    """Liest einen direkt nach ``Grundabgaben`` genannten Ort vorsichtig aus."""
    ort = _grundabgabenort(text)
    return ort.title() if ort else None


def normalisiere_grundabgabenort(text: str) -> str:
    """Macht einen direkt genannten Ort fuer das Sprachmodell eindeutig.

    Umgangssprachlich wird beispielsweise ``grundabgaben erlangen`` gesagt. Die
    vorsichtige Ergaenzung von ``Bescheid aus`` verhindert, dass der Ortsname bei
    der sprachlichen Glaettung verloren geht. Bereits klare Formulierungen und
    Woerter wie ``mit`` oder ``vom`` bleiben unveraendert.
    """
    ort = _grundabgabenort(text)
    if not ort:
        return str(text)
    muster = re.compile(
        rf"\bgrundabgaben(?:bescheid)?\s+{re.escape(ort)}\b",
        flags=re.IGNORECASE,
    )
    return muster.sub(f"Grundabgabenbescheid aus {ort.title()}", str(text), count=1)


def bewahre_grundabgabenort(original: str, ausgabe: str) -> str:
    """Bewahrt einen ausdruecklich genannten Ortsnamen buchstabengetreu."""
    ort = _grundabgabenort(original)
    if not ort or re.search(rf"\b{re.escape(ort)}\b", ausgabe, flags=re.IGNORECASE):
        return ausgabe

    # Eine kleine Schreibabweichung nach "aus/in/von" wird korrigiert.
    nach_praeposition = re.search(
        r"\b(?:aus|in|von)\s+([a-zäöüß-]+)\b",
        ausgabe,
        flags=re.IGNORECASE,
    )
    if nach_praeposition and SequenceMatcher(
        None, normalisiere(nach_praeposition.group(1)), normalisiere(ort)
    ).ratio() >= 0.72:
        start, ende = nach_praeposition.span(1)
        return ausgabe[:start] + ort.title() + ausgabe[ende:]

    # Falls das Modell den Ort ganz auslaesst, bleibt die explizite Nutzerangabe
    # durch eine neutrale Einfuegung am Dokumentnamen erhalten.
    dokument = re.search(r"\bGrundabgabenbescheid(?:e)?\b", ausgabe, flags=re.IGNORECASE)
    if dokument:
        return ausgabe[: dokument.end()] + f" aus {ort.title()}" + ausgabe[dokument.end() :]
    return ausgabe


def bewahre_beschaeftigungsstatus(original: str, ausgabe: str) -> str:
    """Verhindert das Wegglaetten eines ausdruecklichen Angestelltenstatus."""
    original_normal = normalisiere_mit_tippfehlern(original)
    ausgabe_normal = normalisiere_mit_tippfehlern(ausgabe)
    if re.search(r"\b(?:bin|als)\s+angestellt\b", original_normal) and not re.search(
        r"\b(?:angestellt|arbeitnehmer(?:in)?)\b", ausgabe_normal
    ):
        return "Ich bin angestellt. " + ausgabe.lstrip()
    return ausgabe


def kanonisierungs_hinweise(text: str, gespraechstext: str = "") -> list[str]:
    """Liefert nur sprachlich sichere Strukturhinweise für die Kanonisierung."""
    normal = normalisiere_mit_tippfehlern(text)
    gesamtkontext = normalisiere_mit_tippfehlern(gespraechstext + " " + text)
    hinweise: list[str] = []

    if (
        "arbeitgeber" in normal
        and any(wort in normal for wort in ("vorgeschrieben", "schreibt", "verlangt"))
        and re.search(r"\b(?:selbst|selber)\s+bezahlt\b", normal)
    ):
        hinweise.append(
            "Der Arbeitgeber hat die Anschaffung nur vorgeschrieben; der Nutzer hat sie selbst bezahlt."
        )

    if (
        "versicherung" in gesamtkontext
        and "material" in normal
        and any(wort in normal for wort in ("arbeit", "arbeitskosten", "arbeitslohn"))
    ):
        if re.search(r"\bmaterial\b.*\b(?:arbeit|arbeitskosten|arbeitslohn)\b", normal):
            hinweise.append(
                "Die Versicherung hat die Materialkosten übernommen; die Arbeitskosten hat der Nutzer selbst bezahlt."
            )
            hinweise.append(
                "Formuliere daraus die vollständige Frage zur steuerlichen Berücksichtigung des selbst bezahlten Anteils."
            )

    if (
        "versicherung" in gesamtkontext
        and re.search(r"\b(?:nur\s+)?(?:die\s+)?(?:halfte|haelfte|50\s*prozent)\b", normal)
        and any(wort in gesamtkontext for wort in ("rechnung", "kosten", "erstattet", "ubernommen"))
    ):
        hinweise.append(
            "Die Versicherung hat nur die Hälfte der Rechnung oder Kosten übernommen; der übrige Teil wurde selbst getragen."
        )
        hinweise.append(
            "Formuliere die vollständige Steuerfrage zur Berücksichtigung des selbst getragenen Restes."
        )

    if (
        "reparatur" in gesamtkontext
        and "gemeinsame leitung" in normal
        and any(wort in normal for wort in ("mietwohnung", "mieter", "vermietet"))
        and "wohnung" in normal
    ):
        hinweise.append(
            "Die Reparatur betrifft eine gemeinsame Leitung der eigenen und einer vermieteten Wohnung."
        )
        hinweise.append(
            "Formuliere die vollständige Steuerfrage einschließlich der Zuordnung oder Aufteilung der Reparaturkosten."
        )

    if "grundabgaben" in normal:
        hinweise.append("Dokumentart: Grundabgabenbescheid.")
        ort = re.search(r"\bgrundabgaben(?:bescheid)?\s+([a-zäöüß-]+)\b", normal)
        if ort and ort.group(1) not in {"mit", "für", "fuer", "vom", "von", "des", "der", "die", "das"}:
            hinweise.append(
                f"Bewahre den ausdrücklich genannten Ort {ort.group(1).title()} in der Formulierung."
            )

    entfernung = re.search(r"\b(\d+(?:[,.]\d+)?)\s*(?:km|kilometer)\s+einfach\b", normal)
    if entfernung:
        hinweise.append(f"Die genannte einfache Strecke beträgt {entfernung.group(1)} Kilometer.")

    return list(dict.fromkeys(hinweise))
