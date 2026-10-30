from umgangssprache_antwortsystem_webtest import (
    bewerte_antwort,
    lade_faelle,
    repraesentative_faelle,
)


def test_beide_zurueckgehaltenen_korpora_werden_geladen():
    faelle = lade_faelle()
    assert len(faelle) == 172
    assert {fall["korpus"] for fall in faelle} == {
        "kanonisierung_test.jsonl",
        "praxis_kanonisierung_test.jsonl",
    }


def test_hauptstichprobe_deckt_jede_fachbasis_und_alle_praxisfaelle_ab():
    faelle = repraesentative_faelle(lade_faelle())
    assert len(faelle) == 20
    assert len({fall["basis_id"] for fall in faelle if fall["basis_id"]}) == 8
    assert sum(fall["basis_id"] is None for fall in faelle) == 12
    assert len({fall["stil"] for fall in faelle if fall["stil"]}) == 4


def test_pauschale_sicherheitsverweigerung_ist_fehler():
    status, gruende = bewerte_antwort(
        "Das kann ich anhand der gefundenen amtlichen Quellen nicht sicher beantworten. "
        "Deshalb gebe ich keine steuerliche Behauptung aus.",
        [],
        "Welche Unterlagen benötige ich?",
    )
    assert status == "FEHLER"
    assert "Pauschale Verweigerung oder Systemfehler" in gruende


def test_reine_kanonisierung_ist_fehler():
    status, gruende = bewerte_antwort(
        "Welche Unterlagen benötige ich für meine Lohnsteuererklärung?",
        [],
        "Welche Unterlagen benötige ich für meine Lohnsteuererklärung?",
    )
    assert status == "FEHLER"
    assert "Frage nur kanonisiert, nicht beantwortet" in gruende


def test_antwort_mit_quelle_besteht():
    status, gruende = bewerte_antwort(
        "Für Arbeitnehmer ist die Lohnsteuerbescheinigung regelmäßig eine wichtige Unterlage.",
        [{"url": "https://www.elster.de/"}],
        "Welche Unterlagen benötige ich?",
    )
    assert (status, gruende) == ("BESTANDEN", [])


def test_antwort_ohne_quelle_wird_manuell_geprueft():
    status, gruende = bewerte_antwort(
        "Bitte halten Sie die Lohnsteuerbescheinigung bereit.",
        [],
        "Welche Unterlagen benötige ich?",
    )
    assert status == "PRUEFEN"
    assert gruende == ["Keine amtliche Quelle an der Antwort"]
