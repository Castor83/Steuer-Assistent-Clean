import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "app"))

from elster_mehrjahres_integritaet import pruefe_mehrjahres_golden_master  # noqa: E402
from mein_elster_browser import (  # noqa: E402
    browserlauf,
    erstelle_aktionsplan,
    erstelle_sicherheitskontext,
    lade_browser_mapping,
    lade_eingabehilfe,
    mapping_pfad,
    pruefe_aktionsplan_vor_lauf,
    pruefe_versionsschranke,
)


STEUERJAHRE = ("2023", "2024", "2025")


@pytest.mark.parametrize("steuerjahr", STEUERJAHRE)
def test_mapping_und_layoutvertrag_sind_jahresrein(steuerjahr):
    mapping = lade_browser_mapping(steuerjahr)

    assert mapping_pfad(steuerjahr) == (
        ROOT / "wissen" / "elster" / "mappings" / steuerjahr / "browser_feldmapping_v1.json"
    )
    assert mapping["steuerjahr"] == steuerjahr
    assert mapping["formular_merkmale"] == ["Einkommensteuer", steuerjahr]
    assert mapping["layout_vertrag"]["version"] == f"mein-elster-est{steuerjahr}-layout/v1"
    assert mapping["freigabe"] == {
        "sandbox_validiert": True,
        "live_layout_validiert": False,
    }


@pytest.mark.parametrize("steuerjahr", STEUERJAHRE)
def test_eingabehilfe_waehlt_automatisch_das_richtige_mapping(steuerjahr):
    pfad = ROOT / "tests" / "elster" / steuerjahr / "mein_elster_sandbox.json"
    eingabehilfe = lade_eingabehilfe(pfad)
    plan = erstelle_aktionsplan(eingabehilfe)

    assert plan
    assert {aktion["steuerjahr"] for aktion in plan} == {steuerjahr}
    assert pruefe_aktionsplan_vor_lauf(plan) == []


@pytest.mark.parametrize("steuerjahr", STEUERJAHRE)
def test_versionsschranke_prueft_den_jahresbezogenen_vertrag(steuerjahr):
    mapping = lade_browser_mapping(steuerjahr)
    kontext = erstelle_sicherheitskontext(mapping)

    aktuell, fehler = pruefe_versionsschranke(kontext)

    assert fehler == []
    assert aktuell["steuerjahr"] == steuerjahr


def test_mapping_und_aktionsplan_lehnen_unbekannte_oder_gemischte_jahre_ab():
    with pytest.raises(ValueError, match="Nicht unterstütztes Steuerjahr"):
        mapping_pfad("../../2025")

    plan = [
        {"feld_id": "a", "status": "bereit", "wert": "1", "steuerjahr": "2023"},
        {"feld_id": "b", "status": "bereit", "wert": "2", "steuerjahr": "2024"},
    ]
    assert "Der Aktionsplan vermischt mehrere Steuerjahre." in pruefe_aktionsplan_vor_lauf(plan)


def test_eingabehilfe_und_mapping_duerfen_nicht_aus_verschiedenen_jahren_stammen():
    eingabehilfe = lade_eingabehilfe(
        ROOT / "tests" / "elster" / "2023" / "mein_elster_sandbox.json"
    )
    with pytest.raises(ValueError, match="darf nicht mit Mapping 2024 laufen"):
        erstelle_aktionsplan(eingabehilfe, mapping=lade_browser_mapping("2024"))


@pytest.mark.parametrize("steuerjahr", STEUERJAHRE)
def test_echter_fuelllauf_bleibt_bis_zum_live_audit_gesperrt(steuerjahr):
    eingabe = ROOT / "tests" / "elster" / steuerjahr / "mein_elster_sandbox.json"

    with pytest.raises(RuntimeError, match="nur für die lokale Sandbox validiert"):
        browserlauf(eingabe, wirklich_ausfuellen=True)


def test_alle_jahresbezogenen_golden_master_sind_unveraendert():
    assert pruefe_mehrjahres_golden_master() == []
