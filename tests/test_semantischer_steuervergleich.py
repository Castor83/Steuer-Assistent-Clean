import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from semantischer_steuervergleich import (
    KRITISCHE_REGELN,
    _faelle_laden,
    _kosinus,
    _kritische_fakten_pruefen,
)


def test_semantikfaelle_sind_eindeutig_und_decken_kernthemen_ab():
    faelle, pruefsummen = _faelle_laden()
    assert len(faelle) == 14
    assert len({fall["id"] for fall in faelle}) == len(faelle)
    assert {fall["id"] for fall in faelle} == set(KRITISCHE_REGELN)
    themen = " ".join(fall["thema"] for fall in faelle).casefold()
    for thema in ("lohnsteuer", "bayerische grundsteuer", "insolvenzgeld", "erbschaftsteuer"):
        assert thema in themen
    assert all(len(wert) == 64 for wert in pruefsummen.values())


def test_kosinus_erkennt_identische_und_orthogonale_vektoren():
    assert _kosinus([1.0, 2.0], [1.0, 2.0]) == pytest.approx(1.0)
    assert _kosinus([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_kritische_fakten_erkennen_zahlenfehler_trotz_semantischer_naehe():
    falsch = _kritische_fakten_pruefen(
        "neuer_testkatalog_100.json:73", "Die lineare AfA beträgt 2 Prozent."
    )
    richtig = _kritische_fakten_pruefen(
        "neuer_testkatalog_100.json:73", "Die lineare AfA beträgt 3 Prozent."
    )
    assert not falsch["bestanden"]
    assert richtig["bestanden"]
