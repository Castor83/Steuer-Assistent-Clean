from qdrant_client import QdrantClient

client = QdrantClient(path="daten/qdrant")

print("Qdrant wurde erfolgreich gestartet.")
print("Collections:", client.get_collections())

client.close()

print("Qdrant wurde sauber geschlossen.")