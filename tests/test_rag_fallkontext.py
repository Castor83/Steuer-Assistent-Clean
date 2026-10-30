"""Tests für den bei jedem Modellturn angehefteten Fallkontext."""

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import rag_assistent as rag  # noqa: E402


FALLKONTEXT = {
    "version": 1,
    "steuerjahr": "2025",
    "nutzer_name": "Alma",
    "profil": {"angestellter": True},
    "werte": [
        {
            "id": "alma-lohn",
            "art": "bruttoarbeitslohn",
            "bezeichnung": "Bruttoarbeitslohn",
            "betrag_eur": "42000.00",
            "steuerjahr": "2025",
            "status": "bestätigt",
            "wertart": "jahressumme",
        }
    ],
    "dokumente": [],
}


def test_beantworte_reicht_fallkontext_durch_alle_fassaden(monkeypatch) -> None:
    empfangen = {}

    def legacy(frage, **kwargs):
        empfangen.update(kwargs)
        return "Antwort [1].", []

    monkeypatch.setattr(rag, "_beantworte_mit_legacykern", legacy)

    rag.beantworte("Frage", steuerjahr=2025, fallkontext=FALLKONTEXT)

    assert empfangen["fallkontext"] is FALLKONTEXT


def test_strikter_prompt_heftet_fallkontext_an_und_belegt_seine_zahlen(
    monkeypatch,
) -> None:
    prompts = []

    def chat(_modell, nachrichten, **_kwargs):
        prompts.append(nachrichten[0]["content"])
        return {
            "message": {
                "content": "Die hinterlegten 42.000,00 Euro sind Arbeitslohn [1]."
            }
        }

    monkeypatch.setattr(rag.MODELL_RESSOURCEN, "chat", chat)
    quelle = SimpleNamespace(
        payload={
            "quelle": "Einkommensteuergesetz",
            "paragraph": "§ 19 EStG",
            "steuerjahr": "2025",
            "text": "Zu den Einkünften gehören Gehälter und Löhne.",
        }
    )

    antwort = rag._generiere_strikt_quellenbasiert(
        "Wie wird mein Arbeitslohn behandelt?", [quelle], 2025, fallkontext=FALLKONTEXT
    )

    assert antwort is not None and "42.000,00 Euro" in antwort
    assert "Lokale Falldaten (keine Rechtsquelle)" in prompts[0]
    assert prompts[0].index("Lokale Falldaten") < prompts[0].index(
        "Beantworte jetzt ausschließlich diese Frage"
    )
    assert rag._antwortzahlen_belegt(
        "Wie wird mein Arbeitslohn behandelt?",
        "42.000,00 Euro Arbeitslohn [1].",
        [quelle],
        fallkontext=FALLKONTEXT,
    )
    assert not rag._antwortzahlen_belegt(
        "Wie wird mein Arbeitslohn behandelt?",
        "43.000,00 Euro Arbeitslohn [1].",
        [quelle],
        fallkontext=FALLKONTEXT,
    )
