from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from quellen_chunking import fristtyp, quellenkarten_payloads, segmentiere_quellentext


def test_mehrthemenkarte_wird_in_regelnahe_chunks_getrennt():
    quelle = json.loads(
        (ROOT / "wissen" / "quellen" / "lohnsteuer_sonderfaelle_2026_ergaenzung.json")
        .read_text(encoding="utf-8")
    )
    payloads = quellenkarten_payloads(Path("lohnsteuer_sonderfaelle_2026_ergaenzung.json"), quelle)
    assert len(payloads) >= 10
    assert all(len(payload["text"]) <= 760 for payload in payloads)
    fahrrad = [payload for payload in payloads if "Fahrrad" in payload["text"]]
    assert len(fahrrad) == 1
    assert "Jobticket" not in fahrrad[0]["text"]
    assert fahrrad[0]["suchjahre"] == [2023, 2024, 2025, 2026]


def test_bayern_metadaten_werden_an_jeden_chunk_gebunden():
    pfad = ROOT / "wissen" / "quellen" / "steuerjahr_2025_grundsteuer_bayern.json"
    quelle = json.loads(pfad.read_text(encoding="utf-8"))
    payloads = quellenkarten_payloads(pfad, quelle)
    assert payloads
    assert all(payload["bundesland"] == "Bayern" for payload in payloads)
    assert all("BayGrStG" in payload["gesetz"] for payload in payloads)
    assert all(payload["suchjahre"] == [2025] for payload in payloads)


def test_segmentierung_verliert_keinen_text():
    text = "Erste Regel gilt. Zweite Regel gilt; sie hat einen Zusatz. Dritte Regel gilt."
    chunks = segmentiere_quellentext(text)
    assert " ".join(chunks) == text


def test_datum_wird_nicht_nach_der_tageszahl_getrennt():
    chunks = segmentiere_quellentext(
        "Für Gebäude nach dem 31. Dezember 2022 beträgt die AfA 3 Prozent. Zweite Regel."
    )
    assert chunks[0].startswith("Für Gebäude nach dem 31. Dezember 2022")


def test_verfahrensfrist_und_materieller_zeitraum_bleiben_getrennt():
    assert fristtyp("Der Antrag ist binnen zwei Monaten zu stellen.") == "verfahrensfrist"
    assert (
        fristtyp("Mehrere Erwerbe innerhalb von zehn Jahren werden zusammengerechnet.")
        == "materieller_zeitraum"
    )
