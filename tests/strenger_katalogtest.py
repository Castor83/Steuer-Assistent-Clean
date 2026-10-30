"""Strenger, nachvollziehbarer Fachtest für die Steuer-Fragenkataloge.

Der Test bewertet keine freie Formulierung Wort für Wort. Er prüft stattdessen
die maschinell zuverlässig erkennbaren Kernaussagen der hinterlegten
Sollantwort: Ja/Nein, Multiple Choice, Zahlen mit Einheit und Fachbegriffe.
Verdächtige Antworten werden zur fachlichen Prüfung markiert, nicht vorschnell
als definitiv falsch bezeichnet.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from datetime import datetime
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener


TESTORDNER = Path(__file__).resolve().parent
ENDPUNKT = "http://127.0.0.1:8765/api/frage"
UNSICHER = "Das kann ich anhand der vorhandenen Informationen nicht sicher beantworten"
HTTP_OPENER = build_opener(HTTPCookieProcessor(CookieJar()))
KATALOGE = (
    "gesamtkatalog_105.json",
    "neuer_testkatalog_100.json",
    "neuer_testkatalog_150.json",
    "neuer_testkatalog_151_300.json",
    "neuer_testkatalog_lohnsteuer_100.json",
    "neuer_testkatalog_steuerwissen_120.json",
)

STOPPWOERTER = {
    "aber", "alle", "allem", "allen", "aller", "alles", "auch", "auf", "aus",
    "bei", "beim", "berechnet", "berechnung", "beträgt", "bzw", "dabei", "dadurch",
    "dann", "dass", "dem", "den", "der", "des", "die", "dies", "diese", "diesem",
    "diesen", "dieser", "dieses", "durch", "ein", "eine", "einem", "einen", "einer",
    "eines", "entspricht", "erst", "für", "gilt", "haben", "hat", "hier", "ist",
    "jahr", "jahres", "kann", "können", "liegt", "mal", "mit", "muss", "nach",
    "nicht", "noch", "oder", "pro", "sich", "sind", "sowie", "über", "und", "unter",
    "vom", "von", "wenn", "werden", "wird", "wobei", "zum", "zur", "zwischen",
}

ZAHL_MIT_EINHEIT = re.compile(
    r"(?<![\w§])(?P<wert>\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:,\d+)?)\s*"
    r"(?P<einheit>euro|€|prozent|%|cent|tage?n?|monate?n?|jahre?n?|km|kilometer|"
    r"kwh|kw|stunden?|wochen?|werktage?n?)\b",
    re.IGNORECASE,
)


def normalisiere(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text)).lower()
    text = text.replace("€", " euro ").replace("%", " prozent ")
    text = re.sub(r"[^a-zäöüß0-9,.-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def hat_fremdschrift(text: str) -> bool:
    return any("CJK" in unicodedata.name(zeichen, "") for zeichen in text)


def frage_stellen(frage: str, endpunkt: str = ENDPUNKT, steuerjahr: str = "2023") -> dict:
    anfrage = Request(
        endpunkt,
        # Die Weboberfläche sendet das im Auswahlfeld gesetzte Steuerjahr mit.
        # Ohne dieses Feld würde der Katalogtest einen anderen Nutzungskontext
        # prüfen als ein echtes Gespräch im Browser.
        data=json.dumps(
            {"frage": frage, "steuerjahr": steuerjahr}, ensure_ascii=False
        ).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with HTTP_OPENER.open(anfrage, timeout=180) as antwort:
        return json.load(antwort)


def nutzer_waehlen(endpunkt: str, name: str) -> dict:
    basis_url = endpunkt.rsplit("/api/frage", 1)[0]
    with HTTP_OPENER.open(Request(basis_url + "/api/nutzer"), timeout=30) as antwort:
        daten = json.load(antwort)
    gesucht = normalisiere(name)
    nutzer = next(
        (
            eintrag
            for eintrag in daten.get("nutzer", [])
            if normalisiere(eintrag.get("name", "")) == gesucht
        ),
        None,
    )
    if nutzer is None:
        raise ValueError(f"Nutzerprofil nicht gefunden: {name}")
    anfrage = Request(
        basis_url + "/api/nutzer/wechseln",
        data=json.dumps({"nutzer_id": nutzer["id"]}).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with HTTP_OPENER.open(anfrage, timeout=30) as antwort:
        return json.load(antwort)["nutzer"]


def basisfehler(daten: dict) -> str | None:
    antwort = str(daten.get("antwort", "")).strip()
    if not antwort:
        return "LEER"
    if UNSICHER.lower() in antwort.lower():
        return "WISSEN_FEHLT"
    if hat_fremdschrift(antwort):
        return "SPRACHFEHLER"
    if not daten.get("quellen"):
        return "OHNE_QUELLE"
    return None


def polaritaet(text: str) -> str | None:
    anfang = normalisiere(text)[:180]
    if re.match(r"^(ja|grundsätzlich ja|im grundsatz ja)\b", anfang):
        return "ja"
    if re.match(r"^(nein|grundsätzlich nein|im grundsatz nein)\b", anfang):
        return "nein"
    return None


def zahlenfakten(text: str) -> list[str]:
    """Liefert eindeutige Zahlen/Einheiten in einer vergleichbaren Schreibweise."""
    fakten: list[str] = []
    for treffer in ZAHL_MIT_EINHEIT.finditer(normalisiere(text)):
        wert = treffer.group("wert").replace(".", "").replace(",", ".")
        einheit = treffer.group("einheit")
        einheit = {
            "€": "euro", "%": "prozent", "kilometer": "km",
            "tag": "tage", "tagen": "tage", "tage": "tage",
            "monat": "monate", "monaten": "monate", "monate": "monate",
            "jahr": "jahre", "jahren": "jahre", "jahre": "jahre",
            "stunde": "stunden", "stunden": "stunden",
            "woche": "wochen", "wochen": "wochen",
            "werktag": "werktage", "werktagen": "werktage", "werktage": "werktage",
        }.get(einheit, einheit)
        fakt = f"{float(wert):g} {einheit}"
        if fakt not in fakten:
            fakten.append(fakt)
    return fakten


def fachbegriffe(text: str, hoechstens: int = 8) -> list[str]:
    woerter = re.findall(r"[a-zäöüß][a-zäöüß-]{6,}", normalisiere(text))
    ergebnis: list[str] = []
    for wort in woerter:
        if wort in STOPPWOERTER or wort.isdigit() or wort in ergebnis:
            continue
        ergebnis.append(wort)
        if len(ergebnis) >= hoechstens:
            break
    return ergebnis


def ist_multiple_choice(frage: str) -> bool:
    norm = normalisiere(frage)
    # Der frühere Buchstaben-RegEx hielt „z. B.“ irrtümlich für Option B.
    # Die Kataloge kennzeichnen echte Auswahlfragen ausdrücklich.
    return "antwortoption" in norm


def pruefe_sollantwort(frage: str, soll: str, antwort: str) -> dict:
    gruende: list[str] = []
    soll_pol = polaritaet(soll)
    ist_pol = polaritaet(antwort)
    if soll_pol and ist_pol != soll_pol:
        gruende.append(f"Ja/Nein-Kernaussage erwartet: {soll_pol}; erkannt: {ist_pol or 'nicht eindeutig'}")

    soll_zahlen = zahlenfakten(soll)
    ist_zahlen = set(zahlenfakten(antwort))
    fehlende_zahlen = [fakt for fakt in soll_zahlen if fakt not in ist_zahlen]
    if fehlende_zahlen:
        gruende.append("Zahlen/Einheiten fehlen oder weichen ab: " + ", ".join(fehlende_zahlen))

    begriffe = fachbegriffe(soll)
    antwort_norm = normalisiere(antwort)
    # Einfache Beugungen und Zusammensetzungen (Fahrt/Fahrten,
    # Arbeitstag/Arbeitsstätte) sollen nicht als Bedeutungsfehler gelten.
    gefundene = [
        wort for wort in begriffe
        if wort in antwort_norm or (len(wort) >= 8 and wort[:5] in antwort_norm)
    ]
    deckung = len(gefundene) / len(begriffe) if begriffe else 1.0
    # Freie Antworten dürfen Synonyme verwenden. Unter 25 Prozent ist die
    # Kernaussage meist wirklich verfehlt; knapp darüber genügen zusammen mit
    # korrekter Polarität und Zahlen zwei prägnante Fachbegriffe.
    if len(begriffe) >= 3 and deckung < 0.25:
        gruende.append(
            f"Zu geringe Fachbegriff-Deckung ({len(gefundene)}/{len(begriffe)}): "
            + ", ".join(wort for wort in begriffe if wort not in gefundene)
        )

    if ist_multiple_choice(frage):
        # Bei MC muss wenigstens der prägnante Beginn der Sollantwort erkennbar sein.
        kern = " ".join(normalisiere(soll).split()[:6])
        if kern and kern not in antwort_norm:
            gruende.append(f"Multiple-Choice-Lösung nicht eindeutig wiedergefunden: {kern}")

    return {
        "status": "FACHLICH_PRUEFEN" if gruende else "BESTANDEN",
        "gruende": gruende,
        "soll_zahlen": soll_zahlen,
        "fehlende_zahlen": fehlende_zahlen,
        "fachbegriffe": begriffe,
        "fachbegriff_deckung": round(deckung, 3),
    }


def bewerte_fall(fall: dict, daten: dict) -> dict:
    fehler = basisfehler(daten)
    if fehler:
        return {"status": fehler, "gruende": [fehler]}
    soll = str(fall.get("erwartete_antwort") or "").strip()
    if not soll:
        return {
            "status": "NUR_STRUKTURELL_BESTANDEN",
            "gruende": ["Im Katalog ist keine Sollantwort hinterlegt."],
        }
    return pruefe_sollantwort(fall["frage"], soll, str(daten.get("antwort", "")))


def schreibe_bericht(ergebnisse: list[dict], basis: Path, dauer_sekunden: float) -> tuple[Path, Path]:
    basis.parent.mkdir(parents=True, exist_ok=True)
    zaehler = Counter(e["status"] for e in ergebnisse)
    payload = {
        "erstellt_am": datetime.now().astimezone().isoformat(timespec="seconds"),
        "dauer_sekunden": round(dauer_sekunden, 1),
        "anzahl": len(ergebnisse),
        "status": dict(sorted(zaehler.items())),
        "ergebnisse": ergebnisse,
    }
    json_pfad = basis.with_suffix(".json")
    md_pfad = basis.with_suffix(".md")
    json_pfad.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    zeilen = [
        "# Strenger Steuerkatalog-Test",
        "",
        f"Erstellt: {payload['erstellt_am']}",
        f"Geprüfte Fragen: {len(ergebnisse)}",
        f"Laufzeit: {payload['dauer_sekunden']} Sekunden",
        "",
        "## Ergebnis",
        "",
    ]
    for status, anzahl in sorted(zaehler.items()):
        zeilen.append(f"- {status}: {anzahl}")
    zeilen += ["", "## Auffällige Antworten", ""]
    auffaellig = [e for e in ergebnisse if e["status"] not in {"BESTANDEN", "NUR_STRUKTURELL_BESTANDEN"}]
    if not auffaellig:
        zeilen.append("Keine Auffälligkeiten.")
    else:
        zeilen += ["| Katalog | ID | Status | Grund |", "|---|---:|---|---|"]
        for e in auffaellig:
            grund = "; ".join(e.get("gruende", [])) or e.get("fehler", "")
            grund = grund.replace("|", "\\|").replace("\n", " ")
            zeilen.append(f"| {e['katalog']} | {e['id']} | {e['status']} | {grund} |")
    zeilen += [
        "",
        "## Einordnung",
        "",
        "`FACHLICH_PRUEFEN` bedeutet: Die Antwort weicht bei einer maschinell prüfbaren "
        "Kernaussage von der Sollantwort ab. Das ist ein Prüfhinweis, noch kein endgültiges "
        "fachliches Urteil. `NUR_STRUKTURELL_BESTANDEN` betrifft Fragen ohne hinterlegte Sollantwort.",
        "",
    ]
    md_pfad.write_text("\n".join(zeilen), encoding="utf-8")
    return json_pfad, md_pfad


def lade_faelle(pfade: list[Path], begrenzung: int | None = None) -> list[tuple[Path, dict]]:
    alle: list[tuple[Path, dict]] = []
    for pfad in pfade:
        daten = json.loads(pfad.read_text(encoding="utf-8"))
        if isinstance(daten, dict):
            listen = [wert for wert in daten.values() if isinstance(wert, list)]
            if len(listen) != 1:
                raise ValueError(
                    f"{pfad.name}: Erwartet wird eine Fragenliste oder genau eine Liste im JSON-Objekt."
                )
            daten = listen[0]
        alle.extend((pfad, fall) for fall in daten)
    return alle[:begrenzung] if begrenzung else alle


def main() -> int:
    parser = argparse.ArgumentParser(description="Prüft Steuerfragen gegen Sollantworten.")
    parser.add_argument("katalog", nargs="?", help="Ein JSON-Katalog; ohne Angabe werden alle sechs geprüft.")
    parser.add_argument("--limit", type=int, help="Nur die ersten N Fälle prüfen (Kalibrierung).")
    parser.add_argument("--ids", help="Nur diese kommagetrennten IDs eines Katalogs prüfen.")
    parser.add_argument("--ausgabe", type=Path, help="Basispfad für .json und .md")
    parser.add_argument("--endpunkt", default=ENDPUNKT)
    parser.add_argument("--nutzer", default="Alex Beispiel")
    parser.add_argument("--steuerjahr", choices=("2023", "2024", "2025"), default="2023")
    args = parser.parse_args()

    pfade = [Path(args.katalog)] if args.katalog else [TESTORDNER / name for name in KATALOGE]
    faelle = lade_faelle(pfade)
    if args.ids:
        ids = {int(wert.strip()) for wert in args.ids.split(",")}
        faelle = [(pfad, fall) for pfad, fall in faelle if int(fall["id"]) in ids]
    if args.limit:
        faelle = faelle[:args.limit]
    nutzer = nutzer_waehlen(args.endpunkt, args.nutzer)
    print(f"NUTZER {nutzer['name']} | STEUERJAHR {args.steuerjahr}", flush=True)
    start = datetime.now()
    ergebnisse: list[dict] = []
    for nummer, (pfad, fall) in enumerate(faelle, 1):
        basis = {"katalog": pfad.name, "id": fall["id"], "kategorie": fall.get("kategorie", ""), "frage": fall["frage"]}
        try:
            daten = frage_stellen(fall["frage"], args.endpunkt, args.steuerjahr)
            details = bewerte_fall(fall, daten)
            eintrag = {
                **basis,
                **details,
                "erwartete_antwort": fall.get("erwartete_antwort"),
                "antwort": daten.get("antwort", ""),
                "quellen": daten.get("quellen", []),
            }
        except (HTTPError, URLError, TimeoutError, ValueError, OSError) as fehler:
            eintrag = {**basis, "status": "TECHNISCHER_FEHLER", "gruende": [str(fehler)], "fehler": str(fehler)}
        ergebnisse.append(eintrag)
        print(f"[{nummer}/{len(faelle)}] {pfad.name} #{fall['id']}: {eintrag['status']}", flush=True)

    dauer = (datetime.now() - start).total_seconds()
    zeit = datetime.now().strftime("%Y%m%d_%H%M%S")
    basis = args.ausgabe or TESTORDNER / "ergebnisse" / f"strenger_katalogtest_{zeit}"
    json_pfad, md_pfad = schreibe_bericht(ergebnisse, basis, dauer)
    zaehler = Counter(e["status"] for e in ergebnisse)
    print("ZUSAMMENFASSUNG", json.dumps(dict(sorted(zaehler.items())), ensure_ascii=False))
    print(f"BERICHT_JSON {json_pfad}")
    print(f"BERICHT_MD {md_pfad}")
    harte_fehler = {"LEER", "WISSEN_FEHLT", "SPRACHFEHLER", "OHNE_QUELLE", "TECHNISCHER_FEHLER"}
    return 1 if any(e["status"] in harte_fehler or e["status"] == "FACHLICH_PRUEFEN" for e in ergebnisse) else 0


if __name__ == "__main__":
    sys.exit(main())
