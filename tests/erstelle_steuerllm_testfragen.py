"""Baut einen quellengebundenen Fragenentwurf, ohne Modelle oder Trainingsskripte."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("quelle", type=Path)
    args = parser.parse_args()
    basis = args.quelle.resolve()
    katalog = []
    with (ROOT / "tests/steuerllm_fragen_entwurf.tsv").open(encoding="utf-8", newline="") as stream:
        for nummer, entwurf in enumerate(csv.DictReader(stream, delimiter="\t"), 1):
            relativ = Path("Data-Generation/Instruct-Generation/Data") / (entwurf["gesetz"] + ".jsonl")
            raw = (basis / relativ).read_bytes()
            treffer = [(i, json.loads(line)) for i, line in enumerate(raw.decode("utf-8-sig").splitlines(), 1)
                       if line.strip() and json.loads(line).get("num") == "§ " + entwurf["paragraph"]]
            if len(treffer) != 1 or not treffer[0][1].get("text", "").strip():
                raise ValueError(f"Fundstelle fehlt oder ist uneindeutig: {entwurf}")
            zeile, norm = treffer[0]
            katalog.append({
                "id": f"SLLM{nummer:03d}", "frage": entwurf["frage"], "thema": entwurf["gesetz"],
                "prueffokus": entwurf["prueffokus"], "steuerjahr": None,
                "erwartete_antwort": None, "automatische_fachbewertung": False,
                "aktualitaetspruefung_erforderlich": True,
                "quelle_datei": relativ.as_posix(), "quelle_zeile": zeile,
                "quelle_sha256": hashlib.sha256(raw).hexdigest(),
                "quelle_datensatz_id": norm.get("id"), "paragraph": norm["num"],
                "normtitel": norm.get("title", ""), "quelltext": norm["text"],
            })
    ziel = ROOT / "tests/steuerllm_testfragen_50.json"
    ziel.write_text(json.dumps(katalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text = ["# 50 Testfragen aus SteuerLLM", "",
            "Neu formulierte Fallfragen aus den lokalen Gesetzesdateien. Kein Modelllauf und kein Training.", "",
            f"Quelldirectory: `{basis}`. Herkunft: SteuerLLM, Wind et al., 2026 (README des lokalen Repositorys).",
            "Die dortige Nutzungsangabe lautet: Research and academic use only.", "",
            "Der Rechtsstand ist nicht gesichert. Prüffokus sind redaktionelle Prüfhinweise, keine freigegebenen Musterantworten. "
            "Vor einer fachlichen Bewertung müssen die für das Testjahr geltenden Normen und die erwarteten Antworten geprüft werden. "
            "Bis dahin bleiben Steuerjahr und Sollantwort leer; automatische Fachbewertung ist deaktiviert.", "",
            "Jeder JSON-Eintrag enthält Datei, Zeilennummer, SHA-256 und den lokalen Normtext zur Nachprüfung. "
            "Bei Testläufen nur die Frage an den Assistenten übergeben, nicht den beigefügten Quelltext. "
            "Der Bestand stammt aus einer Trainingspipeline und ist kein nachgewiesen unabhängiger Benchmark. "
            "Die vorhandene Praxischarge bleibt separat.", "",
            "Reproduzieren: `.\\.venv\\Scripts\\python.exe tests/erstelle_steuerllm_testfragen.py \"C:\\Users\\USER\\Desktop\\AI\\steuerllm-main\"`", ""]
    for fall in katalog:
        text.extend([f"## {fall['id']} – {fall['thema']}, {fall['paragraph']}", "", fall["frage"], "",
                     f"Prüffokus: {fall['prueffokus']}", "",
                     f"Fundstelle: `{fall['quelle_datei']}`, Zeile {fall['quelle_zeile']} ({fall['normtitel']}).", ""])
    (ROOT / "STEUERLLM_TESTFRAGEN_50.md").write_text("\n".join(text), encoding="utf-8")
    print(f"{len(katalog)} Fragen erstellt: {ziel}")


if __name__ == "__main__":
    main()
