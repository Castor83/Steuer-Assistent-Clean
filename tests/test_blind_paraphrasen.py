"""Holdout: neue Formulierungen, die nicht als Implementierungsvorlagen dienten."""

import re
import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import rag_assistent


FAELLE = [
    ("Womit belege ich dem Finanzamt die Zahlung von Insolvenzgeld?", ("leistungsnachweis", "agentur für arbeit")),
    ("Wird das Insolvenzgeld selbst besteuert, wenn ich 2023 Arbeitnehmer war?", ("steuerfrei", "progressionsvorbehalt")),
    ("Meine Firma ist pleite und zwei Monatsgehälter fehlen – welche Leistung hilft?", ("insolvenzgeld",)),
    ("Die Mietersicherheit liegt noch unangetastet auf dem Kautionskonto. Ist das schon Einnahme?", ("keine mieteinnahme", "rückzahlbare sicherheit")),
    ("Der Bewohner überweist seit Wochen keine Miete. Muss ich den offenen Betrag trotzdem erklären?", ("zuflussprinzip", "nicht als einnahme")),
    ("Meine Schwester soll günstig wohnen. Welche Prozentgrenzen gelten für den Kostenabzug?", ("66 prozent", "50 prozent")),
    ("Zählt für den Arbeitsweg morgens und abends die doppelte Strecke?", ("einfache", "hin- und rückweg")),
    ("Kann ich einen fast nur beruflich eingesetzten Rechner steuerlich berücksichtigen?", ("beruflich", "werbungskosten")),
    ("Ein Fachbuch für meinen Beruf kostete 200 Euro; sonst hatte ich keine Jobkosten.", ("1.230 euro", "erst höhere gesamte werbungskosten")),
    ("Mindern meine Beiträge zur gesetzlichen Rentenkasse das steuerliche Ergebnis?", ("vorsorgeaufwendungen",)),
    ("Welche grundlegenden Versicherungsbeiträge zählen zur Vorsorge?", ("rentenversicherung", "kranken-", "pflege")),
    ("Muss der pauschal besteuerte Nebenjob in meine Einkommensteuerformulare?", ("nicht", "einkommensteuererklärung")),
    ("Bekomme ich durch die Erklärung garantiert Geld zurück?", ("garantiert", "nachzahlung")),
    ("Bis zu welchem Datum musste eine selbst erstellte Pflicht-Erklärung für 2023 raus?", ("2. september 2024",)),
    ("Ich habe das Haus selbst bewohnt und möchte vor Ablauf von zehn Jahren verkaufen. Gibt es eine Ausnahme?", ("innerhalb der zehn jahre", "selbst")),
    ("Sind laufende Pflegekosten für den von Mietern mitgenutzten Garten anteilig abziehbar?", ("anteilig abziehbar", "gartenpflege")),
    ("Die vorhandene alte Zentralheizung wird ersetzt. Wie ist das bei der Vermietung einzuordnen?", ("erhaltungsaufwand", "vermieteten")),
    ("Gibt es eine gesetzlich feste Bearbeitungszeit für meinen Einkommensteuerbescheid?", ("keine allgemein feste",)),
    ("Hebelt ein Sperrvermerk beim BZSt meine Kirchensteuerpflicht aus?", ("nicht", "kirchensteuerpflicht")),
    ("Im Grundabgabenbescheid stehen Grundsteuer, Abwasser und Straßenreinigung zusammen. Darf ich nur die Summe prüfen?", ("getrennt", "abwasser", "straßenreinigung")),
]


@pytest.mark.parametrize("frage,erwartet", FAELLE)
def test_blinde_umformulierung_bleibt_fachlich_belegt(frage, erwartet):
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
    klein = antwort.casefold()
    assert all(begriff.casefold() in klein for begriff in erwartet)
    assert quellen
    assert re.search(r"\[\d+\]", antwort)
    assert all(rag_assistent._amtliche_quelle(quelle) for quelle in quellen)
    assert all(rag_assistent.quelle_passt_zum_steuerjahr(quelle.payload, 2023) for quelle in quellen)
