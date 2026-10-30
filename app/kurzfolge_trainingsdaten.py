"""Erzeugt gezielte Kurzfolge-Dialoge fuer Pilot 07."""

from __future__ import annotations

import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZIEL = ROOT / "testDaten" / "umgangssprache_steuer_training"
SYSTEM = (
    "Formuliere nur die aktuelle Nutzerangabe oder Nutzerfrage in klarem "
    "Standarddeutsch und nutze die vorherige Rueckfrage. Wiederhole die "
    "Rueckfrage nicht. Eine kurze Antwort benennt die erfragte Tatsache. "
    "Beginnt die aktuelle Frage sinngemaess mit 'wenn ... auch', formuliere "
    "'Gilt das auch, wenn ...?'; frage nicht, ob die Bedingung eingetreten ist. "
    "Bewahre alle Details und erfinde nichts. Beantworte die Steuerfrage nicht."
)


FAELLE = (
    ("wohnung-heizung", "Welche Wohnung war von der Heizungsreparatur betroffen?", "Bitte nenne die betroffene Wohnung.", "meine im ersten stock", "Die Heizungsreparatur betraf meine Wohnung im ersten Stock."),
    ("raum-wasser", "Welcher Raum hatte den Wasserschaden?", "Bitte nenne den betroffenen Raum.", "mein bad oben", "Der Wasserschaden betraf mein Badezimmer im Obergeschoss."),
    ("einheit-defekt", "Welche Einheit hatte den Defekt?", "Bitte nenne die betroffene Einheit.", "unsere obere wohnung", "Der Defekt betraf unsere obere Wohnung."),
    ("mieter-dach", "Welcher Gebäudeteil brauchte die Dachreparatur?", "Bitte nenne den betroffenen Gebäudeteil.", "die wohnung von den mietern", "Die Dachreparatur betraf die vermietete Wohnung."),
    ("versicherung-hausrat", "Kann ich die Reparatur steuerlich berücksichtigen?", "Hast du die Rechnung selbst getragen?", "wenn die hausratversicherung bezahlt hat auch", "Gilt das auch, wenn die Hausratversicherung die Kosten übernommen hat?"),
    ("versicherung-teil", "Kann ich meinen Eigenanteil angeben?", "Wie hoch war dein selbst getragener Betrag?", "auch wenn die versicherung vorher fast alles gezahlt hat", "Gilt das auch, wenn die Versicherung zuvor fast alle Kosten übernommen hat?"),
    ("versicherung-gebaeude", "Sind die Handwerkerkosten steuerlich relevant?", "Wurden die Arbeiten an deinem Haus ausgeführt?", "wenns über die gebäudeversicherung ging auch", "Gilt das auch, wenn die Kosten über die Gebäudeversicherung abgewickelt wurden?"),
    ("erstattung-arbeit", "Kann ich die Arbeitskosten ansetzen?", "Hast du sie unbar bezahlt?", "auch wenn material von versicherung erstattet wurde", "Gilt das auch, wenn die Versicherung die Materialkosten erstattet hat?"),
)


VALIDIERUNG = (
    ("val-keller", "Welcher Teil des Hauses wurde saniert?", "Bitte nenne den Gebäudeteil.", "unser keller", "Die Sanierung betraf unseren Keller."),
    ("val-garage", "Wo entstand der Schaden?", "Bitte nenne den Ort des Schadens.", "meine garage", "Der Schaden entstand in meiner Garage."),
    ("val-rechtsschutz", "Kann ich die Beratungskosten angeben?", "Hast du sie selbst bezahlt?", "wenn rechtsschutz was übernommen hat auch", "Gilt das auch, wenn die Rechtsschutzversicherung einen Teil übernommen hat?"),
    ("val-zuschuss", "Kann ich die Modernisierungskosten absetzen?", "Gab es eine Förderung?", "auch wenn ich einen zuschuss gekriegt hab", "Gilt das auch, wenn ich einen Zuschuss erhalten habe?"),
)


VARIANTEN = ("{}", "also {}", "{} bitte eindeutig", "kurz {}", "{} genau", "nee {}", "ich meine {}", "bei mir {}")


def erstellen() -> dict:
    train = []
    for eid, vorher, frage, antwort, ziel in FAELLE:
        for nummer, muster in enumerate(VARIANTEN, 1):
            aktuell = muster.format(antwort)
            train.append(
                {
                    "id": f"kurzfolge-{eid}-{nummer:02d}",
                    "thema": "Kurzantwort und zusaetzliche Bedingung",
                    "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": vorher},
                        {"role": "assistant", "content": frage},
                        {"role": "user", "content": aktuell},
                        {"role": "assistant", "content": ziel},
                    ],
                    "metadaten": {"aufgabe": "kurzfolge_kanonisierung", "split": "train", "synthetisch": True},
                }
            )
    validation = []
    for nummer, (eid, vorher, frage, antwort, ziel) in enumerate(VALIDIERUNG, 1):
        validation.append(
            {
                "id": f"kurzfolge-{eid}-validation-{nummer:02d}",
                "thema": "Kurzantwort und zusaetzliche Bedingung",
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": vorher},
                    {"role": "assistant", "content": frage},
                    {"role": "user", "content": antwort},
                    {"role": "assistant", "content": ziel},
                ],
                "metadaten": {"aufgabe": "kurzfolge_kanonisierung", "split": "validation", "synthetisch": True},
            }
        )
    random.Random(20260827).shuffle(train)
    for name, daten in (("kurzfolge_train.jsonl", train), ("kurzfolge_validation.jsonl", validation)):
        with (ZIEL / name).open("w", encoding="utf-8", newline="\n") as datei:
            for item in daten:
                datei.write(json.dumps(item, ensure_ascii=False) + "\n")
    return {"train": len(train), "validation": len(validation)}


if __name__ == "__main__":
    print(json.dumps(erstellen(), ensure_ascii=False, indent=2))
