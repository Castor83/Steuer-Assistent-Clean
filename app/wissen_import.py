from pathlib import Path
from bs4 import BeautifulSoup
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import hashlib
from modell_ressourcen import MODELL_RESSOURCEN


# --------------------------------------------------
# Einstellungen
# --------------------------------------------------

QUELLE = Path("wissen/quellen/estg_9.html")
COLLECTION = "steuerwissen"

client = QdrantClient(path="daten/qdrant")


# --------------------------------------------------
# HTML lesen und Text extrahieren
# --------------------------------------------------

print("Lese Quelle:", QUELLE)

html = QUELLE.read_text(encoding="cp1252")

soup = BeautifulSoup(html, "html.parser")

# Entfernt unnötige Elemente
for element in soup(["script", "style", "nav", "header", "footer"]):
    element.decompose()

text = soup.get_text("\n")

# Leere Zeilen entfernen
zeilen = [
    zeile.strip()
    for zeile in text.splitlines()
    if zeile.strip()
]

text = "\n".join(zeilen)

print("Text erfolgreich extrahiert.")
print("Zeichen:", len(text))


# --------------------------------------------------
# Text in Abschnitte aufteilen
# --------------------------------------------------

MAX_ZEICHEN = 1200

abschnitte = []

aktueller_abschnitt = ""

for zeile in zeilen:

    if len(aktueller_abschnitt) + len(zeile) > MAX_ZEICHEN:

        if aktueller_abschnitt.strip():
            abschnitte.append(aktueller_abschnitt.strip())

        aktueller_abschnitt = ""

    aktueller_abschnitt += zeile + " "

if aktueller_abschnitt.strip():
    abschnitte.append(aktueller_abschnitt.strip())


print("Abschnitte:", len(abschnitte))


# --------------------------------------------------
# Collection vorbereiten
# --------------------------------------------------


if not client.collection_exists(COLLECTION):

    test_embedding = MODELL_RESSOURCEN.embedding(
        "qwen3-embedding:4b", "Test"
    )["embeddings"][0]

    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(
            size=len(test_embedding),
            distance=Distance.COSINE,
        ),
    )

    print("Collection erstellt.")

else:
    print("Collection bereits vorhanden.")

# --------------------------------------------------
# Embeddings erzeugen
# --------------------------------------------------

points = []

for nummer, abschnitt in enumerate(abschnitte):

    print(
        f"Embedding {nummer + 1}/{len(abschnitte)}..."
    )

    embedding = MODELL_RESSOURCEN.embedding(
        "qwen3-embedding:4b", abschnitt
    )["embeddings"][0]

    # Eindeutige ID erzeugen
    hash_id = hashlib.md5(
        abschnitt.encode("utf-8")
    ).hexdigest()

    point_id = int(hash_id[:12], 16)

    points.append(
        PointStruct(
            id=point_id,
            vector=embedding,
            payload={
                "text": abschnitt,
                "quelle": "Einkommensteuergesetz",
                "paragraph": "§ 9 EStG",
                "steuerjahr": 2025,
                "kategorie": "Werbungskosten",
                "datei": QUELLE.name,
            },
        )
    )


# --------------------------------------------------
# In Qdrant speichern
# --------------------------------------------------

client.upsert(
    collection_name=COLLECTION,
    points=points,
)

print()
print("====================================")
print("IMPORT ERFOLGREICH")
print("====================================")
print("Quelle:", QUELLE)
print("Abschnitte:", len(points))
print("Collection:", COLLECTION)

client.close()
