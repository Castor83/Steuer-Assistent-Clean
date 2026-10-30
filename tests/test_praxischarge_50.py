import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from praxischarge_50 import pruefe_unabhaengigkeit


def test_praxischarge_ist_fest_ausgewogen_und_unabhaengig():
    faelle = json.loads(
        (ROOT / "tests" / "praxischarge_50.json").read_text(encoding="utf-8")
    )
    assert len(faelle) == 50
    assert sum(fall["erwartet"] == "ANTWORT" for fall in faelle) == 20
    assert sum(fall["erwartet"] == "RUECKFRAGE" for fall in faelle) == 20
    assert sum(fall["erwartet"] == "ABLEHNUNG" for fall in faelle) == 10
    assert not pruefe_unabhaengigkeit(faelle)
