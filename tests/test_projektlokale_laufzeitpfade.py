import json
import os
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
PFADE_SCRIPT = ROOT / "app" / "lokale_laufzeitpfade.ps1"


def lade_pfade(quantisierung: str, script: Path = PFADE_SCRIPT) -> dict[str, str]:
    befehl = (
        f". '{script}'; "
        f"Get-SteuerAssistentLaufzeitPfade -Quantisierung {quantisierung} | "
        "ConvertTo-Json -Compress"
    )
    ausgabe = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", befehl],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(ausgabe.stdout)


def pfade_sind_gleich(tatsaechlich: Path, erwartet: Path) -> bool:
    befehl = (
        f". '{PFADE_SCRIPT}'; "
        f"Test-SteuerAssistentPfadGleich -Tatsaechlich '{tatsaechlich}' -Erwartet '{erwartet}'"
    )
    ausgabe = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", befehl],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return ausgabe.stdout.strip() == "True"


def befehlszeilenprofil_passt(
    profil: str,
    befehlszeile: str,
    modell: Path,
    port: int,
    projektor: Path | None = None,
) -> bool:
    befehl = (
        f". '{PFADE_SCRIPT}'; "
        "Test-SteuerAssistentBefehlszeilenProfil "
        f"-Profil {profil} -Befehlszeile $env:TEST_BEFEHLSZEILE "
        "-Modell $env:TEST_MODELL "
        f"-Port {port} "
        "-Projektor $env:TEST_PROJEKTOR"
    )
    umgebung = os.environ.copy()
    umgebung.update(
        {
            "TEST_BEFEHLSZEILE": befehlszeile,
            "TEST_MODELL": str(modell),
            "TEST_PROJEKTOR": "" if projektor is None else str(projektor),
        }
    )
    ausgabe = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", befehl],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=umgebung,
    )
    return ausgabe.stdout.strip() == "True"


def test_chat_vision_embedding_und_backend_liegen_im_projekt():
    pfade = lade_pfade("Q5_K_M")

    assert Path(pfade["Projekt"]) == ROOT
    assert Path(pfade["ChatModell"]) == ROOT / "models" / "steuer-assistent-pilot13-Q5_K_M.gguf"
    assert Path(pfade["VisionModell"]) == Path(pfade["ChatModell"])
    assert Path(pfade["VisionProjektor"]) == ROOT / "models" / "steuer-assistent-pilot13-mmproj-BF16.gguf"
    assert Path(pfade["EmbeddingModell"]) == ROOT / "models" / "qwen3-embedding-4b.gguf"
    assert Path(pfade["Server"]) == (
        ROOT
        / "runtime"
        / "llama.cpp-win-x86_64-nvidia-cuda12-avx2-2.55.0"
        / "llama-server.exe"
    )


def test_q4_fallback_verwendet_dasselbe_projektlokale_backend():
    q5 = lade_pfade("Q5_K_M")
    q4 = lade_pfade("Q4_K_M")

    assert Path(q4["ChatModell"]) == ROOT / "models" / "steuer-assistent-pilot13-Q4_K_M.gguf"
    assert q4["Server"] == q5["Server"]
    assert q4["EmbeddingModell"] == q5["EmbeddingModell"]


def test_gleicher_dateiname_auf_v_wird_nicht_als_projektlokales_modell_akzeptiert():
    lokales_modell = ROOT / "models" / "steuer-assistent-pilot13-Q5_K_M.gguf"
    altes_modell = Path(r"V:\LMStudio\.lmstudio\models\local\steuer-assistent") / lokales_modell.name

    assert pfade_sind_gleich(lokales_modell, lokales_modell)
    assert not pfade_sind_gleich(altes_modell, lokales_modell)


@pytest.mark.parametrize(
    "alter_projektpfad",
    [
        Path(r"C:\Users\USER\Documents\Codex\2026-08-20\referenced-chatgpt-conversation-this-is-an-2\Steuer-Assistent"),
        Path(r"V:\Codex\2026-08-20\referenced-chatgpt-conversation-this-is-an-2\Steuer-Assistent"),
    ],
)
def test_alte_junction_startpfade_werden_auf_d_kanonisiert(alter_projektpfad: Path):
    if not alter_projektpfad.exists():
        pytest.skip("Historischer Junction-Pfad ist auf diesem Rechner nicht eingerichtet")

    pfade = lade_pfade("Q5_K_M", alter_projektpfad / "app" / "lokale_laufzeitpfade.ps1")

    assert Path(pfade["Projekt"]) == ROOT
    assert Path(pfade["ChatModell"]).drive == "D:"
    assert Path(pfade["Server"]).drive == "D:"


def test_chatprofil_lehnt_embedding_und_vision_ab():
    pfade = lade_pfade("Q5_K_M")
    modell = Path(pfade["ChatModell"])
    projektor = Path(pfade["VisionProjektor"])
    basis = f'"{pfade["Server"]}" -m "{modell}" -c 8192 -np 1 --host 127.0.0.1 --port 1247 --no-webui'

    assert befehlszeilenprofil_passt("Chat", basis, modell, 1247)
    assert not befehlszeilenprofil_passt("Chat", f"{basis} --embedding", modell, 1247)
    assert not befehlszeilenprofil_passt(
        "Chat", f'{basis} --mmproj "{projektor}"', modell, 1247
    )


def test_embeddingprofil_verlangt_schalter_und_exaktes_modell():
    pfade = lade_pfade("Q5_K_M")
    modell = Path(pfade["EmbeddingModell"])
    basis = f'"{pfade["Server"]}" -m "{modell}" -c 8192 -np 1 --host 127.0.0.1 --port 1236 --no-webui'

    assert not befehlszeilenprofil_passt("Embedding", basis, modell, 1236)
    assert befehlszeilenprofil_passt("Embedding", f"{basis} --embedding", modell, 1236)
    assert not befehlszeilenprofil_passt(
        "Embedding", f"{basis} --embedding", ROOT / "models" / "anderes.gguf", 1236
    )
    assert not befehlszeilenprofil_passt(
        "Embedding",
        f'{basis} --embedding -m "{ROOT / "models" / "anderes.gguf"}"',
        modell,
        1236,
    )
    assert not befehlszeilenprofil_passt(
        "Embedding",
        f'{basis} --embedding --model "{ROOT / "models" / "anderes.gguf"}"',
        modell,
        1236,
    )
    assert befehlszeilenprofil_passt("Embedding", f"{basis} --embeddings", modell, 1236)


def test_visionprofil_verlangt_exakten_projektor():
    pfade = lade_pfade("Q5_K_M")
    modell = Path(pfade["VisionModell"])
    projektor = Path(pfade["VisionProjektor"])
    basis = f'"{pfade["Server"]}" -m "{modell}" -c 8192 -np 1 --host 127.0.0.1 --port 1237 --no-webui'

    assert not befehlszeilenprofil_passt("Vision", basis, modell, 1237, projektor)
    assert befehlszeilenprofil_passt(
        "Vision", f'{basis} --mmproj "{projektor}"', modell, 1237, projektor
    )
    assert not befehlszeilenprofil_passt(
        "Vision",
        f'{basis} --mmproj "{ROOT / "models" / "falsch.gguf"}"',
        modell,
        1237,
        projektor,
    )
    assert not befehlszeilenprofil_passt(
        "Vision",
        f'{basis} --mmproj "{projektor}" --mmproj "{ROOT / "models" / "falsch.gguf"}"',
        modell,
        1237,
        projektor,
    )
    assert not befehlszeilenprofil_passt(
        "Vision",
        f'{basis} --mmproj "{projektor}" -mm "{ROOT / "models" / "falsch.gguf"}"',
        modell,
        1237,
        projektor,
    )
