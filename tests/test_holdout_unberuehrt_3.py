"""Dritter, bis zum Erstlauf unberührter Holdout."""

import re
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import rag_assistent


UNBERUEHRT = [
    ("Mein Arbeitgeber meldet Insolvenz und schuldet mir Gehälter. Welche Ersatzleistung beantrage ich?", ("insolvenzgeld",)),
    ("Welches Nachweis-Papier brauche ich für das erhaltene Insolvenzgeld?", ("leistungsnachweis",)),
    ("Kann die steuerfreie Lohnersatzleistung Insolvenzgeld meinen Steuersatz beeinflussen?", ("progressionsvorbehalt",)),
    ("Die Mietsicherheit wird nur treuhänderisch verwahrt und später zurückgezahlt. Ist sie Einnahme?", ("keine mieteinnahme",)),
    ("Rückständige Miete ist noch nicht eingegangen. In welchem Jahr zählt sie?", ("zuflussprinzip", "zahlungsjahr")),
    ("Meine Nichte zahlt unter Marktniveau. Ab welcher Quote ist der volle Werbungskostenabzug möglich?", ("66 prozent",)),
    ("Darf ich zur ersten Tätigkeitsstätte Hin- und Rückfahrtkilometer zusammenrechnen?", ("einfache entfernung", "nicht")),
    ("Ein Notebook dient zu 95 Prozent meinem Beruf. Kann der berufliche Anteil Werbungskosten sein?", ("beruflich", "werbungskosten")),
    ("Mein einziges Arbeitsmittel ist ein berufliches Nachschlagewerk für 200 Euro. Wirkt das über der Pauschale?", ("1.230 euro", "kein zusätzlicher steuervorteil")),
    ("Werden Pflichtbeiträge an die gesetzliche Rentenversicherung als Vorsorge berücksichtigt?", ("vorsorgeaufwendungen",)),
    ("Ein Aushilfsjob wurde vom Betrieb pauschal versteuert. Gehört er als Arbeitslohn in meine Erklärung?", ("nicht", "arbeitslohn")),
    ("Kann nach der Veranlagung statt einer Rückzahlung auch eine Steuerschuld herauskommen?", ("nachzahlung", "rückzahlung")),
    ("Die Wohnung war seit dem Kauf ausschließlich selbst bewohnt. Ist ein Verkauf vor zehn Jahren begünstigt?", ("innerhalb der zehn jahre",)),
    ("Kann die Behörde eine feste Wochenzahl bis zum Einkommensteuerbescheid garantieren?", ("keine allgemein feste",)),
    ("Im kommunalen Jahresbescheid stehen Grundsteuer, Wasser und Straßenreinigung. Muss jede Position geprüft werden?", ("getrennt", "straßenreinigung")),
]


@pytest.mark.parametrize("frage,erwartet", UNBERUEHRT)
def test_dritter_holdout(frage, erwartet):
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
