"""Whisper client for audio transcription."""
import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)


class WhisperClient:
    """Client for local Whisper server."""

    def __init__(self, base_url: str = "http://127.0.0.1:9090"):
        self.base_url = base_url.rstrip("/")
        self._available = None

    def is_available(self) -> bool:
        """Check if Whisper server is available."""
        if self._available is not None:
            return self._available

        try:
            response = requests.get(f"{self.base_url}/health", timeout=2)
            self._available = response.status_code == 200
        except Exception as e:
            logger.warning(f"Whisper not available: {e}")
            self._available = False

        return self._available

    def transcribe(self, audio_data: bytes, language: Optional[str] = None) -> dict:
        """Transcribe audio data."""
        if not self.is_available():
            raise RuntimeError("Whisper server not available")

        files = {"file": ("audio.wav", audio_data, "audio/wav")}
        data = {}
        if language:
            data["language"] = language

        response = requests.post(
            f"{self.base_url}/v1/audio/transcriptions",
            files=files,
            data=data,
            timeout=60
        )

        if response.status_code != 200:
            raise RuntimeError(f"Whisper error: {response.status_code} - {response.text}")

        return response.json()

    def transcribe_file(self, file_path: str, language: Optional[str] = None) -> dict:
        """Transcribe an audio file."""
        if not self.is_available():
            raise RuntimeError("Whisper server not available")

        with open(file_path, "rb") as f:
            files = {"file": (file_path.split("/")[-1], f, "audio/wav")}
            data = {}
            if language:
                data["language"] = language

            response = requests.post(
                f"{self.base_url}/v1/audio/transcriptions",
                files=files,
                data=data,
                timeout=120
            )

        if response.status_code != 200:
            raise RuntimeError(f"Whisper error: {response.status_code} - {response.text}")

        return response.json()

    def get_models(self) -> list:
        """Get available Whisper models."""
        if not self.is_available():
            return []

        try:
            response = requests.get(f"{self.base_url}/v1/models", timeout=2)
            if response.status_code == 200:
                return response.json().get("models", [])
        except Exception:
            pass
        return []


whisper_client = None


def get_whisper_client() -> "WhisperClient":
    """Get or create Whisper client instance."""
    global whisper_client
    if whisper_client is None:
        whisper_client = WhisperClient()
    return whisper_client
