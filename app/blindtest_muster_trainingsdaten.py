"""Erzeugt testgetrennte Musterbeispiele fuer Pilot 11."""

from __future__ import annotations

import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZIEL = ROOT / "testDaten" / "umgangssprache_steuer_training"
SYSTEM = (
    "Formuliere die gemeinte Steuerfrage in grammatisch klarem Standarddeutsch. "
    "Bewahre Personen, Orte, Dokumentarten, Kostenarten, Zahlen und Nutzung. "
    "Eine zweistellige Zahl 23, 24 oder 25 ist im genannten Steuerkontext ein "
    "Jahr und wird als 2023, 2024 oder 2025 geschrieben; eine danach genannte "
    "Geldsumme bleibt eine getrennte Zahl. Verwechsle nicht, wer etwas bezahlt "
    "oder vorgeschrieben hat. Nutze kurze Antworten zusammen mit der vorherigen "
    "Rückfrage. Beantworte die Steuerfrage nicht und erfinde nichts."
)
PRAEFIXE = ("", "also ", "bei mir ", "kurz ", "ich meine ", "nochmal ")


EINZELFAELLE = (
    ("spende-jahr-betrag", "hab 23 achtzig euro an den sportverein gespendet nur kontoauszug da", "Ich habe 2023 80 Euro an den Sportverein gespendet und habe nur den Kontoauszug als Nachweis."),
    ("betreuung-jahr-betrag", "tagesmutter hat 25 zweihundertvierzig euro gekostet kann ich das angeben", "Die Tagesmutter hat 2025 240 Euro gekostet. Kann ich die Kosten steuerlich angeben?"),
    ("handwerker-jahr-betrag", "in 24 hab ich dreihundert euro arbeitslohn vom maler bezahlt", "Im Jahr 2024 habe ich 300 Euro Arbeitslohn an den Maler bezahlt. Wie gebe ich die Kosten steuerlich an?"),
    ("arbeitskleidung", "chef schreibt sicherheitsschuhe vor aber bezahlt hab ich sie selbst", "Mein Arbeitgeber schreibt Sicherheitsschuhe vor, aber ich habe sie selbst bezahlt. Kann ich die Kosten steuerlich berücksichtigen?"),
    ("werkzeug", "arbeitgeber wollte dass ich eigenes werkzeug mitbring gekauft hab das von meinem geld", "Mein Arbeitgeber verlangt, dass ich eigenes Werkzeug mitbringe. Ich habe es selbst bezahlt. Wie berücksichtige ich die Kosten steuerlich?"),
    ("grundabgaben-bamberg", "grundabgabenbescheid bamberg hat muell kanal und grundsteuer muss ich die einzeln pruefen", "Der Grundabgabenbescheid aus Bamberg enthält Müllgebühren, Kanalgebühren und Grundsteuer. Muss ich die Positionen steuerlich einzeln prüfen?"),
    ("gebuehren-augsburg", "gebuehrenbescheid augsburg mit wasser strassenreinigung und abfall was davon ist wichtig", "Der Gebührenbescheid aus Augsburg enthält Wassergebühren, Straßenreinigung und Abfallgebühren. Welche Positionen sind steuerlich relevant?"),
    ("pendeln-jahr", "fuer 25 waren es 32 kilometer einfache strecke an 150 arbeitstagen", "Für 2025 betrug mein einfacher Arbeitsweg 32 Kilometer an 150 Arbeitstagen. Wie gebe ich ihn steuerlich an?"),
    ("pendeln-ohne-jahr", "ich fahr 19 km einfach zur arbeit und das an 170 tagen", "Mein einfacher Arbeitsweg beträgt 19 Kilometer an 170 Tagen. Wie gebe ich ihn steuerlich an?"),
    ("eigenes-garagentor", "am eigenen haus ist garagentor kaputt versicherung zahlt nichts kann ich reparatur absetzen", "Das Garagentor an meinem eigenen Haus ist defekt, und die Versicherung übernimmt keine Kosten. Kann ich die Reparatur steuerlich absetzen?"),
    ("eigenes-dachfenster", "dachfenster von meinem eigenen haus war undicht den handwerker hab ich gezahlt", "Das Dachfenster meines eigenen Hauses war undicht. Den Handwerker habe ich selbst bezahlt. Wie werden die Kosten steuerlich behandelt?"),
    ("gemischt-fenster", "zweifamilienhaus unten wohn ich selbst oben ist vermietet wie teil ich neue fenster auf", "In meinem Zweifamilienhaus bewohne ich die untere Wohnung selbst und vermiete die obere Wohnung. Wie teile ich die Kosten der neuen Fenster steuerlich auf?"),
)


FOLGEFAELLE = (
    ("material-arbeit", "Welche Kosten hat die Versicherung erstattet?", "Bitte trenne Material und Arbeit.", "material komplett arbeit hab ich bezahlt", "Die Versicherung hat die Materialkosten vollständig übernommen. Die Arbeitskosten habe ich selbst bezahlt. Kann ich meinen Anteil steuerlich berücksichtigen?"),
    ("ersatzteile-lohn", "Was wurde von der Versicherung übernommen?", "Bitte nenne die einzelnen Rechnungspositionen.", "nur ersatzteile lohn war meiner", "Die Versicherung hat nur die Ersatzteile bezahlt. Den Arbeitslohn habe ich selbst getragen. Wie wird mein Anteil steuerlich berücksichtigt?"),
    ("versicherung-haelfte", "Hat die Versicherung die Rechnung bezahlt?", "Wie groß war der erstattete Anteil?", "nur die haelfte rest hab ich getragen", "Die Versicherung hat nur die Hälfte der Rechnung übernommen. Den Rest habe ich selbst getragen. Kann ich meinen Anteil steuerlich berücksichtigen?"),
    ("leitung-laden-wohnung", "Welcher Teil des Gebäudes war betroffen?", "Bitte ordne die Reparatur zu.", "gemeinsame leitung von meinem laden und der mietwohnung", "Die Reparatur betraf die gemeinsame Leitung meines Ladens und der Mietwohnung. Wie teile ich die Kosten steuerlich auf?"),
    ("leitung-eigen-miete", "War die Leitung privat oder vermietet?", "Bitte nenne alle betroffenen Einheiten.", "meine wohnung und die vermietete oben gemeinsam", "Die gemeinsame Leitung meiner eigenen Wohnung und der vermieteten Wohnung im Obergeschoss war betroffen. Wie ordne ich die Reparaturkosten steuerlich zu?"),
    ("nutzung-anteile", "Wie wird das Gebäude genutzt?", "Bitte nenne die Aufteilung.", "dreissig prozent selbst siebzig vermietet", "Ich nutze 30 Prozent des Gebäudes selbst und vermiete 70 Prozent. Wie teile ich gemeinsame Kosten steuerlich auf?"),
    ("jahr-korrektur-betrag", "Geht es um das Steuerjahr 2024?", "Bitte korrigiere Jahr und Betrag.", "nein 23 und es waren 90 euro", "Es geht um das Steuerjahr 2023 und einen Betrag von 90 Euro."),
    ("ort-bescheid", "Um welchen kommunalen Bescheid geht es?", "Bitte nenne Ort und Positionen.", "regensburg grundabgaben mit wasser muell und grundsteuer", "Es geht um den Grundabgabenbescheid aus Regensburg mit Wassergebühren, Müllgebühren und Grundsteuer. Welche Positionen sind steuerlich relevant?"),
)


VALIDIERUNG = (
    ("val-jahr-betrag", [{"role":"user","content":"hab 24 sechzig euro an tierheim gespendet"},{"role":"assistant","content":"Ich habe 2024 60 Euro an das Tierheim gespendet. Wie weise ich die Spende steuerlich nach?"}]),
    ("val-kostentraeger", [{"role":"user","content":"firma wollte schutzbrille aber bezahlt hab ich die selber"},{"role":"assistant","content":"Mein Arbeitgeber verlangt eine Schutzbrille, die ich selbst bezahlt habe. Kann ich die Kosten steuerlich angeben?"}]),
    ("val-bescheid", [{"role":"user","content":"grundabgabenbescheid wuerzburg mit kanal muell und grundsteuer"},{"role":"assistant","content":"Der Grundabgabenbescheid aus Würzburg enthält Kanalgebühren, Müllgebühren und Grundsteuer. Welche Positionen sind steuerlich relevant?"}]),
    ("val-pendel", [{"role":"user","content":"in 23 waren es 21 km einfach an 130 tagen"},{"role":"assistant","content":"Im Jahr 2023 betrug mein einfacher Arbeitsweg 21 Kilometer an 130 Tagen. Wie gebe ich ihn steuerlich an?"}]),
    ("val-folge-kosten", [{"role":"user","content":"Was hat die Versicherung bezahlt?"},{"role":"assistant","content":"Bitte trenne die Kostenarten."},{"role":"user","content":"teile ja arbeit nein"},{"role":"assistant","content":"Die Versicherung hat die Ersatzteile bezahlt, nicht aber die Arbeitskosten. Die Arbeitskosten habe ich selbst getragen. Wie wird mein Anteil steuerlich berücksichtigt?"}]),
    ("val-folge-leitung", [{"role":"user","content":"Wo verlief die kaputte Leitung?"},{"role":"assistant","content":"Bitte nenne die betroffenen Einheiten."},{"role":"user","content":"durch meine wohnung und den vermieteten laden"},{"role":"assistant","content":"Die defekte Leitung verlief durch meine eigene Wohnung und den vermieteten Laden. Wie ordne ich die Reparaturkosten steuerlich zu?"}]),
)


def eintrag(eid: str, messages: list[dict], split: str, nummer: int) -> dict:
    return {"id": f"blindmuster-{eid}-{split}-{nummer:02d}", "thema": "Robuste Alltagssprache", "messages": [{"role":"system","content":SYSTEM}, *messages], "metadaten":{"aufgabe":"blindmuster_kanonisierung","split":split,"synthetisch":True}}


def erstellen() -> dict:
    train = []
    for eid, roh, ziel in EINZELFAELLE:
        for nummer, prefix in enumerate(PRAEFIXE, 1):
            train.append(eintrag(eid, [{"role":"user","content":prefix + roh},{"role":"assistant","content":ziel}], "train", nummer))
    for eid, vorher, frage, roh, ziel in FOLGEFAELLE:
        for nummer, prefix in enumerate(PRAEFIXE, 1):
            train.append(eintrag(eid, [{"role":"user","content":vorher},{"role":"assistant","content":frage},{"role":"user","content":prefix + roh},{"role":"assistant","content":ziel}], "train", nummer))
    validation = [eintrag(eid, messages, "validation", nr) for nr, (eid, messages) in enumerate(VALIDIERUNG, 1)]
    random.Random(20260827).shuffle(train)
    for name, daten in (("blindmuster_train.jsonl",train),("blindmuster_validation.jsonl",validation)):
        with (ZIEL / name).open("w",encoding="utf-8",newline="\n") as datei:
            for item in daten:
                datei.write(json.dumps(item,ensure_ascii=False)+"\n")
    return {"train":len(train),"validation":len(validation)}


if __name__ == "__main__":
    print(json.dumps(erstellen(),ensure_ascii=False,indent=2))
