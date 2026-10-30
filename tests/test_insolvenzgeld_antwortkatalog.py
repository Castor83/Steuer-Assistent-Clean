import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import rag_assistent


def antwort(frage: str, jahr: int = 2025):
    return rag_assistent.beantworte(frage, steuerjahr=jahr, steuerprofil={})


FAELLE = (
    ("wie weise ich den erhalt von insolvenzgeld nach", ("Leistungsnachweis", "elektronisch"), ("letzten drei Monate",), "Insolvenzgeld Nachweis"),
    ("welcher beleg beweist die auszahlung vom insolvenzgelt", ("Leistungsnachweis", "Kontoauszug"), ("Zweimonatsfrist",), "Insolvenzgeld Nachweis"),
    ("reicht der kontoauszug als nachweis dass ich insolvenzgeld bekommen habe", ("ergänzender Zahlungsbeleg", "ersetzt den Leistungsnachweis nicht"), (), "Insolvenzgeld Nachweis"),
    ("welche bescheinigung lege ich dem finanzamt für das erhaltene insolvenzgeld vor", ("Leistungsnachweis", "Finanzamt"), ("Arbeitsvertrag",), "Insolvenzgeld Nachweis"),
    ("welche nachweise brauche ich für den antrag auf insolvenzgeld", ("Arbeitsvertrag", "Verdienstabrechnungen"), ("Kontoauszug ist nur",), "Insolvenzgeld Anspruch und Antrag"),
    ("meine firma hat nur einen insolvenzantrag gestellt bekomme ich schon insolvenzgeld", ("noch nicht automatisch", "Insolvenzereignis"), (), "Insolvenzgeld Anspruch und Antrag"),
    ("bis wann muss ich insolvenzgeld beantragen", ("zwei Monaten", "Agentur für Arbeit"), (), "Insolvenzgeld Anspruch und Antrag"),
    ("für welche 3 monate gibts insolvenz geld", ("letzten drei Monaten", "vor dem Insolvenzereignis"), (), "Insolvenzgeld Anspruch und Antrag"),
    ("wird insolvenzgeld brutto oder netto gezahlt", ("Nettoarbeitsentgelt", "Beitragsbemessungsgrenze"), (), "Insolvenzgeld Anspruch und Antrag"),
    ("bekomme ich als minijobber insolvenzgelt", ("Minijobber", "Arbeitnehmer"), (), "Insolvenzgeld Anspruch und Antrag"),
    ("kann ich insolvebtsgeld steuerlich absetzten", ("nicht als Sonderausgabe", "auch nicht teilweise"), ("50 %",), "Insolvenzgeld Steuererklärung"),
    ("muss ich das insolvenzgeld versteuern", ("selbst ist steuerfrei", "Progressionsvorbehalt"), ("außergewöhnliche Belastung",), "Insolvenzgeld Steuererklärung"),
    ("wo kommt insolvenzgeld in elster hin", ("Hauptvordruck", "Einkommensersatzleistungen"), (), "Insolvenzgeld Steuererklärung"),
    ("elster hat das insolvenzgeld schon elektronisch übernommen soll ich es nochmal eintragen", ("nicht ein zweites Mal", "Leistungsnachweis"), (), "Insolvenzgeld Steuererklärung"),
    ("300 euro insolvenzgeld und 250 krankengeld zählt das bei den 410 zusammen", ("zusammengerechnet", "über 410 Euro"), (), "Insolvenzgeld Steuererklärung"),
    ("muss ich wegen insolvenzgeld steuern nachzahlen", ("nicht automatisch", "übrigen Einkommen"), (), "Insolvenzgeld Steuererklärung"),
    ("ich hatte nur insolvenzgeld und sonst kein einkommen", ("nicht besteuert", "Pflicht zur Abgabe"), (), "Insolvenzgeld Steuererklärung"),
    ("die bank hat mein insolvenzgeld vorfinanziert ist das steuerlich anders", ("dem Arbeitnehmer zugerechnet", "Progressionsvorbehalt"), (), "Insolvenzgeld Steuererklärung"),
    ("mein leistungsnachweis für insolvenzgeld ist weg was soll ich machen", ("Agentur für Arbeit", "nicht vorsorglich einen geschätzten Betrag"), (), "Insolvenzgeld Steuererklärung"),
)


@pytest.mark.parametrize("frage,erwartet,verboten,kategorie", FAELLE)
def test_antwortkatalog(frage, erwartet, verboten, kategorie):
    text, quellen = antwort(frage)
    for teil in erwartet:
        assert teil in text
    for teil in verboten:
        assert teil not in text
    assert quellen
    assert quellen[0].payload["kategorie"] == kategorie
    assert quellen[0].payload["url"].startswith("https://")
