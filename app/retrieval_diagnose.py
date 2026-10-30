"""Einheitliche, inspizierbare Treffer für alle Retrieval-Wege."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RetrievalTreffer:
    payload: dict
    score: float
    trefferart: str
    rohscore: float
    nachsortierung: float | None = None
    ablehnungsgrund: str | None = None


def als_treffer(ergebnis: Any, trefferart: str) -> RetrievalTreffer:
    if isinstance(ergebnis, RetrievalTreffer):
        return ergebnis
    score = float(getattr(ergebnis, "score", 0.0) or 0.0)
    return RetrievalTreffer(
        payload=dict(getattr(ergebnis, "payload", {}) or {}),
        score=score,
        trefferart=trefferart,
        rohscore=score,
    )


def vereinige_treffer(*gruppen: list, limit: int | None = None) -> list[RetrievalTreffer]:
    """Führt Treffer zusammen und behält die stärkste Fundart je Quelle."""
    eindeutig: dict[tuple, RetrievalTreffer] = {}
    for gruppe in gruppen:
        for ergebnis in gruppe:
            treffer = ergebnis if isinstance(ergebnis, RetrievalTreffer) else als_treffer(ergebnis, "unbekannt")
            schluessel = (
                treffer.payload.get("url"),
                treffer.payload.get("paragraph"),
                treffer.payload.get("text"),
            )
            vorhanden = eindeutig.get(schluessel)
            if vorhanden is None:
                eindeutig[schluessel] = treffer
                continue
            fundarten = {vorhanden.trefferart, treffer.trefferart}
            staerker = treffer if treffer.score > vorhanden.score else vorhanden
            if len(fundarten) > 1:
                staerker.trefferart = "lexikal+semantisch"
            staerker.rohscore = max(vorhanden.rohscore, treffer.rohscore)
            eindeutig[schluessel] = staerker
    ergebnisse = list(eindeutig.values())
    ergebnisse.sort(key=lambda eintrag: eintrag.score, reverse=True)
    return ergebnisse if limit is None else ergebnisse[:limit]
