from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from elster_mapping import lade_mapping
from elster_verfahrensrouting import erstelle_verfahrensplan, validiere_verfahrensrouting


def test_alle_14_kernfaelle_haben_ein_eindeutiges_verfahrensrouting():
    bericht = validiere_verfahrensrouting()

    assert bericht["bestanden"] is True, bericht["fehler"]
    assert bericht["faelle"] == 14


def test_priorisierte_verfahrensgruppen_decken_alle_faelle_genau_einmal_ab():
    plan = erstelle_verfahrensplan()
    ids = [fall["id"] for gruppe in plan["gruppen"] for fall in gruppe["faelle"]]

    assert len(ids) == 14
    assert set(Counter(ids).values()) == {1}
    assert [gruppe["reihenfolge"] for gruppe in plan["gruppen"]] == sorted(
        gruppe["reihenfolge"] for gruppe in plan["gruppen"]
    )
    assert all(gruppe["versandfaehig"] is False for gruppe in plan["gruppen"])


def test_est_2025_strecke_hat_acht_faelle_und_erster_abschnitt_sieben():
    plan = erstelle_verfahrensplan()

    assert plan["est_2025_kernfaelle"] == 8
    assert plan["naechste_freigabestufe"]["faelle"] == 7
    assert plan["naechste_freigabestufe"]["status"].startswith("gesperrt")


def test_insolvenzgeldantrag_wird_nicht_zu_elster_geroutet():
    mapping = lade_mapping()
    fall = next(fall for fall in mapping["faelle"] if fall["id"] == "P27")

    assert fall["verfahrensschluessel"] == "insolvenzgeld_bundesagentur"
    assert fall["eric_relevanz"] == "kein_elster_verfahren"


def test_bayern_grundsteuer_und_rechtsbehelf_bleiben_von_est_getrennt():
    mapping = lade_mapping()
    grundsteuer = [fall for fall in mapping["faelle"] if "grundsteuer" in fall["verfahrensschluessel"]]

    assert len(grundsteuer) == 2
    assert all(not fall["verfahrensschluessel"].startswith("est_") for fall in grundsteuer)
    assert all(fall["prioritaet"] == 5 for fall in grundsteuer)
