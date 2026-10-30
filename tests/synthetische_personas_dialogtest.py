"""Umfangreicher Live-Dialogtest mit ausschließlich synthetischen Personas."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
from http.cookiejar import CookieJar
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener


ROOT = Path(__file__).resolve().parents[1]
PERSONAS_DATEI = ROOT / "testDaten" / "synthetische_personas" / "personas.json"
DIALOGMATRIX_DATEI = ROOT / "testDaten" / "synthetische_personas" / "dialogtests.json"
ERGEBNISORDNER = Path(__file__).resolve().parent / "ergebnisse"
STANDARD_BASIS_URL = "http://127.0.0.1:8766"


def lade_testfaelle() -> list[dict]:
    personas = {
        persona["id"]: persona
        for persona in json.loads(PERSONAS_DATEI.read_text(encoding="utf-8"))["personas"]
    }
    matrix = json.loads(DIALOGMATRIX_DATEI.read_text(encoding="utf-8"))
    faelle: list[dict] = []
    for dialog in matrix["personas"]:
        persona = personas[dialog["persona_id"]]
        for schritt in dialog["dialoge"]:
            faelle.append(
                {
                    **schritt,
                    "persona_id": persona["id"],
                    "persona_name": persona["name"],
                    "steuerjahr": persona["steuerjahr"],
                    "gesicherter_kontext": dialog["gesicherter_kontext"],
                }
            )
    return faelle


def baue_kontextnachricht(fall: dict) -> str:
    return (
        "Dies ist ein ausschließlich synthetischer Testfall – nicht einreichen. "
        "Nutze im folgenden Dialog nur die ausdrücklich genannten Angaben, trenne "
        "bestätigte von offenen Werten und erfinde keine fehlenden Tatsachen.\n\n"
        f"Testkontext: {fall['gesicherter_kontext']}"
    )


def mechanische_pruefung(
    *, antwort: str, quellen: list[dict], quellen_erforderlich: bool
) -> list[str]:
    gruende: list[str] = []
    if not antwort.strip():
        gruende.append("Antwort ist leer")
    if quellen_erforderlich and not quellen:
        gruende.append("Erforderliche Quelle fehlt")
    return gruende


def vorpruefungsstatus(gruende: list[str]) -> str:
    """Bewertet nur die technische Auswertbarkeit, nie die fachliche Richtigkeit."""
    return "TECHNISCH_OK" if not gruende else "PRUEFEN"


class Sitzung:
    def __init__(self, basis_url: str) -> None:
        self.basis_url = basis_url.rstrip("/")
        self.opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def anfrage(self, pfad: str, payload: dict | None = None) -> dict:
        daten = None
        methode = "GET"
        headers: dict[str, str] = {}
        if payload is not None:
            daten = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            methode = "POST"
            headers["Content-Type"] = "application/json; charset=utf-8"
        anfrage = Request(
            self.basis_url + pfad,
            data=daten,
            headers=headers,
            method=methode,
        )
        with self.opener.open(anfrage, timeout=240) as antwort:
            return json.load(antwort)

    def nutzer_waehlen(self, name: str, *, persona_id: str, steuerjahr: str) -> dict:
        erwartete_id = f"synthetisch-{persona_id}"
        daten = self.anfrage("/api/nutzer")
        nutzer = next(
            (eintrag for eintrag in daten.get("nutzer", []) if eintrag.get("name") == name),
            None,
        )
        if nutzer is None:
            raise ValueError(f"Synthetisches Nutzerprofil fehlt: {name}")
        if str(nutzer.get("id", "")) != erwartete_id:
            raise RuntimeError(
                f"Die Nutzerliste ordnet {name} der unerwarteten ID {nutzer.get('id')!r} zu."
            )

        gewechselt = self.anfrage(
            "/api/nutzer/wechseln", {"nutzer_id": erwartete_id}
        ).get("nutzer", {})
        if (
            str(gewechselt.get("id", "")) != erwartete_id
            or str(gewechselt.get("name", "")) != name
        ):
            raise RuntimeError("Die Antwort auf den Profilwechsel bestätigt nicht die erwartete Person.")

        ruecklese = self.anfrage("/api/nutzer")
        aktiv = ruecklese.get("aktiv") or {}
        if (
            str(aktiv.get("id", "")) != erwartete_id
            or str(aktiv.get("name", "")) != name
        ):
            raise RuntimeError("Das Cookie bindet die Sitzung an das falsche Nutzerprofil.")

        profil = self.anfrage("/api/steuerprofil")
        if str(profil.get("steuerjahr_vorschlag", "")) != steuerjahr:
            raise RuntimeError("Das geladene Steuerprofil gehört nicht zum erwarteten Steuerjahr.")
        if str(profil.get("steuerjahr_status", "")) != "Synthetischer Testfall":
            raise RuntimeError("Das geladene Profil ist nicht als synthetischer Testfall markiert.")

        eingangsordner = str(self.anfrage("/api/eingangsordner").get("pfad", ""))
        pfadteile = [teil.casefold() for teil in re.split(r"[\\/]+", eingangsordner) if teil]
        if erwartete_id.casefold() not in pfadteile or not pfadteile or pfadteile[-1] != "eingang":
            raise RuntimeError("Der aktive Eingangsordner gehört nicht zum erwarteten Testprofil.")

        return {
            "persona_id": persona_id,
            "nutzer_id": erwartete_id,
            "nutzer_name": name,
            "cookie_aktiv_bestaetigt": True,
            "profil_steuerjahr": steuerjahr,
            "profil_steuerjahr_bestaetigt": True,
            "eingangsordner": eingangsordner,
            "eingangsordner_bestaetigt": True,
        }

    def frage(self, frage: str, verlauf: list[dict], steuerjahr: str) -> dict:
        return self.anfrage(
            "/api/frage",
            {"frage": frage, "verlauf": verlauf, "steuerjahr": steuerjahr},
        )


def fuehre_dialogtest_aus(
    *, basis_url: str, modus: str, nur_personas: set[str] | None = None
) -> dict:
    if modus not in {"kontext", "profil", "fallkontext"}:
        raise ValueError(f"Unbekannter Dialogtest-Modus: {modus}")
    faelle = lade_testfaelle()
    if modus == "profil":
        faelle = [fall for fall in faelle if fall["originalfrage"]]
    if nur_personas:
        faelle = [fall for fall in faelle if fall["persona_id"] in nur_personas]
    if not faelle:
        raise ValueError("Keine Dialogschritte für die gewählte Personaauswahl gefunden.")

    gruppiert: dict[str, list[dict]] = defaultdict(list)
    for fall in faelle:
        gruppiert[fall["persona_id"]].append(fall)

    ergebnisse: list[dict] = []
    kontextantworten: list[dict] = []
    profilbindungen: list[dict] = []
    persona_fehler: list[dict] = []
    for persona_id, schritte in gruppiert.items():
        erster = schritte[0]
        sitzung = Sitzung(basis_url)
        verlauf: list[dict] = []
        try:
            status = sitzung.anfrage("/api/status")
            if not status.get("bereit"):
                raise RuntimeError("Die Web-Testinstanz meldet sich nicht als bereit.")
            profilbindung = sitzung.nutzer_waehlen(
                erster["persona_name"],
                persona_id=persona_id,
                steuerjahr=erster["steuerjahr"],
            )
            profilbindungen.append(profilbindung)

            if modus == "kontext":
                kontextfrage = baue_kontextnachricht(erster)
                start = time.perf_counter()
                daten = sitzung.frage(kontextfrage, verlauf, erster["steuerjahr"])
                dauer = round(time.perf_counter() - start, 3)
                kontextantwort = str(daten.get("antwort", ""))
                kontextantworten.append(
                    {
                        "persona_id": persona_id,
                        "frage": kontextfrage,
                        "antwort": kontextantwort,
                        "quellen": daten.get("quellen", []),
                        "dauer_sekunden": dauer,
                    }
                )
                verlauf.extend(
                    [
                        {"rolle": "nutzer", "text": kontextfrage},
                        {"rolle": "assistent", "text": kontextantwort},
                    ]
                )
        except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError, OSError) as fehler:
            persona_fehler.append({"persona_id": persona_id, "fehler": str(fehler)})
            print(f"SETUP_FEHLER [{persona_id}] {fehler}", flush=True)
            continue

        for schritt in schritte:
            start = time.perf_counter()
            try:
                daten = sitzung.frage(schritt["frage"], verlauf, schritt["steuerjahr"])
                antwort = str(daten.get("antwort", ""))
                quellen = list(daten.get("quellen", []))
                gruende = mechanische_pruefung(
                    antwort=antwort,
                    quellen=quellen,
                    quellen_erforderlich=schritt["quellen_erforderlich"],
                )
                technischer_fehler = ""
            except (HTTPError, URLError, TimeoutError, ValueError, OSError) as fehler:
                antwort, quellen = "", []
                gruende = [f"Technischer Fehler: {fehler}"]
                technischer_fehler = str(fehler)
            dauer = round(time.perf_counter() - start, 3)
            ergebnis = {
                **schritt,
                "antwort": antwort,
                "quellen": quellen,
                "dauer_sekunden": dauer,
                "vorpruefung": vorpruefungsstatus(gruende),
                "vorpruefung_gruende": gruende,
                "technischer_fehler": technischer_fehler,
            }
            ergebnisse.append(ergebnis)
            print(
                f"{ergebnis['vorpruefung']} [{persona_id} {schritt['id']}] "
                f"{dauer:.1f}s",
                flush=True,
            )
            if gruende:
                print("  " + "; ".join(gruende), flush=True)
            verlauf.extend(
                [
                    {"rolle": "nutzer", "text": schritt["frage"]},
                    {"rolle": "assistent", "text": antwort},
                ]
            )

    zaehler = Counter(ergebnis["vorpruefung"] for ergebnis in ergebnisse)
    return {
        "erstellt_am": datetime.now().astimezone().isoformat(timespec="seconds"),
        "kennzeichnung": "AUSSCHLIESSLICH SYNTHETISCHE TESTDATEN – NICHT EINREICHEN",
        "basis_url": basis_url,
        "modus": modus,
        "anzahl_personas": len(gruppiert),
        "anzahl_dialogschritte": len(ergebnisse),
        "persona_fehler": persona_fehler,
        "vorpruefung": dict(sorted(zaehler.items())),
        "hinweis": (
            "TECHNISCH_OK bedeutet nur: Antwort und gegebenenfalls eine Quelle sind vorhanden. "
            "Die fachlich-semantische Bewertung erfolgt getrennt anhand der Dialogmatrix."
        ),
        "profilbindungen": profilbindungen,
        "kontextantworten": kontextantworten,
        "ergebnisse": ergebnisse,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--basis-url", default=STANDARD_BASIS_URL)
    parser.add_argument(
        "--modus",
        choices=("fallkontext", "kontext", "profil"),
        default="fallkontext",
    )
    parser.add_argument("--nur-persona", action="append", default=[])
    parser.add_argument("--ausgabe", type=Path)
    args = parser.parse_args()

    try:
        bericht = fuehre_dialogtest_aus(
            basis_url=args.basis_url,
            modus=args.modus,
            nur_personas=set(args.nur_persona) or None,
        )
    except (HTTPError, URLError, TimeoutError, ValueError, RuntimeError, OSError) as fehler:
        print(f"NICHT GETESTET: {fehler}")
        return 2

    zeit = datetime.now().strftime("%Y%m%d_%H%M%S")
    ausgabe = args.ausgabe or ERGEBNISORDNER / f"synthetische_personas_dialogtest_{args.modus}_{zeit}.json"
    ausgabe.parent.mkdir(parents=True, exist_ok=True)
    ausgabe.write_text(json.dumps(bericht, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"ERGEBNIS {ausgabe}")
    print("TECHNISCHE_ZUSAMMENFASSUNG " + json.dumps(bericht["vorpruefung"], ensure_ascii=False))
    technisch_vollstaendig = (
        bool(bericht["ergebnisse"])
        and not bericht["persona_fehler"]
        and set(bericht["vorpruefung"]) <= {"TECHNISCH_OK"}
    )
    return 0 if technisch_vollstaendig else 1


if __name__ == "__main__":
    raise SystemExit(main())
