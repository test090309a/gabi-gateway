"""Ollama HTTP client wrapper."""
import logging
import time
from typing import Any

import httpx

from gateway.config import config

# logger = logging.getLogger(__name__) # "magisch", weil die Notation OLLAMA_CLIENT kommt zustande, weil Python in __name__ den Dateinamen speichert.
logger = logging.getLogger("OLLAMA")

def _estimate_tokens_from_messages(messages: list[dict]) -> int:
    """Lightweight token estimate for prompt visibility in logs."""
    text = " ".join([(m.get("content") or "") for m in messages or []])
    return max(1, int(len(text) / 4)) if text else 0


def _last_user_snippet(messages: list[dict], max_len: int = 90) -> str:
    for msg in reversed(messages or []):
        if (msg.get("role") or "").lower() == "user":
            content = " ".join((msg.get("content") or "").split())
            if len(content) > max_len:
                return content[: max_len - 1] + "…"
            return content
    return ""


class OllamaClient:
    """HTTP client for local Ollama instance."""

    def __init__(self):
        self.base_url = config.get("ollama.base_url", "http://localhost:11434")
        self.default_model = config.get("ollama.default_model", "llama3.2")
        try:
            timeout_seconds = float(config.get("ollama.timeout_seconds", 300))
        except Exception:
            timeout_seconds = 300.0
        self.timeout_seconds = max(30.0, timeout_seconds)
        self.client = httpx.Client(timeout=self.timeout_seconds)

    def chat(self, model: str | None = None, messages: list[dict] | None = None, **kwargs) -> dict:
        """Send chat completion request to Ollama."""
        model = model or self.default_model
        messages = messages or []

        payload = {
            "model": model,
            "messages": messages,
            **kwargs,
            "stream": False,  # <--- Das ist wichtig!
        }

        in_tok_est = _estimate_tokens_from_messages(messages)
        user_snip = _last_user_snippet(messages)
        logger.info(
            f"request | model={model} | msgs={len(messages)} | in_tok~{in_tok_est} | q='{user_snip}'"
        )

        try:
            started = time.perf_counter()
            response = self.client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            out_tok = data.get("eval_count", 0)
            prompt_tok = data.get("prompt_eval_count", in_tok_est)
            total_tok = (prompt_tok or 0) + (out_tok or 0)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                f"response | model={model} | out_tok={out_tok} | total_tok={total_tok} | t={elapsed_ms}ms"
            )
            return data
        except httpx.HTTPError as e:
            logger.error(f"Ollama HTTP error: {e}")
            if isinstance(e, httpx.ReadTimeout):
                raise RuntimeError(
                    f"Ollama request timed out after {int(self.timeout_seconds)}s. "
                    "Nutze ein kleineres Modell oder erhöhe ollama.timeout_seconds."
                )
            raise RuntimeError(f"Ollama request failed: {e}")

    def generate(self, model: str | None = None, prompt: str = "", **kwargs) -> dict:
        """Send generate request to Ollama."""
        model = model or self.default_model

        payload = {
            "model": model,
            "prompt": prompt,
            **kwargs,
        }

        logger.info(f"Ollama generate request: model={model}")

        try:
            response = self.client.post(
                f"{self.base_url}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Ollama HTTP error: {e}")
            raise RuntimeError(f"Ollama request failed: {e}")

    def list_models(self) -> dict:
        """List available models."""
        try:
            response = self.client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            return response.json()
        except httpx.ConnectError:
            # Hier fangen wir den Verbindungsfehler gezielt ab
            logger.error("Ollama Offline (Verbindung verweigert)")
            return {"models": []} # Rückgabe einer leeren Liste, damit das Programm nicht abstürzt
        except httpx.HTTPError as e:
            logger.error(f"Ollama Fehler: {e}")
            raise RuntimeError(f"Failed to list models: {e}")

    def close(self):
        """Close the HTTP client."""
        self.client.close()


ollama_client = OllamaClient()
