import sys
import unittest
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))

import rag_assistent
import trainingsdaten_erstellen


class GrundsteuerKernthemaTest(unittest.TestCase):
    def test_grundsteuer_ist_kernthema(self):
        self.assertIn("Grundsteuer und kommunale Grundabgaben", rag_assistent.ASSISTENTEN_KERNTHEMEN)
        self.assertIn("Grundsteuermessbescheid", rag_assistent.GRUNDSTEUER_ANTWORTREGELN)

    def test_grundabgaben_werden_sicher_eingeordnet(self):
        ergebnis = rag_assistent.neu_abgesicherte_grundfaelle(
            "Wie prüfe ich meinen Grundbesitzabgabenbescheid?",
            [],
        )
        self.assertIsNotNone(ergebnis)
        antwort, quellen = ergebnis
        self.assertTrue(quellen)
        self.assertIn("kein einzelner Betrag", antwort)
        self.assertIn("örtlichen Satzungen", antwort)

    def test_grundabgaben_haben_vorrang_vor_allgemeiner_grundsteuer_jahresregel(self):
        antwort, quellen = rag_assistent.beantworte(
            "grundabgaben erlangen mit strassenreinigung abwasser und grundsteuer "
            "muss man das getrennt ansehen",
            steuerprofil={
                "grundabgaben_standardobjekt": {
                    "stadt": "Erlangen",
                    "gebaeudeart": "Dreifamilienhaus",
                }
            },
            steuerjahr="2023",
        )
        self.assertTrue(antwort.startswith("Ja, diese Positionen müssen getrennt"))
        self.assertIn("Straßenreinigung", antwort)
        self.assertIn("Abwasser", antwort)
        self.assertIn("Dreifamilienhaus in Erlangen", antwort)
        self.assertNotIn("Einheitswerte", antwort)
        self.assertTrue(quellen)

    def test_training_hat_eigenes_grundsteuer_thema(self):
        quelle = {
            "titel": "Grundsteuerbescheid und Hebesatz",
            "kategorie": "Grundsteuer",
            "paragraph": "§ 25 GrStG",
        }
        thema = trainingsdaten_erstellen.thema_bestimmen("grundsteuer_hebesatz.json", quelle)
        self.assertEqual("Grundsteuer und kommunale Grundabgaben", thema)


if __name__ == "__main__":
    unittest.main()
