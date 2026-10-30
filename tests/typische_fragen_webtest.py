"""Prüft 20 typische Fragen gegen die laufende lokale Web-Oberfläche.

Der Test verwendet ausschließlich allgemeine Beispiel-Fragen, keine persönlichen
Daten. Er prüft Antwort, Quelle und zentrale Aussagen; auffällige Ergebnisse
werden als Prüfpunkt ausgegeben und nicht stillschweigend als richtig bewertet.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from urllib.error import URLError
from urllib.request import Request, urlopen


FAELLE = [
    ("Pendeln", "Ab wie vielen Kilometern bekomme ich Pendlerpauschale?", ("ersten 20 vollen kilometer", "0,38"), ("vier kilometer",)),
    ("Heizkosten", "Kann ich Heizkosten steuerlich absetzen?", ("reine heizkosten", "arbeitskosten"), ("werbungskosten",)),
    ("Versicherungen", "Welche Versicherungsbeiträge sind als Vorsorgeaufwendungen relevant?", ("rentenversicherung", "kranken"), ()),
    ("Versicherungen", "Sind Beiträge zur Kranken- und Pflegeversicherung steuerlich relevant?", ("kranken", "pflege"), ()),
    ("Versicherungen", "Sind Beiträge zur gesetzlichen Rentenversicherung steuerlich relevant?", ("rentenversicherung",), ()),
    ("Versicherungen", "Können Beiträge zu einer privaten Krankenversicherung berücksichtigt werden?", ("privaten kranken", "basisabsicherung"), ()),
    ("Vermietung", "Zu welchen Einkünften gehört die Vermietung einer Wohnung?", ("vermietung und verpachtung",), ()),
    ("Vermietung", "Was passiert steuerlich, wenn ich meine Wohnung deutlich unter der ortsüblichen Miete vermiete?", ("ortsüblichen", "anteilig"), ()),
    ("Vermietung", "Kann ich die Abschreibung einer vermieteten Wohnung steuerlich berücksichtigen?", ("abschreibung",), ()),
    ("Vermietung", "Kann ich Zinsen für ein Darlehen einer vermieteten Wohnung absetzen?", ("zinsen",), ()),
    ("Vermietung", "Welche Kosten können bei einer vermieteten Wohnung als Werbungskosten relevant sein?", ("werbungskosten",), ()),
    ("Grundsteuer", "Kann ich die Grundsteuer bei einer vermieteten Wohnung auf den Mieter umlegen?", ("mieter", "mietvertrag"), ()),
    ("Grundsteuer", "Wie wird die neue Grundsteuer berechnet?", ("grundsteuerwert", "hebesatz"), ()),
    ("Grundsteuer", "Wann darf ich Betriebskosten auf meinen Mieter umlegen?", ("mietvertrag",), ()),
    ("Grundsteuer", "Gehören Heizkosten zu den Betriebskosten?", ("betriebskosten", "heiz"), ()),
    ("Erbschaftsteuer", "Wie hoch ist die Erbschaftsteuer bei 25.000 Euro?", ("750", "1.500"), ()),
    ("Erbschaftsteuer", "Wie hoch ist die Erbschaftsteuer bei 25.000 Euro von meinem Großvater?", ("keine erbschaftsteuer", "200.000"), ()),
    ("Erbschaftsteuer", "Wie hoch ist die Erbschaftsteuer bei 25.000 Euro für Geschwister?", ("750",), ()),
    ("Kirchensteuer", "Was bewirkt ein Sperrvermerk bei der Kirchensteuer?", ("sperrvermerk",), ()),
    ("Kirchensteuer", "Kann ich mit einem Sperrvermerk die Kirchensteuer vollständig vermeiden?", ("nicht",), ()),
]


def normalisiere(text: str) -> str:
    return "".join(
        zeichen
        for zeichen in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(zeichen)
    )


def frage_stellen(frage: str) -> dict:
    anfrage = Request(
        "http://127.0.0.1:8765/api/frage",
        data=json.dumps({"frage": frage}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(anfrage, timeout=90) as antwort:
        return json.load(antwort)


def main() -> int:
    auffaellig = []
    for bereich, frage, muss_enthalten, darf_nicht_enthalten in FAELLE:
        try:
            daten = frage_stellen(frage)
        except URLError as fehler:
            print(f"NICHT GETESTET: Oberfläche nicht erreichbar ({fehler.reason})")
            return 2

        antwort = normalisiere(daten.get("antwort", ""))
        fehlende_woerter = [wort for wort in muss_enthalten if normalisiere(wort) not in antwort]
        verbotene_woerter = [wort for wort in darf_nicht_enthalten if normalisiere(wort) in antwort]
        hat_quelle = bool(daten.get("quellen"))
        if fehlende_woerter or verbotene_woerter or not hat_quelle:
            auffaellig.append((bereich, frage))
            print(f"PRÜFPUNKT [{bereich}]: {frage}")
            print(f"  Fehlend: {', '.join(fehlende_woerter) or 'nichts'}")
            print(f"  Unerwünscht: {', '.join(verbotene_woerter) or 'nichts'}")
            print(f"  Quelle vorhanden: {'ja' if hat_quelle else 'nein'}")
        else:
            print(f"OK [{bereich}]: {frage}")

    if auffaellig:
        print(f"\n{len(auffaellig)} von {len(FAELLE)} Fragen sind als Prüfpunkte markiert.")
        return 1
    print(f"\nAlle {len(FAELLE)} typischen Fragen wurden erfolgreich geprüft.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
