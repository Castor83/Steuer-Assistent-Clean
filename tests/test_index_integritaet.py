from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from wissen_import_quellen import pruefe_index_integritaet


class FakeClient:
    def __init__(self, punkte):
        self.punkte = punkte

    def scroll(self, **_kwargs):
        return self.punkte, None


def _punkt(punkt_id, payload):
    return SimpleNamespace(id=punkt_id, payload=payload)


def _payload(datei, chunk):
    return {
        "quellenart": "quellenkarte",
        "datei": datei,
        "chunk": chunk,
        "chunk_anzahl": 2,
        "text": f"Regel {chunk}",
        "paragraph": "§ 1 TestG",
        "suchjahre": [2025, 2026],
        "bundesland": "Bayern",
        "fristtyp": "keine_frist",
    }


def test_indexparitaet_besteht_bei_exaktem_sollzustand():
    erwartet = {11: _payload("a.json", 0), 12: _payload("a.json", 1)}
    client = FakeClient([_punkt(k, deepcopy(v)) for k, v in erwartet.items()])

    bericht = pruefe_index_integritaet(client, erwartet)

    assert bericht["bestanden"] is True
    assert bericht["erwartete_chunks"] == 2
    assert bericht["vorhandene_quellenpunkte"] == 2


def test_indexparitaet_findet_fehlende_und_unerwartete_punkte():
    erwartet = {11: _payload("a.json", 0), 12: _payload("a.json", 1)}
    client = FakeClient([_punkt(11, deepcopy(erwartet[11])), _punkt(99, _payload("b.json", 0))])

    bericht = pruefe_index_integritaet(client, erwartet)

    assert bericht["bestanden"] is False
    assert bericht["fehlende_punkt_ids"] == [12]
    assert bericht["unerwartete_punkt_ids"] == [99]


def test_indexparitaet_findet_payloadabweichung():
    erwartet = {11: _payload("a.json", 0)}
    vorhanden = deepcopy(erwartet[11])
    vorhanden["bundesland"] = "Berlin"

    bericht = pruefe_index_integritaet(FakeClient([_punkt(11, vorhanden)]), erwartet)

    assert bericht["bestanden"] is False
    assert bericht["abweichende_payloads"][0]["abweichende_felder"] == ["bundesland"]
