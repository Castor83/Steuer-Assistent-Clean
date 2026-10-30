from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from eric_integration import (
    OFFICIAL_MANIFEST_SCHEMA,
    erzeuge_lock_entwurf,
    inventarisiere_eric_paket,
    pruefe_eric_integration,
    validiere_offizielles_eric_paket,
    validiere_eric_lock,
)


XSD = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
 targetNamespace="urn:test:eric:2025">
  <xs:element name="Testfall" type="xs:string"/>
</xs:schema>
"""


def _testpaket(tmp_path: Path) -> Path:
    paket = tmp_path / "eric"
    paket.mkdir()
    (paket / "est_2025.xsd").write_text(XSD, encoding="utf-8")
    (paket / "ericapi.dll").write_bytes(b"synthetische-testbibliothek")
    return paket


def test_fehlendes_paket_bleibt_gesperrt(tmp_path):
    bericht = pruefe_eric_integration(tmp_path / "fehlt", steuerjahr=2025)

    assert bericht["aktivierbar"] is False
    assert any("nicht gefunden" in fehler for fehler in bericht["fehler"])


def test_paket_wird_mit_xsd_und_runtime_inventarisiert(tmp_path):
    inventar = inventarisiere_eric_paket(_testpaket(tmp_path), steuerjahr=2025)

    assert inventar["bestanden"] is True
    assert inventar["aktivierbar"] is False
    assert inventar["xsd_dateien"] == 1
    assert inventar["runtime_bibliotheken"] == 1
    assert all(eintrag["sha256"] for eintrag in inventar["dateien"])


def test_lockentwurf_aktiviert_das_paket_nicht(tmp_path):
    inventar = inventarisiere_eric_paket(_testpaket(tmp_path), steuerjahr=2025)
    lock = erzeuge_lock_entwurf(inventar)

    bericht = validiere_eric_lock(inventar, lock)

    assert lock["status"] == "entwurf"
    assert lock["manuell_geprueft"] is False
    assert bericht["aktivierbar"] is False


def test_manuell_freigegebener_unveraenderter_lock_besteht(tmp_path):
    inventar = inventarisiere_eric_paket(_testpaket(tmp_path), steuerjahr=2025)
    lock = erzeuge_lock_entwurf(inventar)
    lock.update({
        "status": "freigegeben",
        "manuell_geprueft": True,
        "paket_version": "TEST-2025",
    })

    bericht = validiere_eric_lock(inventar, lock)

    assert bericht["bestanden"] is True
    assert bericht["aktivierbar"] is True


def test_hashabweichung_sperrt_freigegebenes_paket(tmp_path):
    paket = _testpaket(tmp_path)
    inventar = inventarisiere_eric_paket(paket, steuerjahr=2025)
    lock = erzeuge_lock_entwurf(inventar)
    lock.update({
        "status": "freigegeben",
        "manuell_geprueft": True,
        "paket_version": "TEST-2025",
    })
    (paket / "ericapi.dll").write_bytes(b"nachtraeglich-veraendert")
    neues_inventar = inventarisiere_eric_paket(paket, steuerjahr=2025)

    bericht = validiere_eric_lock(neues_inventar, deepcopy(lock))

    assert bericht["aktivierbar"] is False
    assert any("Prüfsummen abweichend" in fehler for fehler in bericht["fehler"])


def test_cli_lockdatei_kann_vollstaendig_validiert_werden(tmp_path):
    paket = _testpaket(tmp_path)
    inventar = inventarisiere_eric_paket(paket, steuerjahr=2025)
    lock = erzeuge_lock_entwurf(inventar)
    lock.update({
        "status": "freigegeben",
        "manuell_geprueft": True,
        "paket_version": "TEST-2025",
    })
    lock_pfad = tmp_path / "lock.json"
    lock_pfad.write_text(json.dumps(lock), encoding="utf-8")

    bericht = pruefe_eric_integration(paket, lock_pfad, steuerjahr=2025)

    assert bericht["aktivierbar"] is True


def test_offizielles_manifest_prueft_dateien_ohne_versandfreigabe(tmp_path):
    paket = tmp_path / "eric"
    paket.mkdir()
    datei = paket / "ericapi.dll"
    datei.write_bytes(b"amtliches-testpaket")

    manifest = {
        "schema": OFFICIAL_MANIFEST_SCHEMA,
        "release": "44.2.4.0",
        "dokumentation": "44.2.4.1",
        "einkommensteuer_schemajahre": [2023, 2024, 2025],
        "originalpakete": [],
        "pruefdateien": [{
            "pfad": "ericapi.dll",
            "groesse": datei.stat().st_size,
            "sha256": hashlib.sha256(datei.read_bytes()).hexdigest(),
        }],
    }

    bericht = validiere_offizielles_eric_paket(paket, manifest)

    assert bericht["lokal_validiert"] is True
    assert bericht["versandfaehig"] is False
    assert bericht["blocker"]


def test_offizielles_manifest_sperrt_hashabweichung(tmp_path):
    paket = tmp_path / "eric"
    paket.mkdir()
    (paket / "ericapi.dll").write_bytes(b"veraendert")
    manifest = {
        "schema": OFFICIAL_MANIFEST_SCHEMA,
        "release": "44.2.4.0",
        "dokumentation": "44.2.4.1",
        "einkommensteuer_schemajahre": [2023, 2024, 2025],
        "originalpakete": [],
        "pruefdateien": [{
            "pfad": "ericapi.dll",
            "sha256": "0" * 64,
        }],
    }

    bericht = validiere_offizielles_eric_paket(paket, manifest)

    assert bericht["lokal_validiert"] is False
    assert any("Prüfsumme" in fehler for fehler in bericht["fehler"])
