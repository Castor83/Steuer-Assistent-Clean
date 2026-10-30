"""Füllt bestätigte Werte in Mein ELSTER aus, übermittelt aber niemals Daten."""

from __future__ import annotations

import argparse
from collections import Counter, OrderedDict
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
MAPPING_ROOT = ROOT / "wissen" / "elster" / "mappings"
START_URL = "https://www.elster.de/eportal/start"
MAPPING_SCHEMA = "steuer-assistent-mein-elster-browser-mapping/v1"
UNTERSTUETZTE_STEUERJAHRE = ("2023", "2024", "2025")
ERLAUBTE_MODI = {"ausfuellen", "abgleich_edaten"}
ERLAUBTE_VERGLEICHE = {"text", "kennung", "iban", "zahl", "betrag"}
VERBOTENE_INPUT_TYPEN = {"button", "submit", "reset", "file", "image", "hidden"}


def _blockzuordnung(mapping: dict) -> dict[str, dict]:
    bloecke = mapping.get("abschnittsbloecke")
    if not isinstance(bloecke, list) or not bloecke:
        raise ValueError("Das Browser-Mapping enthält keine freigegebenen Abschnittsblöcke.")
    zuordnung: dict[str, dict] = {}
    block_ids = set()
    for block in bloecke:
        block_id = str(block.get("id", "")).strip()
        titel = str(block.get("titel", "")).strip()
        felder = block.get("felder")
        if not block_id or block_id in block_ids or not titel:
            raise ValueError("Ein Abschnittsblock ist leer, doppelt oder unvollständig.")
        if not isinstance(felder, list) or not felder:
            raise ValueError(f"{block_id}: Der Abschnittsblock enthält keine Felder.")
        block_ids.add(block_id)
        for feld_id in felder:
            feld_id = str(feld_id).strip()
            if not feld_id or feld_id in zuordnung:
                raise ValueError(f"{block_id}: Feld-ID ist leer oder mehrfach zugeordnet: {feld_id!r}.")
            zuordnung[feld_id] = {"id": block_id, "titel": titel}
    mapping_felder = set(mapping.get("felder", {}))
    if set(zuordnung) != mapping_felder:
        fehlend = sorted(mapping_felder - set(zuordnung))
        unbekannt = sorted(set(zuordnung) - mapping_felder)
        raise ValueError(
            "Abschnittsblöcke und Feldmapping sind nicht deckungsgleich: "
            f"fehlend={fehlend}, unbekannt={unbekannt}."
        )
    return zuordnung


def mapping_pfad(steuerjahr: str) -> Path:
    steuerjahr = str(steuerjahr)
    if steuerjahr not in UNTERSTUETZTE_STEUERJAHRE:
        raise ValueError(f"Nicht unterstütztes Steuerjahr: {steuerjahr!r}.")
    return MAPPING_ROOT / steuerjahr / "browser_feldmapping_v1.json"


def lade_browser_mapping(steuerjahr: str = "2025") -> dict:
    steuerjahr = str(steuerjahr)
    mapping = json.loads(mapping_pfad(steuerjahr).read_text(encoding="utf-8"))
    if mapping.get("schema") != MAPPING_SCHEMA:
        raise ValueError("Unbekanntes Browser-Feldmapping.")
    if mapping.get("steuerjahr") != steuerjahr:
        raise ValueError(f"Das Browser-Feldmapping passt nicht zu ESt {steuerjahr}.")
    freigabe = mapping.get("freigabe", {})
    if freigabe.get("sandbox_validiert") is not True:
        raise ValueError(f"Das Browser-Feldmapping für ESt {steuerjahr} ist nicht sandbox-validiert.")
    layout_vertrag = mapping.get("layout_vertrag", {})
    erwartete_layout_version = f"mein-elster-est{steuerjahr}-layout/v1"
    if layout_vertrag.get("version") != erwartete_layout_version:
        raise ValueError("Der Mein-ELSTER-Layoutvertrag ist unbekannt oder nicht freigegeben.")
    erlaubte_tags = set(layout_vertrag.get("erlaubte_tags", []))
    if not erlaubte_tags or erlaubte_tags - {"input", "textarea"}:
        raise ValueError("Der Layoutvertrag erlaubt einen unsicheren Feldtyp.")
    if not set(layout_vertrag.get("verbotene_input_typen", [])) >= VERBOTENE_INPUT_TYPEN:
        raise ValueError("Der Layoutvertrag enthält nicht alle verbotenen Eingabetypen.")
    _blockzuordnung(mapping)
    for feld_id, regel in mapping.get("felder", {}).items():
        if regel.get("modus") not in ERLAUBTE_MODI:
            raise ValueError(f"{feld_id}: nicht erlaubter Automationsmodus.")
        if regel.get("vergleich", "text") not in ERLAUBTE_VERGLEICHE:
            raise ValueError(f"{feld_id}: unbekannter Soll-Ist-Vergleich.")
        if not regel.get("labels"):
            raise ValueError(f"{feld_id}: sichtbare Feldbezeichnung fehlt.")
    return mapping


def _mapping_sha256(mapping: dict) -> str:
    kanonisch = json.dumps(mapping, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(kanonisch.encode("utf-8")).hexdigest()


def erstelle_sicherheitskontext(mapping: dict | None = None) -> dict:
    mapping = lade_browser_mapping() if mapping is None else mapping
    return {
        "mapping_sha256": _mapping_sha256(mapping),
        "schema": mapping["schema"],
        "steuerjahr": mapping["steuerjahr"],
        "layout_vertrag_version": mapping["layout_vertrag"]["version"],
    }


def pruefe_versionsschranke(sicherheitskontext: dict) -> tuple[dict | None, list[str]]:
    try:
        aktuell = lade_browser_mapping(str(sicherheitskontext.get("steuerjahr", "")))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return None, [f"Browser-Mapping nicht mehr sicher lesbar: {exc}"]
    fehler = []
    erwartete_werte = {
        "schema": aktuell.get("schema"),
        "steuerjahr": aktuell.get("steuerjahr"),
        "layout_vertrag_version": aktuell.get("layout_vertrag", {}).get("version"),
        "mapping_sha256": _mapping_sha256(aktuell),
    }
    for name, ist_wert in erwartete_werte.items():
        if sicherheitskontext.get(name) != ist_wert:
            fehler.append(f"Versionsschranke verletzt: {name} wurde während des Laufs geändert.")
    return aktuell, fehler


def lade_eingabehilfe(pfad: str | Path) -> dict:
    datei = Path(pfad).expanduser().resolve()
    daten = json.loads(datei.read_text(encoding="utf-8-sig"))
    if daten.get("format") != "steuer-assistent-elster-eingabehilfe/v1":
        raise ValueError("Die Datei ist keine Steuer-Assistent-ELSTER-Eingabehilfe.")
    if str(daten.get("steuerjahr", "")) not in UNTERSTUETZTE_STEUERJAHRE:
        raise ValueError(
            "Die Browserbefüllung unterstützt ausschließlich ESt 2023, 2024 und 2025."
        )
    if daten.get("versandfaehig") is not False:
        raise ValueError("Eine als versandfähig markierte Datei wird aus Sicherheitsgründen abgelehnt.")
    if not isinstance(daten.get("felder"), list):
        raise ValueError("Die Feldliste der Eingabehilfe fehlt.")
    return daten


def erstelle_aktionsplan(
    eingabehilfe: dict,
    edaten_ueberschreiben: bool = False,
    mapping: dict | None = None,
) -> list[dict]:
    steuerjahr = str(eingabehilfe.get("steuerjahr", ""))
    mapping = lade_browser_mapping(steuerjahr) if mapping is None else mapping
    if mapping.get("steuerjahr") != steuerjahr:
        raise ValueError(
            f"Eingabehilfe für {steuerjahr} darf nicht mit Mapping {mapping.get('steuerjahr')} laufen."
        )
    blockzuordnung = _blockzuordnung(mapping)
    aktionen = []
    for feld in eingabehilfe["felder"]:
        feld_id = str(feld.get("lokale_feld_id", "")).strip()
        regel = mapping["felder"].get(feld_id)
        if regel is None:
            aktionen.append({
                "feld_id": feld_id,
                "status": "offen_keine_eindeutige_zuordnung",
                "wert": None,
                "labels": [],
                "anlage": str(feld.get("anlage", "Nicht zugeordnet")),
                "abschnitt": str(feld.get("abschnitt", "Nicht zugeordnet")),
                "block_id": "nicht_zugeordnet",
                "block_titel": "Nicht zugeordnet",
                "steuerjahr": steuerjahr,
                "vergleich": "text",
            })
            continue
        modus = regel["modus"]
        status = "bereit"
        if modus == "abgleich_edaten" and not edaten_ueberschreiben:
            status = "nur_edaten_abgleich"
        aktionen.append({
            "feld_id": feld_id,
            "status": status,
            "modus": modus,
            "wert": str(feld.get("wert", "")),
            "labels": list(regel["labels"]),
            "anlage": str(feld.get("anlage", "Nicht zugeordnet")),
            "abschnitt": str(feld.get("abschnitt", "Nicht zugeordnet")),
            "block_id": blockzuordnung[feld_id]["id"],
            "block_titel": blockzuordnung[feld_id]["titel"],
            "steuerjahr": steuerjahr,
            "vergleich": regel.get("vergleich", "text"),
        })
    return aktionen


def pruefe_portalkontext(url: str, sichtbarer_text: str, mapping: dict | None = None) -> list[str]:
    mapping = lade_browser_mapping() if mapping is None else mapping
    fehler = []
    adresse = urlparse(url)
    if adresse.scheme != "https" or (adresse.hostname or "").lower() not in mapping["portal_hosts"]:
        fehler.append("Die geöffnete Seite gehört nicht zum freigegebenen ELSTER-Portal.")
    erlaubte_pfade = [str(pfad) for pfad in mapping.get("portal_pfad_praefixe", [])]
    if not erlaubte_pfade or not any(adresse.path.startswith(pfad) for pfad in erlaubte_pfade):
        fehler.append("Der geöffnete ELSTER-Pfad ist nicht für die Automatisierung freigegeben.")
    text = sichtbarer_text.casefold()
    for merkmal in mapping["formular_merkmale"]:
        if str(merkmal).casefold() not in text:
            fehler.append(f"Formularmerkmal fehlt: {merkmal}")
    return fehler


def pruefe_entwurfkontext(url: str, sichtbarer_text: str, mapping: dict | None = None) -> list[str]:
    """Akzeptiert ausschließlich einen erkennbaren, noch nicht abgegebenen Entwurf."""
    mapping = lade_browser_mapping() if mapping is None else mapping
    fehler = pruefe_portalkontext(url, sichtbarer_text, mapping)
    text = sichtbarer_text.casefold()
    merkmale = [str(wert).casefold() for wert in mapping.get("entwurf_merkmale_eines_davon", [])]
    if not merkmale or not any(merkmal in text for merkmal in merkmale):
        fehler.append("Die geöffnete Erklärung ist nicht eindeutig als Entwurf erkennbar.")
    if any(
        merkmal in text
        for merkmal in ("erfolgreich übermittelt", "übermittelte formulare", "abgegeben am")
    ):
        fehler.append("Eine bereits übermittelte Erklärung darf nicht automatisiert bearbeitet werden.")
    return fehler


def _locator_vertragsfehler(locator, mapping: dict | None = None) -> list[str]:
    layout = (mapping or {}).get("layout_vertrag", {})
    erlaubte_tags = set(layout.get("erlaubte_tags", ["input", "textarea"]))
    verbotene_typen = set(layout.get("verbotene_input_typen", VERBOTENE_INPUT_TYPEN))
    fehler = []
    try:
        if not locator.is_visible() or not locator.is_enabled():
            fehler.append("Zielfeld ist nicht sichtbar oder deaktiviert.")
        tag = locator.evaluate("element => element.tagName.toLowerCase()")
        typ = (locator.get_attribute("type") or "text").lower()
        if tag not in erlaubte_tags:
            fehler.append(f"Unerwarteter HTML-Feldtyp: {tag}.")
        if typ in verbotene_typen:
            fehler.append(f"Nicht erlaubter Eingabetyp: {typ}.")
        if locator.get_attribute("readonly") is not None:
            fehler.append("Zielfeld ist schreibgeschützt.")
    except Exception:
        fehler.append("DOM-Vertrag des Zielfelds konnte nicht geprüft werden.")
    return fehler


def _ist_befuellen_erlaubt(locator, mapping: dict | None = None) -> bool:
    return not _locator_vertragsfehler(locator, mapping)


def _finde_eindeutiges_feld(page, labels: list[str], mapping: dict | None = None):
    for label in labels:
        kandidaten = page.get_by_label(label, exact=False)
        passend = [
            kandidaten.nth(index)
            for index in range(kandidaten.count())
            if _ist_befuellen_erlaubt(kandidaten.nth(index), mapping)
        ]
        if len(passend) == 1:
            return passend[0], label
        if len(passend) > 1:
            return None, f"mehrdeutig:{label}"
    return None, None


def pruefe_interaktionsschranke(
    page,
    aktion: dict,
    sicherheitskontext: dict,
) -> tuple[object | None, str | None, list[str]]:
    """Prüft Version, Portal, Entwurfsstatus und DOM-Vertrag direkt vor einem fill()."""
    mapping, fehler = pruefe_versionsschranke(sicherheitskontext)
    if mapping is None:
        return None, None, fehler
    try:
        sichtbarer_text = page.locator("body").inner_text()
    except Exception:
        return None, None, fehler + ["Der sichtbare Formularinhalt ist nicht mehr lesbar."]
    fehler.extend(pruefe_entwurfkontext(page.url, sichtbarer_text, mapping))
    feld_id = str(aktion.get("feld_id", ""))
    regel = mapping.get("felder", {}).get(feld_id)
    if regel is None:
        fehler.append(f"Unbekanntes Zielfeld im Aktionsplan: {feld_id or '<leer>'}.")
        return None, None, fehler
    if (
        regel.get("modus") != aktion.get("modus")
        or regel.get("vergleich", "text") != aktion.get("vergleich", "text")
        or list(regel.get("labels", [])) != list(aktion.get("labels", []))
    ):
        fehler.append(f"Feldvertrag wurde während des Laufs verändert: {feld_id}.")
        return None, None, fehler
    locator, label = _finde_eindeutiges_feld(page, aktion["labels"], mapping)
    if locator is None:
        art = "mehrdeutig" if label and label.startswith("mehrdeutig:") else "nicht gefunden"
        fehler.append(f"Layoutabweichung bei {feld_id}: Zielfeld {art}.")
        return None, label, fehler
    fehler.extend(_locator_vertragsfehler(locator, mapping))
    return locator, label, fehler


def pruefe_abschnittsschranke(
    page,
    gruppe: dict,
    sicherheitskontext: dict,
) -> tuple[dict | None, list[str]]:
    """Prüft den vollständigen logischen Block vor und nach seiner Bearbeitung."""
    mapping, fehler = pruefe_versionsschranke(sicherheitskontext)
    if mapping is None:
        return None, fehler
    try:
        sichtbarer_text = page.locator("body").inner_text()
    except Exception:
        return None, fehler + ["Der sichtbare Formularinhalt ist nicht mehr lesbar."]
    fehler.extend(pruefe_entwurfkontext(page.url, sichtbarer_text, mapping))
    block_id = str(gruppe.get("block_id", ""))
    bloecke = {
        str(block["id"]): block
        for block in mapping.get("abschnittsbloecke", [])
    }
    block = bloecke.get(block_id)
    if block is None:
        fehler.append(f"Unbekannter oder nicht freigegebener Abschnittsblock: {block_id!r}.")
        return mapping, fehler
    if str(gruppe.get("block_titel", "")) != str(block["titel"]):
        fehler.append(f"Titelvertrag des Abschnittsblocks {block_id} wurde verändert.")
    erlaubte_felder = set(block["felder"])
    for aktion in gruppe.get("aktionen", []):
        feld_id = str(aktion.get("feld_id", ""))
        if aktion.get("block_id") != block_id or feld_id not in erlaubte_felder:
            fehler.append(
                f"{feld_id or '<leer>'}: Feld gehört nicht zum freigegebenen Block {block_id}."
            )
    return mapping, fehler


def _wert_hash(wert: object, _vergleich: str) -> str:
    # Freigabeschranke: keine Normalisierung, Rundung oder Formatkorrektur.
    # Der vom DOM gelieferte String muss Byte für Byte dem lokalen Sollwert entsprechen.
    typname = type(wert).__name__
    exakt = "" if wert is None else str(wert)
    return sha256(f"{typname}\0{exakt}".encode("utf-8")).hexdigest()


def _werte_bitgenau_gleich(soll: object, ist: object) -> bool:
    if not isinstance(soll, str) or not isinstance(ist, str):
        return False
    return soll.encode("utf-8") == ist.encode("utf-8")


def gruppiere_aktionsplan(aktionen: list[dict]) -> list[dict]:
    gruppen: OrderedDict[tuple[str, str], dict] = OrderedDict()
    for aktion in aktionen:
        block_id = str(aktion.get("block_id") or "")
        block_titel = str(aktion.get("block_titel") or "")
        anlage = str(aktion.get("anlage") or "Nicht zugeordnet")
        abschnitt = str(aktion.get("abschnitt") or "Nicht zugeordnet")
        if not block_id:
            block_id = f"formular:{anlage}:{abschnitt}"
            block_titel = f"{anlage} – {abschnitt}"
        schluessel = (block_id, block_titel)
        gruppe = gruppen.setdefault(schluessel, {
            "block_id": block_id,
            "block_titel": block_titel,
            "anlage": anlage,
            "abschnitt": abschnitt,
            "aktionen": [],
        })
        gruppe["aktionen"].append(aktion)
    return list(gruppen.values())


def pruefe_aktionsplan_vor_lauf(aktionen: list[dict]) -> list[str]:
    fehler = []
    aktionsjahre = {
        str(aktion.get("steuerjahr"))
        for aktion in aktionen
        if aktion.get("steuerjahr") is not None
    }
    if len(aktionsjahre) > 1:
        fehler.append("Der Aktionsplan vermischt mehrere Steuerjahre.")
    elif aktionsjahre and next(iter(aktionsjahre)) not in UNTERSTUETZTE_STEUERJAHRE:
        fehler.append("Der Aktionsplan enthält ein nicht unterstütztes Steuerjahr.")
    feld_ids = [str(aktion.get("feld_id", "")).strip() for aktion in aktionen]
    feld_id_haeufigkeit = Counter(feld_ids)
    doppelte_feld_ids = {
        feld_id for feld_id, anzahl in feld_id_haeufigkeit.items() if feld_id and anzahl > 1
    }
    for feld_id in sorted(doppelte_feld_ids):
        fehler.append(f"{feld_id}: Feld kommt mehrfach im Aktionsplan vor.")
    for aktion in aktionen:
        feld_id = str(aktion.get("feld_id", "")).strip()
        status = str(aktion.get("status", ""))
        if not feld_id:
            fehler.append("Leere lokale Feld-ID im Aktionsplan.")
        elif status.startswith("offen"):
            fehler.append(f"{feld_id}: unbekanntes oder nicht freigegebenes Feld.")
        elif status not in {"bereit", "nur_edaten_abgleich"}:
            fehler.append(f"{feld_id}: unbekannter Aktionsstatus {status!r}.")
        elif status == "bereit" and not isinstance(aktion.get("wert"), str):
            fehler.append(
                f"{feld_id}: Sollwert muss ein String sein, ist aber "
                f"{type(aktion.get('wert')).__name__}."
            )
    return fehler


def fuelle_aktionsplan(
    page,
    aktionen: list[dict],
    wirklich_ausfuellen: bool,
    sicherheitskontext: dict | None = None,
) -> dict:
    ergebnisse = []
    abschnittsberichte = []
    abgebrochen = False
    abbruchgrund = None
    if wirklich_ausfuellen and sicherheitskontext is None:
        # Auch direkte interne Aufrufe dürfen die Schranken nicht umgehen.
        aktionsjahre = {
            str(aktion.get("steuerjahr"))
            for aktion in aktionen
            if aktion.get("steuerjahr") is not None
        }
        steuerjahr = next(iter(aktionsjahre)) if len(aktionsjahre) == 1 else "2025"
        sicherheitskontext = erstelle_sicherheitskontext(lade_browser_mapping(steuerjahr))
    gruppen = gruppiere_aktionsplan(aktionen)
    feld_id_haeufigkeit = Counter(
        str(aktion.get("feld_id", "")).strip() for aktion in aktionen
    )

    # Kein partieller Lauf: unbekannte oder schon als offen markierte Eingaben
    # sperren den gesamten Plan, bevor das erste Browserfeld berührt wird.
    offene_aktionen = [
        aktion
        for aktion in aktionen
        if not str(aktion.get("feld_id", "")).strip()
        or feld_id_haeufigkeit[str(aktion.get("feld_id", "")).strip()] > 1
        or (
            str(aktion.get("status", "")) == "bereit"
            and not isinstance(aktion.get("wert"), str)
        )
        or str(aktion.get("status", "")).startswith("offen")
        or str(aktion.get("status", "")) not in {"bereit", "nur_edaten_abgleich"}
    ]
    if offene_aktionen:
        offene_ids = {id(aktion) for aktion in offene_aktionen}
        for gruppe in gruppen:
            gruppe_hat_offenes_feld = False
            for aktion in gruppe["aktionen"]:
                if id(aktion) in offene_ids:
                    feld_id = str(aktion.get("feld_id", "")).strip()
                    ist_doppelt = feld_id_haeufigkeit[feld_id] > 1
                    status = (
                        "offen_doppelte_feld_id"
                        if ist_doppelt
                        else (
                            "offen_datentyp_mismatch"
                            if str(aktion.get("status", "")) == "bereit"
                            and not isinstance(aktion.get("wert"), str)
                            else str(aktion.get("status") or "offen_unbekanntes_feld")
                        )
                    )
                    gruppe_hat_offenes_feld = True
                elif aktion.get("status") == "bereit":
                    status = "blockiert_vor_interaktion"
                else:
                    status = str(aktion.get("status", "blockiert_vor_interaktion"))
                ergebnisse.append({"feld_id": aktion.get("feld_id", ""), "status": status})
            abschnittsberichte.append({
                "block_id": gruppe["block_id"],
                "block_titel": gruppe["block_titel"],
                "anlage": gruppe["anlage"],
                "abschnitt": gruppe["abschnitt"],
                "status": "fehlgeschlagen" if gruppe_hat_offenes_feld else "blockiert_vor_interaktion",
                "vorpruefung": "fehlgeschlagen" if gruppe_hat_offenes_feld else "nicht_ausgefuehrt",
                "nachpruefung": "nicht_ausgefuehrt",
                "felder": len(gruppe["aktionen"]),
            })
        return {
            "format": "steuer-assistent-mein-elster-autofill-bericht/v1",
            "ausgefuehrt": wirklich_ausfuellen,
            "versendet": False,
            "bestanden": False,
            "abgebrochen": True,
            "abbruchgrund": "unbekannte_oder_offene_felder_vor_interaktion",
            "manuelle_pruefung_erforderlich": True,
            "abschnitte": abschnittsberichte,
            "ergebnisse": ergebnisse,
        }

    for gruppe in gruppen:
        if abgebrochen:
            for aktion in gruppe["aktionen"]:
                ergebnisse.append({
                    "feld_id": aktion["feld_id"],
                    "status": "blockiert_nach_abweichung",
                })
            abschnittsberichte.append({
                "block_id": gruppe["block_id"],
                "block_titel": gruppe["block_titel"],
                "anlage": gruppe["anlage"],
                "abschnitt": gruppe["abschnitt"],
                "status": "blockiert_nach_abweichung",
                "vorpruefung": "nicht_ausgefuehrt",
                "nachpruefung": "nicht_ausgefuehrt",
            })
            continue

        abschnitt_ergebnisse = []
        vorbereitet = []
        preflight_fehlgeschlagen = False
        blockbericht = {
            "block_id": gruppe["block_id"],
            "block_titel": gruppe["block_titel"],
            "anlage": gruppe["anlage"],
            "abschnitt": gruppe["abschnitt"],
            "vorpruefung": "nicht_aktiv",
            "nachpruefung": "nicht_ausgefuehrt",
            "felder": len(gruppe["aktionen"]),
        }
        if sicherheitskontext is not None:
            _mapping, blockfehler = pruefe_abschnittsschranke(
                page,
                gruppe,
                sicherheitskontext,
            )
            if blockfehler:
                blockbericht["vorpruefung"] = "fehlgeschlagen"
                blockbericht["status"] = "fehlgeschlagen"
                blockbericht["schrankenfehler"] = blockfehler
                for aktion in gruppe["aktionen"]:
                    ergebnis = {
                        "feld_id": aktion["feld_id"],
                        "status": "blockiert_vor_interaktion",
                    }
                    ergebnisse.append(ergebnis)
                    abschnitt_ergebnisse.append(ergebnis)
                abschnittsberichte.append(blockbericht)
                abgebrochen = True
                abbruchgrund = "abschnitt_vorpruefung_fehlgeschlagen"
                continue
            blockbericht["vorpruefung"] = "bestanden"

        for aktion in gruppe["aktionen"]:
            basis = {"feld_id": aktion["feld_id"], "status": aktion["status"]}
            if aktion["status"] != "bereit":
                ergebnisse.append(basis)
                abschnitt_ergebnisse.append(basis)
                continue
            if sicherheitskontext is not None:
                locator, label, schrankenfehler = pruefe_interaktionsschranke(
                    page,
                    aktion,
                    sicherheitskontext,
                )
            else:
                locator, label = _finde_eindeutiges_feld(page, aktion["labels"])
                schrankenfehler = []
            if locator is None or schrankenfehler:
                if schrankenfehler:
                    basis["status"] = "layout_oder_versionsabweichung"
                    basis["schrankenfehler"] = schrankenfehler
                else:
                    basis["status"] = (
                        "offen_mehrdeutig"
                        if label and label.startswith("mehrdeutig:")
                        else "offen_nicht_gefunden"
                    )
                preflight_fehlgeschlagen = True
                ergebnisse.append(basis)
                abschnitt_ergebnisse.append(basis)
                continue
            basis["status"] = "vorbereitet"
            basis["erkannte_bezeichnung"] = label
            ergebnisse.append(basis)
            abschnitt_ergebnisse.append(basis)
            vorbereitet.append((basis, locator, aktion))

        if preflight_fehlgeschlagen:
            for basis, _locator, _aktion in vorbereitet:
                basis["status"] = "blockiert_vor_interaktion"
            abgebrochen = True
            abbruchgrund = "feld_preflight_fehlgeschlagen"
            blockbericht["nachpruefung"] = "nicht_ausgefuehrt"
        elif wirklich_ausfuellen:
            for index, (basis, locator, aktion) in enumerate(vorbereitet):
                if sicherheitskontext is not None:
                    locator, label, schrankenfehler = pruefe_interaktionsschranke(
                        page,
                        aktion,
                        sicherheitskontext,
                    )
                    if locator is None or schrankenfehler:
                        basis["status"] = "layout_oder_versionsabweichung"
                        basis["schrankenfehler"] = schrankenfehler
                        for restbasis, _restlocator, _restaktion in vorbereitet[index + 1:]:
                            restbasis["status"] = "blockiert_nach_abweichung"
                        abgebrochen = True
                        abbruchgrund = "interaktionsschranke_fehlgeschlagen"
                        break
                    basis["erkannte_bezeichnung"] = label
                # Ausschließlich Formularwerte setzen: kein click(), press(), submit() oder goto().
                locator.fill(aktion["wert"])
                locator.evaluate("element => element.blur()")
                basis["status"] = "ausgefuellt"
                vergleich = str(aktion.get("vergleich", "text"))
                basis["vergleichsart"] = "bitgenau_utf8"
                basis["soll_sha256"] = _wert_hash(aktion["wert"], vergleich)
                try:
                    ist_wert = locator.input_value()
                except Exception:
                    basis["status"] = "offen_ruecklesen_fehlgeschlagen"
                    basis["vergleich_status"] = "fehlgeschlagen"
                    for restbasis, _restlocator, _restaktion in vorbereitet[index + 1:]:
                        restbasis["status"] = "blockiert_nach_abweichung"
                    abgebrochen = True
                    abbruchgrund = "readback_fehlgeschlagen"
                    break
                basis["ist_sha256"] = _wert_hash(ist_wert, vergleich)
                if not _werte_bitgenau_gleich(aktion["wert"], ist_wert):
                    basis["status"] = "abweichung_soll_ist"
                    basis["vergleich_status"] = "fehlgeschlagen"
                    for restbasis, _restlocator, _restaktion in vorbereitet[index + 1:]:
                        restbasis["status"] = "blockiert_nach_abweichung"
                    abgebrochen = True
                    abbruchgrund = "bitgenauer_soll_ist_mismatch"
                    break
                basis["vergleich_status"] = "bestanden"

            # Strikte Nachprüfung des gesamten Blocks. Ein Fehler beendet den Lauf;
            # bereits gesetzte Werte werden aus Sicherheitsgründen nicht automatisch korrigiert.
            if not abgebrochen and sicherheitskontext is not None:
                _mapping, blockfehler = pruefe_abschnittsschranke(
                    page,
                    gruppe,
                    sicherheitskontext,
                )
                if blockfehler:
                    blockbericht["schrankenfehler"] = blockfehler
                    abgebrochen = True
                    abbruchgrund = "abschnitt_nachpruefung_fehlgeschlagen"
                else:
                    for basis, _locator, aktion in vorbereitet:
                        locator, _label, schrankenfehler = pruefe_interaktionsschranke(
                            page,
                            aktion,
                            sicherheitskontext,
                        )
                        if locator is None or schrankenfehler:
                            basis["status"] = "layout_oder_versionsabweichung"
                            basis["schrankenfehler"] = schrankenfehler
                            abgebrochen = True
                            abbruchgrund = "abschnitt_nachpruefung_fehlgeschlagen"
                            break
                        try:
                            ist_wert = locator.input_value()
                        except Exception:
                            basis["status"] = "offen_ruecklesen_fehlgeschlagen"
                            basis["vergleich_status"] = "fehlgeschlagen"
                            abgebrochen = True
                            abbruchgrund = "readback_fehlgeschlagen"
                            break
                        vergleich = str(aktion.get("vergleich", "text"))
                        basis["ist_sha256"] = _wert_hash(ist_wert, vergleich)
                        if not _werte_bitgenau_gleich(aktion["wert"], ist_wert):
                            basis["status"] = "abweichung_soll_ist"
                            basis["vergleich_status"] = "fehlgeschlagen"
                            abgebrochen = True
                            abbruchgrund = "bitgenauer_soll_ist_mismatch"
                            break
                blockbericht["nachpruefung"] = "fehlgeschlagen" if abgebrochen else "bestanden"
            elif abgebrochen:
                blockbericht["nachpruefung"] = "fehlgeschlagen"
            else:
                blockbericht["nachpruefung"] = "bestanden"
        else:
            for basis, _locator, _aktion in vorbereitet:
                basis["status"] = "trockenlauf_gefunden"
            blockbericht["nachpruefung"] = "nicht_erforderlich"

        hat_fehler = any(
            eintrag["status"].startswith("offen")
            or eintrag["status"].startswith("layout_")
            or eintrag["status"].startswith("blockiert_")
            or eintrag["status"] == "abweichung_soll_ist"
            for eintrag in abschnitt_ergebnisse
        )
        blockbericht["status"] = "fehlgeschlagen" if hat_fehler or abgebrochen else "bestanden"
        abschnittsberichte.append(blockbericht)
        if hat_fehler or abgebrochen:
            abgebrochen = True
    bericht = {
        "format": "steuer-assistent-mein-elster-autofill-bericht/v1",
        "ausgefuehrt": wirklich_ausfuellen,
        "versendet": False,
        "bestanden": not abgebrochen,
        "abgebrochen": abgebrochen,
        "manuelle_pruefung_erforderlich": abgebrochen,
        "abschnitte": abschnittsberichte,
        "ergebnisse": ergebnisse,
    }
    if abbruchgrund:
        bericht["abbruchgrund"] = abbruchgrund
    return bericht


def fuelle_abschnittsweise_interaktiv(
    kontext,
    aktionen: list[dict],
    mapping: dict,
    wirklich_ausfuellen: bool,
) -> dict:
    """Lässt den Nutzer navigieren und gibt jeden Abschnitt erst nach Rücklesen frei."""
    gesamt = {
        "format": "steuer-assistent-mein-elster-autofill-bericht/v1",
        "ausgefuehrt": wirklich_ausfuellen,
        "versendet": False,
        "bestanden": True,
        "abgebrochen": False,
        "manuelle_pruefung_erforderlich": False,
        "abschnitte": [],
        "ergebnisse": [],
    }
    sicherheitskontext = erstelle_sicherheitskontext(mapping)
    gruppen = gruppiere_aktionsplan(aktionen)
    for nummer, gruppe in enumerate(gruppen, start=1):
        print(
            f"Block {nummer}/{len(gruppen)}: {gruppe['block_titel']}. "
            "Öffne diesen Abschnitt in Mein ELSTER und drücke hier die Eingabetaste."
        )
        input()
        seite = kontext.pages[-1]
        fehler = pruefe_entwurfkontext(seite.url, seite.locator("body").inner_text(), mapping)
        if fehler:
            raise RuntimeError("Autofill abgebrochen: " + "; ".join(fehler))
        teilbericht = fuelle_aktionsplan(
            seite,
            gruppe["aktionen"],
            wirklich_ausfuellen,
            sicherheitskontext=sicherheitskontext,
        )
        gesamt["abschnitte"].extend(teilbericht["abschnitte"])
        gesamt["ergebnisse"].extend(teilbericht["ergebnisse"])
        if teilbericht["abgebrochen"]:
            gesamt["bestanden"] = False
            gesamt["abgebrochen"] = True
            gesamt["manuelle_pruefung_erforderlich"] = True
            gesamt["abbruchgrund"] = teilbericht.get("abbruchgrund", "unbekannte_abweichung")
            for restgruppe in gruppen[nummer:]:
                gesamt["abschnitte"].append({
                    "block_id": restgruppe["block_id"],
                    "block_titel": restgruppe["block_titel"],
                    "anlage": restgruppe["anlage"],
                    "abschnitt": restgruppe["abschnitt"],
                    "status": "blockiert_nach_abweichung",
                    "vorpruefung": "nicht_ausgefuehrt",
                    "nachpruefung": "nicht_ausgefuehrt",
                })
                gesamt["ergebnisse"].extend(
                    {
                        "feld_id": aktion["feld_id"],
                        "status": "blockiert_nach_abweichung",
                    }
                    for aktion in restgruppe["aktionen"]
                )
            print(
                "HARD STOP: Blockprüfung oder bitgenauer Soll-Ist-Abgleich fehlgeschlagen. "
                "Keine automatische Korrektur; manuelle Prüfung erforderlich."
            )
            break
        print("Vorprüfung, bitgenaues Readback und Nachprüfung für diesen Block bestanden.")
    return gesamt


def _bericht_speichern(bericht: dict, eingabehilfe: dict) -> Path:
    zeit = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    ziel = ROOT / "logs" / f"mein_elster_autofill_{zeit}.json"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    anonym = {
        **bericht,
        "steuerjahr": eingabehilfe["steuerjahr"],
        "eingabe_sha256": sha256(
            json.dumps(eingabehilfe, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
    }
    ziel.write_text(json.dumps(anonym, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ziel


def browserlauf(
    eingabe_pfad: str | Path,
    wirklich_ausfuellen: bool = False,
    edaten_ueberschreiben: bool = False,
) -> int:
    eingabehilfe = lade_eingabehilfe(eingabe_pfad)
    steuerjahr = str(eingabehilfe["steuerjahr"])
    mapping = lade_browser_mapping(steuerjahr)
    if wirklich_ausfuellen and mapping["freigabe"].get("live_layout_validiert") is not True:
        raise RuntimeError(
            f"ESt {steuerjahr} ist nur für die lokale Sandbox validiert. "
            "Ein echter Fülllauf bleibt bis zum bestandenen Live-Layoutaudit gesperrt."
        )
    aktionen = erstelle_aktionsplan(eingabehilfe, edaten_ueberschreiben, mapping)
    aktionsplan_fehler = pruefe_aktionsplan_vor_lauf(aktionen)
    if aktionsplan_fehler:
        raise ValueError(
            "Browserlauf vor der ersten Interaktion gesperrt: "
            + "; ".join(aktionsplan_fehler)
        )

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=False)
        kontext = browser.new_context(locale="de-DE")
        seite = kontext.new_page()
        seite.goto(START_URL, wait_until="domcontentloaded")
        print(
            "Melde dich selbst bei Mein ELSTER an, lege einen neuen Entwurf der "
            f"Einkommensteuererklärung {steuerjahr} an und öffne ihn. Drücke danach hier "
            "die Eingabetaste."
        )
        input()
        # Falls ELSTER das Formular in einem neuen Tab geöffnet hat, wird nur
        # der zuletzt geöffnete Tab verwendet; fremde Hosts bleiben gesperrt.
        seite = kontext.pages[-1]
        fehler = pruefe_entwurfkontext(
            seite.url,
            seite.locator("body").inner_text(),
            mapping,
        )
        if fehler:
            raise RuntimeError("Autofill abgebrochen: " + "; ".join(fehler))
        bericht = fuelle_abschnittsweise_interaktiv(
            kontext,
            aktionen,
            mapping,
            wirklich_ausfuellen,
        )
        bericht_pfad = _bericht_speichern(bericht, eingabehilfe)
        ausgefuellt = sum(e["status"] == "ausgefuellt" for e in bericht["ergebnisse"])
        offen = sum(e["status"].startswith("offen") for e in bericht["ergebnisse"])
        print(f"Autofill abgeschlossen: {ausgefuellt} ausgefüllt, {offen} offen.")
        if bericht["abgebrochen"]:
            print("Der Lauf wurde wegen einer Abweichung vor dem nächsten Abschnitt gesperrt.")
        print(f"Bericht ohne Steuerwerte: {bericht_pfad}")
        print("Kontrolliere alle Angaben selbst. Das Skript übermittelt keine Erklärung.")
        print("Der Browser bleibt für deine Prüfung geöffnet; schließe ihn zum Beenden.")
        try:
            seite.wait_for_event("close", timeout=0)
        finally:
            browser.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eingabe", required=True, type=Path, help="JSON aus der ELSTER-Eingabehilfe.")
    parser.add_argument(
        "--ausfuellen",
        action="store_true",
        help="Füllt gefundene Felder; ohne Option läuft nur die Zuordnungsprüfung.",
    )
    parser.add_argument(
        "--edaten-ueberschreiben",
        action="store_true",
        help="Erlaubt bestätigte eDaten-Felder; standardmäßig werden sie nur abgeglichen.",
    )
    args = parser.parse_args()
    return browserlauf(args.eingabe, args.ausfuellen, args.edaten_ueberschreiben)


if __name__ == "__main__":
    raise SystemExit(main())
