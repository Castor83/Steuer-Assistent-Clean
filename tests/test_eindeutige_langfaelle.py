import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
sys.path.insert(0, str(APP))

import rag_assistent


class EindeutigeLangfaelleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        daten = json.loads((ROOT / "tests" / "steuerex_haertetest_115.json").read_text(encoding="utf-8"))
        cls.fragen = {fall["id"]: fall["frage"] for fall in daten}

    def pruefe(self, fall_id, erwartete_teile):
        ergebnis = rag_assistent.beantworte(self.fragen[fall_id])
        self.assertIsNotNone(ergebnis)
        antwort, quellen = ergebnis
        self.assertTrue(quellen)
        for teil in erwartete_teile:
            self.assertIn(teil, antwort)

    def test_abgabefrist_2019(self):
        self.pruefe(1006, ("31. Juli 2020", "§ 149"))

    def test_tatsaechlich_spaeterer_zugang_2020(self):
        self.pruefe(1007, ("Montag, dem 31. August 2020", "Dreitagesfiktion", "§ 124"))

    def test_el_gordo_lottogewinn(self):
        self.pruefe(1020, ("unbeschränkt", "nicht", "§ 2 Absatz 1 EStG", "DBA"))

    def test_erbschaftsteuerklasse_und_tarif(self):
        self.pruefe(1029, ("Steuerklasse I", "§ 15", "19 Prozent", "§ 19"))

    def test_lottogewinn_und_spieleinsatz(self):
        self.pruefe(1031, ("nicht", "Spieleinsatz", "nicht als Erwerbsaufwendungen"))

    def test_erststudium_nach_abitur(self):
        self.pruefe(
            1032,
            ("Erststudium", "Sonderausgaben", "2.100 Euro", "keinen Verlustvortrag"),
        )

    def test_bella_einkunftsart(self):
        self.pruefe(1048, ("nichtselbständiger Arbeit", "§ 19", "Überschusseinkünfte"))

    def test_bella_einkuenfte_2023(self):
        self.pruefe(
            1049,
            ("34.340 Euro", "600 Euro Tagespauschale", "60 Euro Entfernungspauschale", "1.660 Euro"),
        )

    def test_tassilo_subjektive_steuerpflicht(self):
        self.pruefe(1002, ("unbeschränkt einkommensteuerpflichtig", "§ 1 Absatz 1"))

    def test_tassilo_arbeitslohn(self):
        self.pruefe(1003, ("nichtselbständiger Arbeit", "30.000 Euro", "Überschusseinkünfte"))

    def test_tassilo_summe_der_einkuenfte(self):
        self.pruefe(1004, ("118.580 Euro", "4.830 Euro", "83.750 Euro", "3.750 Euro"))

    def test_tassilo_pflichtveranlagung(self):
        self.pruefe(1005, ("Ja", "§ 46 Absatz 2 Nummer 1", "410 Euro"))

    def test_hochwasserschaden_eigenheim(self):
        self.pruefe(
            1050,
            ("Ja, dem Grunde nach", "§ 33 EStG", "Bewohnbarkeit", "zumutbare Belastung"),
        )


if __name__ == "__main__":
    unittest.main()
