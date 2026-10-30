"""Finaler ungesehener Themenmix, vor seinem Erstlauf festgeschrieben."""

import re
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import rag_assistent


FINAL_UNSEEN = [
    ("Welche Unterlage bestätigt dem Finanzamt meinen Insolvenzgeldbezug?", ("leistungsnachweis",)),
    ("Bleibt Insolvenzgeld ohne eigene Steuer und kann dennoch den Tarif für anderes Einkommen anheben?", ("steuerfrei", "progressionsvorbehalt")),
    ("Ist eine nur verwahrte und rückzahlbare Mietkaution bereits steuerlicher Ertrag?", ("keine mieteinnahme",)),
    ("Noch unbezahlte Miete habe ich nicht erhalten. In welchem Veranlagungsjahr erfasse ich sie?", ("zuflussprinzip", "zahlungsjahr")),
    ("Bei Vermietung an einen Angehörigen: Ab welchem Verhältnis zur Marktmiete bleibt der Abzug vollständig?", ("66 prozent",)),
    ("Rechnet man für den täglichen Weg zur Arbeit nur eine Richtung?", ("einfache entfernung",)),
    ("Nur ein berufliches Fachhandbuch für 200 Euro, sonst nichts: Liegt das über dem Arbeitnehmer-Pauschbetrag?", ("1.230 euro",)),
    ("Sind gesetzliche Altersvorsorgebeiträge als Vorsorgeaufwand einzuordnen?", ("vorsorgeaufwendungen",)),
    ("Muss pauschal versteuerter geringfügiger Arbeitslohn in der Anlage N erscheinen?", ("nicht", "arbeitslohn")),
    ("Kann die Einkommensteuerabrechnung statt Auszahlung einen offenen Zahlbetrag ergeben?", ("nachzahlung",)),
    ("Wann endete für 2023 die Abgabe ohne steuerliche Beratung bei bestehender Erklärungspflicht?", ("2. september 2024",)),
    ("Durchgängige Eigennutzung seit Anschaffung: Kann die Immobilie vor zehn Jahren steuerbegünstigt verkauft werden?", ("innerhalb der zehn jahre",)),
    ("Wie viele Wochen darf die Bearbeitung einer Einkommensteuererklärung verbindlich dauern?", ("keine allgemein feste",)),
    ("Muss ich die Bestandteile eines kommunalen Bescheids mit Grundsteuer, Wasser und Straßenreinigung einzeln kontrollieren?", ("getrennt",)),
    ("Ich arbeitete 2023 an 40 Tagen überwiegend daheim. Welche Homeoffice-Tagespauschale gilt?", ("6 euro", "240 euro")),
    ("Sind Betreuungskosten anerkennbar, wenn ich den Babysitter bar bezahlt habe?", ("bar", "nicht anerkannt")),
    ("Wie wird ein privater Kryptoverkauf innerhalb eines Jahres grundsätzlich behandelt?", ("höchstens ein jahr", "steuerpflichtig")),
    ("Für eine Spende von 150 Euro: Reicht der Überweisungsbeleg statt einer Zuwendungsbestätigung?", ("300 euro", "kontoauszug")),
    ("Beseitigt der Sperrvermerk für den Bankabruf die Kirchensteuerpflicht?", ("nicht", "kirchensteuerpflicht")),
    ("Der vorhandene Heizkessel einer vermieteten Wohnung wird ersetzt. Ist das regelmäßig Erhaltung?", ("erhaltungsaufwand",)),
]


@pytest.mark.parametrize("frage,erwartet", FINAL_UNSEEN)
def test_finaler_ungesehener_mix(frage, erwartet):
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
