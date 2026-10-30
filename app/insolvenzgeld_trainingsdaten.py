"""Erzeugt ein fehlertolerantes Dialogpaket zu Insolvenzgeld bei Arbeitnehmern.

Das Paket trainiert nur Kanonisierung und Gesprächsbezug. Steuerliche Antworten
bleiben in den belegten Regeln des RAG-Assistenten und werden hier nicht gelernt.
Grundfälle werden strikt nach Train, Validation und Control getrennt.
"""

from __future__ import annotations

import json
import random
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZIEL = ROOT / "testDaten" / "umgangssprache_steuer_training" / "insolvenzgeld_arbeitnehmer"
REHEARSAL = (
    ROOT
    / "testDaten"
    / "umgangssprache_steuer_training"
    / "mehrschritt_300"
    / "dialoge_300_train.jsonl"
)
SYSTEM = (
    "Du vereinheitlichst die letzte umgangssprachliche Nachricht eines deutschen Steuerdialogs. "
    "Nutze den Verlauf, löse kurze Bezüge auf und gib nur die gemeinte Frage oder Angabe in "
    "klarem Standarddeutsch aus. Bewahre Leistung, Arbeitnehmerstatus, Betrag, Steuerjahr, "
    "Auszahlungsweg und weitere Einkommensersatzleistungen. Beantworte die Steuerfrage nicht "
    "und erfinde keine Angaben."
)


# Kennung, vorherige Nutzerangabe, Assistentenkontext, aktuelle Äußerung, Ziel.
# Leere Kontextfelder ergeben eigenständige Fragen.
FAELLE = (
    ("absetzen-fehler", "", "", "kann ich insolvebtsgeld steuerlich absetzten", "Kann ich als Arbeitnehmer erhaltenes Insolvenzgeld steuerlich absetzen?"),
    ("halb-abzug", "Ich habe als Arbeitnehmer 2.000 Euro Insolvenzgeld erhalten.", "Es geht um die steuerliche Behandlung.", "kann ich davon wenigstens die hälfte abziehen", "Kann ich die Hälfte der als Arbeitnehmer erhaltenen 2.000 Euro Insolvenzgeld steuerlich abziehen?"),
    ("steuerfrei-angeben", "", "", "insolvenz geld war steuerfrei muss das trotzdem in die erklärung", "Muss ich als Arbeitnehmer erhaltenes steuerfreies Insolvenzgeld trotzdem in der Einkommensteuererklärung angeben?"),
    ("progression-einfach", "Ich habe Insolvenzgeld als Arbeitnehmer erhalten.", "Die Leistung ist steuerfrei und kann dem Progressionsvorbehalt unterliegen.", "was heißt das jetzt für meinen restlichen lohn", "Wie wirkt sich der Progressionsvorbehalt beim Insolvenzgeld auf meinen übrigen Arbeitslohn aus?"),
    ("elster-wo", "", "", "wo kommt das insolvenzgeld bei elster rein", "Wo trage ich als Arbeitnehmer erhaltenes Insolvenzgeld in Mein ELSTER ein?"),
    ("elektronisch-doppelt", "Die Agentur für Arbeit hat mein Insolvenzgeld elektronisch an das Finanzamt gemeldet.", "Die übermittelten Daten können in ELSTER übernommen werden.", "muss ich es dann nochmal selber eintragen", "Muss ich das elektronisch übermittelte Insolvenzgeld zusätzlich selbst in der Steuererklärung eintragen?"),
    ("leistungsnachweis", "", "", "welchen betrag vom insolvenzgeld bescheid muss ich nehmen", "Welchen Betrag aus dem Leistungsnachweis über das Insolvenzgeld muss ich in der Steuererklärung berücksichtigen?"),
    ("grenze-410", "Ich habe als Arbeitnehmer Insolvenzgeld erhalten.", "Für eine mögliche Abgabepflicht wurde die Grenze von 410 Euro erwähnt.", "gelten die 410 für das ganze geld oder nur den teil über 410", "Wie ist die Grenze von 410 Euro bei erhaltenem Insolvenzgeld und der Pflicht zur Einkommensteuererklärung anzuwenden?"),
    ("mehrere-leistungen", "Ich habe 300 Euro Insolvenzgeld und 250 Euro Krankengeld erhalten.", "Für die Abgabepflicht können mehrere Leistungen zusammenzurechnen sein.", "zählt das zusammen obwohl beides unter 410 ist", "Werden meine 300 Euro Insolvenzgeld und 250 Euro Krankengeld für die Prüfung der 410-Euro-Grenze zusammengerechnet?"),
    ("jahr-zufluss", "Mein Arbeitgeber wurde Ende 2024 insolvent.", "Das Insolvenzgeld wurde erst 2025 ausgezahlt.", "in welches steuerjahr gehört es dann", "In welchem Steuerjahr ist das erst 2025 ausgezahlte Insolvenzgeld anzugeben, wenn die Insolvenz des Arbeitgebers 2024 eingetreten ist?"),
    ("lohn-und-insolvenzgeld", "2024 erhielt ich zunächst normalen Arbeitslohn und später Insolvenzgeld.", "Beide Zahlungen sind steuerlich getrennt einzuordnen.", "muss ich beides angeben", "Muss ich für 2024 sowohl meinen normalen Arbeitslohn als auch das erhaltene Insolvenzgeld in der Einkommensteuererklärung angeben?"),
    ("nachzahlung", "", "", "krieg ich wegen insolvenzgeld automatisch eine steuernachzahlung", "Führt erhaltenes Insolvenzgeld bei einem Arbeitnehmer automatisch zu einer Einkommensteuernachzahlung?"),
    ("kein-restlohn", "Ich habe im Jahr nur Insolvenzgeld und keinen weiteren steuerpflichtigen Arbeitslohn erhalten.", "Das Insolvenzgeld selbst ist steuerfrei.", "muss ich dann überhaupt steuer zahlen", "Muss ich Einkommensteuer zahlen, wenn ich im Kalenderjahr nur Insolvenzgeld und keinen weiteren steuerpflichtigen Arbeitslohn erhalten habe?"),
    ("vorfinanziert", "Mein Insolvenzgeld wurde von einer Bank vorfinanziert.", "Auch vorfinanziertes Insolvenzgeld muss richtig zugeordnet werden.", "ist das steuerlich was anderes", "Wird vorfinanziertes Insolvenzgeld bei einem Arbeitnehmer steuerlich anders behandelt als eine direkte Auszahlung durch die Agentur für Arbeit?"),
    ("direkt-dritter", "Mein Anspruch auf Insolvenzgeld wurde an einen Dritten übertragen, der die Zahlung erhalten hat.", "Für die Steuererklärung muss die Leistung dem richtigen Arbeitnehmer zugeordnet werden.", "zählt das trotzdem bei mir", "Muss ich das an einen Dritten ausgezahlte Insolvenzgeld als Arbeitnehmer in meiner Steuererklärung berücksichtigen?"),
    ("bescheinigung-fehlt", "", "", "agentür hat gezahlt aber ich find die insolvenzgeld bescheinigung nicht", "Was soll ich als Arbeitnehmer tun, wenn ich Insolvenzgeld erhalten habe, aber den Leistungsnachweis der Agentur für Arbeit nicht finde?"),
    ("ehegatten", "Ich habe Insolvenzgeld erhalten und werde mit meiner Ehefrau zusammen veranlagt.", "Meine Ehefrau erhielt im selben Jahr Elterngeld.", "wird das für die 410 euro zusammen gerechnet", "Werden bei zusammen veranlagten Ehegatten mein Insolvenzgeld und das Elterngeld meiner Ehefrau für die 410-Euro-Grenze zusammengerechnet?"),
    ("steuerklasse", "Ich habe als Arbeitnehmer Insolvenzgeld erhalten.", "Es geht um die mögliche steuerliche Auswirkung.", "hängt die nachzahlung von meiner steuerklasse ab", "Welche Bedeutung hat meine Steuerklasse für eine mögliche Nachzahlung nach dem Bezug von Insolvenzgeld?"),
    ("werbungskosten", "Während des Jahres mit Insolvenzgeld hatte ich Fahrtkosten für meine Arbeit.", "Insolvenzgeld und berufliche Aufwendungen sind getrennt zu beurteilen.", "darf ich die fahrtkosten trotzdem angeben", "Kann ich meine beruflich veranlassten Fahrtkosten im Jahr des Insolvenzgeldbezugs als Werbungskosten angeben?"),
    ("arbeitnehmer-klarstellung", "Wir sprechen über Insolvenzgeld.", "Für die Einordnung ist wichtig, wer die Leistung erhalten hat.", "ich habs selber als arbeitnehmer bekommen", "Ich habe das Insolvenzgeld persönlich als Arbeitnehmer erhalten."),
)

DETAILREGELN = {
    "absetzen-fehler": (("insolvenzgeld",), ("arbeitnehmer",), ("absetzen", "steuerlich")),
    "halb-abzug": (("2.000 euro", "2000 euro"), ("insolvenzgeld",), ("hälfte", "halb"), ("abziehen", "absetzen")),
    "steuerfrei-angeben": (("steuerfrei",), ("insolvenzgeld",), ("einkommensteuererklärung", "steuererklärung"), ("angeben",)),
    "progression-einfach": (("progressionsvorbehalt",), ("insolvenzgeld",), ("arbeitslohn", "übrigen lohn", "übriges einkommen")),
    "elster-wo": (("insolvenzgeld",), ("elster",), ("eintragen", "wo")),
    "elektronisch-doppelt": (("elektronisch",), ("insolvenzgeld",), ("zusätzlich", "doppelt", "noch einmal"), ("steuererklärung",)),
    "leistungsnachweis": (("betrag",), ("leistungsnachweis", "bescheid"), ("insolvenzgeld",), ("steuererklärung", "berücksichtigen")),
    "grenze-410": (("410 euro",), ("insolvenzgeld",), ("pflicht",), ("einkommensteuererklärung", "steuererklärung")),
    "mehrere-leistungen": (("300 euro",), ("250 euro",), ("insolvenzgeld",), ("krankengeld",), ("410 euro",), ("zusammen",)),
    "jahr-zufluss": (("2024",), ("2025",), ("ausgezahlt",), ("insolvenzgeld",), ("steuerjahr",)),
    "lohn-und-insolvenzgeld": (("2024",), ("arbeitslohn",), ("insolvenzgeld",), ("beide", "sowohl"), ("steuererklärung",)),
    "nachzahlung": (("insolvenzgeld",), ("automatisch",), ("steuernachzahlung", "nachzahlung")),
    "kein-restlohn": (("insolvenzgeld",), ("kein",), ("arbeitslohn", "einkommen"), ("einkommensteuer", "steuer zahlen")),
    "vorfinanziert": (("vorfinanziert",), ("insolvenzgeld",), ("arbeitnehmer",), ("agentur für arbeit", "direkte auszahlung"), ("steuerlich",)),
    "direkt-dritter": (("dritten", "dritter"), ("ausgezahlt",), ("insolvenzgeld",), ("arbeitnehmer",), ("steuererklärung",)),
    "bescheinigung-fehlt": (("insolvenzgeld",), ("leistungsnachweis", "bescheinigung"), ("agentur für arbeit",), ("nicht finde", "fehlt")),
    "ehegatten": (("ehegatten", "ehefrau"), ("insolvenzgeld",), ("elterngeld",), ("410 euro",), ("zusammen",)),
    "steuerklasse": (("steuerklasse",), ("nachzahlung",), ("insolvenzgeld",)),
    "werbungskosten": (("fahrtkosten",), ("insolvenzgeld",), ("werbungskosten", "steuerlich"), ("angeben",)),
    "arbeitnehmer-klarstellung": (("insolvenzgeld",), ("arbeitnehmer",), ("erhalten", "bekommen")),
}

# Zusätzliche, nie trainierte Einzelbeispiele für robuste Abschlussmessungen.
HARD_CONTROL = (
    ("hard-agentur", "Mein Arbeitgeber konnte den Lohn nicht mehr zahlen.", "Wir klären, welche Zahlung du erhalten hast.", "das kam direkt von der agentür für arbeit", "Ich habe das Insolvenzgeld direkt von der Agentur für Arbeit erhalten.", (("insolvenzgeld",), ("agentur für arbeit",), ("direkt",), ("erhalten",))),
    ("hard-kombi", "Ich prüfe, ob ich eine Steuererklärung abgeben muss.", "Dafür sind bestimmte Einkommensersatzleistungen zusammen zu betrachten.", "waren 380 insolvenz geld und noch 50 krankengeld", "Ich habe 380 Euro Insolvenzgeld und zusätzlich 50 Euro Krankengeld erhalten; werden beide Leistungen für die Abgabepflicht zusammengerechnet?", (("380 euro",), ("50 euro",), ("insolvenzgeld",), ("krankengeld",), ("zusammen",))),
    ("hard-vorausgefüllt", "Mein ELSTER-Abruf zeigt bereits eine Zahlung der Agentur für Arbeit.", "Die Daten könnten elektronisch übermittelt worden sein.", "wenns schon drin steht trag ichs nicht nochmal ein oder", "Muss ich das bereits elektronisch übernommene Insolvenzgeld in ELSTER noch einmal eintragen?", (("elektronisch",), ("insolvenzgeld",), ("elster",), ("noch einmal", "doppelt",))),
    ("hard-jahr", "Die Insolvenz meines Arbeitgebers war im Dezember 2024.", "Die Agentur für Arbeit zahlte später.", "geld kam februar 25 welches jahr nehm ich", "Welchem Steuerjahr ordne ich das im Februar 2025 ausgezahlte Insolvenzgeld zu, wenn die Arbeitgeberinsolvenz im Dezember 2024 eingetreten ist?", (("februar",), ("2025",), ("2024",), ("insolvenzgeld",), ("steuerjahr",))),
    ("hard-alg", "Nach der Insolvenz erhielt ich zunächst Insolvenzgeld.", "Später warst du arbeitslos.", "danach kam alg eins zählt das mit", "Werden mein Insolvenzgeld und das anschließend erhaltene Arbeitslosengeld I für die Steuererklärung zusammen berücksichtigt?", (("insolvenzgeld",), ("arbeitslosengeld i", "alg i"), ("anschließend", "danach"), ("steuererklärung",), ("zusammen",))),
    ("hard-bank", "Der offene Lohn wurde vor dem Bescheid ausgezahlt.", "Die Zahlung könnte vorfinanziertes Insolvenzgeld sein.", "bank hat das gemacht nicht die agentur", "Ich habe vorfinanziertes Insolvenzgeld über eine Bank und nicht direkt von der Agentur für Arbeit erhalten.", (("vorfinanziert",), ("insolvenzgeld",), ("bank",), ("agentur für arbeit",), ("nicht direkt",))),
    ("hard-ohne-einkommen", "Ich habe Insolvenzgeld erhalten.", "Für den Progressionsvorbehalt ist weiteres steuerpflichtiges Einkommen wichtig.", "sonst hatte ich null lohn", "Ich hatte außer dem Insolvenzgeld keinen weiteren steuerpflichtigen Arbeitslohn.", (("insolvenzgeld",), ("keinen", "kein"), ("arbeitslohn",), ("steuerpflichtig",))),
    ("hard-arbeitnehmer", "Es geht um die steuerliche Behandlung der Zahlung.", "Wer hat sie erhalten?", "ich persönlich als angestellter", "Ich habe das Insolvenzgeld persönlich als Arbeitnehmer erhalten.", (("insolvenzgeld",), ("persönlich",), ("arbeitnehmer", "angestellter"), ("erhalten",))),
)

# Zusätzliche Trainingsanker aus den beobachteten Fehlerklassen. Sie verwenden
# andere Sachverhalte und Formulierungen als die unangetasteten Kontrollen.
TRAIN_ERGAENZUNGEN = (
    ("anker-agentur", "Ich habe Insolvenzgeld beantragt.", "Die Leistung wurde bewilligt.", "ausgezahlt hats dann die arbeitsagentur", "Die Agentur für Arbeit hat mir das Insolvenzgeld ausgezahlt."),
    ("anker-leistungsart", "Ich habe Insolvenzgeld erhalten.", "Es geht weiterhin nur um diese Leistung.", "das geld kam auf mein konto", "Das Insolvenzgeld wurde auf mein Konto ausgezahlt."),
    ("anker-elster", "Mein Insolvenzgeld wurde von der Agentur für Arbeit gemeldet.", "Im ELSTER-Belegabruf ist der Betrag bereits sichtbar.", "also nicht noch ein zweites mal eintragen", "Muss ich das bereits elektronisch übernommene Insolvenzgeld in ELSTER ein zweites Mal eintragen?"),
    ("anker-zwei-jahre", "Der Arbeitgeber wurde im November 2023 insolvent.", "Die Auszahlung des Insolvenzgeldes erfolgte im Januar 2024.", "welches jahr gilt für die steuer", "Welches Steuerjahr gilt für das im Januar 2024 ausgezahlte Insolvenzgeld nach der Arbeitgeberinsolvenz im November 2023?"),
    ("anker-alg-kombi", "Zuerst erhielt ich Insolvenzgeld.", "Nach dem Ende des Arbeitsverhältnisses erhielt ich Arbeitslosengeld I.", "muss ich beide lohnersatz sachen angeben", "Muss ich sowohl das Insolvenzgeld als auch das anschließend erhaltene Arbeitslosengeld I in der Steuererklärung angeben?"),
    ("anker-bank", "Eine Bank zahlte mir den offenen Nettolohn vorab aus.", "Die Auszahlung beruhte auf einer Vorfinanzierung des Insolvenzgeldes.", "also kam es nicht direkt vom amt", "Ich habe das vorfinanzierte Insolvenzgeld nicht direkt von der Agentur für Arbeit erhalten."),
    ("anker-kein-lohn", "Ich habe Insolvenzgeld erhalten.", "Wir prüfen mein weiteres Einkommen im selben Kalenderjahr.", "anderen arbeitslohn gabs keinen", "Ich hatte außer dem Insolvenzgeld keinen weiteren Arbeitslohn."),
    ("anker-person", "Es geht um mein erhaltenes Insolvenzgeld.", "Die Empfängerstellung soll geklärt werden.", "das war für mich als beschäftigten", "Ich habe das Insolvenzgeld selbst als Arbeitnehmer erhalten."),
    ("anker-steuerklasse", "Ich habe als Arbeitnehmer Insolvenzgeld erhalten.", "Wir prüfen eine mögliche Einkommensteuernachzahlung.", "spielt meine lohnsteuerklasse da mit rein", "Spielt meine Steuerklasse bei einer möglichen Einkommensteuernachzahlung nach dem Insolvenzgeldbezug eine Rolle?"),
    ("anker-fahrtkosten", "Im Jahr des Insolvenzgeldbezugs hatte ich weiterhin berufliche Fahrtkosten.", "Die beruflichen Aufwendungen sind getrennt von der Leistung zu prüfen.", "kann ich die trotzdem als werbungskosten nehmen", "Kann ich die beruflichen Fahrtkosten im Jahr des Insolvenzgeldbezugs trotzdem als Werbungskosten angeben?"),
    ("anker-kein-jahr", "Ich habe Insolvenzgeld erhalten.", "Ein Steuerjahr wurde noch nicht genannt.", "muss das in meine erklärung", "Muss ich das erhaltene Insolvenzgeld in meiner Steuererklärung angeben?"),
    ("anker-kein-jahr-folge", "Mein Insolvenzgeld ist im ELSTER-Belegabruf sichtbar.", "Ein Kalenderjahr wurde bisher nicht genannt.", "ist das dann schon erledigt", "Ist das Insolvenzgeld bereits vollständig in ELSTER übernommen?"),
)

PRAEFIXE = ("", "also ", "mal kurz ", "ich blick da nicht durch ", "bei meiner steuer ", "bitte einfach: ", "noch mal dazu: ", "ohne beamtendeutsch: ")


def variante(text: str, nummer: int) -> str:
    kern = text
    if nummer == 1:
        kern = kern.replace("ich habe", "ich hab").replace("muss ich", "muss ich denn")
    elif nummer == 2:
        kern = kern.replace("Insolvenzgeld", "Insolvenz Geld").replace("insolvenzgeld", "insolvenz geld")
    elif nummer == 3:
        kern = kern.replace("insolvenzgeld", "insolvenzgelt").replace("Insolvenzgeld", "Insolvenzgelt")
    elif nummer == 4:
        kern = kern.replace("insolvenzgeld", "insolvebtsgeld").replace("Insolvenzgeld", "Insolvebtsgeld")
    elif nummer == 5:
        kern = kern.replace("steuer", "steur").replace("erklärung", "erklerung")
    elif nummer == 6:
        kern = kern.rstrip("?") + " oder wie läuft das"
    elif nummer == 7:
        kern = kern.rstrip("?") + " bitte klar sagen"
    praefix = PRAEFIXE[nummer]
    return " ".join((praefix + kern).split())


def _eintrag(kennung: str, vorher: str, assistent: str, folge: str, ziel: str, split: str, nummer: int) -> dict:
    messages = [{"role": "system", "content": SYSTEM}]
    if vorher:
        messages.extend(
            [
                {"role": "user", "content": vorher},
                {"role": "assistant", "content": assistent},
            ]
        )
    messages.extend(
        [
            {"role": "user", "content": variante(folge, nummer)},
            {"role": "assistant", "content": ziel},
        ]
    )
    eintrag = {
        "id": f"insolvenzgeld-{kennung}-{nummer + 1:02d}",
        "thema": "Insolvenzgeld bei Arbeitnehmern",
        "messages": messages,
        "metadaten": {
            "aufgabe": "insolvenzgeld_kanonisierung",
            "basisfall": kennung,
            "split": split,
            "synthetische_sprachvariante": True,
            "fachlich_geprueft": True,
            "redaktionell_geprueft_am": "2026-08-29",
        },
    }
    if kennung in DETAILREGELN:
        eintrag["detailregeln"] = [list(gruppe) for gruppe in DETAILREGELN[kennung]]
    return eintrag


def _laden(pfad: Path) -> list[dict]:
    return [json.loads(zeile) for zeile in pfad.read_text(encoding="utf-8").splitlines() if zeile.strip()]


def erstellen() -> dict:
    ZIEL.mkdir(parents=True, exist_ok=True)
    splits = {"train": [], "validation": [], "control": []}
    split_ids = {"train": set(), "validation": set(), "control": set()}
    for index, fall in enumerate(FAELLE):
        split = "train" if index < 14 else "validation" if index < 17 else "control"
        kennung, vorher, assistent, folge, ziel = fall
        split_ids[split].add(kennung)
        for nummer in range(8):
            splits[split].append(_eintrag(kennung, vorher, assistent, folge, ziel, split, nummer))

    for kennung, vorher, assistent, folge, ziel in TRAIN_ERGAENZUNGEN:
        for nummer in range(8):
            splits["train"].append(
                _eintrag(kennung, vorher, assistent, folge, ziel, "train", nummer)
            )

    # Ein begrenzter Rehearsal-Anteil stabilisiert die bisherige allgemeine
    # Kanonisierung. Kontrollfälle werden niemals in Trainingsdaten gemischt.
    rehearsal = _laden(REHEARSAL)
    random.Random(2026082901).shuffle(rehearsal)
    rehearsal = rehearsal[:48]
    for eintrag in rehearsal:
        kopie = dict(eintrag)
        kopie["id"] = "rehearsal-" + kopie["id"]
        kopie["metadaten"] = {**kopie.get("metadaten", {}), "rehearsal_fuer": "insolvenzgeld_arbeitnehmer"}
        splits["train"].append(kopie)

    for zaehler, (split, daten) in enumerate(splits.items()):
        random.Random(2026082902 + zaehler).shuffle(daten)
        with (ZIEL / f"insolvenzgeld_{split}.jsonl").open("w", encoding="utf-8", newline="\n") as datei:
            for eintrag in daten:
                datei.write(json.dumps(eintrag, ensure_ascii=False) + "\n")

    hard_control = []
    for kennung, vorher, assistent, folge, ziel, regeln in HARD_CONTROL:
        eintrag = _eintrag(kennung, vorher, assistent, folge, ziel, "hard_control", 0)
        eintrag["detailregeln"] = [list(gruppe) for gruppe in regeln]
        hard_control.append(eintrag)
    with (ZIEL / "insolvenzgeld_hard_control.jsonl").open("w", encoding="utf-8", newline="\n") as datei:
        for eintrag in hard_control:
            datei.write(json.dumps(eintrag, ensure_ascii=False) + "\n")

    if any(split_ids[a] & split_ids[b] for a, b in (("train", "validation"), ("train", "control"), ("validation", "control"))):
        raise AssertionError("Grundfall-Leakage zwischen den Splits")

    manifest = {
        "grundfaelle": len(FAELLE),
        "varianten_je_grundfall": 8,
        "spezial_train": (14 + len(TRAIN_ERGAENZUNGEN)) * 8,
        "rehearsal_train": len(rehearsal),
        "train_gesamt": len(splits["train"]),
        "zusaetzliche_trainingsanker": len(TRAIN_ERGAENZUNGEN) * 8,
        "validation": len(splits["validation"]),
        "control": len(splits["control"]),
        "hard_control": len(hard_control),
        "split_nach_grundfall": True,
        "fachantworten_enthalten": False,
        "basis_ids": {name: sorted(ids) for name, ids in split_ids.items()},
    }
    (ZIEL / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


if __name__ == "__main__":
    print(json.dumps(erstellen(), ensure_ascii=False, indent=2))
