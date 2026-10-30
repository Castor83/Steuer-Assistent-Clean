"""Lokale Checkliste für Grundsteuer bei vermieteten Wohnungen.

Die Anwendung speichert keine Eingaben und ersetzt keine Prüfung des
Mietvertrags, Grundsteuerbescheids oder steuerlichen Einzelfalls.
"""


def frage(text: str) -> str:
    antwort = input(f"{text} [ja/nein/unklar]: ").strip().lower()
    return antwort if antwort in {"ja", "nein"} else "unklar"


def status(antwort: str, ja_text: str, nein_text: str, unklar_text: str) -> None:
    if antwort == "ja":
        print(f"  [OK] {ja_text}")
    elif antwort == "nein":
        print(f"  [PRUEFEN] {nein_text}")
    else:
        print(f"  [UNKLAR] {unklar_text}")


def main() -> None:
    print("=" * 52)
    print("  GRUNDSTEUER- UND VERMIETUNGS-CHECKLISTE")
    print("=" * 52)
    print("Die Eingaben werden nicht gespeichert.\n")

    vermietet = frage("Ist die Wohnung im betreffenden Zeitraum vermietet?")
    vereinbarung = frage("Enthält der Mietvertrag eine Betriebskostenvereinbarung?")
    vorauszahlung = frage("Sind Betriebskostenvorauszahlungen vereinbart?")
    bescheid = frage("Liegt der Grundsteuerbescheid für den Zeitraum vor?")
    abrechnung = frage("Wurde bei Vorauszahlungen eine Jahresabrechnung erstellt?")

    print("\nERGEBNIS\n")
    status(
        vermietet,
        "Der Vermietungsbezug ist als Ausgangspunkt dokumentiert.",
        "Für eine Umlage an Mieter ist dieser Fall in der Regel nicht einschlägig.",
        "Kläre zuerst, ob und für welchen Zeitraum eine Vermietung vorlag.",
    )
    status(
        vereinbarung,
        "Eine vertragliche Grundlage für Betriebskosten ist angegeben.",
        "Ohne Vereinbarung ist eine Betriebskostenumlage nicht allein wegen der Kosten möglich.",
        "Prüfe die Betriebskostenklausel im Mietvertrag im Wortlaut.",
    )
    status(
        vorauszahlung,
        "Bei Vorauszahlungen ist eine jährliche Abrechnung relevant.",
        "Prüfe, ob stattdessen eine Betriebskostenpauschale vereinbart wurde.",
        "Kläre, ob Pauschale oder Vorauszahlungen vereinbart sind.",
    )
    status(
        bescheid,
        "Der Grundsteuerbescheid kann für Betrag und Zeitraum herangezogen werden.",
        "Bescheid oder Zahlungsnachweis zum betreffenden Zeitraum beschaffen.",
        "Grundsteuerbescheid und kommunalen Hebesatz dokumentieren.",
    )
    if vorauszahlung == "ja":
        status(
            abrechnung,
            "Die Abrechnung kann anhand von Mietvertrag und Bescheid geprüft werden.",
            "Erstelle bzw. prüfe die jährliche Betriebskostenabrechnung.",
            "Kläre, ob und wann eine Betriebskostenabrechnung erstellt wurde.",
        )

    print("\nRECHTLICHER RAHMEN")
    print("- Grundsteuer ist als laufende öffentliche Last eine Betriebskostenart (§ 2 Nr. 1 BetrKV).")
    print("- Der Mieter trägt Betriebskosten nur bei entsprechender Vereinbarung (§ 556 BGB).")
    print("- Bei Vorauszahlungen ist grundsätzlich jährlich abzurechnen (§ 556 BGB).")
    print("\nUnterlagen bereithalten: Mietvertrag, Grundsteuerbescheid, Zahlungsnachweise,")
    print("Betriebskostenabrechnung und Informationen zum Abrechnungszeitraum.")
    print("\nHinweis: Die Checkliste ersetzt keine Prüfung des konkreten Mietvertrags oder Bescheids.")


if __name__ == "__main__":
    main()
