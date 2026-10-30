"""Lokale Browser-Oberfläche für den Steuer-Assistenten."""

from __future__ import annotations

import os
import re
import time
from collections import defaultdict, deque
from datetime import timedelta
from io import BytesIO
from pathlib import Path

from flask import Flask, jsonify, make_response, redirect, render_template, request, send_file, session

from dialog_assistent import dialogantwort
from dokument_upload import MAX_UPLOAD_BYTES, speichere_upload
from elster_export import erstelle_elster_eingabehilfe, erstelle_elster_export_zip
from manuelle_steuerwerte import (
    DATEINAME as STEUERWERTE_DATEINAME,
    katalog_liste,
    wert_loeschen,
    wert_speichern,
    wert_status_setzen,
    werte_laden,
)
from ordner_ueberwacher import (
    VISION_PROMPT,
    aktueller_eingang,
    dokument_nutzer_bestaetigen,
    dokument_aktualisieren,
    dokumentuebersicht,
    persoenliche_steuerdaten,
    setze_eingang,
    standard_eingang_setzen,
    vision_wertvorschlaege_uebernehmen,
    wertvorschlag_aktualisieren,
)
from rag_assistent import BFH_TESTMODUS, beantworte, starte_ordnerueberwacher
from modell_ressourcen import MODELL_RESSOURCEN
from pruefbericht import erstelle_pruefbericht
from steuer_checkliste import erstelle_checkliste
from steuerakte import erstelle_steuerakten
from steuerprofil import lade_steuerprofil, profil_uebersicht
from stammdaten import (
    DATEINAME as STAMMDATEN_DATEINAME,
    lade_stammdaten,
    speichere_stammdaten,
    stammdaten_status,
)
from gespraechsverstaendnis import (
    interpretationsblock,
    kanonisierungs_hinweise,
    normalisiere_mit_tippfehlern,
)
import nutzerverwaltung
import authentifizierung


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES + 1024 * 1024
app.config["SECRET_KEY"] = authentifizierung.sitzungsschluessel()
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
MAX_FRAGE_ZEICHEN = 10_000
NUTZER_COOKIE = "steuer_assistent_nutzer"
HEIMNETZ_MODUS = os.environ.get("STEUER_ASSISTENT_HEIMNETZ") == "1"
ANMELDEVERSUCHE: dict[str, deque[float]] = defaultdict(deque)
ANMELDEFENSTER_SEKUNDEN = 5 * 60
ANMELDEVERSUCHE_MAXIMAL = 5
VORSCHAU_MIMETYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".txt": "text/plain; charset=utf-8",
    ".csv": "text/plain; charset=utf-8",
}


def ordnerueberwachung_sicherstellen(*, warten: bool = False) -> None:
    """Aktiviert die Überwachung erst bei einem echten Dokumentzugriff."""
    startbereit = starte_ordnerueberwacher()
    if warten:
        startbereit.wait(timeout=5)


@app.before_request
def nutzerkontext_setzen():
    """Bindet jede lokale API-Anfrage an den im Browser gewählten Nutzer."""
    if HEIMNETZ_MODUS and not app.testing:
        if request.path not in {"/anmelden", "/api/status"} and not session.get("angemeldet"):
            if request.path.startswith("/api/"):
                return jsonify(fehler="Bitte melde dich zuerst an."), 401
            return redirect("/anmelden")
    if request.path in {"/", "/anmelden", "/abmelden", "/api/status"} or request.path.startswith("/api/nutzer"):
        return None
    if app.testing:
        return None
    cookie_id = request.cookies.get(NUTZER_COOKIE)
    if HEIMNETZ_MODUS and session.get("rolle") != "admin":
        cookie_id = str(session.get("nutzer_id", ""))
    try:
        nutzerverwaltung.aktiven_nutzer_setzen(cookie_id)
    except ValueError:
        nutzerverwaltung.aktiven_nutzer_setzen(None)
    if request.path.startswith("/api/") and nutzerverwaltung.aktiver_nutzer() is None:
        return jsonify(fehler="Bitte wähle zuerst einen Nutzer aus."), 428
    return None


@app.after_request
def sicherheitsheader_setzen(antwort):
    antwort.headers["X-Content-Type-Options"] = "nosniff"
    if request.path.endswith("/vorschau"):
        antwort.headers["X-Frame-Options"] = "SAMEORIGIN"
        antwort.headers["Content-Security-Policy"] = "frame-ancestors 'self'"
    else:
        antwort.headers["X-Frame-Options"] = "DENY"
    antwort.headers["Referrer-Policy"] = "no-referrer"
    if request.path in {"/anmelden", "/abmelden"} or request.path.endswith("/vorschau"):
        antwort.headers["Cache-Control"] = "no-store"
    return antwort


def _nutzer_cookie_setzen(antwort, nutzer_id: str):
    antwort.set_cookie(
        NUTZER_COOKIE,
        nutzer_id,
        max_age=60 * 60 * 24 * 365 * 5,
        httponly=True,
        samesite="Strict",
    )
    return antwort


def frage_mit_gespraechskontext(frage: str, verlauf: list[dict]) -> str:
    """Verbindet kurze Ergänzungen mit der letzten Nutzerfrage, nicht mit beliebigen Altfragen."""
    text = frage.strip()
    normalisiert = normalisiere_mit_tippfehlern(text)
    folgesignale = (
        "ich bin", "ich habe", "bei mir", "mein haus", "meine wohnung",
        "das haus", "das objekt", "davon", "dafur", "dafür", "wenn das", "wenn alles",
        "auch wenn", "und wenn", "aber", "das war", "das ist", "die hat", "der hat",
        "komplett", "teilweise", "nur", "genau", "ja", "nein",
        "und was", "und warum", "was ist mit",
        "heißt das", "heisst das", "ist das", "muss ich das", "zählt das", "zaehlt das", "zahlt das",
        "und wer", "eine davon", "einer davon", "der käufer", "der kaufer",
        "an den anderen tagen", "das waren", "kann ich die", "muss das",
        "ich habe alles", "muss ich darauf",
    )
    letzte_assistentenantwort = ""
    for eintrag in reversed(verlauf):
        if eintrag.get("rolle") == "assistent":
            letzte_assistentenantwort = str(eintrag.get("text", "")).strip()
            break

    ausdrueckliches_folgesignal = any(
        normalisiert == signal
        or (
            normalisiert.startswith(signal)
            and len(normalisiert) > len(signal)
            and normalisiert[len(signal)] in " ,.!?:;"
        )
        for signal in folgesignale
    )
    frageanfang = (
        "wer ", "wie ", "was ", "wann ", "wo ", "warum ", "wieso ", "weshalb ",
        "welche ", "welcher ", "welches ", "kann ", "muss ", "darf ", "sind ", "ist ",
    )
    antwort_auf_rueckfrage = (
        "?" in letzte_assistentenantwort
        and "?" not in text
        and not normalisiert.startswith(frageanfang)
    )
    alltagshilfe = interpretationsblock(text)
    gespraechstext = "\n".join(
        str(eintrag.get("text", "")) for eintrag in verlauf if isinstance(eintrag, dict)
    )
    # Nur sichere Tatsachenhinweise an den beantwortenden Assistenten geben.
    # Die Kanonisierungsanweisungen "Formuliere ..." sind ausschliesslich fuer
    # den Trainingspruefer bestimmt und duerfen die Fachantwort nicht umlenken.
    strukturhinweise = [
        hinweis
        for hinweis in kanonisierungs_hinweise(text, gespraechstext)
        if not hinweis.startswith("Formuliere")
    ]
    strukturhilfe = (
        "\nSichere Hinweise aus dem Gespräch (bei Widerspruch gilt die Originalnachricht):\n- "
        + "\n- ".join(strukturhinweise)
        if strukturhinweise
        else ""
    )
    sprachhilfen = alltagshilfe + strukturhilfe
    kurze_alltagsfolge = bool(alltagshilfe) and len(text) <= 180 and bool(verlauf)
    bezug_durch_trotzdem = "trotzdem" in normalisiert and len(text) <= 180 and bool(verlauf)
    if len(text) > 240 or not (
        ausdrueckliches_folgesignal or antwort_auf_rueckfrage or kurze_alltagsfolge
        or bezug_durch_trotzdem
    ):
        return text + sprachhilfen

    letzte_nutzerangaben: list[str] = []
    for eintrag in reversed(verlauf):
        if eintrag.get("rolle") == "nutzer":
            angabe = str(eintrag.get("text", "")).strip()
            if angabe:
                letzte_nutzerangaben.append(angabe)
            # Bei echten Mehrschritt-Dialogen liegt das konkrete Thema mitunter
            # vier oder fünf Nutzerbeiträge zurück. Der Server übergibt ohnehin
            # höchstens zwölf Verlaufseinträge; sechs Nutzerangaben bewahren den
            # Themenanker, ohne einen unbegrenzt wachsenden Prompt zu erzeugen.
            if len(letzte_nutzerangaben) == 6:
                break
    letzte_frage = letzte_nutzerangaben[0] if letzte_nutzerangaben else ""
    if not letzte_frage or letzte_frage == text:
        return text + sprachhilfen
    letzter_assistentenkontext = letzte_assistentenantwort[-700:]
    fruehere = list(reversed(letzte_nutzerangaben[1:]))
    frueherer_kontext = "".join(
        f"Frühere Nutzerangabe: {angabe}\n" for angabe in fruehere
    )
    return (
        f"Vorheriger Gesprächskontext:\n"
        f"{frueherer_kontext}"
        f"Letzte Nutzerangabe: {letzte_frage}\n"
        f"Letzte Assistentenantwort: {letzter_assistentenkontext}\n"
        f"Aktuelle Ergänzung: {text}{sprachhilfen}"
    )


def lokalen_ordner_auswaehlen(startordner: str) -> str:
    """Öffnet erst nach einem Nutzerklick den nativen Windows-Ordnerdialog."""
    import tkinter as tk
    from tkinter import filedialog

    fenster = tk.Tk()
    fenster.withdraw()
    fenster.attributes("-topmost", True)
    try:
        return str(
            filedialog.askdirectory(
                parent=fenster,
                title="Ordner für Steuerunterlagen auswählen",
                initialdir=startordner,
                mustexist=True,
            )
        )
    finally:
        fenster.destroy()


def _anmeldung_gebremst(ip_adresse: str) -> bool:
    jetzt = time.monotonic()
    versuche = ANMELDEVERSUCHE[ip_adresse]
    while versuche and jetzt - versuche[0] > ANMELDEFENSTER_SEKUNDEN:
        versuche.popleft()
    return len(versuche) >= ANMELDEVERSUCHE_MAXIMAL


@app.route("/anmelden", methods=["GET", "POST"])
def anmelden():
    if not HEIMNETZ_MODUS:
        return redirect("/")
    if session.get("angemeldet"):
        return redirect("/")
    if not authentifizierung.ist_eingerichtet():
        return render_template(
            "anmelden.html",
            fehler="Die Anmeldung ist noch nicht eingerichtet. Bitte verwende die Kontenverwaltung auf dem Haupt-PC.",
        ), 503
    fehler = ""
    if request.method == "POST":
        ip_adresse = request.remote_addr or "unbekannt"
        if _anmeldung_gebremst(ip_adresse):
            fehler = "Zu viele Versuche. Bitte warte fünf Minuten."
        else:
            konto = authentifizierung.konto_pruefen(
                request.form.get("username", ""), request.form.get("passwort", "")
            )
            if konto:
                ANMELDEVERSUCHE.pop(ip_adresse, None)
                session.clear()
                session["angemeldet"] = True
                session["username"] = konto["username"]
                session["rolle"] = konto["rolle"]
                session.permanent = True
                antwort = redirect("/")
                if konto["rolle"] != "admin":
                    profil = next(
                        (
                            nutzer for nutzer in nutzerverwaltung.nutzer_auflisten()
                            if str(nutzer.get("name", "")).casefold() == konto["username"].casefold()
                        ),
                        None,
                    )
                    if profil is None:
                        profil, _ = nutzerverwaltung.nutzer_anlegen(konto["username"])
                    session["nutzer_id"] = str(profil["id"])
                    antwort = _nutzer_cookie_setzen(antwort, str(profil["id"]))
                return antwort
            ANMELDEVERSUCHE[ip_adresse].append(time.monotonic())
            fehler = "Benutzername oder Kennwort ist nicht richtig."
    return render_template("anmelden.html", fehler=fehler)


@app.post("/abmelden")
def abmelden():
    session.clear()
    return redirect("/anmelden" if HEIMNETZ_MODUS else "/")


@app.get("/")
def startseite():
    return render_template(
        "index.html", bfh_testmodus=BFH_TESTMODUS, heimnetz_modus=HEIMNETZ_MODUS
    )


@app.get("/api/status")
def status_lesen():
    """Einfache lokale Bereitschaftsprüfung für den zuverlässigen Starter."""
    modell = MODELL_RESSOURCEN.konfiguration()
    return jsonify(
        bereit=True,
        bfh_testmodus=BFH_TESTMODUS,
        heimnetz_modus=HEIMNETZ_MODUS,
        anmeldung_erforderlich=HEIMNETZ_MODUS,
        anmeldung_eingerichtet=authentifizierung.ist_eingerichtet(),
        modell_backend=modell["chat_backend"],
        embedding_backend=modell["embedding_backend"],
        modell_kontext=(
            modell["lmstudio_kontext"] if modell["chat_backend"] == "lmstudio" else None
        ),
    )


@app.get("/api/nutzer")
def nutzer_lesen():
    if HEIMNETZ_MODUS and session.get("rolle") != "admin":
        nutzer = nutzerverwaltung.nutzer_finden(str(session.get("nutzer_id", "")))
        nutzerverwaltung.aktiven_nutzer_setzen(str(nutzer["id"]) if nutzer else None)
        return jsonify(nutzer=[nutzer] if nutzer else [], aktiv=nutzer)
    cookie_id = request.cookies.get(NUTZER_COOKIE)
    nutzer = nutzerverwaltung.nutzer_finden(cookie_id)
    nutzerverwaltung.aktiven_nutzer_setzen(str(nutzer["id"]) if nutzer else None)
    return jsonify(nutzer=nutzerverwaltung.nutzer_auflisten(), aktiv=nutzer)


@app.post("/api/nutzer")
def nutzer_erstellen():
    if HEIMNETZ_MODUS and session.get("rolle") != "admin":
        return jsonify(fehler="Nur der Administrator kann weitere Nutzerprofile anlegen."), 403
    if not request.is_json:
        return jsonify(fehler="Ungültige Anfrage."), 415
    daten = request.get_json(silent=True) or {}
    try:
        nutzer, migriert = nutzerverwaltung.nutzer_anlegen(str(daten.get("name", "")))
    except ValueError as fehler:
        return jsonify(fehler=str(fehler)), 400
    antwort = make_response(jsonify(nutzer=nutzer, altbestand_uebernommen=migriert), 201)
    return _nutzer_cookie_setzen(antwort, str(nutzer["id"]))


@app.post("/api/nutzer/wechseln")
def nutzer_wechseln():
    if not request.is_json:
        return jsonify(fehler="Ungültige Anfrage."), 415
    daten = request.get_json(silent=True) or {}
    if HEIMNETZ_MODUS and session.get("rolle") != "admin":
        eigenes_profil = str(session.get("nutzer_id", ""))
        if str(daten.get("nutzer_id", "")) != eigenes_profil:
            return jsonify(fehler="Dieses Konto darf kein anderes Nutzerprofil öffnen."), 403
    try:
        nutzer = nutzerverwaltung.aktiven_nutzer_setzen(str(daten.get("nutzer_id", "")))
    except ValueError as fehler:
        return jsonify(fehler=str(fehler)), 404
    antwort = make_response(jsonify(nutzer=nutzer))
    return _nutzer_cookie_setzen(antwort, str(nutzer["id"]))


@app.get("/api/steuerprofil")
def steuerprofil_lesen():
    """Liefert eine kurze lokale Profilübersicht ohne zusätzliche Annahmen."""
    return jsonify(profil_uebersicht(lade_steuerprofil()))


@app.get("/api/steuerakten")
def steuerakten_lesen():
    """Liefert die automatisch berechneten Jahresakten 2023 bis 2025."""
    ordnerueberwachung_sicherstellen(warten=True)
    return jsonify(
        akten=erstelle_steuerakten(lade_steuerprofil(), dokumentuebersicht())
    )


@app.get("/api/eingangsordner")
def eingangsordner_lesen():
    return jsonify(pfad=str(aktueller_eingang()))


@app.post("/api/eingangsordner")
def eingangsordner_aendern():
    if not request.is_json:
        return jsonify(fehler="Ungültige Anfrage."), 415
    daten = request.get_json(silent=True) or {}
    try:
        if daten.get("standard") is True:
            pfad = standard_eingang_setzen()
        else:
            pfad = setze_eingang(str(daten.get("pfad", "")))
    except ValueError as fehler:
        return jsonify(fehler=str(fehler)), 400
    return jsonify(pfad=str(pfad), meldung="Der überwachte Ordner wurde geändert.")


@app.post("/api/eingangsordner/auswaehlen")
def eingangsordner_auswaehlen():
    if HEIMNETZ_MODUS:
        return jsonify(fehler="Die Ordnerauswahl ist im Heimnetz nur direkt am Serverrechner möglich."), 403
    if not request.is_json:
        return jsonify(fehler="Ungültige Anfrage."), 415
    try:
        auswahl = lokalen_ordner_auswaehlen(str(aktueller_eingang()))
        if not auswahl:
            return jsonify(pfad=str(aktueller_eingang()), abgebrochen=True)
        pfad = setze_eingang(auswahl)
    except Exception:
        return jsonify(fehler="Der Ordnerdialog konnte nicht verwendet werden."), 400
    return jsonify(pfad=str(pfad), meldung="Der überwachte Ordner wurde geändert.")


@app.post("/api/eingangsordner/oeffnen")
def eingangsordner_oeffnen():
    if HEIMNETZ_MODUS:
        return jsonify(fehler="Der Ordner kann im Heimnetz nur direkt am Serverrechner geöffnet werden."), 403
    if not request.is_json:
        return jsonify(fehler="Ungültige Anfrage."), 415
    pfad = aktueller_eingang()
    try:
        ordnerueberwachung_sicherstellen()
        os.startfile(str(pfad))
    except OSError:
        return jsonify(fehler="Der Eingangsordner konnte nicht geöffnet werden."), 500
    return jsonify(meldung="Der Eingangsordner wurde geöffnet.")


@app.get("/api/dokumente")
def dokumente_lesen():
    ordnerueberwachung_sicherstellen(warten=True)
    return jsonify(dokumente=dokumentuebersicht(), ordner=str(aktueller_eingang()))


@app.get("/api/dokumente/<kennung>/vorschau")
def dokument_vorschau(kennung: str):
    """Liefert ausschließlich ein registriertes Dokument des aktiven Profils aus."""
    dokument = next((d for d in dokumentuebersicht() if str(d.get("id", "")) == kennung), None)
    if dokument is None:
        return jsonify(fehler="Das Dokument wurde nicht gefunden."), 404
    try:
        pfad = Path(str(dokument.get("pfad", ""))).resolve(strict=True)
    except (OSError, RuntimeError):
        return jsonify(fehler="Die Originaldatei ist nicht mehr verfügbar."), 404
    if not pfad.is_file():
        return jsonify(fehler="Die Originaldatei ist nicht mehr verfügbar."), 404
    mimetype = VORSCHAU_MIMETYPES.get(pfad.suffix.lower())
    if mimetype is None:
        return jsonify(fehler="Dieser Dateityp kann nicht als Vorschau angezeigt werden."), 415
    return send_file(
        pfad,
        mimetype=mimetype,
        as_attachment=False,
        download_name=pfad.name,
        conditional=True,
        max_age=0,
    )


@app.post("/api/dokumente/upload")
def dokument_hochladen():
    """Speichert einen streng geprüften Beleg im aktiven C:-Eingangsordner."""
    datei = request.files.get("datei")
    if datei is None or not str(datei.filename or "").strip():
        return jsonify(fehler="Bitte wähle eine Datei aus."), 400
    try:
        ziel = speichere_upload(aktueller_eingang(), str(datei.filename), datei.stream)
    except ValueError as fehler:
        return jsonify(fehler=str(fehler)), 400
    nutzer = nutzerverwaltung.aktiver_nutzer() or {}
    ordnerueberwachung_sicherstellen()
    return jsonify(
        dateiname=ziel.name,
        nutzer_name=str(nutzer.get("name", "")),
        meldung="Die Datei wurde auf Laufwerk C: gespeichert. Die lokale Erkennung läuft.",
    ), 201


@app.errorhandler(413)
def upload_zu_gross(_fehler):
    if request.path.startswith("/api/"):
        return jsonify(fehler="Die Anfrage ist zu groß. Pro Dokument sind höchstens 25 MB erlaubt."), 413
    return "Die Anfrage ist zu groß.", 413


@app.get("/api/persoenliche-steuerdaten")
def persoenliche_daten_lesen():
    steuerjahr = str(request.args.get("steuerjahr", "")).strip()
    if not re.fullmatch(r"(?:19|20)\d{2}", steuerjahr):
        return jsonify(fehler="Bitte gib ein gültiges vierstelliges Steuerjahr ein."), 400
    return jsonify(steuerjahr=steuerjahr, werte=persoenliche_steuerdaten(steuerjahr))


def _stammdaten_datei():
    return nutzerverwaltung.datenordner() / STAMMDATEN_DATEINAME


def _steuerwerte_datei():
    return nutzerverwaltung.datenordner() / STEUERWERTE_DATEINAME


@app.get("/api/stammdaten")
def stammdaten_lesen():
    """Gibt absichtlich nur maskierte sensible Werte an den Browser zurück."""
    try:
        return jsonify(felder=stammdaten_status(_stammdaten_datei()))
    except ValueError as fehler:
        return jsonify(fehler=str(fehler)), 400


@app.post("/api/stammdaten")
def stammdaten_aendern():
    if not request.is_json:
        return jsonify(fehler="Ungültige Anfrage."), 415
    daten = request.get_json(silent=True) or {}
    werte = daten.get("werte", {})
    loeschen = daten.get("loeschen", [])
    if not isinstance(werte, dict) or not isinstance(loeschen, list):
        return jsonify(fehler="Die Stammdaten sind ungültig."), 400
    try:
        speichere_stammdaten(_stammdaten_datei(), werte, loeschen)
        return jsonify(felder=stammdaten_status(_stammdaten_datei()))
    except ValueError as fehler:
        return jsonify(fehler=str(fehler)), 400


@app.get("/api/manuelle-werte")
def manuelle_werte_lesen():
    steuerjahr = str(request.args.get("steuerjahr", "")).strip()
    if steuerjahr not in {"2023", "2024", "2025"}:
        return jsonify(fehler="Manuelle Steuerwerte sind für 2023, 2024 und 2025 verfügbar."), 400
    try:
        return jsonify(katalog=katalog_liste(), werte=werte_laden(_steuerwerte_datei(), steuerjahr))
    except ValueError as fehler:
        return jsonify(fehler=str(fehler)), 400


@app.post("/api/manuelle-werte")
def manuellen_wert_anlegen():
    if not request.is_json:
        return jsonify(fehler="Ungültige Anfrage."), 415
    daten = request.get_json(silent=True) or {}
    try:
        wert = wert_speichern(
            _steuerwerte_datei(),
            str(daten.get("steuerjahr", "")),
            str(daten.get("feld_id", "")),
            str(daten.get("wert", "")),
            str(daten.get("quelle", "")),
        )
    except ValueError as fehler:
        return jsonify(fehler=str(fehler)), 400
    return jsonify(wert=wert), 201


@app.post("/api/manuelle-werte/<kennung>/status")
def manuellen_wert_bestaetigen(kennung: str):
    if not request.is_json:
        return jsonify(fehler="Ungültige Anfrage."), 415
    daten = request.get_json(silent=True) or {}
    try:
        wert = wert_status_setzen(_steuerwerte_datei(), kennung, str(daten.get("status", "")))
    except ValueError as fehler:
        return jsonify(fehler=str(fehler)), 400
    return jsonify(wert=wert)


@app.post("/api/manuelle-werte/<kennung>/loeschen")
def manuellen_wert_entfernen(kennung: str):
    if not request.is_json:
        return jsonify(fehler="Ungültige Anfrage."), 415
    try:
        wert_loeschen(_steuerwerte_datei(), kennung)
    except ValueError as fehler:
        return jsonify(fehler=str(fehler)), 400
    return jsonify(meldung="Der manuelle Steuerwert wurde gelöscht.")


@app.post("/api/checkliste")
def checkliste_erstellen():
    if not request.is_json:
        return jsonify(fehler="Ungültige Anfrage."), 415
    daten = request.get_json(silent=True) or {}
    steuerjahr = str(daten.get("steuerjahr", "")).strip()
    bereiche = daten.get("bereiche", [])
    if not re.fullmatch(r"(?:19|20)\d{2}", steuerjahr):
        return jsonify(fehler="Bitte gib ein gültiges vierstelliges Steuerjahr ein."), 400
    if not isinstance(bereiche, list):
        return jsonify(fehler="Die ausgewählten Bereiche sind ungültig."), 400
    punkte = erstelle_checkliste(steuerjahr, [str(bereich) for bereich in bereiche], dokumentuebersicht())
    return jsonify(steuerjahr=steuerjahr, punkte=punkte)


@app.post("/api/pruefbericht")
def pruefbericht_erstellen():
    if not request.is_json:
        return jsonify(fehler="Ungültige Anfrage."), 415
    daten = request.get_json(silent=True) or {}
    steuerjahr = str(daten.get("steuerjahr", "")).strip()
    bereiche = daten.get("bereiche", [])
    if not re.fullmatch(r"(?:19|20)\d{2}", steuerjahr):
        return jsonify(fehler="Bitte gib ein gültiges vierstelliges Steuerjahr ein."), 400
    if not isinstance(bereiche, list):
        return jsonify(fehler="Die ausgewählten Bereiche sind ungültig."), 400
    nutzer = nutzerverwaltung.aktiver_nutzer() or {}
    bericht = erstelle_pruefbericht(
        steuerjahr,
        [str(bereich) for bereich in bereiche],
        dokumentuebersicht(),
        str(nutzer.get("name", "")),
    )
    return jsonify(bericht)


def _elster_eingabehilfe_erstellen(daten: dict):
    steuerjahr = str(daten.get("steuerjahr", "")).strip()
    bereiche = daten.get("bereiche", [])
    if steuerjahr not in {"2023", "2024", "2025"}:
        raise ValueError("Der ELSTER-Eingabeexport ist derzeit für 2023, 2024 und 2025 verfügbar.")
    if not isinstance(bereiche, list):
        raise TypeError("Die ausgewählten Bereiche sind ungültig.")
    nutzer = nutzerverwaltung.aktiver_nutzer() or {}
    return erstelle_elster_eingabehilfe(
        steuerjahr,
        [str(bereich) for bereich in bereiche],
        dokumentuebersicht(),
        lade_steuerprofil(),
        str(nutzer.get("name", "")),
        lade_stammdaten(_stammdaten_datei()),
        werte_laden(_steuerwerte_datei(), steuerjahr),
    )


@app.post("/api/elster-vorschau")
def elster_vorschau_erstellen():
    """Zeigt vor dem Download alle exportierbaren und noch offenen Angaben."""
    if not request.is_json:
        return jsonify(fehler="Ungültige Anfrage."), 415
    try:
        eingabehilfe = _elster_eingabehilfe_erstellen(request.get_json(silent=True) or {})
    except (TypeError, ValueError) as fehler:
        return jsonify(fehler=str(fehler)), 400
    return jsonify(eingabehilfe)


@app.post("/api/elster-export")
def elster_export_erstellen():
    """Liefert eine geprüfte Eingabehilfe, niemals eine versandfertige Erklärung."""
    if not request.is_json:
        return jsonify(fehler="Ungültige Anfrage."), 415
    try:
        eingabehilfe = _elster_eingabehilfe_erstellen(request.get_json(silent=True) or {})
    except (TypeError, ValueError) as fehler:
        return jsonify(fehler=str(fehler)), 400
    archiv = erstelle_elster_export_zip(eingabehilfe)
    return send_file(
        BytesIO(archiv),
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"elster-eingabehilfe-{eingabehilfe['steuerjahr']}.zip",
        max_age=0,
    )


@app.post("/api/dokumente/<kennung>")
def dokument_bearbeiten(kennung: str):
    if not request.is_json:
        return jsonify(fehler="Ungültige Anfrage."), 415
    daten = request.get_json(silent=True) or {}
    try:
        eintrag = dokument_aktualisieren(
            kennung,
            str(daten.get("status", "Zu prüfen")),
            str(daten["dokumenttyp"]) if "dokumenttyp" in daten else None,
            str(daten["steuerjahr"]) if "steuerjahr" in daten else None,
        )
    except ValueError as fehler:
        return jsonify(fehler=str(fehler)), 400
    return jsonify(dokument=eintrag)


@app.post("/api/dokumente/<kennung>/vision")
def dokument_genauer_pruefen(kennung: str):
    """Prüft ein einzelnes Foto lokal; Ergebnisse bleiben bestätigungspflichtig."""
    dokument = next((d for d in dokumentuebersicht() if d.get("id") == kennung), None)
    if dokument is None:
        return jsonify(fehler="Das Dokument wurde nicht gefunden."), 404
    pfad = Path(str(dokument.get("pfad", "")))
    if pfad.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"} or not pfad.is_file():
        return jsonify(fehler="Die genauere Prüfung ist nur für vorhandene Bilddateien möglich."), 400
    prompt = VISION_PROMPT
    try:
        antwort = MODELL_RESSOURCEN.vision_chat(
            "steuer-assistent-pilot13:bf16",
            [{"role": "user", "content": prompt, "images": [str(pfad.resolve())]}],
            options={"temperature": 0, "num_predict": 256},
            fallback_modell="qwen3.5:9b",
        )
        text = str((antwort.get("message") or {}).get("content", ""))
        eintrag = vision_wertvorschlaege_uebernehmen(kennung, text)
    except (OSError, RuntimeError, ValueError) as fehler:
        return jsonify(fehler=f"Die lokale Bildprüfung ist fehlgeschlagen: {fehler}"), 503
    return jsonify(
        dokument=eintrag,
        meldung=eintrag.get("vision_status", "Lokale Vision-Prüfung abgeschlossen."),
    )


@app.post("/api/dokumente/<kennung>/werte/<wert_id>")
def dokumentwert_bearbeiten(kennung: str, wert_id: str):
    if not request.is_json:
        return jsonify(fehler="Ungültige Anfrage."), 415
    daten = request.get_json(silent=True) or {}
    try:
        eintrag = wertvorschlag_aktualisieren(kennung, wert_id, str(daten.get("status", "Zu prüfen")))
    except ValueError as fehler:
        return jsonify(fehler=str(fehler)), 400
    return jsonify(dokument=eintrag)


@app.post("/api/dokumente/<kennung>/nutzerzuordnung")
def dokumentnutzer_bestaetigen(kennung: str):
    if not request.is_json:
        return jsonify(fehler="Ungültige Anfrage."), 415
    try:
        eintrag = dokument_nutzer_bestaetigen(kennung)
    except ValueError as fehler:
        return jsonify(fehler=str(fehler)), 400
    return jsonify(dokument=eintrag)


def _nutzer_fuer_aktuelle_anfrage() -> dict | None:
    """Ermittelt den Nutzer aus dieser Anfrage statt aus dem globalen Prozesszustand."""
    nutzer_id = request.cookies.get(NUTZER_COOKIE, "")
    if HEIMNETZ_MODUS and session.get("rolle") != "admin":
        nutzer_id = str(session.get("nutzer_id", ""))
    nutzer = nutzerverwaltung.nutzer_finden(str(nutzer_id))
    if nutzer is None and app.testing:
        return nutzerverwaltung.aktiver_nutzer()
    return nutzer


@app.post("/api/frage")
def frage_beantworten():
    if not request.is_json:
        return jsonify(fehler="Ungültige Anfrage."), 415
    daten = request.get_json(silent=True) or {}
    frage = str(daten.get("frage", "")).strip()
    verlauf = daten.get("verlauf", [])
    steuerjahr = str(daten.get("steuerjahr", "")).strip()
    if steuerjahr and not re.fullmatch(r"(?:19|20)\d{2}", steuerjahr):
        return jsonify(fehler="Bitte wähle ein gültiges vierstelliges Steuerjahr."), 400
    if not frage:
        return jsonify(fehler="Bitte gib eine Frage ein."), 400
    if len(frage) > MAX_FRAGE_ZEICHEN:
        return jsonify(
            fehler=f"Die Frage ist zu lang. Maximal sind {MAX_FRAGE_ZEICHEN:,} Zeichen erlaubt.".replace(",", ".")
        ), 400

    if not isinstance(verlauf, list):
        verlauf = []
    verlauf = [eintrag for eintrag in verlauf[-12:] if isinstance(eintrag, dict)]

    normalisierte_frage = normalisiere_mit_tippfehlern(frage)
    if "unterlagen sind im ordner" in normalisierte_frage:
        ordnerueberwachung_sicherstellen()

    try:
        from fallkontext import beantworte_falldatenfrage, lade_dialogzustand

        request_nutzer = _nutzer_fuer_aktuelle_anfrage()
        fallkontext = None
        vollprofil = None
        eingangsordner = None
        if request_nutzer is not None:
            fallkontext, vollprofil, eingangsordner = lade_dialogzustand(
                nutzer_id=str(request_nutzer["id"]),
                steuerjahr=steuerjahr,
            )
        if vollprofil is None:
            vollprofil = lade_steuerprofil()
        if eingangsordner is None:
            eingangsordner = aktueller_eingang()

        antwort = (
            beantworte_falldatenfrage(frage, fallkontext, verlauf)
            if fallkontext is not None
            else None
        )
        if antwort is None:
            antwort = dialogantwort(
                frage,
                verlauf,
                str(eingangsordner),
                steuerprofil=vollprofil,
            )
        if antwort is not None:
            quellen = []
        else:
            fachfrage = frage_mit_gespraechskontext(frage, verlauf)
            antwort, quellen = beantworte(
                fachfrage,
                steuerprofil=vollprofil,
                gespraech=verlauf,
                aktuelle_nachricht=frage,
                steuerjahr=(fallkontext or {}).get("steuerjahr") or steuerjahr or None,
                fallkontext=fallkontext,
            )
    except Exception:
        return jsonify(fehler="Der Assistent konnte die Frage gerade nicht beantworten. Bitte erneut versuchen."), 500

    return jsonify(
        antwort=antwort,
        quellen=[
            {
                "nummer": nummer,
                "titel": quelle.payload.get("quelle", "Unbekannte Quelle"),
                "paragraph": quelle.payload.get("paragraph", ""),
                "jahr": quelle.payload.get("steuerjahr", ""),
                "url": quelle.payload.get("url", ""),
            }
            for nummer, quelle in enumerate(quellen, start=1)
        ],
    )


if __name__ == "__main__":
    host = "0.0.0.0" if HEIMNETZ_MODUS else "127.0.0.1"
    app.run(host=host, port=8765, debug=False, threaded=True)
