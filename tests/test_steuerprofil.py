from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from steuerprofil import empfohlene_bereiche, lade_steuerprofil, profil_uebersicht


class SteuerprofilTest(unittest.TestCase):
    def test_bestaetigtes_profil_empfiehlt_passende_bereiche(self):
        profil = lade_steuerprofil()
        self.assertEqual(
            ["arbeitnehmer", "vermietung", "haushalt", "grundsteuer"],
            empfohlene_bereiche(profil),
        )

    def test_uebersicht_nennt_bestaetigte_daten_und_offene_wohnungszahlen(self):
        uebersicht = profil_uebersicht(lade_steuerprofil())
        self.assertTrue(uebersicht["gespeichert"])
        self.assertIn("Angestellter", uebersicht["angaben"])
        self.assertTrue(any("Beispielstraße 1" in text for text in uebersicht["angaben"]))
        self.assertIn("Dreifamilienhaus", uebersicht["angaben"])
        self.assertEqual(2, len(uebersicht["offene_angaben"]))
        self.assertEqual("2023", uebersicht["steuerjahr_vorschlag"])
        self.assertIn("voraussichtlich", uebersicht["steuerjahr_status"])
        self.assertEqual(2, uebersicht["version"])

    def test_leeres_profil_erzeugt_keine_empfehlungen(self):
        self.assertEqual([], empfohlene_bereiche({}))
        self.assertFalse(profil_uebersicht({})["gespeichert"])


if __name__ == "__main__":
    unittest.main()
