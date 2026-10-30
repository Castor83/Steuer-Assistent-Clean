"""Frageaspekte für Suche und Quellenwahl, ohne vorgefertigte Fachantworten."""

from dataclasses import dataclass
import re
from antwortentscheidung import _normalisiere


@dataclass(frozen=True)
class Fragefokus:
    suchbegriffe: str
    thema: str
    aspekte: tuple[str, ...]

    def passt(self, payload: dict) -> bool:
        # Überschrift und Kategorie beschreiben den Gegenstand einer Quelle.
        # Eine beiläufige Erwähnung im Volltext reicht für die Freigabe nicht.
        titel = _normalisiere(" ".join(str(payload.get(k, "")) for k in
                                      ("quelle", "titel", "kategorie", "paragraph")))
        return self.thema in titel and any(aspekt in titel for aspekt in self.aspekte)


def bestimme_fragefokus(frage: str) -> Fragefokus | None:
    text = _normalisiere(frage)
    text = next((zeile.strip() for zeile in reversed(text.splitlines()) if zeile.strip()), text)
    if (
        ("beruflich" in text and re.search(r"\b(?:ausgaben|kosten)\b", text))
        and any(w in text for w in ("zusatz", "extra", "pauschbetrag"))
        and not any(w in text for w in ("selbstandig", "betrieb", "freiberuf", "gewerb"))
    ):
        return Fragefokus("Werbungskosten Arbeitnehmer-Pauschbetrag § 9a EStG",
                          "arbeitnehmer", ("pausch", "9a"))
    if any(w in text for w in ("leerstand", "steht leer", "leer stehend")) and any(
        w in text for w in ("kosten", "abzieh", "abzug", "absetz")
    ):
        return Fragefokus("Vermietung Leerstand Werbungskosten Vermietungsabsicht",
                          "vermiet", ("werbungskosten", "eigenheim", "leerstand"))
    if (
        any(w in text for w in ("geschatzt", "schatzung"))
        and "erklar" in text
        and any(w in text for w in ("finanzamt", "bescheid"))
    ):
        return Fragefokus("Schätzung Abgabepflicht Steuererklärung § 149 AO",
                          "erklar", ("162", "schatzung"))
    if "einspruch" in text and any(w in text for w in ("zahl", "rechnung", "vollziehung")):
        return Fragefokus("Einspruch Zahlung Aussetzung der Vollziehung § 361 AO",
                          "einspruch", ("zahlung", "vollziehung", "361"))
    if "beleg" in text and any(w in text for w in ("schick", "einreich", "senden", "vorleg")):
        return Fragefokus("Belegvorhaltepflicht Belege Einkommensteuererklärung Anforderung",
                          "beleg", ("vorhalt", "einkommensteuer", "unterlagen"))
    if "grundsteuer" in text:
        # „erklären“ beschreibt hier nur den gewünschten Sprachstil und darf
        # nicht als „Grundsteuererklärung“ fehlgedeutet werden.
        if "grundsteuer zurechnung und befreiung" in text:
            return None
        if any(w in text for w in ("modell", "uberall", "bundesweit", "je land", "je bundesland")):
            return Fragefokus("Grundsteuer Bundesmodell Ländermodelle Länderöffnungsklausel",
                              "grundsteuer", (
                                  "landermodelle", "bundesmodell", "flachenmodell",
                                  "aquivalenzmodell", "baygrstg",
                              ))
        if any(w in text for w in ("erklar", "formular", "meld", "anzeig")):
            return Fragefokus("Grundsteuer Erklärung Anzeigepflicht Landesmodell Zuständigkeit",
                              "grundsteuer", ("erklar", "anzeig", "zustand", "modelle"))
    if "einspruch" in text and any(w in text for w in ("frist", "wie lange", "bis wann", "zeit")):
        # Die Dauer der behördlichen Bearbeitung ist keine Einlegungsfrist.
        if not any(w in text for w in ("bearbeit", "dauert", "entscheidung", "warte")):
            return Fragefokus("Einspruchsfrist Bekanntgabe § 355 AO",
                              "einspruch", ("frist", "355"))
    if "kindergeld" in text and any(w in text for w in ("anspruch", "bekomm", "berechtigt")):
        if not any(w in text for w in ("wie viel", "wie hoch", "betrag", "freibetrag", "zusatzlich")):
            return Fragefokus("Kindergeld berücksichtigungsfähige Kinder § 63 § 32 EStG",
                              "kind", ("anspruch", "berucksichtig", "63"))
    return None
