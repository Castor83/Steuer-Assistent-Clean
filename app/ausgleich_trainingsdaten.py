"""Erzeugt eine kleine Ausgleichscharge fuer Jahre und kurze Folgeangaben."""

from __future__ import annotations

import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZIEL = ROOT / "testDaten" / "umgangssprache_steuer_training"
SYSTEM = (
    "Formuliere in klarem Standarddeutsch, ohne die Steuerfrage zu beantworten. "
    "Bewahre alle Details. Schreibe 23, 24 und 25 als Steuerjahre 2023, 2024 und "
    "2025 aus. Verbinde eine kurze Antwort mit der vorherigen Frage zu einer "
    "vollstaendigen Aussage oder Frage; wiederhole die Rueckfrage nicht."
)
PRAEFIXE = ("", "also ", "bei mir ", "genau ", "kurz gesagt ", "ich meine ")


JAHRESFAELLE = (
    ("jahr-nebenkosten", "nebenkostenabrechnung 23 vom vermieter wo kommt die rein", "Wo trage ich die Nebenkostenabrechnung meines Vermieters für 2023 in der Steuererklärung ein?"),
    ("jahr-lohn", "lohnsteuerbescheinigung fuer 24 passt die zur erklaerung", "Passt die Lohnsteuerbescheinigung für 2024 zu meiner Steuererklärung 2024?"),
    ("jahr-bescheid", "der gebuehrenbescheid aus erlangen ist fuer 25 was davon brauch ich", "Der Gebührenbescheid aus Erlangen betrifft das Jahr 2025. Welche Angaben daraus benötige ich steuerlich?"),
    ("jahr-fahrt", "in 23 bin ich an 140 tagen zur arbeit gefahren wie geb ich das an", "Im Jahr 2023 bin ich an 140 Tagen zur Arbeit gefahren. Wie gebe ich die Fahrten steuerlich an?"),
    ("jahr-vermietung", "wohnung hab ich ab april 24 vermietet welche kosten zaehlen", "Ich habe die Wohnung ab April 2024 vermietet. Welche Kosten kann ich steuerlich berücksichtigen?"),
    ("jahr-rechnung", "handwerker war ende 25 da rechnung kam spaeter welches jahr gilt", "Der Handwerker war Ende 2025 bei mir, die Rechnung kam später. Welches Steuerjahr gilt für die Kosten?"),
)


FOLGEFAELLE = (
    ("folge-haelfte", "Hat die Versicherung einen Teil der Rechnung übernommen?", "Wie groß war die Erstattung?", "nur die haelfte den rest hab ich bezahlt", "Die Versicherung hat nur die Hälfte der Rechnung übernommen. Den Rest habe ich selbst bezahlt. Kann ich meinen Anteil steuerlich berücksichtigen?"),
    ("folge-fast-alles", "Wurden die Reparaturkosten erstattet?", "Bitte nenne den erstatteten Anteil.", "fast alles nur hundert euro waren von mir", "Die Versicherung hat fast alle Reparaturkosten übernommen. 100 Euro habe ich selbst getragen. Kann ich diesen Rest steuerlich angeben?"),
    ("folge-gemeinsam", "Welche Einheit war von dem Schaden betroffen?", "Bitte ordne die Leitung zu.", "die gemeinsame leitung von laden und buero", "Der Schaden betraf die gemeinsame Leitung des Ladens und des Büros. Wie ordne ich die Reparaturkosten steuerlich zu?"),
    ("folge-mietwohnung", "War deine eigene oder eine vermietete Einheit betroffen?", "Bitte nenne die betroffene Einheit.", "die mietwohnung im zweiten stock", "Die Reparatur betraf die vermietete Wohnung im zweiten Stock."),
    ("folge-liste", "Welche Gebühren nennt der Bescheid?", "Bitte nenne alle Positionen.", "wasser muell gehweg und grundsteuer", "Der Bescheid enthält Wassergebühren, Müllgebühren, Gehwegreinigungsgebühren und Grundsteuer. Welche Positionen sind steuerlich relevant?"),
    ("folge-viertel", "Wie viel vom Schaden wurde ersetzt?", "Bitte nenne den Anteil.", "ein viertel kam von versicherung", "Die Versicherung hat ein Viertel der Schadenskosten übernommen. Wie wird mein verbleibender Eigenanteil steuerlich behandelt?"),
)


VALIDIERUNG = (
    ("val-jahr", [{"role":"user","content":"grundsteuerbescheid 24 aus fuerth muss der zur erklaerung"},{"role":"assistant","content":"Gehört der Grundsteuerbescheid 2024 aus Fürth zu meiner Steuererklärung 2024?"}]),
    ("val-jahr-zwei", [{"role":"user","content":"hab in 25 neue fenster bezahlt welches steuerjahr ist das"},{"role":"assistant","content":"Ich habe 2025 neue Fenster bezahlt. Zu welchem Steuerjahr gehören die Kosten?"}]),
    ("val-folge", [{"role":"user","content":"Hat die Versicherung etwas erstattet?"},{"role":"assistant","content":"Wie hoch war die Erstattung?"},{"role":"user","content":"zwei drittel den rest ich"},{"role":"assistant","content":"Die Versicherung hat zwei Drittel der Kosten erstattet. Den Rest habe ich selbst getragen. Wie wird mein Anteil steuerlich behandelt?"}]),
    ("val-leitung", [{"role":"user","content":"Welche Wohnung war betroffen?"},{"role":"assistant","content":"Bitte ordne den Schaden zu."},{"role":"user","content":"gemeinsame leitung von zwei bueros"},{"role":"assistant","content":"Der Schaden betraf die gemeinsame Leitung zweier Büros. Wie werden die Reparaturkosten steuerlich zugeordnet?"}]),
)


def eintrag(eid: str, messages: list[dict], split: str, nummer: int) -> dict:
    return {"id": f"ausgleich-{eid}-{split}-{nummer:02d}", "thema": "Jahre und Kurzfolgen", "messages": [{"role": "system", "content": SYSTEM}, *messages], "metadaten": {"aufgabe": "ausgleich_kanonisierung", "split": split, "synthetisch": True}}


def erstellen() -> dict:
    train = []
    for eid, roh, ziel in JAHRESFAELLE:
        for nummer, prefix in enumerate(PRAEFIXE, 1):
            train.append(eintrag(eid, [{"role":"user","content":prefix + roh},{"role":"assistant","content":ziel}], "train", nummer))
    for eid, vorher, frage, roh, ziel in FOLGEFAELLE:
        for nummer, prefix in enumerate(PRAEFIXE, 1):
            train.append(eintrag(eid, [{"role":"user","content":vorher},{"role":"assistant","content":frage},{"role":"user","content":prefix + roh},{"role":"assistant","content":ziel}], "train", nummer))
    validation = [eintrag(eid, messages, "validation", nr) for nr, (eid, messages) in enumerate(VALIDIERUNG, 1)]
    random.Random(20260827).shuffle(train)
    for name, daten in (("ausgleich_train.jsonl", train), ("ausgleich_validation.jsonl", validation)):
        with (ZIEL / name).open("w", encoding="utf-8", newline="\n") as datei:
            for item in daten:
                datei.write(json.dumps(item, ensure_ascii=False) + "\n")
    return {"train": len(train), "validation": len(validation)}


if __name__ == "__main__":
    print(json.dumps(erstellen(), ensure_ascii=False, indent=2))
