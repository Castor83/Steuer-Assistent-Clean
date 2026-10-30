"""Erzeugt 300 neue, redaktionell geprüfte Mehrschritt-Dialoge.

Die Dialoge trainieren ausschließlich das Verstehen und Vereinheitlichen der
aktuellen Folgeäußerung. Sie beantworten keine Steuerfrage. Alle Varianten
eines Grundfalls bleiben im selben Split, damit keine Varianten durchsickern.
"""

from __future__ import annotations

import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZIEL = ROOT / "testDaten" / "umgangssprache_steuer_training" / "mehrschritt_300"
SYSTEM = (
    "Du vereinheitlichst die letzte umgangssprachliche Nachricht eines deutschen Steuerdialogs. "
    "Nutze den Verlauf, löse Pronomen und verkürzte Bezüge auf und gib nur die gemeinte Frage "
    "oder Angabe in klarem Standarddeutsch aus. Bewahre Gegenstand, Person, Betrag, Jahr, Ort, "
    "Nutzungsart und Behörde. Unterscheide Meldung, Anzeige und Steuerpflicht. Beantworte die "
    "Steuerfrage nicht und erfinde keine Angaben."
)


# id, Nutzerkontext, Assistentenkontext, Folgeäußerung, eindeutiges Ziel,
# maschinell prüfbare Detailgruppen
FAELLE = (
    ("laptop-720-sofort", "Mein 2023 gekaufter Laptop kostete 1.200 Euro und wird zu 60 Prozent beruflich genutzt.", "Der berufliche Anteil beträgt 720 Euro.", "Kann ich die dann direkt ganz nehmen?", "Kann ich den beruflichen Anteil von 720 Euro für den 2023 gekauften Laptop im Anschaffungsjahr vollständig als Arbeitsmittel ansetzen?", (("laptop",), ("720 euro",), ("2023",), ("anschaffungsjahr",), ("arbeitsmittel",))),
    ("lstb-steuerklasse-2024", "Ich prüfe gerade meine Lohnsteuerbescheinigung 2024.", "Die persönlichen Lohnsteuermerkmale stehen im Kopfbereich.", "Wo genau steht da meine Klasse?", "Wo steht meine Steuerklasse auf der Lohnsteuerbescheinigung 2024?", (("steuerklasse",), ("lohnsteuerbescheinigung",), ("2024",))),
    ("lstb-steuerklasse-2025", "Die Dokumentenprüfung hat meine Lohnsteuerbescheinigung 2025 erkannt.", "Als Nächstes sollen Steuerjahr, Arbeitgeber und Steuerklasse geprüft werden.", "Und welche war bei mir eingetragen?", "Welche Steuerklasse ist auf meiner Lohnsteuerbescheinigung 2025 eingetragen?", (("steuerklasse",), ("lohnsteuerbescheinigung",), ("2025",))),
    ("arbeitsmittel-erstattung", "Ich habe 2024 einen Bürostuhl für 600 Euro gekauft.", "Berufliche Nutzung und eine Arbeitgebererstattung müssen getrennt werden.", "Der Chef hat mir davon 200 zurückgegeben.", "Mein Arbeitgeber hat mir 200 Euro der Kosten des 2024 gekauften Bürostuhls erstattet; wie ist der selbst getragene Rest als Arbeitsmittel zu behandeln?", (("arbeitgeber",), ("200 euro",), ("2024",), ("burostuhl", "bürostuhl"), ("selbst getragen",))),
    ("arbeitsweg-resttage", "Mein Arbeitsweg beträgt 18 Kilometer einfache Strecke und ich war 70 Tage im Homeoffice.", "Für die Berechnung fehlen die tatsächlichen Bürotage.", "An 110 Tagen bin ich hingefahren.", "Ich bin an 110 Arbeitstagen jeweils 18 Kilometer einfache Strecke zur ersten Tätigkeitsstätte gefahren.", (("110",), ("18 kilometer",), ("einfache strecke",), ("tatig", "tätig"), ("statte", "stätte"))),
    ("homeoffice-jahrbezug", "Für meine Steuererklärung 2024 habe ich 95 Homeoffice-Tage notiert.", "Die Tagespauschale ist jahresbezogen zu prüfen.", "Gilt das so auch für das Jahr, das wir gerade machen?", "Gilt die Homeoffice-Tagespauschale für meine 95 Homeoffice-Tage im Steuerjahr 2024?", (("homeoffice",), ("95",), ("2024",), ("tagespauschale",))),
    ("arbeitskleidung-zuschuss", "Mein Arbeitgeber verlangte 2023 bestimmte Schutzkleidung, die ich selbst gekauft habe.", "Nur der selbst getragene berufliche Aufwand ist gemeint.", "50 Euro Zuschuss gab es aber noch.", "Mein Arbeitgeber hat 50 Euro Zuschuss zu der von mir 2023 selbst gekauften vorgeschriebenen Schutzkleidung gezahlt; wie ist der verbleibende berufliche Aufwand zu behandeln?", (("50 euro",), ("arbeitgeber",), ("2023",), ("schutzkleidung",), ("verbleib", "selbst getragen"))),
    ("minijob-pauschal", "Ich hatte 2024 neben dem Hauptjob einen Minijob mit 538 Euro monatlich.", "Entscheidend ist die pauschale oder individuelle Besteuerung.", "Auf der Abrechnung steht pauschal versteuert.", "Mein Minijob mit 538 Euro monatlich wurde 2024 pauschal versteuert; muss ich ihn in der Einkommensteuererklärung angeben?", (("minijob",), ("538 euro",), ("2024",), ("pauschal",), ("einkommensteuererklarung", "einkommensteuererklärung"))),
    ("babysitter-teils-bar", "Für den Babysitter habe ich 2023 insgesamt 1.200 Euro gezahlt.", "Kinderbetreuungskosten setzen Rechnung und unbare Zahlung voraus.", "900 überwiesen und 300 bar.", "Von den 1.200 Euro Babysitterkosten 2023 habe ich 900 Euro überwiesen und 300 Euro bar bezahlt; welcher Teil kann als Kinderbetreuungskosten berücksichtigt werden?", (("1.200 euro", "1200 euro"), ("900 euro",), ("300 euro",), ("bar",), ("2023",))),
    ("spende-nachweis", "Ich habe 2025 einer gemeinnützigen Organisation 250 Euro gespendet.", "Für den Abzug ist ein geeigneter Zuwendungsnachweis wichtig.", "Der Kontoauszug ist da, sonst nix.", "Reicht für meine Spende von 250 Euro im Jahr 2025 der Kontoauszug als Nachweis, wenn ich keine weitere Bescheinigung habe?", (("250 euro",), ("2025",), ("kontoauszug",), ("spende",), ("nachweis",))),
    ("bayern-garage-separat", "Beim Haus in Erlangen gehört die Garage normalerweise zum Grundstück.", "In Bayern bleiben zugeordnete Garagenflächen unter bestimmten Voraussetzungen außer Ansatz.", "Die steht aber auf einem eigenen Flurstück.", "Wie ist die Garage auf einem eigenen Flurstück bei der bayerischen Grundsteuer für mein Haus in Erlangen einzuordnen?", (("garage",), ("eigenen flurstuck", "eigenen flurstück"), ("bayerisch",), ("erlangen",))),
    ("bayern-schuppen-38", "Neben meinem Wohnhaus in Erlangen steht ein untergeordneter Schuppen.", "Bei der bayerischen Grundsteuer ist für solche Nebengebäude die Fläche wichtig.", "Der hat 38 Quadratmeter.", "Wie wird der 38 Quadratmeter große Schuppen neben meinem Wohnhaus in Erlangen bei der bayerischen Grundsteuer berücksichtigt?", (("38",), ("schuppen",), ("wohnhaus",), ("erlangen",), ("bayerisch",))),
    ("bayern-terrasse", "Ich ermittle die Wohnfläche für die bayerische Grundsteuer meines Hauses.", "Balkon- und Terrassenflächen werden nicht immer vollständig angesetzt.", "Die Terrasse hat 20 Quadratmeter.", "Mit welchem Anteil werden die 20 Quadratmeter Terrassenfläche bei der bayerischen Grundsteuer als Wohnfläche berücksichtigt?", (("20",), ("terrasse",), ("bayerisch",), ("wohnflache", "wohnfläche"))),
    ("bayern-keller", "Für mein Dreifamilienhaus in Erlangen prüfe ich die Wohnfläche der Grundsteuer.", "Normale Keller- und Heizungsräume sind von ausgebauten Aufenthaltsräumen zu unterscheiden.", "Der eine Keller ist nur Lager.", "Zählt der nur als Lager genutzte Keller meines Dreifamilienhauses in Erlangen bei der bayerischen Grundsteuer zur Wohnfläche?", (("lager",), ("keller",), ("dreifamilienhaus",), ("erlangen",), ("wohnflache", "wohnfläche"))),
    ("grundsteuer-zahlungsfolge", "Vom Finanzamt habe ich den Grundsteuerwertbescheid und den Grundsteuermessbescheid erhalten.", "Die eigentliche Zahlungsfestsetzung kommt von der Gemeinde.", "Wer schickt mir jetzt die Rechnung fürs Haus?", "Welche Behörde schickt mir nach dem Grundsteuerwertbescheid und dem Grundsteuermessbescheid den eigentlichen Grundsteuerbescheid mit der Zahlungsaufforderung für mein Haus?", (("behorde", "behörde"), ("grundsteuerwertbescheid",), ("grundsteuermessbescheid",), ("grundsteuerbescheid",), ("zahlungsaufforderung",))),
    ("grundsteuer-nutzungsanderung", "Eine bisher vermietete Wohnung im Haus in Erlangen nutze ich jetzt selbst.", "Eine Nutzungsänderung kann für die bayerische Grundsteuer anzuzeigen sein.", "Heißt das, ich muss gleich mehr Steuer zahlen?", "Führt die Anzeige der geänderten Nutzung einer bisher vermieteten und jetzt selbst genutzten Wohnung in Erlangen automatisch zu höherer Grundsteuer?", (("anzeige",), ("vermietet",), ("selbst genutzt",), ("erlangen",), ("automatisch",))),
    ("grundsteuer-eigentumerwechsel", "Das Haus wurde auf meine Tochter übertragen.", "Der Eigentümerwechsel muss dem Finanzamt beziehungsweise über die vorgesehenen Wege bekannt werden.", "Ist diese Meldung schon die neue Steuerrechnung?", "Ist die Meldung des Eigentümerwechsels am Haus bereits der neue Grundsteuerbescheid beziehungsweise die neue Zahlungsfestsetzung?", (("meldung",), ("eigentumerwechsel", "eigentümerwechsel"), ("grundsteuerbescheid",), ("zahlungsfestsetzung",))),
    ("grundabgaben-kanal", "Der Grundabgabenbescheid für mein teilweise vermietetes Haus enthält Grundsteuer, Müll und Kanal.", "Die Positionen sind getrennt nach Nutzung und Umlage zu prüfen.", "Was davon gehört zu den Mietern?", "Welche Anteile von Grundsteuer, Müll- und Kanalgebühren des teilweise vermieteten Hauses können den Mietern als Betriebskosten zugeordnet werden?", (("grundsteuer",), ("mull", "müll"), ("kanal",), ("teilweise vermietet",), ("mieter",))),
    ("leerstand-betriebskosten", "Von den zwei vermietbaren Wohnungen stand eine vier Monate leer.", "Der Vermieter darf Leerstandskosten nicht einfach auf die übrigen Mieter verschieben.", "Auch nicht bei den Müllkosten?", "Müssen die Mieter der bewohnten Wohnung die Müllkosten der vier Monate leerstehenden Wohnung mittragen?", (("mieter",), ("mull", "müll"), ("vier monate",), ("leersteh",))),
    ("hausverkauf-innenausgleich", "Ich war am 1. Januar Eigentümer und habe das Haus im September verkauft.", "Gegenüber der Stadt bleibe ich regelmäßig für die Jahresgrundsteuer verantwortlich.", "Im Vertrag zahlt der Käufer ab Oktober, hilft mir das bei der Stadt?", "Ändert die im Kaufvertrag vereinbarte Übernahme der Grundsteuer durch den Käufer ab Oktober meine Steuerschuld gegenüber der Stadt für das Verkaufsjahr?", (("kaufvertrag",), ("kaufer", "käufer"), ("oktober",), ("stadt",), ("steuerschuld",))),
    ("kleinanzeigen-30-keingewinn", "Kleinanzeigen meldet möglicherweise meine 30 privaten Verkäufe.", "Die Plattformmeldung entscheidet nicht über eine Steuerpflicht.", "Ich hab dabei überhaupt keinen Gewinn gemacht.", "Muss ich wegen der Plattformmeldung von 30 privaten Kleinanzeigen-Verkäufen Einkommensteuer zahlen, obwohl ich keinen Gewinn erzielt habe?", (("plattformmeldung",), ("30",), ("kleinanzeigen",), ("einkommensteuer",), ("kein gewinn", "keinen gewinn"))),
    ("plattform-2000-meldung", "Ich habe auf einer Plattform 18 gebrauchte Sachen verkauft.", "Für die Plattformmeldung sind Anzahl und Gesamtvergütung getrennte Schwellenmerkmale.", "Zusammen waren das genau 2.000 Euro.", "Kann die Plattform meine 18 Verkäufe mit einer Gesamtvergütung von genau 2.000 Euro an das Finanzamt melden, und bedeutet diese Meldung automatisch Steuerpflicht?", (("18",), ("2.000 euro", "2000 euro"), ("plattform",), ("meldung",), ("steuerpflicht",))),
    ("vinted-verlust-privat", "Vinted kann meine 32 Verkäufe gebrauchter eigener Kleidung melden.", "Meldung und steuerlicher Gewinn sind getrennt zu beurteilen.", "Alles war billiger als beim Kauf.", "Muss ich für 32 über Vinted verkaufte eigene gebrauchte Kleidungsstücke Einkommensteuer zahlen, wenn alle Verkaufspreise unter den damaligen Kaufpreisen lagen?", (("32",), ("vinted",), ("gebraucht",), ("einkommensteuer",), ("unter", "billiger", "verlust"))),
    ("schenkung-mutter-anzeige", "Meine Mutter hat mir 2024 einmalig 20.000 Euro geschenkt.", "Der Freibetrag und die Anzeigepflicht sind getrennte Fragen.", "Also melden, auch wenn keine Steuer rauskommt?", "Muss ich die Schenkung meiner Mutter über 20.000 Euro aus 2024 beim Schenkungsteuerfinanzamt anzeigen, obwohl voraussichtlich keine Schenkungsteuer entsteht?", (("mutter",), ("20.000 euro", "20000 euro"), ("2024",), ("schenkungsteuerfinanzamt",), ("keine schenkungsteuer",))),
    ("schenkung-notar", "Mein Vater hat mir ein Grundstück notariell übertragen.", "Bei notariell beurkundeten Schenkungen kann die gesonderte Anzeige entfallen.", "Muss ich trotzdem selbst noch ein Schreiben hinschicken?", "Muss ich die notariell beurkundete Grundstücksschenkung meines Vaters zusätzlich selbst schriftlich beim Schenkungsteuerfinanzamt anzeigen?", (("notariell",), ("grundstucksschenkung", "grundstücksschenkung"), ("vater",), ("schriftlich",), ("schenkungsteuerfinanzamt",))),
    ("streaming-meldung-steuer", "Die Streaming-Plattform übermittelt möglicherweise meine Einnahmendaten.", "Eine Datenmeldung ersetzt nicht die steuerliche Einordnung der Tätigkeit.", "Bin ich dadurch automatisch ein Gewerbe?", "Führt die Datenmeldung meiner Streaming-Einnahmen durch die Plattform automatisch dazu, dass meine Tätigkeit als Gewerbe gilt?", (("datenmeldung",), ("streaming",), ("plattform",), ("automatisch",), ("gewerbe",))),
    ("kaution-einbehalten", "Mein Mieter ist ausgezogen; die Kaution war bislang nur verwahrt.", "Eine rückzahlbare Kaution ist zunächst keine Mieteinnahme.", "300 Euro behalte ich wegen eines Schadens.", "Wie sind die 300 Euro der Mietkaution steuerlich zu behandeln, die ich nach dem Auszug wegen eines Schadens einbehalte?", (("300 euro",), ("mietkaution", "kaution"), ("auszug",), ("schaden",), ("einbehalt",))),
    ("leerstand-badsanierung", "Eine Wohnung steht seit drei Monaten leer, soll aber nach der Renovierung wieder vermietet werden.", "Die fortbestehende Vermietungsabsicht und die Art der Baumaßnahme sind wichtig.", "Jetzt wird das ganze Bad neu gemacht.", "Wie sind die Kosten der vollständigen Badsanierung während des dreimonatigen Leerstands einer weiterhin zur Vermietung bestimmten Wohnung einzuordnen?", (("badsanierung",), ("drei monate", "dreimonatigen"), ("leerstand",), ("weiterhin",), ("vermietung",))),
    ("versicherung-material", "Nach dem Rohrbruch in meiner eigenen Wohnung hat die Gebäudeversicherung einen Teil übernommen.", "Nur selbst getragene begünstigte Kosten können geprüft werden.", "Material hat sie gezahlt, die Arbeit ich.", "Die Gebäudeversicherung hat beim Rohrbruch in meiner selbst genutzten Wohnung die Materialkosten übernommen; die Arbeitskosten habe ich selbst bezahlt.", (("gebaudeversicherung", "gebäudeversicherung"), ("rohrbruch",), ("selbst genutzt",), ("materialkosten",), ("arbeitskosten",))),
    ("gemeinsame-leitung-aufteilung", "Im Dreifamilienhaus wurde eine gebrochene Wasserleitung repariert.", "Für die steuerliche Zuordnung ist der versorgte Gebäudeteil entscheidend.", "Die Leitung versorgt meine und beide Mietwohnungen.", "Die reparierte gemeinsame Wasserleitung versorgt meine selbst genutzte Wohnung und beide vermieteten Wohnungen des Dreifamilienhauses; wie sind die Kosten aufzuteilen?", (("gemeinsame wasserleitung",), ("selbst genutzt",), ("beide vermieteten",), ("dreifamilienhaus",), ("aufteil", "aufzuteil"))),
)


PRAEFIXE = (
    "",
    "Also, ",
    "Mal kurz: ",
    "Nur damit ich es kapier: ",
    "Okay, ",
    "Ich blick da nicht durch: ",
    "Ganz normal gefragt: ",
    "Und zwar: ",
    "Noch mal dazu: ",
    "Bitte ohne Beamtendeutsch: ",
)


def variante(text: str, nummer: int) -> str:
    kern = text
    if nummer in (1, 6):
        kern = kern.replace("ich habe", "ich hab").replace("Muss ich", "Muss ich denn")
    if nummer in (2, 7):
        kern = kern.replace("nicht", "nicht wirklich").replace("jetzt", "jetzt eigentlich")
    if nummer in (3, 8):
        kern = kern.replace("Wie ist", "Wie ist denn").replace("Kann ich", "Kann ich dann")
    if nummer in (4, 9) and kern.endswith("?"):
        kern = kern[:-1] + " – wie läuft das?"
    praefix = PRAEFIXE[nummer]
    if praefix:
        kern = kern[:1].lower() + kern[1:]
    return " ".join((praefix + kern).split())


def erstellen() -> dict:
    if len(FAELLE) != 30:
        raise ValueError(f"Erwartet sind 30 Grundfälle, vorhanden sind {len(FAELLE)}")

    ZIEL.mkdir(parents=True, exist_ok=True)
    splits = {"train": [], "validation": [], "control": []}
    basis_ids = {name: set() for name in splits}
    for index, (kennung, vorher, assistent, folge, ziel, regeln) in enumerate(FAELLE):
        split = "train" if index < 22 else "validation" if index < 26 else "control"
        basis_ids[split].add(kennung)
        for nummer in range(10):
            splits[split].append(
                {
                    "id": f"dialog300-{kennung}-{nummer + 1:02d}",
                    "thema": "Mehrschritt-Gesprächsverständnis Steuerrecht",
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": vorher},
                        {"role": "assistant", "content": assistent},
                        {"role": "user", "content": variante(folge, nummer)},
                        {"role": "assistant", "content": ziel},
                    ],
                    "detailregeln": [list(gruppe) for gruppe in regeln],
                    "metadaten": {
                        "aufgabe": "mehrschritt_kanonisierung",
                        "basisfall": kennung,
                        "split": split,
                        "synthetische_sprachvariante": True,
                        "fachlich_geprueft": True,
                        "redaktionell_geprueft_am": "2026-08-28",
                        "abgeleitet_aus": "Praxisdialog-Chargen 04 bis 06 und angrenzende Fehlerklasse",
                    },
                }
            )

    for zaehler, (split, eintraege) in enumerate(splits.items()):
        random.Random(2026082804 + zaehler).shuffle(eintraege)
        with (ZIEL / f"dialoge_300_{split}.jsonl").open("w", encoding="utf-8", newline="\n") as datei:
            for eintrag in eintraege:
                datei.write(json.dumps(eintrag, ensure_ascii=False) + "\n")

    manifest = {
        "gesamt": sum(map(len, splits.values())),
        "grundfaelle": len(FAELLE),
        "varianten_je_grundfall": 10,
        "train": len(splits["train"]),
        "validation": len(splits["validation"]),
        "control": len(splits["control"]),
        "fachlich_geprueft": True,
        "split_nach_grundfall": True,
        "basis_ids": {name: sorted(ids) for name, ids in basis_ids.items()},
        "fehlerkatalog": "tests/ergebnisse/praxisdialog_chargen_04_06_fehlerkatalog.json",
    }
    (ZIEL / "dialoge_300_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    print(json.dumps(erstellen(), ensure_ascii=False, indent=2))
