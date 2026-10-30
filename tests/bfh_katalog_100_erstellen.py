"""Erzeugt einen stabilen 100-Fälle-Katalog für den BFH-Testmodus."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "app"))
import rag_assistent


ZIEL = Path(__file__).with_name("bfh_pilot_katalog_100.json")

POSITIVE_BASIS = (
    ("IX R 9/21", (
        "Sind Zahlungen für die Löschung eines Wohnungsrechts zwecks anschließender Vermietung sofort als Werbungskosten abziehbar?",
        "Ein Vermieter bezahlt den Wohnungsberechtigten für Löschung und Räumung. Sind das vorab entstandene Werbungskosten?",
        "Wie behandelt der BFH ein Entgelt für den Verzicht auf ein Wohnungsrecht, damit das Gebäude vermietet werden kann?",
        "Führt die Ablösung eines dinglichen Wohnungsrechts vor Vermietungsbeginn zu sofort abziehbaren Werbungskosten?",
    )),
    ("II R 35/21", (
        "Bindet ein gesonderter Grundbesitzwert auch bei der Zusammenrechnung früherer Erwerbe für die Schenkungsteuer?",
        "Welche Bindungswirkung hat eine Wertfeststellung, wenn Schenkungen innerhalb mehrerer Erwerbe zusammengerechnet werden?",
        "Muss der festgestellte Grundbesitzwert in allen Schenkungsteuerbescheiden mit früherem Erwerb übernommen werden?",
        "Gilt ein Wertfeststellungsbescheid auch für die Zusammenrechnung eines früheren Erwerbs?",
    )),
    ("III R 10/22", (
        "Unterbricht ein Freiwilligendienst zwischen Ausbildungsabschnitten die einheitliche Ausbildung beim Kindergeld?",
        "Genügt für Kindergeld der zeitliche Zusammenhang zwischen Freiwilligendienst und nächstem Ausbildungsabschnitt?",
        "Wann bleiben Ausbildungsabschnitte trotz dazwischenliegendem Freiwilligendienst eine erstmalige Ausbildung?",
        "Wie beurteilt der BFH einen Freiwilligendienst zwischen zwei Ausbildungsabschnitten beim Kindergeld?",
    )),
    ("XI R 8/21", (
        "Ist bei Lieferung von Mieterstrom aus einer Photovoltaikanlage der Vorsteuerabzug möglich?",
        "Kann ein Vermieter für eine Anlage zur Lieferung von Mieterstrom Vorsteuer abziehen?",
        "Wie behandelt der BFH den Vorsteuerabzug bei umsatzsteuerpflichtigem Mieterstrom?",
        "Besteht Vorsteuerabzug, wenn Strom getrennt von der Wohnraumvermietung an Mieter geliefert wird?",
        "Ist die Lieferung von Mieterstrom eine eigene Leistung mit Vorsteuerabzug?",
    )),
    ("IX R 29/21", (
        "Sind Mieterabfindungen sofort als Werbungskosten aus Vermietung abziehbar?",
        "Gehört eine Abfindung an Mieter zu anschaffungsnahen Kosten oder zu sofortigen Werbungskosten?",
        "Wie wird eine Mieterabfindung bei Einkünften aus Vermietung behandelt?",
    )),
    ("II R 31/21", (
        "Sind Bestattungskosten trotz Auszahlung einer Sterbegeldversicherung Nachlassverbindlichkeiten bei der Erbschaft?",
        "Wie beeinflusst eine Sterbegeldversicherung den Abzug von Bestattungskosten als Nachlassverbindlichkeiten?",
        "Dürfen Erben Bestattungskosten abziehen, wenn Sterbegeld gezahlt wurde?",
    )),
    ("II R 20/22", (
        "Wie bemisst sich die Schenkungsteuer bei einem niedrig verzinsten Darlehen?",
        "Ist der Zinsvorteil aus einem niedrig verzinsten Darlehen eine Schenkung?",
        "Welche freigebige Zuwendung entsteht durch ein Darlehen mit zu niedrigem Zins?",
    )),
    ("II R 11/21", (
        "Wann gilt eine gemischt-freigebige Grundstücksschenkung als ausgeführt?",
        "Welcher Zeitpunkt zählt bei einer gemischt freigebigen Schenkung eines Grundstücks?",
        "Wann entsteht die Schenkungsteuer bei gemischt-freigebiger Grundstücksübertragung?",
    )),
    ("II R 13/22", (
        "Welcher Erbschaft-Freibetrag gilt für das Kind eines zivilrechtlich als verstorben geltenden Elternteils?",
        "Wie behandelt der BFH den Freibetrag, wenn ein Elternteil als verstorben gilt?",
        "Erhält das Kind eines als verstorben geltenden Elternteils den höheren Freibetrag bei der Erbschaft?",
    )),
    ("II R 43/22", (
        "Sind Kosten der Auseinandersetzung einer Erbengemeinschaft Nachlassverbindlichkeiten?",
        "Können Erben Aufwendungen für die Erbengemeinschaft als Nachlassverbindlichkeiten abziehen?",
        "Wie werden Auseinandersetzungskosten einer Erbengemeinschaft bei der Erbschaft behandelt?",
    )),
    ("III R 11/21", (
        "Besteht Kindergeld für ein in Australien studierendes Kind?",
        "Welche Wohnsitzfragen gelten beim Kindergeld für ein Studium in Australien?",
        "Kann für ein volljähriges Kind während des Studiums in Australien Kindergeld gezahlt werden?",
    )),
    ("III R 2/23", (
        "Wie werden behinderungsbedingte Fahrtaufwendungen eines Kindes beim Kindergeld ermittelt?",
        "Welche Fahrtaufwendungen zählen beim Kindergeld für ein behindertes Kind?",
        "Sind behinderungsbedingte Fahrten eines Kindes für den Kindergeldanspruch relevant?",
    )),
    ("IX R 14/23", (
        "Kann ein Gutachten nach der ImmoWertV eine kürzere Restnutzungsdauer für die Abschreibung belegen?",
        "Genügt die modellhafte Restnutzungsdauer nach ImmoWertV für eine höhere Gebäudeabschreibung?",
        "Welche Anforderungen stellt der BFH an ein Gutachten zur Restnutzungsdauer nach ImmoWertV?",
    )),
    ("V R 15/21", (
        "Besteht bei einer vermieteten Wohnung Vorsteuerabzug aus einer neuen Heizungsanlage?",
        "Ist die Heizungsanlage eine eigene Leistung für den Vorsteuerabzug trotz Wohnraumvermietung?",
        "Kann der Vermieter Vorsteuer aus Kosten einer Heizungsanlage geltend machen?",
    )),
    ("II R 40/21", (
        "Ist ein Forderungsverzicht zwischen GmbH-Gesellschaftern eine freigebige Schenkung?",
        "Kann der Verzicht eines Gesellschafters den Wert anderer Anteile erhöhen und Schenkungsteuer auslösen?",
        "Wann gilt ein Forderungsverzicht unter Gesellschaftern als freigebige Zuwendung?",
    )),
)


def lade_negative_kandidaten() -> list[dict]:
    kandidaten = []
    gesehen = set()
    for pfad in sorted((PROJECT_ROOT / "tests").glob("*.json")):
        if pfad.name.startswith("bfh_pilot_katalog"):
            continue
        try:
            daten = json.loads(pfad.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(daten, list):
            continue
        for eintrag in daten:
            frage = str(eintrag.get("frage", "")).strip()
            if not 30 <= len(frage) <= 450:
                continue
            norm = rag_assistent.normalisiere(frage)
            if norm in gesehen:
                continue
            thema = rag_assistent.bestimme_bfh_thema(frage)
            if not thema:
                continue
            spezifisch = any(
                signal in norm
                for signal in rag_assistent.BFH_FALLBEGRIFFE
                if signal not in rag_assistent.BFH_ALLGEMEINE_SIGNALE
            )
            if spezifisch:
                continue
            gesehen.add(norm)
            kandidaten.append({
                "frage": frage,
                "thema": thema,
                "quelle_datei": pfad.name,
                "quelle_id": eintrag.get("id"),
            })
    return kandidaten


def main() -> None:
    positive = []
    for aktenzeichen, fragen in POSITIVE_BASIS:
        for frage in fragen:
            positive.append({
                "erwartet": "treffer",
                "aktenzeichen": aktenzeichen,
                "frage": frage,
                "herkunft": "gepruefte_fallparaphrase",
            })
    if len(positive) != 50:
        raise RuntimeError(f"Erwartet wurden 50 positive Fälle, gefunden: {len(positive)}")

    gruppen = defaultdict(list)
    for kandidat in lade_negative_kandidaten():
        gruppen[kandidat["thema"]].append(kandidat)
    negative = []
    themen = sorted(gruppen)
    while len(negative) < 50 and any(gruppen.values()):
        for thema in themen:
            if gruppen[thema] and len(negative) < 50:
                kandidat = gruppen[thema].pop(0)
                negative.append({
                    "erwartet": "kein_treffer",
                    "frage": kandidat["frage"],
                    "herkunft": "vorhandener_fragenkatalog",
                    "quelle_datei": kandidat["quelle_datei"],
                    "quelle_id": kandidat["quelle_id"],
                })
    if len(negative) != 50:
        raise RuntimeError(f"Erwartet wurden 50 negative Fälle, gefunden: {len(negative)}")

    faelle = []
    for nummer, fall in enumerate([*positive, *negative], start=1):
        faelle.append({"id": nummer, **fall})
    ZIEL.write_text(json.dumps(faelle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "gesamt": len(faelle),
        "positive": len(positive),
        "negative_aus_bestehenden_katalogen": len(negative),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
