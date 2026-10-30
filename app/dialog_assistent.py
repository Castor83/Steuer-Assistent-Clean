"""Einfache, sichere Gesprächsführung für wiederkehrende Steuerabläufe."""

from __future__ import annotations

import re

from gespraechsverstaendnis import normalisiere_mit_tippfehlern
from steuerprofil import empfohlene_bereiche, lade_steuerprofil


def normalisiere(text: str) -> str:
    return normalisiere_mit_tippfehlern(text)


def _ist_start_einkommensteuer(text: str) -> bool:
    steuer_machen = bool(re.search(r"\b(?:meine\s+)?steuern?\s+(?:machen|anfangen|starten)\b", text))
    if not steuer_machen and not any(
        begriff in text for begriff in ("einkommensteuererklarung", "steuererklarung")
    ):
        return False

    # Fachfragen enthalten oft "geltend machen" oder "erstellen und
    # einreichen". Nur einen ausdruecklichen Arbeitsbeginn als Dialogstart
    # behandeln, damit solche Fragen beim Fachassistenten bleiben.
    einstiege = (
        r"\b(?:ich\s+)?(?:mochte|will|wurde\s+gern)\b.{0,35}\b(?:steuererklarung|einkommensteuererklarung)\b",
        r"\b(?:steuererklarung|einkommensteuererklarung)\b.{0,20}\b(?:anfangen|starten|vorbereiten)\b",
        r"\bhilfe\s+(?:bei|mit)\s+(?:der\s+)?(?:steuererklarung|einkommensteuererklarung)\b",
        r"\b(?:ich\s+)?(?:mochte|will|wurde\s+gern)\b.{0,25}\b(?:meine\s+)?steuern?\s+machen\b",
        r"\b(?:mit\s+)?(?:der\s+|meiner\s+)?steuer\s+(?:anfangen|starten)\b",
    )
    return any(re.search(muster, text) for muster in einstiege)


def _ist_start_grundsteuer(text: str) -> bool:
    """Erkennt einen Arbeitsbeginn, ohne normale Grundsteuerfragen abzufangen."""
    if not any(begriff in text for begriff in ("grundsteuer", "grundabgaben", "grundbesitzabgaben")):
        return False
    einstiege = (
        "ich mochte", "ich will", "ich wurde gern", "ich brauche hilfe", "hilf mir", "hilfe bei",
        "grundsteuer starten", "grundsteuer anfangen", "grundabgaben starten",
        "grundabgaben anfangen", "grundbesitzabgaben starten",
    )
    return any(einstieg in text for einstieg in einstiege)


def _ist_unterlagenfrage(text: str) -> bool:
    return any(begriff in text for begriff in (
        "welche dokument", "was fur dokument", "welche unterlag",
        "was fur unterlag", "was brauche ich", "was benotige ich",
    ))


def _letzte_assistentenantwort(verlauf: list[dict]) -> str:
    for eintrag in reversed(verlauf):
        if eintrag.get("rolle") == "assistent":
            return normalisiere(str(eintrag.get("text", "")))
    return ""


def dialogantwort(
    nachricht: str,
    verlauf: list[dict] | None = None,
    eingangsordner: str = r"dokumente\eingang",
    steuerprofil: dict | None = None,
) -> str | None:
    """Antwortet auf geführte Einstiege; normale Fachfragen bleiben beim RAG-Assistenten."""
    text = normalisiere(nachricht)
    verlauf = verlauf or []
    letzte_antwort = _letzte_assistentenantwort(verlauf)
    steuerprofil = lade_steuerprofil() if steuerprofil is None else steuerprofil

    def antwort_nach_steuerjahr(jahr: str) -> str:
        profilbezeichnungen = {
            "arbeitnehmer": "Arbeitnehmer",
            "vermietung": "Vermietung",
            "haushalt": "selbst genutzter Gebäudeteil",
            "grundsteuer": "Grundsteuer und Grundabgaben",
        }
        merkmale = [
            bezeichnung
            for bereich in empfohlene_bereiche(steuerprofil)
            if (bezeichnung := profilbezeichnungen.get(bereich))
        ]
        for suchwort, bezeichnung in (
            ("arbeitnehmer", "Arbeitnehmer"),
            ("kind", "Kinder"),
            ("vermiet", "Vermietung"),
            ("rente", "Rente"),
            ("selbststandig", "Selbstständigkeit"),
        ):
            if suchwort in text and bezeichnung not in merkmale:
                merkmale.append(bezeichnung)
        situation = ", ".join(merkmale) if merkmale else "deine persönliche Situation"
        return (
            f"Alles klar: {jahr}, Bereich {situation}. Lege zuerst die Lohnsteuerbescheinigung "
            f"und die Versicherungsbescheinigungen in „{eingangsordner}“. Ergänze danach die "
            "Belege, die zu deiner Situation passen. Du kannst die Dateien einzeln oder gesammelt "
            "hineinkopieren.\n\n"
            "Wenn die Unterlagen dort liegen, schreibe einfach „Unterlagen sind im Ordner“. "
            "Dann gehen wir gemeinsam durch, was vorhanden ist und was möglicherweise noch fehlt."
        )

    wartet_auf_grundstuecksdaten = any(
        kennung in letzte_antwort
        for kennung in (
            "in welchem bundesland liegt das grundstuck",
            "betrifft der bescheid oder die erklarung das grundstuck in",
            "mochtest du einen bescheid prufen oder eine erklarung",
        )
    )

    if _ist_unterlagenfrage(text) and any(
        begriff in text for begriff in ("lohnsteuer", "arbeitnehmer", "einkommensteuer")
    ):
        return (
            "Wenn du als Arbeitnehmer deine Steuererklärung vorbereiten möchtest, lege zuerst "
            "diese Unterlagen bereit:\n\n"
            "• die Lohnsteuerbescheinigung jedes Arbeitgebers\n"
            "• Bescheinigungen zu Kranken-, Pflege-, Renten- und sonstigen Versicherungen\n"
            "• Bescheide über Lohnersatzleistungen, zum Beispiel Arbeitslosen-, Kranken-, "
            "Eltern-, Kurzarbeiter- oder Insolvenzgeld\n"
            "• Nachweise zu beruflichen Ausgaben, etwa Arbeitsweg, Homeoffice, Arbeitsmittel, "
            "Fortbildung, Dienstreisen oder doppelte Haushaltsführung\n"
            "• Spendenbescheinigungen und Nachweise über außergewöhnliche Belastungen\n"
            "• Rechnungen und Zahlungsnachweise für haushaltsnahe Dienstleistungen und "
            "Handwerkerleistungen\n"
            "• je nach Situation Unterlagen zu Kindern, Kinderbetreuung, Vermietung, Rente "
            "oder weiteren Einkünften\n\n"
            "Viele Daten werden elektronisch gemeldet; die Bescheinigungen solltest du trotzdem "
            "zum Abgleichen bereithalten. Für welches Steuerjahr möchtest du die Erklärung "
            "vorbereiten?"
        )

    if _ist_unterlagenfrage(text) and any(
        begriff in text for begriff in ("grundsteuer", "grundabgaben")
    ):
        return (
            "Für den Einstieg solltest du diese Grundsteuer-Unterlagen bereitlegen:\n\n"
            "• vorhandene Grundsteuerwert-, Grundsteuermess- und Grundsteuerbescheide\n"
            "• das Aktenzeichen des Finanzamts und die Grundstücksanschrift\n"
            "• Grundbuchauszug oder andere Unterlagen mit Gemarkung, Flur und Flurstück\n"
            "• Angaben zu den Eigentümern und ihren Eigentumsanteilen\n"
            "• Unterlagen zu Grundstücks-, Wohn- und Nutzflächen\n"
            "• bei Gebäuden Angaben zu Gebäudeart und Baujahr\n\n"
            "Welche weiteren Angaben nötig sind, hängt vom Bundesland und davon ab, ob du "
            "eine Erklärung beziehungsweise Änderung vorbereiten oder einen Bescheid prüfen "
            "möchtest. In welchem Bundesland liegt das Grundstück, und worum geht es bei dir?"
        )

    if _ist_start_grundsteuer(text) and not wartet_auf_grundstuecksdaten:
        wohnsitz = steuerprofil.get("wohnsitz", {})
        standardobjekt = steuerprofil.get("grundabgaben_standardobjekt", {})
        stadt = str(wohnsitz.get("stadt", "")).strip()
        bundesland = str(wohnsitz.get("bundesland", "")).strip()
        objekt_strasse = str(standardobjekt.get("strasse", "")).strip()
        objekt_hausnummer = str(standardobjekt.get("hausnummer", "")).strip()
        objekt_plz = str(standardobjekt.get("postleitzahl", "")).strip()
        objekt_stadt = str(standardobjekt.get("stadt", "")).strip()
        objekt_bundesland = str(standardobjekt.get("bundesland", "")).strip()
        objekt_gebaeudeart = str(standardobjekt.get("gebaeudeart", "")).strip()
        if objekt_strasse and objekt_hausnummer and objekt_plz and objekt_stadt and objekt_bundesland:
            objektadresse = f"{objekt_strasse} {objekt_hausnummer}, {objekt_plz} {objekt_stadt}"
            objektbeschreibung = f"das {objekt_gebaeudeart}" if objekt_gebaeudeart else "das Haus"
            ortsfrage = (
                f"Als Standardobjekt für Grundabgaben ist {objektbeschreibung} {objektadresse} in "
                f"{objekt_bundesland} gespeichert. Ich gehe bei Grundabgaben zunächst von diesem "
                "Objekt aus; falls eine Frage ein anderes Grundstück betrifft, sagst du mir das bitte. "
                "Möchtest du einen Bescheid prüfen oder eine Erklärung beziehungsweise Änderung vorbereiten?"
            )
        elif stadt and bundesland:
            ortsfrage = (
                f"Als fester Wohnsitz ist {stadt} in {bundesland} gespeichert. "
                f"Betrifft der Bescheid oder die Erklärung das Grundstück in {stadt}, oder liegt "
                "das Grundstück in einer anderen Gemeinde? Um welche Objektart geht es und möchtest "
                "du einen Bescheid prüfen oder eine Erklärung beziehungsweise Änderung vorbereiten?"
            )
        else:
            ortsfrage = (
                "In welchem Bundesland liegt das Grundstück, in welcher Gemeinde befindet es sich, "
                "um welche Objektart geht es und möchtest du einen Bescheid prüfen oder eine Erklärung "
                "beziehungsweise Änderung vorbereiten?"
            )
        return (
            "Gern – Grundsteuer und kommunale Grundabgaben sind ein Kernthema des Assistenten. "
            "Wir klären zuerst, was du erledigen möchtest. "
            "Möglich sind vor allem:\n\n"
            "• einen Grundsteuerwert- oder Grundsteuermessbescheid des Finanzamts prüfen\n"
            "• den endgültigen Grundsteuerbescheid der Stadt oder Gemeinde prüfen\n"
            "• einen kommunalen Grundbesitzabgabenbescheid mit Gebührenpositionen prüfen\n"
            "• eine Grundsteuererklärung oder eine Änderungsanzeige vorbereiten\n\n"
            f"Lege vorhandene Bescheide und Grundstücksunterlagen in „{eingangsordner}“. "
            "Hilfreich sind insbesondere Aktenzeichen, Grundstücksanschrift, Grundbuch- oder "
            "Flurstücksdaten, Eigentumsanteile sowie – abhängig vom Landesmodell – Grundstücks-, "
            "Wohn- und Nutzflächen, Bodenrichtwert und Baujahr. Die Dateien bleiben lokal und "
            "werden nicht verändert.\n\n"
            f"{ortsfrage}"
        )

    if wartet_auf_grundstuecksdaten:
        bundeslaender = (
            "baden-wurttemberg", "bayern", "berlin", "brandenburg", "bremen", "hamburg",
            "hessen", "mecklenburg-vorpommern", "niedersachsen", "nordrhein-westfalen",
            "rheinland-pfalz", "saarland", "sachsen", "sachsen-anhalt", "schleswig-holstein",
            "thuringen",
        )
        bundesland = next((land for land in bundeslaender if land in text), "das genannte Bundesland")
        if "bescheid" in text or "pruf" in text:
            aufgabe = "Bescheidprüfung"
            details = (
                "Lege bitte den vollständigen Bescheid einschließlich Berechnungsseiten ab. "
                "Bei einem kommunalen Grundsteuerbescheid ist zusätzlich der zugrunde liegende "
                "Grundsteuermessbescheid hilfreich."
            )
        else:
            aufgabe = "Erklärung oder Änderung"
            details = (
                "Lege bitte vorhandene Grundbuch-, Flurstücks- und Flächenunterlagen sowie frühere "
                "Bescheide ab. Welche Werte benötigt werden, hängt vom Modell des Bundeslands ab."
            )
        return (
            f"Alles klar: {bundesland.title()}, {aufgabe}. {details}\n\n"
            f"Kopiere die Unterlagen nach „{eingangsordner}“ und schreibe anschließend "
            "„Grundsteuer-Unterlagen sind im Ordner“. Dann beginnen wir mit der kontrollierten "
            "Checkliste. Fristen oder Einspruchsmöglichkeiten bewerte ich erst anhand des "
            "Bescheiddatums und der konkreten Unterlage."
        )

    if "grundsteuer-unterlagen sind im ordner" in text or "grundsteuer unterlagen sind im ordner" in text:
        return (
            "Gut. Der lokale Ordnerüberwacher kann die Dateien jetzt als Grundsteuerbescheid oder "
            "Grundsteuerunterlage erkennen. Öffne den Bereich „Unterlagen“. Prüfe zuerst, ob alle "
            "Seiten vorhanden und Aktenzeichen, Grundstück sowie Bescheiddatum lesbar sind.\n\n"
            "Schreibe mir danach, welcher Bescheid vorliegt: Grundsteuerwertbescheid, "
            "Grundsteuermessbescheid oder Grundsteuerbescheid der Gemeinde. Dann erkläre ich dir "
            "die passenden nächsten Prüfschritte."
        )

    if _ist_start_einkommensteuer(text):
        profilbereiche = empfohlene_bereiche(steuerprofil)
        if profilbereiche:
            bezeichnungen = {
                "arbeitnehmer": "Angestellter",
                "vermietung": "teilweise Vermietung des Dreifamilienhauses",
                "haushalt": "selbst genutzter Gebäudeteil",
                "grundsteuer": "Grundsteuer und Grundabgaben",
            }
            vorgemerkt = ", ".join(
                bezeichnungen[bereich]
                for bereich in profilbereiche
                if bereich in bezeichnungen
            )
            steuerjahr = str(
                steuerprofil.get("steuererklaerung", {}).get(
                    "naechstes_zu_bearbeitendes_steuerjahr", ""
                )
            ).strip()
            jahresfrage = (
                f"Als nächstes zu bearbeitendes Steuerjahr ist vorläufig {steuerjahr} vorgemerkt. "
                f"Soll ich mit der Checkliste für {steuerjahr} beginnen?"
                if steuerjahr
                else "Für welches Steuerjahr möchtest du die Erklärung vorbereiten?"
            )
            return (
                "Gern – dein gespeichertes Profil wird dafür verwendet. Bereits vorgemerkt sind: "
                f"{vorgemerkt}. Fehlende Einzelheiten wie Wohnflächen und die Zahl der vermieteten "
                "Wohnungen frage ich erst im passenden Abschnitt ab und erkläre dabei, wofür sie "
                "benötigt werden.\n\n"
                "Lege vorhandene Unterlagen nach und nach in den überwachten Ordner "
                f"„{eingangsordner}“. Die Erkennung läuft lokal; deine Originaldateien werden nicht "
                "verschoben oder verändert.\n\n"
                f"{jahresfrage}"
            )
        return (
            "Gern – wir bereiten deine Einkommensteuererklärung Schritt für Schritt vor. "
            "Für den Anfang brauchst du meistens:\n\n"
            "• Steuer-ID, Bankverbindung und – falls vorhanden – den letzten Steuerbescheid\n"
            "• elektronische Lohnsteuerbescheinigung\n"
            "• Bescheinigungen zu Kranken-, Pflege- und Altersvorsorge\n"
            "• Belege zu Fahrtkosten, Homeoffice, Arbeitsmitteln oder Fortbildungen\n"
            "• je nach Situation Unterlagen zu Kindern, Spenden, Handwerkerleistungen, "
            "Vermietung oder weiteren Einkünften\n\n"
            "Lege vorhandene PDF-, Bild-, Text- oder CSV-Dateien in den überwachten Ordner "
            f"„{eingangsordner}“. Die Erkennung läuft lokal; deine Originaldateien werden "
            "nicht verschoben oder verändert.\n\n"
            "Für welches Steuerjahr möchtest du die Erklärung machen, und trifft etwas davon "
            "auf dich zu: Arbeitnehmer, Kinder, Vermietung, Rente oder Selbstständigkeit?"
        )

    if "als nachstes zu bearbeitendes steuerjahr ist vorlaufig" in letzte_antwort:
        profiljahr = str(
            steuerprofil.get("steuererklaerung", {}).get(
                "naechstes_zu_bearbeitendes_steuerjahr", ""
            )
        ).strip()
        genannte_jahre = [
            wort for wort in text.replace(",", " ").split()
            if wort.isdigit() and len(wort) == 4
        ]
        if text in {"ja", "ja bitte", "genau", "ok", "okay"} and profiljahr:
            return antwort_nach_steuerjahr(profiljahr)
        if genannte_jahre:
            return antwort_nach_steuerjahr(genannte_jahre[0])
        return (
            f"Kein Problem. Ist {profiljahr or 'dieses Steuerjahr'} doch nicht richtig? "
            "Nenne mir bitte das vierstellige Steuerjahr, mit dem wir beginnen sollen."
        )

    if "fur welches steuerjahr" in letzte_antwort:
        jahre = [wort for wort in text.replace(",", " ").split() if wort.isdigit() and len(wort) == 4]
        jahr = jahre[0] if jahre else "das gewünschte Steuerjahr"
        return antwort_nach_steuerjahr(jahr)

    if "unterlagen sind im ordner" in text or "dokumente sind im ordner" in text:
        return (
            "Gut. Der Ordnerüberwacher prüft unterstützte Dateien lokal und schlägt Dokumenttypen "
            "vor. Öffne jetzt den Bereich „Unterlagen“, um den vorgesehenen Ablauf zu sehen. "
            "Als Nächstes vergleichen wir deine Unterlagen mit der Checkliste. Nenne mir dazu "
            "bitte kurz das Steuerjahr und ob du Arbeitnehmer, Rentner, Vermieter oder selbstständig bist."
        )

    if text in {"was brauche ich", "welche unterlagen brauche ich", "unterlagen"}:
        return (
            "Das hängt von deiner Situation ab. Fast immer hilfreich sind Steuer-ID, Bankverbindung, "
            "Lohnsteuerbescheinigung und Versicherungsbescheinigungen. Hinzu kommen passende Belege, "
            "zum Beispiel für Arbeitsweg, Homeoffice, Arbeitsmittel, Kinder, Spenden, Handwerker oder "
            "Vermietung. Sag mir bitte das Steuerjahr und deine Einkunftsarten, dann grenze ich die Liste ein."
        )

    return None
