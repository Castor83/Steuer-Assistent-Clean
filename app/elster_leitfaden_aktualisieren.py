"""Lädt die vollständige amtliche ELSTER-Einkommensteuerhilfe abschnittsweise.

Die Quelle bleibt über ihre offizielle URL nachvollziehbar. Navigation, Skripte
und Seitenelemente werden verworfen; Überschriften und Hilfetexte werden in
kleine, gezielt durchsuchbare Abschnitte für die lokale Qdrant-Datenbank geteilt.
"""

from __future__ import annotations

import argparse
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup, Tag


PROJECT_ROOT = Path(__file__).resolve().parent.parent
QDRANT_ORDNER = PROJECT_ROOT / "daten" / "qdrant"
STATUS_DATEI = PROJECT_ROOT / "daten" / "elster_leitfaden_status.json"
COLLECTION = "steuerwissen"
EMBEDDING_MODEL = "qwen3-embedding:4b"
UNTERSTUETZTE_STEUERJAHRE = (2023, 2024, 2025)
MINDEST_ABSCHNITTE = 100
MINDEST_ZEICHEN = 100_000


def leitfaden_daten(steuerjahr: int) -> dict:
    if steuerjahr not in UNTERSTUETZTE_STEUERJAHRE:
        raise ValueError(
            f"Unterstützt werden nur die Steuerjahre {', '.join(map(str, UNTERSTUETZTE_STEUERJAHRE))}."
        )
    return {
        "steuerjahr": steuerjahr,
        "export_datei": PROJECT_ROOT / "wissen" / "elster" / f"einkommensteuer_{steuerjahr}_komplett.json",
        "quelle_id": f"elster_est_{steuerjahr}_komplett",
        "url": f"https://www.elster.de/eportal/helpGlobal?themaGlobal=help_est_ufa_10_{steuerjahr}",
        "titel": f"ELSTER – vollständige Anleitung zur Einkommensteuererklärung {steuerjahr}",
    }


def lade_html(steuerjahr: int = 2025) -> str:
    daten = leitfaden_daten(steuerjahr)
    anfrage = Request(daten["url"], headers={"User-Agent": "Steuer-Assistent/1.0 ELSTER-Leitfaden"})
    with urlopen(anfrage, timeout=90) as antwort:
        zeichensatz = antwort.headers.get_content_charset() or "utf-8"
        return antwort.read().decode(zeichensatz, errors="replace")


def _zerlege_text(text: str, maximale_laenge: int = 1_400) -> list[str]:
    woerter = text.split()
    ergebnis: list[str] = []
    aktuell: list[str] = []
    laenge = 0
    for wort in woerter:
        if aktuell and laenge + len(wort) + 1 > maximale_laenge:
            ergebnis.append(" ".join(aktuell))
            aktuell, laenge = [], 0
        aktuell.append(wort)
        laenge += len(wort) + 1
    if aktuell:
        ergebnis.append(" ".join(aktuell))
    return ergebnis


def extrahiere_abschnitte(html: str, steuerjahr: int = 2025) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup(["script", "style", "nav", "header", "footer", "button", "form"]):
        element.decompose()

    start = next(
        (
            element
            for element in soup.find_all(["h1", "h2"])
            if f"Anleitung zur Einkommensteuererklärung {steuerjahr}" in element.get_text(" ", strip=True)
        ),
        None,
    )
    if start is None:
        raise RuntimeError("Die erwartete ELSTER-Anleitung wurde auf der amtlichen Seite nicht gefunden.")

    ueberschriften: dict[int, str] = {2: f"Anleitung zur Einkommensteuererklärung {steuerjahr}"}
    sammlung: list[dict] = []
    aktueller_text: list[str] = []

    def abschliessen() -> None:
        text = " ".join(aktueller_text).strip()
        aktueller_text.clear()
        if len(text) < 40:
            return
        pfad = " > ".join(ueberschriften[ebene] for ebene in sorted(ueberschriften))
        for teil in _zerlege_text(text):
            sammlung.append({"abschnitt": pfad, "inhalt": teil})

    for element in start.find_all_next():
        if not isinstance(element, Tag):
            continue
        if element.name in {"h2", "h3", "h4", "h5"}:
            if element is not start:
                abschliessen()
                ebene = int(element.name[1])
                ueberschriften[ebene] = element.get_text(" ", strip=True)
                for tiefer in [wert for wert in ueberschriften if wert > ebene]:
                    del ueberschriften[tiefer]
            continue
        if element.name not in {"p", "li", "td", "th"}:
            continue
        if element.find_parent(["nav", "header", "footer", "form"]):
            continue
        # Bei Tabellen und Listen steckt derselbe Text häufig zusätzlich in
        # untergeordneten p/li/td-Elementen. Nur das jeweils tiefste relevante
        # Element übernehmen, damit der Leitfaden nicht mehrfach indexiert wird.
        if element.find(["p", "li", "td", "th"]):
            continue
        text = element.get_text(" ", strip=True)
        if text:
            aktueller_text.append(text)
    abschliessen()

    # Identische Navigations- oder Tabellenfragmente nur einmal übernehmen.
    eindeutig: list[dict] = []
    gesehen: set[tuple[str, str]] = set()
    for eintrag in sammlung:
        schluessel = (eintrag["abschnitt"], eintrag["inhalt"])
        if schluessel not in gesehen:
            gesehen.add(schluessel)
            eindeutig.append(eintrag)
    return eindeutig


def pruefe_vollstaendigkeit(abschnitte: list[dict]) -> None:
    zeichen = sum(len(eintrag["inhalt"]) for eintrag in abschnitte)
    if len(abschnitte) < MINDEST_ABSCHNITTE or zeichen < MINDEST_ZEICHEN:
        raise RuntimeError(
            f"ELSTER-Abruf unvollständig: nur {len(abschnitte)} Abschnitte und {zeichen} Zeichen."
        )
    pfade = "\n".join(eintrag["abschnitt"] for eintrag in abschnitte)
    erforderlich = (
        "Hauptvordruck",
        "Anlage N",
        "Anlage Kind",
        "Anlage KAP",
        "Anlage V",
        "Anlage Vorsorgeaufwand",
        "Anlage Sonderausgaben",
        "Außergewöhnliche Belastungen",
    )
    fehlend = [titel for titel in erforderlich if titel not in pfade]
    if fehlend:
        raise RuntimeError(f"ELSTER-Bereiche fehlen: {', '.join(fehlend)}")


def punkt_id(quelle_id: str, abschnitt: str, inhalt: str) -> int:
    text = f"{quelle_id}\n{abschnitt}\n{inhalt}"
    return int(sha256(text.encode("utf-8")).hexdigest()[:15], 16)


def aktualisiere(
    nur_pruefen: bool = False,
    exportieren: bool = False,
    steuerjahr: int = 2025,
) -> dict:
    daten = leitfaden_daten(steuerjahr)
    html = lade_html(steuerjahr)
    abschnitte = extrahiere_abschnitte(html, steuerjahr)
    pruefe_vollstaendigkeit(abschnitte)
    inhalts_hash = sha256(html.encode("utf-8")).hexdigest()
    ergebnis = {
        "quelle": daten["titel"],
        "url": daten["url"],
        "steuerjahr": steuerjahr,
        "abschnitte": len(abschnitte),
        "zeichen": sum(len(eintrag["inhalt"]) for eintrag in abschnitte),
        "hash": inhalts_hash,
        "stand": date.today().isoformat(),
    }
    if exportieren or not nur_pruefen:
        daten["export_datei"].parent.mkdir(parents=True, exist_ok=True)
        daten["export_datei"].write_text(
            json.dumps(
                {"metadaten": ergebnis, "abschnitte": abschnitte},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        STATUS_DATEI.write_text(json.dumps(ergebnis, ensure_ascii=False, indent=2), encoding="utf-8")
    if nur_pruefen:
        return ergebnis

    from qdrant_client import QdrantClient
    from qdrant_client.models import FieldCondition, Filter, MatchValue, PointStruct
    from modell_ressourcen import MODELL_RESSOURCEN

    client = QdrantClient(path=QDRANT_ORDNER)
    try:
        if not client.collection_exists(COLLECTION):
            raise RuntimeError("Die lokale Wissensdatenbank fehlt.")
        version = date.today().isoformat()
        paketgroesse = 24
        for start in range(0, len(abschnitte), paketgroesse):
            paket = abschnitte[start : start + paketgroesse]
            texte = [f"{eintrag['abschnitt']}\n{eintrag['inhalt']}" for eintrag in paket]
            embeddings = MODELL_RESSOURCEN.embedding(
                EMBEDDING_MODEL, texte
            )["embeddings"]
            punkte = []
            for nummer, (eintrag, embedding) in enumerate(zip(paket, embeddings), start=start + 1):
                punkte.append(
                    PointStruct(
                            id=punkt_id(daten["quelle_id"], eintrag["abschnitt"], eintrag["inhalt"]),
                        vector=embedding,
                        payload={
                            "text": eintrag["inhalt"],
                            "quelle": daten["titel"],
                            "herausgeber": "Steuerverwaltung / ELSTER",
                            "paragraph": eintrag["abschnitt"],
                            "steuerjahr": steuerjahr,
                            "stand_abgerufen": version,
                            "url": daten["url"],
                            "kategorie": f"ELSTER-Leitfaden Einkommensteuer {steuerjahr}",
                            "quelle_id": daten["quelle_id"],
                            "jahr_abhaengig": True,
                            "gueltig_fuer": [steuerjahr],
                            "quellen_version": version,
                            "abschnitt": nummer,
                        },
                    )
                )
            client.upsert(collection_name=COLLECTION, points=punkte)
        client.delete(
            collection_name=COLLECTION,
            points_selector=Filter(
                must=[FieldCondition(key="quelle_id", match=MatchValue(value=daten["quelle_id"]))],
                must_not=[FieldCondition(key="quellen_version", match=MatchValue(value=version))],
            ),
        )
    finally:
        client.close()

    STATUS_DATEI.write_text(json.dumps(ergebnis, ensure_ascii=False, indent=2), encoding="utf-8")
    return ergebnis


def main() -> None:
    parser = argparse.ArgumentParser(description="Aktualisiert die vollständigen ELSTER-Leitfäden 2023 bis 2025.")
    parser.add_argument(
        "--steuerjahr",
        type=int,
        choices=UNTERSTUETZTE_STEUERJAHRE,
        help="Ein einzelnes Steuerjahr; ohne Angabe werden 2023 bis 2025 verarbeitet.",
    )
    parser.add_argument("--nur-pruefen", action="store_true", help="Prüft den Abruf, ohne die Datenbank zu ändern.")
    parser.add_argument(
        "--exportieren",
        action="store_true",
        help="Speichert die geprüften Abschnitte zusätzlich als lokale Wissensquelle.",
    )
    argumente = parser.parse_args()
    jahre = (argumente.steuerjahr,) if argumente.steuerjahr else UNTERSTUETZTE_STEUERJAHRE
    ergebnisse = [
        aktualisiere(
            nur_pruefen=argumente.nur_pruefen,
            exportieren=argumente.exportieren,
            steuerjahr=jahr,
        )
        for jahr in jahre
    ]
    print(json.dumps(ergebnisse[0] if len(ergebnisse) == 1 else ergebnisse, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
