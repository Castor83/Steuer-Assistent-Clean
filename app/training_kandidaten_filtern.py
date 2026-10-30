"""Filtert ungeprüfte Trainingskandidaten aus dem SteuerLLM-Instruct-Datensatz.

Die Ausgabe ist ausdrücklich kein Wissensbestand. Antworten aus den automatisch
erzeugten Quelldaten bleiben bis zu einem Abgleich mit amtlichen Quellen als
ungeprüft gekennzeichnet.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUELLEN_ORDNER = PROJECT_ROOT / "testDaten" / "steuerllm_instruct_dataset"
ZIEL_ORDNER = PROJECT_ROOT / "testDaten" / "steuerllm_instruct_gefiltert"

QUELLEN = {
    "openlegal": QUELLEN_ORDNER / "openlegal_conversations.jsonl",
    "waterfall": QUELLEN_ORDNER / "tax_waterfall_webqa_generated.jsonl",
}

# Pro Thema bleiben bewusst mehr automatisch erzeugte als mehrteilige Dialoge
# möglich. OpenLegal wird dennoch separat quotiert, damit es nicht von der
# erheblich größeren Waterfall-Datei verdrängt wird.
QUOTEN = {"openlegal": 100, "waterfall": 400}

STEUERBEGRIFFE = {
    "abgabenordnung", "abschreibung", "anlage n", "anlage vorsorgeaufwand",
    "arbeitnehmer-pauschbetrag", "außergewöhnliche belastung", "betriebsaufgabe",
    "betriebsausgabe", "doppelbesteuerungsabkommen", "einkommensteuer",
    "einkommensteuererklärung", "einspruch", "erbsteuer", "erbschaftsteuer",
    "estg", "finanzamt", "freibetrag", "gewerbesteuer", "grundsteuer",
    "kapitalertragsteuer", "kinderfreibetrag", "kirchensteuer", "kleinunternehmer",
    "lohnsteuer", "pauschbetrag", "schenkungsteuer", "sonderausgabe",
    "steuerbescheid", "steuererklärung", "steuerklasse", "steuerpflicht",
    "umsatzsteuer", "ustg", "vorsteuer", "werbungskosten",
}

THEMEN = {
    "Arbeitnehmer und Werbungskosten": (
        "arbeitnehmer", "arbeitslohn", "lohnsteuer", "werbungskosten", "homeoffice",
        "entfernungspauschale", "dienstreise", "arbeitszimmer", "doppelte haushaltsführung",
    ),
    "Steuererklärung und Finanzamt": (
        "steuererklärung", "steuerbescheid", "finanzamt", "einspruch", "frist",
        "abgabenordnung", "elster", "nachzahlung", "erstattung",
    ),
    "Familie und Kinder": (
        "kindergeld", "kinderfreibetrag", "kinderbetreuung", "alleinerzieh",
        "ehegatte", "ehepartner", "unterhalt", "splitting",
    ),
    "Vermietung und Immobilien": (
        "vermietung", "vermieter", "mieteinnah", "ferienwohnung", "immobilie",
        "grundstück", "grundsteuer", "anschaffungsnahe", "afa",
    ),
    "Rente und Vorsorge": (
        "rente", "rentner", "pension", "altersvorsorge", "riester", "rürup",
        "krankenversicherung", "pflegeversicherung", "vorsorgeaufwand",
    ),
    "Selbstständigkeit und Kleinunternehmen": (
        "selbstständig", "selbständig", "freiberuf", "kleinunternehmer", "gewerbe",
        "betriebsausgabe", "betriebsaufgabe", "einnahmenüberschuss", "eür",
    ),
    "Umsatzsteuer": (
        "umsatzsteuer", "vorsteuer", "ustg", "mehrwertsteuer", "reverse charge",
        "umsatzsteuervoranmeldung",
    ),
    "Kapital und private Verkäufe": (
        "kapitalertrag", "aktie", "dividende", "sparer-pauschbetrag", "krypto",
        "bitcoin", "private veräußerung", "abgeltungsteuer",
    ),
    "Erbschaft und Schenkung": (
        "erbschaft", "schenkung", "erbfall", "nachlass", "erbsteuer",
        "schenkungsteuer", "erbstg",
    ),
}

UNERWUENSCHTE_ANTWORTEN = (
    "als ki-sprachmodell", "als künstliche intelligenz", "ich habe keinen zugriff",
    "ich kann keine rechtsberatung", "ich kann keine steuerberatung",
    "leider kann ich diese frage nicht", "hierzu liegen mir keine informationen vor",
)

FACHGEBIET_OHNE_ALLTAGSBEZUG = (
    "umwandlungssteuer", "organschaft", "hinzurechnungsbesteuerung", "körperschaftsteuer",
    "verschmelzung", "spaltung", "konzernsteuer", "investmentsteuergesetz",
)

PARAGRAPH = re.compile(r"§{1,2}\s*\d+[a-z]?(?:\s*(?:abs\.?|satz|nr\.?)\s*\d+)?", re.I)
JAHR = re.compile(r"\b(?:19|20)\d{2}\b")
DYNAMISCHER_WERT = re.compile(
    r"\b\d[\d.]*\s*(?:euro|€|dm|deutsche mark|prozent|%)(?=\s|[.,;:]|$)", re.I
)

# Diese Formulierungen waren in der ersten fachlichen Stichprobe ein deutlicher
# Hinweis auf erfundene Gesetzeszitate oder zu pauschale Gestaltungsversprechen.
# Der Ausschluss ersetzt keine Fachprüfung, reduziert aber vermeidbare Risiken.
RISIKANTE_TRAININGSFORMULIERUNGEN = (
    "zitat aus dem",
    "steuerlich optimal",
    "steuerlast minimieren",
    "sicherstellen dass keine",
)

# Ein fachlich geprüfter Kandidat bleibt gesperrt, bis eine überarbeitete Fassung
# erneut geprüft wurde. Begründungen und amtliche Quellen stehen in
# testDaten/steuerllm_instruct_gefiltert/fachpruefung_charge_01.json.
MANUELL_NICHT_FREIGEGEBENE_IDS = {
    "openlegal--6516751069646218947",
    "waterfall-333310",
    "waterfall-471302",
    "waterfall-96688",
    "waterfall-403224",
    "openlegal--1554615613725120988",
    "openlegal--861050029028656776",
    "openlegal--7053226763887804073",
    "waterfall-412255",
    # Fachprüfung Charge 02: abgelehnt oder zurückgestellt.
    "waterfall-228040",
    "waterfall-143940",
    "waterfall-228042",
    "waterfall-475024",
    "waterfall-441861",
    "waterfall-437580",
    "waterfall-136569",
    "waterfall-18046",
    "waterfall-127698",
}


def normalisiere(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text)).casefold()
    text = text.replace("ß", "ss")
    text = re.sub(r"[^a-z0-9äöü§? -]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def standardisiere_nachrichten(rohdaten: dict) -> list[dict[str, str]]:
    nachrichten = rohdaten.get("conversation") or rohdaten.get("conversations") or []
    ergebnis = []
    for nachricht in nachrichten:
        rolle = {"human": "user", "gpt": "assistant"}.get(
            nachricht.get("role") or nachricht.get("from"),
            nachricht.get("role") or nachricht.get("from"),
        )
        inhalt = str(nachricht.get("content") or nachricht.get("value") or "").strip()
        ergebnis.append({"role": rolle, "content": inhalt})
    return ergebnis


def pruefe_struktur(nachrichten: list[dict[str, str]]) -> str | None:
    if len(nachrichten) < 2 or len(nachrichten) % 2:
        return "dialogstruktur"
    for index, nachricht in enumerate(nachrichten):
        erwartet = "user" if index % 2 == 0 else "assistant"
        if nachricht["role"] != erwartet or not nachricht["content"]:
            return "dialogstruktur"
    fragen = [n["content"] for n in nachrichten if n["role"] == "user"]
    antworten = [n["content"] for n in nachrichten if n["role"] == "assistant"]
    if any(not 25 <= len(frage) <= 3_000 for frage in fragen):
        return "fragenlaenge"
    if any(not 70 <= len(antwort) <= 6_000 for antwort in antworten):
        return "antwortlaenge"
    return None


def bestimme_thema(text: str) -> tuple[str | None, int]:
    treffer = {
        thema: sum(1 for wort in stichworte if wort in text)
        for thema, stichworte in THEMEN.items()
    }
    thema, anzahl = max(treffer.items(), key=lambda paar: paar[1])
    return (thema, anzahl) if anzahl else (None, 0)


def bewerte(nachrichten: list[dict[str, str]]) -> tuple[int, str | None, dict]:
    fragen = "\n".join(n["content"] for n in nachrichten if n["role"] == "user")
    antworten = "\n".join(n["content"] for n in nachrichten if n["role"] == "assistant")
    frage_norm = normalisiere(fragen)
    antwort_norm = normalisiere(antworten)
    gesamt_norm = f"{frage_norm} {antwort_norm}"

    steuer_treffer = sorted(wort for wort in STEUERBEGRIFFE if wort in frage_norm)
    if not steuer_treffer:
        return 0, None, {"ablehnung": "keine_steuerfrage"}
    if any(phrase in antwort_norm for phrase in UNERWUENSCHTE_ANTWORTEN):
        return 0, None, {"ablehnung": "nicht_verwendbare_antwort"}
    if not any(wort in antwort_norm for wort in STEUERBEGRIFFE):
        return 0, None, {"ablehnung": "antwort_ohne_steuerbezug"}

    thema, themen_treffer = bestimme_thema(frage_norm)
    if thema is None:
        return 0, None, {"ablehnung": "nicht_alltagsnah_zuordenbar"}
    if any(wort in frage_norm for wort in FACHGEBIET_OHNE_ALLTAGSBEZUG) and themen_treffer < 2:
        return 0, None, {"ablehnung": "reines_spezialthema"}

    paragraphen = sorted(set(PARAGRAPH.findall(antworten)))
    jahre = sorted({int(jahr) for jahr in JAHR.findall(gesamt_norm)})
    punkte = min(16, 4 * len(steuer_treffer))
    punkte += min(6, 2 * themen_treffer)
    punkte += 4 if paragraphen else 0
    punkte += 2 if any(k in antwort_norm for k in ("estg", "ustg", "ao ", "erbstg")) else 0
    punkte += 2 if "?" in fragen else 0
    punkte += 2 if len(nachrichten) > 2 else 0
    if "um die frage zu beantworten" in antwort_norm or "hier sind die wichtigsten punkte" in antwort_norm:
        punkte -= 2
    if jahre and max(jahre) <= 2021:
        punkte -= 2

    details = {
        "steuerbegriffe": steuer_treffer,
        "paragraphen": paragraphen[:20],
        "erkannte_jahre": jahre,
        "themen_treffer": themen_treffer,
    }
    if punkte < 12:
        details["ablehnung"] = "qualitaetswert_zu_niedrig"
        return punkte, thema, details
    return punkte, thema, details


def kandidat(source: str, laufende_nummer: int, rohdaten: dict) -> tuple[dict | None, str]:
    nachrichten = standardisiere_nachrichten(rohdaten)
    strukturfehler = pruefe_struktur(nachrichten)
    if strukturfehler:
        return None, strukturfehler
    punkte, thema, details = bewerte(nachrichten)
    if "ablehnung" in details:
        return None, details["ablehnung"]

    erste_frage = next(n["content"] for n in nachrichten if n["role"] == "user")
    fingerabdruck = hashlib.sha256(normalisiere(erste_frage).encode("utf-8")).hexdigest()
    quell_id = str(rohdaten.get("id") or laufende_nummer)
    return {
        "id": f"{source}-{quell_id}",
        "quelle": source,
        "quell_id": quell_id,
        "thema": thema,
        "qualitaetswert": punkte,
        "status": "ungepruefter_trainingskandidat",
        "rechtsstand_pruefen": True,
        "nicht_fuer_qdrant": True,
        "frage_fingerabdruck": fingerabdruck,
        "merkmale": details,
        "messages": nachrichten,
    }, "akzeptiert"


def ist_strenger_sprachkandidat(eintrag: dict) -> bool:
    """Begrenzt zeit- und betragsabhängige Falschaussagen im Sprachtraining."""
    antworten = "\n".join(
        nachricht["content"]
        for nachricht in eintrag["messages"]
        if nachricht["role"] == "assistant"
    )
    antwort_norm = normalisiere(antworten)
    if eintrag.get("id") in MANUELL_NICHT_FREIGEGEBENE_IDS:
        return False
    # OpenLegal enthält wertvolle Dialogformen, aber keine belastbare Fundstelle
    # (Gericht, Datum, Aktenzeichen). Die erste Stichprobe zeigte dadurch nicht
    # prüfbare und teils veraltete Urteilszusammenfassungen. Sie bleiben in der
    # breiten Prüfliste, gelangen jedoch nicht in die strengere Vorauswahl.
    if eintrag.get("quelle") == "openlegal":
        return False
    if eintrag["merkmale"]["erkannte_jahre"]:
        return False
    if not eintrag["merkmale"]["paragraphen"]:
        return False
    if DYNAMISCHER_WERT.search(antworten):
        return False
    if any(
        phrase in antwort_norm
        for phrase in ("geplante änderung", "gesetzentwurf", "zukünftig soll")
    ):
        return False
    if any(phrase in antwort_norm for phrase in RISIKANTE_TRAININGSFORMULIERUNGEN):
        return False
    return True


def in_heap(heaps: dict, schluessel: tuple[str, str], eintrag: dict, limit: int) -> None:
    # Der Hash macht Gleichstände stabil und verhindert einen Vergleich der Dicts.
    tie = int(eintrag["frage_fingerabdruck"][:16], 16)
    element = (eintrag["qualitaetswert"], tie, eintrag)
    heap = heaps[schluessel]
    if len(heap) < limit:
        heapq.heappush(heap, element)
    elif element[:2] > heap[0][:2]:
        heapq.heapreplace(heap, element)


def main() -> None:
    for pfad in QUELLEN.values():
        if not pfad.is_file():
            raise FileNotFoundError(pfad)

    heaps: dict[tuple[str, str], list] = defaultdict(list)
    statistik = Counter()
    akzeptiert_vor_quote = Counter()
    bekannte_fragen: set[str] = set()

    for source, pfad in QUELLEN.items():
        with pfad.open("r", encoding="utf-8") as datei:
            for nummer, zeile in enumerate(datei, 1):
                statistik[f"gelesen_{source}"] += 1
                try:
                    roh = json.loads(zeile)
                except json.JSONDecodeError:
                    statistik["ungueltiges_json"] += 1
                    continue
                eintrag, grund = kandidat(source, nummer, roh)
                if eintrag is None:
                    statistik[f"abgelehnt_{grund}"] += 1
                    continue
                fingerabdruck = eintrag["frage_fingerabdruck"]
                if fingerabdruck in bekannte_fragen:
                    statistik["abgelehnt_doppelte_frage"] += 1
                    continue
                bekannte_fragen.add(fingerabdruck)
                akzeptiert_vor_quote[(source, eintrag["thema"])] += 1
                in_heap(heaps, (source, eintrag["thema"]), eintrag, QUOTEN[source])

    ausgewaehlt = []
    for heap in heaps.values():
        ausgewaehlt.extend(element[2] for element in heap)
    ausgewaehlt.sort(key=lambda x: (x["thema"], -x["qualitaetswert"], x["id"]))

    ZIEL_ORDNER.mkdir(parents=True, exist_ok=True)
    kandidaten_pfad = ZIEL_ORDNER / "kandidaten_alltagsnah.jsonl"
    with kandidaten_pfad.open("w", encoding="utf-8", newline="\n") as datei:
        for eintrag in ausgewaehlt:
            datei.write(json.dumps(eintrag, ensure_ascii=False) + "\n")

    strenge_kandidaten = [eintrag for eintrag in ausgewaehlt if ist_strenger_sprachkandidat(eintrag)]
    for eintrag in strenge_kandidaten:
        eintrag["status"] = "ungepruefter_sprachtrainingskandidat_streng"
        eintrag["verwendungszweck"] = "Sprach- und Fallverständnis; keine konkreten Steuerwerte lernen"
    with (ZIEL_ORDNER / "sprachtraining_streng.jsonl").open(
        "w", encoding="utf-8", newline="\n"
    ) as datei:
        for eintrag in strenge_kandidaten:
            datei.write(json.dumps(eintrag, ensure_ascii=False) + "\n")

    # Gleichmäßig verteilte, deterministische Prüfstichprobe: bis zu 20 je Thema.
    pro_thema = defaultdict(list)
    for eintrag in ausgewaehlt:
        pro_thema[eintrag["thema"]].append(eintrag)
    stichprobe = []
    for thema in THEMEN:
        kandidaten = sorted(pro_thema.get(thema, []), key=lambda x: x["frage_fingerabdruck"])
        stichprobe.extend(kandidaten[:20])
    (ZIEL_ORDNER / "pruefstichprobe.json").write_text(
        json.dumps(stichprobe, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    strenge_pro_thema = defaultdict(list)
    for eintrag in strenge_kandidaten:
        strenge_pro_thema[eintrag["thema"]].append(eintrag)
    strenge_stichprobe = []
    for thema in THEMEN:
        kandidaten = sorted(
            strenge_pro_thema.get(thema, []), key=lambda x: x["frage_fingerabdruck"]
        )
        strenge_stichprobe.extend(kandidaten[:10])
    (ZIEL_ORDNER / "pruefstichprobe_streng.json").write_text(
        json.dumps(strenge_stichprobe, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    bericht = {
        "hinweis": "Alle Antworten sind ungeprüfte Trainingskandidaten und kein RAG-Wissen.",
        "quellen": {name: str(pfad) for name, pfad in QUELLEN.items()},
        "quoten_pro_thema": QUOTEN,
        "statistik": dict(sorted(statistik.items())),
        "akzeptiert_vor_quote": {
            f"{source} | {thema}": anzahl
            for (source, thema), anzahl in sorted(akzeptiert_vor_quote.items())
        },
        "ausgewaehlt": len(ausgewaehlt),
        "sprachtraining_streng": len(strenge_kandidaten),
        "stichprobe": len(stichprobe),
        "stichprobe_streng": len(strenge_stichprobe),
        "ausgewaehlt_nach_thema": dict(sorted(Counter(x["thema"] for x in ausgewaehlt).items())),
        "ausgewaehlt_nach_quelle": dict(sorted(Counter(x["quelle"] for x in ausgewaehlt).items())),
        "sprachtraining_streng_nach_thema": dict(
            sorted(Counter(x["thema"] for x in strenge_kandidaten).items())
        ),
    }
    (ZIEL_ORDNER / "filterbericht.json").write_text(
        json.dumps(bericht, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(bericht, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
