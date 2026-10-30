"""Importiert strukturierte, lokale Quellen in die Qdrant-Collection.

Nur Dateien im Ordner wissen/quellen mit den benötigten Metadaten werden
übernommen. Bereits vorhandene Inhalte erhalten durch ihre Hash-ID stets
dieselbe ID und werden beim erneuten Import aktualisiert, nicht dupliziert.
"""

from hashlib import sha256
import json
from pathlib import Path
from collections import Counter

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from quellen_chunking import embedding_text, quellenkarten_payloads
from modell_ressourcen import MODELL_RESSOURCEN


COLLECTION = "steuerwissen"
EMBEDDING_MODEL = "qwen3-embedding:4b"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUELLEN_ORDNER = PROJECT_ROOT / "wissen" / "quellen"
QDRANT_ORDNER = PROJECT_ROOT / "daten" / "qdrant"
ERFORDERLICHE_FELDER = {
    "titel", "herausgeber", "paragraph", "steuerjahr", "stand_abgerufen",
    "url", "kategorie", "inhalt",
}


def point_id(text: str) -> int:
    """Erzeugt eine stabile, positive ID für einen Quellentext."""
    return int(sha256(text.encode("utf-8")).hexdigest()[:15], 16)


def lade_quellen() -> list[tuple[Path, dict]]:
    quellen = []
    for datei in sorted(QUELLEN_ORDNER.glob("*.json")):
        daten = json.loads(datei.read_text(encoding="utf-8"))
        fehlend = ERFORDERLICHE_FELDER - daten.keys()
        if fehlend:
            print(f"Übersprungen: {datei.name} (fehlend: {', '.join(sorted(fehlend))})")
            continue
        if not daten["inhalt"].strip():
            print(f"Übersprungen: {datei.name} (leerer Inhalt)")
            continue
        quellen.append((datei, daten))
    return quellen


def erwartete_index_payloads(
    quellen: list[tuple[Path, dict]] | None = None,
) -> dict[int, dict]:
    """Berechnet den vollständigen Sollzustand ohne Embeddings zu erzeugen."""
    quellen = lade_quellen() if quellen is None else quellen
    payloads = (
        payload
        for datei, quelle in quellen
        for payload in quellenkarten_payloads(datei, quelle)
    )
    return {
        point_id(
            f"quellenkarte\n{payload['datei']}\n{payload['chunk']}\n"
            f"{payload['text']}"
        ): payload
        for payload in payloads
    }


def pruefe_index_integritaet(
    client: QdrantClient,
    erwartete: dict[int, dict] | None = None,
) -> dict:
    """Prüft exakte Parität zwischen Regelchunks und Quellenkarten-Vektoren."""
    erwartete = erwartete_index_payloads() if erwartete is None else erwartete
    bestand = []
    offset = None
    while True:
        punkte, offset = client.scroll(
            collection_name=COLLECTION,
            limit=512,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        bestand.extend(
            punkt for punkt in punkte
            if (
                (punkt.payload or {}).get("quellenart") == "quellenkarte"
                or str((punkt.payload or {}).get("datei", "")).endswith(".json")
            )
        )
        if offset is None:
            break

    ist = {punkt.id: dict(punkt.payload or {}) for punkt in bestand}
    erwartete_ids = set(erwartete)
    ist_ids = set(ist)
    fehlend = sorted(erwartete_ids - ist_ids, key=str)
    unerwartet = sorted(ist_ids - erwartete_ids, key=str)
    schluessel = [
        (payload.get("datei"), payload.get("chunk")) for payload in ist.values()
    ]
    doppelte = [
        {"datei": datei, "chunk": chunk, "anzahl": anzahl}
        for (datei, chunk), anzahl in Counter(schluessel).items()
        if anzahl > 1
    ]
    abweichende_payloads = []
    for punkt_id in sorted(erwartete_ids & ist_ids, key=str):
        soll = erwartete[punkt_id]
        vorhanden = ist[punkt_id]
        felder = (
            "datei", "chunk", "chunk_anzahl", "text", "paragraph",
            "suchjahre", "bundesland", "fristtyp",
        )
        abweichungen = [
            feld for feld in felder if vorhanden.get(feld) != soll.get(feld)
        ]
        if abweichungen:
            abweichende_payloads.append({
                "punkt_id": punkt_id,
                "datei": soll.get("datei"),
                "chunk": soll.get("chunk"),
                "abweichende_felder": abweichungen,
            })

    quellkarten = {payload.get("datei") for payload in erwartete.values()}
    ergebnis = {
        "bestanden": not fehlend and not unerwartet and not doppelte and not abweichende_payloads,
        "erwartete_quellkarten": len(quellkarten),
        "erwartete_chunks": len(erwartete),
        "vorhandene_quellenpunkte": len(bestand),
        "fehlende_punkt_ids": fehlend,
        "unerwartete_punkt_ids": unerwartet,
        "doppelte_datei_chunk_paare": doppelte,
        "abweichende_payloads": abweichende_payloads,
    }
    return ergebnis


def main() -> None:
    quellen = lade_quellen()
    if not quellen:
        print("Keine vollständigen JSON-Quellen gefunden.")
        return

    client = QdrantClient(path=QDRANT_ORDNER)
    try:
        if not client.collection_exists(COLLECTION):
            raise RuntimeError(
                f"Collection '{COLLECTION}' fehlt. Starte zuerst wissen_import.py."
            )

        payloads = [
            payload
            for datei, quelle in quellen
            for payload in quellenkarten_payloads(datei, quelle)
        ]
        erwartete = erwartete_index_payloads(quellen)
        points = []
        paketgroesse = 24
        for start in range(0, len(payloads), paketgroesse):
            paket = payloads[start : start + paketgroesse]
            print(f"Embedding {start + 1}-{start + len(paket)}/{len(payloads)}")
            embeddings = MODELL_RESSOURCEN.embedding(
                EMBEDDING_MODEL,
                [embedding_text(payload) for payload in paket],
            )["embeddings"]
            for payload, embedding in zip(paket, embeddings):
                points.append(
                    PointStruct(
                        id=point_id(
                            f"quellenkarte\n{payload['datei']}\n{payload['chunk']}\n"
                            f"{payload['text']}"
                        ),
                        vector=embedding,
                        payload=payload,
                    )
                )

        neue_ids = {punkt.id for punkt in points}
        for start in range(0, len(points), 256):
            client.upsert(collection_name=COLLECTION, points=points[start:start + 256])

        # Erst nach vollstaendig erfolgreichem Upsert werden alte Ganzkarten,
        # ueberholte Hash-Versionen und fruehere Chunk-Zustaende entfernt.
        alte_ids = []
        offset = None
        while True:
            bestand, offset = client.scroll(
                collection_name=COLLECTION,
                limit=512,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            alte_ids.extend(
                punkt.id for punkt in bestand
                if str((punkt.payload or {}).get("datei", "")).endswith(".json")
                and punkt.id not in neue_ids
            )
            if offset is None:
                break
        for start in range(0, len(alte_ids), 256):
            client.delete(
                collection_name=COLLECTION,
                points_selector=alte_ids[start:start + 256],
            )
        integritaet = pruefe_index_integritaet(client, erwartete)
        if not integritaet["bestanden"]:
            raise RuntimeError(
                "Index-Parität fehlgeschlagen: "
                + json.dumps(integritaet, ensure_ascii=False)
            )
        print(
            f"IMPORT ERFOLGREICH: {len(quellen)} Quellen in {len(points)} Chunks; "
            f"{len(alte_ids)} Alt-Punkte entfernt; Parität bestätigt."
        )
    finally:
        client.close()


if __name__ == "__main__":
    main()
