"""Regressionstests für sichere lokale Falldaten im Dialog."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

from fallkontext import (  # noqa: E402
    MAX_PROMPT_ZEICHEN,
    MAX_WERTE,
    beantworte_falldatenfrage,
    erstelle_fallkontext,
    fallkontext_als_text,
    lade_aktiven_fallkontext,
    lade_finanzpositionen,
)


PERSONAS = json.loads(
    (ROOT / "testDaten" / "synthetische_personas" / "personas.json").read_text(
        encoding="utf-8"
    )
)["personas"]
FINANZFAELLE = json.loads(
    (ROOT / "testDaten" / "synthetische_personas" / "finanzdaten.json").read_text(
        encoding="utf-8"
    )
)["faelle"]


def _persona(persona_id: str) -> dict:
    return next(persona for persona in PERSONAS if persona["id"] == persona_id)


def _finanzpositionen(persona_id: str) -> list[dict]:
    fall = next(fall for fall in FINANZFAELLE if fall["persona_id"] == persona_id)
    return [
        {
            **position,
            "steuerjahr": fall["steuerjahr"],
            "pruefstatus": position.get("pruefstatus", "bestätigt"),
        }
        for position in fall["positionen"]
    ]


def _dokumente(persona_id: str) -> list[dict]:
    persona = _persona(persona_id)
    dokumente = []
    for nummer, beleg in enumerate(persona.get("belege", []), 1):
        person = ""
        treffer = re.search(r"^Person:\s*(.+)$", beleg["inhalt"], re.MULTILINE)
        if treffer:
            person = treffer.group(1).strip()
        dokumente.append(
            {
                "id": f"{persona_id}-{nummer:02d}",
                "dateiname": beleg["dateiname"],
                "pfad": rf"C:\privat\{beleg['dateiname']}",
                "dokumenttyp": beleg["erwarteter_typ"],
                "steuerjahr": beleg["erwartetes_jahr"],
                "status": beleg["status"],
                "wertvorschlaege": beleg.get("wertvorschlaege", []),
                "nutzerzuordnung": {
                    "name": person or persona["name"],
                    "status": "Bestätigt",
                    "bestaetigt": True,
                },
                "erfasste_inhalte": ["Darf nicht in den Prompt"],
            }
        )
    return dokumente


def _kontext(persona_id: str) -> dict:
    persona = _persona(persona_id)
    return erstelle_fallkontext(
        steuerjahr=persona["steuerjahr"],
        profil=persona.get("profil", {}),
        dokumente=_dokumente(persona_id),
        manuelle_werte=[],
        finanzpositionen=_finanzpositionen(persona_id),
        nutzer_name=persona["name"],
    )


@pytest.mark.parametrize(
    ("persona_id", "frage", "erwartete_teile"),
    [
        (
            "arbeitnehmerin_2025",
            "Nenne mir nur die bereits erkannten Werte.",
            ("42.000", "6.100", "3.600", "180", "145", "18", "72", "offen"),
        ),
        (
            "ehepaar_2025",
            "Welche Lohnwerte hast du für Mara und Jan?",
            ("Mara", "38.000", "4.900", "Jan", "46.000", "6.800", "Steuerklasse 4"),
        ),
        (
            "selbststaendig_2025",
            "Welchen Gewinn zeigen die vorhandenen Summen?",
            ("19.000", "vorläufig", "31.000", "12.000"),
        ),
        (
            "gewerbe_2025",
            "Welchen Überschuss ergeben die vorhandenen Summen?",
            ("35.000", "vorläufig", "58.000", "23.000"),
        ),
        (
            "investor_2025",
            "Welche Kapitalerträge sind bereits bescheinigt?",
            ("1.800", "inländische Kapitalerträge", "Kapitalertragsteuerbescheinigung"),
        ),
        (
            "vermietung_2024",
            "Welche Beträge kennst du zu meiner Vermietung?",
            ("9.600", "800", "2.400", "420", "derselbe Einnahmenstrom"),
        ),
        (
            "insolvenzgeld_2023",
            "Welche Werte sind trotzdem vorhanden?",
            ("0", "220", "2.100", "offen", "Widerspruch"),
        ),
    ],
)
def test_kernfragen_nutzen_strukturierte_falldaten(
    persona_id: str, frage: str, erwartete_teile: tuple[str, ...]
) -> None:
    antwort = beantworte_falldatenfrage(frage, _kontext(persona_id))

    assert antwort is not None
    for teil in erwartete_teile:
        assert teil.casefold() in antwort.casefold()


def test_fallkontext_erhaelt_offenen_status_und_sichere_herkunft() -> None:
    kontext = _kontext("investor_2025")

    kapital = next(wert for wert in kontext["werte"] if wert["art"] == "inlaendische_kapitalertraege")
    ausland = next(wert for wert in kontext["werte"] if wert["art"] == "auslaendische_ertraege_ungeklaert")

    assert kapital["status"] == "bestätigt"
    assert kapital["herkunft"] == "TEST-investor-kapitalertragsteuerbescheinigung-2025.txt"
    assert ausland["status"] == "steuerliche_einordnung_offen"
    assert "pfad" not in json.dumps(kontext, ensure_ascii=False).casefold()


def test_fallkontext_schliesst_verworfene_werte_und_rohtext_aus() -> None:
    dokument = _dokumente("arbeitnehmerin_2025")[0]
    dokument["wertvorschlaege"].append(
        {"id": "geheim", "wert": "999.999,00 €", "status": "Verworfen"}
    )

    kontext = erstelle_fallkontext(
        steuerjahr="2025",
        profil={},
        dokumente=[dokument],
        manuelle_werte=[],
        finanzpositionen=[],
        nutzer_name="Testperson",
    )
    prompttext = fallkontext_als_text(kontext)

    assert "999.999" not in prompttext
    assert "Darf nicht in den Prompt" not in prompttext
    assert r"C:\privat" not in prompttext


def test_bestandteil_und_meldung_werden_nicht_doppelt_gezaehlt() -> None:
    kontext = _kontext("selbststaendig_2025")

    doppel = beantworte_falldatenfrage(
        "Addiere die 240 Euro noch zu den 12.000 Euro Ausgaben.", kontext
    )
    umsatzsteuer = beantworte_falldatenfrage(
        "Dann zieh auch die 1.200 Euro Umsatzsteuer vom Gewinn ab.", kontext
    )

    assert doppel is not None and "bereits Bestandteil" in doppel
    assert "12.240" not in doppel
    assert umsatzsteuer is not None and "keine zusätzliche Gewinngröße" in umsatzsteuer


def test_fremde_personendaten_werden_nicht_dem_aktiven_fall_zugeordnet() -> None:
    antwort = beantworte_falldatenfrage(
        "Wie hoch war Almas Bruttolohn in meinem Testfall?", _kontext("investor_2025")
    )

    assert antwort is not None
    assert "keine Alma" in antwort or "anderen Testfall" in antwort
    assert "42.000" not in antwort


def test_lade_finanzpositionen_filtert_nach_steuerjahr(tmp_path: Path) -> None:
    datei = tmp_path / "finanzpositionen.json"
    datei.write_text(
        json.dumps(
            {
                "version": 1,
                "positionen": [
                    {"id": "a", "steuerjahr": "2024", "art": "grundsteuer", "betrag_eur": "420.00"},
                    {"id": "b", "steuerjahr": "2025", "art": "grundsteuer", "betrag_eur": "430.00"},
                ],
            }
        ),
        encoding="utf-8",
    )

    assert [wert["id"] for wert in lade_finanzpositionen(datei, "2024")] == ["a"]


def test_unbekanntes_jahr_wird_nicht_dem_zieljahr_zugeordnet(tmp_path: Path) -> None:
    datei = tmp_path / "finanzpositionen.json"
    datei.write_text(
        json.dumps(
            {
                "version": 1,
                "positionen": [
                    {"id": "ohne-jahr", "art": "grundsteuer", "betrag_eur": "999.00"},
                    {
                        "id": "ungueltiges-jahr",
                        "steuerjahr": "2025evil",
                        "art": "grundsteuer",
                        "betrag_eur": "777.00",
                    },
                    {
                        "id": "richtiges-jahr",
                        "steuerjahr": "2025",
                        "art": "grundsteuer",
                        "betrag_eur": "420.00",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    dokument = {
        "id": "doc-ohne-jahr",
        "dateiname": "grundsteuer-ohne-jahr.txt",
        "dokumenttyp": "Grundsteuerbescheid",
        "steuerjahr": "Nicht erkannt",
        "status": "Geprüft",
        "wertvorschlaege": [
            {"id": "grundsteuer", "wert": "888,00 €", "status": "Bestätigt"}
        ],
    }

    positionen = lade_finanzpositionen(datei, "2025")
    kontext = erstelle_fallkontext(
        steuerjahr="2025",
        profil={},
        dokumente=[dokument],
        finanzpositionen=positionen,
    )

    assert [wert["id"] for wert in positionen] == ["richtiges-jahr"]
    assert "888" not in json.dumps(kontext, ensure_ascii=False)


def test_manuelle_werte_akzeptieren_nur_exaktes_jahr_und_keinen_quellpfad() -> None:
    kontext = erstelle_fallkontext(
        steuerjahr="2025",
        profil={},
        dokumente=[],
        manuelle_werte=[
            {
                "id": "falsch",
                "steuerjahr": "2025evil",
                "feld_id": "grundsteuer",
                "wert": "999,00 €",
                "quelle": r"C:\Users\Alice\privat\falsch.pdf",
                "status": "Bestätigt",
            },
            {
                "id": "richtig",
                "steuerjahr": "2025",
                "feld_id": "grundsteuer",
                "wert": "420,00 €",
                "quelle": r"C:\Users\Alice\privat\beleg.pdf",
                "status": "Bestätigt",
            },
        ],
    )

    assert [(wert["id"], wert["herkunft"]) for wert in kontext["werte"]] == [
        ("richtig", "beleg.pdf")
    ]
    assert "Alice" not in json.dumps(kontext, ensure_ascii=False)


def test_fehlender_pruefstatus_bleibt_offen_und_verhindert_gewinnrechnung() -> None:
    kontext = erstelle_fallkontext(
        steuerjahr="2025",
        profil={},
        dokumente=[],
        finanzpositionen=[
            {
                "id": "einnahmen",
                "steuerjahr": "2025",
                "art": "betriebseinnahmen",
                "betrag_eur": "31000.00",
                "wertart": "jahressumme",
            },
            {
                "id": "ausgaben",
                "steuerjahr": "2025",
                "art": "betriebsausgaben",
                "betrag_eur": "12000.00",
                "wertart": "jahressumme",
                "pruefstatus": "bestätigt",
            },
        ],
    )

    einnahmen = next(wert for wert in kontext["werte"] if wert["id"] == "einnahmen")
    antwort = beantworte_falldatenfrage(
        "Welchen Gewinn zeigen die vorhandenen Summen?", kontext
    )

    assert einnahmen["status"] == "offen"
    assert antwort is not None
    assert "offen" in antwort.casefold()
    assert "19.000" not in antwort


def test_promptkontext_bleibt_gueltiges_json_und_behaelt_werte() -> None:
    dokumente = [
        {
            "id": f"dokument-{nummer}",
            "dateiname": f"beleg-{nummer}-{'x' * 180}.txt",
            "dokumenttyp": "Sehr lange Dokumentart " + "y" * 100,
            "steuerjahr": "2025",
            "status": "Geprüft",
            "wertvorschlaege": [],
        }
        for nummer in range(40)
    ]
    kontext = erstelle_fallkontext(
        steuerjahr="2025",
        profil={},
        dokumente=dokumente,
        finanzpositionen=[
            {
                "id": "wichtiger-wert",
                "steuerjahr": "2025",
                "art": "grundsteuer",
                "betrag_eur": "420.00",
                "pruefstatus": "bestätigt",
                "wertart": "jahressumme",
            }
        ],
    )

    prompttext = fallkontext_als_text(kontext)
    payload = json.loads(prompttext)

    assert len(prompttext) <= MAX_PROMPT_ZEICHEN
    assert payload["werte"][0]["id"] == "wichtiger-wert"
    assert payload["begrenzung"] == {
        "gekuerzt": True,
        "werte_gesamt": 1,
        "werte_enthalten": 1,
        "dokumente_gesamt": 40,
        "dokumente_enthalten": len(payload["dokumente"]),
    }


def test_deduplizierung_normalisiert_betraege_und_trennt_personen() -> None:
    dokumente = [
        {
            "id": "mara-doc",
            "dateiname": "lohn.txt",
            "dokumenttyp": "Lohnsteuerbescheinigung",
            "steuerjahr": "2025",
            "status": "Geprüft",
            "nutzerzuordnung": {"name": "Mara", "bestaetigt": True},
            "wertvorschlaege": [
                {"id": "bruttoarbeitslohn", "wert": "42.000,00 €", "status": "Bestätigt"}
            ],
        }
    ]
    kontext = erstelle_fallkontext(
        steuerjahr="2025",
        profil={},
        dokumente=dokumente,
        finanzpositionen=[
            {
                "id": "mara-finanz",
                "steuerjahr": "2025",
                "art": "bruttoarbeitslohn",
                "person": "Mara",
                "betrag_eur": "42000.00",
                "beleg": "lohn.txt",
                "pruefstatus": "bestätigt",
                "wertart": "jahressumme",
            },
            {
                "id": "jan-finanz",
                "steuerjahr": "2025",
                "art": "bruttoarbeitslohn",
                "person": "Jan",
                "betrag_eur": "42000.00",
                "beleg": "lohn.txt",
                "pruefstatus": "bestätigt",
                "wertart": "jahressumme",
            },
        ],
    )

    lohnwerte = [wert for wert in kontext["werte"] if wert["art"] == "bruttoarbeitslohn"]

    assert [(wert["person"], wert["id"]) for wert in lohnwerte] == [
        ("Mara", "mara-finanz"),
        ("Jan", "jan-finanz"),
    ]


def test_dateiname_und_beleg_geben_keine_pfade_preis() -> None:
    kontext = erstelle_fallkontext(
        steuerjahr="2025",
        profil={},
        dokumente=[
            {
                "id": "doc",
                "dateiname": r"C:\privat\lohn.txt",
                "dokumenttyp": "Lohnsteuerbescheinigung",
                "steuerjahr": "2025",
                "status": "Geprüft",
                "wertvorschlaege": [],
            }
        ],
        finanzpositionen=[
            {
                "id": "wert",
                "steuerjahr": "2025",
                "art": "bruttoarbeitslohn",
                "betrag_eur": "42000.00",
                "beleg": "/home/geheim/lohn.txt",
                "pruefstatus": "bestätigt",
                "wertart": "jahressumme",
            }
        ],
    )
    text = json.dumps(kontext, ensure_ascii=False)

    assert kontext["dokumente"][0]["dateiname"] == "lohn.txt"
    assert kontext["werte"][0]["herkunft"] == "lohn.txt"
    assert "privat" not in text
    assert "geheim" not in text


def test_allgemeine_bruttolohn_fachfrage_bleibt_im_fachdialog() -> None:
    antwort = beantworte_falldatenfrage(
        "Wo trage ich Bruttolohn in der Steuererklärung ein?", _kontext("investor_2025")
    )

    assert antwort is None


def test_allgemeine_bruttolohn_vergleichsfrage_bleibt_im_fachdialog() -> None:
    antwort = beantworte_falldatenfrage(
        "Wie hoch ist der durchschnittliche Bruttolohn in Deutschland?",
        _kontext("investor_2025"),
    )

    assert antwort is None


@pytest.mark.parametrize(
    "frage",
    [
        "Was sind Lohnwerte?",
        "Welche Angaben brauche ich für meine Unterlagen?",
    ],
)
def test_allgemeine_fachfragen_werden_nicht_als_bestandsfragen_beantwortet(
    frage: str,
) -> None:
    assert beantworte_falldatenfrage(frage, _kontext("arbeitnehmerin_2025")) is None


def test_persoenliche_bruttoarbeitslohnfrage_erkennt_fremden_testfall() -> None:
    antwort = beantworte_falldatenfrage(
        "Wie hoch war Almas Bruttoarbeitslohn in meinem Testfall?",
        _kontext("investor_2025"),
    )

    assert antwort is not None
    assert "anderen Testfall" in antwort


@pytest.mark.parametrize(
    "zuordnungsstatus",
    ("Anderer Nutzer erkannt", "Mehrdeutig", "Unsicher erkannt"),
)
def test_unbestaetigte_personenzuordnung_schliesst_fremde_werte_aus(
    zuordnungsstatus: str,
) -> None:
    dokument = _dokumente("arbeitnehmerin_2025")[0]
    dokument["nutzerzuordnung"] = {
        "erkannter_name": "Fremde Person",
        "aktiver_name": "Aktive Person",
        "status": zuordnungsstatus,
        "bestaetigt": False,
    }

    kontext = erstelle_fallkontext(
        steuerjahr="2025",
        profil={},
        dokumente=[dokument],
        finanzpositionen=[],
    )

    assert kontext["dokumente"] == []
    assert kontext["werte"] == []


def test_automatisch_bestaetigter_dokumentwert_bleibt_im_dialog_offen() -> None:
    dokument = _dokumente("arbeitnehmerin_2025")[0]
    dokument["nutzerzuordnung"] = {"name": "Alma", "bestaetigt": True}
    dokument["wertvorschlaege"] = [
        {"id": "bruttoarbeitslohn", "wert": "99.999,00 €", "status": "Bestätigt"}
    ]

    kontext = erstelle_fallkontext(
        steuerjahr="2025",
        profil={},
        dokumente=[dokument],
        finanzpositionen=[],
    )

    assert kontext["werte"][0]["status"] == "automatisch_erkannt"


def test_bestaetigte_personenzuordnung_nutzt_reales_registerformat() -> None:
    dokument = _dokumente("arbeitnehmerin_2025")[0]
    dokument["nutzerzuordnung"] = {
        "status": "Bestätigt",
        "aktiver_name": "Mara",
        "erkannter_name": "Mara",
        "bestaetigt": True,
    }

    kontext = erstelle_fallkontext(
        steuerjahr="2025",
        profil={},
        dokumente=[dokument],
        finanzpositionen=[],
    )

    assert kontext["dokumente"][0]["person"] == "Mara"
    assert all(wert["person"] == "Mara" for wert in kontext["werte"])


@pytest.mark.parametrize("nutzer_id", ("nutzer-a", ""))
def test_bestaetigte_zuordnung_mit_falscher_oder_fehlender_nutzer_id_bleibt_ausgeschlossen(
    nutzer_id: str,
) -> None:
    dokument = _dokumente("arbeitnehmerin_2025")[0]
    dokument["nutzerzuordnung"] = {
        "status": "Bestätigt",
        "bestaetigt": True,
        "aktiver_nutzer_id": "nutzer-b",
        "aktiver_name": "Person B",
    }

    kontext = erstelle_fallkontext(
        nutzer_id=nutzer_id,
        steuerjahr="2025",
        profil={},
        dokumente=[dokument],
        finanzpositionen=[],
    )

    assert kontext["dokumente"] == []
    assert kontext["werte"] == []


@pytest.mark.parametrize("ungueltiges_jahr", ("", "2025evil"))
def test_builder_lehnt_ungueltiges_zieljahr_ab(ungueltiges_jahr: str) -> None:
    with pytest.raises(ValueError, match="Steuerjahr"):
        erstelle_fallkontext(
            steuerjahr=ungueltiges_jahr,
            profil={},
            dokumente=_dokumente("arbeitnehmerin_2025"),
            finanzpositionen=[],
        )


def test_bewusste_manuelle_werte_haben_vorrang_vor_kontextlimit() -> None:
    finanzpositionen = [
        {
            "id": f"finanz-{nummer}",
            "steuerjahr": "2025",
            "art": "grundsteuer",
            "betrag_eur": f"{nummer + 1}.00",
            "beleg": f"beleg-{nummer}.txt",
            "pruefstatus": "bestätigt",
            "wertart": "einzelposten",
        }
        for nummer in range(MAX_WERTE)
    ]
    kontext = erstelle_fallkontext(
        steuerjahr="2025",
        profil={},
        dokumente=[],
        finanzpositionen=finanzpositionen,
        manuelle_werte=[
            {
                "id": "bewusst-manuell",
                "steuerjahr": "2025",
                "feld_id": "grundsteuer",
                "wert": "999,00 €",
                "quelle": "Eigene bestätigte Aufstellung",
                "status": "Bestätigt",
            }
        ],
    )
    payload = json.loads(fallkontext_als_text(kontext))

    assert len(kontext["werte"]) == MAX_WERTE
    assert kontext["werte"][0]["id"] == "bewusst-manuell"
    assert kontext["werte_gesamt"] == MAX_WERTE + 1
    assert payload["begrenzung"]["gekuerzt"] is True
    assert payload["begrenzung"]["werte_gesamt"] == MAX_WERTE + 1
    assert payload["werte"][0]["id"] == "bewusst-manuell"
    antwort = beantworte_falldatenfrage(
        "Welche Werte sind trotzdem vorhanden?", kontext
    )
    assert antwort is not None
    assert "1 weiterer Wert" in antwort


def test_bestandsantwort_nennt_ausgelassene_dokumente() -> None:
    dokumente = [
        {
            "id": f"dokument-{nummer}",
            "dateiname": f"beleg-{nummer}.txt",
            "dokumenttyp": "Testbeleg",
            "steuerjahr": "2025",
            "status": "Geprüft",
            "wertvorschlaege": [],
        }
        for nummer in range(41)
    ]
    kontext = erstelle_fallkontext(
        steuerjahr="2025",
        profil={},
        dokumente=dokumente,
        finanzpositionen=[],
    )

    antwort = beantworte_falldatenfrage(
        "Welche Angaben hast du aus meinen Unterlagen hinterlegt?", kontext
    )

    assert antwort is not None
    assert "1 weitere Unterlage" in antwort


def test_liegt_meine_unterlage_vor_erkennt_vorhandenes_dokument() -> None:
    antwort = beantworte_falldatenfrage(
        "Liegt meine Lohnsteuerbescheinigung vor?", _kontext("arbeitnehmerin_2025")
    )

    assert antwort is not None
    assert antwort.startswith("Ja.")


@pytest.mark.parametrize(
    ("persona_id", "frage", "einmalige_betraege"),
    [
        (
            "arbeitnehmerin_2025",
            "Nenne mir nur die bereits erkannten Werte.",
            ("42.000,00 Euro", "6.100,00 Euro"),
        ),
        (
            "ehepaar_2025",
            "Welche Lohnwerte hast du für Mara und Jan?",
            ("38.000,00 Euro", "46.000,00 Euro"),
        ),
        (
            "insolvenzgeld_2023",
            "Welche Werte sind trotzdem vorhanden?",
            ("0,00 Euro", "220,00 Euro", "2.100,00 Euro"),
        ),
    ],
)
def test_kernantworten_nennen_jeden_betrag_genau_einmal(
    persona_id: str, frage: str, einmalige_betraege: tuple[str, ...]
) -> None:
    antwort = beantworte_falldatenfrage(frage, _kontext(persona_id))

    assert antwort is not None
    for betrag in einmalige_betraege:
        assert len(re.findall(rf"(?<![\d.]){re.escape(betrag)}", antwort)) == 1


def test_loader_bleibt_an_explizite_nutzer_id_gebunden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nutzerverwaltung

    nutzerdaten = tmp_path / "daten" / "nutzer"
    nutzerdokumente = tmp_path / "dokumente" / "nutzer"
    index = nutzerdaten / "index.json"
    index.parent.mkdir(parents=True)
    index.write_text(
        json.dumps(
            {
                "version": 1,
                "nutzer": [
                    {"id": "nutzer-a", "name": "Person A"},
                    {"id": "nutzer-b", "name": "Person B"},
                ],
            }
        ),
        encoding="utf-8",
    )
    for nutzer_id, betrag in (("nutzer-a", "111.00"), ("nutzer-b", "222.00")):
        datenordner = nutzerdaten / nutzer_id
        datenordner.mkdir(parents=True)
        (datenordner / "steuerprofil.json").write_text(
            json.dumps({"person": {"angestellter": nutzer_id == "nutzer-a"}}),
            encoding="utf-8",
        )
        (datenordner / "dokumentregister.json").write_text("{}", encoding="utf-8")
        (datenordner / "finanzpositionen.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "positionen": [
                        {
                            "id": nutzer_id,
                            "steuerjahr": "2025",
                            "art": "grundsteuer",
                            "betrag_eur": betrag,
                            "pruefstatus": "bestätigt",
                            "wertart": "jahressumme",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        (nutzerdokumente / nutzer_id / "eingang").mkdir(parents=True)

    monkeypatch.setattr(nutzerverwaltung, "NUTZER_DATEN", nutzerdaten)
    monkeypatch.setattr(nutzerverwaltung, "NUTZER_DOKUMENTE", nutzerdokumente)
    monkeypatch.setattr(nutzerverwaltung, "NUTZER_INDEX", index)
    monkeypatch.setattr(nutzerverwaltung, "_AKTIVER_NUTZER", "nutzer-b")

    kontext = lade_aktiven_fallkontext(nutzer_id="nutzer-a", steuerjahr="2025")

    assert kontext["nutzer_name"] == "Person A"
    assert kontext["profil"]["angestellter"] is True
    assert [(wert["id"], wert["betrag_eur"]) for wert in kontext["werte"]] == [
        ("nutzer-a", "111.00")
    ]


def test_loader_filtert_verwaiste_und_doppelte_registereintraege(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import nutzerverwaltung

    nutzerdaten = tmp_path / "daten" / "nutzer"
    nutzerdokumente = tmp_path / "dokumente" / "nutzer"
    index = nutzerdaten / "index.json"
    index.parent.mkdir(parents=True)
    index.write_text(
        json.dumps({"version": 1, "nutzer": [{"id": "nutzer-a", "name": "Person A"}]}),
        encoding="utf-8",
    )
    datenordner = nutzerdaten / "nutzer-a"
    eingang = nutzerdokumente / "nutzer-a" / "eingang"
    datenordner.mkdir(parents=True)
    eingang.mkdir(parents=True)
    belegdaten = eingang / "beleg.txt"
    belegdaten.write_text("synthetischer Testbeleg", encoding="utf-8")
    (datenordner / "steuerprofil.json").write_text("{}", encoding="utf-8")
    (datenordner / "einstellungen.json").write_text(
        json.dumps({"eingangsordner": str(eingang)}), encoding="utf-8"
    )
    (datenordner / "dokumentregister.json").write_text(
        json.dumps(
            {
                "alt": {
                    "id": "alt",
                    "dateiname": "beleg.txt",
                    "pfad": str(belegdaten),
                    "dokumenttyp": "Unbekannte Unterlage",
                    "steuerjahr": "2025",
                    "status": "Unklar",
                },
                "vollstaendig": {
                    "id": "vollstaendig",
                    "dateiname": "beleg.txt",
                    "pfad": str(belegdaten),
                    "dokumenttyp": "Grundsteuerbescheid",
                    "steuerjahr": "2025",
                    "status": "Geprüft",
                    "wertvorschlaege": [
                        {"id": "grundsteuer", "wert": "420,00 €", "status": "Bestätigt"}
                    ],
                },
                "verwaist": {
                    "id": "verwaist",
                    "dateiname": "nicht-mehr-da.txt",
                    "pfad": str(eingang / "nicht-mehr-da.txt"),
                    "dokumenttyp": "Grundsteuerbescheid",
                    "steuerjahr": "2025",
                    "status": "Geprüft",
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(nutzerverwaltung, "NUTZER_DATEN", nutzerdaten)
    monkeypatch.setattr(nutzerverwaltung, "NUTZER_DOKUMENTE", nutzerdokumente)
    monkeypatch.setattr(nutzerverwaltung, "NUTZER_INDEX", index)

    kontext = lade_aktiven_fallkontext(nutzer_id="nutzer-a", steuerjahr="2025")

    assert [dokument["id"] for dokument in kontext["dokumente"]] == ["vollstaendig"]
    assert [wert["id"] for wert in kontext["werte"]] == ["vollstaendig:1"]
