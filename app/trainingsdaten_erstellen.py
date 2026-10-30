"""Erstellt einen kleinen, quellenbasierten 9B-Pilotdatensatz.

Es werden ausschließlich die redaktionell gepflegten Zusammenfassungen unter
``wissen/quellen`` verwendet. Ungeprüfte Antworten aus SteuerLLM, OpenLegal
oder früheren Modelltests gelangen nicht in diese Ausgabe.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUELLEN_ORDNER = PROJECT_ROOT / "wissen" / "quellen"
ERGAENZUNGEN_PFAD = PROJECT_ROOT / "wissen" / "trainings_ergaenzungen.json"
ZIEL_ORDNER = PROJECT_ROOT / "testDaten" / "steuerllm_training_freigegeben"
CHARGEN_ORDNER = ZIEL_ORDNER / "chargen"

PFLICHTFELDER = {
    "titel",
    "herausgeber",
    "paragraph",
    "steuerjahr",
    "stand_abgerufen",
    "url",
    "kategorie",
    "inhalt",
}

AMTLICHE_DOMAINS = {
    "ao.bundesfinanzministerium.de",
    "download.elster.de",
    "esth.bundesfinanzministerium.de",
    "lsth.bundesfinanzministerium.de",
    "online.portal.bzst.de",
    "www.bundesfinanzhof.de",
    "www.bundesfinanzministerium.de",
    "www.bundesregierung.de",
    "con.arbeitsagentur.de",
    "www.arbeitsagentur.de",
    "www.deutsche-rentenversicherung.de",
    "www.elster.de",
    "www.finanzamt.bayern.de",
    "www.gesetze-im-internet.de",
    "www.grundsteuer.bayern.de",
    "www.minijob-zentrale.de",
    "www.portal.elster.de",
}

SYSTEMTEXT = (
    "Du bist ein vorsichtiger deutscher Steuerassistent. Antworte klar und "
    "knapp, nenne Rechtsgrundlage und Rechtsstand, erfinde keine Ausnahmen und "
    "weise bei fallabhängigen Ergebnissen auf die notwendige Einzelfallprüfung hin."
)

FRAGEVORLAGEN = (
    "Erkläre mir bitte {titel}. Welche Rechtsgrundlage gilt nach dem Rechtsstand {jahr}?",
    "Was muss ich zum Thema „{kategorie}“ wissen? Bitte nenne auch die Rechtsgrundlage und den Rechtsstand {jahr}.",
    "Gib mir eine kurze steuerliche Einordnung zu „{titel}“ mit Rechtsgrundlage. Stand: {jahr}.",
    "Wie ist „{kategorie}“ steuerlich einzuordnen? Verwende den Rechtsstand {jahr} und nenne die maßgebliche Vorschrift.",
)


def thema_bestimmen(dateiname: str, quelle: dict) -> str:
    text = " ".join(
        (dateiname, quelle["titel"], quelle["kategorie"], quelle["paragraph"])
    ).casefold()
    regeln = (
        ("Erbschaft und Schenkung", ("erbstg", "erbschaft", "schenkung")),
        ("Umsatzsteuer", ("ustg", "umsatzsteuer", "vorsteuer", "kleinunternehmer")),
        ("Kapital und private Verkäufe", ("kapital", "invstg", "krypto", "lottogewinn", "§ 20 ", "§ 23 ")),
        ("Grundsteuer und kommunale Grundabgaben", ("grundsteuer", "grundabgabe", "grundbesitzabgabe", "grstg", "hebesatz", "grundsteuermess")),
        ("Vermietung und Immobilien", ("vermiet", "betrkv", "mieter", "immobil", "gebäude", "erbbaurecht")),
        ("Familie und Kinder", ("kind", "familie", "ehegatt", "alleinerzieh", "splitting", "unterhalt")),
        ("Rente und Vorsorge", ("rente", "vorsorge", "versicherung", "riester", "pflege", "krankheits")),
        ("Steuererklärung und Finanzamt", ("ao_", "elster", "finanzamt", "einspruch", "steuererklär", "frist", "bzst", "steuer-id", "kirchensteuer")),
        ("Selbstständigkeit und Kleinunternehmen", ("gewerbe", "gewstg", "betrieb", "photovoltaik", "selbstst", "minijob")),
    )
    for thema, begriffe in regeln:
        if any(begriff in text for begriff in begriffe):
            return thema
    return "Arbeitnehmer und Werbungskosten"


def quelle_pruefen(pfad: Path, quelle: dict) -> None:
    fehlend = sorted(PFLICHTFELDER - quelle.keys())
    if fehlend:
        raise ValueError(f"{pfad.name}: Pflichtfelder fehlen: {', '.join(fehlend)}")
    domain = urlparse(str(quelle["url"])).netloc.casefold()
    if domain not in AMTLICHE_DOMAINS:
        raise ValueError(f"{pfad.name}: nicht freigegebene Domain: {domain or '<leer>'}")
    if not str(quelle["inhalt"]).strip() or len(str(quelle["inhalt"]).strip()) < 80:
        raise ValueError(f"{pfad.name}: Zusammenfassung ist zu kurz oder leer")
    if not str(quelle["paragraph"]).strip():
        raise ValueError(f"{pfad.name}: Rechtsgrundlage fehlt")


def beispiel_bauen(pfad: Path, quelle: dict) -> dict:
    kandidat_id = f"amtlich-{pfad.stem}"
    digest = hashlib.sha256(kandidat_id.encode("utf-8")).digest()
    vorlage = FRAGEVORLAGEN[digest[0] % len(FRAGEVORLAGEN)]
    frage = vorlage.format(
        titel=quelle["titel"], kategorie=quelle["kategorie"], jahr=quelle["steuerjahr"]
    )
    antwort = (
        f"{str(quelle['inhalt']).strip()}\n\n"
        f"Rechtsgrundlage: {quelle['paragraph']}. "
        f"Rechtsstand: {quelle['steuerjahr']}; Quelle abgerufen am "
        f"{quelle['stand_abgerufen']}."
    )
    return {
        "id": kandidat_id,
        "thema": thema_bestimmen(pfad.name, quelle),
        "messages": [
            {"role": "system", "content": SYSTEMTEXT},
            {"role": "user", "content": frage},
            {"role": "assistant", "content": antwort},
        ],
        "metadaten": {
            "status": "quellenbasiert_freigegeben",
            "quelle_datei": pfad.name,
            "quelle_url": quelle["url"],
            "herausgeber": quelle["herausgeber"],
            "paragraph": quelle["paragraph"],
            "rechtsstand": quelle["steuerjahr"],
            "stand_abgerufen": quelle["stand_abgerufen"],
            "nicht_fuer_qdrant": True,
            "trainingszweck": "9B-Pilot: Antwortstil, Quellenbezug und vorsichtige Falleinordnung",
        },
    }


def quellen_laden() -> list[dict]:
    beispiele = []
    for pfad in sorted(QUELLEN_ORDNER.glob("*.json")):
        with pfad.open("r", encoding="utf-8") as datei:
            quelle = json.load(datei)
        quelle_pruefen(pfad, quelle)
        beispiele.append(beispiel_bauen(pfad, quelle))
    if len({x["id"] for x in beispiele}) != len(beispiele):
        raise ValueError("Doppelte Trainings-IDs erkannt")
    if len({x["messages"][1]["content"] for x in beispiele}) != len(beispiele):
        raise ValueError("Doppelte Trainingsfragen erkannt")
    return beispiele


def ergaenzungen_laden() -> list[dict]:
    with ERGAENZUNGEN_PFAD.open("r", encoding="utf-8") as datei:
        roh = json.load(datei)
    beispiele = []
    pflicht = {"id", "thema", "frage", "antwort", "paragraph", "url"}
    for eintrag in roh:
        fehlend = sorted(pflicht - eintrag.keys())
        if fehlend:
            raise ValueError(f"Trainings-Ergänzung {eintrag.get('id')}: Felder fehlen: {fehlend}")
        domain = urlparse(eintrag["url"]).netloc.casefold()
        if domain not in AMTLICHE_DOMAINS:
            raise ValueError(f"Trainings-Ergänzung {eintrag['id']}: Domain nicht amtlich")
        if len(eintrag["antwort"].strip()) < 80:
            raise ValueError(f"Trainings-Ergänzung {eintrag['id']}: Antwort zu kurz")
        beispiele.append(
            {
                "id": f"amtlich-ergaenzung-{eintrag['id']}",
                "thema": eintrag["thema"],
                "messages": [
                    {"role": "system", "content": SYSTEMTEXT},
                    {"role": "user", "content": eintrag["frage"]},
                    {
                        "role": "assistant",
                        "content": (
                            f"{eintrag['antwort'].strip()}\n\n"
                            f"Rechtsgrundlage: {eintrag['paragraph']}. Rechtsstand: 2026."
                        ),
                    },
                ],
                "metadaten": {
                    "status": "quellenbasiert_freigegeben",
                    "quelle_datei": ERGAENZUNGEN_PFAD.name,
                    "quelle_url": eintrag["url"],
                    "herausgeber": "Bundesministerium der Justiz / Bundesamt für Justiz",
                    "paragraph": eintrag["paragraph"],
                    "rechtsstand": 2026,
                    "stand_abgerufen": "2026-08-25",
                    "nicht_fuer_qdrant": True,
                    "trainingszweck": "9B-Pilot: Antwortstil, Quellenbezug und vorsichtige Falleinordnung",
                },
            }
        )
    if len(beispiele) != 31 or len({x["id"] for x in beispiele}) != 31:
        raise ValueError("Erwartet werden 31 eindeutige Trainings-Ergänzungen")
    return beispiele


def deterministische_reihenfolge(beispiele: list[dict]) -> list[dict]:
    return sorted(
        beispiele,
        key=lambda x: hashlib.sha256(("split-" + x["id"]).encode("utf-8")).hexdigest(),
    )


def jsonl_schreiben(pfad: Path, beispiele: list[dict]) -> None:
    with pfad.open("w", encoding="utf-8", newline="\n") as datei:
        for beispiel in beispiele:
            datei.write(json.dumps(beispiel, ensure_ascii=False) + "\n")


def chargen_schreiben(
    basis_train: list[dict], ergaenzungen: list[dict], validation: list[dict], test: list[dict]
) -> None:
    CHARGEN_ORDNER.mkdir(parents=True, exist_ok=True)
    gruppen = (
        [(nummer, basis_train[i : i + 15], "training") for nummer, i in enumerate(range(0, len(basis_train), 15), 3)]
        + [(10, validation + test, "validierung_und_test")]
        + [
            (11, ergaenzungen[:10], "training_themenausgleich"),
            (12, ergaenzungen[10:20], "training_themenausgleich"),
            (13, ergaenzungen[20:], "training_themenausgleich"),
        ]
    )
    for nummer, gruppe, verwendung in gruppen:
        bericht = {
            "charge": nummer,
            "modus": "quellenbasierte Trainingsfreigabe",
            "verwendung": verwendung,
            "geprueft": len(gruppe),
            "freigegeben": len(gruppe),
            "abgelehnt": 0,
            "methodik": (
                "Nur redaktionell gepflegte lokale Zusammenfassungen mit Pflichtfeldern, "
                "amtlicher Domain, Rechtsgrundlage, Rechtsstand und Abrufdatum. Keine "
                "ungeprueften Modellantworten."
            ),
            "beispiele": [
                {
                    "id": x["id"],
                    "thema": x["thema"],
                    "status": "quellenbasiert_freigegeben",
                    "quelle_datei": x["metadaten"]["quelle_datei"],
                    "quelle_url": x["metadaten"]["quelle_url"],
                    "paragraph": x["metadaten"]["paragraph"],
                }
                for x in gruppe
            ],
        }
        (CHARGEN_ORDNER / f"fachpruefung_charge_{nummer:02d}.json").write_text(
            json.dumps(bericht, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def main() -> None:
    basis = deterministische_reihenfolge(quellen_laden())
    ergaenzungen = deterministische_reihenfolge(ergaenzungen_laden())
    if len(basis) < 16:
        raise ValueError("Für getrennte Validierungs- und Testmengen werden mindestens 16 amtliche Wissenseinträge benötigt")

    basis_train = basis[:-16]
    validation = basis[-16:-8]
    test = basis[-8:]
    train = basis_train + ergaenzungen
    ZIEL_ORDNER.mkdir(parents=True, exist_ok=True)
    jsonl_schreiben(ZIEL_ORDNER / "train.jsonl", train)
    jsonl_schreiben(ZIEL_ORDNER / "validation.jsonl", validation)
    jsonl_schreiben(ZIEL_ORDNER / "test.jsonl", test)
    chargen_schreiben(basis_train, ergaenzungen, validation, test)

    manifest = {
        "datensatz": "Steuer-Assistent 9B Pilot",
        "zielmodell": "Qwen 3.5 9B (lokaler Assistent: qwen3.5:9b)",
        "format": "JSONL mit messages im System/User/Assistant-Format",
        "status": "technisch_bereit_fuer_pilottraining",
        "hinweis": "Kein Ersatz für RAG, amtliche Quellen oder fachliche Endkontrolle.",
        "quelle": ["wissen/quellen/*.json", "wissen/trainings_ergaenzungen.json"],
        "ausgeschlossen": [
            "SteuerLLM-Rohantworten",
            "OpenLegal-Rohantworten",
            "Modellantworten aus früheren Testläufen",
        ],
        "anzahl": {"train": len(train), "validation": len(validation), "test": len(test)},
        "themen_train": dict(sorted(Counter(x["thema"] for x in train).items())),
        "themen_validation": dict(sorted(Counter(x["thema"] for x in validation).items())),
        "themen_test": dict(sorted(Counter(x["thema"] for x in test).items())),
        "chargen": list(range(3, 14)),
        "split_verfahren": (
            f"{len(basis)} RAG-Zusammenfassungen deterministisch "
            f"{len(basis_train)}/8/8; 31 gezielte amtlich belegte "
            "Themenausgleichsfälle nur im Training."
        ),
    }
    (ZIEL_ORDNER / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
