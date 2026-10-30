"""Erzeugt und prüft einen strikt nicht versandfähigen ELSTER-Sandbox-Entwurf."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
from xml.etree import ElementTree as ET

from elster_mapping import erstelle_transferentwurf, lade_mapping


ROOT = Path(__file__).resolve().parent.parent
SANDBOX_NS = "urn:steuer-assistent:elster-sandbox:v1"
ET.register_namespace("sa", SANDBOX_NS)


def _element(eltern: ET.Element, name: str, wert: object = None) -> ET.Element:
    element = ET.SubElement(eltern, f"{{{SANDBOX_NS}}}{name}")
    if wert is not None:
        element.text = str(wert)
    return element


def erzeuge_sandbox_xml(antworten: dict[str, str]) -> bytes:
    """Serialisiert ausschließlich das interne Sandboxformat, niemals ERiC-XML."""
    entwurf = erstelle_transferentwurf(antworten)
    wurzel = ET.Element(f"{{{SANDBOX_NS}}}SteuerAssistentSandbox")
    _element(wurzel, "Format", entwurf["format"])
    _element(wurzel, "Versandfaehig", str(entwurf["versandfaehig"]).lower())
    _element(
        wurzel,
        "AmtlichesSchemaValidiert",
        str(entwurf["amtliches_schema_validiert"]).lower(),
    )

    header = _element(wurzel, "TransferHeaderEntwurf")
    for name, wert in entwurf["transferheader_entwurf"].items():
        _element(header, name, wert)

    mappings = _element(wurzel, "KernfallMappings")
    for fall in entwurf["faelle"]:
        eintrag = _element(mappings, "Mapping")
        for name in (
            "id",
            "thema",
            "zielverfahren",
            "formularbereich",
            "verfahrensschluessel",
            "prioritaet",
            "eric_relevanz",
            "uebertragungsart",
            "eric_datenart",
            "eric_xml_pfad",
            "antwort_sha256",
            "datenwert_status",
            "freigabe",
        ):
            _element(eintrag, name, fall.get(name))
    return ET.tostring(wurzel, encoding="utf-8", xml_declaration=True)


def validiere_sandbox_xml(xml_daten: bytes) -> dict:
    fehler = []
    try:
        wurzel = ET.fromstring(xml_daten)
    except ET.ParseError as exc:
        return {"bestanden": False, "fehler": [f"XML nicht lesbar: {exc}"]}

    ns = {"sa": SANDBOX_NS}
    if wurzel.tag != f"{{{SANDBOX_NS}}}SteuerAssistentSandbox":
        fehler.append("Falsches oder potenziell amtliches Wurzelelement.")
    if wurzel.findtext("sa:Versandfaehig", namespaces=ns) != "false":
        fehler.append("Sandbox muss ausdrücklich nicht versandfähig sein.")
    if wurzel.findtext("sa:AmtlichesSchemaValidiert", namespaces=ns) != "false":
        fehler.append("Amtliches Schema darf ohne ERiC-Paket nicht aktiv sein.")

    mappings = wurzel.findall("sa:KernfallMappings/sa:Mapping", ns)
    ids = [mapping.findtext("sa:id", namespaces=ns) for mapping in mappings]
    if len(mappings) != 14 or len(set(ids)) != 14 or None in ids:
        fehler.append("Es müssen genau 14 eindeutige Kernfall-Mappings vorliegen.")

    gesperrte_felder = (
        "sa:TransferHeaderEntwurf/sa:eric_version",
        "sa:TransferHeaderEntwurf/sa:verfahren",
        "sa:TransferHeaderEntwurf/sa:datenart",
        "sa:TransferHeaderEntwurf/sa:vorgang",
        "sa:TransferHeaderEntwurf/sa:testmerker",
        "sa:TransferHeaderEntwurf/sa:hersteller_id",
        "sa:TransferHeaderEntwurf/sa:datenlieferant",
    )
    for pfad in gesperrte_felder:
        wert = wurzel.findtext(pfad, namespaces=ns)
        if wert and wert.strip():
            fehler.append(f"Gesperrtes Headerfeld befüllt: {pfad.rsplit('/', 1)[-1]}")
    for mapping in mappings:
        for name in ("eric_datenart", "eric_xml_pfad"):
            wert = mapping.findtext(f"sa:{name}", namespaces=ns)
            if wert and wert.strip():
                fall_id = mapping.findtext("sa:id", namespaces=ns)
                fehler.append(f"{fall_id}: nicht validiertes ERiC-Feld {name} befüllt.")

    return {
        "bestanden": not fehler,
        "format": "steuer-assistent-elster-sandbox-validierung/v1",
        "versandfaehig": False,
        "amtliches_schema_validiert": False,
        "kernfall_mappings": len(mappings),
        "xml_bytes": len(xml_daten),
        "xml_sha256": sha256(xml_daten).hexdigest(),
        "fehler": fehler,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ausgabe", type=Path, help="Optionaler JSON-Prüfbericht.")
    args = parser.parse_args()
    antworten = {
        fall["id"]: f"SYNTHETISCHE TESTANTWORT {fall['id']}"
        for fall in lade_mapping()["faelle"]
    }
    bericht = validiere_sandbox_xml(erzeuge_sandbox_xml(antworten))
    if args.ausgabe:
        ausgabe = args.ausgabe if args.ausgabe.is_absolute() else ROOT / args.ausgabe
        ausgabe.parent.mkdir(parents=True, exist_ok=True)
        ausgabe.write_text(
            json.dumps(bericht, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(bericht, ensure_ascii=False, indent=2))
    return 0 if bericht["bestanden"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
