"""Prüft einen erweiterten Katalog typischer Steuerfragen über die Web-Oberfläche."""

from __future__ import annotations

import json
import unicodedata
from urllib.error import URLError
from urllib.request import Request, urlopen


FRAAGEN = [
    "Wie setzen Studierende oder Azubis ihre Ausbildungskosten ab?",
    "Was ist die Entfernungspauschale und wie berechnet man sie?",
    "Kann ich Umzugskosten aus beruflichen Gründen von der Steuer absetzen?",
    "Wie funktioniert die Homeoffice-Pauschale bei mehreren Arbeitsplätzen?",
    "Was passiert mit Abfindungen oder dem Bezug von Arbeitslosengeld?",
    "Wie setzen Vermieter Renovierungskosten oder Abschreibungen ab?",
    "Welche Freibeträge gelten für Kinder und das Kindergeld?",
    "Können Alleinerziehende einen Entlastungsbetrag beantragen?",
    "Was sind außergewöhnliche Belastungen bei Krankheits- oder Pflegekosten?",
    "Wie wirken sich Handwerkerleistungen in der selbstgenutzten Wohnung aus?",
    "Wie hoch ist der Steueranteil für Rentner und Pensionäre?",
    "Wo trägt man Beiträge zur Kranken-, Pflege- und Rentenversicherung ein?",
    "Was ist der Sparerpauschbetrag bei Kapitaleinkünften aus Aktien?",
    "Wie funktioniert die Verlustverrechnung bei Wertpapieren?",
    "Müssen Gewinne aus Kryptowährungen oder Privatverkäufen versteuert werden?",
    "Was bedeutet die vorausgefüllte Steuererklärung (Belegabruf)?",
    "Welche Steuerklasse ist für Ehepaare am günstigsten?",
    "Wann lohnt sich die Zusammenveranlagung gegenüber der Einzelveranlagung?",
    "Wie legt man Einspruch gegen einen fehlerhaften Steuerbescheid ein?",
    "Ab welcher Summe verlangt das Finanzamt noch Papiernachweise?",
]


def frage_stellen(frage: str) -> dict:
    anfrage = Request(
        "http://127.0.0.1:8765/api/frage",
        data=json.dumps({"frage": frage}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(anfrage, timeout=120) as antwort:
        return json.load(antwort)


def hat_fremdschrift(text: str) -> bool:
    return any("CJK" in unicodedata.name(zeichen, "") for zeichen in text)


def main() -> int:
    ergebnisse = []
    for nummer, frage in enumerate(FRAAGEN, start=1):
        try:
            daten = frage_stellen(frage)
            antwort = daten.get("antwort", "")
            if not antwort:
                status = "LEER"
            elif "Das kann ich anhand der vorhandenen Informationen nicht sicher beantworten" in antwort:
                status = "WISSEN_FEHLT"
            elif not daten.get("quellen"):
                status = "OHNE_QUELLE"
            elif hat_fremdschrift(antwort):
                status = "SPRACHFEHLER"
            else:
                status = "ANTWORT_VORHANDEN"
            ergebnis = {"nummer": nummer, "frage": frage, "status": status, "quellen": len(daten.get("quellen", [])), "antwort": antwort}
        except (URLError, TimeoutError, ValueError) as fehler:
            ergebnis = {"nummer": nummer, "frage": frage, "status": "TECHNISCHER_FEHLER", "fehler": str(fehler)}
        ergebnisse.append(ergebnis)
        print(json.dumps(ergebnis, ensure_ascii=False), flush=True)

    print("ZUSAMMENFASSUNG", json.dumps({
        status: sum(ergebnis["status"] == status for ergebnis in ergebnisse)
        for status in sorted({ergebnis["status"] for ergebnis in ergebnisse})
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
