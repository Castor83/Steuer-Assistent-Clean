"""Sicherer Ordnerüberwacher für neue Steuerunterlagen.

Überwacht dokumente/eingang und meldet neue, vollständig kopierte Dateien.
Er verändert, verschiebt oder löscht keine Unterlagen. Die weitere Prüfung
und Verarbeitung bleibt eine bewusste, separate Aktion.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
from threading import Event, Lock
import time
import unicodedata

import nutzerverwaltung
from stammdaten import DATEINAME as STAMMDATEN_DATEINAME, lade_stammdaten, speichere_stammdaten


PROJECT_ROOT = Path(__file__).resolve().parent.parent
STANDARD_EINGANG = PROJECT_ROOT / "dokumente" / "eingang"
EINSTELLUNGEN = PROJECT_ROOT / "daten" / "einstellungen.json"
DOKUMENTREGISTER = PROJECT_ROOT / "daten" / "dokumentregister.json"
REGISTER_SPERRE = Lock()
PRUEFEN = PROJECT_ROOT / "dokumente" / "pruefen"
TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
TESSDATA = PROJECT_ROOT / "daten" / "tessdata"
UNTERSTUETZTE_ENDUNGEN = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".txt", ".csv"}
BILD_ENDUNGEN = {".png", ".jpg", ".jpeg", ".webp"}
PDF_ENDUNGEN = {".pdf"}
TEXT_ENDUNGEN = {".txt", ".csv"}
PDF_SEITEN_LIMIT = 100
TEXT_ZEICHEN_LIMIT = 100_000


def _einstellungen_datei() -> Path:
    return nutzerverwaltung.einstellungen_datei() or EINSTELLUNGEN


def _dokumentregister_datei() -> Path:
    return nutzerverwaltung.dokumentregister_datei() or DOKUMENTREGISTER


def _standard_eingang() -> Path:
    return nutzerverwaltung.standard_eingang() or STANDARD_EINGANG


def _pruefordner() -> Path:
    return nutzerverwaltung.pruefordner() or PRUEFEN


def aktueller_eingang() -> Path:
    """Liest den lokal gespeicherten Eingangsordner mit sicherem Standardwert."""
    einstellungen = _einstellungen_datei()
    try:
        daten = json.loads(einstellungen.read_text(encoding="utf-8"))
        pfad = Path(str(daten.get("eingangsordner", ""))).expanduser()
        if pfad.is_absolute() and pfad.exists() and pfad.is_dir():
            return pfad.resolve()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return _standard_eingang().resolve()


def setze_eingang(pfad_text: str) -> Path:
    """Prüft und speichert einen bereits vorhandenen lokalen Ordner."""
    pfad = Path(pfad_text.strip().strip('"')).expanduser()
    if not pfad.is_absolute():
        raise ValueError("Bitte gib einen vollständigen Ordnerpfad ein.")
    try:
        pfad = pfad.resolve(strict=True)
    except OSError as fehler:
        raise ValueError("Der angegebene Ordner wurde nicht gefunden.") from fehler
    if not pfad.is_dir():
        raise ValueError("Der angegebene Pfad ist kein Ordner.")
    if pfad == Path(pfad.anchor):
        raise ValueError("Ein gesamtes Laufwerk kann nicht überwacht werden. Bitte wähle einen Unterordner.")

    einstellungen = _einstellungen_datei()
    einstellungen.parent.mkdir(parents=True, exist_ok=True)
    temp = einstellungen.with_suffix(".tmp")
    temp.write_text(
        json.dumps({"eingangsordner": str(pfad)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(einstellungen)
    return pfad


def standard_eingang_setzen() -> Path:
    standard = _standard_eingang()
    standard.mkdir(parents=True, exist_ok=True)
    return setze_eingang(str(standard))


@dataclass(frozen=True)
class DateiStand:
    groesse: int
    geaendert_ns: int


def finde_dateien(ordner: Path) -> dict[Path, DateiStand]:
    """Liest unterstützte Dateien rekursiv, ohne ihren Inhalt zu verändern."""
    ergebnis: dict[Path, DateiStand] = {}
    for datei in ordner.rglob("*"):
        if not datei.is_file() or datei.suffix.lower() not in UNTERSTUETZTE_ENDUNGEN:
            continue
        try:
            status = datei.stat()
        except OSError:
            # Eine gerade kopierte oder entfernte Datei wird im nächsten Intervall erneut geprüft.
            continue
        ergebnis[datei] = DateiStand(status.st_size, status.st_mtime_ns)
    return ergebnis


def format_weg(datei: Path) -> str:
    try:
        return str(datei.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(datei)


def normalisiere(text: str) -> str:
    return "".join(
        zeichen
        for zeichen in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(zeichen)
    ).replace("ß", "ss")


def _steuer_id_pruefziffer_stimmt(ziffern: str) -> bool:
    """Prüft die elfte Ziffer der deutschen Identifikationsnummer."""
    if not re.fullmatch(r"\d{11}", ziffern):
        return False
    produkt = 10
    for zeichen in ziffern[:10]:
        summe = (int(zeichen) + produkt) % 10
        if summe == 0:
            summe = 10
        produkt = (2 * summe) % 11
    pruefziffer = 11 - produkt
    if pruefziffer == 10:
        pruefziffer = 0
    return pruefziffer == int(ziffern[-1])


def erkenne_steuer_id(text: str) -> str | None:
    """Erkennt nur eine prüfziffergültige 11-stellige ID in eindeutigem Kontext."""
    normal = normalisiere(text)
    muster = (
        r"(?:steuer[- ]?identifikationsnummer|steuer[- ]?id|identifikationsnummer|idnr[.]?)"
        r"[^\d]{0,40}((?:\d[\s./-]?){11})(?!\d)",
        r"((?:\d[\s./-]?){11})(?!\d)[^\n]{0,35}"
        r"(?:steuer[- ]?identifikationsnummer|steuer[- ]?id|identifikationsnummer|idnr[.]?)",
    )
    for ausdruck in muster:
        for treffer in re.finditer(ausdruck, normal):
            ziffern = re.sub(r"\D", "", treffer.group(1))
            if _steuer_id_pruefziffer_stimmt(ziffern):
                return ziffern
    return None


def _enthaelt_tokenfolge(text_tokens: list[str], name_tokens: list[str]) -> bool:
    if not name_tokens or len(name_tokens) > len(text_tokens):
        return False
    return any(
        text_tokens[start : start + len(name_tokens)] == name_tokens
        for start in range(len(text_tokens) - len(name_tokens) + 1)
    )


def erkenne_nutzerzuordnung(text: str) -> dict:
    """Vergleicht OCR-Text nur lokal mit bereits angelegten Nutzernamen."""
    aktiv = nutzerverwaltung.aktiver_nutzer()
    if aktiv is None:
        return {}

    normaler_text = normalisiere(text)
    text_tokens = re.findall(r"[a-z0-9]+", normaler_text)
    treffer: list[dict] = []
    unsichere_treffer: list[dict] = []
    for nutzer in nutzerverwaltung.nutzer_auflisten():
        name_tokens = re.findall(r"[a-z0-9]+", normalisiere(str(nutzer.get("name", ""))))
        if len(name_tokens) >= 2:
            varianten = [name_tokens, [name_tokens[-1], *name_tokens[:-1]]]
            if any(_enthaelt_tokenfolge(text_tokens, variante) for variante in varianten):
                treffer.append(nutzer)
        elif len(name_tokens) == 1:
            # Ein einzelner Vorname ist nur in typischem Personenkontext ein schwacher Treffer.
            muster = rf"(?:name|vorname|steuerpflichtig|arbeitnehmer|empfanger|herr|frau).{{0,60}}\b{re.escape(name_tokens[0])}\b"
            if re.search(muster, normaler_text):
                unsichere_treffer.append(nutzer)

    grunddaten = {
        "aktiver_nutzer_id": str(aktiv["id"]),
        "aktiver_name": str(aktiv["name"]),
        "bestaetigt": False,
    }
    if len(treffer) == 1:
        erkannt = treffer[0]
        passend = erkannt.get("id") == aktiv.get("id")
        return {
            **grunddaten,
            "status": "Erkannt" if passend else "Anderer Nutzer erkannt",
            "erkannter_nutzer_id": str(erkannt["id"]),
            "erkannter_name": str(erkannt["name"]),
            "hinweis": (
                f"Der Name {erkannt['name']} wurde im Dokument erkannt und passt zum geöffneten Profil."
                if passend
                else f"Achtung: Im Dokument wurde {erkannt['name']} erkannt, geöffnet ist aber {aktiv['name']}."
            ),
        }
    if len(treffer) > 1:
        namen = ", ".join(str(n["name"]) for n in treffer)
        return {
            **grunddaten,
            "status": "Mehrdeutig",
            "erkannter_name": namen,
            "hinweis": f"Mehrere bekannte Namen wurden gefunden: {namen}. Bitte manuell prüfen.",
        }
    if len(unsichere_treffer) == 1:
        erkannt = unsichere_treffer[0]
        return {
            **grunddaten,
            "status": "Unsicher erkannt",
            "erkannter_nutzer_id": str(erkannt["id"]),
            "erkannter_name": str(erkannt["name"]),
            "hinweis": f"Der einzelne Name {erkannt['name']} könnte gemeint sein. Bitte am Original prüfen.",
        }
    return {
        **grunddaten,
        "status": "Nicht erkannt",
        "erkannter_name": "",
        "hinweis": "Kein bereits angelegter vollständiger Nutzername wurde sicher erkannt.",
    }


def lies_ocr_text(datei: Path) -> tuple[str, str]:
    """Liest Bild- oder PDF-Text lokal und gibt ihn niemals an die Konsole weiter."""
    endung = datei.suffix.lower()
    if endung in TEXT_ENDUNGEN:
        try:
            return datei.read_text(encoding="utf-8", errors="replace")[:TEXT_ZEICHEN_LIMIT], "Text lokal eingelesen"
        except OSError:
            return "", "Textdatei konnte nicht gelesen werden"
    if endung not in BILD_ENDUNGEN | PDF_ENDUNGEN:
        return "", "Fuer diesen Dateityp noch keine OCR"

    try:
        if endung in BILD_ENDUNGEN:
            if not TESSERACT.exists() or not (TESSDATA / "deu.traineddata").exists():
                return "", "OCR-Komponenten nicht vollstaendig vorhanden"
            from PIL import Image
            import pytesseract

            pytesseract.pytesseract.tesseract_cmd = str(TESSERACT)
            os.environ["TESSDATA_PREFIX"] = str(TESSDATA)
            with Image.open(datei) as bild:
                text = pytesseract.image_to_string(bild, lang="deu")
            return text, "OCR lokal ausgefuehrt"

        import pymupdf

        texte: list[str] = []
        ocr_seiten = 0
        nicht_lesbare_seiten = 0
        with pymupdf.open(datei) as dokument:
            seitenzahl = min(len(dokument), PDF_SEITEN_LIMIT)
            for nummer in range(seitenzahl):
                seite = dokument.load_page(nummer)
                nativer_text = seite.get_text("text").strip()
                if len(nativer_text) >= 20:
                    texte.append(nativer_text)
                    continue
                if not TESSERACT.exists() or not (TESSDATA / "deu.traineddata").exists():
                    nicht_lesbare_seiten += 1
                    continue
                from PIL import Image
                import pytesseract

                pytesseract.pytesseract.tesseract_cmd = str(TESSERACT)
                os.environ["TESSDATA_PREFIX"] = str(TESSDATA)
                bilddaten = seite.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
                bild = Image.frombytes("RGB", (bilddaten.width, bilddaten.height), bilddaten.samples)
                texte.append(pytesseract.image_to_string(bild, lang="deu"))
                ocr_seiten += 1

            begrenzt = len(dokument) > PDF_SEITEN_LIMIT
            status = f"PDF lokal vollständig ausgewertet ({seitenzahl} Seite(n))"
            if ocr_seiten:
                status += f", davon {ocr_seiten} per OCR"
            if nicht_lesbare_seiten:
                status += f"; {nicht_lesbare_seiten} Scan-Seite(n) ohne verfügbare OCR"
            if begrenzt:
                status = (
                    f"PDF lokal bis zur Sicherheitsgrenze von {PDF_SEITEN_LIMIT} Seiten ausgewertet; "
                    f"Dokument hat {len(dokument)} Seiten"
                )
            return "\n".join(texte), status
    except Exception:
        if endung in PDF_ENDUNGEN:
            return "", "PDF-OCR konnte die Datei nicht auslesen"
        return "", "OCR konnte das Bild nicht auslesen"


def _jahr_aus_kontext(name: str, inhalt: str, dokumenttyp: str) -> str:
    """Bestimmt ein Bezugsjahr nur aus belastbarem Dokumentkontext."""
    if dokumenttyp in {
        "Historische Einkommensteuererklärung",
        "Historische Grundstücks- und Gebäudedaten",
    }:
        return "Nicht erkannt"

    text = f"{name}\n{inhalt}"
    kontextmuster = (
        r"((?:19|20)\d{2})\s*an(?:l|i)vor\w*",
        r"(?:bescheinigungs|leistungs|abrechnungs|beitrags)?zeitraum[^\d]{0,30}"
        r"\d{1,2}[.]\d{1,2}[.](20\d{2})\s*(?:bis|[-])",
        r"(?:kalender|steuer|veranlagungs|beitrags)jahr[^\d]{0,20}((?:19|20)\d{2})",
        r"(?:einkommensteuer|lohnsteuerbescheinigung|leistungsnachweis)[^\d]{0,25}((?:19|20)\d{2})",
        r"(?:fur|für|im jahr|zum)[^\d]{0,20}((?:19|20)\d{2})",
        r"(?:per|stand)[^\d]{0,15}\d{1,2}[.]\d{1,2}[.]((?:19|20)\d{2})",
        r"(?:rechnungs|ausstellungs|bescheid)?datum[^\d]{0,20}"
        r"\d{1,2}[.]\d{1,2}[.]((?:19|20)\d{2})",
    )
    for muster in kontextmuster:
        treffer = re.search(muster, text)
        if treffer:
            return treffer.group(1)

    dateiname_jahre = re.findall(r"\b(?:19|20)\d{2}\b", name)
    if dateiname_jahre:
        return dateiname_jahre[0]
    return "Nicht erkannt"


def _jahr_aus_bildkopf(datei: Path) -> str:
    """Liest ein einzelnes deutliches Jahr im oberen rechten Bildbereich nach.

    Diese zweite, eng begrenzte OCR-Stufe wird nur aufgerufen, wenn die normale
    Texterkennung bei einem jahresbezogenen Dokument kein Jahr gefunden hat.
    """
    if datei.suffix.lower() not in BILD_ENDUNGEN:
        return "Nicht erkannt"
    if not TESSERACT.exists() or not (TESSDATA / "deu.traineddata").exists():
        return "Nicht erkannt"
    try:
        from PIL import Image, ImageOps
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = str(TESSERACT)
        os.environ["TESSDATA_PREFIX"] = str(TESSDATA)
        with Image.open(datei) as original:
            ausschnitt = original.crop(
                (
                    round(original.width * 0.72),
                    0,
                    original.width,
                    round(original.height * 0.14),
                )
            )
            grau = ImageOps.autocontrast(ImageOps.grayscale(ausschnitt), cutoff=1)
            grau = grau.resize((grau.width * 2, grau.height * 2))
            kandidaten: list[str] = []
            for schwelle, psm in ((120, 11), (130, 6), (130, 11), (140, 11)):
                kontrast = grau.point(lambda pixel, grenze=schwelle: 255 if pixel > grenze else 0)
                text = pytesseract.image_to_string(
                    kontrast,
                    lang="deu",
                    config=f"--psm {psm} -c tessedit_char_whitelist=0123456789",
                )
                kandidaten.extend(re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", text))
        erlaubtes_hoechstjahr = datetime.now().year + 1
        stimmen = Counter(
            jahr for jahr in kandidaten if 1900 <= int(jahr) <= erlaubtes_hoechstjahr
        )
        if not stimmen:
            return "Nicht erkannt"
        jahr, anzahl = stimmen.most_common(1)[0]
        zweitplatz = stimmen.most_common(2)[1][1] if len(stimmen) > 1 else 0
        return jahr if anzahl >= 2 and anzahl > zweitplatz else "Nicht erkannt"
    except Exception:
        return "Nicht erkannt"


def _steuerjahr_mit_bildkopf(datei: Path, name: str, inhalt: str, dokumenttyp: str) -> str:
    steuerjahr = _jahr_aus_kontext(name, inhalt, dokumenttyp)
    if steuerjahr != "Nicht erkannt":
        return steuerjahr
    if dokumenttyp not in {
        "Elektronische Lohnsteuerbescheinigung",
        "Anlage Vorsorgeaufwand",
    }:
        return steuerjahr
    return _jahr_aus_bildkopf(datei)


def _starker_dokumenttyp(name: str, inhalt: str) -> tuple[str, str] | None:
    """Erkennt charakteristische Überschriften vor schwachen Einzelbegriffen."""
    text = f"{name} {inhalt}"
    if "2010" in text and any(
        begriff in text
        for begriff in (
            "2010est1a",
            "erklarung zur festsetzung",
            "allgemeine angaben",
            "steuerpflichtige person",
        )
    ) and "anlage v" not in text:
        return "Historische Einkommensteuererklärung", "Dokumentinhalt"
    if "2010" in text and any(
        begriff in text
        for begriff in (
            "anlage v",
            "einkommensteuer",
            "einkommensteuer 2010",
            "vermietung",
            "verpachtung",
            "anschaffungskosten haus",
            "anteil grund und boden",
            "absetzung fur abnutzung",
        )
    ):
        return "Historische Grundstücks- und Gebäudedaten", "Dokumentinhalt"
    if "vorsorgeaufwendungen" in text and any(
        begriff in text
        for begriff in (
            "beitrage zur altersvorsorge",
            "private kranken- und pflegeversicherung",
            "steuerfreie arbeitgeberzuschusse",
            "anivor",
            "anlvor",
        )
    ):
        return "Anlage Vorsorgeaufwand", "Dokumentinhalt"
    if (
        "lohnsteuerbescheinigung" in text
        or "ausdruck der elektronischen lohnsteuer" in text
        # Bei schräg fotografierten Formularen trennt Tesseract das lange Wort
        # gelegentlich genau an der Spaltengrenze und schiebt den Mittelteil
        # der Überschrift dazwischen.
        or all(begriff in text for begriff in ("lohnste", "uerbescheinigung", "elektronischen"))
    ):
        return "Elektronische Lohnsteuerbescheinigung", "Dokumentinhalt"
    if "insolvenzgeld" in text and any(
        begriff in text for begriff in ("leistungsnachweis", "leistungsart", "agentur fur arbeit")
    ):
        return "Insolvenzgeldbescheinigung", "Dokumentinhalt"
    if "insolvenzgeld" in text:
        return "Notiz – Insolvenzgeld", "Dokumentinhalt"
    if any(begriff in text for begriff in ("wohnraummietvertrag", "mietvertrag")):
        return "Mietvertrag", "Dokumentinhalt"
    if (
        any(begriff in text for begriff in ("anlage v", "vermietung", "verpachtung"))
        and "anschaffungskosten" in text
        and any(begriff in text for begriff in ("abschreib", "linear", "2%"))
    ):
        return "Notiz – Vermietung", "Dokumentinhalt"
    if any(
        begriff in text
        for begriff in ("saldenmitteilung", "zins- und kostenbescheinigung", "darlehenszinsbescheinigung")
    ):
        return "Darlehenszinsbescheinigung", "Dokumentinhalt"
    if "gebaudeversicherung" in text or "wohn-/gewerbeflache" in text:
        return "Gebäudeversicherungsunterlage", "Dokumentinhalt"
    if "haftpflicht" in text and any(
        begriff in text for begriff in ("versicherung", "beitrag", "monat", "jahrlich")
    ):
        return "Notiz – Versicherungen", "Dokumentinhalt"
    if "rechnung" in text and any(
        begriff in text for begriff in ("schornsteinfeger", "kehrarbeiten", "uberprufungsarbeiten")
    ):
        return "Schornsteinfegerrechnung", "Dokumentinhalt"
    return None


def erkenne_dokumenttyp(datei: Path, mit_text: bool = False):
    """Ermittelt einen vorsichtigen Dokumenttyp aus Dateiname und lokalem OCR-Text.

    Das Ergebnis ist stets ein Vorschlag und keine verbindliche Klassifikation.
    """
    name = normalisiere(datei.stem)
    ocr_text, ocr_status = lies_ocr_text(datei)
    inhalt = normalisiere(ocr_text)
    stark = _starker_dokumenttyp(name, inhalt)
    if stark is not None:
        dokumenttyp, grundlage = stark
        steuerjahr = _steuerjahr_mit_bildkopf(datei, name, inhalt, dokumenttyp)
        ergebnis = (dokumenttyp, grundlage, ocr_status, steuerjahr)
        return (*ergebnis, ocr_text) if mit_text else ergebnis
    muster = (
        (("lohnsteuerbescheinigung", "elektronische-lohnsteuer"), "Elektronische Lohnsteuerbescheinigung"),
        (("rentenbezugsmitteilung", "mitteilung zur vorlage beim finanzamt", "bezugsmitteilung rente"), "Rentenbezugsmitteilung"),
        (("krankengeldbescheinigung", "bezogenes krankengeld"), "Krankengeldbescheinigung"),
        (("insolvenzgeldbescheid", "insolvenzgeldbescheinigung", "bescheinigung fur insolvenzgeld", "bescheinigung für insolvenzgeld"), "Insolvenzgeldbescheinigung"),
        (("arbeitsvertrag", "arbeitsverhaltnis", "arbeitsverhältnis"), "Arbeitsvertrag"),
        (("verdienstabrechnung", "gehaltsabrechnung", "lohnabrechnung"), "Verdienstabrechnung"),
        (("arbeitslosengeld", "leistungsnachweis agentur fur arbeit"), "Arbeitslosengeldbescheinigung"),
        (("elterngeldbescheid", "elterngeld plus", "basiselterngeld"), "Elterngeldbescheid"),
        (("kurzarbeitergeld", "saison-kurzarbeitergeld"), "Kurzarbeitergeldnachweis"),
        (("beitragsbescheinigung kranken", "basisabsicherung", "pflegepflichtversicherung"), "Kranken- und Pflegeversicherungsbescheinigung"),
        (("riester", "altersvorsorgezulage", "bescheinigung nach 92 estg"), "Riester-Bescheinigung"),
        (("rurup", "basisrente", "bescheinigung nach 10 absatz 1 nummer 2"), "Rürup- oder Basisrentenbescheinigung"),
        (("steuerbescheinigung kapital", "kapitalertragsteuer", "verlustbescheinigung", "jahressteuerbescheinigung"), "Kapitalertragsteuerbescheinigung"),
        (("zuwendungsbestaetigung", "spendenbescheinigung", "spendenquittung"), "Spendenbescheinigung"),
        (("kinderbetreuung", "kindertagesstatte", "kita-gebuhr", "tagesmutter"), "Kinderbetreuungskosten"),
        (("haushaltsnahe dienstleistung", "35a estg", "handwerkerleistung"), "Handwerker- oder haushaltsnahe Dienstleistung"),
        (("fortbildungskosten", "seminargebuhr", "teilnahmebescheinigung"), "Fortbildungsunterlage"),
        (("reisekostenabrechnung", "dienstreise", "verpflegungsmehraufwand"), "Reisekostenunterlage"),
        (("arbeitsmittel", "beruflich genutz", "buroausstattung"), "Arbeitsmittelbeleg"),
        (("entfernungspauschale", "fahrten zur ersten tatigkeitsstatte", "pendlerpauschale"), "Fahrtkostenaufstellung"),
        (("grundsteuerwertbescheid", "bescheid uber den grundsteuerwert", "bescheid über den grundsteuerwert"), "Grundsteuerwertbescheid"),
        (("grundstucksaquivalenzbetrag", "grundstücksäquivalenzbetrag", "aquivalenzbetragsbescheid", "äquivalenzbetragsbescheid"), "Grundsteueräquivalenzbetragsbescheid"),
        (("grundsteuermessbescheid", "grundsteuermessbetrag"), "Grundsteuermessbescheid"),
        (("grundsteuerbescheid", "hebesatz grundsteuer"), "Kommunaler Grundsteuerbescheid"),
        (("grundbuchauszug", "grundbuch von"), "Grundbuchauszug"),
        (("erbschaftsteuerbescheid", "schenkungsteuerbescheid"), "Erbschaft- oder Schenkungsteuerbescheid"),
        (("erbschein", "zeugnis uber das erbrecht", "zeugnis über das erbrecht"), "Erbschein"),
        (("testament", "letztwillige verfugung", "letztwillige verfügung", "erbvertrag"), "Testament oder Erbvertrag"),
        (("nachlassverzeichnis", "nachlassaufstellung", "nachlassverbindlichkeiten"), "Nachlassaufstellung"),
        (("bodenrichtwert", "boris"), "Bodenrichtwertunterlage"),
        (("mietvertrag", "mietverhaltnis"), "Mietvertrag"),
        (("betriebskosten", "nebenkostenabrechnung"), "Betriebskostenabrechnung"),
        (("hausgeldabrechnung", "wohnungseigentumergemeinschaft", "weg-abrechnung"), "Hausgeldabrechnung"),
        (("schuldzinsen", "zinsbescheinigung darlehen", "darlehenszinsen", "baufinanzierung"), "Darlehenszinsbescheinigung"),
        (("mieteinnahmen", "mietaufstellung", "mietkonto"), "Mieteinnahmenaufstellung"),
        (("einnahmenuberschussrechnung", "anlage eur", "betriebseinnahmen", "betriebsausgaben"), "Einnahmenüberschussrechnung"),
        (("umsatzsteuer-voranmeldung", "umsatzsteuervoranmeldung"), "Umsatzsteuer-Voranmeldung"),
        (("gewerbesteuermessbescheid",), "Gewerbesteuermessbescheid"),
        (("ubertragungsprotokoll", "elster-protokoll", "komprimierte steuererklarung"), "ELSTER-Übertragungsprotokoll"),
        (("einkommensteuerbescheid", "bescheid fur 20", "festsetzung der einkommensteuer"), "Einkommensteuerbescheid"),
        (("versicherung", "beitragsbescheinigung"), "Sonstige Versicherungsunterlage"),
        (("rechnung", "invoice", "rechnungsnummer"), "Sonstige Rechnung"),
        (("grundsteuer",), "Sonstige Grundsteuerunterlage"),
        (("steuerbescheid",), "Sonstiger Steuerbescheid"),
    )
    for begriffe, dokumenttyp in muster:
        if any(begriff in inhalt for begriff in begriffe):
            steuerjahr = _steuerjahr_mit_bildkopf(datei, name, inhalt, dokumenttyp)
            ergebnis = (dokumenttyp, "Dokumentinhalt", ocr_status, steuerjahr)
            return (*ergebnis, ocr_text) if mit_text else ergebnis
        if any(begriff in name for begriff in begriffe):
            steuerjahr = _steuerjahr_mit_bildkopf(datei, name, inhalt, dokumenttyp)
            ergebnis = (dokumenttyp, "Dateiname", ocr_status, steuerjahr)
            return (*ergebnis, ocr_text) if mit_text else ergebnis
    steuerjahr = _jahr_aus_kontext(name, inhalt, "Unbekannte Unterlage")
    ergebnis = ("Unbekannte Unterlage", "Dateiname und Dokumentinhalt nicht eindeutig", ocr_status, steuerjahr)
    return (*ergebnis, ocr_text) if mit_text else ergebnis


def _deutscher_betrag(text: str) -> str | None:
    treffer = re.search(r"(?<!\d)(\d{1,3}(?:[. ]\d{3})*(?:,\d{2})|\d+,\d{2})(?!\d)", text)
    if not treffer:
        return None
    return treffer.group(1).replace(" ", ".") + " €"


def _betrag_nach_begriff(text: str, begriffe: tuple[str, ...]) -> str | None:
    for zeile in text.splitlines():
        normal = normalisiere(zeile)
        if any(begriff in normal for begriff in begriffe):
            betrag = _deutscher_betrag(zeile)
            if betrag:
                return betrag
    return None


def _merkmal(text: str, muster: tuple[str, ...]) -> str | None:
    normal = normalisiere(text)
    for ausdruck in muster:
        treffer = re.search(ausdruck, normal, flags=re.IGNORECASE)
        if treffer:
            return treffer.group(1).strip().upper()
    return None


def _gebaeudemerkmale(text: str) -> list[dict]:
    """Liest nur klar beschriftete Gebäudestammdaten als strukturierte Rohwerte."""
    felder = (
        (
            "grundstuecksflaeche",
            "Grundstücksfläche",
            (r"grundstuck(?:s)?flache[^\n\d]{0,30}(\d{1,6}(?:[,.]\d{1,2})?)\s*(?:m2|qm)",),
            " m²",
        ),
        (
            "wohnflaeche",
            "Wohnfläche",
            (r"wohnflache[^\n\d]{0,30}(\d{1,5}(?:[,.]\d{1,2})?)\s*(?:m2|qm)",),
            " m²",
        ),
        (
            "baujahr",
            "Baujahr",
            (r"baujahr[^\n\d]{0,25}((?:18|19|20)\d{2})",),
            "",
        ),
        (
            "wohneinheiten",
            "Wohneinheiten",
            (r"(?:anzahl der )?wohneinheiten[^\n\d]{0,25}(\d{1,3})\b",),
            "",
        ),
    )
    vorschlaege = []
    for kennung, bezeichnung, muster, einheit in felder:
        wert = _merkmal(text, muster)
        if wert:
            vorschlaege.append(
                {
                    "id": kennung,
                    "bezeichnung": bezeichnung,
                    "wert": wert.replace(".", ",") + einheit,
                    "art": "Gebäudestammdatum",
                    "status": "Zu prüfen",
                }
            )
    return vorschlaege


def _ocr_ziffernkandidaten(bild) -> list[str]:
    """Liest eine kleine Tabellenzelle mehrfach und liefert nur Ziffernfolgen."""
    from PIL import ImageEnhance, ImageOps
    import pytesseract

    zelle = ImageOps.autocontrast(ImageOps.grayscale(bild), cutoff=1)
    zelle = zelle.resize((zelle.width * 6, zelle.height * 6))
    kandidaten: list[str] = []
    for psm in (6, 7, 11, 13):
        text = pytesseract.image_to_string(
            zelle,
            lang="deu",
            config=f"--psm {psm} -c tessedit_char_whitelist=0123456789",
        )
        wert = "".join(re.findall(r"\d", text))
        if wert:
            kandidaten.append(wert)
    # Zwei voneinander abweichende Aufbereitungen helfen bei einer schmalen
    # Endziffer, die direkt neben der Tabellenlinie steht. Sie werden bewusst
    # nur mit demselben Segmentierungsmodus verglichen.
    grau = ImageOps.grayscale(bild)
    schwierig = (
        ImageOps.autocontrast(grau, cutoff=3).point(lambda pixel: 255 if pixel > 160 else 0),
        ImageEnhance.Contrast(grau).enhance(3.0).point(lambda pixel: 255 if pixel > 100 else 0),
    )
    for variante in schwierig:
        variante = variante.resize((variante.width * 10, variante.height * 10))
        text = pytesseract.image_to_string(
            variante,
            lang="deu",
            config="--psm 6 -c tessedit_char_whitelist=0123456789",
        )
        wert = "".join(re.findall(r"\d", text))
        if wert:
            kandidaten.append(wert)
    return kandidaten


def _betragsvorschlaege_aus_bild(datei: Path) -> list[dict]:
    """Liest bei einer fotografierten LStB ausgewählte Tabellenzellen konservativ.

    Tabellenlinien zwischen Euro und Cent verwirren die Ganzseiten-OCR häufig.
    Diese zweite Stufe sucht die amtlichen Zeilennummern und liest beide Spalten
    getrennt. Fehlt eine zweistellige Centangabe, wird kein Betrag vorgeschlagen.
    """
    if datei.suffix.lower() not in BILD_ENDUNGEN:
        return []
    if not TESSERACT.exists() or not (TESSDATA / "deu.traineddata").exists():
        return []
    try:
        from PIL import Image, ImageOps
        import pytesseract
        from pytesseract import Output

        pytesseract.pytesseract.tesseract_cmd = str(TESSERACT)
        os.environ["TESSDATA_PREFIX"] = str(TESSDATA)
        zeilen = {
            3: ("bruttoarbeitslohn", "Bruttoarbeitslohn"),
            # Die Nullfelder 4 bis 6 liegen direkt an mehreren Tabellenlinien.
            # Bei diesem Foto verwechselt die OCR einzelne Linien mit einer 1.
            # Sie bleiben daher bewusst der manuellen Sichtprüfung vorbehalten.
            23: ("rentenversicherung", "Arbeitnehmerbeitrag Rentenversicherung"),
            25: ("krankenversicherung", "Arbeitnehmerbeitrag Krankenversicherung"),
            26: ("pflegeversicherung", "Arbeitnehmerbeitrag Pflegeversicherung"),
            27: ("arbeitslosenversicherung", "Arbeitnehmerbeitrag Arbeitslosenversicherung"),
        }
        with Image.open(datei) as original:
            grau = ImageOps.autocontrast(ImageOps.grayscale(original), cutoff=2)
            analyse_links = round(original.width * 0.45)
            analyse_oben = round(original.height * 0.05)
            analyse_rechts = round(original.width * 0.97)
            analyse_unten = round(original.height * 0.72)
            analyse_ausschnitt = grau.crop(
                (analyse_links, analyse_oben, analyse_rechts, analyse_unten)
            )
            analyse = analyse_ausschnitt.resize(
                (analyse_ausschnitt.width * 2, analyse_ausschnitt.height * 2)
            )
            daten = pytesseract.image_to_data(
                analyse,
                lang="deu",
                config="--psm 4",
                output_type=Output.DICT,
            )
            fundstellen: dict[int, tuple[int, int]] = {}
            for index, token in enumerate(daten["text"]):
                treffer = re.fullmatch(r"(3|4|5|6|23|25|26|27)[.]?", token.strip())
                if not treffer:
                    continue
                nummer = int(treffer.group(1))
                links = analyse_links + int(daten["left"][index]) // 2
                if not original.width * 0.45 <= links <= original.width * 0.58:
                    continue
                oben = analyse_oben + int(daten["top"][index]) // 2
                hoehe = max(8, int(daten["height"][index]) // 2)
                fundstellen.setdefault(nummer, (oben, hoehe))

            vorschlaege: list[dict] = []
            for nummer, (kennung, bezeichnung) in zeilen.items():
                if nummer not in fundstellen:
                    continue
                oben, hoehe = fundstellen[nummer]
                if nummer == 3:
                    wert_oben = oben
                elif nummer in {4, 5, 6}:
                    wert_oben = round(oben - hoehe * 0.4)
                else:
                    wert_oben = round(oben - hoehe * (1.3 if nummer == 23 else 0.8))
                wert_unten = wert_oben + max(24, round(hoehe * 2.2))

                def linie_nahe(anteil: float, radius: float) -> int:
                    mitte = round(original.width * anteil)
                    abstand = round(original.width * radius)
                    kandidaten = []
                    for x in range(max(0, mitte - abstand), min(original.width, mitte + abstand + 1)):
                        mittelwert = sum(
                            grau.getpixel((x, y))
                            for y in range(max(0, wert_oben), min(original.height, wert_unten))
                        ) / max(1, wert_unten - wert_oben)
                        kandidaten.append((mittelwert, x))
                    return min(kandidaten)[1]

                # Durch die Perspektive des Fotos wandert die Tabelle von oben
                # nach unten leicht nach rechts. Die erwarteten Linienpositionen
                # werden deshalb aus der Zeilenhöhe interpoliert.
                zeilenmitte = (wert_oben + wert_unten) / 2
                linke_linie = linie_nahe(0.795 + 0.0000227 * zeilenmitte, 0.012)
                trennlinie = linie_nahe(0.892 + 0.0000227 * zeilenmitte, 0.012)
                rechte_linie = linie_nahe(0.923 + 0.0000236 * zeilenmitte, 0.009)
                if not (linke_linie + 15 < trennlinie < rechte_linie - 8):
                    continue
                zellen_oben = max(0, wert_oben - 7)
                zellen_unten = min(original.height, wert_oben + 23)
                euro_bild = original.crop(
                    (linke_linie + 4, zellen_oben, trennlinie - 4, zellen_unten)
                )
                cent_bild = original.crop(
                    (trennlinie + 2, zellen_oben, rechte_linie - 3, zellen_unten)
                )
                euro_kandidaten = _ocr_ziffernkandidaten(euro_bild)
                cent_kandidaten = _ocr_ziffernkandidaten(cent_bild)
                euro_stimmen = Counter(
                    wert.lstrip("0") or "0"
                    for wert in euro_kandidaten
                    if len(wert) <= 6
                )
                euro, euro_anzahl = euro_stimmen.most_common(1)[0] if euro_stimmen else ("", 0)
                cent_stimmen = Counter(wert for wert in cent_kandidaten if len(wert) == 2)
                cent, stimmen = cent_stimmen.most_common(1)[0] if cent_stimmen else ("", 0)
                if euro_anzahl < 2:
                    euro = ""
                if stimmen < 2:
                    cent = ""
                if not euro or not cent:
                    continue
                vorschlaege.append(
                    {
                        "id": kennung,
                        "bezeichnung": bezeichnung,
                        "wert": f"{int(euro):,}".replace(",", ".") + f",{cent} €",
                        "art": "Betrag",
                        "status": "Zu prüfen",
                        "grundlage": "Getrennte lokale Tabellen-OCR",
                    }
                )
            return vorschlaege
    except Exception:
        return []


def extrahiere_wertvorschlaege(
    dokumenttyp: str,
    text: str,
    datei: Path | None = None,
) -> list[dict]:
    """Extrahiert wenige klar bezeichnete Werte; Rohtext wird nicht gespeichert."""
    felder: list[tuple[str, str, tuple[str, ...]]] = []
    if dokumenttyp == "Elektronische Lohnsteuerbescheinigung":
        felder = [
            ("bruttoarbeitslohn", "Bruttoarbeitslohn", ("bruttoarbeitslohn",)),
            ("lohnsteuer", "Einbehaltene Lohnsteuer", ("einbehaltene lohnsteuer", "lohnsteuer")),
            ("solidaritaetszuschlag", "Solidaritätszuschlag", ("solidaritatszuschlag",)),
            ("kirchensteuer", "Kirchensteuer", ("kirchensteuer",)),
            ("rentenversicherung", "Arbeitnehmerbeitrag Rentenversicherung", ("arbeitnehmeranteil am gesamtsozialversicherungsbeitrag renten", "rentenversicherung")),
            ("krankenversicherung", "Arbeitnehmerbeitrag Krankenversicherung", ("krankenversicherung",)),
            ("pflegeversicherung", "Arbeitnehmerbeitrag Pflegeversicherung", ("pflegeversicherung",)),
            ("arbeitslosenversicherung", "Arbeitnehmerbeitrag Arbeitslosenversicherung", ("arbeitslosenversicherung",)),
        ]
    elif dokumenttyp == "Grundsteuerwertbescheid":
        felder = [("grundsteuerwert", "Grundsteuerwert", ("grundsteuerwert",))]
    elif dokumenttyp == "Grundsteuermessbescheid":
        felder = [("grundsteuermessbetrag", "Grundsteuermessbetrag", ("grundsteuermessbetrag", "steuermessbetrag"))]
    elif dokumenttyp == "Kommunaler Grundsteuerbescheid":
        felder = [
            ("grundsteuermessbetrag", "Grundsteuermessbetrag", ("grundsteuermessbetrag", "messbetrag")),
            ("jahresgrundsteuer", "Jahresgrundsteuer", ("jahresbetrag", "grundsteuer fur", "grundsteuer 20")),
        ]
    elif dokumenttyp in {
        "Sonstige Rechnung",
        "Schornsteinfegerrechnung",
        "Handwerker- oder haushaltsnahe Dienstleistung",
        "Kinderbetreuungskosten",
    }:
        felder = [
            (
                "rechnungsbetrag",
                "Rechnungsbetrag",
                ("rechnungsbetrag", "gesamtbetrag", "zu zahlen", "endbetrag", "gesamt eur"),
            ),
            (
                "arbeitskosten",
                "Ausgewiesene Arbeitskosten",
                ("arbeitskosten", "lohnkosten", "lohnanteil"),
            ),
        ]

    if dokumenttyp in {
        "Mietvertrag",
        "Gebäudeversicherungsunterlage",
        "Historische Grundstücks- und Gebäudedaten",
        "Notiz Grundstücks- und Gebäudedaten",
    }:
        vorschlaege = _gebaeudemerkmale(text)
    else:
        vorschlaege = []

    if dokumenttyp == "Historische Grundstücks- und Gebäudedaten":
        historische_betraege = (
            ("anschaffungskosten", "Historische Anschaffungskosten", ("anschaffungskosten", "kaufpreis")),
            ("grund_und_boden", "Anteil Grund und Boden", ("anteil grund und boden", "grund und boden")),
            ("gebaeudewert", "Historischer Gebäudewert", ("gebaudewert", "anteil gebaude")),
        )
        for kennung, bezeichnung, begriffe in historische_betraege:
            wert = _betrag_nach_begriff(text, begriffe)
            if wert:
                vorschlaege.append(
                    {
                        "id": kennung,
                        "bezeichnung": bezeichnung,
                        "wert": wert,
                        "art": "Historischer Betrag",
                        "status": "Zu prüfen",
                    }
                )

    for kennung, bezeichnung, begriffe in felder:
        wert = _betrag_nach_begriff(text, begriffe)
        if wert is not None:
            vorschlaege.append(
                {"id": kennung, "bezeichnung": bezeichnung, "wert": wert, "art": "Betrag", "status": "Zu prüfen"}
            )

    if dokumenttyp == "Elektronische Lohnsteuerbescheinigung":
        merkmale = [
            (
                "steuerklasse",
                "Steuerklasse",
                (
                    r"steuerklasse(?:\s*/\s*faktor)?[^\n\d]{0,25}\n\s*([1-6])\b",
                    r"steuerklasse(?:\s*/\s*faktor)?[^\n\d]{0,25}([1-6])\b",
                ),
            ),
            (
                "faktor",
                "Faktorverfahren",
                (r"steuerklasse\s*/\s*faktor[^\n\d]{0,25}[1-6]\s*[/ ]\s*(0[,.]\d{2,4})", r"faktor[^\n\d]{0,15}(0[,.]\d{2,4})"),
            ),
            (
                "kinderfreibetrag",
                "Zahl der Kinderfreibeträge",
                (
                    # Bei fotografierten Bescheinigungen hängt Tesseract häufig eine
                    # fremde Tabellenziffer an die Überschrift. Der echte Wert steht
                    # dann als Dezimalzahl am Anfang der folgenden Zeile.
                    r"(?:zahl der )?kinderfreibetrag(?:e|en)?[^\n]{0,40}\n\s*(\d[,.]\d)\b",
                    r"(?:zahl der )?kinderfreibetrag(?:e|en)?[^\n\d]{0,30}(\d(?:[,.]\d)?)\b",
                ),
            ),
            (
                "kirchensteuermerkmal",
                "Kirchensteuermerkmal",
                (r"kirchensteuermerkmal(?:e)?[^\n\w]{0,15}([a-z]{2,8}(?:\s*/\s*[a-z]{2,8})?)",),
            ),
            (
                "beschaeftigungszeitraum",
                "Bescheinigungszeitraum",
                (
                    r"(?:bescheinigungs|beschaftigungs)zeitraum[^\n\d]{0,30}"
                    r"(\d{2}[.]\d{2}[.](?:\d{4})?\s*(?:bis|[-])\s*\d{2}[.]\d{2}[.]\d{4})",
                ),
            ),
            (
                "grossbuchstaben",
                "Steuerliche Großbuchstaben",
                (r"(?:grossbuchstaben|grossbuchstabe)\b\s*[:\-]\s*([a-z](?:\s*[,/]\s*[a-z])*)",),
            ),
        ]
        vorhandene_ids = {wert["id"] for wert in vorschlaege}
        for kennung, bezeichnung, muster in merkmale:
            wert = _merkmal(text, muster)
            if wert and kennung == "beschaeftigungszeitraum":
                zeitraum = re.fullmatch(
                    r"(\d{2}[.]\d{2}[.])(\d{4})?\s*(?:BIS|[-])\s*"
                    r"(\d{2}[.]\d{2}[.](\d{4}))",
                    wert,
                )
                if zeitraum:
                    startjahr = zeitraum.group(2) or zeitraum.group(4)
                    wert = f"{zeitraum.group(1)}{startjahr} BIS {zeitraum.group(3)}"
            if wert and kennung not in vorhandene_ids:
                vorschlaege.append(
                    {"id": kennung, "bezeichnung": bezeichnung, "wert": wert, "art": "Merkmal", "status": "Zu prüfen"}
                )
        if datei is not None:
            vorhandene_ids = {wert["id"] for wert in vorschlaege}
            vorschlaege.extend(
                wert
                for wert in _betragsvorschlaege_aus_bild(datei)
                if wert["id"] not in vorhandene_ids
            )
    return vorschlaege


def pruefhinweise(dokumenttyp: str) -> tuple[str, ...]:
    """Nennt nur Prüfpunkte; es werden keine Dokumentdaten gespeichert."""
    if dokumenttyp.startswith("Notiz – "):
        return (
            "Nur als persönliche Information verwenden, nicht als amtlichen Nachweis",
            "Angaben vor einer steuerlichen Übernahme mit dem Originalbeleg abgleichen",
        )
    hinweise = {
        "Elektronische Lohnsteuerbescheinigung": (
            "Steuerjahr, Arbeitgeber und Steuerklasse pruefen",
            "Bruttoarbeitslohn und einbehaltene Lohnsteuer vergleichen",
            "Angaben zu Kranken-, Pflege-, Renten- und Arbeitslosenversicherung pruefen",
        ),
        "Anlage Vorsorgeaufwand": (
            "Steuerjahr und zugeordnete Person prüfen",
            "Beiträge, Erstattungen und Arbeitgeberzuschüsse getrennt vergleichen",
            "Historische Werte nicht für ein aktuelles Steuerjahr oder ELSTER übernehmen",
        ),
        "Grundsteuerbescheid oder Grundsteuerunterlage": (
            "Grundstueck oder Wohnung eindeutig zuordnen",
            "Zeitraum und festgesetzten Betrag pruefen",
            "Bei Vermietung: mietvertragliche Betriebskostenregelung pruefen",
        ),
        "Grundsteuerwertbescheid": (
            "Aktenzeichen, Grundstück und Hauptfeststellungszeitpunkt prüfen",
            "Flächen, Grundstücksart und Bewertungsangaben mit den eingereichten Daten vergleichen",
            "Bekanntgabedatum für eine mögliche Rechtsbehelfsfrist festhalten",
        ),
        "Grundsteueräquivalenzbetragsbescheid": (
            "Aktenzeichen, Grundstück und Hauptfeststellungszeitpunkt prüfen",
            "Grundstücks-, Wohn- und Nutzflächen mit der bayerischen Grundsteuererklärung vergleichen",
            "Bekanntgabedatum für eine mögliche Rechtsbehelfsfrist festhalten",
        ),
        "Grundsteuermessbescheid": (
            "Grundsteuerwert und Steuermesszahl mit dem Wertbescheid vergleichen",
            "Grundsteuermessbetrag nachvollziehen",
            "Bekanntgabedatum für eine mögliche Rechtsbehelfsfrist festhalten",
        ),
        "Kommunaler Grundsteuerbescheid": (
            "Grundsteuermessbetrag mit dem Finanzamtsbescheid vergleichen",
            "Kommunalen Hebesatz und Jahresbetrag prüfen",
            "Fälligkeitstermine und Bescheiddatum festhalten",
        ),
        "Rentenbezugsmitteilung": (
            "Rentenart, Rentenbeginn und Leistungsbetrag prüfen",
            "Kranken- und Pflegeversicherungsbeiträge sowie Nachzahlungen beachten",
            "Steuerjahr eindeutig zuordnen",
        ),
        "Insolvenzgeldbescheinigung": (
            "Insolvenzereignis und bescheinigten Dreimonatszeitraum prüfen",
            "Offenes Brutto- und Nettoarbeitsentgelt mit den letzten Verdienstabrechnungen vergleichen",
            "Auszahlungsbetrag und Steuerjahr für den Progressionsvorbehalt festhalten",
        ),
        "Erbschaft- oder Schenkungsteuerbescheid": (
            "Erwerber, Erblasser oder Schenker und Steuerentstehungszeitpunkt prüfen",
            "Steuerklasse, Freibeträge und steuerpflichtigen Erwerb nachvollziehen",
            "Bekanntgabedatum für eine mögliche Rechtsbehelfsfrist festhalten",
        ),
        "Erbschein": (
            "Erblasser, Erben und Erbquoten mit dem Nachlassfall abgleichen",
            "Ausstellungsdatum und zuständiges Nachlassgericht festhalten",
        ),
        "Testament oder Erbvertrag": (
            "Erblasser, Bedachte, Vermächtnisse und Auflagen erfassen",
            "Eröffnungsprotokoll und spätere Verfügungen mitprüfen",
        ),
        "Nachlassaufstellung": (
            "Vermögenswerte und Bewertungsstichtag dokumentieren",
            "Nachlassverbindlichkeiten und zugehörige Nachweise getrennt erfassen",
        ),
        "Kapitalertragsteuerbescheinigung": (
            "Kapitalerträge und einbehaltene Steuern prüfen",
            "Freistellungsauftrag und Verlustverrechnung beachten",
            "Prüfen, ob eine Anlage KAP erforderlich oder sinnvoll ist",
        ),
        "Kinderbetreuungskosten": (
            "Name des Kindes, Betreuungszeitraum und Leistungsart prüfen",
            "Rechnung oder Vertrag und unbare Zahlung nachweisen",
            "Verpflegungs- und Unterrichtsanteile getrennt betrachten",
        ),
        "Handwerker- oder haushaltsnahe Dienstleistung": (
            "Arbeits-, Maschinen- und Fahrtkosten getrennt vom Material prüfen",
            "Rechnung und unbare Zahlung nachweisen",
            "Leistungsort im eigenen Haushalt prüfen",
        ),
        "Kranken- und Pflegeversicherungsbescheinigung": (
            "Basisbeiträge, Zusatzleistungen und Erstattungen unterscheiden",
            "Arbeitgeber- oder Rentenversicherungsträger-Zuschüsse prüfen",
            "Beitragsjahr eindeutig zuordnen",
        ),
        "ELSTER-Übertragungsprotokoll": (
            "Steuerjahr und Übermittlungszeitpunkt prüfen",
            "Übertragene Anlagen und Angaben auf Vollständigkeit prüfen",
            "Protokoll ist kein Steuerbescheid; späteren Bescheid gesondert vergleichen",
        ),
        "Mietvertrag": (
            "Mietobjekt, Beginn und vereinbarte Miete pruefen",
            "Vereinbarung zu Betriebskosten und Grundsteuer pruefen",
            "Bei verbilligter Vermietung: Vergleich zur ortsueblichen Miete vormerken",
        ),
        "Darlehenszinsbescheinigung": (
            "Bescheinigten Zeitraum und Darlehenskonto prüfen",
            "Schuldzinsen getrennt von Tilgung und sonstigen Kosten erfassen",
            "Darlehen und Zinsen eindeutig dem vermieteten Objekt zuordnen",
        ),
        "Betriebskostenabrechnung": (
            "Abrechnungszeitraum und Verteilerschluessel pruefen",
            "Grundsteuer und weitere umlagefaehige Positionen pruefen",
            "Vorauszahlungen, Nachzahlung oder Guthaben vergleichen",
        ),
        "Sonstige Versicherungsunterlage": (
            "Versicherungsart und Beitragsjahr pruefen",
            "Gezahlte Beitraege, Erstattungen und Zuschuesse festhalten",
            "Pruefen, ob die Unterlage zur privaten Vorsorge oder Vermietung gehoert",
        ),
        "Sonstige Rechnung": (
            "Rechnungsdatum, Leistung und Betrag pruefen",
            "Pruefen, welchem Mietobjekt oder Bereich die Ausgabe zuzuordnen ist",
            "Beleg unveraendert aufbewahren",
        ),
        "Schornsteinfegerrechnung": (
            "Rechnungsdatum, Leistungszeitraum und Gesamtbetrag prüfen",
            "Arbeits-, Fahrt- und Messkosten für § 35a EStG prüfen",
            "Unbare Zahlung und Zuordnung zum Gebäude nachweisen",
        ),
        "Gebäudeversicherungsunterlage": (
            "Versicherungszeitraum und Gebäude eindeutig zuordnen",
            "Wohn-, Gewerbe- und Grundstücksangaben als Stammdaten prüfen",
            "Beitrag nur dem passenden Steuerjahr und Mietobjekt zuordnen",
        ),
        "Historische Grundstücks- und Gebäudedaten": (
            "Nur Grundstücks-, Gebäude-, Flächen- und Anschaffungsdaten übernehmen",
            "Das Quelljahr 2010 nicht als aktuelles Steuerjahr verwenden",
            "Historische Beträge und AfA-Grundlagen am Original prüfen",
        ),
        "Historische Einkommensteuererklärung": (
            "Nur als historische Vergleichsunterlage verwenden",
            "Das Quelljahr nicht als aktuelles Steuerjahr übernehmen",
            "Namen, Anlagen und damalige Angaben am Original prüfen",
        ),
        "Einkommensteuerbescheid": (
            "Steuerjahr, Bescheiddatum und festgesetzten Betrag pruefen",
            "Abweichungen zur abgegebenen Erklaerung markieren",
            "Fristen fuer einen moeglichen Einspruch gesondert pruefen",
        ),
    }
    return hinweise.get(
        dokumenttyp,
        ("Dokumenttyp und Steuerjahr pruefen", "Beleg unveraendert aufbewahren"),
    )


def dokument_id(datei: Path) -> str:
    return hashlib.sha256(str(datei.resolve()).casefold().encode("utf-8")).hexdigest()[:20]


def _register_lesen() -> dict[str, dict]:
    registerdatei = _dokumentregister_datei()
    try:
        daten = json.loads(registerdatei.read_text(encoding="utf-8"))
        return daten if isinstance(daten, dict) else {}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}


def _register_schreiben(daten: dict[str, dict]) -> None:
    registerdatei = _dokumentregister_datei()
    registerdatei.parent.mkdir(parents=True, exist_ok=True)
    temp = registerdatei.with_suffix(".tmp")
    temp.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(registerdatei)


def _bereinige_notiz_angaben(angaben) -> list[dict]:
    """Bewahrt wenige kuratierte Notizangaben als reine Information auf."""
    if not isinstance(angaben, list):
        return []
    ergebnis: list[dict] = []
    for angabe in angaben:
        if not isinstance(angabe, dict):
            continue
        bezeichnung = str(angabe.get("bezeichnung", "")).strip()[:120]
        wert = str(angabe.get("wert", "")).strip()[:240]
        if not bezeichnung or not wert:
            continue
        ergebnis.append(
            {
                "bezeichnung": bezeichnung,
                "wert": wert,
                "status": "Aus Notiz übernommen",
                "verwendung": "Nur Information – Originalnachweis erforderlich",
            }
        )
        if len(ergebnis) >= 12:
            break
    return ergebnis


def ist_unveraendert_registriert(datei: Path, stand: DateiStand) -> bool:
    """Vermeidet teure erneute OCR für bereits vollständig erfasste Dateien."""
    with REGISTER_SPERRE:
        eintrag = _register_lesen().get(dokument_id(datei), {})
    zuordnung_aktuell = nutzerverwaltung.aktiver_nutzer() is None or "nutzerzuordnung" in eintrag
    return (
        bool(eintrag)
        and int(eintrag.get("groesse", -1)) == stand.groesse
        and int(eintrag.get("geaendert_ns", -1)) == stand.geaendert_ns
        and bool(eintrag.get("dokumenttyp"))
        and zuordnung_aktuell
    )


def speichere_erkennung(
    datei: Path,
    stand: DateiStand,
    dokumenttyp: str,
    grundlage: str,
    ocr_status: str,
    steuerjahr: str,
    wertvorschlaege: list[dict] | None = None,
    nutzerzuordnung: dict | None = None,
) -> dict:
    """Speichert Metadaten und wenige strukturierte Angaben, nie den Dokumenttext."""
    kennung = dokument_id(datei)
    with REGISTER_SPERRE:
        register = _register_lesen()
        bisher = register.get(kennung, {})
        manuell = bool(bisher.get("manuell"))
        vision_typ_beibehalten = (
            not manuell
            and dokumenttyp == "Unbekannte Unterlage"
            and str(bisher.get("grundlage", "")).startswith("Lokale Bildprüfung")
            and str(bisher.get("dokumenttyp", "")) not in {"", "Unbekannte Unterlage"}
        )
        gespeicherter_typ = (
            str(bisher.get("dokumenttyp"))
            if manuell or vision_typ_beibehalten
            else dokumenttyp
        )
        gespeicherte_grundlage = (
            "Manuell bestätigt"
            if manuell
            else str(bisher.get("grundlage"))
            if vision_typ_beibehalten
            else grundlage
        )
        alte_werte = {
            wert.get("id"): wert
            for wert in bisher.get("wertvorschlaege", [])
            if isinstance(wert, dict) and wert.get("id")
        }
        neue_werte = []
        for wert in wertvorschlaege or []:
            alt = alte_werte.get(wert.get("id"))
            if alt and alt.get("status") in {"Bestätigt", "Verworfen"}:
                # Eine bewusste Nutzerentscheidung wird durch einen späteren
                # OCR-Lauf weder ersetzt noch wieder aktiviert.
                wert = alt
            else:
                wert = {**wert, "status": "Bestätigt"}
            neue_werte.append(wert)
        neue_ids = {str(wert.get("id")) for wert in neue_werte}
        neue_werte.extend(
            wert
            for kennung, wert in alte_werte.items()
            if str(kennung) not in neue_ids and wert.get("status") == "Bestätigt"
        )
        gespeicherte_zuordnung = (
            bisher.get("nutzerzuordnung", nutzerzuordnung or {})
            if bool(bisher.get("nutzerzuordnung", {}).get("bestaetigt"))
            else (nutzerzuordnung or {})
        )
        if gespeicherte_zuordnung.get("status") == "Erkannt":
            gespeicherte_zuordnung = {
                **gespeicherte_zuordnung,
                "status": "Bestätigt",
                "bestaetigt": True,
                "hinweis": "Die eindeutig erkannte Person wurde automatisch zugeordnet.",
            }
        eintrag = {
            "id": kennung,
            "dateiname": datei.name,
            "pfad": str(datei.resolve()),
            "dokumenttyp": gespeicherter_typ,
            "steuerjahr": bisher.get("steuerjahr", steuerjahr) if manuell else steuerjahr,
            "grundlage": gespeicherte_grundlage,
            "ocr_status": ocr_status,
            "groesse": stand.groesse,
            "geaendert_ns": stand.geaendert_ns,
            "status": "Unklar" if gespeicherter_typ == "Unbekannte Unterlage" else "Geprüft",
            "manuell": manuell,
            "pruefhinweise": list(pruefhinweise(gespeicherter_typ)),
            "erfasste_inhalte": [
                str(angabe).strip()[:240]
                for angabe in bisher.get("erfasste_inhalte", [])
                if str(angabe).strip()
            ][:8],
            "notiz_angaben": _bereinige_notiz_angaben(bisher.get("notiz_angaben", [])),
            "notiz_geprueft_am": (
                str(bisher.get("notiz_geprueft_am", ""))[:10]
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(bisher.get("notiz_geprueft_am", "")))
                else ""
            ),
            "vision_status": str(bisher.get("vision_status", ""))[:500],
            "vision_automatisch_versucht_am": str(
                bisher.get("vision_automatisch_versucht_am", "")
            )[:32],
            "steuer_id_status": str(bisher.get("steuer_id_status", ""))[:240],
            "wertvorschlaege": neue_werte,
            "nutzerzuordnung": gespeicherte_zuordnung,
            "erkannt_am": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        register[kennung] = eintrag
        _register_schreiben(register)
        return eintrag


def erkannte_daten_uebernehmen() -> dict[str, int]:
    """Überführt bereits gespeicherte, eindeutig erkannte Angaben in den übernommenen Zustand."""
    zaehler = {"dokumente": 0, "werte": 0, "zuordnungen": 0}
    with REGISTER_SPERRE:
        register = _register_lesen()
        geaendert = False
        for eintrag in register.values():
            if not isinstance(eintrag, dict):
                continue
            dokumenttyp = str(eintrag.get("dokumenttyp", "Unbekannte Unterlage"))
            zielstatus = "Unklar" if dokumenttyp == "Unbekannte Unterlage" else "Geprüft"
            if eintrag.get("status") != zielstatus:
                eintrag["status"] = zielstatus
                zaehler["dokumente"] += 1
                geaendert = True
            for wert in eintrag.get("wertvorschlaege", []):
                if not isinstance(wert, dict) or wert.get("status") in {"Bestätigt", "Verworfen"}:
                    continue
                wert["status"] = "Bestätigt"
                zaehler["werte"] += 1
                geaendert = True
            zuordnung = eintrag.get("nutzerzuordnung")
            if isinstance(zuordnung, dict) and zuordnung.get("status") == "Erkannt":
                zuordnung.update(
                    status="Bestätigt",
                    bestaetigt=True,
                    hinweis="Die eindeutig erkannte Person wurde automatisch zugeordnet.",
                )
                zaehler["zuordnungen"] += 1
                geaendert = True
        if geaendert:
            _register_schreiben(register)
    return zaehler


def dokumentuebersicht() -> list[dict]:
    eingang = aktueller_eingang()
    vorhandene = finde_dateien(eingang)
    with REGISTER_SPERRE:
        register = _register_lesen()
    nach_pfad: dict[Path, dict] = {}
    for eintrag in register.values():
        try:
            pfad = Path(str(eintrag.get("pfad", ""))).resolve()
            pfad.relative_to(eingang)
        except (OSError, ValueError):
            continue
        if pfad in vorhandene:
            bisher = nach_pfad.get(pfad)
            if bisher is None:
                nach_pfad[pfad] = eintrag
                continue
            # Nach einer Altbestandsmigration kann derselbe Beleg unter einer alten
            # und einer neuen Kennung stehen. Für die Anzeige gewinnt der vollständigere
            # Eintrag; die Originaldatei und das Register werden nicht gelöscht.
            def vollstaendigkeit(kandidat: dict) -> tuple[int, str]:
                return (
                    int(bool(kandidat.get("nutzerzuordnung")))
                    + int(bool(kandidat.get("wertvorschlaege")))
                    + int(bool(kandidat.get("notiz_angaben")))
                    + int(bool(kandidat.get("manuell"))),
                    str(kandidat.get("erkannt_am", "")),
                )

            if vollstaendigkeit(eintrag) > vollstaendigkeit(bisher):
                nach_pfad[pfad] = eintrag
    ergebnis = list(nach_pfad.values())
    return sorted(ergebnis, key=lambda eintrag: str(eintrag.get("dateiname", "")).casefold())


def persoenliche_steuerdaten(steuerjahr: str) -> list[dict]:
    persoenliche_ids = {
        "steuerklasse",
        "faktor",
        "kinderfreibetrag",
        "kirchensteuermerkmal",
        "beschaeftigungszeitraum",
        "grossbuchstaben",
    }
    ergebnis = []
    for dokument in dokumentuebersicht():
        if dokument.get("steuerjahr") not in {steuerjahr, "Nicht erkannt", ""}:
            continue
        for wert in dokument.get("wertvorschlaege", []):
            if wert.get("id") not in persoenliche_ids:
                continue
            ergebnis.append(
                {
                    **wert,
                    "dokument_id": dokument.get("id"),
                    "dateiname": dokument.get("dateiname"),
                    "steuerjahr": dokument.get("steuerjahr"),
                }
            )
    return sorted(ergebnis, key=lambda wert: (str(wert.get("bezeichnung", "")), str(wert.get("dateiname", ""))))


def dokument_aktualisieren(kennung: str, status: str, dokumenttyp: str | None = None, steuerjahr: str | None = None) -> dict:
    erlaubte_status = {"Zu prüfen", "Geprüft", "Unklar"}
    if status not in erlaubte_status:
        raise ValueError("Unbekannter Dokumentstatus.")
    with REGISTER_SPERRE:
        register = _register_lesen()
        if kennung not in register:
            raise ValueError("Das Dokument wurde nicht gefunden.")
        eintrag = register[kennung]
        if dokumenttyp is not None:
            dokumenttyp = dokumenttyp.strip()
            if not dokumenttyp or len(dokumenttyp) > 120:
                raise ValueError("Bitte gib einen gültigen Dokumenttyp ein.")
            eintrag["dokumenttyp"] = dokumenttyp
            eintrag["manuell"] = True
            eintrag["grundlage"] = "Manuell bestätigt"
            eintrag["pruefhinweise"] = list(pruefhinweise(dokumenttyp))
        if steuerjahr is not None:
            steuerjahr = steuerjahr.strip()
            if steuerjahr and not re.fullmatch(r"(?:19|20)\d{2}|Nicht erkannt", steuerjahr):
                raise ValueError("Bitte gib ein gültiges vierstelliges Steuerjahr ein.")
            eintrag["steuerjahr"] = steuerjahr or "Nicht erkannt"
            eintrag["manuell"] = True
        eintrag["status"] = status
        register[kennung] = eintrag
        _register_schreiben(register)
        return eintrag


def wertvorschlag_aktualisieren(kennung: str, wert_id: str, status: str) -> dict:
    if status not in {"Zu prüfen", "Bestätigt", "Verworfen"}:
        raise ValueError("Unbekannter Wertstatus.")
    with REGISTER_SPERRE:
        register = _register_lesen()
        if kennung not in register:
            raise ValueError("Das Dokument wurde nicht gefunden.")
        eintrag = register[kennung]
        gefunden = False
        for wert in eintrag.get("wertvorschlaege", []):
            if wert.get("id") == wert_id:
                wert["status"] = status
                gefunden = True
                break
        if not gefunden:
            raise ValueError("Der Wertvorschlag wurde nicht gefunden.")
        register[kennung] = eintrag
        _register_schreiben(register)
        return eintrag


VISION_DOKUMENTTYPEN = (
    "Elektronische Lohnsteuerbescheinigung",
    "Anlage Vorsorgeaufwand",
    "Arbeitslosengeldbescheinigung",
    "Insolvenzgeldbescheinigung",
    "Mietvertrag",
    "Darlehenszinsbescheinigung",
    "Gebäudeversicherungsunterlage",
    "Handwerker- oder haushaltsnahe Dienstleistung",
    "Schornsteinfegerrechnung",
    "Historische Einkommensteuererklärung",
    "Historische Grundstücks- und Gebäudedaten",
    "Notiz – Versicherungen",
    "Notiz – Insolvenzgeld",
    "Notiz – Vermietung",
    "Sonstige Rechnung",
    "Unbekannte Unterlage",
)

VISION_PROMPT = (
    "Prüfe dieses Steuerdokument oder diese handschriftliche Notiz lokal. "
    "Die erste Zeile muss exakt 'Dokumentart: <Art>' lauten. Verwende nur eine dieser Arten: "
    "Elektronische Lohnsteuerbescheinigung; Arbeitslosengeldbescheinigung; "
    "Insolvenzgeldbescheinigung; Mietvertrag; Darlehenszinsbescheinigung; "
    "Gebäudeversicherungsunterlage; Handwerker- oder haushaltsnahe Dienstleistung; "
    "Schornsteinfegerrechnung; Historische Einkommensteuererklärung; "
    "Historische Grundstücks- und Gebäudedaten; Notiz – Versicherungen; "
    "Notiz – Insolvenzgeld; Notiz – Vermietung; Sonstige Rechnung; Unbekannte Unterlage. "
    "Wähle Unbekannte Unterlage, wenn die Art nicht klar erkennbar ist. "
    "Lies danach ausschließlich klar erkennbare Werte. "
    "Antworte für Werte zeilenweise im Format Bezeichnung: Wert. Zulässige Bezeichnungen sind: "
    "Grundstücksfläche, Wohnfläche, Baujahr, Wohneinheiten, Anschaffungskosten, "
    "Anteil Grund und Boden, Gebäudewert, Rechnungsbetrag, Arbeitskosten und Steuer-ID. "
    "Eine Steuer-ID darfst du nur als 11 Ziffern ausgeben, wenn neben der Nummer ausdrücklich "
    "Steuer-ID, Identifikationsnummer oder IdNr. steht. Nenne unklare oder fehlende Werte nicht "
    "und gib keine Namen, Adressen, Steuernummern oder Kontodaten aus. Erfinde nichts."
)


def _steuer_id_status_speichern(kennung: str, status: str) -> dict:
    with REGISTER_SPERRE:
        register = _register_lesen()
        if kennung not in register:
            raise ValueError("Das Dokument wurde nicht gefunden.")
        eintrag = register[kennung]
        eintrag["steuer_id_status"] = status[:240]
        register[kennung] = eintrag
        _register_schreiben(register)
        return eintrag


def steuer_id_automatisch_uebernehmen(kennung: str, text: str) -> dict | None:
    """Speichert eine eindeutig erkannte Steuer-ID bestätigt und verschlüsselt."""
    steuer_id = erkenne_steuer_id(text)
    aktiver_nutzer = nutzerverwaltung.aktiver_nutzer()
    if steuer_id is None or aktiver_nutzer is None:
        return None
    with REGISTER_SPERRE:
        eintrag = _register_lesen().get(kennung, {})
    zuordnung = eintrag.get("nutzerzuordnung", {})
    passt = bool(zuordnung.get("bestaetigt")) or (
        zuordnung.get("status") == "Erkannt"
        and str(zuordnung.get("erkannter_nutzer_id", "")) == str(aktiver_nutzer.get("id", ""))
    )
    if not passt:
        return _steuer_id_status_speichern(
            kennung,
            "Steuer-ID erkannt, aber die Person ist noch nicht eindeutig diesem Profil zugeordnet.",
        )
    datei = nutzerverwaltung.datenordner() / STAMMDATEN_DATEINAME
    vorhanden = str(lade_stammdaten(datei).get("steuer_id", ""))
    if vorhanden and vorhanden != steuer_id:
        return _steuer_id_status_speichern(
            kennung,
            "Eine abweichende Steuer-ID wurde erkannt und nicht überschrieben.",
        )
    speichere_stammdaten(datei, {"steuer_id": steuer_id})
    return _steuer_id_status_speichern(
        kennung,
        "Steuer-ID erkannt, bestätigt und verschlüsselt im Profil gespeichert.",
    )


def automatische_vision_noetig(
    datei: Path,
    ocr_text: str,
    ocr_status: str,
    dokumenttyp: str,
    wertvorschlaege: list[dict],
    bisher: dict | None = None,
) -> bool:
    """Entscheidet konservativ, ob ein Bild einmal lokal nachgelesen werden soll."""
    if datei.suffix.lower() not in BILD_ENDUNGEN:
        return False
    if str((bisher or {}).get("vision_automatisch_versucht_am", "")).strip():
        return False
    status = normalisiere(ocr_status)
    if not ocr_text.strip() or "konnte" in status or "nicht vollstandig" in status:
        return True
    if dokumenttyp == "Unbekannte Unterlage":
        return True

    woerter = re.findall(r"\b[a-z0-9]{3,}\b", normalisiere(ocr_text))
    zeichen = sum(zeichen.isalnum() for zeichen in ocr_text)
    if len(woerter) < 35 or zeichen < 260:
        return True
    wertrelevante_typen = {
        "Mietvertrag",
        "Gebäudeversicherungsunterlage",
        "Schornsteinfegerrechnung",
        "Sonstige Rechnung",
        "Historische Grundstücks- und Gebäudedaten",
        "Notiz – Vermietung",
    }
    return dokumenttyp in wertrelevante_typen and not wertvorschlaege and len(woerter) < 120


def _vision_status_speichern(kennung: str, status: str, *, versucht: bool = False) -> dict:
    with REGISTER_SPERRE:
        register = _register_lesen()
        if kennung not in register:
            raise ValueError("Das Dokument wurde nicht gefunden.")
        eintrag = register[kennung]
        eintrag["vision_status"] = status[:500]
        if versucht:
            eintrag["vision_automatisch_versucht_am"] = datetime.now().astimezone().isoformat(
                timespec="seconds"
            )
        register[kennung] = eintrag
        _register_schreiben(register)
        return eintrag


def dokument_vision_pruefen(kennung: str, *, automatisch: bool = False) -> dict:
    """Führt die streng begrenzte lokale Vision-Zweitprüfung eines Bildes aus."""
    dokument = next((d for d in dokumentuebersicht() if d.get("id") == kennung), None)
    if dokument is None:
        raise ValueError("Das Dokument wurde nicht gefunden.")
    pfad = Path(str(dokument.get("pfad", "")))
    if pfad.suffix.lower() not in BILD_ENDUNGEN or not pfad.is_file():
        raise ValueError("Die genauere Prüfung ist nur für vorhandene Bilddateien möglich.")
    if automatisch:
        _vision_status_speichern(
            kennung,
            "Schwache OCR erkannt – automatische lokale Bildprüfung läuft.",
            versucht=True,
        )

    from modell_ressourcen import MODELL_RESSOURCEN

    antwort = MODELL_RESSOURCEN.vision_chat(
        "steuer-assistent-pilot13:bf16",
        [{"role": "user", "content": VISION_PROMPT, "images": [str(pfad.resolve())]}],
        options={"temperature": 0, "num_predict": 256},
        fallback_modell="qwen3.5:9b",
    )
    text = str((antwort.get("message") or {}).get("content", ""))
    steuer_id_automatisch_uebernehmen(kennung, text)
    eintrag = vision_wertvorschlaege_uebernehmen(kennung, text)
    if automatisch:
        eintrag = _vision_status_speichern(
            kennung,
            str(eintrag.get("vision_status", "Lokale Bildprüfung abgeschlossen."))
            + " Automatisch wegen schwacher OCR ausgeführt.",
        )
    return eintrag


def _vision_dokumenttyp_vorschlag(vision_text: str) -> str | None:
    """Akzeptiert nur eine explizite Dokumentart aus der festen lokalen Auswahlliste."""
    treffer = re.search(r"(?im)^\s*dokumentart\s*:\s*([^\r\n]+)", vision_text)
    if not treffer:
        return None
    kandidat = normalisiere(treffer.group(1)).strip(" .-:")
    aliases = {
        "versicherungsnotiz": "Notiz – Versicherungen",
        "notiz versicherungen": "Notiz – Versicherungen",
        "informationsnotiz versicherungen": "Notiz – Versicherungen",
        "insolvenzgeldnotiz": "Notiz – Insolvenzgeld",
        "informationsnotiz insolvenzgeld": "Notiz – Insolvenzgeld",
        "vermietungsnotiz": "Notiz – Vermietung",
        "informationsnotiz vermietung": "Notiz – Vermietung",
        "historische anlage v": "Historische Grundstücks- und Gebäudedaten",
    }
    if kandidat in aliases:
        return aliases[kandidat]
    return next((typ for typ in VISION_DOKUMENTTYPEN if normalisiere(typ) == kandidat), None)


def vision_wertvorschlaege_uebernehmen(kennung: str, vision_text: str) -> dict:
    """Übernimmt ausschließlich klar erkannte Vision-Werte automatisch."""
    with REGISTER_SPERRE:
        register = _register_lesen()
        if kennung not in register:
            raise ValueError("Das Dokument wurde nicht gefunden.")
        eintrag = register[kennung]
        datei = Path(str(eintrag.get("pfad", "")))
        if datei.suffix.lower() not in BILD_ENDUNGEN or not datei.is_file():
            raise ValueError("Die genauere Prüfung ist nur für vorhandene Bilddateien möglich.")
        bisheriger_typ = str(eintrag.get("dokumenttyp", "Unbekannte Unterlage"))
        typ_vorschlag = _vision_dokumenttyp_vorschlag(vision_text)
        if bisheriger_typ == "Unbekannte Unterlage" and typ_vorschlag not in {None, "Unbekannte Unterlage"}:
            eintrag["dokumenttyp"] = typ_vorschlag
            eintrag["grundlage"] = "Lokale Bildprüfung"
            eintrag["status"] = "Geprüft"
            eintrag["pruefhinweise"] = list(pruefhinweise(typ_vorschlag))
        verwendeter_typ = str(eintrag.get("dokumenttyp", "Unbekannte Unterlage"))
        neue_werte = (
            []
            if verwendeter_typ.startswith("Notiz – ")
            else extrahiere_wertvorschlaege(verwendeter_typ, vision_text)
        )
        vorhandene = {
            str(wert.get("id")): wert
            for wert in eintrag.get("wertvorschlaege", [])
            if isinstance(wert, dict) and wert.get("id")
        }
        for wert in neue_werte:
            alt = vorhandene.get(str(wert.get("id")))
            if alt and alt.get("status") in {"Bestätigt", "Verworfen"}:
                continue
            wert["status"] = "Bestätigt"
            wert["grundlage"] = "Lokale Vision-Prüfung"
            vorhandene[str(wert["id"])] = wert
        eintrag["wertvorschlaege"] = list(vorhandene.values())
        meldungen = []
        if bisheriger_typ == "Unbekannte Unterlage" and verwendeter_typ != bisheriger_typ:
            meldungen.append(f"Dokumentart erkannt und übernommen: {verwendeter_typ}.")
        meldungen.append(f"{len(neue_werte)} Wert(e) erkannt und übernommen.")
        eintrag["vision_status"] = "Lokale Bildprüfung abgeschlossen: " + " ".join(meldungen)
        register[kennung] = eintrag
        _register_schreiben(register)
        return eintrag


def dokument_nutzer_bestaetigen(kennung: str) -> dict:
    """Bestätigt bewusst die Zuordnung zum aktuell geöffneten Nutzerprofil."""
    aktiv = nutzerverwaltung.aktiver_nutzer()
    if aktiv is None:
        raise ValueError("Es ist kein Nutzerprofil geöffnet.")
    with REGISTER_SPERRE:
        register = _register_lesen()
        if kennung not in register:
            raise ValueError("Das Dokument wurde nicht gefunden.")
        eintrag = register[kennung]
        eintrag["nutzerzuordnung"] = {
            "status": "Bestätigt",
            "aktiver_nutzer_id": str(aktiv["id"]),
            "aktiver_name": str(aktiv["name"]),
            "erkannter_nutzer_id": str(aktiv["id"]),
            "erkannter_name": str(aktiv["name"]),
            "bestaetigt": True,
            "hinweis": f"Die Zuordnung zu {aktiv['name']} wurde manuell bestätigt.",
        }
        register[kennung] = eintrag
        _register_schreiben(register)
        return eintrag


def ausgabe_neue_datei(datei: Path, stand: DateiStand) -> None:
    dokumenttyp, grundlage, ocr_status, steuerjahr, dokumenttext = erkenne_dokumenttyp(datei, mit_text=True)
    with REGISTER_SPERRE:
        bisher = _register_lesen().get(dokument_id(datei), {})
    if bool(bisher.get("manuell")):
        dokumenttyp = str(bisher.get("dokumenttyp") or dokumenttyp)
        steuerjahr = str(bisher.get("steuerjahr") or steuerjahr)
        grundlage = "Manuell bestätigt"
    wertvorschlaege = extrahiere_wertvorschlaege(dokumenttyp, dokumenttext, datei)
    nutzerzuordnung = erkenne_nutzerzuordnung(dokumenttext)
    eintrag = speichere_erkennung(
        datei,
        stand,
        dokumenttyp,
        grundlage,
        ocr_status,
        steuerjahr,
        wertvorschlaege,
        nutzerzuordnung,
    )
    steuer_id_eintrag = steuer_id_automatisch_uebernehmen(eintrag["id"], dokumenttext)
    if steuer_id_eintrag is not None:
        eintrag = steuer_id_eintrag
    vision_automatisch = automatische_vision_noetig(
        datei,
        dokumenttext,
        ocr_status,
        dokumenttyp,
        wertvorschlaege,
        bisher,
    )
    if vision_automatisch:
        try:
            eintrag = dokument_vision_pruefen(eintrag["id"], automatisch=True)
        except (OSError, RuntimeError, ValueError):
            eintrag = _vision_status_speichern(
                eintrag["id"],
                "Automatische lokale Bildprüfung konnte nicht abgeschlossen werden; "
                "die normale OCR-Erfassung bleibt erhalten.",
                versucht=True,
            )
    print("\nNEUE UNTERLAGE ZUR PRUEFUNG")
    print(f"Datei: {format_weg(datei)}")
    print(f"Groesse: {stand.groesse} Byte")
    print(f"Dokumenttyp (Vorschlag): {eintrag.get('dokumenttyp', dokumenttyp)}")
    print(f"Erkennungsgrundlage: {eintrag.get('grundlage', grundlage)}")
    print(f"OCR-Status: {ocr_status}")
    print(f"Steuerjahr: {eintrag.get('steuerjahr', steuerjahr)}")
    print(
        f"Wertvorschlaege: {len(eintrag.get('wertvorschlaege', wertvorschlaege))} "
        "(nur lokal gespeichert, noch nicht bestaetigt)"
    )
    if vision_automatisch:
        print(f"Bildpruefung: {eintrag.get('vision_status', 'Automatisch ausgefuehrt')}")
    if nutzerzuordnung:
        print(f"Nutzerzuordnung: {nutzerzuordnung.get('status', 'Nicht erkannt')}")
    print("Pruefpunkte:")
    for hinweis in pruefhinweise(str(eintrag.get("dokumenttyp", dokumenttyp))):
        print(f"- {hinweis}")
    print(f"Vorgesehener Pruefordner: {format_weg(_pruefordner())}")
    print("Hinweis: Die Datei bleibt unveraendert im Eingang; erkannter Text wird nicht gespeichert oder ausgegeben.")


def ueberwache(
    intervall: float,
    einmalig: bool,
    startbereit: Event | None = None,
    neu_erkennen: bool = False,
) -> None:
    _standard_eingang().mkdir(parents=True, exist_ok=True)
    _pruefordner().mkdir(parents=True, exist_ok=True)
    eingang = aktueller_eingang()

    vorher = finde_dateien(eingang)
    bestaetigt: set[Path] = set()
    print("ORDNERUEBERWACHER GESTARTET")
    print(f"Eingang: {format_weg(eingang)}")
    print(f"Unterstuetzte Dateitypen: {', '.join(sorted(UNTERSTUETZTE_ENDUNGEN))}")
    print("Es werden keine Dateien verschoben, umbenannt oder geloescht.")

    if einmalig:
        if vorher:
            print(f"Vorhandene Unterlagen: {len(vorher)} (nur Bestandsanzeige)")
            for datei, stand in sorted(vorher.items()):
                if neu_erkennen or not ist_unveraendert_registriert(datei, stand):
                    ausgabe_neue_datei(datei, stand)
        else:
            print("Keine Unterlagen im Eingang gefunden.")
        return

    if vorher:
        neu_oder_geaendert = [
            (datei, stand)
            for datei, stand in sorted(vorher.items())
            if neu_erkennen or not ist_unveraendert_registriert(datei, stand)
        ]
        print(
            f"Vorhandene Unterlagen: {len(vorher)} "
            f"({len(neu_oder_geaendert)} neu oder geaendert)"
        )
        for datei, stand in neu_oder_geaendert:
            ausgabe_neue_datei(datei, stand)
        bestaetigt.update(vorher)

    print("Warte auf neue Unterlagen. Beenden mit Strg+C.")
    if startbereit is not None:
        startbereit.set()
    while True:
        time.sleep(intervall)
        neuer_eingang = aktueller_eingang()
        if neuer_eingang != eingang:
            eingang = neuer_eingang
            vorher = finde_dateien(eingang)
            bestaetigt.clear()
            print(f"\nEINGANGSORDNER GEÄNDERT: {format_weg(eingang)}")
            for datei, stand in sorted(vorher.items()):
                if not ist_unveraendert_registriert(datei, stand):
                    ausgabe_neue_datei(datei, stand)
            bestaetigt.update(vorher)
        aktuell = finde_dateien(eingang)

        for datei, stand in aktuell.items():
            if datei in bestaetigt:
                continue
            # Erst nach zwei identischen Messungen melden: Kopiervorgänge werden so abgewartet.
            if vorher.get(datei) == stand:
                bestaetigt.add(datei)
                ausgabe_neue_datei(datei, stand)

        vorher = aktuell


def main() -> None:
    parser = argparse.ArgumentParser(description="Überwacht neue Steuerunterlagen ohne sie zu verändern.")
    parser.add_argument(
        "--einmalig",
        action="store_true",
        help="Zeigt den aktuellen Bestand einmalig und beendet sich dann.",
    )
    parser.add_argument(
        "--intervall",
        type=float,
        default=2.0,
        help="Prüfintervall in Sekunden (Standard: 2).",
    )
    parser.add_argument(
        "--neu-erkennen",
        action="store_true",
        help="Wertet vorhandene Unterlagen erneut aus; manuelle Bestätigungen bleiben erhalten.",
    )
    args = parser.parse_args()
    if args.intervall <= 0:
        parser.error("--intervall muss groesser als 0 sein.")

    try:
        ueberwache(args.intervall, args.einmalig, neu_erkennen=args.neu_erkennen)
    except KeyboardInterrupt:
        print("\nOrdnerueberwacher beendet.")


if __name__ == "__main__":
    main()
