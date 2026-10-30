from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from performance_abnahme import PerformanceGrenzen, performance_freigegeben, pruefe_performance


GRENZEN = PerformanceGrenzen()


def test_vier_feste_performance_schwellen_sind_aktiv():
    assert pruefe_performance({
        "ttft_sekunden": GRENZEN.ttft_sekunden,
        "token_pro_sekunde": GRENZEN.token_pro_sekunde,
        "vram_spitze_mib": GRENZEN.vram_spitze_mib,
        "neuladungen": GRENZEN.max_neuladungen,
        "oom_wiederholungen": GRENZEN.max_oom_wiederholungen,
    }) == {"ttft": True, "tokenrate": True, "vram_spitze": True, "neuladungen_oom": True}


def test_jede_einzelne_ueberschreitung_sperrt_die_freigabe():
    basis = {
        "ttft_sekunden": 1, "token_pro_sekunde": 100,
        "vram_spitze_mib": 100, "neuladungen": 0, "oom_wiederholungen": 0,
    }
    felder = {
        "ttft_sekunden": GRENZEN.ttft_sekunden + .01,
        "token_pro_sekunde": GRENZEN.token_pro_sekunde - .01,
        "vram_spitze_mib": GRENZEN.vram_spitze_mib + 1,
        "neuladungen": GRENZEN.max_neuladungen + 1,
        "oom_wiederholungen": GRENZEN.max_oom_wiederholungen + 1,
    }
    for feld, wert in felder.items():
        assert not performance_freigegeben({**basis, feld: wert})
