from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from golden_master import pruefe_golden_master


def test_golden_master_manifest_und_quellenbestand_sind_unveraendert():
    bericht = pruefe_golden_master(require_reports=False)

    assert bericht["bestanden"] is True, bericht["fehler"]
    assert bericht["quellenkarten"] == 187
    assert bericht["regelchunks"] == 853
