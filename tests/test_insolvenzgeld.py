import sys
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import rag_assistent
import web_ui
from steuerjahr_pakete import quelle_passt_zum_steuerjahr


def antwort(frage: str, jahr: int = 2023):
    return rag_assistent.beantworte(frage, steuerjahr=jahr, steuerprofil={})


def test_insolvenzgeld_ist_eigenes_kernthema():
    assert any("Insolvenzgeld" in thema for thema in rag_assistent.ASSISTENTEN_KERNTHEMEN)


def test_grundantwort_trennt_zeitraum_und_antragsfrist():
    text, quellen = antwort("Was ist Insolvenzgeld und wie lange habe ich für den Antrag?")
    assert "Agentur für Arbeit" in text
    assert "zwei Monaten" in text
    assert "bloße Insolvenzantrag" in text
    assert quellen[0].payload["kategorie"] == "Insolvenzgeld Anspruch und Antrag"


def test_alltagssprache_braucht_den_fachbegriff_nicht():
    text, _ = antwort("Mein Chef ist pleite und zwei Gehälter fehlen. Wer zahlt mir den Lohn?")
    assert "Insolvenzgeld" in text
    assert "Agentur für Arbeit" in text
    assert "letzten drei Monate" in text


def test_bl_osser_insolvenzantrag_ist_noch_nicht_das_ereignis():
    text, _ = antwort(
        "Meine Firma hat Insolvenz angemeldet und mein Gehalt ist noch offen. Bekomme ich Insolvenzgeld?"
    )
    assert "bloß gestellter Insolvenzantrag" in text
    assert "noch nicht automatisch" in text
    assert "Zweimonatsfrist" in text


def test_dreimonatszeitraum_wird_nicht_mit_antragsfrist_verwechselt():
    text, _ = antwort("Für welche drei Monate bekomme ich Insolvenzgeld?")
    assert "offene Arbeitsentgelt" in text
    assert "letzten drei Monaten" in text
    assert "vor dem Insolvenzereignis" in text


def test_noetige_unterlagen_werden_konkret_genannt():
    text, _ = antwort("Welche Unterlagen brauche ich für Insolvenzgeld?")
    assert "Insolvenzgeldbescheinigung" in text
    assert "Arbeitsvertrag" in text
    assert "letzten drei Verdienstabrechnungen" in text
    assert "Aktenzeichen" in text


def test_erhalt_von_insolvenzgeld_wird_mit_leistungsnachweis_belegt():
    text, quellen = antwort("wie weise ich den erhalt von insolvenzgeld nach")
    assert text.startswith("Den Erhalt und die Höhe")
    assert "Leistungsnachweis der Agentur für Arbeit" in text
    assert "elektronisch an das Finanzamt übermittelten Daten" in text
    assert "Kontoauszug ist nur ein ergänzender Zahlungsbeleg" in text
    assert "letzten drei Monate" not in text
    assert quellen[0].payload["kategorie"] == "Insolvenzgeld Nachweis"
    assert "Merkblatt-10-Insolvenzgeld" in quellen[0].payload["url"]


def test_nachweis_fuer_den_antrag_bleibt_vom_erhaltsnachweis_getrennt():
    text, quellen = antwort("Welche Nachweise brauche ich für den Antrag auf Insolvenzgeld?")
    assert "Arbeitsvertrag" in text
    assert "letzten drei Verdienstabrechnungen" in text
    assert quellen[0].payload["kategorie"] == "Insolvenzgeld Anspruch und Antrag"


def test_minijobber_koennen_anspruch_haben():
    text, _ = antwort("Können auch Minijobber Insolvenzgeld bekommen?")
    assert "Minijobber" in text
    assert "Arbeitnehmer" in text
    assert "offenen Lohn" in text


def test_hoehe_ist_netto_und_nicht_unbegrenzt():
    text, _ = antwort("Wie hoch ist das Insolvenzgeld, brutto oder netto?")
    assert "Nettoarbeitsentgelt" in text
    assert "Beitragsbemessungsgrenze" in text
    assert "Abrechnungen" in text


def test_steuerbehandlung_fuer_2023_bis_2025():
    for jahr in (2023, 2024, 2025):
        text, quellen = antwort(
            "Muss ich Insolvenzgeld versteuern und in der Steuererklärung angeben?", jahr
        )
        assert "steuerfrei" in text
        assert "Progressionsvorbehalt" in text
        assert str(jahr) in text
        assert "mehr als 410 Euro" in text
        assert quellen[0].payload["kategorie"] == "Insolvenzgeld Steuererklärung"
        assert quelle_passt_zum_steuerjahr(quellen[0].payload, jahr)


def test_insolvenzgeld_ist_auch_mit_tippfehler_nicht_absetzbar():
    text, quellen = antwort("kann ich insolvebtsgeld steuerlich absetzten", 2023)
    assert "nicht als Sonderausgabe" in text
    assert "Werbungskosten" in text
    assert "außergewöhnliche Belastung" in text
    assert "auch nicht teilweise" in text
    assert "steuerfrei" in text
    assert "Progressionsvorbehalt" in text
    assert quellen[0].payload["kategorie"] == "Insolvenzgeld Steuererklärung"


def test_keine_falsche_fuenfzig_prozent_regel_im_mehrschritt_dialog():
    text, _ = antwort(
        "Vorheriger Gesprächskontext:\n"
        "Letzte Nutzerangabe: kann ich insolvebtsgeld steuerlich absetzten\n"
        "Letzte Assistentenantwort: Insolvenzgeld ist steuerfrei.\n"
        "Aktuelle Ergänzung: ich habe es als arbeitnehmer bekommen",
        2023,
    )
    assert "steuerfrei" in text
    assert "Progressionsvorbehalt" in text
    assert "50 %" not in text
    assert "1.000 Euro" not in text


def test_elektronisch_uebernommenes_insolvenzgeld_nicht_doppelt_erfassen():
    text, _ = antwort("Das Insolvenzgeld steht schon elektronisch in ELSTER. Muss ich es nochmal selber eintragen?")
    assert "nicht ein zweites Mal" in text
    assert "Leistungsnachweis" in text


def test_elster_ort_wird_ohne_starre_zeilennummer_genannt():
    text, _ = antwort("Wo trage ich Insolvenzgeld bei ELSTER ein?", 2025)
    assert "Einkommensersatzleistungen" in text
    assert "Hauptvordruck" in text
    assert "genaue Zeile hängt vom Steuerjahr ab" in text


def test_410_euro_sind_keine_abzugsgrenze_und_leistungen_werden_addiert():
    text, _ = antwort("Ich hatte 300 Euro Insolvenzgeld und 250 Euro Krankengeld. Zählt das für die 410 Euro zusammen?")
    assert "kein steuerpflichtiger oder abziehbarer Anteil" in text
    assert "zusammengerechnet" in text
    assert "über 410 Euro" in text


def test_insolvenzgeld_verursacht_nicht_automatisch_nachzahlung():
    text, _ = antwort("Bekomme ich wegen Insolvenzgeld automatisch eine Steuernachzahlung?")
    assert "nicht automatisch" in text
    assert "übrigen Einkommen" in text
    assert "bereits einbehaltenen Steuer" in text


def test_nur_insolvenzgeld_ohne_anderes_einkommen_bleibt_steuerfrei():
    text, _ = antwort("Ich hatte nur Insolvenzgeld und kein anderes Einkommen. Muss ich Steuer zahlen?")
    assert "nicht besteuert" in text
    assert "keinen höheren Steuersatz" in text
    assert "Pflicht zur Abgabe" in text


def test_vorfinanziertes_insolvenzgeld_bleibt_dem_arbeitnehmer_zugerechnet():
    text, _ = antwort("Eine Bank hat mein Insolvenzgeld vorfinanziert. Ist das steuerlich anders?")
    assert "dem Arbeitnehmer zugerechnet" in text
    assert "steuerfrei" in text
    assert "Progressionsvorbehalt" in text


def test_falsche_fuenfzig_prozent_vorantwort_wird_im_folgeschritt_korrigiert():
    text, _ = antwort(
        "Vorheriger Gesprächskontext:\n"
        "Letzte Nutzerangabe: kann ich insolvebtsgeld steuerlich absetzten\n"
        "Letzte Assistentenantwort: Du kannst Insolvenzgeld zu 50 % als außergewöhnliche "
        "Belastung beziehungsweise Sonderausgabe absetzen.\n"
        "Aktuelle Ergänzung: ich habe es als arbeitnehmer bekommen",
        2023,
    )
    assert "nicht als Sonderausgabe" in text
    assert "auch nicht teilweise" in text
    assert "steuerfrei" in text
    assert "Progressionsvorbehalt" in text
    assert "50 % als" not in text


def test_umgangssprachliche_folge_bleibt_beim_insolvenzgeld():
    text, _ = antwort(
        "Vorheriger Gesprächskontext:\n"
        "Letzte Nutzerangabe: Mein Arbeitgeber ist pleite und zwei Gehälter fehlen.\n"
        "Letzte Assistentenantwort: Du kannst Insolvenzgeld bei der Agentur für Arbeit beantragen.\n"
        "Aktuelle Ergänzung: Muss ich das bei der Steuer angeben?",
        2024,
    )
    assert "Insolvenzgeld selbst ist steuerfrei" in text
    assert "Progressionsvorbehalt" in text
    assert "2024" in text


def test_web_api_fuehrt_echten_mehrschritt_dialog():
    web_ui.app.config.update(TESTING=True)
    client = web_ui.app.test_client()
    verlauf = [
        {
            "rolle": "nutzer",
            "text": "Mein Arbeitgeber ist pleite und hat die letzten zwei Gehälter nicht bezahlt.",
        },
        {
            "rolle": "assistent",
            "text": "Dann kann Insolvenzgeld bei der Agentur für Arbeit in Betracht kommen.",
        },
    ]
    with patch.object(web_ui, "dialogantwort", return_value=None), patch.object(
        web_ui, "lade_steuerprofil", return_value={}
    ):
        response = client.post(
            "/api/frage",
            json={
                "frage": "Ist das steuerfrei oder muss ich das angeben?",
                "verlauf": verlauf,
                "steuerjahr": "2025",
            },
        )

    assert response.status_code == 200
    daten = response.get_json()
    assert "Insolvenzgeld selbst ist steuerfrei" in daten["antwort"]
    assert "Progressionsvorbehalt" in daten["antwort"]
    assert daten["quellen"][0]["jahr"] == "2023-2025"
