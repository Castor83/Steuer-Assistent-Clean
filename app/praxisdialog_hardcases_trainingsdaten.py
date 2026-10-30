"""Erzeugt gezielte, testgetrennte Dialogfaelle fuer Pilot 06."""

from __future__ import annotations

import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZIEL = ROOT / "testDaten" / "umgangssprache_steuer_training"
SYSTEM = (
    "Formuliere nur die aktuelle Nutzerfrage oder Nutzerangabe in klarem "
    "Standarddeutsch. Bewahre Orte, Personen, Nutzung, Jahre, Betraege, "
    "Kostenarten und Versicherungsanteile. Beantworte die Steuerfrage nicht. "
    "Erfinde nichts: Eigentum bedeutet nicht automatisch Selbstnutzung. "
    "Mache kurze Folgeantworten mithilfe der vorherigen Rueckfrage eindeutig, "
    "ohne die Rueckfrage zu wiederholen. Bewahre auch Woerter wie 'auch', "
    "wenn der Nutzer eine zusaetzliche Bedingung erfragt."
)


EINZELFAELLE = (
    ("bad-versicherung", "im bad von unserer erdgeschosswohnung war ein rohr leck die versicherung zahlt neunzig prozent kann ich den rest angeben", "In unserer Erdgeschosswohnung war ein Wasserrohr undicht. Die Versicherung übernimmt 90 Prozent der Kosten. Kann ich den verbleibenden selbst getragenen Anteil steuerlich angeben?"),
    ("mieter-leitung", "über der vermieteten dachwohnung ist die gemeinsame wasserleitung kaputt was kann ich davon absetzen", "Die gemeinsame Wasserleitung über der vermieteten Dachwohnung ist beschädigt. Welche Kosten kann ich davon steuerlich absetzen?"),
    ("grundsteuer-fuerth", "grundsteuerbescheid fürs vierfamilienhaus in fürth ist für 2024 gekommen muss ich was prüfen", "Der Grundsteuerbescheid für mein Vierfamilienhaus in Fürth für 2024 ist eingegangen. Muss ich etwas prüfen?"),
    ("grundsteuer-eigenheim", "kommt die grundsteuer vom selbst bewohnten haus in die einkommensteuer für 2024", "Muss ich die Grundsteuer für mein selbst bewohntes Haus in der Einkommensteuererklärung 2024 angeben?"),
    ("steuerklasse-vier", "auf der lohnsteuerbescheinigung steht klasse vier obwohl wir seit juli getrennt sind stimmt das", "Auf meiner Lohnsteuerbescheinigung steht Steuerklasse IV, obwohl wir seit Juli getrennt leben. Ist das richtig?"),
    ("gemischte-reparatur", "2023 hab ich unten selber gewohnt und oben vermietet wie verteile ich die kosten von der heizung", "Ich habe 2023 die untere Wohnung selbst genutzt und die obere Wohnung vermietet. Wie verteile ich die Kosten der Heizungsreparatur steuerlich?"),
    ("konto-ohne-rechnung", "rechnung find ich nicht mehr aber die überweisung ist aufm kontoauszug reicht das als beleg", "Ich finde die Rechnung nicht mehr, aber die Überweisung ist auf dem Kontoauszug erkennbar. Reicht das als Beleg?"),
    ("eigen-ohne-nutzung", "kann ich die renovierung von meinem eigenen haus absetzen wenn die versicherung nur die hälfte gezahlt hat", "Kann ich die Renovierung meines eigenen Hauses steuerlich absetzen, wenn die Versicherung nur die Hälfte der Kosten übernommen hat?"),
    ("material-lohn", "die versicherung hat die ersatzteile bezahlt den arbeitslohn vom installateur hab ich übernommen", "Die Versicherung hat die Ersatzteile bezahlt. Den Arbeitslohn des Installateurs habe ich selbst übernommen. Wie wird das steuerlich berücksichtigt?"),
    ("homeoffice-keller", "ich war 2024 angestellt und hab im keller am normalen tisch gearbeitet kann ich dafür was eintragen", "Ich war 2024 angestellt und habe im Keller an einem normalen Tisch gearbeitet. Kann ich dafür steuerlich etwas eintragen?"),
)


FOLGEFAELLE = (
    ("folge-erdgeschoss", "Bei uns gab es einen Wasserschaden im Haus.", "Welche Einheit war betroffen?", "unsere wohnung unten", "Der Wasserschaden betraf unsere Wohnung im Erdgeschoss."),
    ("folge-versicherung-auch", "Kann ich meinen Anteil an den Reparaturkosten steuerlich angeben?", "Hast du die Rechnung selbst bezahlt?", "gilt das auch wenn die gebäudeversicherung das meiste übernommen hat", "Gilt das auch, wenn die Gebäudeversicherung den größten Teil der Kosten übernommen hat?"),
    ("folge-jahr-korrektur", "Dann bereiten wir die Erklärung 2024 vor.", "Ist das richtige Steuerjahr 2024?", "nee ich meinte 2023", "Ich meinte nicht 2024, sondern das Steuerjahr 2023."),
    ("folge-vermietet", "Du besitzt die Wohnung.", "Nutzt du sie selbst?", "gehört mir ist aber vermietet", "Die Wohnung gehört mir, ist aber vermietet."),
    ("folge-mieter-unten", "Im Dreifamilienhaus wurde ein Rohr repariert.", "Welcher Gebäudeteil war betroffen?", "bei den mietern unten", "Die vermietete Wohnung im Erdgeschoss war betroffen."),
    ("folge-nur-konto", "Für Handwerkerkosten benötigst du einen Nachweis.", "Hast du Rechnung und Überweisungsbeleg?", "nur den kontoauszug keine rechnung", "Ich habe nur den Kontoauszug und keine Rechnung."),
    ("folge-entfernung", "Du möchtest deinen Arbeitsweg angeben.", "Wie lang ist der einfache Weg?", "17 kilometer einfach", "Mein einfacher Arbeitsweg beträgt 17 Kilometer."),
    ("folge-kostenanteile", "Ein Teil der Reparatur wurde erstattet.", "Was hat die Versicherung übernommen?", "material war versichert arbeit hab ich gezahlt", "Die Versicherung hat die Materialkosten übernommen. Die Arbeitskosten habe ich selbst bezahlt."),
)


VALIDIERUNG = (
    ("val-abwasser", "die abwasserleitung im vermieteten laden war 2024 kaputt versicherung hat 600 euro gezahlt", "Die Abwasserleitung im vermieteten Laden war 2024 beschädigt. Die Versicherung hat 600 Euro übernommen."),
    ("val-bescheid", "hab den grundabgabenbescheid 2025 fürs zweifamilienhaus in erlangen bekommen", "Ich habe den Grundabgabenbescheid für mein Zweifamilienhaus in Erlangen für 2025 erhalten."),
    ("val-klasse", "lohnzettel sagt steuerklasse fünf ist das korrekt", "Auf meiner Lohnsteuerbescheinigung steht Steuerklasse V. Ist das korrekt?"),
    ("val-folge-name", "Auf dem Dokument steht ein anderer Name.", "Wessen Dokument ist es?", "das ist von meiner frau", "Das Dokument gehört meiner Frau."),
    ("val-folge-anteil", "Die Versicherung hat einen Teil erstattet.", "Wie viel hast du selbst bezahlt?", "noch 350 euro", "Ich habe noch 350 Euro selbst bezahlt."),
    ("val-folge-nutzung", "Das Haus gehört dir.", "Bewohnst du es selbst?", "nein komplett vermietet", "Nein, das Haus ist vollständig vermietet."),
)


PRAEFIXE = ("", "also ", "kurz gesagt ", "bei mir ")


def varianten(text: str) -> list[str]:
    ausgabe = []
    for prefix in PRAEFIXE:
        basis = prefix + text
        ausgabe.extend(
            (
                basis,
                basis.lower().replace("?", ""),
                basis.replace("ich habe", "ich hab").replace("nicht", "nich"),
            )
        )
    return list(dict.fromkeys(" ".join(x.split()) for x in ausgabe))


def eintrag(eid: str, messages: list[dict], split: str, nummer: int) -> dict:
    return {
        "id": f"hard-{eid}-{split}-{nummer:02d}",
        "thema": "Detailtreue und echter Gespraechsbezug",
        "messages": [{"role": "system", "content": SYSTEM}, *messages],
        "metadaten": {"aufgabe": "hardcase_kanonisierung", "split": split, "synthetisch": True},
    }


def erstellen() -> dict:
    train = []
    validation = []
    for eid, roh, ziel in EINZELFAELLE:
        for nummer, text in enumerate(varianten(roh), 1):
            train.append(eintrag(eid, [{"role": "user", "content": text}, {"role": "assistant", "content": ziel}], "train", nummer))
    for eid, vorher, frage, antwort, ziel in FOLGEFAELLE:
        for nummer, text in enumerate(varianten(antwort), 1):
            train.append(eintrag(eid, [{"role": "user", "content": vorher}, {"role": "assistant", "content": frage}, {"role": "user", "content": text}, {"role": "assistant", "content": ziel}], "train", nummer))
    for eid, *werte in VALIDIERUNG:
        if len(werte) == 2:
            roh, ziel = werte
            messages = [{"role": "user", "content": roh}, {"role": "assistant", "content": ziel}]
        else:
            vorher, frage, roh, ziel = werte
            messages = [{"role": "user", "content": vorher}, {"role": "assistant", "content": frage}, {"role": "user", "content": roh}, {"role": "assistant", "content": ziel}]
        validation.append(eintrag(eid, messages, "validation", 1))
    random.Random(20260827).shuffle(train)
    for name, daten in (("hardcases_train.jsonl", train), ("hardcases_validation.jsonl", validation)):
        with (ZIEL / name).open("w", encoding="utf-8", newline="\n") as datei:
            for item in daten:
                datei.write(json.dumps(item, ensure_ascii=False) + "\n")
    return {"train": len(train), "validation": len(validation)}


if __name__ == "__main__":
    print(json.dumps(erstellen(), ensure_ascii=False, indent=2))
