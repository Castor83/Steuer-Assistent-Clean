"""Direkter Semantikvergleich der finalen GGUF-Kandidaten.

Der Lauf verwendet ausschließlich bereits vorhandene, unveränderte Sollfälle.
XML-/ELSTER-Export ist nicht Bestandteil dieser Freigabeschranke.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "tests"))

from modell_ressourcen import ModellRessourcenManager
from strenger_katalogtest import normalisiere, pruefe_sollantwort


# Datei und ID bilden zusammen den unveränderlichen Selektor. Die Auswahl deckt
# Trennungsfragen, Rechenlogik und die vier priorisierten Fachbereiche ab.
SELEKTOREN = (
    ("neuer_testkatalog_100.json", 68, "Lebensführung/Krankheitskosten"),
    ("neuer_testkatalog_100.json", 72, "AfA: Grund und Boden"),
    ("neuer_testkatalog_100.json", 73, "AfA: Abschreibungssatz"),
    ("neuer_testkatalog_100.json", 63, "Außergewöhnliche Belastung"),
    ("neuer_testkatalog_150.json", 25, "Lohnsteuer/private Lebensführung"),
    ("neuer_testkatalog_150.json", 32, "AfA-Bemessungsgrundlage"),
    ("neuer_testkatalog_150.json", 79, "Grundsteuer/Rechtsbehelf"),
    ("neuer_testkatalog_150.json", 3, "Lohnsteuer/Sachbezug"),
    ("neuer_testkatalog_lohnsteuer_100.json", 47, "Bayerische Grundsteuer"),
    ("neuer_testkatalog_151_300.json", 151, "Erbschaftsteuer/Freibetrag"),
    ("neuer_testkatalog_151_300.json", 153, "Erbschaftsteuer/Familienheim"),
    ("neuer_testkatalog_151_300.json", 158, "Erbschaftsteuer/Meldeverfahren"),
)

INSOLVENZGELD_FAELLE = (
    {
        "id": "P27",
        "thema": "Insolvenzgeld/Antragsverfahren",
        "frage": "Über meinen Arbeitgeber wurde das Insolvenzverfahren eröffnet. Bis wann muss ich Insolvenzgeld beantragen?",
        "erwartete_antwort": "Der Antrag auf Insolvenzgeld muss innerhalb von zwei Monaten nach dem Insolvenzereignis bei der Agentur für Arbeit gestellt werden.",
    },
    {
        "id": "P29",
        "thema": "Insolvenzgeld/Steuerwirkung",
        "frage": "Wird auf Insolvenzgeld direkt Einkommensteuer einbehalten?",
        "erwartete_antwort": "Nein. Insolvenzgeld ist steuerfrei, unterliegt aber dem Progressionsvorbehalt.",
    },
)

SYSTEM = (
    "Beantworte den deutschen Steuerfall fachlich präzise und knapp. "
    "Nenne Voraussetzungen und Einschränkungen, wenn sie für die Entscheidung wesentlich sind. "
    "Erfinde keine Tatsachen und stelle keine Rückfrage, wenn der Sachverhalt ausreicht."
)

# Die Embedding-Nähe erkennt Bedeutungsdrift, aber keine einzelne falsche Zahl.
# Diese Regeln sichern deshalb die entscheidenden Fakten der ausgewählten,
# bereits vorhandenen Sollantworten zusätzlich ab.
KRITISCHE_REGELN = {
    "neuer_testkatalog_100.json:68": {
        "muss": ((r"ärztlich\w* (?:verordnet|verschrieben)", r"konkrete\w* erkrankung", r"medizinische\w* indikation"),),
        "darf_nicht": (r"selbst bei medizinischer indikation.*keine krankheitskosten",),
    },
    "neuer_testkatalog_100.json:72": {
        "muss": (
            (r"grund und boden", r"bodenanteil"),
            (r"nicht (?:abgeschrieben|absetzbar)", r"nicht abnutzbar", r"abgeschrieben wird.*nicht grund und boden"),
        ),
    },
    "neuer_testkatalog_100.json:73": {
        "muss": ((r"3 (?:prozent|%)",),), "darf_nicht": (r"2 (?:prozent|%)",),
    },
    "neuer_testkatalog_100.json:63": {
        "muss": ((r"nachlass", r"erb\w*"), (r"übersteig\w*",)),
        "darf_nicht": (r"selbstbehalt.*1[ .]?080", r"pauschale freibeträge.*verwandtschaftsgrad"),
    },
    "neuer_testkatalog_150.json:25": {
        "muss": ((r"lohnsteuerpflicht\w*", r"steuerpflicht\w* arbeitslohn", r"geldwerte\w* vorteil"),),
    },
    "neuer_testkatalog_150.json:32": {
        "muss": ((r"150[ .]?000 euro",), (r"grund und boden", r"bodenanteil")),
        "darf_nicht": (r"selbst genutz\w*.*(?:afa|abschreibung).*anrechenbar",),
    },
    "neuer_testkatalog_150.json:79": {
        "muss": ((r"keine aufschiebende wirkung",), (r"zahl\w*",)),
    },
    "neuer_testkatalog_150.json:3": {
        "muss": ((r"steuerfrei",), (r"zusätzlich",)),
        "darf_nicht": (r"(?:regulär\w*|voll).*lohnsteuer", r"arbeitslohn.*versteuer"),
    },
    "neuer_testkatalog_lohnsteuer_100.json:47": {
        "muss": ((r"flächenmodell", r"äquivalenzmodell"), (r"wertunabhängig",)),
        "darf_nicht": (r"wertorientiert\w* modell",),
    },
    "neuer_testkatalog_151_300.json:151": {
        "muss": ((r"500[ .]?000 euro",), (r"10 jahre",)),
    },
    "neuer_testkatalog_151_300.json:153": {
        "muss": ((r"unverzüglich",), (r"10 jahre",), (r"200 quadratmeter", r"200 qm")),
    },
    "neuer_testkatalog_151_300.json:158": {
        "muss": ((r"3 monate", r"drei monate"),), "darf_nicht": (r"6 monate", r"sechs monate"),
    },
    "P27": {
        "muss": ((r"2 monate", r"zwei monate"), (r"agentur für arbeit",)),
        "darf_nicht": (r"31 dezember", r"ablauf des monats",),
    },
    "P29": {
        "muss": ((r"steuerfrei",), (r"progressionsvorbehalt",)),
    },
}

# Die Modellabnahme darf erst starten, wenn die entscheidenden amtlichen
# Regelchunks tatsaechlich unter den acht Kontexttreffern liegen. Damit werden
# Retrieval- und Generierungsfehler getrennt ausgewiesen.
RETRIEVAL_REGELN = {
    "neuer_testkatalog_100.json:68": {
        "dateien": ("standardfaelle_2023_2025_ergaenzung.json",),
        "muss": ((r"verhütungs", r"nahrungsergänzung"), (r"ärztlich", r"verordnung")),
    },
    "neuer_testkatalog_100.json:72": {
        "dateien": ("estg_7_afa_vermietung.json", "esth_anschaffungsnebenkosten_immobilie.json"),
        "muss": ((r"grund und boden",), (r"nicht (?:abnutzbar|abschreibbar)",)),
    },
    "neuer_testkatalog_100.json:73": {
        "dateien": ("estg_7_afa_vermietung.json", "estg_7_afa_wohngebaeude_2026.json"),
        "muss": ((r"3 prozent",), (r"31\. dezember 2022",)),
    },
    "neuer_testkatalog_100.json:63": {
        "dateien": ("estg_33_bestattungskosten.json",),
        "muss": ((r"nachlass",), (r"ersatzleistungen",), (r"übersteigen",)),
    },
    "neuer_testkatalog_150.json:25": {
        "dateien": ("estg_19_private_umzugskosten_arbeitgeber.json",),
        "muss": ((r"privat",), (r"steuerpflichtiger arbeitslohn", r"geldwerten vorteil")),
    },
    "neuer_testkatalog_150.json:32": {
        "dateien": ("esth_anschaffungsnebenkosten_immobilie.json", "estg_7_afa_vermietung.json"),
        "muss": ((r"afa-bemessungsgrundlage", r"afa-bemessungsgrundlag"), (r"grund und boden",)),
    },
    "neuer_testkatalog_150.json:79": {
        "dateien": ("ao_222_355_361_rechtsbehelf_stundung.json",),
        "muss": ((r"einspruch",), (r"zahlung nicht", r"zahlungspflicht")),
    },
    "neuer_testkatalog_150.json:3": {
        "dateien": ("lohnsteuer_sonderfaelle_2026_ergaenzung.json",),
        "muss": ((r"3 nr\. 37",), (r"steuerfrei",), (r"gehaltsumwandlung",)),
    },
    "neuer_testkatalog_lohnsteuer_100.json:47": {
        "dateien": ("steuerjahr_2025_grundsteuer_bayern.json", "bayern_grundsteuer_praxis.json"),
        "muss": ((r"flächenmodell",), (r"wertunabhängig",)),
    },
    "neuer_testkatalog_151_300.json:151": {
        "dateien": ("erbstg_freibetraege_steuersaetze.json",),
        "muss": ((r"500\.000 euro",), (r"zehn jahren",)),
    },
    "neuer_testkatalog_151_300.json:153": {
        "dateien": ("erbstg_13_familienheim.json",),
        "muss": ((r"unverzüglich",), (r"zehn jahren",), (r"200 quadratmetern",)),
    },
    "neuer_testkatalog_151_300.json:158": {
        "dateien": ("erbstg_30_schenkungsanzeige.json",),
        "muss": ((r"drei monaten",), (r"nach kenntnis",)),
    },
    "P27": {
        "dateien": ("insolvenzgeld_anspruch_antrag.json",),
        "muss": ((r"zwei monaten",), (r"agentur für arbeit",)),
    },
    "P29": {
        "dateien": ("insolvenzgeld_steuer_2023_2025.json",),
        "muss": ((r"steuerfrei",), (r"progressionsvorbehalt",)),
    },
}

ERWARTETER_FRISTTYP = {
    "neuer_testkatalog_151_300.json:151": "materieller_zeitraum",
    "neuer_testkatalog_151_300.json:153": "materieller_zeitraum",
    "neuer_testkatalog_151_300.json:158": "verfahrensfrist",
    "P27": "verfahrensfrist",
}


def _fristtypen(text: str) -> set[str]:
    """Trennt Verfahrensfristen von materiellen Zehnjahreszeiträumen."""
    norm = normalisiere(text)
    typen = set()
    if re.search(r"(?:10|zehn) jahr", norm):
        typen.add("materieller_zeitraum")
    if (
        re.search(r"(?:zwei|2|drei|3) monate", norm)
        and any(wort in norm for wort in (
            "antrag", "beantrag", "anzeig", "melde", "frist",
            "agentur fur arbeit", "kenntnis",
        ))
    ) or (
        "einspruch" in norm
        and any(wort in norm for wort in ("monat", "frist", "bekanntgabe"))
    ):
        typen.add("verfahrensfrist")
    return typen


def _sha256(pfad: Path) -> str:
    return hashlib.sha256(pfad.read_bytes()).hexdigest()


def _faelle_laden() -> tuple[list[dict], dict[str, str]]:
    cache: dict[str, list[dict]] = {}
    pruefsummen: dict[str, str] = {}
    faelle: list[dict] = []
    for datei, fall_id, thema in SELEKTOREN:
        pfad = ROOT / "tests" / datei
        if datei not in cache:
            cache[datei] = json.loads(pfad.read_text(encoding="utf-8"))
            pruefsummen[datei] = _sha256(pfad)
        treffer = [fall for fall in cache[datei] if int(fall["id"]) == fall_id]
        if len(treffer) != 1:
            raise ValueError(f"{datei}: ID {fall_id} nicht eindeutig gefunden")
        fall = treffer[0]
        faelle.append({
            "id": f"{datei}:{fall_id}",
            "thema": thema,
            "frage": fall["frage"],
            "erwartete_antwort": fall["erwartete_antwort"],
        })

    praxis = ROOT / "tests" / "praxischarge_50.json"
    pruefsummen[praxis.name] = _sha256(praxis)
    praxis_ids = {fall["id"] for fall in json.loads(praxis.read_text(encoding="utf-8"))}
    for fall in INSOLVENZGELD_FAELLE:
        if fall["id"] not in praxis_ids:
            raise ValueError(f"{praxis.name}: ID {fall['id']} fehlt")
        faelle.append(dict(fall))
    return faelle, pruefsummen


def _kosinus(a: list[float], b: list[float]) -> float:
    skalar = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return skalar / (norm_a * norm_b) if norm_a and norm_b else 0.0


def _inhalt(antwort) -> str:
    message = antwort.get("message", {})
    return str(message.get("content", "")).strip()


def _kritische_fakten_pruefen(fall_id: str, antwort: str) -> dict:
    regeln = KRITISCHE_REGELN.get(fall_id, {})
    text = normalisiere(antwort)
    fehlende = [
        list(alternativen)
        for alternativen in regeln.get("muss", ())
        if not any(re.search(muster, text) for muster in alternativen)
    ]
    verbotene = [
        muster for muster in regeln.get("darf_nicht", ()) if re.search(muster, text)
    ]
    return {
        "bestanden": not fehlende and not verbotene,
        "fehlende_mustergruppen": fehlende,
        "getroffene_verbote": verbotene,
    }


def _retrieval_vorpruefung(rag_assistent, faelle: list[dict]) -> dict:
    auswertung = []
    for fall in faelle:
        jahr = rag_assistent.bestimme_steuerjahr(fall["frage"], 2025, {})
        kanonisch = rag_assistent.kanonisiere_alltagssprache(
            rag_assistent.normalisiere(fall["frage"])
        )
        fokus = rag_assistent.bestimme_fragefokus(fall["frage"])
        if fokus:
            kanonisch += " " + fokus.suchbegriffe
        suchfrage = f"{fall['frage']}\nSuchbegriffe: {kanonisch}"
        suchdiagnose = {}
        treffer = rag_assistent.suche_wissen(
            suchfrage,
            limit=24,
            steuerjahr=jahr,
            diagnose=suchdiagnose,
        )
        if fokus:
            treffer = [quelle for quelle in treffer if fokus.passt(quelle.payload)]
        kontext = treffer[:8]
        regeln = RETRIEVAL_REGELN[fall["id"]]
        erwartete_dateien = set(regeln["dateien"])
        gefundene_dateien = {
            str(quelle.payload.get("datei", "")) for quelle in kontext
        }
        quelltext = normalisiere(" ".join(
            str(quelle.payload.get("text", "")) for quelle in kontext
        ))
        fehlende_muster = [
            list(alternativen)
            for alternativen in regeln["muss"]
            if not any(re.search(muster, quelltext) for muster in alternativen)
        ]
        datei_ok = bool(erwartete_dateien & gefundene_dateien)
        erwartete_raenge = [
            {
                "datei": datei,
                "raenge": [
                    rang for rang, quelle in enumerate(treffer, 1)
                    if str(quelle.payload.get("datei", "")) == datei
                ],
                "im_top_8": any(
                    str(quelle.payload.get("datei", "")) == datei
                    for quelle in kontext
                ),
            }
            for datei in sorted(erwartete_dateien)
        ]
        rohe_solltreffer = [
            eintrag for eintrag in suchdiagnose.get("semantische_rohtreffer", [])
            if eintrag.get("datei") in erwartete_dateien
        ]
        schwellenwert_diagnose = []
        for datei in sorted(erwartete_dateien):
            rohe_dateitreffer = [
                eintrag for eintrag in rohe_solltreffer
                if eintrag.get("datei") == datei
            ]
            bester = max(
                rohe_dateitreffer,
                key=lambda eintrag: float(eintrag.get("score", 0.0)),
                default=None,
            )
            schwelle = (
                0.35
                if bester and bester.get("quellenart") == "quellenkarte"
                else rag_assistent.SCORE_THRESHOLD
            )
            schwellenwert_diagnose.append({
                "datei": datei,
                "semantischer_rohrang": bester.get("rohrang") if bester else None,
                "semantischer_rohscore": bester.get("score") if bester else None,
                "angewandter_schwellenwert": schwelle,
                "am_schwellenwert_gescheitert": bool(
                    bester and float(bester.get("score", 0.0)) < schwelle
                ),
            })

        sollquellen_metadaten = []
        for datei in sorted(erwartete_dateien):
            payload = next(
                (
                    karte for karte in rag_assistent.lokale_quellenkarten()
                    if karte.get("datei") == datei
                ),
                None,
            )
            sollquellen_metadaten.append({
                "datei": datei,
                "steuerjahr": payload.get("steuerjahr") if payload else None,
                "suchjahre": payload.get("suchjahre") if payload else None,
                "gueltig_fuer": payload.get("gueltig_fuer") if payload else None,
                "jahr_abhaengig": payload.get("jahr_abhaengig") if payload else None,
                "jahr_unabhaengig": payload.get("jahr_unabhaengig") if payload else None,
                "fuer_aktives_jahr_zugelassen": bool(
                    payload
                    and rag_assistent.quelle_passt_zum_steuerjahr(payload, jahr)
                ),
            })

        fristtypen_im_kontext = sorted(_fristtypen(quelltext))
        erwarteter_fristtyp = ERWARTETER_FRISTTYP.get(fall["id"])
        frist_isolierung_ok = (
            True
            if erwarteter_fristtyp is None
            else erwarteter_fristtyp in fristtypen_im_kontext
            and not (
                {"materieller_zeitraum", "verfahrensfrist"}
                <= set(fristtypen_im_kontext)
            )
        )
        original_woerter = set(normalisiere(fall["frage"]).split())
        kanonische_woerter = set(normalisiere(kanonisch).split())
        auswertung.append({
            "id": fall["id"],
            "steuerjahr": jahr,
            "bestanden": datei_ok and not fehlende_muster and frist_isolierung_ok,
            "kanonisierung": {
                "originalfrage": fall["frage"],
                "kanonisierte_suchbegriffe": kanonisch,
                "finale_suchfrage": suchdiagnose.get("erweiterte_suchfrage", suchfrage),
                "hinzugefuegte_woerter": sorted(kanonische_woerter - original_woerter),
                "fragefokus": fokus.suchbegriffe if fokus else None,
            },
            "erwartete_dateien": sorted(erwartete_dateien),
            "datei_gefunden": datei_ok,
            "erwartete_datei_raenge": erwartete_raenge,
            "schwellenwert_diagnose": schwellenwert_diagnose,
            "jahresfilter_diagnose": {
                "aktives_steuerjahr": jahr,
                "sollquellen": sollquellen_metadaten,
                "abgelehnte_kandidaten": suchdiagnose.get("jahresfilter_abgelehnt", []),
            },
            "fristen_diagnose": {
                "erwarteter_typ": erwarteter_fristtyp,
                "typen_im_top_8": fristtypen_im_kontext,
                "isolierung_bestanden": frist_isolierung_ok,
            },
            "fehlende_mustergruppen": fehlende_muster,
            "kontext": [
                {
                    "rang": rang,
                    "datei": quelle.payload.get("datei") or quelle.payload.get("quelle_id"),
                    "paragraph": quelle.payload.get("paragraph"),
                    "steuerjahr": quelle.payload.get("steuerjahr"),
                    "chunk": quelle.payload.get("chunk"),
                    "score": round(float(quelle.score), 6),
                    "rohscore": round(float(getattr(
                        quelle, "rohscore", quelle.score
                    )), 6),
                    "nachsortierung": round(float(getattr(
                        quelle, "nachsortierung", quelle.score
                    )), 6),
                    "trefferart": getattr(quelle, "trefferart", "elster"),
                    "fristtypen": sorted(_fristtypen(str(quelle.payload.get("text", "")))),
                    "text": str(quelle.payload.get("text", ""))[:500],
                }
                for rang, quelle in enumerate(kontext, 1)
            ],
        })
    return {
        "bestanden": all(eintrag["bestanden"] for eintrag in auswertung),
        "faelle": len(auswertung),
        "bestanden_anzahl": sum(eintrag["bestanden"] for eintrag in auswertung),
        "ergebnisse": auswertung,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--modelle", nargs="+",
        default=["steuer-assistent-pilot13:q5_k_m", "steuer-assistent-pilot13:q4_k_m"],
    )
    parser.add_argument("--embedding", default="qwen3-embedding:4b")
    parser.add_argument("--min-aehnlichkeit", type=float, default=0.60)
    parser.add_argument("--modus", choices=("rag", "rohmodell"), default="rag")
    parser.add_argument(
        "--nur-retrieval", action="store_true",
        help="Prueft nur, ob die korrekten amtlichen Regelchunks im Kontext liegen.",
    )
    parser.add_argument(
        "--ausgabe",
        default=str(ROOT / "tests/ergebnisse/semantischer_steuervergleich.json"),
    )
    args = parser.parse_args()

    faelle, pruefsummen = _faelle_laden()
    manager = ModellRessourcenManager()
    rag_assistent = None
    if args.modus == "rag" or args.nur_retrieval:
        import rag_assistent as rag_modul
        rag_assistent = rag_modul
    start = time.perf_counter()
    ergebnisse: dict[str, list[dict]] = {}

    retrieval_vorpruefung = None
    if rag_assistent is not None:
        retrieval_vorpruefung = _retrieval_vorpruefung(rag_assistent, faelle)
        print(
            f"RETRIEVAL {retrieval_vorpruefung['bestanden_anzahl']}/"
            f"{retrieval_vorpruefung['faelle']}",
            flush=True,
        )
        if args.nur_retrieval or not retrieval_vorpruefung["bestanden"]:
            bericht = {
                "zweck": "Retrieval-Vorpruefung vor dem semantischen Modelllauf",
                "modus": "nur-retrieval",
                "katalog_pruefsummen": pruefsummen,
                "dauer_sekunden": round(time.perf_counter() - start, 2),
                "retrieval_vorpruefung": retrieval_vorpruefung,
                "vollstaendig_bestanden": retrieval_vorpruefung["bestanden"],
            }
            ziel = Path(args.ausgabe)
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_text(json.dumps(bericht, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"BERICHT {ziel}", flush=True)
            return 0 if retrieval_vorpruefung["bestanden"] else 2

    for modell in args.modelle:
        modell_ergebnisse: list[dict] = []
        print(f"MODELL {modell}", flush=True)
        for nummer, fall in enumerate(faelle, 1):
            quellen = []
            if args.modus == "rag":
                rag_assistent.CHAT_MODEL = modell
                # Der Vergleich darf einen Modellfehler nicht durch einen
                # unbemerkten Wechsel auf ein anderes Modell verdecken.
                rag_assistent.RESSOURCEN_FALLBACK_CHAT_MODEL = modell
                text, quellen = rag_assistent.beantworte(
                    fall["frage"], steuerprofil={}, steuerjahr=2025
                )
            else:
                antwort = manager.chat(
                    modell,
                    [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": fall["frage"]},
                    ],
                    options={"temperature": 0, "num_predict": 384, "num_ctx": 4096},
                )
                text = _inhalt(antwort)
            regelpruefung = pruefe_sollantwort(
                fall["frage"], fall["erwartete_antwort"], text
            )
            kritische_pruefung = _kritische_fakten_pruefen(fall["id"], text)
            modell_ergebnisse.append({
                **fall,
                "antwort": text,
                "regelpruefung": regelpruefung,
                "kritische_fakten": kritische_pruefung,
                "quellenanzahl": len(quellen),
            })
            print(
                f"[{nummer:02d}/{len(faelle)}] {fall['thema']}: {regelpruefung['status']}",
                flush=True,
            )
        ergebnisse[modell] = modell_ergebnisse
        manager.chat_entladen(modell)

    # Alle Texte in einem Aufruf einbetten, damit identische Bedingungen gelten.
    texte: list[str] = []
    zuordnung: list[tuple[str, int, str]] = []
    for modell, modell_ergebnisse in ergebnisse.items():
        for index, fall in enumerate(modell_ergebnisse):
            texte.extend((fall["erwartete_antwort"], fall["antwort"]))
            zuordnung.extend(((modell, index, "soll"), (modell, index, "ist")))
    embedding_antwort = manager.embedding(args.embedding, texte)
    vektoren = embedding_antwort.get("embeddings", [])
    if len(vektoren) != len(texte):
        raise RuntimeError("Embedding-Runtime lieferte nicht für jeden Text einen Vektor")
    vektor_map = {schluessel: vektor for schluessel, vektor in zip(zuordnung, vektoren)}

    for modell, modell_ergebnisse in ergebnisse.items():
        for index, fall in enumerate(modell_ergebnisse):
            aehnlichkeit = _kosinus(
                vektor_map[(modell, index, "soll")],
                vektor_map[(modell, index, "ist")],
            )
            fall["semantische_aehnlichkeit"] = round(aehnlichkeit, 4)
            fall["semantik_gate"] = aehnlichkeit >= args.min_aehnlichkeit
            # Die allgemeine Regelprüfung bleibt als Diagnose erhalten. Das
            # harte Gate stützt sich auf die fallspezifischen Kernfakten und
            # die Semantik; eine korrekte Antwort muss nicht mit "Ja/Nein"
            # beginnen und darf deshalb nicht allein daran scheitern.
            fall["bestanden"] = (
                fall["kritische_fakten"]["bestanden"] and fall["semantik_gate"]
            )

    zusammenfassung = {}
    for modell, modell_ergebnisse in ergebnisse.items():
        zusammenfassung[modell] = {
            "faelle": len(modell_ergebnisse),
            "bestanden": sum(fall["bestanden"] for fall in modell_ergebnisse),
            "regelpruefung_bestanden": sum(
                fall["regelpruefung"]["status"] == "BESTANDEN"
                for fall in modell_ergebnisse
            ),
            "kritische_fakten_bestanden": sum(
                fall["kritische_fakten"]["bestanden"] for fall in modell_ergebnisse
            ),
            "semantik_gate_bestanden": sum(
                fall["semantik_gate"] for fall in modell_ergebnisse
            ),
            "mittlere_semantische_aehnlichkeit": round(
                sum(fall["semantische_aehnlichkeit"] for fall in modell_ergebnisse)
                / len(modell_ergebnisse),
                4,
            ),
        }

    vollstaendig_bestanden = all(
        info["bestanden"] == info["faelle"] for info in zusammenfassung.values()
    )
    bericht = {
        "zweck": "Semantische Freigabeschranke vor XML-/Formular-Export",
        "modus": args.modus,
        "modelle": args.modelle,
        "embedding_modell": args.embedding,
        "min_semantische_aehnlichkeit": args.min_aehnlichkeit,
        "katalog_pruefsummen": pruefsummen,
        "dauer_sekunden": round(time.perf_counter() - start, 2),
        "retrieval_vorpruefung": retrieval_vorpruefung,
        "zusammenfassung": zusammenfassung,
        "vollstaendig_bestanden": vollstaendig_bestanden,
        "ergebnisse": ergebnisse,
    }
    ziel = Path(args.ausgabe)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(json.dumps(bericht, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(zusammenfassung, ensure_ascii=False, indent=2), flush=True)
    print(f"BERICHT {ziel}", flush=True)
    return 0 if vollstaendig_bestanden else 1


if __name__ == "__main__":
    raise SystemExit(main())
