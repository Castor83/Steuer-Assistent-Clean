"""Erzeugt detailtreue Praxisdaten fuer Umgangssprache und Folgeantworten."""

from __future__ import annotations

import json
import random
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ZIEL = ROOT / "testDaten" / "umgangssprache_steuer_training"
SYSTEM = (
    "Du vereinheitlichst umgangssprachliche deutsche Steuerfragen. Formuliere "
    "nur die gemeinte Frage oder Angabe in klarem Standarddeutsch. Bewahre alle "
    "genannten Personen, Nutzungsarten, Kostenarten und Jahreszahlen. Beantworte "
    "die Steuerfrage nicht und ergaenze keine Tatsachen. Nutze bei kurzen "
    "Folgeantworten den vorherigen Gespraechsverlauf."
)


EINZELFAELLE = (
    ("rohr-eigenanteil", "bei uns ist ein wasserrohr geplatzt versicherung zahlt fast alles kann ich meinen eigenanteil absetzen", "Bei uns ist ein Wasserrohr geplatzt. Die Versicherung übernimmt fast alle Kosten. Kann ich meinen Eigenanteil steuerlich absetzen?"),
    ("rohr-vermietet", "in der vermieteten wohnung war rohrbruch ich hab die reparatur bezahlt wie geb ich das an", "In der vermieteten Wohnung gab es einen Rohrbruch. Ich habe die Reparatur bezahlt. Wie gebe ich die Kosten steuerlich an?"),
    ("leitung-gemeinsam", "die kaputte leitung ist für alle drei wohnungen wie teile ich die kosten auf", "Die beschädigte Leitung versorgt alle drei Wohnungen. Wie teile ich die Kosten steuerlich auf?"),
    ("versicherung-material", "gebäudeversicherung übernimmt das material aber den handwerker zahl ich", "Die Gebäudeversicherung übernimmt die Materialkosten, aber die Handwerkerkosten bezahle ich selbst. Wie wird das steuerlich berücksichtigt?"),
    ("versicherung-alles", "wenn die versicherung die komplette rechnung bezahlt kann ich trotzdem was ansetzen", "Kann ich Kosten steuerlich ansetzen, wenn die Versicherung die vollständige Rechnung bezahlt?"),
    ("selbstbehalt", "ich musste trotz versicherung 800 euro selbst zahlen zählt das", "Ich musste trotz der Versicherung 800 Euro selbst bezahlen. Kann ich diesen Selbstbehalt steuerlich berücksichtigen?"),
    ("rechnung-bar", "handwerkerrechnung hab ich aber bar bezahlt geht das trotzdem", "Ich habe eine Handwerkerrechnung, sie aber bar bezahlt. Kann ich die Kosten trotzdem steuerlich berücksichtigen?"),
    ("rechnung-konto", "rechnung fehlt aber überweisung sieht man auf konto reicht das", "Die Rechnung fehlt, aber die Überweisung ist auf dem Kontoauszug erkennbar. Reicht das als Nachweis?"),
    ("grundsteuer-2023", "grundsteuer fürs selbst bewohnte haus muss die in meine erklärung 2023", "Muss ich die Grundsteuer für mein selbst bewohntes Haus in meiner Steuererklärung 2023 angeben?"),
    ("grundsteuer-2024", "ich hab für 2024 grundsteuer fürs dreifamilienhaus gezahlt zwei wohnungen sind vermietet", "Ich habe 2024 Grundsteuer für mein Dreifamilienhaus gezahlt. Zwei Wohnungen sind vermietet. Wie berücksichtige ich die Grundsteuer steuerlich?"),
    ("grundsteuer-2025", "der neue grundsteuerbescheid für 2025 in bayern ist da was muss ich prüfen", "Der neue Grundsteuerbescheid für 2025 in Bayern ist eingegangen. Was muss ich prüfen?"),
    ("grundabgaben", "auf dem bescheid stehen grundsteuer müll und kanal was davon ist steuer", "Auf dem Bescheid stehen Grundsteuer, Müll- und Kanalgebühren. Welche Beträge sind steuerlich relevant?"),
    ("erlangen", "es geht um mein dreifamilienhaus in erlangen zwei wohnungen vermietet eine selbst genutzt", "Es geht um mein Dreifamilienhaus in Erlangen. Zwei Wohnungen sind vermietet, eine nutze ich selbst."),
    ("reparatur-aufteilen", "dachreparatur war 2024 fürs ganze haus ich wohn da und vermiete auch wie aufteilen", "Die Dachreparatur im Jahr 2024 betraf das gesamte Haus. Ich nutze einen Teil selbst und vermiete den übrigen Teil. Wie teile ich die Kosten steuerlich auf?"),
    ("steuerklasse-i", "auf lohnsteuerbescheinigung 2023 steht klasse 1 aber ich hab geheiratet stimmt das", "Auf meiner Lohnsteuerbescheinigung 2023 steht Steuerklasse I, obwohl ich geheiratet habe. Ist das richtig?"),
    ("steuerklasse-iii", "arbeitgeber hat steuerklasse drei abgerechnet wo seh ich ob das passt", "Mein Arbeitgeber hat mit Steuerklasse III abgerechnet. Wo kann ich prüfen, ob das richtig ist?"),
    ("homeoffice-2023", "2023 hab ich oft daheim gearbeitet aber kein arbeitszimmer kann ich was eintragen", "Ich habe 2023 häufig zu Hause gearbeitet, aber kein Arbeitszimmer. Kann ich dafür etwas steuerlich angeben?"),
    ("homeoffice-2024", "für 2024 war ich 90 tage im homeoffice was brauch ich als nachweis", "Ich habe 2024 an 90 Tagen im Homeoffice gearbeitet. Welchen Nachweis benötige ich?"),
    ("arbeitsweg-2023", "bin 2023 jeden tag 18 kilometer zur arbeit gefahren was kann ich angeben", "Ich bin 2023 an meinen Arbeitstagen jeweils 18 Kilometer zur Arbeit gefahren. Was kann ich steuerlich angeben?"),
    ("arbeitsmittel", "laptop halb beruflich halb privat wie geb ich das bei steuer an", "Ich nutze meinen Laptop jeweils zur Hälfte beruflich und privat. Wie gebe ich ihn steuerlich an?"),
    ("ocr-steuerklasse", "ocr hat arbeitgeber und jahr erkannt aber steuerklasse fehlt noch", "Die Dokumentenerkennung hat Arbeitgeber und Steuerjahr erkannt, aber die Steuerklasse fehlt noch."),
    ("vermietung-2023", "eine wohnung war 2023 nur acht monate vermietet was mach ich mit den kosten", "Eine Wohnung war 2023 nur acht Monate vermietet. Wie berücksichtige ich die Kosten?"),
    ("sanierung-versicherung", "kan ich sanirung vom eigenem haus absetzten wen versicherung nur teil gezalt hat", "Kann ich die Sanierung meines eigenen Hauses steuerlich absetzen, wenn die Versicherung nur einen Teil bezahlt hat?"),
    ("jahr-korrektur", "nein nicht 2025 ich meine die erklärung für 2023", "Ich meine nicht die Steuererklärung 2025, sondern die Steuererklärung 2023."),
    ("eigentum", "ich bin eigentümer und wohne selbst in der wohnung", "Ich bin Eigentümer und wohne selbst in der Wohnung."),
    ("teilvermietet", "von den drei wohnungen bewohne ich eine die anderen zwei sind vermietet", "Von den drei Wohnungen bewohne ich eine selbst. Die beiden anderen sind vermietet."),
)


# Aufbau: Kennung, vorherige Nutzerfrage, echte Rueckfrage des Assistenten,
# umgangssprachliche Folgeantwort, gewuenschte eindeutige Formulierung.
# Pilot 03 enthielt hier faelschlich die Assistentenantwort "Bitte antworte kurz".
# Das war kein natuerlicher Dialog und trainierte den Gespraechsbezug nur schwach.
FOLGEFAELLE = (
    ("folge-eigen", "Bei uns war ein Wasserschaden. Kann ich die Reparatur absetzen?", "Welcher Teil des Hauses war betroffen?", "meine eigene wohnung", "Der Wasserschaden betraf meine selbst genutzte Wohnung."),
    ("folge-mieter", "Im Haus ist eine Leitung kaputtgegangen.", "Welcher Gebäudeteil war betroffen?", "bei den mietern oben", "Die Leitung in der oberen vermieteten Wohnung war betroffen."),
    ("folge-leitung", "Eine Wasserleitung im Haus musste erneuert werden.", "War eine einzelne Wohnung oder eine gemeinsame Leitung betroffen?", "die leitung für alle", "Betroffen war die gemeinsame Leitung für alle Wohnungen."),
    ("folge-versichert", "Ich habe eine Handwerkerrechnung wegen eines Wasserschadens.", "Hat eine Versicherung Kosten übernommen?", "ja die hat alles gezahlt", "Ja, die Versicherung hat die gesamten Kosten übernommen."),
    ("folge-teil", "Die Gebäudeversicherung war an der Reparatur beteiligt.", "Hat die Versicherung die gesamten Kosten übernommen?", "nein nur das material", "Nein, die Gebäudeversicherung hat nur die Materialkosten übernommen."),
    ("folge-selbstbehalt", "Der Schaden wurde über die Versicherung abgewickelt.", "Welche Kosten hast du selbst getragen?", "nur den selbstbehalt von 500 euro", "Ich habe nur den Selbstbehalt von 500 Euro selbst getragen."),
    ("folge-jahr23", "Ich möchte meine noch offene Steuererklärung vorbereiten.", "Für welches Steuerjahr möchtest du die Erklärung machen?", "für 23", "Ich möchte die Steuererklärung für 2023 machen."),
    ("folge-jahr24", "Es geht um die Grundsteuer.", "Geht es um 2023 oder 2024?", "nee 2024", "Es geht um die Grundsteuer im Jahr 2024."),
    ("folge-nutzung", "Am Dreifamilienhaus wurde das Dach repariert.", "Nutzt du das Haus selbst oder vermietest du es?", "beides ich wohn drin und vermiete zwei wohnungen", "Ich wohne selbst im Haus und vermiete zwei Wohnungen."),
    ("folge-rechnung", "Ich möchte Handwerkerkosten angeben.", "Hast du eine Rechnung und unbar bezahlt?", "rechnung ja aber bar", "Ich habe eine Rechnung, aber bar bezahlt."),
    ("folge-arbeitsweg", "Ich fahre mit dem Auto zur Arbeit.", "Wie weit ist dein einfacher Arbeitsweg?", "15 kilometer einfach", "Mein einfacher Arbeitsweg beträgt 15 Kilometer."),
    ("folge-korrektur", "Dann betrachten wir die Steuererklärung 2025.", "Ist das Steuerjahr 2025 richtig?", "nein ich mein 2023", "Ich meine nicht 2025, sondern das Steuerjahr 2023."),
)


PRAEFIXE = ("", "also ", "kurz gefragt ", "ich blick da nicht durch ", "mal ohne beamtendeutsch ", "bei meiner steuer ")


def variante(text: str, nummer: int) -> str:
    text = PRAEFIXE[nummer % len(PRAEFIXE)] + text
    modus = (nummer // len(PRAEFIXE)) % 4
    if modus == 1:
        text = text.lower().replace("?", "") + " bitte klar formulieren"
    elif modus == 2:
        vorher = text
        text = text.replace("ich habe", "ich hab").replace("es geht", "es gehts")
        if text == vorher:
            text += " bitte normal formulieren"
    elif modus == 3:
        vorher = text
        text = re.sub(r"\bsteuerlich\b", "steurlich", text, count=1, flags=re.I)
        text = re.sub(r"\bVersicherung\b", "Versicherrung", text, count=1, flags=re.I)
        if text == vorher:
            text += " bitte einfach erkleren"
    return " ".join(text.split())


def eintrag(eid: str, messages: list[dict], split: str, nummer: int) -> dict:
    return {
        "id": f"praxis-{eid}-{split}-{nummer:02d}",
        "thema": "Praxisdialog und Detailerhalt",
        "messages": messages,
        "metadaten": {"aufgabe": "detailtreue_kanonisierung", "synthetisch": True, "split": split},
    }


def erstellen() -> dict:
    train: list[dict] = []
    validation: list[dict] = []
    for index, (eid, roh, ziel) in enumerate(EINZELFAELLE):
        split = "validation" if index % 8 == 7 else "train"
        anzahl = 8 if split == "validation" else 24
        sammlung = validation if split == "validation" else train
        for nummer in range(anzahl):
            messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": variante(roh, nummer)}, {"role": "assistant", "content": ziel}]
            sammlung.append(eintrag(eid, messages, split, nummer + 1))
    for index, (eid, vorher, frage, antwort, ziel) in enumerate(FOLGEFAELLE):
        split = "validation" if index % 5 == 4 else "train"
        anzahl = 8 if split == "validation" else 24
        sammlung = validation if split == "validation" else train
        for nummer in range(anzahl):
            messages = [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": vorher},
                {"role": "assistant", "content": frage},
                {"role": "user", "content": variante(antwort, nummer)},
                {"role": "assistant", "content": ziel},
            ]
            sammlung.append(eintrag(eid, messages, split, nummer + 1))
    random.Random(20260826).shuffle(train)
    random.Random(20260827).shuffle(validation)
    for name, daten in (("praxisdialog_train.jsonl", train), ("praxisdialog_validation.jsonl", validation)):
        with (ZIEL / name).open("w", encoding="utf-8", newline="\n") as datei:
            for item in daten:
                datei.write(json.dumps(item, ensure_ascii=False) + "\n")
    return {"train": len(train), "validation": len(validation), "test_bleibt_getrennt": "praxis_kanonisierung_test.jsonl"}


if __name__ == "__main__":
    print(json.dumps(erstellen(), ensure_ascii=False, indent=2))
