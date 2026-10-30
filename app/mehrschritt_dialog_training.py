"""Erzeugt getrennte Mehrschritt-Daten aus echten Fehlern der Web-Dialogtests."""

from __future__ import annotations

import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZIEL = ROOT / "testDaten" / "umgangssprache_steuer_training"
SYSTEM = (
    "Du vereinheitlichst kurze umgangssprachliche Folgefragen in deutschen Steuerdialogen. "
    "Nutze den vorherigen Gesprächsverlauf, löse Pronomen eindeutig auf und formuliere nur "
    "die gemeinte Frage oder Angabe in Standarddeutsch. Bewahre Personen, Beträge, Jahre, "
    "Nutzungsarten und Behörden. Beantworte die Steuerfrage nicht und erfinde nichts."
)


# Kennung, vorherige Nutzerangabe, vorherige Assistentenantwort, kurze Folge,
# eindeutiges Ziel, maschinell prüfbare Detailgruppen.
FAELLE = (
    ("schenkung-melden", "Meine Mutter hat mir 20.000 Euro geschenkt.", "Das ist kein Einkommen; es gilt Schenkungsteuerrecht.", "Muss ich das trotzdem irgendwo melden?", "Muss ich die Schenkung meiner Mutter über 20.000 Euro trotz des Freibetrags beim Schenkungsteuerfinanzamt anzeigen?", (("mutter",), ("20.000 euro", "20000 euro"), ("schenkungsteuerfinanzamt",), ("anzeigen", "melden"))),
    ("minijob-eintragen", "Ich hatte 2023 neben meinem Hauptjob einen Minijob mit 520 Euro monatlich.", "Entscheidend ist, ob er pauschal oder individuell versteuert wurde.", "Muss das in meine Steuererklärung rein?", "Muss ich den Minijob aus 2023 mit 520 Euro monatlich in meiner Steuererklärung angeben, wenn er pauschal oder individuell versteuert wurde?", (("minijob",), ("2023",), ("520 euro",), ("pauschal",), ("individuell",))),
    ("heirat-ganzjahr", "Wir haben erst im Dezember 2023 geheiratet.", "Eine Zusammenveranlagung kann trotzdem möglich sein.", "Zählt das wirklich für das ganze Jahr?", "Gilt die Heirat im Dezember 2023 bei der Zusammenveranlagung für das gesamte Steuerjahr?", (("heirat",), ("dezember",), ("2023",), ("gesamte steuerjahr", "ganze jahr"))),
    ("einspruch-zahlen", "Ich habe gegen den Grundsteuerwertbescheid Einspruch eingelegt.", "Der Einspruch läuft; die Zahlung wird dadurch nicht automatisch ausgesetzt.", "Muss ich das trotzdem erst mal bezahlen?", "Muss ich die Grundsteuer trotz des laufenden Einspruchs gegen den Grundsteuerwertbescheid zunächst bezahlen oder eine Aussetzung der Vollziehung beantragen?", (("grundsteuer",), ("einspruch",), ("bezahlen", "zahlen"), ("aussetzung der vollziehung",))),
    ("plattform-steuer", "Kleinanzeigen kann meine 30 Verkäufe an das Finanzamt melden.", "Die Meldeschwelle ist keine Steuerfreigrenze.", "Heißt das, ich muss jetzt automatisch Steuern zahlen?", "Muss ich wegen der Plattformmeldung von 30 Kleinanzeigen-Verkäufen automatisch Einkommensteuer zahlen?", (("plattformmeldung",), ("30",), ("kleinanzeigen",), ("automatisch",), ("einkommensteuer",))),
    ("garage-schuppen", "Bei der bayerischen Grundsteuer habe ich die Garage am Wohnhaus eingeordnet.", "Für zugeordnete Garagen gelten besondere Flächenregeln.", "Und was ist mit dem kleinen Schuppen daneben?", "Wie ist der kleine Schuppen neben der Garage am Wohnhaus bei der bayerischen Grundsteuer zu berücksichtigen?", (("schuppen",), ("garage",), ("wohnhaus",), ("bayerischen grundsteuer", "grundsteuer in bayern"))),
    ("grundsteuer-zahlungsbescheid", "Der Grundsteuerwertbescheid ist noch keine Zahlungsaufforderung.", "Den Zahlungsbescheid erlässt später die Gemeinde.", "Und wer schickt mir den dann?", "Welche Behörde schickt mir nach dem Grundsteuerwertbescheid den eigentlichen Grundsteuerbescheid mit der Zahlungsaufforderung?", (("behörde",), ("grundsteuerwertbescheid",), ("grundsteuerbescheid",), ("zahlungsaufforderung",))),
    ("leerstand-umlage", "Ich vermiete zwei Wohnungen und lege die Grundsteuer laut Mietvertrag um.", "Für die Abrechnung ist der richtige Verteilerschlüssel nötig.", "Eine davon stand aber ein halbes Jahr leer. Zahlen die anderen das mit?", "Müssen die Mieter der bewohnten Wohnung den Grundsteueranteil der anderen, ein halbes Jahr leerstehenden Wohnung mittragen?", (("mieter",), ("grundsteueranteil",), ("halbes jahr",), ("leersteh",))),
    ("laptop-sofort", "Mein 2023 gekaufter Laptop kostete 1.200 Euro und wird zu 60 Prozent beruflich genutzt.", "Der berufliche Anteil beträgt 720 Euro.", "Kann ich die 720 Euro sofort komplett ansetzen?", "Kann ich den beruflichen Anteil von 720 Euro für den 2023 gekauften Laptop im Anschaffungsjahr vollständig als Arbeitsmittel ansetzen?", (("720 euro",), ("2023",), ("laptop",), ("anschaffungsjahr",), ("arbeitsmittel",))),
    ("babysitter-bar", "Für die Kinderbetreuung 2023 habe ich eine ordnungsgemäße Rechnung.", "Die Zahlung muss unbar erfolgen.", "Die 600 Euro für den Babysitter waren aber bar. Geht das auch?", "Kann ich die 2023 bar bezahlten 600 Euro für den Babysitter als Kinderbetreuungskosten abziehen?", (("2023",), ("600 euro",), ("babysitter",), ("bar",), ("kinderbetreuungskosten",))),
    ("hausverkauf-erstattung", "Ich habe das Haus im Juli verkauft und war am 1. Januar Eigentümer.", "Gegenüber der Stadt schulde ich regelmäßig die Jahresgrundsteuer.", "Der Käufer hat mir laut Notarvertrag die Hälfte erstattet. Ändert das etwas?", "Ändert die im Notarvertrag vereinbarte hälftige Erstattung des Käufers etwas an meiner Grundsteuerschuld gegenüber der Stadt für das Verkaufsjahr?", (("notarvertrag",), ("halftig", "hälftig", "hälfte"), ("kaufer", "käufer"), ("grundsteuerschuld",), ("stadt",))),
    ("vinted-verlust", "Vinted meldet möglicherweise meine 35 Verkäufe über insgesamt 1.500 Euro.", "Die Plattformmeldung entscheidet nicht über die Steuerpflicht.", "Ich hab alle alten Klamotten billiger verkauft als gekauft. Muss ich Steuern zahlen?", "Muss ich Einkommensteuer zahlen, wenn ich 35 eigene gebrauchte Kleidungsstücke über Vinted für insgesamt 1.500 Euro mit Verlust verkauft habe?", (("einkommensteuer",), ("35",), ("vinted",), ("1.500 euro", "1500 euro"), ("verlust",))),
    ("wohnflaeche-frist", "Im Grundsteuerbescheid stehen 180 statt der richtigen 120 Quadratmeter Wohnfläche.", "Gegen den Grundlagenbescheid gilt grundsätzlich eine einmonatige Einspruchsfrist.", "Und wenn ich das erst zwei Monate später gemerkt habe?", "Wie kann ich die Wohnfläche von 180 auf 120 Quadratmeter korrigieren, wenn ich den Fehler im Grundsteuerbescheid erst zwei Monate später nach Ablauf der Einspruchsfrist bemerkt habe?", (("180",), ("120",), ("wohnflache", "wohnfläche"), ("zwei monate",), ("einspruchsfrist",))),
    ("versicherung-haelfte", "Der Rohrbruch betraf meine selbst genutzte Wohnung.", "Nur selbst getragene begünstigte Handwerkerkosten kommen in Betracht.", "Die Versicherung hat aber nur die Hälfte bezahlt.", "Die Gebäudeversicherung hat beim Rohrbruch in meiner selbst genutzten Wohnung nur die Hälfte der Kosten übernommen; die andere Hälfte habe ich selbst getragen.", (("gebäudeversicherung", "versicherung"), ("rohrbruch",), ("selbst genutzt",), ("halfte", "hälfte"), ("selbst getragen",))),
    ("wohnung-eigen", "Im Dreifamilienhaus wurde ein Rohrbruch repariert.", "Für die Einordnung muss der betroffene Gebäudeteil feststehen.", "Das war bei mir in der Wohnung.", "Der Rohrbruch betraf meine selbst genutzte Wohnung im Dreifamilienhaus.", (("rohrbruch",), ("selbst genutzt",), ("wohnung",), ("dreifamilienhaus",))),
    ("leitung-alle", "Im Dreifamilienhaus ist eine Wasserleitung gebrochen.", "Es muss geklärt werden, welcher Gebäudeteil betroffen war.", "Die Leitung ist für alle drei Wohnungen.", "Betroffen ist die gemeinsame Wasserleitung für alle drei Wohnungen des Dreifamilienhauses.", (("gemeinsame",), ("wasserleitung",), ("drei wohnungen",), ("dreifamilienhaus",))),
    ("arbeitsweg-tage", "Mein einfacher Arbeitsweg beträgt 15 Kilometer.", "Für die Entfernungspauschale fehlen noch die Arbeitstage.", "Das waren 120 Tage.", "Ich bin an 120 Arbeitstagen jeweils 15 Kilometer einfache Strecke zur ersten Tätigkeitsstätte gefahren.", (("120",), ("15 kilometer",), ("einfache strecke",), ("erste tatigkeitsstatte", "erste tätigkeitsstätte"))),
    ("homeoffice-resttage", "Ich habe 2023 an 80 Tagen zu Hause gearbeitet.", "Für diese Tage kommt die Homeoffice-Tagespauschale in Betracht.", "An den anderen Tagen war ich im Büro.", "An den übrigen Arbeitstagen im Jahr 2023 habe ich nicht im Homeoffice, sondern im Büro gearbeitet.", (("ubrigen arbeitstagen", "übrigen arbeitstagen"), ("2023",), ("homeoffice",), ("buro", "büro"))),
    ("steuerklasse-pruefen", "Auf meiner Lohnsteuerbescheinigung 2023 steht Steuerklasse I.", "Die Steuerklasse sollte mit den persönlichen Verhältnissen abgeglichen werden.", "Und warum soll ich das prüfen?", "Warum soll ich die Steuerklasse I auf meiner Lohnsteuerbescheinigung 2023 prüfen?", (("steuerklasse i", "steuerklasse 1"), ("lohnsteuerbescheinigung",), ("2023",), ("prufen", "prüfen"))),
    ("grundabgaben-muell", "Auf meinem Bescheid für das Haus stehen Grundsteuer, Müll und Kanalgebühren.", "Die Positionen müssen getrennt eingeordnet werden.", "Und was davon kann ich bei der Vermietung ansetzen?", "Welche Anteile von Grundsteuer, Müll- und Kanalgebühren für das teilweise vermietete Haus kann ich bei den Vermietungseinkünften ansetzen?", (("grundsteuer",), ("mull", "müll"), ("kanal",), ("teilweise vermietet",), ("vermietungseinkunfte", "vermietungseinkünfte"))),
    ("kaution-rueckgabe", "Mein Mieter hat beim Einzug eine Kaution gezahlt.", "Eine nur verwahrte rückzahlbare Kaution ist noch keine Mieteinnahme.", "Und wenn ich sie beim Auszug komplett zurückzahle?", "Ist die vollständig an den Mieter zurückgezahlte Kaution bei meinen Vermietungseinkünften zu versteuern?", (("vollstandig", "vollständig"), ("mieter",), ("kaution",), ("vermietungseinkunfte", "vermietungseinkünfte"))),
    ("leerstand-sanierung", "Eine Wohnung im Dreifamilienhaus steht leer und soll wieder vermietet werden.", "Die Vermietungsabsicht muss nachweisbar bleiben.", "Kann ich währenddessen das Bad komplett sanieren?", "Wie sind die Kosten einer vollständigen Badsanierung während des vorübergehenden Leerstands einer weiterhin zur Vermietung bestimmten Wohnung einzuordnen?", (("badsanierung",), ("vorubergehend", "vorübergehend"), ("leerstand",), ("vermietung",))),
    ("ebike-arbeitsweg", "Ich habe gefragt, ob ich mein E-Bike steuerlich absetzen kann.", "Dafür muss zwischen Kaufpreis und Arbeitsweg unterschieden werden.", "Ich fahre damit jeden Tag zur Arbeit.", "Wie wird mein täglich mit dem E-Bike zurückgelegter Arbeitsweg steuerlich berücksichtigt?", (("e-bike",), ("taglich", "täglich"), ("arbeitsweg",), ("steuerlich",))),
    ("dokument-name", "Die Dokumentenerkennung hat auf der Lohnsteuerbescheinigung den Namen Alex Beispiel erkannt.", "Der erkannte Name soll dem richtigen Nutzerprofil zugeordnet werden.", "Das bin ich, speicher das bitte bei mir.", "Der auf der Lohnsteuerbescheinigung erkannte Name Alex Beispiel gehört zu meinem Nutzerprofil und soll dort gespeichert werden.", (("lohnsteuerbescheinigung",), ("alex beispiel",), ("nutzerprofil",), ("gespeichert",))),
)


PRAEFIXE = (
    "",
    "Also, ",
    "Mal kurz: ",
    "Ich blicke da nicht durch: ",
    "Nur damit ich es verstehe: ",
    "Bitte normal gesagt: ",
    "Noch eine Frage: ",
    "Okay, und ",
)


def variante(text: str, nummer: int) -> str:
    praefix = PRAEFIXE[nummer % len(PRAEFIXE)]
    kern = text if not praefix else text[:1].lower() + text[1:]
    ausgabe = praefix + kern
    if nummer in (1, 4):
        ausgabe = ausgabe.replace("ich habe", "ich hab").replace("muss ich", "muss ich denn")
    elif nummer == 2 and ausgabe.endswith("?"):
        ausgabe = ausgabe[:-1] + " – wie ist das gemeint?"
    return " ".join(ausgabe.split())


def erstellen() -> dict:
    splits = {"train": [], "validation": [], "control": []}
    basis_ids = {name: set() for name in splits}
    for index, (eid, vorher, assistent, folge, ziel, regeln) in enumerate(FAELLE):
        rest = index % 8
        split = "validation" if rest == 6 else "control" if rest == 7 else "train"
        basis_ids[split].add(eid)
        for nummer in range(8):
            splits[split].append(
                {
                    "id": f"mehrschritt-{eid}-{split}-{nummer + 1:02d}",
                    "thema": "Echte mehrteilige Steuerdialoge",
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
                        "synthetisch": True,
                        "fachlich_geprueft": True,
                        "basisfall": eid,
                        "split": split,
                    },
                }
            )
    for zaehler, (split, eintraege) in enumerate(splits.items()):
        random.Random(20260828 + zaehler).shuffle(eintraege)
        pfad = ZIEL / f"mehrschritt_{split}.jsonl"
        with pfad.open("w", encoding="utf-8", newline="\n") as datei:
            for eintrag in eintraege:
                datei.write(json.dumps(eintrag, ensure_ascii=False) + "\n")
    manifest = {
        "basisfaelle": len(FAELLE),
        "varianten_je_basisfall": 8,
        "train": len(splits["train"]),
        "validation": len(splits["validation"]),
        "control": len(splits["control"]),
        "basis_ids": {name: sorted(ids) for name, ids in basis_ids.items()},
    }
    (ZIEL / "mehrschritt_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    print(json.dumps(erstellen(), ensure_ascii=False, indent=2))
