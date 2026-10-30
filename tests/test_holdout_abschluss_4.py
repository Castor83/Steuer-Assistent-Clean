"""Unabhängiger Abschluss-Holdout; Formulierungen vor dem Erstlauf festgelegt."""

import re
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import rag_assistent


ABSCHLUSS = [
    ("Der Chef kann wegen der Firmeninsolvenz drei offene Löhne nicht zahlen. Was springt dafür ein?", ("insolvenzgeld",)),
    ("Was akzeptiert das Amt als Nachweis über Höhe und Empfang des Insolvenzgeldes?", ("leistungsnachweis",)),
    ("Ist Insolvenzgeld abgabenfrei und wirkt trotzdem auf die Besteuerung des Restlohns?", ("steuerfrei", "progressionsvorbehalt")),
    ("Eine rückzahlbare Mietsicherheit liegt separat auf dem Konto. Zählt das als Vermietungseinnahme?", ("keine mieteinnahme",)),
    ("Die Miete ist fällig, wurde aber nicht überwiesen. Wann entsteht bei mir die Einnahme?", ("zuflussprinzip",)),
    ("Mein Neffe bekommt die Wohnung billiger. Welche Schwelle sichert den vollständigen Kostenabzug?", ("66 prozent",)),
    ("Setzt die Pendlerregel nur die einfache Distanz oder beide Fahrtrichtungen an?", ("einfache entfernung",)),
    ("Mein Desktopcomputer wird nahezu ausschließlich dienstlich verwendet. Ist der berufliche Anteil abziehbar?", ("beruflich", "werbungskosten")),
    ("Außer einem beruflichen Handbuch für 200 Euro habe ich keine Werbungskosten. Bringt das extra etwas?", ("1.230 euro", "erst höhere gesamte werbungskosten")),
    ("Zählen meine gesetzlichen Rentenbeiträge zu den steuerlichen Vorsorgeposten?", ("vorsorgeaufwendungen",)),
    ("Welche Basisbeiträge für Rente, Gesundheit und Pflege gehören zur Vorsorge?", ("rentenversicherung", "kranken-", "pflege")),
    ("Der Arbeitgeber hat meinen kleinen Aushilfsverdienst pauschal besteuert. Muss er in Anlage N?", ("nicht", "arbeitslohn")),
    ("Ist bei der Jahresabrechnung der Einkommensteuer neben Guthaben auch ein Fehlbetrag möglich?", ("nachzahlung", "erstattung")),
    ("An welchem Tag lief die normale Frist der nicht beratenen Pflicht-Erklärung 2023 ab?", ("2. september 2024",)),
    ("Ich nutzte das Objekt seit Erwerb ohne Unterbrechung selbst. Greift beim frühen Verkauf die Wohn-Ausnahme?", ("innerhalb der zehn jahre",)),
    ("Der gemeinschaftliche Mietergarten verursacht laufende Pflegekosten. Welcher Anteil ist abziehbar?", ("anteilig abziehbar", "gartenpflege")),
    ("Der alte Heizkessel des vermieteten Hauses wird erneuert. Ist das typischer Erhaltungsaufwand?", ("erhaltungsaufwand",)),
    ("Existiert eine garantierte Bearbeitungsfrist in Wochen für Einkommensteuererklärungen?", ("keine allgemein feste",)),
    ("Verhindert der BZSt-Widerspruch gegen den Kirchensteuerabruf auch die Steuerpflicht selbst?", ("nicht", "kirchensteuerpflicht")),
    ("Der Gemeindebescheid bündelt Grundsteuer, Wasser und Straßenreinigung. Sind das getrennte Prüfposten?", ("getrennt", "straßenreinigung")),
]


@pytest.mark.parametrize("frage,erwartet", ABSCHLUSS)
def test_unabhaengiger_abschluss_holdout(frage, erwartet):
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
