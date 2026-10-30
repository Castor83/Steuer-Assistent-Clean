import sys
import re
import unittest
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

import umgangssprache_trainingsdaten as sprachdaten


class UmgangsspracheTrainingsdatenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.train = sprachdaten.jsonl_laden(sprachdaten.QUELLORDNER / "train.jsonl")

    def test_thema_wird_ohne_paragraphenpraefix_lesbar(self):
        spenden = next(x for x in self.train if "Spenden" in x["messages"][1]["content"])
        self.assertEqual("Spenden", sprachdaten.thema_aus_beispiel(spenden))

    def test_80_eindeutige_varianten_pro_basisfall(self):
        beispiele = sprachdaten.kanonisierungsbeispiele_bauen(self.train[:2], 80)
        self.assertEqual(160, len(beispiele))
        self.assertEqual(160, len({x["messages"][1]["content"].casefold() for x in beispiele}))
        self.assertTrue(all(x["metadaten"]["fachantwort_enthalten"] is False for x in beispiele))

    def test_kanonisierung_beantwortet_die_steuerfrage_nicht(self):
        basis = self.train[0]
        beispiel = sprachdaten.kanonisierungsbeispiele_bauen([basis], 1)[0]
        thema = sprachdaten.thema_aus_beispiel(basis)
        ziel = beispiel["messages"][-1]["content"]
        self.assertEqual(sprachdaten.kanonische_frage(thema), ziel)
        self.assertNotEqual(basis["messages"][-1]["content"], ziel)
        self.assertNotIn("Rechtsstand", ziel)

    def test_kanonisierung_erfindet_keine_jahreszahl(self):
        beispiele = sprachdaten.kanonisierungsbeispiele_bauen(self.train, 1)
        for beispiel in beispiele:
            eingabe = beispiel["messages"][-2]["content"]
            ziel = beispiel["messages"][-1]["content"]
            self.assertEqual(
                set(re.findall(r"\b(?:19|20)\d{2}\b", eingabe)),
                set(re.findall(r"\b(?:19|20)\d{2}\b", ziel)),
                beispiel["id"],
            )

    def test_mehrturn_dialog_uebernimmt_fachantwort_unveraendert(self):
        basis = self.train[0]
        dialoge = sprachdaten.dialogbeispiele_bauen([basis])
        self.assertEqual(4, len(dialoge))
        self.assertTrue(all(x["messages"][-1] == basis["messages"][-1] for x in dialoge))
        self.assertTrue(all(x["metadaten"]["fachantwort_unveraendert"] for x in dialoge))

    def test_tippfehler_bleibt_kontrolliert(self):
        text, stil = sprachdaten.oberflaeche_variieren(
            "Was bedeutet das für meine Steuererklärung?", 3
        )
        self.assertEqual("ein_tippfehler", stil)
        self.assertIn("steuererklerung", text)

    def test_tippfehlermodus_aendert_jede_vorlage(self):
        for vorlage in sprachdaten.EINLEITUNGEN:
            original = vorlage.format(thema="Arbeitskleidung") + "?"
            fehler, stil = sprachdaten.oberflaeche_variieren(original, 3)
            self.assertEqual("ein_tippfehler", stil)
            self.assertNotEqual(original.casefold().rstrip("?"), fehler.casefold())

    def test_split_basisfaelle_sind_getrennt(self):
        splits = {
            name: sprachdaten.jsonl_laden(sprachdaten.QUELLORDNER / f"{name}.jsonl")
            for name in ("train", "validation", "test")
        }
        mengen = [{x["id"] for x in splits[name]} for name in ("train", "validation", "test")]
        self.assertFalse(mengen[0] & mengen[1])
        self.assertFalse(mengen[0] & mengen[2])
        self.assertFalse(mengen[1] & mengen[2])


if __name__ == "__main__":
    unittest.main()
