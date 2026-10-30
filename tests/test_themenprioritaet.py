"""Sachverhaltswörter dürfen die tatsächlich gestellte Frage nicht verdrängen."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
import rag_assistent as rag
from antwortentscheidung import Antwortstatus, pruefe_sachverhalt
from fragefokus import bestimme_fragefokus


def test_kernthemen_entsprechen_dem_bayern_praxisfokus():
    assert rag.ASSISTENTEN_KERNTHEMEN == (
        "Lohnsteuer",
        "Grundsteuer und kommunale Grundabgaben",
        "Verfahren beim Erhalt von Insolvenzgeld und seine Steuerbehandlung",
        "Erbschaft- und Schenkungsteuer",
    )


@pytest.mark.parametrize(
    "frage,erwartet",
    (
        ("Bis wann muss ich Insolvenzgeld beantragen?", "verfahrensfrist"),
        ("Innerhalb welcher Frist muss ich die Schenkung anzeigen?", "verfahrensfrist"),
        ("Werden Erwerbe innerhalb von zehn Jahren zusammengerechnet?", "materieller_zeitraum"),
    ),
)
def test_fristfragen_werden_nach_rechtswirkung_getrennt(frage, erwartet):
    assert rag.gesuchter_fristtyp(frage) == erwartet


@pytest.mark.parametrize("frage", [
    "Wer meldet bei der Grundsteuer eine Änderung der Nutzung?",
    "Ich vermiete ein Haus. Unterscheiden sich die Grundsteuererklärungen je Land?",
    "Welches Grundsteuermodell gilt in Hessen?",
])
def test_jahresregeln_uebernehmen_keine_fremde_grundsteuerfrage(frage):
    assert rag.steuerjahr_grundantwort(frage, 2025, {}) is None


@pytest.mark.parametrize("steuerart", ["Einkommensteuer", "Lohnsteuer"])
def test_steuerabzug_bei_leistung_ist_keine_anspruchsfrage(steuerart):
    antwort, quellen = rag.insolvenzgeld_grundfall(
        f"Wird bei meinem Insolvenzgeld {steuerart} abgezogen?", 2024
    )
    assert "steuerfrei" in antwort
    assert {q.payload["datei"] for q in quellen} == {"insolvenzgeld_steuer_2023_2025.json"}


def test_rechtsbehelfsfrist_ist_keine_bearbeitungsdauer():
    antwort, quellen = rag.neu_abgesicherte_grundfaelle(
        "Wie lange darf ich gegen den Steuerbescheid Einspruch einlegen?", [], 2025
    )
    assert "Bekanntgabe" in antwort
    assert "Bearbeitung" not in antwort
    assert quellen


def test_kindergeld_anspruch_ist_keine_guenstigerpruefung():
    frage = "Habe ich für meinen digitalen Avatar Anspruch auf Kindergeld?"
    assert pruefe_sachverhalt(frage).status == Antwortstatus.ANTWORT
    assert rag.neu_abgesicherte_grundfaelle(frage, [], 2025) is None


@pytest.mark.parametrize("frage,passend,fremd", [
    ("Wer meldet eine Änderung zur Grundsteuer?",
     "bmf_grundsteuer_erklaerungspflicht.json", "steuerjahr_2025_vermietung_eigenheim.json"),
    ("Bis wann darf ich Einspruch einlegen?",
     "ao_355_einspruchsfrist_2025.json", "ao_122_124_bekanntgabe_historisch.json"),
    ("Für wen bekomme ich Kindergeld?",
     "estg_63_kinder_2025.json", "estg_33a_ausbildungsfreibetrag.json"),
    ("Mein Mietobjekt steht leer. Kann ich Kosten abziehen?",
     "steuerjahr_2024_vermietung_eigenheim.json", "estg_33_hochwasserschaden_eigenheim.json"),
    ("Das Finanzamt hat geschätzt. Muss ich die Erklärung noch abgeben?",
     "ao_149_162_schaetzung_erklaerung_2025.json", "bmf_grundsteuer_erklaerungspflicht.json"),
])
def test_quelle_muss_den_gefragten_aspekt_belegen(frage, passend, fremd):
    fokus = bestimme_fragefokus(frage)
    assert fokus.passt(rag.quelle_aus_datei(passend).payload)
    assert not fokus.passt(rag.quelle_aus_datei(fremd).payload)


def test_freie_altantwort_darf_strenge_generierung_nicht_umgehen(monkeypatch):
    quelle = rag.quelle_aus_datei("bmf_grundsteuer_erklaerungspflicht.json")
    monkeypatch.setattr(rag, "suche_wissen", lambda *a, **k: [quelle])
    monkeypatch.setattr(rag, "_beantworte_ohne_zentrale_quellensperre",
                        lambda *a, **k: ("Ungeprüfte Zusatzannahme [1].", [quelle]))
    aufrufe = []

    def generiere(frage, quellen, jahr):
        aufrufe.append(quellen)
        return "Die Eigentümer sind zuständig [1]."

    monkeypatch.setattr(rag, "_generiere_strikt_quellenbasiert", generiere)
    antwort, quellen = rag.beantworte("Wer meldet Änderungen zur Grundsteuer?", steuerjahr=2025)
    assert aufrufe == [[quelle]]
    assert "Zusatzannahme" not in antwort
    assert quellen == [quelle]


def test_hintergrundthema_verdrangt_aktuelle_frage_nicht():
    frage = "Das Haus ist vermietet, Grundsteuer wurde gezahlt und eine Erklärung abgegeben.\nWie werden die Einkünfte zusammengerechnet?"
    assert bestimme_fragefokus(frage) is None


def test_eigene_kostenschaetzung_ist_keine_finanzamtsschaetzung():
    assert bestimme_fragefokus("Darf ich geschätzte Fahrtkosten in der Erklärung angeben?") is None


def test_quellenmarke_allein_erlaubt_keinen_erfundenen_betrag(monkeypatch):
    quelle = rag.quelle_aus_datei("estg_9a_arbeitnehmer_pauschbetrag.json")
    monkeypatch.setattr(rag.MODELL_RESSOURCEN, "chat", lambda *args, **kwargs: {
        "message": {"content": "Der Arbeitnehmer-Pauschbetrag beträgt 9.999 Euro [1]."}
    })
    assert rag._generiere_strikt_quellenbasiert(
        "Wie hoch ist der Arbeitnehmer-Pauschbetrag?", [quelle], 2025
    ) is None


@pytest.mark.parametrize("frage", [
    "Muss ich nach einer Schätzung durch das Finanzamt noch eine Steuererklärung abgeben?",
    "Das Finanzamt hat geschätzt. Erledigt sich meine fehlende Erklärung?",
])
def test_schaetzung_waehlt_keine_reine_abgabefrist(frage):
    fokus = bestimme_fragefokus(frage)
    assert fokus.passt(rag.quelle_aus_datei("ao_149_162_schaetzung_erklaerung_2025.json").payload)
    assert not fokus.passt({"quelle": "Pflicht zur Steuererklärung und Abgabefristen",
                            "paragraph": "§ 149 AO", "kategorie": "Erklärungspflicht"})


def test_suchbegriffe_werden_nicht_zu_zusaetzlichen_nutzeranforderungen(monkeypatch):
    frage = "Ist die Erklärung zur Grundsteuer überall gleich?"
    quelle = rag.quelle_aus_datei("grsth_2025_bundesmodell_laendermodelle.json")
    monkeypatch.setattr(rag, "suche_wissen", lambda *a, **k: [quelle])
    monkeypatch.setattr(rag, "_beantworte_ohne_zentrale_quellensperre", lambda *a, **k: ("", []))
    gesehen = []
    def generiere(text, quellen, jahr):
        gesehen.append(text)
        return "Das hängt vom Landesmodell ab [1]."
    monkeypatch.setattr(rag, "_generiere_strikt_quellenbasiert", generiere)
    rag.beantworte(frage, steuerjahr=2025)
    assert gesehen == [frage]


@pytest.mark.parametrize("frage", [
    "Ich vermiete zwei Wohnungen. Ist die Grundsteuererklärung überall gleich?",
    "Gilt bei der Grundsteuer bundesweit dasselbe Verfahren?",
    "Welches Grundsteuermodell gilt in Hessen?",
])
def test_modellvergleich_ist_keine_erklaerungspflicht(frage):
    fokus = bestimme_fragefokus(frage)
    assert fokus.passt(rag.quelle_aus_datei("grsth_2025_bundesmodell_laendermodelle.json").payload)
    assert not fokus.passt(rag.quelle_aus_datei("bmf_grundsteuer_erklaerungspflicht.json").payload)


def test_bayern_modellfrage_behaelt_die_spezifische_flaechenmodellquelle():
    fokus = bestimme_fragefokus(
        "Welches Berechnungsmodell nutzt Bayern für die neue Grundsteuer?"
    )
    assert fokus.passt(
        rag.quelle_aus_datei("steuerjahr_2025_grundsteuer_bayern.json").payload
    )


def test_erbschaftssteuer_schreibvariante_wird_als_erbschaftsteuer_belegt():
    quelle = rag.quelle_aus_datei("erbstg_freibetraege_steuersaetze.json")
    assert rag._quellen_decken_fachbegriff(
        "Wie hoch ist die Erbschaftssteuer?", [quelle]
    )


def test_firmen_e_bike_wird_nicht_zum_arbeitsweg_umgeschrieben():
    frage = rag.kanonisiere_alltagssprache(
        rag.normalisiere(
            "Der Arbeitgeber überlässt ein Firmen-E-Bike zusätzlich zum Arbeitslohn."
        )
    )
    assert "§ 3 nummer 37" in frage.casefold()
    assert "entfernungspauschale" not in frage.casefold()
