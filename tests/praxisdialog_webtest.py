"""Praxistest der laufenden Web-App mit Nutzerprofil und Gesprächsverlauf.

Der Test arbeitet ausschließlich lesend mit allgemeinen Beispielfragen. Er
wählt ein vorhandenes Nutzerprofil, führt mehrere kurze Dialoge und schreibt
einen nachvollziehbaren Bericht. Freie Modellantworten werden über robuste
Kernaussagen statt über einen exakten Wortlaut bewertet.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from datetime import datetime
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener


STANDARD_BASIS_URL = "http://127.0.0.1:8765"
STANDARD_NUTZER = "Alex Beispiel"
ERGEBNISORDNER = Path(__file__).resolve().parent / "ergebnisse"


SZENARIEN = [
    {
        "name": "Arbeitnehmer und Steuerklasse",
        "nachrichten": [
            {
                "frage": "Ich hab hier meine Lohnsteuerbescheinigung. Wo sehe ich, welche Steuerklasse da drin steht?",
                "muss": [("steuerklasse",), ("lohnsteuerbescheinigung", "bescheinigung")],
            },
            {
                "frage": "Und warum soll ich das für 2023 überhaupt prüfen?",
                "muss": [("steuerklasse",), ("lohnsteuer", "abzug", "erstattung")],
            },
        ],
    },
    {
        "name": "Homeoffice und Arbeitsweg 2023",
        "nachrichten": [
            {
                "frage": "Ich war 2023 an 80 Tagen daheim am Arbeiten. Bringt mir das steuerlich was?",
                "muss": [("homeoffice", "tagespauschale"), ("6 euro", "6 €"), ("480 euro", "480 €")],
            },
            {
                "frage": "An den anderen Tagen bin ich immer 15 Kilometer einfach zur Arbeit gefahren.",
                "muss": [
                    ("entfernungspauschale", "pendlerpauschale"),
                    ("15 kilometer", "15 km"),
                    ("nicht 7,5 kilometer", "nicht 7,5 km", "nicht halbiert"),
                ],
                "darf_nicht": ("halbe entfernungspauschale", "nur hin oder ruck"),
            },
            {
                "frage": "Das waren 120 Tage.",
                "muss": [
                    ("entfernungspauschale",),
                    ("120",),
                    ("15 kilometer", "15 km"),
                    ("540 euro", "540 €"),
                ],
            },
        ],
    },
    {
        "name": "Gemischt genutztes Dreifamilienhaus",
        "nachrichten": [
            {
                "frage": "Bei meinem Dreifamilienhaus wohne ich in einer Wohnung selbst und vermiete einen Teil. Wie behandle ich die Grundsteuer?",
                "muss": [("vermiet",), ("selbst", "eigene wohnung"), ("aufteil", "anteil")],
            },
            {
                "frage": "Und was ist mit den Müllgebühren?",
                "muss": [("müll", "abfall"), ("betriebskosten", "nebenkosten"), ("mieter", "vermiet")],
            },
        ],
    },
    {
        "name": "Rohrbruch und Versicherung in Umgangssprache",
        "nachrichten": [
            {
                "frage": "Die Versicherung hat den Rohrbruch bezahlt, nur 500 Euro musste ich für meine eigene Wohnung selber übernehmen. Bringt mir das bei der Steuer was?",
                "muss": [("versicherung", "erstattung"), ("500 euro", "500 €", "selbst"), ("arbeitskosten", "arbeits-", "lohnkosten", "handwerker")],
                "darf_nicht": ("hat die gebaudeversicherung",),
            }
        ],
    },
    {
        "name": "Bayern-Grundsteuer Garage und Schuppen",
        "nachrichten": [
            {
                "frage": "Muss ich meine normale Garage am Haus bei der Grundsteuer extra erklären?",
                "muss": [("wirtschaftliche einheit", "zum haus"), ("50 m²", "50 quadratmeter")],
            },
            {
                "frage": "Und was ist mit meinem kleinen Schuppen direkt daneben?",
                "muss": [("schuppen", "nebengebäude"), ("30 m²", "30 quadratmeter")],
                "darf_nicht": ("40 kubikmeter",),
            },
        ],
    },
    {
        "name": "Grundsteuer-Einspruch und Zahlung",
        "nachrichten": [
            {
                "frage": "Wie lange kann ich gegen meinen Grundsteuerwertbescheid Einspruch einlegen?",
                "muss": [("einen monat", "1 monat"), ("bekanntgabe",)],
            },
            {
                "frage": "Muss ich die Grundsteuer in der Zeit trotzdem erst mal bezahlen?",
                "muss": [("zahlen", "zahlung"), ("aussetzung der vollziehung",)],
            },
        ],
    },
    {
        "name": "Plattformmeldung ist nicht Steuerpflicht",
        "nachrichten": [
            {
                "frage": "Ab wann meldet Kleinanzeigen meine Verkäufe eigentlich ans Finanzamt?",
                "muss": [("30",), ("2.000 euro", "2000 euro"), ("plattform", "meldung")],
            },
            {
                "frage": "Heißt das, dass ich bei 30 Verkäufen automatisch Steuern zahlen muss?",
                "muss": [("nein", "nicht automatisch"), ("keine steuerfreigrenze", "nicht die steuerpflicht", "steuer getrennt")],
            },
        ],
    },
    {
        "name": "Schenkung von der Mutter und Meldepflicht",
        "nachrichten": [
            {
                "frage": "Meine Mutter hat mir 20.000 Euro überwiesen und gesagt, das ist ein Geschenk. Ist das Einkommen?",
                "muss": [("keine einkommensteuer", "nicht einkommensteuer", "kein einkommensteuerpflichtiges", "keine einkünfte"), ("400.000 euro", "400000 euro")],
            },
            {
                "frage": "Muss ich das trotzdem irgendwo melden?",
                "muss": [("schenkungsteuerfinanzamt", "schenkungsteuer-finanzamt"), ("drei monaten", "3 monaten")],
            },
        ],
    },
    {
        "name": "Minijob und Steuererklärung",
        "nachrichten": [
            {
                "frage": "Ich hatte 2023 neben meinem normalen Job noch einen Minijob mit 520 Euro im Monat.",
                "muss": [("520 euro", "520 €"), ("pauschal", "individuell")],
            },
            {
                "frage": "Muss das in meine Steuererklärung rein?",
                "muss": [("pauschal",), ("nicht",), ("individuell", "lohnsteuermerkmale")],
            },
        ],
    },
    {
        "name": "Heirat am Jahresende",
        "nachrichten": [
            {
                "frage": "Wir haben erst im Dezember 2023 geheiratet. Bringt uns das steuerlich noch etwas?",
                "muss": [("zusammenveranlagung", "splitting"), ("unterschiedlich", "vergleich")],
            },
            {
                "frage": "Zählt das wirklich für das ganze Jahr?",
                "muss": [("ganze jahr", "gesamte jahr", "gesamte steuerjahr"), ("nicht dauernd getrennt", "voraussetzungen")],
            },
        ],
    },
    {
        "name": "Grundsteuerwertbescheid und Zahlungsbescheid",
        "nachrichten": [
            {
                "frage": "Ist der Grundsteuerwertbescheid schon die Rechnung, die ich bezahlen muss?",
                "muss": [("nein",), ("grundlagen", "grundsteuermess"), ("gemeinde", "stadt")],
            },
            {
                "frage": "Und wer schickt mir dann den eigentlichen Zahlungsbescheid?",
                "muss": [("gemeinde", "stadt erlangen", "erlangen"), ("grundsteuerbescheid",)],
            },
        ],
    },
    {
        "name": "Grundsteuerumlage bei Leerstand",
        "nachrichten": [
            {
                "frage": "Ich vermiete zwei Wohnungen im Haus. Darf ich die Grundsteuer über die Nebenkosten abrechnen?",
                "muss": [("mietvertrag",), ("umlage", "betriebskosten"), ("verteilerschlüssel", "anteil")],
            },
            {
                "frage": "Eine davon stand aber ein halbes Jahr leer. Zahlen die anderen Mieter den Anteil mit?",
                "muss": [("nein", "nicht"), ("leerstand",), ("vermieter", "selbst")],
            },
        ],
    },
    {
        "name": "Arbeitslaptop mit privater Nutzung",
        "nachrichten": [
            {
                "frage": "Ich habe 2023 einen Laptop für 1.200 Euro gekauft und nutze ihn ungefähr zu 60 Prozent für die Arbeit.",
                "muss": [("60 prozent", "60 %"), ("720 euro", "720 €"), ("arbeitsmittel", "beruflich")],
            },
            {
                "frage": "Kann ich die 720 Euro dann sofort komplett ansetzen?",
                "muss": [("computer", "laptop", "hardware"), ("anschaffungsjahr", "sofort", "vollständig")],
            },
        ],
    },
    {
        "name": "Kinderbetreuung und Barzahlung",
        "nachrichten": [
            {
                "frage": "Die Kita hat mich 2023 insgesamt 3.000 Euro gekostet. Wie viel davon kann ich angeben?",
                "muss": [("zwei drittel", "2/3"), ("2.000 euro", "2000 euro"), ("unbar", "überweisung")],
            },
            {
                "frage": "Und 600 Euro für den Babysitter habe ich bar bezahlt. Geht das auch?",
                "muss": [("nein", "nicht"), ("unbar", "überweisung"), ("bar",)],
            },
        ],
    },
    {
        "name": "Hausverkauf und Grundsteuer im Kaufjahr",
        "nachrichten": [
            {
                "frage": "Ich habe ein Haus im Juli verkauft. Wer schuldet der Gemeinde die Grundsteuer für dieses Jahr?",
                "muss": [("1. januar", "jahresbeginn"), ("verkaufer", "verkäufer", "bisherige eigentümer")],
            },
            {
                "frage": "Der Käufer hat mir laut Notarvertrag die Hälfte erstattet. Ändert das etwas gegenüber der Stadt?",
                "muss": [("nein", "nicht"), ("innenverhältnis", "notarvertrag", "vertraglich"), ("gemeinde", "stadt")],
            },
        ],
    },
    {
        "name": "Viele private Vinted-Verkäufe",
        "nachrichten": [
            {
                "frage": "Ich habe auf Vinted 35 alte eigene Kleidungsstücke für zusammen 1.500 Euro verkauft. Meldet die Plattform das?",
                "muss": [("30",), ("meldung", "meldet"), ("keine steuer", "nicht automatisch", "steuerpflicht getrennt")],
            },
            {
                "frage": "Ich habe alles billiger verkauft als damals gekauft. Muss ich darauf Einkommensteuer zahlen?",
                "muss": [("nein", "normalerweise nicht"), ("gebraucht", "alltagskleidung", "gegenstände des täglichen gebrauchs"), ("kein gewinn", "verlust")],
            },
        ],
    },
    {
        "name": "Flächenfehler im Grundsteuerbescheid",
        "nachrichten": [
            {
                "frage": "Im Grundsteuerbescheid stehen 180 Quadratmeter Wohnfläche, richtig wären aber nur 120. Was mache ich?",
                "muss": [("einspruch",), ("einen monat", "monatsfrist"), ("120",), ("nachweis", "wohnflächenberechnung")],
            },
            {
                "frage": "Und wenn ich den Fehler erst zwei Monate nach dem Bescheid bemerkt habe?",
                "muss": [("frist", "bestandskraft"), ("anderung", "änderung", "korrektur"), ("nicht automatisch", "prüfen", "finanzamt")],
            },
        ],
    },
]


def normalisiere(text: str) -> str:
    text = "".join(
        zeichen
        for zeichen in unicodedata.normalize("NFKD", str(text).lower())
        if not unicodedata.combining(zeichen)
    )
    return " ".join(text.replace("\u00a0", " ").split())


class Sitzung:
    def __init__(self, basis_url: str) -> None:
        self.basis_url = basis_url.rstrip("/")
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def anfrage(self, pfad: str, payload: dict | None = None) -> dict:
        daten = None
        methode = "GET"
        header = {}
        if payload is not None:
            daten = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            methode = "POST"
            header["Content-Type"] = "application/json; charset=utf-8"
        anfrage = Request(self.basis_url + pfad, data=daten, headers=header, method=methode)
        with self.opener.open(anfrage, timeout=240) as antwort:
            return json.load(antwort)

    def nutzer_waehlen(self, name: str) -> dict:
        daten = self.anfrage("/api/nutzer")
        gesucht = normalisiere(name)
        nutzer = next(
            (eintrag for eintrag in daten.get("nutzer", []) if normalisiere(eintrag.get("name", "")) == gesucht),
            None,
        )
        if not nutzer:
            raise ValueError(f"Nutzerprofil nicht gefunden: {name}")
        return self.anfrage("/api/nutzer/wechseln", {"nutzer_id": nutzer["id"]})["nutzer"]

    def frage(self, text: str, verlauf: list[dict], steuerjahr: str) -> dict:
        return self.anfrage(
            "/api/frage",
            {"frage": text, "verlauf": verlauf, "steuerjahr": steuerjahr},
        )


def bewerte(
    antwort: str,
    quellen: list[dict],
    gruppen: list[tuple[str, ...]],
    darf_nicht: tuple[str, ...] = (),
) -> tuple[str, list[str]]:
    norm = normalisiere(antwort)
    fehlend = [" / ".join(gruppe) for gruppe in gruppen if not any(normalisiere(wort) in norm for wort in gruppe)]
    gruende: list[str] = []
    if not antwort.strip():
        gruende.append("Antwort ist leer")
    if fehlend:
        gruende.append("Kernaussagen fehlen: " + ", ".join(fehlend))
    unerwuenscht = [wort for wort in darf_nicht if normalisiere(wort) in norm]
    if unerwuenscht:
        gruende.append("Sachlich unerwünschte Aussage: " + ", ".join(unerwuenscht))
    if not quellen:
        gruende.append("Keine Quelle vorhanden")
    if "steuerjahr 2026" in norm or "fur 2026" in norm:
        gruende.append("Antwort wechselt trotz Auswahl auf das Steuerjahr 2026")
    return ("BESTANDEN" if not gruende else "PRUEFEN"), gruende


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--basis-url", default=STANDARD_BASIS_URL)
    parser.add_argument("--nutzer", default=STANDARD_NUTZER)
    parser.add_argument("--steuerjahr", default="2023")
    parser.add_argument("--ausgabe", type=Path)
    args = parser.parse_args()

    sitzung = Sitzung(args.basis_url)
    try:
        status = sitzung.anfrage("/api/status")
        if not status.get("bereit"):
            raise RuntimeError("Server meldet sich nicht als bereit.")
        nutzer = sitzung.nutzer_waehlen(args.nutzer)
    except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as fehler:
        print(f"NICHT GETESTET: {fehler}")
        return 2

    ergebnisse: list[dict] = []
    print(f"Nutzer: {nutzer['name']} | Steuerjahr: {args.steuerjahr}", flush=True)
    for szenario in SZENARIEN:
        verlauf: list[dict] = []
        for nummer, schritt in enumerate(szenario["nachrichten"], 1):
            try:
                daten = sitzung.frage(schritt["frage"], verlauf, args.steuerjahr)
                antwort = str(daten.get("antwort", ""))
                quellen = daten.get("quellen", [])
                status, gruende = bewerte(
                    antwort,
                    quellen,
                    schritt["muss"],
                    schritt.get("darf_nicht", ()),
                )
            except (HTTPError, URLError, TimeoutError, ValueError, OSError) as fehler:
                antwort, quellen = "", []
                status, gruende = "TECHNISCHER_FEHLER", [str(fehler)]

            eintrag = {
                "szenario": szenario["name"],
                "schritt": nummer,
                "frage": schritt["frage"],
                "status": status,
                "gruende": gruende,
                "antwort": antwort,
                "quellen": quellen,
            }
            ergebnisse.append(eintrag)
            print(f"{status} [{szenario['name']} {nummer}/{len(szenario['nachrichten'])}]", flush=True)
            if gruende:
                print("  " + "; ".join(gruende), flush=True)
            verlauf.extend(
                [
                    {"rolle": "nutzer", "text": schritt["frage"]},
                    {"rolle": "assistent", "text": antwort},
                ]
            )

    payload = {
        "erstellt_am": datetime.now().astimezone().isoformat(timespec="seconds"),
        "nutzer": nutzer["name"],
        "steuerjahr": args.steuerjahr,
        "anzahl": len(ergebnisse),
        "bestanden": sum(e["status"] == "BESTANDEN" for e in ergebnisse),
        "ergebnisse": ergebnisse,
    }
    zeit = datetime.now().strftime("%Y%m%d_%H%M%S")
    ausgabe = args.ausgabe or ERGEBNISORDNER / f"praxisdialog_webtest_{zeit}.json"
    ausgabe.parent.mkdir(parents=True, exist_ok=True)
    ausgabe.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"ERGEBNIS {ausgabe}")
    print(f"ZUSAMMENFASSUNG {payload['bestanden']}/{payload['anzahl']} bestanden")
    return 0 if payload["bestanden"] == payload["anzahl"] else 1


if __name__ == "__main__":
    sys.exit(main())
