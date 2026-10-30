from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from gespraechsverstaendnis import (
    alltagssprache_hinweise,
    bewahre_beschaeftigungsstatus,
    bewahre_grundabgabenort,
    grundabgabenort,
    interpretationsblock,
    kanonisierungs_hinweise,
    normalisiere_grundabgabenort,
    normalisiere_mit_tippfehlern,
)


class GespraechsverstaendnisTest(unittest.TestCase):
    def test_umgangssprachlicher_rohrbruch_in_eigener_wohnung(self):
        hinweise = alltagssprache_hinweise(
            "Bei mir in der Bude ist das Rohr geplatzt, kann ich da bei der Steuer was absetzen?"
        )
        text = " ".join(hinweise)
        self.assertIn("Rohrbruch", text)
        self.assertIn("selbst genutzte", text)
        self.assertIn("steuerliche Berücksichtigung", text)

    def test_tippfehler_bei_versicherung_wird_verstanden(self):
        block = interpretationsblock("Die Versicherrung hats komplett bezahlt")
        self.assertIn("Gebäudeversicherung", block)
        self.assertIn("bezahlt", block)

    def test_mieterwohnung_wird_von_eigener_wohnung_unterschieden(self):
        text = " ".join(alltagssprache_hinweise("Das kaputte Rohr war bei den Mietern"))
        self.assertIn("vermietete Wohnung", text)
        self.assertNotIn("selbst genutzte", text)

    def test_homeoffice_und_arbeitsweg_werden_alltagssprachlich_erkannt(self):
        zuhause = " ".join(alltagssprache_hinweise("Ich hab drei Tage von zuhause gearbeitet"))
        arbeitsweg = " ".join(alltagssprache_hinweise("Was ist mit meinem Weg zur Arbeit?"))
        self.assertIn("Homeoffice", zuhause)
        self.assertIn("Entfernungspauschale", arbeitsweg)

    def test_einfache_entfernung_wird_nicht_als_einzelfahrt_missverstanden(self):
        text = " ".join(
            alltagssprache_hinweise(
                "Ich bin 15 Kilometer einfach zur Arbeit gefahren."
            )
        )
        self.assertIn("einfache Entfernung", text)
        self.assertIn("Entfernungspauschale", text)
        self.assertIn("nicht halbiert", text)

    def test_daheim_am_arbeiten_wird_als_homeoffice_verstanden(self):
        text = " ".join(
            alltagssprache_hinweise("Ich war 80 Tage daheim am Arbeiten")
        )
        self.assertIn("Homeoffice", text)

    def test_haeufige_fachwort_tippfehler_werden_kontrolliert_korrigiert(self):
        text = normalisiere_mit_tippfehlern(
            "Steuererklerung, Versicherrung, Sanirung und Wohnnung"
        )
        self.assertIn("steuererklarung", text)
        self.assertIn("versicherung", text)
        self.assertIn("sanierung", text)
        self.assertIn("wohnung", text)

    def test_grundabgabenort_wird_als_sichere_angabe_verdeutlicht(self):
        self.assertEqual(
            normalisiere_grundabgabenort(
                "grundabgaben erlangen mit strassenreinigung"
            ),
            "Grundabgabenbescheid aus Erlangen mit strassenreinigung",
        )
        self.assertEqual("Erlangen", grundabgabenort("grundabgaben erlangen mit abwasser"))

    def test_grundabgabenformulierung_ohne_direkten_ort_bleibt_unveraendert(self):
        text = "grundabgaben mit strassenreinigung"
        self.assertEqual(normalisiere_grundabgabenort(text), text)

    def test_grundabgabenort_wird_in_modellausgabe_buchstabengetreu_bewahrt(self):
        original = "grundabgaben erlangen mit strassenreinigung"
        self.assertIn(
            "aus Erlangen",
            bewahre_grundabgabenort(
                original,
                "Der Grundabgabenbescheid aus Erlangan enthält Straßenreinigung.",
            ),
        )
        self.assertIn(
            "aus Erlangen",
            bewahre_grundabgabenort(
                original,
                "Muss ich den Grundabgabenbescheid getrennt betrachten?",
            ),
        )

    def test_ausdruecklicher_angestelltenstatus_bleibt_erhalten(self):
        self.assertTrue(
            bewahre_beschaeftigungsstatus(
                "ich bin angestellt und hab zuhause gearbeitet",
                "Ich habe zu Hause gearbeitet.",
            ).startswith("Ich bin angestellt.")
        )
        unveraendert = "Ich bin Arbeitnehmer und habe zu Hause gearbeitet."
        self.assertEqual(
            bewahre_beschaeftigungsstatus("ich bin angestellt", unveraendert),
            unveraendert,
        )

    def test_kurzantwort_versicherung_bewahrt_frageziel(self):
        hinweise = " ".join(
            kanonisierungs_hinweise(
                "ja aber nur die haelfte",
                "Hat eine Versicherung etwas von der Rechnung übernommen?",
            )
        )
        self.assertIn("selbst getragenen Restes", hinweise)

    def test_gemeinsame_leitung_bewahrt_kostenaufteilung_als_frageziel(self):
        hinweise = " ".join(
            kanonisierungs_hinweise(
                "die gemeinsame leitung von meiner wohnung und einer mietwohnung",
                "War die Reparatur in deiner Wohnung oder einer Mietwohnung?",
            )
        )
        self.assertIn("Aufteilung der Reparaturkosten", hinweise)


if __name__ == "__main__":
    unittest.main()
