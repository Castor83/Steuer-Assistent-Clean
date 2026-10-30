"""Feste, reproduzierbare Freigabeschranken fuer die lokale Modelllaufzeit."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PerformanceGrenzen:
    ttft_sekunden: float = 30.0
    token_pro_sekunde: float = 8.0
    vram_spitze_mib: int = 15_700
    max_neuladungen: int = 3
    max_oom_wiederholungen: int = 0


STANDARD_GRENZEN = PerformanceGrenzen()


def pruefe_performance(messung: dict, grenzen: PerformanceGrenzen = STANDARD_GRENZEN) -> dict[str, bool]:
    """Prueft die vier verpflichtenden Laufzeitmetriken einzeln."""
    return {
        "ttft": float(messung["ttft_sekunden"]) <= grenzen.ttft_sekunden,
        "tokenrate": float(messung["token_pro_sekunde"]) >= grenzen.token_pro_sekunde,
        "vram_spitze": int(messung["vram_spitze_mib"]) <= grenzen.vram_spitze_mib,
        "neuladungen_oom": (
            int(messung["neuladungen"]) <= grenzen.max_neuladungen
            and int(messung["oom_wiederholungen"]) <= grenzen.max_oom_wiederholungen
        ),
    }


def performance_freigegeben(messung: dict, grenzen: PerformanceGrenzen = STANDARD_GRENZEN) -> bool:
    return all(pruefe_performance(messung, grenzen).values())
