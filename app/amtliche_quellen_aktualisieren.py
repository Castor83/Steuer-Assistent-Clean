"""Aktualisiert die lokale Wissensbasis aus festgelegten amtlichen Rechtsquellen.

Es werden ausschließlich URLs von Gesetze im Internet verwendet. Bei fehlender
Internetverbindung oder einem Fehler bleibt die vorhandene Wissensbasis erhalten.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from hashlib import sha256
import json
from pathlib import Path
import re
from shutil import which
from subprocess import run

from bs4 import BeautifulSoup
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct
from modell_ressourcen import MODELL_RESSOURCEN


PROJECT_ROOT = Path(__file__).resolve().parent.parent
QDRANT_ORDNER = PROJECT_ROOT / "daten" / "qdrant"
STATUS_DATEI = QDRANT_ORDNER / "amtliche_quellen_status.json"
COLLECTION = "steuerwissen"
EMBEDDING_MODEL = "qwen3-embedding:4b"
AKTUALISIERUNGSINTERVALL = timedelta(days=30)
QUELLEN = (
    {
        "id": "estg_gesamt",
        "titel": "Einkommensteuergesetz (amtlicher Gesamttext)",
        "paragraph": "EStG",
        "kategorie": "Einkommensteuer",
        "url": "https://www.gesetze-im-internet.de/estg/BJNR010050934.html",
    },
    {
        "id": "betrkv_gesamt",
        "titel": "Betriebskostenverordnung (amtlicher Gesamttext)",
        "paragraph": "BetrKV",
        "kategorie": "Vermietung und Betriebskosten",
        "url": "https://www.gesetze-im-internet.de/betrkv/BJNR234700003.html",
    },
)


def lade_status() -> dict:
    if not STATUS_DATEI.exists():
        return {}
    try:
        return json.loads(STATUS_DATEI.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def speichere_status(status: dict) -> None:
    STATUS_DATEI.parent.mkdir(parents=True, exist_ok=True)
    STATUS_DATEI.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def lade_amtlichen_text(url: str) -> str:
    curl = which("curl.exe") or which("curl")
    if not curl:
        raise RuntimeError("Kein sicherer Web-Abruf vorhanden")
    ergebnis = run(
        [
            curl, "--fail", "--location", "--silent", "--show-error",
            "--ssl-revoke-best-effort", "--max-time", "30", url,
        ],
        capture_output=True,
        check=True,
    )
    html = ergebnis.stdout.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "nav", "header", "footer"]):
        element.decompose()
    zeilen = [zeile.strip() for zeile in soup.get_text("\n").splitlines() if zeile.strip()]
    return "\n".join(zeilen)


def abschnitte(text: str, maximale_laenge: int = 1400) -> list[tuple[str, str]]:
    """Teilt einen Gesetzestext abschnittsweise und mit Paragraphenhinweis auf."""
    teile = re.split(r"(?=^§\s*\d+[a-zA-Z]*\b)", text, flags=re.MULTILINE)
    ergebnis: list[tuple[str, str]] = []
    for teil in teile:
        teil = teil.strip()
        if not teil:
            continue
        treffer = re.match(r"(§\s*\d+[a-zA-Z]*(?:\s+[^\n]{0,100})?)", teil)
        hinweis = treffer.group(1) if treffer else "Allgemeiner Gesetzestext"
        woerter = teil.split()
        aktueller: list[str] = []
        laenge = 0
        for wort in woerter:
            if aktueller and laenge + len(wort) + 1 > maximale_laenge:
                ergebnis.append((" ".join(aktueller), hinweis))
                aktueller, laenge = [], 0
            aktueller.append(wort)
            laenge += len(wort) + 1
        if aktueller:
            ergebnis.append((" ".join(aktueller), hinweis))
    return ergebnis


def punkt_id(quellen_id: str, text: str) -> int:
    return int(sha256(f"{quellen_id}\n{text}".encode("utf-8")).hexdigest()[:15], 16)


def aktualisiere(anzeigen: bool = True, erzwingen: bool = False) -> bool:
    status = lade_status()
    heute = date.today()
    letztes_datum = status.get("letzte_pruefung")
    if not erzwingen and letztes_datum:
        try:
            if heute - date.fromisoformat(letztes_datum) < AKTUALISIERUNGSINTERVALL:
                return False
        except ValueError:
            pass

    client = QdrantClient(path=QDRANT_ORDNER)
    try:
        if not client.collection_exists(COLLECTION):
            if anzeigen:
                print("Amtliche Aktualisierung uebersprungen: Wissensdatenbank fehlt.")
            return False

        neu = False
        neue_hashes: dict[str, str] = {}
        for quelle in QUELLEN:
            try:
                text = lade_amtlichen_text(quelle["url"])
            except Exception as fehler:
                if anzeigen:
                    print(f"Amtliche Quelle nicht erreichbar: {quelle['titel']} ({fehler})")
                continue
            inhalts_hash = sha256(text.encode("utf-8")).hexdigest()
            neue_hashes[quelle["id"]] = inhalts_hash
            if status.get("hashes", {}).get(quelle["id"]) == inhalts_hash:
                continue

            stuecke = abschnitte(text)
            if not stuecke:
                continue
            if anzeigen:
                print(f"Aktualisiere amtliche Quelle: {quelle['titel']} ({len(stuecke)} Abschnitte)")
            version = heute.isoformat()
            punkte = []
            paketgroesse = 32
            for start in range(0, len(stuecke), paketgroesse):
                paket = stuecke[start:start + paketgroesse]
                if anzeigen:
                    print(f"  Embedding {min(start + paketgroesse, len(stuecke))}/{len(stuecke)}")
                embeddings = MODELL_RESSOURCEN.embedding(
                    EMBEDDING_MODEL, [inhalt for inhalt, _ in paket]
                )["embeddings"]
                for versatz, ((inhalt, paragraph), embedding) in enumerate(zip(paket, embeddings), start=1):
                    nummer = start + versatz
                    punkte.append(PointStruct(
                        id=punkt_id(quelle["id"], inhalt),
                        vector=embedding,
                        payload={
                            "text": inhalt,
                            "quelle": quelle["titel"],
                            "herausgeber": "Bundesministerium der Justiz / Bundesamt fuer Justiz",
                            "paragraph": paragraph,
                            "steuerjahr": heute.year,
                            "stand_abgerufen": version,
                            "url": quelle["url"],
                            "kategorie": quelle["kategorie"],
                            "quelle_id": quelle["id"],
                            "quellen_version": version,
                            "abschnitt": nummer,
                        },
                    ))
            client.upsert(collection_name=COLLECTION, points=punkte)
            client.delete(
                collection_name=COLLECTION,
                points_selector=Filter(
                    must=[FieldCondition(key="quelle_id", match=MatchValue(value=quelle["id"]))],
                    must_not=[FieldCondition(key="quellen_version", match=MatchValue(value=version))],
                ),
            )
            neu = True

        status["letzte_pruefung"] = heute.isoformat()
        status["hashes"] = {**status.get("hashes", {}), **neue_hashes}
        speichere_status(status)
        if anzeigen and neu:
            print("Amtliche Wissensbasis aktualisiert.")
        return neu
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aktualisiert amtliche Steuerquellen.")
    parser.add_argument("--erzwingen", action="store_true", help="Prueft alle Quellen sofort.")
    argumente = parser.parse_args()
    aktualisiere(anzeigen=True, erzwingen=argumente.erzwingen)
