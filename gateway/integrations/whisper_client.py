# integrations/whisper_client.py
"""Whisper client for speech recognition with VAD and endpointing support."""

import logging
import requests
import time
from typing import Dict, Any, Optional, List

from config import config

logger = logging.getLogger(__name__)


class WhisperClient:
    """Client for Whisper ASR server with integrated voice settings."""
    
    def __init__(self):
        self.base_url = config.get("whisper.server_url", "http://127.0.0.1:9090")
        self.timeout = 30
        
        # Lade VAD & Endpointing Einstellungen aus der config.yaml
        self.voice_settings = config.get("voice_settings", {
            "vad_threshold": 0.5,
            "min_speech_duration": 0.2,
            "silence_timeout": 0.8,  # Standard: 800ms
            "max_record_time": 30.0
        })
        
        logger.info(f"Whisper client initialized: {self.base_url}")
        logger.info(f"Endpointing active: {self.voice_settings['silence_timeout']}s silence threshold")
    
    def get_settings(self) -> Dict[str, Any]:
        """Gibt die aktuellen Voice-Einstellungen zurück."""
        return self.voice_settings

    def is_available(self) -> bool:
        """Check if Whisper server is available."""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except Exception:
            return False
    
    def get_models(self) -> List[str]:
        """Get available models."""
        try:
            response = requests.get(f"{self.base_url}/models", timeout=5)
            if response.status_code == 200:
                return response.json().get("models", [])
        except Exception:
            pass
        return []
    
    def transcribe_file(self, file_path: str, language: Optional[str] = None) -> Dict[str, Any]:
        """Transcribe audio file."""
        try:
            # Falls Sprache nicht übergeben wurde, nimm Standard aus config
            if not language:
                language = config.get("whisper.language", "de")

            with open(file_path, 'rb') as f:
                files = {'file': f}
                params = {}
                if language:
                    params['language'] = language
                
                response = requests.post(
                    f"{self.base_url}/inference",
                    params=params,
                    files=files,
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    data = response.json()
                    text = data.get('text', '').strip()
                    
                    # Fallback für Segment-basierte Rückgaben
                    if not text and 'segments' in data:
                        text = ' '.join([s.get('text', '') for s in data.get('segments', [])]).strip()
                    
                    logger.debug(f"Transcription successful: {text[:50]}...")
                    
                    return {
                        'status': 'success',
                        'text': text,
                        'language': data.get('detected_language', language),
                        'duration': data.get('duration', 0),
                        'result': data
                    }
                else:
                    return {
                        'status': 'error',
                        'error': f"HTTP {response.status_code}: {response.text}"
                    }
        except Exception as e:
            logger.error(f"Whisper transcribe error: {e}")
            return {'status': 'error', 'error': str(e)}


_whisper_client = None

def get_whisper_client() -> WhisperClient:
    global _whisper_client
    if _whisper_client is None:
        _whisper_client = WhisperClient()
    return _whisper_client