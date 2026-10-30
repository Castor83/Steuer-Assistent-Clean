import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import rag_assistent


FAELLE = (
    ("Was passiert mit meinen Riester-Beiträgen bei unbezahltem Urlaub?", ("nicht automatisch", "Vorjahres"), ("gesetzlichen Rentenversicherung können",)),
    ("Wo trage ich Beiträge zur Kranken-, Pflege- und Rentenversicherung ein?", ("Anlage Vorsorgeaufwand", "vorausgefüllt"), ("Ja. Beiträge",)),
    ("Mein 20-jähriges Kind macht eine Erstausbildung und wohnt auswärts. Welche Freibeträge kann ich geltend machen?", ("Ausbildungsfreibetrag", "1.200 Euro", "Anlage Kind"), ("deiner ersten Ausbildung",)),
    ("Wie wirkt sich Arbeitslosengeld auf meinen Steuersatz aus?", ("Progressionsvorbehalt",), ("Abfindung",)),
    ("Muss ich Gewinne aus Kryptowährungen oder Aktien versteuern?", ("600 Euro", "Aktiengewinne"), ("50 %",)),
    ("Welche Steuerklassenkombination passt zu Ehepaaren und ändert sie die endgültige Jahressteuer?", ("ändert nicht", "IV/IV mit Faktor", "III/V"), ()),
    ("Wovon hängt der steuerpflichtige Anteil einer gesetzlichen Rente ab?", ("Rentenbeginn", "82,5 Prozent"), ("2026",)),
)


@pytest.mark.parametrize("frage,erwartet,verboten", FAELLE)
def test_jahresrichtige_allgemeine_antworten(frage, erwartet, verboten):
    text, quellen = rag_assistent.beantworte(frage, steuerjahr=2023, steuerprofil={})
    for teil in erwartet:
        assert teil in text
    for teil in verboten:
        assert teil not in text
    assert quellen
    assert all(q.payload.get("url", "").startswith("https://") for q in quellen)


@pytest.mark.parametrize(
    "jahr,anteil,maximum",
    ((2023, "zwei Drittel", "4.000 Euro"), (2024, "zwei Drittel", "4.000 Euro"), (2025, "80 Prozent", "4.800 Euro")),
)
def test_kinderbetreuung_nutzt_das_ausgewaehlte_steuerjahr(jahr, anteil, maximum):
    text, quellen = rag_assistent.beantworte(
        "Welche Kinderbetreuungskosten kann ich absetzen?",
        steuerjahr=jahr,
        steuerprofil={},
    )
    assert anteil in text
    assert maximum in text
    assert quellen[0].payload["kategorie"] == "Kinderbetreuung nach Steuerjahr"


@pytest.mark.parametrize("jahr,grenze", ((2023, "62.810"), (2024, "66.761"), (2025, "68.481")))
def test_spitzensteuersatz_nutzt_das_ausgewaehlte_steuerjahr(jahr, grenze):
    text, quellen = rag_assistent.beantworte(
        "Ab wann gilt der Spitzensteuersatz?",
        steuerjahr=jahr,
        steuerprofil={},
    )
    assert str(jahr) in text
    assert grenze in text
    assert "nur für den Teil" in text
    assert quellen[0].payload["kategorie"] == "Einkommensteuertarif nach Steuerjahr"
