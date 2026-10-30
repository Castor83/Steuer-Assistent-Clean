"""Erstellt eine vorsichtige Unterlagen-Checkliste aus lokal erkannten Metadaten."""

from __future__ import annotations


ANFORDERUNGEN = {
    "allgemein": [
        ("stammdaten", "Steuer-ID, Bankverbindung und letzter Steuerbescheid", ("Einkommensteuerbescheid", "Sonstiger Steuerbescheid")),
        ("versicherung", "Kranken- und Pflegeversicherungsnachweis", ("Kranken- und Pflegeversicherungsbescheinigung", "Sonstige Versicherungsunterlage")),
    ],
    "arbeitnehmer": [
        ("lohn", "Elektronische Lohnsteuerbescheinigung", ("Elektronische Lohnsteuerbescheinigung",)),
        ("werbungskosten", "Belege zu Arbeitsweg, Homeoffice, Arbeitsmitteln, Fortbildung oder Dienstreisen", ("Fahrtkostenaufstellung", "Arbeitsmittelbeleg", "Fortbildungsunterlage", "Reisekostenunterlage")),
        ("lohnersatz", "Nachweise über mögliche Lohnersatzleistungen", ("Krankengeldbescheinigung", "Arbeitslosengeldbescheinigung", "Elterngeldbescheid", "Kurzarbeitergeldnachweis", "Insolvenzgeldbescheid", "Insolvenzgeldbescheinigung")),
    ],
    "insolvenzgeld": [
        ("insolvenzgeld_nachweis", "Leistungsnachweis oder Bescheid über das Insolvenzgeld", ("Insolvenzgeldbescheinigung",)),
        ("insolvenzgeld_lohn", "Arbeitsvertrag und letzte Verdienstabrechnungen zum offenen Arbeitsentgelt", ("Arbeitsvertrag", "Verdienstabrechnung")),
    ],
    "erbschaft": [
        ("erbschaft_erwerb", "Testament, Erbvertrag oder Erbschein zum Erwerb", ("Testament oder Erbvertrag", "Erbschein")),
        ("erbschaft_nachlass", "Aufstellung des Nachlasses und der Nachlassverbindlichkeiten", ("Nachlassaufstellung",)),
        ("erbschaft_bescheid", "Erbschaft- oder Schenkungsteuerbescheid, falls bereits vorhanden", ("Erbschaft- oder Schenkungsteuerbescheid",)),
    ],
    "kinder": [
        ("kinderbetreuung", "Rechnungen und Zahlungsnachweise zur Kinderbetreuung", ("Kinderbetreuungskosten",)),
    ],
    "vermietung": [
        ("mietvertrag", "Mietvertrag beziehungsweise Mietverträge", ("Mietvertrag",)),
        ("mieteinnahmen", "Aufstellung der Mieteinnahmen", ("Mieteinnahmenaufstellung",)),
        ("vermietungskosten", "Betriebs-, Hausgeld- und Darlehenszinsunterlagen", ("Betriebskostenabrechnung", "Hausgeldabrechnung", "Darlehenszinsbescheinigung")),
        ("grundsteuer_vermietung", "Grundsteuerbescheid für das Mietobjekt", ("Kommunaler Grundsteuerbescheid", "Sonstige Grundsteuerunterlage")),
    ],
    "rente": [
        ("rente", "Rentenbezugsmitteilung", ("Rentenbezugsmitteilung",)),
    ],
    "selbststaendig": [
        ("eur", "Einnahmenüberschussrechnung oder Gewinnermittlung", ("Einnahmenüberschussrechnung",)),
        ("umsatzsteuer", "Umsatzsteuer-Unterlagen, falls umsatzsteuerpflichtig", ("Umsatzsteuer-Voranmeldung",)),
    ],
    "kapital": [
        ("kapital", "Steuer- und Verlustbescheinigungen der Banken", ("Kapitalertragsteuerbescheinigung",)),
    ],
    "haushalt": [
        ("haushalt", "Spenden, Handwerker und haushaltsnahe Dienstleistungen", ("Spendenbescheinigung", "Handwerker- oder haushaltsnahe Dienstleistung")),
    ],
    "grundsteuer": [
        ("grundsteuer_basis", "In Bayern: Grundsteueräquivalenzbetragsbescheid; andernfalls Grundsteuerwertbescheid", ("Grundsteueräquivalenzbetragsbescheid", "Grundsteuerwertbescheid")),
        ("grundsteuermessbetrag", "Grundsteuermessbescheid", ("Grundsteuermessbescheid",)),
        ("grundsteuerkommune", "Grundsteuerbescheid der Stadt oder Gemeinde", ("Kommunaler Grundsteuerbescheid",)),
        ("grundstueck", "Grundstücks-, Flächen- oder Bodenrichtwertunterlagen", ("Grundbuchauszug", "Bodenrichtwertunterlage")),
    ],
}


def _jahr_passt(dokument: dict, steuerjahr: str) -> bool:
    jahr = str(dokument.get("steuerjahr", "Nicht erkannt"))
    return jahr in {steuerjahr, "Nicht erkannt", ""}


def erstelle_checkliste(steuerjahr: str, bereiche: list[str], dokumente: list[dict]) -> list[dict]:
    ausgewaehlt = ["allgemein", *[bereich for bereich in bereiche if bereich in ANFORDERUNGEN and bereich != "allgemein"]]
    ergebnis = []
    gesehen = set()
    for bereich in ausgewaehlt:
        for kennung, bezeichnung, typen in ANFORDERUNGEN[bereich]:
            if kennung in gesehen:
                continue
            gesehen.add(kennung)
            passend = [
                dokument
                for dokument in dokumente
                if dokument.get("dokumenttyp") in typen and _jahr_passt(dokument, steuerjahr)
            ]
            if passend:
                status = "Vorhanden"
                if all(dokument.get("status") == "Unklar" for dokument in passend):
                    status = "Unklar"
            else:
                status = "Noch nicht gefunden"
            ergebnis.append(
                {
                    "id": kennung,
                    "bereich": bereich,
                    "bezeichnung": bezeichnung,
                    "status": status,
                    "dokumente": [dokument.get("dateiname", "") for dokument in passend],
                }
            )
    return ergebnis
