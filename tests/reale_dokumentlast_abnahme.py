"""Realer, bewusst nicht automatisch von pytest gestarteter GPU-Abnahmelauf."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from modell_ressourcen import ModellRessourcenManager
from performance_abnahme import STANDARD_GRENZEN, performance_freigegeben, pruefe_performance


def gpu_mib() -> int:
    ausgabe = subprocess.check_output([
        "nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"
    ], text=True)
    return max(int(zeile.strip()) for zeile in ausgabe.splitlines() if zeile.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--modell", default="steuer-assistent-pilot13:bf16")
    parser.add_argument("--embedding", default="qwen3-embedding:4b")
    parser.add_argument("--vision-modell", default="steuer-assistent-pilot13:bf16")
    parser.add_argument("--fallback", default="qwen3.5:9b")
    parser.add_argument("--dokument", default=str(ROOT / "dokumente/eingang/20260909_160930.jpg"))
    parser.add_argument("--ausgabe", default=str(ROOT / "tests/ergebnisse/reale_dokumentlast_abnahme.json"))
    args = parser.parse_args()
    # Die regulären Startskripte setzen diese Werte für die Web-App. Der
    # eigenständig gestartete Abnahmelauf muss denselben geprüften Standard
    # verwenden und darf nicht unbemerkt auf eine andere Runtime fallen.
    os.environ.setdefault("STEUER_CHAT_BACKEND", "lmstudio")
    os.environ.setdefault("STEUER_EMBEDDING_BACKEND", "lmstudio")
    os.environ.setdefault("STEUER_VISION_BACKEND", "lmstudio")
    manager = ModellRessourcenManager()
    spitzen = {"vram": 0}
    stop = threading.Event()

    def beobachten():
        while not stop.wait(.2):
            spitzen["vram"] = max(spitzen["vram"], gpu_mib())

    def rag(frage):
        start = time.perf_counter()
        manager.embedding(args.embedding, frage)
        antwort = manager.chat_mit_fallback(
            args.modell, args.fallback, [{"role": "user", "content": frage}],
            options={"temperature": 0, "num_predict": 96},
        )
        ttft = (antwort.get("load_duration", 0) + antwort.get("prompt_eval_duration", 0)) / 1e9
        rate = antwort.get("eval_count", 0) / max(antwort.get("eval_duration", 0) / 1e9, .001)
        return {"art": "rag", "frage": frage, "sekunden": time.perf_counter() - start, "ttft": ttft,
                "token_pro_sekunde": rate, "neuladung": int(antwort.get("load_duration", 0) > 100_000_000)}

    def vision():
        start = time.perf_counter()
        antwort = manager.vision_chat(args.vision_modell, [{
            "role": "user", "content": "Lies das Dokument und nenne Dokumentart und Steuerjahr knapp.",
            "images": [str(Path(args.dokument).resolve())],
        }], options={"temperature": 0, "num_predict": 96}, fallback_modell=args.fallback)
        ttft = (antwort.get("load_duration", 0) + antwort.get("prompt_eval_duration", 0)) / 1e9
        rate = antwort.get("eval_count", 0) / max(antwort.get("eval_duration", 0) / 1e9, .001)
        return {"art": "vision", "sekunden": time.perf_counter() - start, "ttft": ttft,
                "token_pro_sekunde": rate, "neuladung": int(antwort.get("load_duration", 0) > 100_000_000)}

    manager.embedding(args.embedding, "Vorladung fuer den Lasttest")
    watcher = threading.Thread(target=beobachten, daemon=True)
    watcher.start()
    start = time.perf_counter()
    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            jobs = [
                pool.submit(vision),
                pool.submit(rag, "Wie wird Insolvenzgeld steuerlich behandelt?"),
                pool.submit(rag, "Welche Unterlagen brauche ich fuer die bayerische Grundsteuer?"),
            ]
            details = []
            fehler = []
            for job in jobs:
                try:
                    details.append(job.result())
                except Exception as exc:
                    fehler.append(f"{type(exc).__name__}: {exc}")
    finally:
        stop.set()
        watcher.join(timeout=2)
    vollstaendig = len(details) == 3 and not fehler
    messung = {
        "ttft_sekunden": max((item["ttft"] for item in details), default=1_000_000_000),
        "token_pro_sekunde": min((item["token_pro_sekunde"] for item in details), default=0),
        "gesamt_sekunden": time.perf_counter() - start,
        "vram_spitze_mib": spitzen["vram"],
        "neuladungen": sum(item["neuladung"] for item in details),
        "oom_wiederholungen": manager.messwerte()["vision_oom_wiederholungen"],
    }
    bericht = {
        "modell": args.modell, "vision_modell": args.vision_modell,
        "dokument": str(Path(args.dokument).resolve()), "messung": messung,
        "grenzen": STANDARD_GRENZEN.__dict__, "pruefungen": pruefe_performance(messung),
        "freigegeben": vollstaendig and performance_freigegeben(messung),
        "vollstaendig": vollstaendig, "fehler": fehler,
        "ressourcenmanager": manager.messwerte(), "details": details,
    }
    ziel = Path(args.ausgabe)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(json.dumps(bericht, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(bericht, ensure_ascii=False, indent=2))
    return 0 if bericht["freigegeben"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
