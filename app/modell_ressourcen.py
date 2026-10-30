"""Zentrale Laufzeitsteuerung der lokalen Modellserver.

Der Manager ist pro Serverprozess einmal vorhanden. Nutzerwechsel verändern
seinen Zustand nicht. Chat, Embeddings und Vision laufen ausschließlich über
die lokalen GGUF-Runtimes.
"""

from __future__ import annotations

import json
import base64
import mimetypes
import os
from pathlib import Path
import subprocess
import sys
import threading
from typing import Any, Mapping, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

class ModellRessourcenManager:
    def __init__(self) -> None:
        self.chat_backend = "lmstudio"
        self.lmstudio_url = os.environ.get(
            "STEUER_LMSTUDIO_URL", "http://127.0.0.1:1235/v1"
        ).rstrip("/")
        self.lmstudio_modell = os.environ.get(
            "STEUER_LMSTUDIO_MODELL", "steuer-assistent-q5"
        )
        self.chat_fallback_backend = "gguf"
        self.gguf_fallback_quantisierung = os.environ.get(
            "STEUER_GGUF_FALLBACK_QUANTISIERUNG", "Q4_K_M"
        ).strip()
        self.lmstudio_timeout = float(os.environ.get("STEUER_LMSTUDIO_TIMEOUT", "120"))
        self.lmstudio_kontext = int(os.environ.get("STEUER_LMSTUDIO_KONTEXT", "32768"))
        self.embedding_backend = "lmstudio"
        self.lmstudio_embedding_url = os.environ.get(
            "STEUER_LMSTUDIO_EMBEDDING_URL", "http://127.0.0.1:1236/v1"
        ).rstrip("/")
        self.lmstudio_embedding_modell = os.environ.get(
            "STEUER_LMSTUDIO_EMBEDDING_MODELL", "qwen3-embedding-4b"
        )
        self.lmstudio_embedding_batch = max(
            1, int(os.environ.get("STEUER_LMSTUDIO_EMBEDDING_BATCH", "1"))
        )
        self.vision_backend = "lmstudio"
        self.lmstudio_vision_url = os.environ.get(
            "STEUER_LMSTUDIO_VISION_URL", "http://127.0.0.1:1237/v1"
        ).rstrip("/")
        self.lmstudio_vision_modell = os.environ.get(
            "STEUER_LMSTUDIO_VISION_MODELL", "steuer-assistent-vision-q5"
        )
        self._vision_startskript = Path(__file__).with_name("lmstudio_vision_runtime_starten.ps1")
        self._embedding_startskript = Path(__file__).with_name(
            "lmstudio_embedding_runtime_starten.ps1"
        )
        self._chat_startskript = Path(__file__).with_name("lmstudio_steuer_runtime_starten.ps1")
        self.chat_keep_alive = os.environ.get("STEUER_CHAT_KEEP_ALIVE", "10m")
        self.embedding_keep_alive = os.environ.get("STEUER_EMBEDDING_KEEP_ALIVE", "5m")
        self.fallback_keep_alive = os.environ.get("STEUER_FALLBACK_KEEP_ALIVE", "0")
        # Modellwechsel werden serialisiert, damit die drei lokalen Runtimes
        # nicht gleichzeitig um denselben Grafikspeicher konkurrieren.
        self._modell_lock = threading.RLock()
        self._letztes_embedding_modell: str | None = None
        self._vision_aktiv = False
        self._gesperrte_modelle: dict[str, str] = {}
        self._messwerte = {
            "embedding_entladungen": 0,
            "vision_entladungen": 0,
            "vision_oom_wiederholungen": 0,
            "vision_modell_fallbacks": 0,
            "chat_modell_fallbacks": 0,
            "runner_fehler": 0,
        }

    def embedding(self, modell: str, eingabe: str | Sequence[str]):
        with self._modell_lock:
            try:
                ergebnis = self._lmstudio_embedding(eingabe)
            except RuntimeError:
                self._embedding_runtime_starten()
                ergebnis = self._lmstudio_embedding(eingabe)
            self._letztes_embedding_modell = modell
            return ergebnis

    def _lmstudio_embedding(self, eingabe: str | Sequence[str]) -> dict:
        if isinstance(eingabe, str):
            return self._lmstudio_embedding_batch(eingabe)
        texte = list(eingabe)
        if len(texte) <= self.lmstudio_embedding_batch:
            return self._lmstudio_embedding_batch(texte)
        embeddings: list[list[float]] = []
        verwendung: dict[str, int] = {}
        for start in range(0, len(texte), self.lmstudio_embedding_batch):
            teil = self._lmstudio_embedding_batch(
                texte[start : start + self.lmstudio_embedding_batch]
            )
            embeddings.extend(teil["embeddings"])
            for name, wert in teil.get("usage", {}).items():
                if isinstance(wert, int):
                    verwendung[name] = verwendung.get(name, 0) + wert
        return {
            "embeddings": embeddings,
            "model": self.lmstudio_embedding_modell,
            "usage": verwendung,
        }

    def _lmstudio_embedding_batch(self, eingabe: str | Sequence[str]) -> dict:
        payload = {
            "model": self.lmstudio_embedding_modell,
            "input": eingabe,
        }
        anfrage = Request(
            f"{self.lmstudio_embedding_url}/embeddings",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(anfrage, timeout=self.lmstudio_timeout) as antwort:
                daten = json.loads(antwort.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(
                f"LM-Studio-Embedding ist nicht einsatzbereit: {exc}"
            ) from exc
        punkte = sorted(daten.get("data", []), key=lambda punkt: punkt.get("index", 0))
        if not punkte or any(not isinstance(punkt.get("embedding"), list) for punkt in punkte):
            raise RuntimeError("LM Studio lieferte keine gueltigen Embeddings.")
        return {
            "embeddings": [punkt["embedding"] for punkt in punkte],
            "model": self.lmstudio_embedding_modell,
            "usage": daten.get("usage", {}),
        }

    def _embedding_runtime_befehl(self, *argumente: str) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Die LM-Studio-Embedding-Steuerung ist fuer Windows eingerichtet.")
        ergebnis = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self._embedding_startskript),
                *argumente,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=90,
            check=False,
        )
        if ergebnis.returncode != 0:
            raise RuntimeError(
                "Embedding-Runtime-Steuerung fehlgeschlagen; siehe Runtime-Protokoll."
            )

    def _embedding_runtime_starten(self) -> None:
        self._embedding_runtime_befehl()

    def _embedding_runtime_stoppen(self) -> None:
        self._embedding_runtime_befehl("-Stoppen")

    def chat(
        self,
        modell: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        primaermodell: bool = True,
        options: Mapping[str, Any] | None = None,
        think: bool = False,
    ):
        with self._modell_lock:
            return self._lmstudio_chat(messages, options=options, think=think)

    def _lmstudio_chat(
        self,
        messages: Sequence[Mapping[str, Any]],
        *,
        options: Mapping[str, Any] | None,
        think: bool,
    ) -> dict:
        """Übersetzt die interne Chat-Schnittstelle in LM Studios lokale API."""
        optionen = dict(options or {})
        angeforderter_kontext = int(optionen.pop("num_ctx", self.lmstudio_kontext))
        if angeforderter_kontext > self.lmstudio_kontext:
            raise ValueError(
                f"Angeforderter Kontext {angeforderter_kontext} überschreitet das "
                f"LM-Studio-Profil ({self.lmstudio_kontext})."
            )
        payload: dict[str, Any] = {
            "model": self.lmstudio_modell,
            "messages": list(messages),
            "temperature": float(optionen.pop("temperature", 0)),
            "max_tokens": int(optionen.pop("num_predict", 1024)),
            "stream": False,
        }
        for name in ("top_p", "seed", "repeat_penalty"):
            if name in optionen:
                payload[name] = optionen.pop(name)
        if think:
            raise ValueError("Das feste LM-Studio-Produktionsprofil erlaubt kein Reasoning.")
        if optionen:
            raise ValueError(
                "Nicht unterstützte LM-Studio-Optionen: " + ", ".join(sorted(optionen))
            )
        anfrage = Request(
            f"{self.lmstudio_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(anfrage, timeout=self.lmstudio_timeout) as antwort:
                daten = json.loads(antwort.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"LM Studio ist nicht einsatzbereit: {exc}") from exc
        choices = daten.get("choices", [])
        if not choices or not isinstance(choices[0].get("message"), dict):
            raise RuntimeError("LM Studio lieferte keine gültige Chatantwort.")
        timings = daten.get("timings", {})
        usage = daten.get("usage", {})
        return {
            "message": choices[0]["message"],
            "done": True,
            "model": self.lmstudio_modell,
            "timings": timings,
            "usage": usage,
            # Einheitliche Messfelder für Abnahmen, unabhängig vom Backend.
            "load_duration": 0,
            "prompt_eval_duration": int(float(timings.get("prompt_ms", 0)) * 1_000_000),
            "eval_duration": int(float(timings.get("predicted_ms", 0)) * 1_000_000),
            "eval_count": int(timings.get("predicted_n", usage.get("completion_tokens", 0))),
        }

    def chat_mit_fallback(
        self,
        primaermodell: str,
        fallback_modell: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        options: Mapping[str, Any] | None = None,
        think: bool = False,
    ):
        """Wechselt nur bei Lade-, Speicher- oder Runnerfehlern das Modell."""
        with self._modell_lock:
            if primaermodell in self._gesperrte_modelle and primaermodell != fallback_modell:
                self._messwerte["chat_modell_fallbacks"] += 1
                return self._chat_fallback(
                    fallback_modell, messages, options=options, think=think
                )
        try:
            return self.chat(primaermodell, messages, options=options, think=think)
        except Exception as fehler:
            if primaermodell == fallback_modell or not self._ist_laufzeit_fallbackfehler(fehler):
                raise
            with self._modell_lock:
                self._zaehle_runnerfehler(fehler)
                self._sperre_modell(primaermodell, fehler)
                self._messwerte["chat_modell_fallbacks"] += 1
                return self._chat_fallback(
                    fallback_modell, messages, options=options, think=think
                )

    def _chat_fallback(
        self,
        fallback_modell: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        options: Mapping[str, Any] | None,
        think: bool,
    ):
        """Startet bei Ausfall des Hauptmodells das kleinere GGUF."""
        self._chat_runtime_befehl("-Stoppen")
        self._chat_runtime_befehl("-Quantisierung", self.gguf_fallback_quantisierung)
        return self._lmstudio_chat(messages, options=options, think=think)

    def vision_chat(
        self,
        modell: str,
        messages: Sequence[Mapping[str, Any]],
        *,
        options: Mapping[str, Any] | None = None,
        fallback_modell: str | None = None,
    ):
        """Fuehrt einen exklusiven Vision-Peak mit geordneter Freigabe aus."""
        with self._modell_lock:
            # Der Starter lädt die Runtime bereits vor der ersten Suche.
            # Deshalb muss auch ein sofortiger Dokument-Upload sie stoppen.
            self.embedding_entladen()
            self._vision_aktiv = True
            try:
                self._chat_runtime_befehl("-Stoppen")
                self._vision_runtime_befehl()
                return self._lmstudio_vision(messages, options)
            finally:
                self._vision_runtime_befehl("-Stoppen")
                self._chat_runtime_befehl()
                self._messwerte["vision_entladungen"] += 1
                self._vision_aktiv = False

    @staticmethod
    def _ist_speicherfehler(fehler: Exception) -> bool:
        text = str(fehler).lower()
        return any(marker in text for marker in (
            "out of memory", "cuda oom", "insufficient memory",
            "not enough memory", "speicher", "resource exhausted",
            "but only", "memory required",
        ))

    @classmethod
    def _ist_laufzeit_fallbackfehler(cls, fehler: Exception) -> bool:
        text = str(fehler).lower()
        return cls._ist_speicherfehler(fehler) or any(marker in text for marker in (
            "runner failed", "mlx not available", "failed to load model",
            "model not found", "connection refused", "lm studio",
        ))

    def _zaehle_runnerfehler(self, fehler: Exception) -> None:
        text = str(fehler).lower()
        if "runner failed" in text or "mlx not available" in text:
            self._messwerte["runner_fehler"] += 1

    def _sperre_modell(self, modell: str, fehler: Exception) -> None:
        fehlertext = str(fehler).lower()
        if (
            self._ist_speicherfehler(fehler)
            or "runner failed" in fehlertext
            or "lm studio" in fehlertext
        ):
            self._gesperrte_modelle[modell] = str(fehler)

    def modell_freigeben(self, modell: str) -> None:
        """Loescht den Circuit-Breaker nach einer bewussten Laufzeitaenderung."""
        with self._modell_lock:
            self._gesperrte_modelle.pop(modell, None)

    def _vision_runtime_befehl(self, *argumente: str) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Die LM-Studio-Vision-Steuerung ist fuer Windows eingerichtet.")
        ergebnis = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(self._vision_startskript), *argumente],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=120, check=False,
        )
        if ergebnis.returncode != 0:
            raise RuntimeError(
                "Vision-Runtime-Steuerung fehlgeschlagen; siehe Runtime-Protokoll."
            )

    def _chat_runtime_befehl(self, *argumente: str) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Die LM-Studio-Chat-Steuerung ist fuer Windows eingerichtet.")
        ergebnis = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
             str(self._chat_startskript), *argumente],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=120, check=False,
        )
        if ergebnis.returncode != 0:
            raise RuntimeError(
                "Chat-Runtime-Steuerung fehlgeschlagen; siehe Runtime-Protokoll."
            )

    def _lmstudio_vision(self, messages, options) -> dict:
        uebersetzt = []
        for nachricht in messages:
            teile = [{"type": "text", "text": str(nachricht.get("content", ""))}]
            for bild in nachricht.get("images", []):
                bildpfad = Path(str(bild))
                if bildpfad.is_file():
                    mime = mimetypes.guess_type(bildpfad.name)[0] or "image/png"
                    kodiert = base64.b64encode(bildpfad.read_bytes()).decode("ascii")
                    url = f"data:{mime};base64,{kodiert}"
                else:
                    url = str(bild)
                teile.append({"type": "image_url", "image_url": {"url": url}})
            uebersetzt.append({"role": nachricht["role"], "content": teile})
        optionen = dict(options or {})
        payload = {
            "model": self.lmstudio_vision_modell,
            "messages": uebersetzt,
            "temperature": float(optionen.pop("temperature", 0)),
            "max_tokens": int(optionen.pop("num_predict", 1024)),
            "reasoning_budget": 0,
            "chat_template_kwargs": {"enable_thinking": False},
            "stream": False,
        }
        optionen.pop("num_ctx", None)
        if optionen:
            raise ValueError("Nicht unterstuetzte Vision-Optionen: " + ", ".join(sorted(optionen)))
        anfrage = Request(
            f"{self.lmstudio_vision_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urlopen(anfrage, timeout=self.lmstudio_timeout) as antwort:
                daten = json.loads(antwort.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"LM-Studio-Vision ist nicht einsatzbereit: {exc}") from exc
        choices = daten.get("choices", [])
        if not choices or not isinstance(choices[0].get("message"), dict):
            raise RuntimeError("LM Studio lieferte keine gueltige Visionantwort.")
        timings = daten.get("timings", {})
        usage = daten.get("usage", {})
        return {
            "message": choices[0]["message"],
            "done": True,
            "model": self.lmstudio_vision_modell,
            "usage": usage,
            "timings": timings,
            # Einheitliche Messfelder für die lokalen Abnahmen.
            "load_duration": 0,
            "prompt_eval_duration": int(float(timings.get("prompt_ms", 0)) * 1_000_000),
            "eval_duration": int(float(timings.get("predicted_ms", 0)) * 1_000_000),
            "eval_count": int(timings.get("predicted_n", usage.get("completion_tokens", 0))),
        }

    def embedding_entladen(self, modell: str | None = None) -> None:
        """Entlädt ausschließlich die konfigurierte Embedding-Runtime."""
        with self._modell_lock:
            self._embedding_runtime_stoppen()
            self._messwerte["embedding_entladungen"] += 1
            self._letztes_embedding_modell = None

    def chat_entladen(self, modell: str) -> None:
        """Das persistente GGUF-Chatmodell wird nur über das Startskript beendet."""
        return None

    def messwerte(self) -> dict[str, int | bool]:
        with self._modell_lock:
            return {
                **self._messwerte,
                "vision_aktiv": self._vision_aktiv,
                "gesperrte_modelle": len(self._gesperrte_modelle),
            }

    def konfiguration(self) -> dict[str, Any]:
        return {
            "chat_backend": self.chat_backend,
            "lmstudio_url": self.lmstudio_url,
            "lmstudio_modell": self.lmstudio_modell,
            "lmstudio_kontext": self.lmstudio_kontext,
            "chat_fallback_backend": self.chat_fallback_backend,
            "gguf_fallback_quantisierung": self.gguf_fallback_quantisierung,
            "embedding_backend": self.embedding_backend,
            "lmstudio_embedding_url": self.lmstudio_embedding_url,
            "lmstudio_embedding_modell": self.lmstudio_embedding_modell,
            "lmstudio_embedding_batch": self.lmstudio_embedding_batch,
            "vision_backend": self.vision_backend,
            "lmstudio_vision_url": self.lmstudio_vision_url,
            "chat_keep_alive": self.chat_keep_alive,
            "embedding_keep_alive": self.embedding_keep_alive,
            "fallback_keep_alive": self.fallback_keep_alive,
            "nutzerabhaengig": False,
        }


MODELL_RESSOURCEN = ModellRessourcenManager()
