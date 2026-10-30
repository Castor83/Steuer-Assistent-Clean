"""Zweiter Holdout mit zuvor nicht ausgeführten Formulierungen."""

import re
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import rag_assistent


NEUE_FAELLE = [
    ("Der Betrieb ist zahlungsunfähig und mein Lohn blieb aus. Wo bekomme ich Ersatz?", ("insolvenzgeld", "agentur für arbeit")),
    ("Welches Schreiben gilt als Beleg für ausgezahltes Insolvenzgeld?", ("leistungsnachweis",)),
    ("Erhöht eine steuerfreie Insolvenzgeldzahlung eventuell den Satz auf meinen übrigen Lohn?", ("progressionsvorbehalt", "steuerfrei")),
    ("Die Kaution muss ich später komplett zurückgeben. Muss sie jetzt in Anlage V?", ("keine mieteinnahme", "rückzahlbare")),
    ("Eine Monatsmiete ist nur eine Forderung und noch nicht auf meinem Konto. Ist sie schon steuerpflichtig?", ("zuflussprinzip", "nicht als einnahme")),
    ("Mein Sohn zahlt eine reduzierte Wohnungsmiete. Wann bleiben die Werbungskosten voll erhalten?", ("66 prozent", "50 prozent")),
    ("Wird beim Pendeln die Strecke Wohnung–Büro zweimal angesetzt?", ("einfache entfernung", "nicht")),
    ("Der PC wird zu 90 Prozent für meinen Beruf benutzt. Welcher Anteil ist Werbungskosten?", ("beruflich", "werbungskosten")),
    ("Ich kaufte nur ein berufliches Lehrbuch für 200 Euro. Überschreite ich damit die Arbeitnehmerpauschale?", ("1.230 euro", "kein zusätzlicher steuervorteil")),
    ("Sind Einzahlungen in die gesetzliche Rentenversicherung Vorsorgeaufwand?", ("vorsorgeaufwendungen",)),
    ("Nenne mir die zentralen gesetzlichen Vorsorgeversicherungen.", ("rentenversicherung", "kranken-", "pflege")),
    ("Muss eine pauschal versteuerte geringfügige Beschäftigung als normaler Lohn erklärt werden?", ("nicht", "normalen arbeitslohn")),
    ("Kann der Einkommensteuerbescheid trotz Abgabe der Erklärung eine Zahlung von mir verlangen?", ("nachzahlung", "erstattung")),
    ("Welcher reguläre Abgabetag galt ohne Berater für die Pflichtveranlagung 2023?", ("2. september 2024",)),
    ("Das Eigenheim war durchgehend mein Wohnsitz. Kann der Verkauf vor dem zehnten Jahr ausgenommen sein?", ("innerhalb der zehn jahre", "selbst")),
    ("Wie behandle ich Gärtnerrechnungen für eine Grünfläche, die auch die Mieter nutzen?", ("anteilig abziehbar", "gartenpflege")),
    ("Ist die Erneuerung der bestehenden Heizungsanlage im Mietshaus gewöhnlich Instandhaltung?", ("erhaltungsaufwand",)),
    ("Kann mir das Finanzamt verbindlich zusagen, nach wie vielen Wochen der Bescheid kommt?", ("keine allgemein feste",)),
    ("Bleibt Kirchensteuer auf Kapitalerträge trotz eines BZSt-Sperrvermerks ein Thema?", ("kirchensteuerpflicht", "nicht")),
    ("Warum sollte ich Wassergebühr, Straßenreinigung und Grundsteuer im Sammelbescheid einzeln ansehen?", ("getrennt", "straßenreinigung", "grundsteuer")),
]


@pytest.mark.parametrize("frage,erwartet", NEUE_FAELLE)
def test_zweiter_holdout(frage, erwartet):
    antwort, quellen = rag_assistent.beantworte(
        frage,
        steuerjahr=2023,
        steuerprofil={
            "person": {"angestellter": True, "hausbesitzer": True},
            "grundabgaben_standardobjekt": {
                "gebaeudeart": "Dreifamilienhaus",
                "nutzung": "teilweise selbst genutzt und teilweise vermietet",
            },
        },
    )
    assert all(wort.casefold() in antwort.casefold() for wort in erwartet)
    assert quellen and re.search(r"\[\d+\]", antwort)
    assert all(rag_assistent._amtliche_quelle(quelle) for quelle in quellen)
    assert all(rag_assistent.quelle_passt_zum_steuerjahr(quelle.payload, 2023) for quelle in quellen)
