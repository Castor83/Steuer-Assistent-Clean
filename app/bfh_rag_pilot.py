"""Bereitet einen kleinen, getrennten BFH-RAG-Pilotbestand vor.

Die Entscheidungen sind Rechtsprechung mit historischem Entscheidungsdatum und
kein Ersatz für aktuelle Gesetze. Ohne ``--importieren`` wird Qdrant nicht
verändert. Der Pilot nutzt ausschließlich Titel und Leitsatz zur Suche; der
amtliche Volltext bleibt über die BFH-URL nachvollziehbar.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from hashlib import sha256
import json
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROHDATEN = (
    PROJECT_ROOT
    / "testDaten"
    / "bfh_entscheidungen_roh"
    / "csv_datensatz"
    / "CE-BFH_2025-01-14_DE_CSV_Datensatz.csv"
)
ZIEL_ORDNER = PROJECT_ROOT / "testDaten" / "bfh_rag_pilot"
PILOT_DATEI = ZIEL_ORDNER / "bfh_pilot.jsonl"
BERICHT_DATEI = ZIEL_ORDNER / "bfh_pilot_bericht.json"
SUCHTEST_DATEI = ZIEL_ORDNER / "bfh_pilot_suchtest.json"
QDRANT_ORDNER = PROJECT_ROOT / "daten" / "qdrant_bfh_pilot"
COLLECTION = "bfh_steuerrecht_pilot_v2"
EMBEDDING_MODEL = "qwen3-embedding:4b"
DATENSTAND = "2025-01-14"
CSV_FELDGRENZE = 10_000_000
TESTFAELLE = (
    ("Wann kann ich Kosten für mein häusliches Arbeitszimmer als Werbungskosten abziehen?", "Arbeitnehmer"),
    ("Wie werden Verluste und Werbungskosten bei der Vermietung einer Immobilie behandelt?", "Vermietung und Immobilien"),
    ("Kann ich beim Betrieb einer Photovoltaikanlage Vorsteuer abziehen?", "Umsatzsteuer"),
    ("Wie wird ein Grundstück bei einer Erbschaft steuerlich bewertet?", "Erbschaft und Schenkung"),
    ("Wann besteht für ein volljähriges Kind in Ausbildung Anspruch auf Kindergeld?", "Familie und Kindergeld"),
)

STEUERGESETZE = re.compile(
    r"\b(?:AO|AStG|BewG|EStDV|EStG|ErbStG|GewStG|GrEStG|"
    r"InvStG|KStG|LStDV|SolzG|UStDV|UStG)\b",
    re.IGNORECASE,
)
STEUERWOERTER = re.compile(
    r"einkommensteuer|umsatzsteuer|lohnsteuer|erbschaftsteuer|schenkungsteuer|"
    r"gewerbesteuer|körperschaftsteuer|grundsteuer|einkünfte|werbungskosten|"
    r"betriebsausgaben|vermietung|vorsteuer|kindergeld|abschreibung",
    re.IGNORECASE,
)
THEMEN = (
    ("Umsatzsteuer", re.compile(r"\bUStG\b|umsatzsteuer|vorsteuer", re.I)),
    ("Erbschaft und Schenkung", re.compile(r"\bErbStG\b|erbschaft|schenkung|nachlass", re.I)),
    ("Familie und Kindergeld", re.compile(r"kindergeld|\bEStG § (?:32|6[2-9]|7[0-8])\b", re.I)),
    ("Vermietung und Immobilien", re.compile(r"\bEStG § 21\b|vermiet|verpacht|immobil", re.I)),
    ("Arbeitnehmer", re.compile(r"\bEStG § (?:9|19)\b|arbeitszimmer|werbungskosten|haushaltsführung", re.I)),
    ("Unternehmen", re.compile(r"\b(?:GewStG|KStG)\b|betriebsausgabe|\bEStG § 15\b", re.I)),
)


def ist_steuerlich_relevant(zeile: dict[str, str]) -> bool:
    normen = zeile.get("normen", "") or ""
    titel = zeile.get("titel", "") or ""
    leitsatz = zeile.get("text_leitsatz", "") or ""
    return bool(STEUERGESETZE.search(normen) or STEUERWOERTER.search(f"{titel} {leitsatz}"))


def bestimme_thema(zeile: dict[str, str]) -> str:
    text = " ".join(
        (zeile.get("normen", "") or "", zeile.get("titel", "") or "", zeile.get("text_leitsatz", "") or "")
    )
    for thema, muster in THEMEN:
        if muster.search(text):
            return thema
    return "Sonstige Alltagssteuern"


def suchtext(zeile: dict[str, str], maximale_laenge: int = 6000) -> str:
    teile = [
        f"BFH-Entscheidung {zeile.get('aktenzeichen', '').strip()}",
        f"Datum: {zeile.get('datum', '').strip()}",
        f"Titel: {zeile.get('titel', '').strip()}",
        f"Normen: {zeile.get('normen', '').strip()}",
        f"Leitsatz: {zeile.get('text_leitsatz', '').strip()}",
    ]
    text = "\n".join(teil for teil in teile if not teil.endswith(": "))
    return text[:maximale_laenge].strip()


def erstelle_eintrag(zeile: dict[str, str]) -> dict:
    entscheidung_id = (zeile.get("bfh_id") or zeile.get("doc_id") or "").strip()
    return {
        "id": entscheidung_id,
        "quelle": "Bundesfinanzhof – Entscheidungen online",
        "quellensammlung": "CE-BFH 2025-01-14",
        "aktenzeichen": (zeile.get("aktenzeichen") or "").strip(),
        "ecli": (zeile.get("ecli") or "").strip(),
        "datum": (zeile.get("datum") or "").strip(),
        "entscheidungsjahr": int(zeile.get("entscheidungsjahr") or 0),
        "titel": (zeile.get("titel") or "").strip(),
        "thema": bestimme_thema(zeile),
        "leitsatz": (zeile.get("text_leitsatz") or "").strip(),
        "normen": (zeile.get("normen") or "").strip(),
        "url": (zeile.get("url_html") or "").strip(),
        "status": "historische_bfh_rechtsprechung",
        "datenstand": DATENSTAND,
        "rechtsstand_separat_pruefen": True,
        "suchtext": suchtext(zeile),
    }


def bereite_vor(limit: int = 300, mindestjahr: int = 2022) -> dict:
    if not ROHDATEN.is_file():
        raise FileNotFoundError(f"BFH-Rohdaten fehlen: {ROHDATEN}")

    csv.field_size_limit(CSV_FELDGRENZE)
    gelesen = 0
    relevant = []
    with ROHDATEN.open("r", encoding="utf-8-sig", newline="") as datei:
        for zeile in csv.DictReader(datei):
            gelesen += 1
            jahr = int(zeile.get("entscheidungsjahr") or 0)
            if jahr < mindestjahr or not ist_steuerlich_relevant(zeile):
                continue
            eintrag = erstelle_eintrag(zeile)
            if not eintrag["id"] or len(eintrag["suchtext"]) < 100:
                continue
            relevant.append(eintrag)

    relevant.sort(key=lambda x: (x["datum"], x["id"]), reverse=True)
    themennamen = [thema for thema, _ in THEMEN] + ["Sonstige Alltagssteuern"]
    quote = max(1, limit // len(themennamen))
    ausgewaehlt = []
    ausgewaehlte_ids = set()
    for thema in themennamen:
        for eintrag in (x for x in relevant if x["thema"] == thema):
            if sum(1 for x in ausgewaehlt if x["thema"] == thema) >= quote:
                break
            ausgewaehlt.append(eintrag)
            ausgewaehlte_ids.add(eintrag["id"])
    if len(ausgewaehlt) < limit:
        for eintrag in relevant:
            if eintrag["id"] in ausgewaehlte_ids:
                continue
            ausgewaehlt.append(eintrag)
            ausgewaehlte_ids.add(eintrag["id"])
            if len(ausgewaehlt) >= limit:
                break
    ausgewaehlt.sort(key=lambda x: (x["thema"], x["datum"], x["id"]), reverse=True)
    ZIEL_ORDNER.mkdir(parents=True, exist_ok=True)
    with PILOT_DATEI.open("w", encoding="utf-8", newline="\n") as datei:
        for eintrag in ausgewaehlt:
            datei.write(json.dumps(eintrag, ensure_ascii=False) + "\n")

    bericht = {
        "hinweis": "BFH-Rechtsprechung, kein aktueller Gesetzesbestand",
        "datenstand": DATENSTAND,
        "mindestjahr": mindestjahr,
        "gelesen": gelesen,
        "steuerlich_relevant_ab_mindestjahr": len(relevant),
        "pilot_ausgewaehlt": len(ausgewaehlt),
        "nach_entscheidungsjahr": dict(
            sorted(Counter(x["entscheidungsjahr"] for x in ausgewaehlt).items())
        ),
        "nach_thema": dict(sorted(Counter(x["thema"] for x in ausgewaehlt).items())),
        "ausgabedatei": str(PILOT_DATEI),
        "qdrant_getrennt": str(QDRANT_ORDNER),
        "qdrant_collection": COLLECTION,
        "qdrant_importiert": False,
    }
    BERICHT_DATEI.write_text(
        json.dumps(bericht, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return bericht


def punkt_id(eintrag_id: str) -> int:
    return int(sha256(eintrag_id.encode("utf-8")).hexdigest()[:15], 16)


def lade_pilot() -> list[dict]:
    if not PILOT_DATEI.is_file():
        raise FileNotFoundError("Pilotdatei fehlt. Zuerst ohne --importieren vorbereiten.")
    with PILOT_DATEI.open("r", encoding="utf-8") as datei:
        return [json.loads(zeile) for zeile in datei if zeile.strip()]


def importiere() -> int:
    from modell_ressourcen import MODELL_RESSOURCEN
    from qdrant_client import QdrantClient
    from qdrant_client.models import Distance, PointStruct, VectorParams

    eintraege = lade_pilot()
    if not eintraege:
        raise RuntimeError("Pilotdatei ist leer.")
    client = QdrantClient(path=QDRANT_ORDNER)
    try:
        if client.collection_exists(COLLECTION):
            client.delete_collection(COLLECTION)
        paketgroesse = 16
        importiert = 0
        for start in range(0, len(eintraege), paketgroesse):
            paket = eintraege[start:start + paketgroesse]
            embeddings = MODELL_RESSOURCEN.embedding(
                EMBEDDING_MODEL, [eintrag["suchtext"] for eintrag in paket]
            )["embeddings"]
            if not client.collection_exists(COLLECTION):
                client.create_collection(
                    collection_name=COLLECTION,
                    vectors_config=VectorParams(size=len(embeddings[0]), distance=Distance.COSINE),
                )
            punkte = []
            for eintrag, embedding in zip(paket, embeddings):
                payload = {k: v for k, v in eintrag.items() if k != "suchtext"}
                payload["text"] = eintrag["suchtext"]
                punkte.append(
                    PointStruct(id=punkt_id(eintrag["id"]), vector=embedding, payload=payload)
                )
            client.upsert(collection_name=COLLECTION, points=punkte)
            importiert += len(punkte)
            print(f"BFH-Pilot: {importiert}/{len(eintraege)} eingebettet")
    finally:
        client.close()

    bericht = json.loads(BERICHT_DATEI.read_text(encoding="utf-8"))
    bericht["qdrant_importiert"] = True
    bericht["qdrant_punkte"] = importiert
    bericht["embedding_modell"] = EMBEDDING_MODEL
    BERICHT_DATEI.write_text(
        json.dumps(bericht, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return importiert


def suche(frage: str, limit: int = 5) -> list[dict]:
    from modell_ressourcen import MODELL_RESSOURCEN
    from qdrant_client import QdrantClient

    client = QdrantClient(path=QDRANT_ORDNER)
    try:
        if not client.collection_exists(COLLECTION):
            raise RuntimeError("BFH-Pilot wurde noch nicht importiert.")
        embedding = MODELL_RESSOURCEN.embedding(EMBEDDING_MODEL, frage)["embeddings"][0]
        treffer = client.query_points(
            collection_name=COLLECTION, query=embedding, limit=limit, with_payload=True
        ).points
        return [
            {"score": round(t.score, 4), **(t.payload or {})}
            for t in treffer
        ]
    finally:
        client.close()


def pruefe_suche(limit: int = 3) -> list[dict]:
    """Erzeugt einen reproduzierbaren Treffertest ohne Modellantwort."""
    from modell_ressourcen import MODELL_RESSOURCEN
    from qdrant_client import QdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    embeddings = MODELL_RESSOURCEN.embedding(
        EMBEDDING_MODEL, [frage for frage, _ in TESTFAELLE]
    )["embeddings"]
    client = QdrantClient(path=QDRANT_ORDNER)
    try:
        if not client.collection_exists(COLLECTION):
            raise RuntimeError("BFH-Pilot wurde noch nicht importiert.")
        ergebnis = []
        for (frage, thema), embedding in zip(TESTFAELLE, embeddings):
            punkte = client.query_points(
                collection_name=COLLECTION,
                query=embedding,
                query_filter=Filter(
                    must=[FieldCondition(key="thema", match=MatchValue(value=thema))]
                ),
                limit=limit,
                with_payload=True,
            ).points
            ergebnis.append(
                {
                    "frage": frage,
                    "themenfilter": thema,
                    "treffer": [
                        {
                            "score": round(punkt.score, 4),
                            "aktenzeichen": punkt.payload.get("aktenzeichen"),
                            "datum": punkt.payload.get("datum"),
                            "titel": punkt.payload.get("titel"),
                            "normen": punkt.payload.get("normen"),
                            "url": punkt.payload.get("url"),
                        }
                        for punkt in punkte
                    ],
                }
            )
    finally:
        client.close()

    SUCHTEST_DATEI.write_text(
        json.dumps(ergebnis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return ergebnis


def main() -> None:
    parser = argparse.ArgumentParser(description="Getrennter BFH-RAG-Pilotbestand")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--mindestjahr", type=int, default=2022)
    parser.add_argument("--importieren", action="store_true")
    parser.add_argument("--suchtest", action="store_true")
    parser.add_argument("--frage")
    argumente = parser.parse_args()
    if argumente.frage:
        print(json.dumps(suche(argumente.frage), ensure_ascii=False, indent=2))
    elif argumente.suchtest:
        print(json.dumps(pruefe_suche(), ensure_ascii=False, indent=2))
    elif argumente.importieren:
        print(f"Import abgeschlossen: {importiere()} Entscheidungen")
    else:
        print(json.dumps(bereite_vor(argumente.limit, argumente.mindestjahr), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
