"""Sicherer, strukturierter Kontext des aktiven Steuerfalls für den Dialog.

Lokale Falldaten und amtliche Rechtsquellen bleiben getrennte Evidenzarten.
Dieses Modul übernimmt deshalb nur begrenzte strukturierte Felder, niemals
Dateipfade oder Dokumentrohtext.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re
from typing import Iterable


FINANZPOSITIONEN_DATEINAME = "finanzpositionen.json"
MAX_DOKUMENTE = 40
MAX_WERTE = 120
MAX_PROMPT_ZEICHEN = 12_000

ART_BEZEICHNUNGEN = {
    "bruttoarbeitslohn": "Bruttoarbeitslohn",
    "einbehaltene_lohnsteuer": "einbehaltene Lohnsteuer",
    "lohnsteuer": "einbehaltene Lohnsteuer",
    "kranken_und_pflegeversicherung": "Kranken- und Pflegeversicherung",
    "arbeitsmittel_ausgabe": "Arbeitsmittel",
    "pendeltage": "Pendeltage",
    "homeoffice_tage": "Homeoffice-Tage",
    "steuerklasse": "Steuerklasse",
    "kinderbetreuung_zahlung": "Kinderbetreuungskosten",
    "betriebseinnahmen": "Betriebseinnahmen",
    "betriebsausgaben": "Betriebsausgaben",
    "software_rechnung": "Software-Rechnung",
    "drucker_rechnung": "Drucker-Rechnung",
    "umsatzsteuer_voranmeldung_betrag": "Umsatzsteuer-Voranmeldung",
    "inlaendische_kapitalertraege": "inländische Kapitalerträge",
    "auslaendische_ertraege_ungeklaert": "ausländische Erträge",
    "krypto_kauf": "Krypto-Kauf",
    "krypto_verkauf": "Krypto-Verkauf",
    "krypto_transaktionsgebuehr": "Krypto-Transaktionsgebühr",
    "kaltmieteinnahmen": "Jahreskaltmiete",
    "darlehenszinsen": "Darlehenszinsen",
    "grundsteuer": "Grundsteuer",
    "rentenversicherung": "Rentenversicherungsbeitrag",
    "insolvenzgeld": "Insolvenzgeld",
}

ART_ALIAS = {
    "lohnsteuer": "einbehaltene_lohnsteuer",
}

SICHERE_POSITIONSSCHLUESSEL = {
    "id",
    "steuerjahr",
    "art",
    "person",
    "betrag_eur",
    "anzahl",
    "entfernung_km_einfach",
    "datum",
    "wertart",
    "pruefstatus",
    "beleg",
    "in_summe_von",
    "monate",
    "monatsbetrag_eur",
}


def _text(wert: object, maximal: int = 180) -> str:
    return " ".join(str(wert or "").strip().split())[:maximal]


def _dateiname(wert: object, maximal: int = 200) -> str:
    """Reduziert Windows- und POSIX-Pfade auf einen unkritischen Dateinamen."""
    teile = [teil for teil in re.split(r"[\\/]", str(wert or "").strip()) if teil]
    return _text(teile[-1] if teile else "", maximal)


def _steuerjahr(wert: object) -> str:
    roh = str(wert or "").strip()
    return roh if re.fullmatch(r"(?:19|20)\d{2}", roh) else ""


def _sichere_quelle(wert: object, maximal: int = 120) -> str:
    roh = str(wert or "").strip()
    if "/" in roh or "\\" in roh:
        return _dateiname(roh, maximal)
    return _text(roh, maximal)


def _status(wert: object, *, standard: str = "offen") -> str:
    roh = _text(wert, 80).casefold().replace(" ", "_")
    if roh in {"bestätigt", "bestaetigt", "geprüft", "geprueft"}:
        return "bestätigt"
    if roh in {"zu_prüfen", "zu_pruefen", "unklar", "erkannt", ""}:
        return standard
    return roh


def _betrag_deutsch(wert: object) -> str:
    try:
        betrag = Decimal(str(wert).replace("€", "").replace(" ", "").replace(".", "").replace(",", "."))
        # JSON-Finanzpositionen verwenden einen Dezimalpunkt statt Tausenderpunkten.
        if re.fullmatch(r"-?\d+\.\d{1,2}", str(wert).strip()):
            betrag = Decimal(str(wert).strip())
    except (InvalidOperation, ValueError):
        return _text(wert)
    return f"{betrag:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " Euro"


def _zahl_aus_betrag(wert: dict) -> Decimal | None:
    return _normalisierte_zahl(wert.get("betrag_eur", ""))


def _normalisierte_zahl(wert: object) -> Decimal | None:
    roh = str(wert or "").strip().replace("\u00a0", "").replace(" ", "")
    roh = roh.replace("€", "").replace("EUR", "").replace("Euro", "")
    if not roh:
        return None
    if "," in roh and "." in roh:
        if roh.rfind(",") > roh.rfind("."):
            roh = roh.replace(".", "").replace(",", ".")
        else:
            roh = roh.replace(",", "")
    elif "," in roh:
        roh = roh.replace(",", ".")
    try:
        return Decimal(roh)
    except InvalidOperation:
        return None


def lade_finanzpositionen(datei: Path, steuerjahr: str) -> list[dict]:
    """Lädt nur die allgemeinen Positionen eines Jahres aus einem Nutzerordner."""
    zieljahr = _steuerjahr(steuerjahr)
    if not zieljahr:
        return []
    try:
        daten = json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return []
    positionen = daten.get("positionen", []) if isinstance(daten, dict) else []
    ergebnis = []
    for position in positionen:
        if not isinstance(position, dict):
            continue
        jahr = _steuerjahr(position.get("steuerjahr"))
        if jahr != zieljahr:
            continue
        if not _text(position.get("id")) or not _text(position.get("art")):
            continue
        ergebnis.append(
            {
                schluessel: position[schluessel]
                for schluessel in SICHERE_POSITIONSSCHLUESSEL
                if schluessel in position
            }
        )
    return ergebnis


def _dokumentindex(dokumente: Iterable[dict]) -> dict[str, dict]:
    ergebnis: dict[str, dict] = {}
    for dokument in dokumente:
        if not isinstance(dokument, dict):
            continue
        roh = _text(dokument.get("dateiname"), 500)
        name = _dateiname(roh)
        if roh:
            ergebnis[roh] = dokument
        if name:
            ergebnis[name] = dokument
    return ergebnis


def _profilmerkmale(profil: dict) -> dict:
    person = profil.get("person", {}) if isinstance(profil.get("person"), dict) else {}
    objekt = (
        profil.get("grundabgaben_standardobjekt", {})
        if isinstance(profil.get("grundabgaben_standardobjekt"), dict)
        else {}
    )
    steuererklaerung = (
        profil.get("steuererklaerung", {})
        if isinstance(profil.get("steuererklaerung"), dict)
        else {}
    )
    return {
        "angestellter": person.get("angestellter") is True,
        "hausbesitzer": person.get("hausbesitzer") is True,
        "wohnt_im_standardobjekt": person.get("wohnt_im_standardobjekt") is True,
        "gebaeudeart": _text(objekt.get("gebaeudeart"), 80),
        "nutzung": _text(objekt.get("nutzung"), 80),
        "steuerfall_status": _text(steuererklaerung.get("status"), 80),
    }


def _finanzwert(position: dict, dokumente: dict[str, dict], steuerjahr: str) -> dict:
    beleg_roh = _text(position.get("beleg"), 500)
    beleg = _dateiname(beleg_roh)
    dokument = dokumente.get(beleg_roh, dokumente.get(beleg, {}))
    art = ART_ALIAS.get(_text(position.get("art"), 100), _text(position.get("art"), 100))
    ergebnis = {
        "id": _text(position.get("id"), 120),
        "art": art,
        "bezeichnung": ART_BEZEICHNUNGEN.get(art, art.replace("_", " ").capitalize()),
        "steuerjahr": _steuerjahr(position.get("steuerjahr")),
        "person": _text(position.get("person"), 100),
        "status": _status(position.get("pruefstatus"), standard="offen"),
        "herkunft": beleg,
        "dokumenttyp": _text(dokument.get("dokumenttyp"), 120),
        "wertart": _text(position.get("wertart"), 40),
    }
    for schluessel in (
        "betrag_eur",
        "anzahl",
        "entfernung_km_einfach",
        "datum",
        "in_summe_von",
        "monate",
        "monatsbetrag_eur",
    ):
        if schluessel in position:
            ergebnis[schluessel] = position[schluessel]
    return ergebnis


def _dokumentwerte(dokumente: list[dict], steuerjahr: str) -> Iterable[dict]:
    for dokument in dokumente:
        if not isinstance(dokument, dict):
            continue
        jahr = _steuerjahr(dokument.get("steuerjahr"))
        if steuerjahr and jahr != steuerjahr:
            continue
        zuordnung = dokument.get("nutzerzuordnung", {})
        if isinstance(zuordnung, dict) and zuordnung and zuordnung.get("bestaetigt") is not True:
            continue
        person = (
            _text(
                zuordnung.get("name")
                or zuordnung.get("erkannter_name")
                or zuordnung.get("aktiver_name"),
                100,
            )
            if isinstance(zuordnung, dict) and zuordnung.get("bestaetigt") is True
            else ""
        )
        for nummer, wert in enumerate(dokument.get("wertvorschlaege", []), 1):
            if not isinstance(wert, dict) or _text(wert.get("status"), 40) == "Verworfen":
                continue
            art = ART_ALIAS.get(_text(wert.get("id"), 100), _text(wert.get("id"), 100))
            if not art:
                continue
            yield {
                "id": f"{_text(dokument.get('id'), 100)}:{nummer}",
                "art": art,
                "bezeichnung": _text(wert.get("bezeichnung"), 120)
                or ART_BEZEICHNUNGEN.get(art, art.replace("_", " ").capitalize()),
                "wert": _text(wert.get("wert"), 120),
                "steuerjahr": jahr,
                "person": person,
                "status": _dokumentwert_status(wert),
                "herkunft": _dateiname(dokument.get("dateiname"), 200),
                "dokumenttyp": _text(dokument.get("dokumenttyp"), 120),
                "wertart": "dokumentwert",
            }


def _manuelle_werte(werte: list[dict], steuerjahr: str) -> Iterable[dict]:
    for wert in werte:
        if not isinstance(wert, dict) or _steuerjahr(wert.get("steuerjahr")) != steuerjahr:
            continue
        art = ART_ALIAS.get(_text(wert.get("feld_id"), 100), _text(wert.get("feld_id"), 100))
        if not art:
            continue
        yield {
            "id": _text(wert.get("id"), 120),
            "art": art,
            "bezeichnung": _text(wert.get("bezeichnung"), 120)
            or ART_BEZEICHNUNGEN.get(art, art.replace("_", " ").capitalize()),
            "wert": _text(wert.get("wert"), 120),
            "steuerjahr": steuerjahr,
            "person": "",
            "status": _status(wert.get("status")),
            "herkunft": _sichere_quelle(wert.get("quelle"), 120),
            "dokumenttyp": "Bewusste Nutzereingabe",
            "wertart": "manuelle_angabe",
        }


def _dokumentwert_status(wert: dict) -> str:
    status = _status(wert.get("status"))
    if status != "bestätigt":
        return status
    herkunft = _text(
        wert.get("bestaetigt_durch")
        or wert.get("bestaetigungsquelle")
        or wert.get("bestaetigungsart"),
        80,
    ).casefold()
    if herkunft in {"nutzer", "benutzer", "manuell", "manuell bestätigt", "manuell bestaetigt"}:
        return "bestätigt"
    return "automatisch_erkannt"


def _dedupliziere(werte: Iterable[dict]) -> list[dict]:
    def basis(wert: dict) -> tuple[str, str, str]:
        skalar = wert.get("betrag_eur", wert.get("wert", wert.get("anzahl", "")))
        zahl = _normalisierte_zahl(skalar)
        normalisiert = (
            format(zahl.normalize(), "f")
            if zahl is not None
            else _text(skalar, 120).casefold()
        )
        return (
            _text(wert.get("art"), 100).casefold(),
            normalisiert,
            _text(wert.get("herkunft"), 200).casefold(),
        )

    def gleiche_person(person_a: object, person_b: object) -> bool:
        a = _text(person_a, 100).casefold()
        b = _text(person_b, 100).casefold()
        if not a or not b or a == b:
            return True
        a_teile = set(re.findall(r"\w+", a, flags=re.UNICODE))
        b_teile = set(re.findall(r"\w+", b, flags=re.UNICODE))
        return (len(a_teile) == 1 and a_teile <= b_teile) or (
            len(b_teile) == 1 and b_teile <= a_teile
        )

    ergebnis: list[dict] = []
    for wert in werte:
        basisschluessel = basis(wert)
        person = _text(wert.get("person"), 100).casefold()
        duplikat = next(
            (
                vorhanden
                for vorhanden in ergebnis
                if basis(vorhanden) == basisschluessel
                and gleiche_person(vorhanden.get("person"), person)
            ),
            None,
        )
        if duplikat is not None:
            if not duplikat.get("person") and wert.get("person"):
                duplikat["person"] = wert["person"]
            continue
        ergebnis.append(wert)
    return ergebnis


def _dokument_gehoert_zum_fall(dokument: dict, nutzer_id: str) -> bool:
    zuordnung = dokument.get("nutzerzuordnung")
    if not isinstance(zuordnung, dict) or not zuordnung:
        return True
    if zuordnung.get("bestaetigt") is not True:
        return False
    gespeicherte_ids = {
        _text(zuordnung.get(schluessel), 120)
        for schluessel in ("nutzer_id", "aktiver_nutzer_id", "erkannter_nutzer_id")
        if _text(zuordnung.get(schluessel), 120)
    }
    if gespeicherte_ids:
        return bool(nutzer_id) and gespeicherte_ids == {nutzer_id}
    return True


def erstelle_fallkontext(
    *,
    steuerjahr: str,
    profil: dict,
    dokumente: list[dict],
    manuelle_werte: list[dict] | None = None,
    finanzpositionen: list[dict] | None = None,
    nutzer_name: str = "",
    nutzer_id: str = "",
) -> dict:
    """Erstellt einen begrenzten Kontext ohne Pfade, Rohtext oder Fremdjahre."""
    jahr = _steuerjahr(steuerjahr)
    if not jahr:
        raise ValueError("Das Steuerjahr muss vierstellig und gültig sein.")
    alle_passenden_dokumente = [
        dokument
        for dokument in dokumente
        if isinstance(dokument, dict)
        and _steuerjahr(dokument.get("steuerjahr")) == jahr
        and _dokument_gehoert_zum_fall(dokument, _text(nutzer_id, 120))
    ]
    passende_dokumente = alle_passenden_dokumente[:MAX_DOKUMENTE]
    index = _dokumentindex(passende_dokumente)
    dokumentlisten = [
        {
            "id": _text(dokument.get("id"), 100),
            "dateiname": _dateiname(dokument.get("dateiname"), 200),
            "dokumenttyp": _text(dokument.get("dokumenttyp"), 120),
            "steuerjahr": _steuerjahr(dokument.get("steuerjahr")),
            "status": _status(dokument.get("status")),
            "person": _text(
                (dokument.get("nutzerzuordnung") or {}).get("name")
                or (dokument.get("nutzerzuordnung") or {}).get("erkannter_name")
                or (dokument.get("nutzerzuordnung") or {}).get("aktiver_name"),
                100,
            )
            if isinstance(dokument.get("nutzerzuordnung"), dict)
            and (dokument.get("nutzerzuordnung") or {}).get("bestaetigt") is True
            else "",
        }
        for dokument in passende_dokumente
    ]
    finanzwerte = [
        _finanzwert(position, index, jahr)
        for position in (finanzpositionen or [])
        if isinstance(position, dict)
        and _steuerjahr(position.get("steuerjahr")) == jahr
    ]
    alle_werte = _dedupliziere(
        [
            *_manuelle_werte(manuelle_werte or [], jahr),
            *finanzwerte,
            *_dokumentwerte(passende_dokumente, jahr),
        ]
    )
    werte = alle_werte[:MAX_WERTE]
    return {
        "version": 1,
        "steuerjahr": jahr,
        "nutzer_name": _text(nutzer_name, 100),
        "profil": _profilmerkmale(profil if isinstance(profil, dict) else {}),
        "dokumente": dokumentlisten,
        "werte": werte,
        "dokumente_gesamt": len(alle_passenden_dokumente),
        "werte_gesamt": len(alle_werte),
    }


def _json_objekt_laden(datei: Path) -> dict:
    try:
        daten = json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return {}
    return daten if isinstance(daten, dict) else {}


def _dokumentregister_laden(datei: Path, eingang: Path) -> list[dict]:
    register = _json_objekt_laden(datei)
    try:
        eingang = eingang.resolve(strict=True)
    except OSError:
        return []
    nach_pfad: dict[Path, dict] = {}
    for eintrag in register.values():
        if not isinstance(eintrag, dict):
            continue
        try:
            pfad = Path(str(eintrag.get("pfad", ""))).expanduser().resolve(strict=True)
            pfad.relative_to(eingang)
        except (OSError, TypeError, ValueError):
            continue
        if not pfad.is_file():
            continue
        bisher = nach_pfad.get(pfad)
        if bisher is None:
            nach_pfad[pfad] = dict(eintrag)
            continue

        def vollstaendigkeit(kandidat: dict) -> tuple[int, str]:
            return (
                int(bool(kandidat.get("nutzerzuordnung")))
                + int(bool(kandidat.get("wertvorschlaege")))
                + int(bool(kandidat.get("notiz_angaben")))
                + int(bool(kandidat.get("manuell"))),
                str(kandidat.get("erkannt_am", "")),
            )

        if vollstaendigkeit(eintrag) > vollstaendigkeit(bisher):
            nach_pfad[pfad] = dict(eintrag)
    return sorted(
        nach_pfad.values(), key=lambda eintrag: _dateiname(eintrag.get("dateiname")).casefold()
    )


def _eingangsordner_laden(datenordner: Path, standard: Path) -> Path:
    einstellungen = _json_objekt_laden(datenordner / "einstellungen.json")
    try:
        konfiguriert = Path(str(einstellungen.get("eingangsordner", ""))).expanduser()
        if konfiguriert.is_absolute() and konfiguriert.is_dir():
            return konfiguriert.resolve(strict=True)
    except (OSError, TypeError, ValueError):
        pass
    return standard.resolve()


def lade_dialogzustand(
    *, nutzer_id: str, steuerjahr: str
) -> tuple[dict, dict, Path]:
    """Lädt Fallkontext, Vollprofil und Eingang für genau einen Request-Nutzer."""
    import nutzerverwaltung
    from manuelle_steuerwerte import DATEINAME as MANUELLE_DATEI, werte_laden

    nutzer = nutzerverwaltung.nutzer_finden(nutzer_id)
    if nutzer is None:
        raise ValueError("Dieser Nutzer wurde nicht gefunden.")
    datenordner = nutzerverwaltung.datenordner(nutzer_id)
    eingang = _eingangsordner_laden(
        datenordner, nutzerverwaltung.dokumentordner(nutzer_id) / "eingang"
    )
    profil = _json_objekt_laden(datenordner / "steuerprofil.json")
    zieljahr = _steuerjahr(steuerjahr) or _steuerjahr(
        (profil.get("steuererklaerung") or {}).get(
            "naechstes_zu_bearbeitendes_steuerjahr"
        )
        if isinstance(profil.get("steuererklaerung"), dict)
        else ""
    )
    if not zieljahr:
        raise ValueError("Für den Dialog ist kein gültiges Steuerjahr festgelegt.")
    dokumente = _dokumentregister_laden(datenordner / "dokumentregister.json", eingang)
    manuelle_werte: list[dict] = []
    finanzpositionen: list[dict] = []
    try:
        manuelle_werte = werte_laden(datenordner / MANUELLE_DATEI, zieljahr)
        finanzpositionen = lade_finanzpositionen(
            datenordner / FINANZPOSITIONEN_DATEINAME, zieljahr
        )
    except (OSError, TypeError, ValueError):
        pass
    fallkontext = erstelle_fallkontext(
        steuerjahr=zieljahr,
        profil=profil,
        dokumente=dokumente,
        manuelle_werte=manuelle_werte,
        finanzpositionen=finanzpositionen,
        nutzer_name=_text(nutzer.get("name"), 100),
        nutzer_id=nutzer_id,
    )
    return fallkontext, profil, eingang


def lade_aktiven_fallkontext(*, nutzer_id: str, steuerjahr: str) -> dict:
    """Lädt alle Falldaten ausschließlich für eine ausdrücklich gebundene Nutzer-ID."""
    fallkontext, _profil, _eingang = lade_dialogzustand(
        nutzer_id=nutzer_id, steuerjahr=steuerjahr
    )
    return fallkontext


def fallkontext_als_text(kontext: dict) -> str:
    """Serialisiert ausschließlich den bereits bereinigten Kontext für das Modell."""
    alle_werte = [wert for wert in kontext.get("werte", []) if isinstance(wert, dict)]
    alle_dokumente = [
        dokument for dokument in kontext.get("dokumente", []) if isinstance(dokument, dict)
    ]
    def gesamtzahl(schluessel: str, mindestens: int) -> int:
        try:
            return max(mindestens, int(kontext.get(schluessel, mindestens)))
        except (TypeError, ValueError):
            return mindestens

    werte_gesamt = gesamtzahl("werte_gesamt", len(alle_werte))
    dokumente_gesamt = gesamtzahl("dokumente_gesamt", len(alle_dokumente))
    payload = {
        "version": kontext.get("version", 1),
        "steuerjahr": _steuerjahr(kontext.get("steuerjahr")),
        "nutzer_name": _text(kontext.get("nutzer_name"), 100),
        "profil": kontext.get("profil", {}) if isinstance(kontext.get("profil"), dict) else {},
        "werte": [],
        "dokumente": [],
        "begrenzung": {
            "gekuerzt": False,
            "werte_gesamt": werte_gesamt,
            "werte_enthalten": 0,
            "dokumente_gesamt": dokumente_gesamt,
            "dokumente_enthalten": 0,
        },
    }

    def passt() -> bool:
        return len(json.dumps(payload, ensure_ascii=False, separators=(",", ":"))) <= MAX_PROMPT_ZEICHEN

    for wert in alle_werte:
        payload["werte"].append(wert)
        payload["begrenzung"]["werte_enthalten"] = len(payload["werte"])
        if not passt():
            payload["werte"].pop()
            payload["begrenzung"]["werte_enthalten"] = len(payload["werte"])
            break
    for dokument in alle_dokumente:
        payload["dokumente"].append(dokument)
        payload["begrenzung"]["dokumente_enthalten"] = len(payload["dokumente"])
        if not passt():
            payload["dokumente"].pop()
            payload["begrenzung"]["dokumente_enthalten"] = len(payload["dokumente"])
            break
    payload["begrenzung"]["gekuerzt"] = (
        payload["begrenzung"]["werte_enthalten"] < werte_gesamt
        or payload["begrenzung"]["dokumente_enthalten"] < dokumente_gesamt
    )
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _wertanzeige(wert: dict) -> str:
    if wert.get("betrag_eur") not in {None, ""}:
        anzeige = _betrag_deutsch(wert["betrag_eur"])
    elif wert.get("wert") not in {None, ""}:
        anzeige = _text(wert["wert"], 120).replace("€", "Euro")
    elif wert.get("anzahl") not in {None, ""}:
        anzeige = f"{wert['anzahl']} Tage"
        if wert.get("entfernung_km_einfach") not in {None, ""}:
            anzeige += f" bei {wert['entfernung_km_einfach']} km einfacher Entfernung"
    else:
        anzeige = _text(wert.get("datum"), 40) or "ohne Zahlenwert"
    person = _text(wert.get("person"), 100)
    prefix = f"{person}: " if person else ""
    status = _text(wert.get("status"), 80)
    statustext = "" if status == "bestätigt" else f"; Status: {status.replace('_', ' ')}"
    herkunft = _text(wert.get("herkunft"), 200)
    quelltext = f"; Herkunft: {herkunft}" if herkunft else ""
    bezeichnung = wert.get("bezeichnung", wert.get("art"))
    trennzeichen = " " if wert.get("art") == "steuerklasse" else ": "
    return f"{prefix}{bezeichnung}{trennzeichen}{anzeige}{statustext}{quelltext}"


def _finde(werte: list[dict], *arten: str) -> list[dict]:
    gesucht = {ART_ALIAS.get(art, art) for art in arten}
    return [wert for wert in werte if wert.get("art") in gesucht]


def _begrenzungshinweis(kontext: dict, art: str, enthalten: int) -> str:
    schluessel = "werte_gesamt" if art == "wert" else "dokumente_gesamt"
    try:
        gesamt = int(kontext.get(schluessel, enthalten))
    except (TypeError, ValueError):
        gesamt = enthalten
    rest = max(0, gesamt - enthalten)
    if not rest:
        return ""
    if art == "wert":
        bezeichnung = "1 weiterer Wert ist" if rest == 1 else f"{rest} weitere Werte sind"
    else:
        bezeichnung = "1 weitere Unterlage ist" if rest == 1 else f"{rest} weitere Unterlagen sind"
    return f" Hinweis: {bezeichnung} wegen der Kontextbegrenzung hier nicht aufgeführt."


def _enthaelt_betrag(frage: str, wert: dict) -> bool:
    betrag = _zahl_aus_betrag(wert)
    if betrag is None:
        return False
    deutsch = f"{betrag:,.0f}".replace(",", ".")
    return deutsch in frage or str(int(betrag)) in frage.replace(".", "")


def beantworte_falldatenfrage(
    frage: str, kontext: dict, verlauf: list[dict] | None = None
) -> str | None:
    """Beantwortet reine Bestandsfragen ohne künstliche amtliche Rechtsquelle."""
    text = _text(frage, 2_000).casefold()
    werte = list(kontext.get("werte", []))
    dokumente = list(kontext.get("dokumente", []))
    jahr = _steuerjahr(kontext.get("steuerjahr"))

    persoenliche_lohnfrage = any(
        signal in text
        for signal in (
            "mein bruttolohn",
            "mein bruttoarbeitslohn",
            "meinem testfall",
            "meine lohnwerte",
        )
    )
    if (
        any(begriff in text for begriff in ("bruttolohn", "bruttoarbeitslohn"))
        and persoenliche_lohnfrage
        and not _finde(werte, "bruttoarbeitslohn")
    ):
        return (
            f"Im aktiven Fall für {jahr} sind keine Bruttolohn-Daten zu dieser Person hinterlegt. "
            "Der genannte Wert gehört daher nicht zu diesem Profil und darf höchstens aus einem anderen Testfall stammen."
        )

    bestandteile = [wert for wert in werte if wert.get("wertart") == "bestandteil"]
    if any(wort in text for wort in ("addiere", "zusätzlich", "noch zu")):
        bestandteil = next((wert for wert in bestandteile if _enthaelt_betrag(frage, wert)), None)
        if bestandteil is not None:
            ziel = next(
                (wert for wert in werte if wert.get("id") == bestandteil.get("in_summe_von")),
                None,
            )
            zieltext = _betrag_deutsch(ziel["betrag_eur"]) if ziel and ziel.get("betrag_eur") else "der Jahressumme"
            return (
                f"Nein. Die {bestandteil['bezeichnung']} über {_betrag_deutsch(bestandteil['betrag_eur'])} "
                f"ist bereits Bestandteil von {zieltext} und darf nicht noch einmal addiert werden."
            )

    meldungen = [wert for wert in werte if wert.get("wertart") == "meldung"]
    if meldungen and any(wort in text for wort in ("umsatzsteuer", "voranmeldung")) and any(
        wort in text for wort in ("gewinn", "zieh", "rechne", "einrechnen")
    ):
        meldung = meldungen[0]
        return (
            f"Nein. Die {_betrag_deutsch(meldung['betrag_eur'])} aus der "
            "Umsatzsteuer-Voranmeldung sind hier nur als Meldungsbetrag hinterlegt und keine zusätzliche Gewinngröße."
        )

    if any(wort in text for wort in ("gewinn zeigen", "überschuss ergeben", "uberschuss ergeben")):
        einnahmen = _finde(werte, "betriebseinnahmen")
        ausgaben = _finde(werte, "betriebsausgaben")
        if einnahmen and ausgaben:
            if any(
                wert.get("status") != "bestätigt"
                for wert in (einnahmen[0], ausgaben[0])
            ):
                return (
                    "Eine vorläufige Differenz kann ich noch nicht berechnen, weil mindestens "
                    "eine der benötigten Jahressummen offen oder ungeklärt ist."
                )
            ein = _zahl_aus_betrag(einnahmen[0])
            aus = _zahl_aus_betrag(ausgaben[0])
            if ein is not None and aus is not None:
                return (
                    f"Aus den vorhandenen Jahressummen ergibt sich vorläufig eine Differenz von "
                    f"{_betrag_deutsch(ein - aus)}: {_betrag_deutsch(ein)} Betriebseinnahmen minus "
                    f"{_betrag_deutsch(aus)} Betriebsausgaben. Enthaltene Einzelposten und Meldungsbeträge "
                    "werden nicht erneut eingerechnet."
                )

    if "kapitalerträge" in text and "bescheinigt" in text:
        kapital = [
            wert
            for wert in _finde(werte, "inlaendische_kapitalertraege")
            if wert.get("status") == "bestätigt"
        ]
        if not kapital:
            return f"Für {jahr} sind im aktiven Profil keine Kapitalerträge als bescheinigt hinterlegt."
        wert = kapital[0]
        return (
            f"Bescheinigt sind {_betrag_deutsch(wert['betrag_eur'])} inländische Kapitalerträge. "
            f"Herkunft: {wert.get('herkunft') or 'lokale Kapitalertragsteuerbescheinigung'} "
            f"({wert.get('dokumenttyp') or 'Kapitalertragsteuerbescheinigung'})."
        )

    fragt_nach_vorhandenen_lohnwerten = "lohnwerte" in text and (
        ("welche" in text and "hast du" in text)
        or any(signal in text for signal in ("vorhandene lohnwerte", "meine lohnwerte", "lohnwerte hinterlegt"))
    )
    if fragt_nach_vorhandenen_lohnwerten:
        lohnwerte = _finde(
            werte, "bruttoarbeitslohn", "einbehaltene_lohnsteuer", "steuerklasse"
        )
        if lohnwerte:
            return (
                "Vorhandene Lohnwerte: "
                + "; ".join(_wertanzeige(wert) for wert in lohnwerte)
                + "."
                + _begrenzungshinweis(kontext, "wert", len(werte))
            )

    if "vermietung" in text and "beträge" in text:
        miete = _finde(werte, "kaltmieteinnahmen")
        zinsen = _finde(werte, "darlehenszinsen")
        grundsteuer = _finde(werte, "grundsteuer")
        if miete:
            beteiligte = [*miete[:1], *zinsen[:1], *grundsteuer[:1]]
            if any(wert.get("status") != "bestätigt" for wert in beteiligte):
                return (
                    "Zu der Vermietung sind Beträge vorhanden, aber mindestens ein benötigter "
                    "Wert ist noch offen oder ungeklärt. Deshalb fasse ich sie noch nicht als "
                    "bestätigte Vermietungswerte zusammen."
                )
            m = miete[0]
            monat = _betrag_deutsch(m.get("monatsbetrag_eur"))
            return (
                f"Hinterlegt sind {_betrag_deutsch(m['betrag_eur'])} Jahreskaltmiete. "
                f"Die {monat} Monatsmiete sind derselbe Einnahmenstrom und keine zweite Einnahme. "
                f"Außerdem sind {_betrag_deutsch(zinsen[0]['betrag_eur']) if zinsen else 'keine'} Darlehenszinsen "
                f"und {_betrag_deutsch(grundsteuer[0]['betrag_eur']) if grundsteuer else 'keine'} Grundsteuer erfasst."
            )

    if "bereits erkannten werte" in text or "werte sind trotzdem vorhanden" in text:
        if not werte:
            return f"Für {jahr} sind noch keine strukturierten Werte hinterlegt."
        return (
            "Vorhandene strukturierte Werte: "
            + "; ".join(_wertanzeige(wert) for wert in werte)
            + "."
            + _begrenzungshinweis(kontext, "wert", len(werte))
        )

    fragt_nach_hinterlegten_unterlagen = (
        "welche angaben" in text
        and "unterlagen" in text
        and any(signal in text for signal in ("hast du", "hinterlegt", "vorhanden", "bereits erkannt"))
    )
    if fragt_nach_hinterlegten_unterlagen:
        if not dokumente and not werte:
            return f"Für {jahr} sind noch keine bestätigten Angaben, Unterlagen oder Finanzwerte hinterlegt."
        dokumentnamen = ", ".join(
            f"{dokument.get('dokumenttyp') or dokument.get('dateiname')} ({dokument.get('status')})"
            for dokument in dokumente
        )
        return (
            f"Für {jahr} sind folgende Unterlagen hinterlegt: {dokumentnamen}."
            + _begrenzungshinweis(kontext, "dokument", len(dokumente))
        )

    if text.startswith("liegt meine ") and " vor" in text:
        suchtext = re.sub(r"^liegt meine\s+", "", text).strip()
        suchtext = re.sub(r"\s+(?:schon\s+)?vor\??$", "", suchtext).strip()
        gefunden = [
            dokument
            for dokument in dokumente
            if suchtext in _text(dokument.get("dokumenttyp"), 120).casefold()
            or suchtext in _text(dokument.get("dateiname"), 200).casefold()
        ]
        if gefunden:
            return f"Ja. Hinterlegt ist {gefunden[0].get('dateiname')} mit Status {gefunden[0].get('status')}."
        return f"Nein. Für {jahr} ist keine passende Unterlage im aktiven Profil hinterlegt."

    if "welche quelle belegt" in text and verlauf:
        zahl = next(iter(re.findall(r"\d[\d.]*", frage)), "")
        passende = [wert for wert in werte if zahl and zahl in _wertanzeige(wert)]
        if passende:
            return f"Der Wert stammt aus {passende[0].get('herkunft')}; Status: {passende[0].get('status')}."
        if any(
            eintrag.get("rolle") == "nutzer" and zahl in str(eintrag.get("text", ""))
            for eintrag in verlauf
        ):
            return "Dafür liegt nur deine Aussage im Gespräch vor; ein bestätigender Beleg ist nicht hinterlegt."

    return None
