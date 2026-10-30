from qdrant_client import QdrantClient
from modell_ressourcen import MODELL_RESSOURCEN


COLLECTION = "steuerwissen"
EMBEDDING_MODEL = "qwen3-embedding:4b"
SCORE_THRESHOLD = 0.4

frage = input("Deine Frage: ")

# Qdrant öffnen
client = QdrantClient(path="daten/qdrant")

# Frage in Embedding umwandeln
frage_embedding = MODELL_RESSOURCEN.embedding(
    EMBEDDING_MODEL, frage
)["embeddings"][0]

# Suche
ergebnisse = client.query_points(
    collection_name=COLLECTION,
    query=frage_embedding,
    limit=5,
    score_threshold=SCORE_THRESHOLD,
).points

print()
print("--- RELEVANTE INFORMATIONEN ---")
print()

if not ergebnisse:
    print("Keine ausreichend passenden Quellen gefunden.")

for ergebnis in ergebnisse:

    payload = ergebnis.payload

    print(f"Score: {ergebnis.score:.4f}")
    print(f"Quelle: {payload.get('quelle')}")
    print(f"Paragraph: {payload.get('paragraph')}")
    print(f"Steuerjahr: {payload.get('steuerjahr')}")
    print()
    print(payload.get("text"))
    print()
    print("-" * 60)

client.close()
