"""Entscheidet vor dem Fachpfad, ob der Sachverhalt beantwortbar ist.

Dieses Modul enthält bewusst keine steuerlichen Ergebnisse. Es beschreibt nur,
welche Angaben eine Anfrage für eine belastbare Prüfung benötigt.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
import unicodedata


class Antwortstatus(str, Enum):
    ANTWORT = "ANTWORT"
    RUECKFRAGE = "RUECKFRAGE"
    ABLEHNUNG = "ABLEHNUNG"


@dataclass(frozen=True)
class Vorpruefung:
    status: Antwortstatus
    grund: str
    text: str = ""
    fehlende_angaben: tuple[str, ...] = ()


@dataclass(frozen=True)
class AntwortErgebnis:
    status: Antwortstatus
    text: str
    quellen: tuple
    grund: str


ANTWORTBAR = Vorpruefung(Antwortstatus.ANTWORT, "Sachverhalt ausreichend")


def _normalisiere(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.casefold())
    return "".join(zeichen for zeichen in text if not unicodedata.combining(zeichen))


def _enthaelt(text: str, *muster: str) -> bool:
    return any(musterteil in text for musterteil in muster)


def _rolle_aus_text(text: str, profil: dict | None) -> str | None:
    profil = profil or {}
    profiltext = _normalisiere(" ".join(f"{k} {v}" for k, v in profil.items()))
    gesamt = f"{text} {profiltext}"
    if _enthaelt(gesamt, "mieter", "zur miete", "gemietet"):
        return "mieter"
    if _enthaelt(gesamt, "eigentumer", "mein grundstuck", "mein haus", "meine wohnung"):
        return "eigentümer"
    return None


def _bundesland_vorhanden(text: str, profil: dict | None) -> bool:
    laender = (
        "baden-wurttemberg", "bayern", "berlin", "brandenburg", "bremen",
        "hamburg", "hessen", "mecklenburg-vorpommern", "niedersachsen",
        "nordrhein-westfalen", "rheinland-pfalz", "saarland", "sachsen",
        "sachsen-anhalt", "schleswig-holstein", "thuringen",
    )
    profil = profil or {}
    gesamt = f"{text} {_normalisiere(' '.join(map(str, profil.values())))}"
    return any(land in gesamt for land in laender)


def pruefe_sachverhalt(frage: str, steuerprofil: dict | None = None) -> Vorpruefung:
    """Fordert nur Angaben an, die vor einer Fachprüfung zwingend fehlen."""
    text = _normalisiere(frage).strip()
    frageteil = next(
        (zeile.strip() for zeile in reversed(text.splitlines()) if zeile.strip()),
        text,
    )

    # Nicht reale Rechtssubjekte, Orte und Vorgänge dürfen nicht durch bloße
    # Ähnlichkeit zu echten Steuerbegriffen zu einer Fachantwort werden.
    fiktionssignale = (
        "gedankenubertragung", "zeitmaschine", "einhorn", "auf dem mond",
        "erfundenes land",
    )
    if any(signal in text for signal in fiktionssignale) or (
        "traum" in text and "wirtschaftsgut" in text
    ) or (
        "roboter" in text and "steuerklasse" in text
    ):
        return Vorpruefung(
            Antwortstatus.ABLEHNUNG,
            "Kein realer steuerlicher Sachverhalt",
            "Dazu liegt kein realer steuerlicher Sachverhalt mit einer passenden amtlichen Quelle vor. Deshalb gebe ich keine steuerliche Behauptung aus.",
        )

    if "steuer-id" in text and _enthaelt(text, "erraten", "raten"):
        return Vorpruefung(
            Antwortstatus.ABLEHNUNG,
            "Geschützte Kennung ist nicht ableitbar",
            "Eine Steuer-ID kann ich ohne deine Unterlagen nicht kennen oder erraten.",
        )

    if re.search(r"steuerbonus fur (besonders |sehr )?[a-z]+ (nachbarn|menschen)", text):
        return Vorpruefung(
            Antwortstatus.ABLEHNUNG,
            "Kein belegter steuerlicher Tatbestand",
            "Dafür habe ich keine passende amtliche Grundlage. Deshalb gebe ich keine steuerliche Behauptung aus.",
        )

    # Ein unaufgelöstes Demonstrativpronomen bezeichnet keinen prüfbaren
    # Sachverhalt. Konkrete Substantive in längeren Fragen bleiben unberührt.
    if len(text.split()) <= 8 and re.search(r"\b(das|dies|diese|diesen)\b", text):
        if _enthaelt(text, "absetzen", "finanzamt melden", "steuerlich geltend"):
            return Vorpruefung(
                Antwortstatus.RUECKFRAGE,
                "Bezug der Frage fehlt",
                "Worum geht es genau – welche Ausgabe, Einnahme oder welchen Sachverhalt meinst du?",
                ("Sachverhalt",),
            )

    if re.search(r"\b(welche|welchen) anlage\b", text) and re.search(
        r"\b(dafur|hierfur|das)\b", text
    ):
        return Vorpruefung(
            Antwortstatus.RUECKFRAGE,
            "Erklärungsgegenstand fehlt",
            "Für welchen Sachverhalt oder welche Art von Einkünften suchst du die Anlage?",
            ("Sachverhalt oder Einkunftsart",),
        )

    unbestimmte_ausgabe = (
        _enthaelt(
            text,
            "diese rechnung",
            "diesen rechnungsbetrag",
            "einen betrag in bar",
            "betrag bar",
        )
        and _enthaelt(text, "steuer", "berucksichtigen", "absetz", "angeben")
        and not _enthaelt(text, "handwerker", "spende", "kinderbetreuung", "haushaltsnah")
    )
    if unbestimmte_ausgabe:
        return Vorpruefung(
            Antwortstatus.RUECKFRAGE,
            "Art der Ausgabe fehlt",
            "Wofür war die Ausgabe beziehungsweise Rechnung, und in welchem Zusammenhang ist sie entstanden?",
            ("Art und Anlass der Ausgabe",),
        )

    if (
        _enthaelt(text, "noch geld bekommen", "irgendeine zahlung")
        and _enthaelt(text, "erklar", "arbeitsagentur", "eintragen")
    ):
        return Vorpruefung(
            Antwortstatus.RUECKFRAGE,
            "Art der Einnahme oder Leistung fehlt",
            "Welche Zahlung oder Leistung war das genau, und welche Bescheinigung hast du dazu erhalten?",
            ("Leistungsart",),
        )

    if "arbeitgeber" in text and _enthaelt(text, "etwas bezahlt", "etwas gezahlt"):
        return Vorpruefung(
            Antwortstatus.RUECKFRAGE,
            "Art der Arbeitgeberleistung fehlt",
            "Welche Leistung hat der Arbeitgeber bezahlt und wofür?",
            ("Arbeitgeberleistung",),
        )

    ist_grundsteuererklaerung = (
        "grundsteuer" in frageteil
        and (
            _enthaelt(frageteil, "erklar", "formular")
            or bool(re.search(r"\b(abgabe|abgeben)\b", frageteil))
        )
        and "extra erklar" not in frageteil
        and not _enthaelt(frageteil, "wertbescheid", "messbescheid", "steuerbescheid")
        and _enthaelt(
            frageteil, "muss", "brauche", "pflicht", "abgabe", "abgeben",
            "fur mich", "für mich",
        )
    )
    if ist_grundsteuererklaerung:
        rolle = _rolle_aus_text(text, steuerprofil)
        fehlend = []
        if rolle is None:
            fehlend.append("Eigentümerstatus")
        # Für Mieter ist schon die Zuständigkeit prüfbar; bei Eigentümern hängt
        # das Verfahren dagegen vom Landesmodell ab.
        if rolle != "mieter" and not _bundesland_vorhanden(text, steuerprofil):
            fehlend.append("Bundesland")
        if fehlend:
            return Vorpruefung(
                Antwortstatus.RUECKFRAGE,
                "Landesabhängiger Sachverhalt unvollständig",
                "Bist du Eigentümer oder Mieter, und in welchem Bundesland liegt das Grundstück?",
                tuple(fehlend),
            )

    if "grundsteuer" in text and _enthaelt(text, "ausrechnen", "berechnen"):
        return Vorpruefung(
            Antwortstatus.RUECKFRAGE,
            "Berechnungsgrundlagen der Grundsteuer fehlen",
            "Welche Gemeinde, welchen Grundsteuermessbetrag oder Grundsteuerwert und welchen Hebesatz nennt dein Bescheid?",
            ("Bescheid- und Gemeindedaten",),
        )

    if "grundsteuer" in text and _enthaelt(text, "post", "schreiben") and _enthaelt(
        text, "was muss", "was tun"
    ):
        return Vorpruefung(
            Antwortstatus.RUECKFRAGE,
            "Bescheidart fehlt",
            "Welches Schreiben ist es genau: Grundsteuerwertbescheid, Messbescheid oder Grundsteuerbescheid der Gemeinde?",
            ("Bescheidart",),
        )

    ist_berechnung = _enthaelt(
        text, "wie hoch ist meine einkommensteuer", "einkommensteuer berechnen",
        "wie viel steuer bekomme", "wie hoch ist meine steuererstattung",
    )
    hat_betrag = bool(re.search(r"\b\d[\d .,'€]*\b", text))
    if ist_berechnung and not hat_betrag:
        return Vorpruefung(
            Antwortstatus.RUECKFRAGE,
            "Berechnungsgrundlage fehlt",
            "Welche Einkünfte, Beträge und persönlichen Daten soll ich für die Berechnung berücksichtigen?",
            ("Einkünfte und Beträge", "persönliche Besteuerungsmerkmale"),
        )

    if _enthaelt(text, "darf ich die fahrt absetzen", "kann ich die fahrt absetzen"):
        return Vorpruefung(
            Antwortstatus.RUECKFRAGE,
            "Art der Fahrt fehlt",
            "Wohin führte die Fahrt – zum Arbeitsweg, zu einem Auswärtstermin oder zu einem vermieteten Objekt?",
            ("Fahrtart",),
        )

    if "arbeitsweg" in text and _enthaelt(text, "was brauchst", "welche angaben"):
        return Vorpruefung(
            Antwortstatus.RUECKFRAGE,
            "Arbeitstage für die Berechnung fehlen",
            "An wie vielen tatsächlichen Arbeitstagen hast du diesen Arbeitsweg zurückgelegt?",
            ("Arbeitstage",),
        )

    ist_allgemeine_arbeitswegfrage = (
        _enthaelt(text, "arbeitsweg", "weg zur arbeit", "fahrt zur arbeit")
        and _enthaelt(text, "absetz", "steuerlich")
    )
    if ist_allgemeine_arbeitswegfrage:
        hat_entfernung = bool(re.search(r"\b\d{1,4}(?:[,.]\d+)?\s*(?:km|kilometer)\b", text))
        hat_arbeitstage = bool(re.search(r"\b\d{1,3}\s+(?:arbeits|fahrt)?tage?n?\b", text))
        fehlend = []
        if not hat_entfernung:
            fehlend.append("einfache Entfernung")
        if not hat_arbeitstage:
            fehlend.append("tatsächliche Arbeitstage")
        if fehlend:
            if len(fehlend) == 2:
                rueckfrage = (
                    "Wie viele Kilometer beträgt die einfache Strecke zur ersten Tätigkeitsstätte, "
                    "und an wie vielen tatsächlichen Arbeitstagen bist du dorthin gefahren?"
                )
            elif fehlend[0] == "einfache Entfernung":
                rueckfrage = "Wie viele Kilometer beträgt die einfache Strecke zur ersten Tätigkeitsstätte?"
            else:
                rueckfrage = "An wie vielen tatsächlichen Arbeitstagen bist du zur ersten Tätigkeitsstätte gefahren?"
            return Vorpruefung(
                Antwortstatus.RUECKFRAGE,
                "Angaben zum Arbeitsweg fehlen",
                rueckfrage,
                tuple(fehlend),
            )

    if _enthaelt(text, "arbeite zu hause", "arbeite zuhause") and _enthaelt(
        text, "welche kosten", "was kann"
    ):
        return Vorpruefung(
            Antwortstatus.RUECKFRAGE,
            "Homeoffice-Sachverhalt unvollständig",
            "An wie vielen Tagen arbeitest du zu Hause, gibt es einen anderen Arbeitsplatz und geht es um die Tagespauschale oder ein häusliches Arbeitszimmer?",
            ("Homeoffice-Art und Tage",),
        )

    if "mietshaus" in text and _enthaelt(text, "etwas repariert", "etwas erneuert"):
        return Vorpruefung(
            Antwortstatus.RUECKFRAGE,
            "Art und Umfang der Baumaßnahme fehlen",
            "Was wurde repariert, wann wurde das Haus angeschafft und wie hoch waren die Kosten?",
            ("Baumaßnahme", "Anschaffungszeitpunkt", "Kosten"),
        )

    if "insolvenzgeld" in text and _enthaelt(text, "bekomme ich", "anspruch") and not _enthaelt(
        text, "insolvenzverfahren", "insolvenzereignis", "insolvent", "abgewiesen",
        "nachzahlung", "steuer", "progression", "eintrag",
        "insolvenzantrag", "insolvenz angemeldet", "bescheinigung", "nachweis",
        "beleg", "welche monate", "drei monate", "zeitraum",
    ):
        return Vorpruefung(
            Antwortstatus.RUECKFRAGE,
            "Maßgebliches Insolvenzereignis fehlt",
            "Ist bereits ein Insolvenzereignis beim Arbeitgeber eingetreten, etwa die Eröffnung des Insolvenzverfahrens?",
            ("Insolvenzereignis",),
        )

    if "rechtsbehelfsbelehrung" in text and _enthaelt(text, "was kann", "was tun"):
        return Vorpruefung(
            Antwortstatus.RUECKFRAGE,
            "Bescheid und Zugangsdaten fehlen",
            "Um welchen Bescheid geht es, welches Datum trägt er und wann ist er dir zugegangen?",
            ("Bescheidart", "Zugang"),
        )

    if _enthaelt(text, "ob der betrag auf meinem bescheid stimmt", "bescheid stimmt"):
        return Vorpruefung(
            Antwortstatus.RUECKFRAGE,
            "Bescheidinhalt fehlt",
            "Welcher Bescheid ist es, welchen Betrag und welche Berechnungsgrundlagen nennt er?",
            ("Bescheidinhalt",),
        )

    if _enthaelt(text, "erklarung noch nicht abgegeben", "noch keine erklarung abgegeben") and _enthaelt(
        text, "zu spat", "frist"
    ):
        return Vorpruefung(
            Antwortstatus.RUECKFRAGE,
            "Erklärungsart und Beratung fehlen",
            "Für welches Steuerjahr und welche Erklärung gilt die Frage, bist du abgabepflichtig und wirst du steuerlich beraten?",
            ("Erklärungsart", "Abgabepflicht", "Beratung"),
        )

    ist_fahrzeugkostenfrage = (
        _enthaelt(text, "e-bike", "ebike", "pedelec")
        and _enthaelt(text, "absetz", "steuerlich")
    )
    nutzung_geklart = _enthaelt(
        text,
        "arbeitsweg", "erste tatigkeitsstatte", "dienstfahrrad", "firmenrad",
        "arbeitgeber", "betrieblich", "selbstandig", "auswartstermin",
    )
    if ist_fahrzeugkostenfrage and not nutzung_geklart:
        return Vorpruefung(
            Antwortstatus.RUECKFRAGE,
            "Nutzungsart des Fahrzeugs fehlt",
            "Geht es um einen privaten Kauf, deinen Arbeitsweg, ein Dienstfahrrad oder eine betriebliche Nutzung?",
            ("Nutzungsart",),
        )

    return ANTWORTBAR


def strukturiere_ausgabe(text: str, quellen: list) -> AntwortErgebnis:
    """Macht den Ausgang der kompatiblen Antwortpipeline explizit."""
    if quellen:
        status = Antwortstatus.ANTWORT
        grund = "Fachantwort mit geprüften Quellen"
    elif "?" in text:
        status = Antwortstatus.RUECKFRAGE
        grund = "Entscheidende Sachverhaltsangabe fehlt"
    else:
        status = Antwortstatus.ABLEHNUNG
        grund = "Keine ausreichend tragfähige Evidenz"
    return AntwortErgebnis(status, text, tuple(quellen), grund)
