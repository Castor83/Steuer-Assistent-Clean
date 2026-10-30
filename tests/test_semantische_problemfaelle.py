from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import rag_assistent as rag


FAELLE = (
    (
        "Kann ich die Beerdigungskosten für einen nahen Verwandten als außergewöhnliche Belastung geltend machen?",
        ("Nachlass", "übersteigen"),
    ),
    (
        "Welche steuerlichen Folgen hat es, wenn ein Arbeitgeber die Umzugskosten für einen Mitarbeiter übernimmt, der aus rein privaten Gründen in eine andere Stadt zieht?",
        ("geldwerter Vorteil", "lohnsteuer"),
    ),
    (
        "Ein Steuerzahler kauft eine vermietete Eigentumswohnung. Der Kaufpreis beträgt 200.000 Euro, wovon laut Gutachten 50.000 Euro auf den Grund- und Bodenanteil entfallen. Auf welcher Basis berechnet er seine jährliche Gebäude-AfA?",
        ("150.000 Euro", "Grund- und Bodenanteil"),
    ),
    (
        "Ein Arbeitnehmer bittet seinen Chef, die Lohnsteuer für ein ihm überlassenes Firmen-E-Bike (bis 25 km/h) pauschal zu versteuern. Gilt hierbei die 0,25-%-Regel, wenn das Rad zusätzlich zum ohnehin geschuldeten Arbeitslohn gewährt wird?",
        ("Nein", "steuerfrei", "zusätzlich"),
    ),
    (
        "Wie hoch ist der persönliche Freibetrag für Ehegatten bei der Erbschaftssteuer im Jahr 2026 und innerhalb welcher Frist gilt er?",
        ("500.000 Euro", "10 Jahre"),
    ),
    (
        "Unter welchen genauen Bedingungen erben Ehegatten oder Kinder ein Familienheim (selbstgenutztes Wohnhaus) komplett erbschaftssteuerfrei?",
        ("unverzüglich", "10 Jahre", "200 Quadratmeter"),
    ),
    (
        "Welches Berechnungsmodell nutzt das Bundesland Bayern für die Ermittlung der neuen Grundsteuer?",
        ("Flächenmodell", "0,04 Euro", "0,50 Euro"),
    ),
)


@pytest.mark.parametrize("frage,erwartet", FAELLE)
def test_problemfall_hat_deterministische_vollantwort(frage, erwartet):
    ergebnis = rag.steuerjahr_grundantwort(frage, 2025, {})
    assert ergebnis is not None
    antwort, quellen = ergebnis
    assert quellen
    for text in erwartet:
        assert text.casefold() in antwort.casefold()
