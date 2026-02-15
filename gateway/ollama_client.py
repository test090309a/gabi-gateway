"""Ollama HTTP client wrapper."""
import logging
from typing import Any

import httpx

from gateway.config import config

logger = logging.getLogger(__name__)


class OllamaClient:
    """HTTP client for local Ollama instance."""

    def __init__(self):
        self.base_url = config.get("ollama.base_url", "http://localhost:11434")
        self.default_model = config.get("ollama.default_model", "llama3.2")
        self.client = httpx.Client(timeout=120.0)

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

        logger.info(f"Ollama chat request: model={model}, messages_count={len(messages)}")

        try:
            response = self.client.post(
                f"{self.base_url}/api/chat",
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.error(f"Ollama HTTP error: {e}")
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
        except httpx.HTTPError as e:
            logger.error(f"Ollama list models error: {e}")
            raise RuntimeError(f"Failed to list models: {e}")

    def close(self):
        """Close the HTTP client."""
        self.client.close()


ollama_client = OllamaClient()
