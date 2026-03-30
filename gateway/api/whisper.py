# gateway/api/whisper.py
"""Whisper API endpoints for speech recognition."""

import os
import tempfile
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import APIRouter, Header, HTTPException, Depends, UploadFile, File, Form

from auth import verify_token
from config import config

logger = logging.getLogger(__name__)

router = APIRouter()


class WhisperWrapper:
    """Wrapper für Whisper Client mit Lazy-Import."""
    
    _client = None
    _available = None
    
    @classmethod
    def get_client(cls):
        if cls._client is None and cls._available is not False:
            try:
                from gateway.integrations.whisper_client import get_whisper_client
                cls._client = get_whisper_client()
                cls._available = True
                logger.info("✅ Whisper client initialized")
            except ImportError as e:
                logger.warning(f"⚠️ Whisper client not available: {e}")
                cls._available = False
        return cls._client
    
    @classmethod
    def is_available(cls):
        if cls._available is None:
            cls.get_client()
        return cls._available is True


def get_whisper():
    return WhisperWrapper.get_client()


@router.get("/whisper/status")
async def whisper_status(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Prüft den Whisper-Server Status."""
    whisper = get_whisper()
    if not whisper:
        return {"available": False, "message": "Whisper client nicht verfügbar"}
    
    try:
        available = whisper.is_available()
        models = whisper.get_models() if available else []
        return {"available": available, "models": models}
    except Exception as e:
        logger.error(f"Whisper status error: {e}")
        return {"available": False, "error": str(e)}


def convert_to_wav(input_path: str, output_path: str) -> bool:
    """
    Konvertiert eine Audiodatei zu WAV (16kHz, mono, PCM16).
    
    Args:
        input_path: Pfad zur Eingabedatei
        output_path: Pfad zur Ausgabedatei
    
    Returns:
        True bei Erfolg, False bei Fehler
    """
    try:
        cmd = [
            'ffmpeg', '-y',
            '-i', input_path,
            '-ar', '16000',      # 16kHz Sampling Rate
            '-ac', '1',          # Mono
            '-c:a', 'pcm_s16le', # PCM 16-bit little endian
            output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        
        if result.returncode != 0:
            error_msg = result.stderr.decode('utf-8', errors='replace')
            logger.error(f"ffmpeg conversion failed: {error_msg[:200]}")
            return False
        
        if not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
            logger.error(f"Converted file too small: {output_path}")
            return False
        
        return True
        
    except subprocess.TimeoutExpired:
        logger.error("ffmpeg conversion timeout")
        return False
    except Exception as e:
        logger.error(f"ffmpeg conversion error: {e}")
        return False


@router.post("/whisper/transcribe")
async def whisper_transcribe(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """Transkribiert eine Audiodatei."""
    whisper = get_whisper()
    if not whisper:
        raise HTTPException(status_code=503, detail="Whisper client nicht verfügbar")
    
    if not whisper.is_available():
        raise HTTPException(status_code=503, detail="Whisper server nicht erreichbar")
    
    tmp_path = None
    wav_path = None
    
    try:
        # 1. Empfangene Datei speichern
        filename = file.filename or 'audio.webm'
        content = await file.read()
        logger.info(f"🎤 Transcribing: {filename} ({len(content)} bytes)")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        
        logger.info(f"💾 Saved temp file: {tmp_path}")
        
        # 2. Prüfe ob es bereits eine WAV-Datei ist
        is_wav = Path(filename).suffix.lower() in ['.wav', '.wave']
        
        if is_wav:
            # Direkt transkribieren
            audio_file = tmp_path
            logger.info(f"📁 Direct transcription (WAV): {tmp_path}")
        else:
            # Konvertiere zu WAV
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as wav:
                wav_path = wav.name
            
            logger.info(f"🔄 Converting {tmp_path} -> {wav_path}")
            
            if not convert_to_wav(tmp_path, wav_path):
                return {"status": "error", "error": "Audio conversion failed"}
            
            audio_file = wav_path
            logger.info(f"✅ Converted to WAV: {os.path.getsize(wav_path)} bytes")
        
        # 3. Transkribieren
        result = whisper.transcribe_file(audio_file, language)
        
        if result.get("status") == "success":
            return {
                "status": "success",
                "text": result.get("text", ""),
                "language": result.get("language", "unknown"),
                "duration": result.get("duration", 0)
            }
        else:
            return {"status": "error", "error": result.get("error", "Transcription failed")}
    
    except Exception as e:
        logger.error(f"Whisper transcribe error: {e}")
        return {"status": "error", "error": str(e)}
    
    finally:
        # Aufräumen
        for path in [tmp_path, wav_path]:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except:
                    pass


@router.post("/whisper/transcribe/sync")
async def whisper_transcribe_sync(
    file: UploadFile = File(...),
    language: Optional[str] = Form(None),
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """Transkribiert eine Audiodatei synchron (Alias)."""
    return await whisper_transcribe(file, language, _api_key)


@router.get("/whisper/help")
async def whisper_help(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Zeigt Hilfe für Whisper-Befehle an."""
    help_text = """🎤 **Whisper Spracherkennung:**

**Status:**
`/whisper status` - Whisper-Server Status prüfen

**Transkription:**
`/whisper transcribe` - Audiodatei transkribieren (mit Upload)

**Hinweise:**
- Unterstützte Formate: WAV, MP3, M4A, OGG, WEBM
- Automatische Spracherkennung oder manuelle Angabe
- Ergebnis wird als Text zurückgegeben

**Beispiele:**
- Audio im Web-Interface aufnehmen
- Audiodatei im Chat hochladen"""
    
    return {"status": "success", "help": help_text}