"""Prüft fiktive Personas ohne Zugriff auf echte Nutzerregister."""

from __future__ import annotations

import csv
from decimal import Decimal
import json
from pathlib import Path
import sys
import tempfile
import unittest


PROJEKT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJEKT / "app"))

from ordner_ueberwacher import erkenne_dokumenttyp  # noqa: E402
from steuerakte import erstelle_steuerakte  # noqa: E402
from steuerprofil import empfohlene_bereiche  # noqa: E402


PERSONAS = PROJEKT / "testDaten" / "synthetische_personas" / "personas.json"
FINANZDATEN = PROJEKT / "testDaten" / "synthetische_personas" / "finanzdaten.json"
FINANZDATEN_CSV = PROJEKT / "testDaten" / "synthetische_personas" / "finanzdaten.csv"


class SynthetischePersonasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.personas = json.loads(PERSONAS.read_text(encoding="utf-8"))["personas"]

    def test_alle_personas_sind_eindeutig_und_klar_markiert(self) -> None:
        self.assertEqual(8, len(self.personas))
        self.assertTrue(
            {"arbeitnehmerin_2025", "ehepaar_2025", "selbststaendig_2025", "gewerbe_2025", "investor_2025"}
            .issubset({p["id"] for p in self.personas})
        )
        self.assertEqual(len(self.personas), len({p["id"] for p in self.personas}))
        alle_dateinamen = []
        for persona in self.personas:
            self.assertTrue(persona["name"].startswith("Testperson "))
            for beleg in persona["belege"]:
                self.assertIn("SYNTHETISCHE TESTDATEI – NICHT EINREICHEN", beleg["inhalt"])
                self.assertTrue(beleg["dateiname"].startswith("TEST-"))
                alle_dateinamen.append(beleg["dateiname"])
        self.assertEqual(len(alle_dateinamen), len(set(alle_dateinamen)))

    def test_belege_werden_erkannt_und_jahresakten_bleiben_getrennt(self) -> None:
        for persona in self.personas:
            with self.subTest(persona=persona["id"]), tempfile.TemporaryDirectory() as verzeichnis:
                dokumente = []
                for beleg in persona["belege"]:
                    pfad = Path(verzeichnis) / beleg["dateiname"]
                    pfad.write_text(beleg["inhalt"], encoding="utf-8")
                    typ, _, _, jahr = erkenne_dokumenttyp(pfad)
                    self.assertEqual(beleg["erwarteter_typ"], typ, beleg["dateiname"])
                    self.assertEqual(beleg["erwartetes_jahr"], jahr, beleg["dateiname"])
                    dokumente.append(
                        {
                            "dateiname": beleg["dateiname"],
                            "dokumenttyp": typ,
                            "steuerjahr": jahr,
                            "status": beleg["status"],
                            "nutzerzuordnung": {"status": "Erkannt", "bestaetigt": True},
                            "wertvorschlaege": beleg.get("wertvorschlaege", []),
                        }
                    )

                self.assertEqual(
                    persona["erwartete_empfohlene_bereiche"],
                    empfohlene_bereiche(persona["profil"]),
                )
                akte = erstelle_steuerakte(persona["steuerjahr"], persona["bereiche"], dokumente)
                self.assertEqual(persona["erwarteter_aktenstatus"], akte["status"])
                self.assertEqual(len(dokumente), akte["zusammenfassung"]["dokumente"])
                warncodes = {warnung["code"] for warnung in akte["warnungen"]}
                self.assertTrue(set(persona["erwartete_warncodes"]).issubset(warncodes))
                anderes_jahr = "2024" if persona["steuerjahr"] != "2024" else "2025"
                fremde_akte = erstelle_steuerakte(anderes_jahr, persona["bereiche"], dokumente)
                self.assertEqual(0, fremde_akte["zusammenfassung"]["dokumente"])

    def test_finanzdaten_passen_zu_personas_und_belegen(self) -> None:
        daten = json.loads(FINANZDATEN.read_text(encoding="utf-8"))
        faelle = daten["faelle"]
        personas = {persona["id"]: persona for persona in self.personas}
        self.assertEqual(set(personas), {fall["persona_id"] for fall in faelle})
        self.assertEqual([], next(fall for fall in faelle if fall["persona_id"] == "leer_2025")["positionen"])
        ids = set()
        erwartete_csv_zeilen = []
        for fall in faelle:
            persona = personas[fall["persona_id"]]
            self.assertEqual(persona["steuerjahr"], fall["steuerjahr"])
            belege = {beleg["dateiname"] for beleg in persona["belege"]}
            positionen = {position["id"]: position for position in fall["positionen"]}
            for position in fall["positionen"]:
                self.assertNotIn(position["id"], ids)
                ids.add(position["id"])
                self.assertIn(position["beleg"], belege)
                if "betrag_eur" in position:
                    self.assertGreaterEqual(Decimal(position["betrag_eur"]), 0)
                if position["wertart"] == "bestandteil":
                    summe = positionen[position["in_summe_von"]]
                    self.assertEqual("jahressumme", summe["wertart"])
                    self.assertLessEqual(Decimal(position["betrag_eur"]), Decimal(summe["betrag_eur"]))
                if position["art"].startswith("krypto_") or position["art"] == "auslaendische_ertraege_ungeklaert":
                    self.assertEqual("steuerliche_einordnung_offen", position["pruefstatus"])
                erwartete_csv_zeilen.append((fall["persona_id"], position["id"], position.get("betrag_eur", "")))
        self.assertEqual(30, len(ids))
        with FINANZDATEN_CSV.open(encoding="utf-8-sig", newline="") as datei:
            csv_zeilen = list(csv.DictReader(datei, delimiter=";"))
        self.assertEqual(
            erwartete_csv_zeilen,
            [(zeile["persona_id"], zeile["id"], zeile["betrag_eur"]) for zeile in csv_zeilen],
        )
        self.assertTrue(all(zeile["kennzeichnung"] == daten["kennzeichnung"] for zeile in csv_zeilen))


if __name__ == "__main__":
    unittest.main()
