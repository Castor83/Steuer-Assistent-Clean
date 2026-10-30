"""Eng begrenzter Online-Fallback für amtliche deutsche Steuerquellen.

Die Suche liefert nur Kandidaten von Behörden, Gerichten und dem amtlichen
Gesetzesportal. Sie formuliert selbst keine Steuerantwort.
"""

from __future__ import annotations

from html.parser import HTMLParser
import re
from types import SimpleNamespace
from functools import lru_cache
from io import BytesIO
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import zipfile


ERLAUBTE_DOMAINS = (
    "gesetze-im-internet.de",
    "bundesfinanzministerium.de",
    "esth.bundesfinanzministerium.de",
    "ao.bundesfinanzministerium.de",
    "usth.bundesfinanzministerium.de",
    "elster.de",
    "arbeitsagentur.de",
    "deutsche-rentenversicherung.de",
    "bundesfinanzhof.de",
    "bundesverfassungsgericht.de",
    "zoll.de",
    "bund.de",
)

_STOPP = {
    "aber", "auch", "dann", "dass", "eine", "einen", "einer", "fur",
    "haben", "kann", "meine", "muss", "nicht", "oder", "sind", "steuer",
    "steuerlich", "und", "von", "wann", "welche", "wenn", "werden", "wird",
    "wurde", "zum", "zur",
}


def _normalisiere(text: str) -> str:
    text = text.casefold().replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("ß", "ss")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9§]+", " ", text)).strip()


def _begriffe(text: str) -> set[str]:
    return {
        wort for wort in re.findall(r"[a-z0-9§]{4,}", _normalisiere(text))
        if wort not in _STOPP and not wort.isdigit()
    }


def _amtlich(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == domain or host.endswith("." + domain) for domain in ERLAUBTE_DOMAINS)


class _TextLeser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ignorieren = 0
        self.teile: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "nav", "header", "footer", "svg"}:
            self.ignorieren += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "nav", "header", "footer", "svg"} and self.ignorieren:
            self.ignorieren -= 1

    def handle_data(self, data: str) -> None:
        if not self.ignorieren and data.strip():
            self.teile.append(data.strip())


def _abrufen(url: str, timeout: int = 10) -> str:
    anfrage = Request(url, headers={
        "User-Agent": "Steuer-Assistent/1.0 (amtliche Quellenpruefung)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.2",
    })
    with urlopen(anfrage, timeout=timeout) as antwort:
        typ = antwort.headers.get_content_type()
        roh = antwort.read(1_500_000)
        if typ == "application/pdf" or url.lower().endswith(".pdf"):
            return ""
        charset = antwort.headers.get_content_charset() or "utf-8"
    return roh.decode(charset, errors="replace")


def _abrufen_roh(url: str, timeout: int = 12) -> bytes:
    anfrage = Request(url, headers={
        "User-Agent": "Steuer-Assistent/1.0 (amtliche Quellenpruefung)",
        "Accept": "application/zip,application/xml,text/xml,*/*;q=0.2",
    })
    with urlopen(anfrage, timeout=timeout) as antwort:
        return antwort.read(8_000_000)


def _auszug(html: str, frage: str, hoechstens: int = 6500) -> str:
    leser = _TextLeser()
    leser.feed(html)
    text = re.sub(r"\s+", " ", " ".join(leser.teile)).strip()
    fragewoerter = _begriffe(frage)
    saetze = re.split(r"(?<=[.!?])\s+", text)
    bewertet = sorted(
        (
            (len(_begriffe(satz) & fragewoerter), nummer, satz)
            for nummer, satz in enumerate(saetze)
            if 40 <= len(satz) <= 1200
        ),
        reverse=True,
    )
    gewaehlt = [satz for treffer, _, satz in bewertet[:18] if treffer]
    return " ".join(gewaehlt)[:hoechstens]


_GESETZE = {
    "estg": "Einkommensteuergesetz",
    "estdv": "Einkommensteuer-Durchführungsverordnung",
    "ao_1977": "Abgabenordnung",
    "ustg_1980": "Umsatzsteuergesetz",
    "erbstg_1974": "Erbschaftsteuer- und Schenkungsteuergesetz",
    "gewstg": "Gewerbesteuergesetz",
    "grstg_1973": "Grundsteuergesetz",
    "kstg_1977": "Körperschaftsteuergesetz",
}


def _passende_gesetze(frage: str) -> list[str]:
    text = _normalisiere(frage)
    auswahl = ["estg"]
    routen = (
        (("einspruch", "festsetzung", "verspat", "frist", "steuerbescheid"), "ao_1977"),
        (("umsatzsteuer", "vorsteuer", "mehrwertsteuer"), "ustg_1980"),
        (("erbschaft", "schenkung", "nachlass"), "erbstg_1974"),
        (("gewerbesteuer",), "gewstg"),
        (("grundsteuer",), "grstg_1973"),
        (("korperschaftsteuer", "gmbh"), "kstg_1977"),
        (("verordnung", "nachweis", "gutachten"), "estdv"),
    )
    for signale, gesetz in routen:
        if any(signal in text for signal in signale) and gesetz not in auswahl:
            auswahl.insert(0, gesetz)
    return auswahl[:2]


@lru_cache(maxsize=12)
def _gesetzesnormen(gesetz: str) -> tuple[tuple[str, str], ...]:
    """Lädt den amtlichen XML-Gesamtbestand direkt vom Gesetzesportal."""
    url = f"https://www.gesetze-im-internet.de/{gesetz}/xml.zip"
    roh = _abrufen_roh(url)
    archiv = zipfile.ZipFile(BytesIO(roh))
    xml = archiv.read(archiv.namelist()[0])
    wurzel = ET.fromstring(xml)
    normen = []
    for norm in wurzel.findall(".//norm"):
        bezeichnung = " ".join(
            text.strip() for text in (
                norm.findtext("./metadaten/enbez") or "",
                norm.findtext("./metadaten/titel") or "",
            ) if text.strip()
        )
        inhalt = re.sub(r"\s+", " ", " ".join(norm.itertext())).strip()
        if bezeichnung and len(inhalt) >= 60:
            normen.append((bezeichnung, inhalt[:12000]))
    return tuple(normen)


@lru_cache(maxsize=1)
def _bmf_sitemap_urls() -> tuple[str, ...]:
    xml = _abrufen("https://www.bundesfinanzministerium.de/sitemap.xml", timeout=15)
    wurzel = ET.fromstring(xml)
    return tuple(
        element.text.strip() for element in wurzel.findall(".//{*}loc")
        if element.text and element.text.startswith("https://")
    )


def suche_amtliche_quellen(frage: str, steuerjahr: int | None, limit: int = 3) -> list:
    """Durchsucht Behördenbestände direkt, ohne eine allgemeine Suchmaschine."""
    fragewoerter = _begriffe(frage)
    bewertet: list[tuple[float, SimpleNamespace]] = []

    # Zuerst BMF-Seiten, deren URL bereits Thema und gewünschtes Jahr trägt.
    try:
        url_kandidaten = []
        for url in _bmf_sitemap_urls():
            urlwoerter = _begriffe(url)
            deckung = fragewoerter & urlwoerter
            if deckung and (steuerjahr is None or str(steuerjahr) in url):
                url_kandidaten.append((len(deckung), url))
        for _, url in sorted(url_kandidaten, reverse=True)[:8]:
            try:
                inhalt = _auszug(_abrufen(url), frage)
            except Exception:
                continue
            deckung = fragewoerter & _begriffe(inhalt)
            if not deckung:
                continue
            titel = url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ")
            quelle = SimpleNamespace(score=min(0.94, 0.6 + len(deckung) * 0.06), payload={
                "text": inhalt,
                "quelle": f"Bundesministerium der Finanzen – {titel}",
                "paragraph": "Amtliche BMF-Veröffentlichung",
                "steuerjahr": steuerjahr or "aktueller Stand",
                "kategorie": "Amtliche Internetquelle",
                "url": url,
                "gueltig_fuer": [steuerjahr] if steuerjahr is not None else [],
                "online_abgerufen": True,
            })
            bewertet.append((quelle.score, quelle))
    except Exception:
        pass

    # Danach die amtlichen XML-Fassungen der einschlägigen Kerngesetze.
    for gesetz in _passende_gesetze(frage):
        try:
            normen = _gesetzesnormen(gesetz)
        except Exception:
            continue
        for bezeichnung, inhalt in normen:
            deckung = fragewoerter & _begriffe(f"{bezeichnung} {inhalt}")
            if len(deckung) < min(2, max(1, len(fragewoerter))):
                continue
            # Aktuelles Bundesrecht darf nur dann für ein älteres ausgewähltes
            # Jahr dienen, wenn genau dieses Jahr im Normtext vorkommt.
            if steuerjahr is not None and str(steuerjahr) not in inhalt:
                continue
            url = f"https://www.gesetze-im-internet.de/{gesetz}/"
            quelle = SimpleNamespace(score=min(0.9, 0.52 + len(deckung) * 0.05), payload={
                "text": inhalt,
                "quelle": f"{_GESETZE[gesetz]} – {bezeichnung}",
                "paragraph": bezeichnung,
                "steuerjahr": steuerjahr or "aktueller Stand",
                "kategorie": "Amtliche Internetquelle",
                "url": url,
                "gueltig_fuer": [steuerjahr] if steuerjahr is not None else [],
                "online_abgerufen": True,
            })
            bewertet.append((quelle.score, quelle))

    bewertet.sort(key=lambda eintrag: eintrag[0], reverse=True)
    ergebnisse = []
    gesehen = set()
    for _, quelle in bewertet:
        schluessel = (quelle.payload["url"], quelle.payload["paragraph"])
        if schluessel in gesehen:
            continue
        gesehen.add(schluessel)
        ergebnisse.append(quelle)
        if len(ergebnisse) >= limit:
            break
    return ergebnisse
