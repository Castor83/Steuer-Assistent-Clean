from pathlib import Path
import json
import sys
from unittest.mock import MagicMock, patch

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from modell_ressourcen import ModellRessourcenManager


def test_manager_verwendet_ausschliesslich_lokale_gguf_runtimes():
    konfiguration = ModellRessourcenManager().konfiguration()
    assert konfiguration["chat_backend"] == "lmstudio"
    assert konfiguration["embedding_backend"] == "lmstudio"
    assert konfiguration["vision_backend"] == "lmstudio"
    assert konfiguration["chat_fallback_backend"] == "gguf"
    assert konfiguration["nutzerabhaengig"] is False


def test_chat_uebersetzt_in_lokales_api_format():
    manager = ModellRessourcenManager()
    http_antwort = MagicMock()
    http_antwort.__enter__.return_value.read.return_value = json.dumps({
        "choices": [{"message": {"role": "assistant", "content": "Antwort"}}],
        "timings": {"prompt_ms": 120.0, "predicted_ms": 500.0, "predicted_n": 51},
        "usage": {"completion_tokens": 51},
    }).encode("utf-8")
    with patch("modell_ressourcen.urlopen", return_value=http_antwort) as aufruf:
        antwort = manager.chat(
            "interner-name", [{"role": "user", "content": "Frage"}],
            options={"temperature": 0, "num_predict": 64, "num_ctx": 4096},
        )
    payload = json.loads(aufruf.call_args.args[0].data.decode("utf-8"))
    assert payload["model"] == "steuer-assistent-q5"
    assert payload["max_tokens"] == 64
    assert antwort["message"]["content"] == "Antwort"
    assert antwort["eval_count"] == 51


def test_chat_blockiert_zu_grossen_kontext():
    manager = ModellRessourcenManager()
    with patch("modell_ressourcen.urlopen") as aufruf, pytest.raises(
        ValueError, match="überschreitet das LM-Studio-Profil"
    ):
        manager.chat("x", [{"role": "user", "content": "x"}], options={"num_ctx": 65536})
    aufruf.assert_not_called()


def test_chat_ausfall_startet_q4_gguf_fallback():
    manager = ModellRessourcenManager()
    with patch.object(
        manager, "_lmstudio_chat",
        side_effect=[RuntimeError("LM Studio ist nicht einsatzbereit"), {"message": {"content": "Q4"}}],
    ) as chat, patch.object(manager, "_chat_runtime_befehl") as runtime:
        antwort = manager.chat_mit_fallback("q5", "q4", [{"role": "user", "content": "Frage"}])
    assert antwort["message"]["content"] == "Q4"
    assert [aufruf.args for aufruf in runtime.call_args_list] == [
        ("-Stoppen",), ("-Quantisierung", "Q4_K_M")
    ]
    assert chat.call_count == 2


def test_embedding_uebersetzt_openai_format(monkeypatch):
    monkeypatch.setenv("STEUER_LMSTUDIO_EMBEDDING_BATCH", "2")
    manager = ModellRessourcenManager()
    http_antwort = MagicMock()
    http_antwort.__enter__.return_value.read.return_value = json.dumps({
        "data": [{"index": 1, "embedding": [0.3]}, {"index": 0, "embedding": [0.1]}]
    }).encode("utf-8")
    with patch("modell_ressourcen.urlopen", return_value=http_antwort):
        antwort = manager.embedding("embed", ["eins", "zwei"])
    assert antwort["embeddings"] == [[0.1], [0.3]]


def test_embedding_startet_runtime_nach_verbindungsfehler():
    manager = ModellRessourcenManager()
    with patch.object(
        manager, "_lmstudio_embedding",
        side_effect=[RuntimeError("nicht bereit"), {"embeddings": [[1.0]]}],
    ), patch.object(manager, "_embedding_runtime_starten") as starten:
        antwort = manager.embedding("embed", "Text")
    assert antwort["embeddings"] == [[1.0]]
    starten.assert_called_once_with()


def test_vision_stoppt_embedding_und_stellt_chat_wieder_her():
    manager = ModellRessourcenManager()
    with patch.object(manager, "_embedding_runtime_stoppen") as embedding, patch.object(
        manager, "_chat_runtime_befehl"
    ) as chat, patch.object(manager, "_vision_runtime_befehl") as vision, patch.object(
        manager, "_lmstudio_vision", return_value={"message": {"content": "ok"}}
    ):
        antwort = manager.vision_chat("vision", [{"role": "user", "content": "scan"}])
    assert antwort["message"]["content"] == "ok"
    embedding.assert_called_once_with()
    assert [aufruf.args for aufruf in chat.call_args_list] == [("-Stoppen",), ()]
    assert [aufruf.args for aufruf in vision.call_args_list] == [(), ("-Stoppen",)]


def test_chat_cleanup_beendet_persistente_runtime_nicht():
    manager = ModellRessourcenManager()
    with patch.object(manager, "_chat_runtime_befehl") as runtime:
        assert manager.chat_entladen("q5") is None
    runtime.assert_not_called()
