import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import amtliche_internetsuche
import rag_assistent


def test_sonderantwort_ohne_fund_der_zentralen_suche_wird_blockiert(monkeypatch):
    monkeypatch.setattr(rag_assistent, "suche_wissen", lambda *args, **kwargs: [])
    monkeypatch.setattr(amtliche_internetsuche, "suche_amtliche_quellen", lambda *args, **kwargs: [])

    text, quellen = rag_assistent.beantworte(
        "Bekomme ich wegen Insolvenzgeld automatisch eine Steuernachzahlung?",
        steuerjahr=2023,
        steuerprofil={},
    )

    assert not quellen
    assert "keine steuerliche Behauptung" in text
    assert "Progressionsvorbehalt" not in text


def test_quelle_mit_falschem_steuerjahr_gibt_antwort_nicht_frei(monkeypatch):
    falsche_quelle = SimpleNamespace(
        score=1.0,
        payload={
            "text": "Ein nur für 2025 geltender Betrag beträgt 9.999 Euro.",
            "quelle": "Amtliche Testquelle 2025",
            "paragraph": "§ 1 TestG",
            "steuerjahr": 2025,
            "kategorie": "Test",
            "url": "https://www.gesetze-im-internet.de/estg/",
            "jahr_abhaengig": True,
            "gueltig_fuer": [2025],
        },
    )
    monkeypatch.setattr(
        rag_assistent, "suche_wissen", lambda *args, **kwargs: [falsche_quelle]
    )
    monkeypatch.setattr(amtliche_internetsuche, "suche_amtliche_quellen", lambda *args, **kwargs: [])

    text, quellen = rag_assistent.beantworte(
        "Wie hoch ist der Testbetrag?", steuerjahr=2023, steuerprofil={}
    )

    assert not quellen
    assert "9.999" not in text
    assert "keine steuerliche Behauptung" in text


def test_amtliche_domain_ist_zwingend():
    quelle = SimpleNamespace(payload={"url": "https://beispiel-ratgeber.de/steuer"})
    assert rag_assistent._amtliche_quelle(quelle) is False


def test_online_fallback_verwendet_keine_allgemeine_suchmaschine():
    quelltext = Path(amtliche_internetsuche.__file__).read_text(encoding="utf-8").casefold()
    for dienst in ("bing", "duckduckgo", "google.com/search", "brave.com"):
        assert dienst not in quelltext


def test_allgemeine_arbeitgeberleistungen_2026_werden_belegt_beantwortet():
    text, quellen = rag_assistent.beantworte(
        "Was muss ich zu Arbeitgeberleistungen 2026 bei der Steuer wissen?",
        steuerjahr=2026,
        steuerprofil={},
    )

    assert "nicht einheitlich steuerfrei" in text
    assert "50 Euro" in text
    assert "110 Euro" in text
    assert quellen
    assert quellen[0].payload["kategorie"] == "Arbeitgeberleistungen 2026"
    assert "[1]" in text


def test_insolvenzgeld_tippfehlerrouting_hat_enge_grenzen():
    for frage in (
        "Welche Folgen hat ein Insolvenzantrag des Vermieters?",
        "Was macht ein Insolvenzverwalter?",
        "Wie wird Arbeitslosengeld behandelt?",
    ):
        kanonisch = rag_assistent.kanonisiere_alltagssprache(
            rag_assistent.normalisiere(frage)
        )
        assert "progressionsvorbehalt nicht als sonderausgabe" not in kanonisch


def test_inventarisierte_ueberblicksfaelle_bleiben_quellengebunden():
    profil = {
        "grundabgaben_standardobjekt": {
            "stadt": "Erlangen",
            "nutzung": "teilweise selbst genutzt und teilweise vermietet",
        }
    }
    faelle = (
        ("Wie läuft das beim Thema Bekanntgabe Steuerbescheid historisch?", 2023),
        ("bei mir gehts um Rente und Vorsorge Ergänzung 2026", 2026),
        ("Wie läuft das beim Thema Vermietung und Betriebskosten?", 2023),
        ("Wie läuft das beim Thema Private Rentenversicherung und Vorsorgeaufwand?", 2023),
        ("Wie läuft das beim Thema Hochwasserschaden außergewöhnliche Belastung?", 2023),
        ("Wie läuft das beim Thema Grundsteuer Zurechnung und Befreiung?", 2023),
        ("Kannste mir das Thema „Grundsteuer Zurechnung und Befreiung“ mal normal erklären?", 2023),
        ("Was bedeutet „Grundsteuer Zurechnung und Befreiung“ für meine Steuererklärung?", 2023),
        ("ich brauch eine einfache erklärung zum tema „grundsteuer zurechnung und befreiung“", 2023),
        ("Wie läuft das beim Thema Investmentfonds und Teilfreistellung?", 2023),
        ("hab grundsteuerbescheid fürs dreifamilienhaus in erlangen bekommen geht um 2025", 2025),
        ("versicherung hat nur material bezahlt handwerker hab ich selbst bezahlt", 2023),
        ("kan ich die sanirung im eigenem haus absetzten wen versicherung gezalt hat", 2023),
        ("Kann ich die Reparaturkosten steuerlich berücksichtigen?", 2023),
    )

    for frage, steuerjahr in faelle:
        text, quellen = rag_assistent.beantworte(
            frage,
            steuerjahr=steuerjahr,
            steuerprofil=profil,
        )
        assert "keine steuerliche Behauptung" not in text
        assert quellen
        assert "[1]" in text


def test_grundsteuer_thementitel_wird_nicht_zur_erklaerungspflicht_umgedeutet():
    for frage in (
        "Kannste mir das Thema Grundsteuer Zurechnung und Befreiung normal erklären?",
        "Was bedeutet Grundsteuer Zurechnung und Befreiung für meine Steuererklärung?",
    ):
        assert rag_assistent.bestimme_fragefokus(frage) is None
