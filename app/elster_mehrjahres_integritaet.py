"""Prüft die fixierten Browserartefakte für ESt 2023 bis 2025."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
STEUERJAHRE = ("2023", "2024", "2025")
SCHEMA = "steuer-assistent-elster-browser-golden-master/v1"


def _datei_hash(pfad: Path) -> str:
    return sha256(pfad.read_bytes()).hexdigest()


def pruefe_mehrjahres_golden_master() -> list[str]:
    fehler: list[str] = []
    for steuerjahr in STEUERJAHRE:
        manifest_pfad = ROOT / "tests" / "golden_master" / f"elster_browser_{steuerjahr}_v1.json"
        try:
            manifest = json.loads(manifest_pfad.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            fehler.append(f"{steuerjahr}: Golden Master nicht lesbar: {exc}")
            continue
        if manifest.get("schema") != SCHEMA or manifest.get("steuerjahr") != steuerjahr:
            fehler.append(f"{steuerjahr}: Golden-Master-Kopf ist ungültig.")
        status = manifest.get("status", {})
        if status != {"sandbox_validiert": True, "live_layout_validiert": False}:
            fehler.append(f"{steuerjahr}: Freigabestatus ist nicht fail-closed.")
        for schluessel in ("mapping", "sandbox_eingabe"):
            eintrag = manifest.get(schluessel, {})
            relativer_pfad = Path(str(eintrag.get("pfad", "")))
            ziel = (ROOT / relativer_pfad).resolve()
            try:
                ziel.relative_to(ROOT.resolve())
            except ValueError:
                fehler.append(f"{steuerjahr}: {schluessel} verlässt den Projektordner.")
                continue
            if not ziel.is_file():
                fehler.append(f"{steuerjahr}: {schluessel} fehlt: {relativer_pfad}")
            elif _datei_hash(ziel) != eintrag.get("sha256"):
                fehler.append(f"{steuerjahr}: Prüfsumme für {schluessel} stimmt nicht.")
    return fehler


if __name__ == "__main__":
    probleme = pruefe_mehrjahres_golden_master()
    if probleme:
        raise SystemExit("\n".join(probleme))
    print("ESt 2023–2025: alle Browser-Golden-Master unverändert.")
