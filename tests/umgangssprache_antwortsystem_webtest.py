"""End-to-End-Audit des Antwortsystems mit zurückgehaltenen Alltagsfragen.

Die Korpora enthalten bewusst nur die umgangssprachliche Eingabe und ihre
kanonische Bedeutung, aber keine vorformulierte Fachantwort. Deshalb prüft
dieser Audit robuste Systemeigenschaften statt eines exakten Antwortwortlauts.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError

from praxisdialog_webtest import STANDARD_BASIS_URL, STANDARD_NUTZER, Sitzung, normalisiere


PROJEKT = Path(__file__).resolve().parents[1]
KORPUSORDNER = PROJEKT / "testDaten" / "umgangssprache_steuer_training"
STANDARD_KORPORA = (
    KORPUSORDNER / "kanonisierung_test.jsonl",
    KORPUSORDNER / "praxis_kanonisierung_test.jsonl",
)
ERGEBNISORDNER = Path(__file__).resolve().parent / "ergebnisse"

HARTE_FEHLERTEXTE = (
    "das kann ich anhand der gefundenen amtlichen quellen nicht sicher beantworten",
    "deshalb gebe ich keine steuerliche behauptung aus",
    "das kann ich anhand der vorhandenen informationen nicht sicher beantworten",
    "bei der verarbeitung ist ein fehler aufgetreten",
    "interner serverfehler",
)


def lade_faelle(pfade: tuple[Path, ...] = STANDARD_KORPORA) -> list[dict]:
    faelle: list[dict] = []
    for pfad in pfade:
        with pfad.open(encoding="utf-8") as datei:
            for zeile in datei:
                datensatz = json.loads(zeile)
                nachrichten = datensatz["messages"]
                nutzerfrage = next(m["content"] for m in nachrichten if m["role"] == "user")
                kanonisch = next(m["content"] for m in nachrichten if m["role"] == "assistant")
                faelle.append(
                    {
                        "id": datensatz["id"],
                        "basis_id": datensatz.get("basis_id"),
                        "korpus": pfad.name,
                        "thema": datensatz.get("thema", ""),
                        "frage": nutzerfrage,
                        "kanonisch": kanonisch,
                        "stil": datensatz.get("metadaten", {}).get("stil"),
                        "erwartete_quelle": datensatz.get("metadaten", {}).get("quelle_url"),
                    }
                )
    return faelle


def repraesentative_faelle(faelle: list[dict]) -> list[dict]:
    """Wählt je Fachbasis eine Variante, rotiert dabei durch alle Sprachstile."""
    gruppen: dict[str, list[dict]] = {}
    praxis: list[dict] = []
    for fall in faelle:
        if fall["basis_id"]:
            gruppen.setdefault(fall["basis_id"], []).append(fall)
        else:
            praxis.append(fall)
    auswahl = []
    for gruppenindex, basis_id in enumerate(sorted(gruppen)):
        varianten = gruppen[basis_id]
        auswahl.append(varianten[gruppenindex % len(varianten)])
    return auswahl + praxis


def bewerte_antwort(antwort: str, quellen: list[dict], kanonisch: str) -> tuple[str, list[str]]:
    """Klassifiziert harte Antwortfehler und separat prüfenswerte Antworten."""
    norm = normalisiere(antwort)
    gruende: list[str] = []
    hart = False

    if not norm:
        gruende.append("Antwort ist leer")
        hart = True
    treffer = [text for text in HARTE_FEHLERTEXTE if text in norm]
    if treffer:
        gruende.append("Pauschale Verweigerung oder Systemfehler")
        hart = True

    norm_kanonisch = normalisiere(kanonisch).rstrip("?.!")
    norm_antwort = norm.rstrip("?.!")
    if norm_antwort and (norm_antwort == norm_kanonisch or (
        len(norm_antwort) <= len(norm_kanonisch) + 20 and norm_kanonisch in norm_antwort
    )):
        gruende.append("Frage nur kanonisiert, nicht beantwortet")
        hart = True

    if hart:
        return "FEHLER", gruende
    if not quellen:
        return "PRUEFEN", ["Keine amtliche Quelle an der Antwort"]
    return "BESTANDEN", []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--basis-url", default=STANDARD_BASIS_URL)
    parser.add_argument("--nutzer", default=STANDARD_NUTZER)
    parser.add_argument("--steuerjahr", default="2023")
    parser.add_argument(
        "--vollstaendig",
        action="store_true",
        help="Alle 172 Varianten statt der repräsentativen Hauptstichprobe prüfen.",
    )
    parser.add_argument("--limit", type=int)
    parser.add_argument("--ausgabe", type=Path)
    args = parser.parse_args()

    faelle = lade_faelle()
    if not args.vollstaendig:
        faelle = repraesentative_faelle(faelle)
    if args.limit is not None:
        faelle = faelle[: args.limit]

    sitzung = Sitzung(args.basis_url)
    try:
        serverstatus = sitzung.anfrage("/api/status")
        if not serverstatus.get("bereit"):
            raise RuntimeError("Server meldet sich nicht als bereit.")
        nutzer = sitzung.nutzer_waehlen(args.nutzer)
    except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError) as fehler:
        print(f"NICHT GETESTET: {fehler}")
        return 2

    print(
        f"Umgangssprache-Audit: {len(faelle)} Fälle | Nutzer: {nutzer['name']} | Steuerjahr: {args.steuerjahr}",
        flush=True,
    )
    ergebnisse: list[dict] = []
    for nummer, fall in enumerate(faelle, 1):
        try:
            daten = sitzung.frage(fall["frage"], [], args.steuerjahr)
            antwort = str(daten.get("antwort", ""))
            quellen = daten.get("quellen", [])
            status, gruende = bewerte_antwort(antwort, quellen, fall["kanonisch"])
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as fehler:
            antwort, quellen = "", []
            status, gruende = "TECHNISCHER_FEHLER", [str(fehler)]

        ergebnisse.append({**fall, "status": status, "gruende": gruende, "antwort": antwort, "quellen": quellen})
        print(f"{nummer:03}/{len(faelle):03} {status:18} {fall['id']}", flush=True)

    zaehler = {
        status: sum(e["status"] == status for e in ergebnisse)
        for status in ("BESTANDEN", "PRUEFEN", "FEHLER", "TECHNISCHER_FEHLER")
    }
    payload = {
        "erstellt_am": datetime.now().astimezone().isoformat(timespec="seconds"),
        "basis_url": args.basis_url,
        "nutzer": nutzer["name"],
        "steuerjahr": args.steuerjahr,
        "anzahl": len(ergebnisse),
        "zaehler": zaehler,
        "bewertung": {
            "BESTANDEN": "inhaltliche Antwort mit mindestens einer Quelle",
            "PRUEFEN": "inhaltliche Antwort ohne Quelle; manuelle Prüfung erforderlich",
            "FEHLER": "leer, pauschal verweigert oder nur umformuliert",
        },
        "ergebnisse": ergebnisse,
    }
    zeit = datetime.now().strftime("%Y%m%d_%H%M%S")
    ausgabe = args.ausgabe or ERGEBNISORDNER / f"umgangssprache_antwortsystem_{zeit}.json"
    ausgabe.parent.mkdir(parents=True, exist_ok=True)
    ausgabe.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"ERGEBNIS {ausgabe}")
    print("ZUSAMMENFASSUNG " + " | ".join(f"{k}: {v}" for k, v in zaehler.items()))
    return 1 if zaehler["FEHLER"] or zaehler["TECHNISCHER_FEHLER"] else 0


if __name__ == "__main__":
    sys.exit(main())
