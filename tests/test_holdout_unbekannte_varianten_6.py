"""Vor dem ersten Lauf festgelegte, neu formulierte Abschlussfragen."""

import re
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import rag_assistent


FAELLE = [
    ("Woher bekomme ich die Bescheinigung, mit der ich ausgezahltes Insolvenzgeld beim Finanzamt belege?", ("leistungsnachweis",)),
    ("Bleibt Insolvenzgeld zwar steuerfrei, erhöht aber möglicherweise den Satz für meinen übrigen Lohn?", ("steuerfrei", "progressionsvorbehalt")),
    ("Genügt bei einer Spende von 180 Euro normalerweise der Kontoauszug als vereinfachter Beleg?", ("300 euro", "konto")),
    ("Ich kaufte nur ein berufliches Fachlexikon für 150 Euro. Entsteht dadurch neben dem Arbeitnehmer-Pauschbetrag ein Extraabzug?", ("1.230 euro", "werbungskosten")),
    ("Fließen meine Pflichtzahlungen an die gesetzliche Alterskasse in die Vorsorgeaufwendungen ein?", ("vorsorgeaufwendungen",)),
    ("Der Betrieb versteuerte meinen Minijob pauschal. Muss ich diesen Verdienst nochmals als Arbeitslohn erklären?", ("nicht", "arbeitslohn")),
    ("Darf ich für den Weg zur ersten Tätigkeitsstätte die Kilometer morgens und abends addieren?", ("einfache entfernung", "nicht")),
    ("An 62 Tagen arbeitete ich 2023 überwiegend in meiner Wohnung. Wie hoch ist die Tagespauschale insgesamt?", ("372 euro", "6 euro")),
    ("Eine rückzahlbare Mietkaution verwahre ich getrennt. Ist sie bereits steuerpflichtige Miete?", ("keine mieteinnahme",)),
    ("Der Mieter schuldet Dezembermiete, bezahlt aber erst später. Gilt beim Vermieter der tatsächliche Geldzufluss?", ("zuflussprinzip",)),
    ("Bei einer verbilligten Wohnung für meinen Bruder: Ab welcher Mietquote bleibt der volle Werbungskostenabzug erhalten?", ("66 prozent",)),
    ("Kann ich laufende Pflege des Gartens eines vermieteten Mehrfamilienhauses anteilig ansetzen?", ("gartenpflege", "anteilig")),
    ("Der verschlissene Heizkessel im Mietshaus wird ersetzt. Wird das regelmäßig als Erhaltungsaufwand behandelt?", ("erhaltungsaufwand",)),
    ("Welche Abgabefrist galt für die selbst erstellte Pflichtveranlagung des Jahres 2023?", ("2. september 2024",)),
    ("Verspricht das Finanzamt nach Eingang der Erklärung einen Bescheid binnen einer bestimmten Zahl von Wochen?", ("keine allgemein feste",)),
    ("Kann die Einkommensteuerabrechnung außer einer Erstattung ebenso eine Nachzahlung ergeben?", ("erstattung", "nachzahlung")),
    ("Hebt ein Sperrvermerk gegen den Kirchensteuer-Datenabruf meine eigentliche Kirchensteuerpflicht auf?", ("nicht", "kirchensteuerpflicht")),
    ("Ich wohnte seit dem Erwerb durchgehend selbst im Haus. Kann der Verkauf schon vor Ablauf von zehn Jahren steuerbegünstigt sein?", ("innerhalb der zehn jahre",)),
    ("Im Abgabenbescheid der Gemeinde stehen Wasser, Grundsteuer und Straßenreinigung. Sind diese Kosten einzeln zu beurteilen?", ("getrennt", "straßenreinigung")),
]


@pytest.mark.parametrize("frage,erwartet", FAELLE)
def test_unbekannte_varianten(frage, erwartet):
    antwort, quellen = rag_assistent.beantworte(
        frage,
        steuerjahr=2023,
        steuerprofil={
            "person": {"angestellter": True, "hausbesitzer": True},
            "grundabgaben_standardobjekt": {
                "gebaeudeart": "Mehrfamilienhaus",
                "nutzung": "teilweise selbst genutzt und teilweise vermietet",
            },
        },
    )
    assert all(wort.casefold() in antwort.casefold() for wort in erwartet), antwort
    assert quellen and re.search(r"\[\d+\]", antwort)
    assert all(rag_assistent._amtliche_quelle(quelle) for quelle in quellen)
    assert all(rag_assistent.quelle_passt_zum_steuerjahr(quelle.payload, 2023) for quelle in quellen)
