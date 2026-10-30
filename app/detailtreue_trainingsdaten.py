"""Erzeugt eine testgetrennte Detailtreue-Charge fuer Pilot 08."""

from __future__ import annotations

import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZIEL = ROOT / "testDaten" / "umgangssprache_steuer_training"
SYSTEM = (
    "Formuliere die aktuelle umgangssprachliche Steuerfrage in natuerlichem, "
    "grammatisch richtigem Standarddeutsch. Bewahre jedes genannte Jahr, jeden "
    "Ort, jedes Bauteil, jede Kostenart, Anzahl und Nutzung. Schreibe zweistellige "
    "Steuerjahre wie 23, 24 oder 25 eindeutig als 2023, 2024 oder 2025. "
    "Verallgemeinere konkrete Angaben nicht. Nutze bei kurzen Folgeantworten den "
    "Gespraechskontext und formuliere die gemeinte vollstaendige Frage, ohne die "
    "vorherige Rueckfrage erneut zu stellen. Beantworte die Steuerfrage nicht und "
    "erfinde nichts."
)


EINZELFAELLE = (
    ("jahr-ansbach", "grundsteuerbescheid fuer mein zweifamilienhaus in ansbach ist von 25 muss ich den aufheben", "Der Grundsteuerbescheid für mein Zweifamilienhaus in Ansbach betrifft das Jahr 2025. Muss ich ihn aufbewahren?"),
    ("jahr-erklaerung", "ich mach jetzt die einkommensteuer fuer 23 welche lohnzettel brauch ich", "Ich erstelle jetzt die Einkommensteuererklärung 2023. Welche Lohnsteuerbescheinigungen benötige ich?"),
    ("dachfenster", "am eigenen haus ist das dachfenster undicht und versicherung zahlt nichts kann ich die reparatur angeben", "Das Dachfenster an meinem eigenen Haus ist undicht, und die Versicherung übernimmt keine Kosten. Kann ich die Reparatur steuerlich angeben?"),
    ("kellerwand", "kellerwand war nass gebaeudeversicherung hat nur trocknung bezahlt wie ist es mit dem streichen", "Die Kellerwand war feucht. Die Gebäudeversicherung hat nur die Trocknung bezahlt. Wie wird das anschließende Streichen steuerlich behandelt?"),
    ("abgaben-nuernberg", "im grundabgabenbescheid nuernberg stehen abfall strassenreinigung und niederschlagswasser was davon brauch ich", "Im Grundabgabenbescheid der Stadt Nürnberg stehen Abfallgebühren, Straßenreinigungsgebühren und Niederschlagswassergebühren. Welche davon benötige ich für die Steuererklärung?"),
    ("kostenliste", "rechnung hat anfahrt arbeitszeit ersatzteile und entsorgung muss ich das trennen", "Die Rechnung enthält Anfahrt, Arbeitszeit, Ersatzteile und Entsorgungskosten. Muss ich diese Positionen steuerlich trennen?"),
    ("vierfamilienhaus", "vierfamilienhaus eine wohnung bewohn ich drei vermiete ich wie teile ich heizungskosten", "In meinem Vierfamilienhaus bewohne ich eine Wohnung selbst und vermiete drei Wohnungen. Wie teile ich die Heizungskosten steuerlich auf?"),
    ("rechnung-fehlt", "mir fehlt die rechnung vom elektriker hab aber ueberweisungsbeleg erkennt finanzamt das an", "Mir fehlt die Rechnung des Elektrikers, aber ich habe den Überweisungsbeleg. Erkennt das Finanzamt diesen Nachweis an?"),
    ("name-dokument", "auf dem bescheid steht maria beispiel statt marie beispiel muss ich das melden", "Auf dem Bescheid steht Maria Beispiel statt Marie Beispiel. Muss ich den falschen Namen melden?"),
    ("arbeitsweg", "fuer 24 waren es 18 kilometer einfach zur arbeit und an 160 tagen wie trag ich das ein", "Für 2024 betrug mein einfacher Arbeitsweg 18 Kilometer an 160 Tagen. Wie trage ich ihn in der Steuererklärung ein?"),
)


FOLGEFAELLE = (
    ("haelfte-haftpflicht", "Hat eine Versicherung einen Teil des Schadens ersetzt?", "Wie viel wurde erstattet?", "ja die haftpflicht hat genau die haelfte von der rechnung gezahlt", "Die Haftpflichtversicherung hat genau die Hälfte der Rechnung übernommen. Kann ich den verbleibenden selbst getragenen Teil steuerlich berücksichtigen?"),
    ("viertel-versicherung", "Wurde die Sanierung bezuschusst oder erstattet?", "Bitte nenne die Erstattung.", "versicherung hat ein viertel gezahlt den rest ich", "Die Versicherung hat ein Viertel der Sanierungskosten übernommen. Den verbleibenden Teil habe ich selbst bezahlt. Wie wird mein Anteil steuerlich behandelt?"),
    ("leitung-laden", "War nur eine Einheit oder eine gemeinsame Leitung betroffen?", "Bitte ordne die Reparatur zu.", "gemeinsame leitung vom laden und der wohnung oben", "Die Reparatur betraf die gemeinsame Leitung des Ladens und der darüberliegenden Wohnung. Wie ordne ich die Kosten steuerlich zu?"),
    ("jahr-korrektur", "Dann geht es um die Erklärung 2023.", "Ist 2023 das richtige Steuerjahr?", "nein vierundzwanzig meinte ich", "Ich meinte nicht 2023, sondern das Steuerjahr 2024."),
    ("raum-speicher", "Welcher Teil des Gebäudes wurde repariert?", "Bitte nenne den betroffenen Gebäudeteil.", "der speicher ueber der mietwohnung", "Die Reparatur betraf den Speicher über der vermieteten Wohnung."),
    ("abgaben-folge", "Welche Positionen stehen auf dem kommunalen Bescheid?", "Bitte nenne alle aufgeführten Abgaben.", "kanal wasser muell und grundsteuer", "Auf dem kommunalen Bescheid stehen Kanalgebühren, Wassergebühren, Müllgebühren und Grundsteuer. Welche Positionen sind steuerlich relevant?"),
)


VALIDIERUNG = (
    ("val-jahr", "erklaerung 25 und lohnbescheinigung 25 passen die zusammen", "Passen die Lohnsteuerbescheinigung 2025 und die Steuererklärung 2025 zusammen?"),
    ("val-bauteil", "garagentor am eigenen haus defekt versicherung zahlt nur motor", "Das Garagentor an meinem eigenen Haus ist defekt. Die Versicherung bezahlt nur den Motor. Wie werden die übrigen Kosten steuerlich behandelt?"),
    ("val-liste", "bescheid hat wasser kanal und muellgebuehr welche davon angeben", "Der Bescheid enthält Wassergebühren, Kanalgebühren und Müllgebühren. Welche davon muss ich steuerlich angeben?"),
    ("val-nutzung", "zweifamilienhaus unten wohn ich oben vermietet wie rechne ich dach", "In meinem Zweifamilienhaus bewohne ich die untere Wohnung selbst und vermiete die obere Wohnung. Wie teile ich die Dachkosten steuerlich auf?"),
    ("val-folge-haelfte", "Wie viel hat die Hausratversicherung erstattet?", "Bitte nenne den erstatteten Anteil.", "nur ein drittel rest war meiner", "Die Hausratversicherung hat nur ein Drittel der Kosten erstattet. Den Rest habe ich selbst getragen. Wie wird mein Anteil steuerlich behandelt?"),
    ("val-folge-ort", "Wo genau wurde das Rohr repariert?", "Bitte nenne den betroffenen Bereich.", "im treppenhaus zwischen zwei mietwohnungen", "Das Rohr wurde im Treppenhaus zwischen zwei vermieteten Wohnungen repariert."),
)


PRAEFIXE = ("", "also ", "bei mir ", "kurz ", "ich meine ", "nochmal ")


def eintrag(eid: str, messages: list[dict], split: str, nummer: int) -> dict:
    return {
        "id": f"detail-{eid}-{split}-{nummer:02d}",
        "thema": "Detailtreue, Jahresnormalisierung und Folgekontext",
        "messages": [{"role": "system", "content": SYSTEM}, *messages],
        "metadaten": {"aufgabe": "detailtreue_kanonisierung", "split": split, "synthetisch": True},
    }


def varianten(text: str) -> list[str]:
    return [" ".join((praefix + text).split()) for praefix in PRAEFIXE]


def erstellen() -> dict:
    train = []
    for eid, roh, ziel in EINZELFAELLE:
        for nummer, text in enumerate(varianten(roh), 1):
            train.append(eintrag(eid, [{"role": "user", "content": text}, {"role": "assistant", "content": ziel}], "train", nummer))
    for eid, vorher, frage, roh, ziel in FOLGEFAELLE:
        for nummer, text in enumerate(varianten(roh), 1):
            train.append(eintrag(eid, [{"role": "user", "content": vorher}, {"role": "assistant", "content": frage}, {"role": "user", "content": text}, {"role": "assistant", "content": ziel}], "train", nummer))
    validation = []
    for nummer, werte in enumerate(VALIDIERUNG, 1):
        eid, *inhalt = werte
        if len(inhalt) == 2:
            roh, ziel = inhalt
            messages = [{"role": "user", "content": roh}, {"role": "assistant", "content": ziel}]
        else:
            vorher, frage, roh, ziel = inhalt
            messages = [{"role": "user", "content": vorher}, {"role": "assistant", "content": frage}, {"role": "user", "content": roh}, {"role": "assistant", "content": ziel}]
        validation.append(eintrag(eid, messages, "validation", nummer))
    random.Random(20260827).shuffle(train)
    for name, daten in (("detailtreue_train.jsonl", train), ("detailtreue_validation.jsonl", validation)):
        with (ZIEL / name).open("w", encoding="utf-8", newline="\n") as datei:
            for item in daten:
                datei.write(json.dumps(item, ensure_ascii=False) + "\n")
    return {"train": len(train), "validation": len(validation)}


if __name__ == "__main__":
    print(json.dumps(erstellen(), ensure_ascii=False, indent=2))
