from xml.etree import ElementTree as ET
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from elster_mapping import erstelle_transferentwurf, lade_mapping
from elster_sandbox import SANDBOX_NS, erzeuge_sandbox_xml, validiere_sandbox_xml


def test_kernmapping_hat_genau_14_gesperrte_faelle():
    mapping = lade_mapping()

    assert len(mapping["faelle"]) == 14
    assert len({fall["id"] for fall in mapping["faelle"]}) == 14
    assert mapping["amtliches_eric_schema"]["status"] == "nicht_eingebunden"
    assert all(fall["eric_datenart"] is None for fall in mapping["faelle"])
    assert all(fall["eric_xml_pfad"] is None for fall in mapping["faelle"])


def test_transferentwurf_bleibt_nicht_versandfaehig():
    antworten = {fall["id"]: "synthetisch" for fall in lade_mapping()["faelle"]}
    entwurf = erstelle_transferentwurf(antworten)

    assert entwurf["versandfaehig"] is False
    assert entwurf["sandbox"] is True
    assert entwurf["amtliches_schema_validiert"] is False
    assert len(entwurf["faelle"]) == 14
    assert all(fall["datenwert"] is None for fall in entwurf["faelle"])
    assert all(fall["antwort_sha256"] for fall in entwurf["faelle"])


def test_sandbox_xml_ist_eigenes_format_und_besteht_validierung():
    antworten = {fall["id"]: "synthetisch" for fall in lade_mapping()["faelle"]}
    xml_daten = erzeuge_sandbox_xml(antworten)
    wurzel = ET.fromstring(xml_daten)
    bericht = validiere_sandbox_xml(xml_daten)

    assert wurzel.tag == f"{{{SANDBOX_NS}}}SteuerAssistentSandbox"
    assert bericht["bestanden"] is True
    assert bericht["kernfall_mappings"] == 14


def test_sandbox_validator_blockiert_versandfreigabe():
    antworten = {fall["id"]: "synthetisch" for fall in lade_mapping()["faelle"]}
    xml_daten = erzeuge_sandbox_xml(antworten).replace(
        b"<sa:Versandfaehig>false</sa:Versandfaehig>",
        b"<sa:Versandfaehig>true</sa:Versandfaehig>",
    )

    bericht = validiere_sandbox_xml(xml_daten)

    assert bericht["bestanden"] is False
    assert any("nicht versandfähig" in fehler for fehler in bericht["fehler"])
