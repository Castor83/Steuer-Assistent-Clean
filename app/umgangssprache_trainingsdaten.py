"""Erzeugt ein kontrolliertes Umgangssprache-Paket fuer den Steuer-Assistenten.

Die fachlich freigegebenen Steuerfaelle bleiben die einzige Quelle fuer
Sollantworten. Externe Sprachdaten werden nur als getrennte Referenz fuer kurze
deutsche Formulierungen gespeichert und niemals als steuerliche Wissensquelle
behandelt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUELLORDNER = PROJECT_ROOT / "testDaten" / "steuerllm_training_freigegeben"
ZIELORDNER = PROJECT_ROOT / "testDaten" / "umgangssprache_steuer_training"

KANONISIERUNGS_SYSTEMTEXT = (
    "Du vereinheitlichst umgangssprachliche deutsche Steuerfragen. Formuliere "
    "nur die gemeinte Frage in klarem Standarddeutsch. Beantworte sie nicht "
    "und ergaenze keine Tatsachen, die der Nutzer nicht genannt hat."
)

EINLEITUNGEN = (
    "Wie läuft das eigentlich beim Thema „{thema}“",
    "Was gilt beim Thema „{thema}“",
    "Kannst du mir das Thema „{thema}“ mal normal erklären",
    "Ich blick beim Thema „{thema}“ nicht durch",
    "Was muss ich zu „{thema}“ bei der Steuer wissen",
    "Wie ist das Thema „{thema}“ steuerlich einzuordnen",
    "Was sagt das Finanzamt zum Thema „{thema}“",
    "Bei mir gehts um „{thema}“, wie wird das eingeordnet",
    "Muss ich bei „{thema}“ steuerlich etwas beachten",
    "Was ist bei „{thema}“ für die Steuer wichtig",
    "Wie funktioniert das beim Thema „{thema}“",
    "Kann mir jemand das Thema „{thema}“ verständlich erklären",
    "Wie wird „{thema}“ bei der Steuer behandelt",
    "Ich versteh die Regel zu „{thema}“ nicht",
    "Was bedeutet „{thema}“ für meine Steuererklärung",
    "Kannst du „{thema}“ kurz steuerlich einordnen",
    "Worum gehts steuerlich bei „{thema}“",
    "Wie muss ich „{thema}“ bei der Steuer sehen",
    "Was steckt steuerlich hinter „{thema}“",
    "Ich brauch eine einfache Erklärung zum Thema „{thema}“",
)

FRAGE_EINLEITUNGEN = (
    "Kannst du das bitte einfach erklären: {frage}",
    "Ich versteh diese Steuerfrage nicht: {frage}",
    "Wie ist das steuerlich einzuordnen: {frage}",
    "Mal ohne Beamtendeutsch: {frage}",
    "Ich blick da nicht durch, {frage}",
    "Was heißt das genau: {frage}",
    "Kannste mir sagen, {frage}",
    "Ich brauch Hilfe bei der Frage: {frage}",
    "Wie läuft das in diesem Fall: {frage}",
    "Was muss ich hierzu wissen: {frage}",
    "Kurz erklärt bitte: {frage}",
    "Ich hab gelesen, dass das wichtig ist. {frage}",
    "Wie sieht das Finanzamt das: {frage}",
    "Was gilt denn nun: {frage}",
    "Kann mir das jemand verständlich machen: {frage}",
    "Was steckt steuerlich dahinter: {frage}",
    "Ich mach gerade die Steuer und frage mich: {frage}",
    "Kannst du diese Frage normal beantworten: {frage}",
    "Was bedeutet das für mich: {frage}",
    "Ich brauche eine klare Einordnung: {frage}",
)

NACHSAETZE = (
    "?",
    ", bitte einfach erklärt?",
    ", kurz und verständlich?",
    ", was heißt das genau?",
)

MEHRTURN_START = (
    "Ich hab eine Steuerfrage zu {thema}.",
    "Bei mir geht es um {thema}.",
    "Ich brauch Hilfe wegen {thema}.",
    "Es geht um {thema} bei meiner Steuer.",
)

MEHRTURN_FOLGE = (
    "wie läuft das da steuerlich",
    "was gilt da genau",
    "kannst du mir das normal erklären",
    "was muss ich dabei wissen",
)

EXTERNE_QUELLEN = (
    {
        "id": "AmazonScience/massive",
        "config": "de-DE",
        "split": "train",
        "feld": "utt",
        "lizenz": "CC BY 4.0",
        "url": "https://huggingface.co/datasets/AmazonScience/massive",
        "zweck": "kurze deutsche alltagssprachliche Aeusserungen und Intenterkennung",
    },
    {
        "id": "clips/mfaq",
        "config": "de_flat",
        "split": "train",
        "feld": "question",
        "lizenz": "CC0 1.0",
        "url": "https://huggingface.co/datasets/clips/mfaq",
        "zweck": "natuerliche deutsche FAQ-Frageformulierungen",
    },
)


def jsonl_laden(pfad: Path) -> list[dict]:
    return [json.loads(zeile) for zeile in pfad.read_text(encoding="utf-8").splitlines() if zeile.strip()]


def jsonl_schreiben(pfad: Path, eintraege: list[dict]) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    with pfad.open("w", encoding="utf-8", newline="\n") as datei:
        for eintrag in eintraege:
            datei.write(json.dumps(eintrag, ensure_ascii=False) + "\n")


@lru_cache(maxsize=1)
def _kategorie_haeufigkeiten() -> Counter:
    zaehler: Counter = Counter()
    for pfad in (PROJECT_ROOT / "wissen" / "quellen").glob("*.json"):
        try:
            kategorie = str(json.loads(pfad.read_text(encoding="utf-8")).get("kategorie", "")).strip()
        except (OSError, ValueError, TypeError):
            continue
        if kategorie:
            zaehler[kategorie] += 1
    return zaehler


def thema_aus_beispiel(beispiel: dict) -> str:
    """Gewinnt einen sprechbaren Gegenstand ohne Paragraphen-Praefix."""
    frage = beispiel["messages"][-2]["content"].strip()
    quellname = beispiel.get("metadaten", {}).get("quelle_datei", "")
    if quellname == "trainings_ergaenzungen.json":
        return frage.rstrip(" ?")
    quellpfad = PROJECT_ROOT / "wissen" / "quellen" / quellname
    quelltitel = ""
    quellkategorie = ""
    if quellpfad.is_file():
        try:
            quelldaten = json.loads(quellpfad.read_text(encoding="utf-8"))
            quelltitel = str(quelldaten.get("titel", "")).strip()
            quellkategorie = str(quelldaten.get("kategorie", "")).strip()
        except (OSError, ValueError, TypeError):
            quelltitel = ""
            quellkategorie = ""
    treffer = re.search(r"„([^”]+)“", frage)
    if quellkategorie and _kategorie_haeufigkeiten()[quellkategorie] == 1:
        thema = quellkategorie
    elif quelltitel:
        thema = quelltitel
    elif treffer:
        thema = treffer.group(1)
    else:
        treffer = re.search(r"Erkläre mir bitte (.+?)\. Welche Rechtsgrundlage", frage)
        thema = treffer.group(1) if treffer else beispiel["thema"]
    thema = re.sub(
        r"^(?:EStG|AO|UStG|ErbStG|GrStG|GewStG|InvStG|BetrKV)\s*§{1,2}\s*[^–-]+[–-]\s*",
        "",
        thema,
        flags=re.IGNORECASE,
    )
    thema = re.sub(
        r"^(?:Bundesregierung|Bundesfinanzministerium|BMF|ELSTER)\s*[–-]\s*",
        "",
        thema,
        flags=re.IGNORECASE,
    )
    return thema.strip(" .:–-") or beispiel["thema"]


def oberflaeche_variieren(text: str, modus: int) -> tuple[str, str]:
    """Erzeugt kontrollierte Schreibvarianten ohne die Bedeutung zu aendern."""
    if modus == 0:
        return text, "alltagssprache"
    if modus == 1:
        return text.lower().rstrip("?"), "kleinschreibung_ohne_satzzeichen"
    if modus == 2:
        ersetzt = (
            text.replace("Kannst du", "Kannste")
            .replace("kannst du", "kannste")
            .replace("Ich habe", "Ich hab")
            .replace("ich habe", "ich hab")
            .replace("geht es", "gehts")
        )
        return ersetzt, "gesprochene_kurzform"
    # Genau ein kontrollierter Tippfehler; falls kein Steuerwort vorkommt,
    # wird ein haeufiger Funktionswortfehler verwendet.
    fehler = text.replace("Steuererklärung", "Steuererklerung", 1)
    if fehler == text:
        fehler = text.replace("steuerlich", "steurlich", 1)
    if fehler == text:
        fehler = text.replace("erklären", "erkleren", 1)
    if fehler == text:
        fehler = text.replace("bei der", "bei de", 1)
    if fehler == text:
        fehler = text.replace("Thema", "Tema", 1)
    if fehler == text:
        fehler = text.replace("Was", "Wass", 1)
    if fehler == text:
        fehler = text.rstrip("?") + " bite?"
    return fehler.lower().rstrip("?"), "ein_tippfehler"


def kanonische_frage(thema: str) -> str:
    """Glaettet nur die Sprache, ohne Rechtsstand oder Normen zu erfinden."""
    thema = thema.strip().rstrip("?.!")
    return f"Was muss ich steuerlich zum Thema „{thema}“ wissen?"


def kanonisierungsbeispiele_bauen(basis: list[dict], varianten: int) -> list[dict]:
    if varianten < 1 or varianten > len(EINLEITUNGEN) * len(NACHSAETZE):
        raise ValueError(f"varianten muss zwischen 1 und {len(EINLEITUNGEN) * len(NACHSAETZE)} liegen")
    ausgabe: list[dict] = []
    for beispiel in basis:
        thema = thema_aus_beispiel(beispiel)
        kanonisch = kanonische_frage(thema)
        ist_frageform = beispiel.get("metadaten", {}).get("quelle_datei") == "trainings_ergaenzungen.json"
        for nummer in range(varianten):
            einleitungen = FRAGE_EINLEITUNGEN if ist_frageform else EINLEITUNGEN
            einleitung = einleitungen[nummer % len(einleitungen)]
            nachsatz = NACHSAETZE[(nummer // len(EINLEITUNGEN)) % len(NACHSAETZE)]
            if ist_frageform:
                frageform = thema[:1].lower() + thema[1:]
                roh = einleitung.format(frage=frageform) + nachsatz
            else:
                roh = einleitung.format(thema=thema) + nachsatz
            umgang, stil = oberflaeche_variieren(roh, nummer % 4)
            ausgabe.append(
                {
                    "id": f"{beispiel['id']}-kanon-{nummer + 1:02d}",
                    "basis_id": beispiel["id"],
                    "thema": beispiel["thema"],
                    "messages": [
                        {"role": "system", "content": KANONISIERUNGS_SYSTEMTEXT},
                        {"role": "user", "content": umgang},
                        {"role": "assistant", "content": kanonisch},
                    ],
                    "metadaten": {
                        "aufgabe": "umgangssprache_kanonisieren",
                        "stil": stil,
                        "synthetisch": True,
                        "fachantwort_enthalten": False,
                        "basis_status": beispiel["metadaten"]["status"],
                        "quelle_url": beispiel["metadaten"]["quelle_url"],
                    },
                }
            )
    return ausgabe


def dialogbeispiele_bauen(basis: list[dict]) -> list[dict]:
    """Ergaenzt wenige mehrteilige Dialoge mit unveraenderter Sollantwort."""
    ausgabe: list[dict] = []
    for beispiel in basis:
        thema = thema_aus_beispiel(beispiel)
        ist_frageform = beispiel.get("metadaten", {}).get("quelle_datei") == "trainings_ergaenzungen.json"
        system = beispiel["messages"][0]
        antwort = beispiel["messages"][-1]
        for nummer, (start, folge) in enumerate(zip(MEHRTURN_START, MEHRTURN_FOLGE), 1):
            if ist_frageform:
                erster_turn = "Ich hab eine Steuerfrage."
                folgeturn = f"{folge}: {thema[:1].lower() + thema[1:]}?"
            else:
                erster_turn = start.format(thema=thema)
                folgeturn = folge
            ausgabe.append(
                {
                    "id": f"{beispiel['id']}-dialog-{nummer:02d}",
                    "basis_id": beispiel["id"],
                    "thema": beispiel["thema"],
                    "messages": [
                        system,
                        {"role": "user", "content": erster_turn},
                        {"role": "assistant", "content": "Gern. Was möchtest du dazu wissen?"},
                        {"role": "user", "content": folgeturn},
                        antwort,
                    ],
                    "metadaten": {
                        **beispiel["metadaten"],
                        "aufgabe": "mehrturn_dialog_mit_quellenantwort",
                        "synthetische_nutzeraeusserungen": True,
                        "fachantwort_unveraendert": True,
                        "basis_id": beispiel["id"],
                    },
                }
            )
    return ausgabe


def _zeilen_abrufen(quelle: dict, anzahl: int) -> list[dict]:
    ausgabe: list[dict] = []
    seiten = (anzahl + 99) // 100
    offsets = [0]
    # Die Gesamtzahl steht in jeder Antwort. Mit einer Ein-Zeilen-Abfrage wird
    # sie zuerst ermittelt, damit mFAQ nicht nur vom ersten Quelldomain-Block
    # stammt.
    start_parameter = urlencode(
        {
            "dataset": quelle["id"],
            "config": quelle["config"],
            "split": quelle["split"],
            "offset": 0,
            "length": 1,
        }
    )
    start_request = Request(
        "https://datasets-server.huggingface.co/rows?" + start_parameter,
        headers={"User-Agent": "Steuer-Assistent-Sprachdaten/1.0"},
    )
    with urlopen(start_request, timeout=30) as antwort:
        gesamt = int(json.load(antwort)["num_rows_total"])
    if seiten > 1:
        letzter_start = max(0, gesamt - 100)
        offsets = [round(i * letzter_start / (seiten - 1)) for i in range(seiten)]

    verbleibend = anzahl
    for offset in offsets:
        laenge = min(100, verbleibend)
        parameter = urlencode(
            {
                "dataset": quelle["id"],
                "config": quelle["config"],
                "split": quelle["split"],
                "offset": offset,
                "length": laenge,
            }
        )
        request = Request(
            "https://datasets-server.huggingface.co/rows?" + parameter,
            headers={"User-Agent": "Steuer-Assistent-Sprachdaten/1.0"},
        )
        with urlopen(request, timeout=30) as antwort:
            daten = json.load(antwort)
        for element in daten["rows"]:
            original = element["row"]
            text = str(original.get(quelle["feld"], "")).strip()
            if text:
                herkunft = {
                    schluessel: original[schluessel]
                    for schluessel in ("domain", "locale", "intent", "scenario")
                    if schluessel in original
                }
                ausgabe.append(
                    {
                        "text": text,
                        "quelle": quelle["id"],
                        "lizenz": quelle["lizenz"],
                        "verwendung": "sprachreferenz_nicht_steuerwissen",
                        "herkunft": herkunft,
                    }
                )
        verbleibend -= laenge
    return ausgabe


def sprachreferenzen_laden(anzahl_je_quelle: int) -> list[dict]:
    if not 1 <= anzahl_je_quelle <= 5000:
        raise ValueError("anzahl_je_quelle muss zwischen 1 und 5000 liegen")
    ausgabe = []
    for quelle in EXTERNE_QUELLEN:
        ausgabe.extend(_zeilen_abrufen(quelle, anzahl_je_quelle))
    return ausgabe


def _eindeutigkeit_pruefen(eintraege: list[dict], bezeichnung: str) -> None:
    ids = [x["id"] for x in eintraege]
    if len(ids) != len(set(ids)):
        raise ValueError(f"Doppelte IDs in {bezeichnung}")
    fragen = [x["messages"][-2]["content"].casefold().strip() for x in eintraege]
    if len(fragen) != len(set(fragen)):
        raise ValueError(f"Doppelte Nutzerfragen in {bezeichnung}")


def paket_erstellen(externe_abrufen: bool = False, sprachreferenzen_je_quelle: int = 500) -> dict:
    splits = {name: jsonl_laden(QUELLORDNER / f"{name}.jsonl") for name in ("train", "validation", "test")}
    varianten = {"train": 80, "validation": 20, "test": 20}
    kanon = {name: kanonisierungsbeispiele_bauen(split, varianten[name]) for name, split in splits.items()}
    dialoge = {name: dialogbeispiele_bauen(split) for name, split in splits.items()}

    ZIELORDNER.mkdir(parents=True, exist_ok=True)
    for name in splits:
        _eindeutigkeit_pruefen(kanon[name], f"Kanonisierung {name}")
        jsonl_schreiben(ZIELORDNER / f"kanonisierung_{name}.jsonl", kanon[name])
        jsonl_schreiben(ZIELORDNER / f"dialog_{name}.jsonl", dialoge[name])

    referenzanzahl = 0
    if externe_abrufen:
        referenzen = sprachreferenzen_laden(sprachreferenzen_je_quelle)
        jsonl_schreiben(ZIELORDNER / "externe_sprachreferenzen.jsonl", referenzen)
        referenzanzahl = len(referenzen)

    train_basis = {x["id"] for x in splits["train"]}
    andere_basis = {x["id"] for name in ("validation", "test") for x in splits[name]}
    if train_basis & andere_basis:
        raise ValueError("Basisfall-Leck zwischen Training und Auswertung")

    manifest = {
        "datensatz": "Umgangssprache-Steuer-Paket 01",
        "ziel": "Alltagssprache, Tippfehler und kurze Gespraechsbezuege verstehen",
        "zielmodell": "Qwen 3.5 9B",
        "status": "synthetischer_pilot_automatisch_geprueft_fachantworten_quellenbasiert",
        "anzahl": {
            name: {
                "basisfaelle": len(splits[name]),
                "kanonisierung": len(kanon[name]),
                "mehrturn_dialoge": len(dialoge[name]),
            }
            for name in splits
        },
        "kanonisierung_train_themen": dict(sorted(Counter(x["thema"] for x in kanon["train"]).items())),
        "externe_sprachreferenzen": referenzanzahl,
        "split_regel": "Alle Varianten eines Basisfalls bleiben im selben Split.",
        "sicherheitsregel": "Externe Sprachdaten liefern keine steuerlichen Sollantworten.",
        "fachquelle": "testDaten/steuerllm_training_freigegeben",
        "externe_quellen": list(EXTERNE_QUELLEN),
        "hinweis": "Vor echtem Training Stichprobe fachlich und sprachlich pruefen; RAG bleibt fuer aktuelles Steuerwissen erforderlich.",
    }
    (ZIELORDNER / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--externe-sprachreferenzen", action="store_true")
    parser.add_argument("--anzahl-je-quelle", type=int, default=500)
    args = parser.parse_args()
    print(
        json.dumps(
            paket_erstellen(args.externe_sprachreferenzen, args.anzahl_je_quelle),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
