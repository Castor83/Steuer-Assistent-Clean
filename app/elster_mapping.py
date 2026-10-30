"""Sicheres Zwischenmapping zwischen Fachantworten und ELSTER-Verfahren."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
MAPPING_DATEI = ROOT / "wissen" / "elster" / "kernthemen_mapping_v1.json"


def lade_mapping() -> dict:
    mapping = json.loads(MAPPING_DATEI.read_text(encoding="utf-8"))
    faelle = mapping.get("faelle", [])
    ids = [str(fall.get("id", "")) for fall in faelle]
    if len(ids) != 14 or len(set(ids)) != 14:
        raise ValueError("Das ELSTER-Kernmapping muss genau 14 eindeutige Fälle enthalten.")
    schema_aktiv = mapping.get("amtliches_eric_schema", {}).get("status") == "validiert"
    for fall in faelle:
        hat_eric_feld = bool(fall.get("eric_datenart") or fall.get("eric_xml_pfad"))
        if hat_eric_feld and not schema_aktiv:
            raise ValueError(
                f"{fall['id']}: ERiC-Feld ohne validiertes amtliches Schema gesperrt."
            )
    return mapping


def erstelle_transferentwurf(antworten: dict[str, str]) -> dict:
    """Erzeugt nur einen gesperrten Entwurf, niemals eine ERiC-Versanddatei."""
    mapping = lade_mapping()
    schema = mapping["amtliches_eric_schema"]
    schema_aktiv = schema.get("status") == "validiert"
    eintraege = []
    for fall in mapping["faelle"]:
        antwort = str(antworten.get(fall["id"], ""))
        eintraege.append({
            **fall,
            "antwort_vorhanden": bool(antwort.strip()),
            "antwort_sha256": sha256(antwort.encode("utf-8")).hexdigest() if antwort else None,
            "datenwert": None,
            "datenwert_status": "nicht_aus_fachantwort_ableitbar",
            "freigabe": "gesperrt_bis_nutzerbestaetigung_und_schema_validierung",
        })
    return {
        "format": "steuer-assistent-eric-transferentwurf/v1",
        "versandfaehig": False,
        "sandbox": True,
        "amtliches_schema_validiert": schema_aktiv,
        "transferheader_entwurf": {
            "status": "gesperrt",
            "eric_version": schema.get("version"),
            "verfahren": None,
            "datenart": None,
            "vorgang": None,
            "testmerker": None,
            "hersteller_id": None,
            "datenlieferant": None,
        },
        "faelle": eintraege,
    }
