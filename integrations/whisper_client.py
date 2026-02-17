# integrations/whisper_client.py

import logging
import requests
import json
from typing import Optional, List, Dict, Any
import os

logger = logging.getLogger(__name__)

class WhisperClient:
    """Client für den Whisper.cpp Server"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:9090"):
        self.base_url = base_url.rstrip('/')
        self.timeout = 60
        
    def is_available(self) -> bool:
        """Prüft ob der Whisper-Server erreichbar ist"""
        try:
            response = requests.get(f"{self.base_url}/", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def get_models(self) -> List[str]:
        """Listet verfügbare Modelle auf"""
        try:
            if self.is_available():
                return ["large-v3", "large-v2", "medium", "small", "base", "tiny"]
            return []
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Whisper-Modelle: {e}")
            return []
    
    def transcribe_file(self, file_path: str, language: Optional[str] = None) -> Dict[str, Any]:
        """
        Transkribiert eine Audiodatei mit dem Whisper.cpp Server
        
        WICHTIG: Der Whisper-Server erwartet:
        - file im QUERY-STRING (z.B. ?file=audio.wav)
        - Die Datei im Body als multipart/form-data
        """
        try:
            if not os.path.exists(file_path):
                return {
                    "status": "error",
                    "error": f"Datei nicht gefunden: {file_path}"
                }
            
            # Datei-Infos
            filename = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            logger.info(f"📤 Sende an Whisper: {filename} ({file_size} bytes)")
            
            # WICHTIG: Parameter für den Query-String
            params = {'file': filename}  # file MUSS im Query sein!
            if language:
                params['language'] = language
            
            # Datei für Multipart-Body
            with open(file_path, 'rb') as f:
                files = {'file': (filename, f, 'audio/wav')}
                
                # Sende Anfrage mit params (Query) und files (Body)
                response = requests.post(
                    f"{self.base_url}/inference",
                    params=params,  # Query-Parameter
                    files=files,    # Multipart Body
                    timeout=self.timeout
                )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"✅ Whisper erfolgreich")
                
                # Extrahiere den Text aus der Antwort
                text = result.get('text', '')
                if not text and 'segments' in result:
                    text = ' '.join([seg.get('text', '') for seg in result.get('segments', [])])
                
                return {
                    "status": "success",
                    "text": text,
                    "result": result,
                    "language": result.get('detected_language', language),
                    "duration": result.get('duration', 0)
                }
            else:
                error_msg = f"HTTP {response.status_code}: {response.text}"
                logger.error(f"❌ Whisper Fehler: {error_msg}")
                return {
                    "status": "error",
                    "error": error_msg
                }
                    
        except requests.exceptions.Timeout:
            return {
                "status": "error",
                "error": "Timeout beim Verbinden mit Whisper-Server"
            }
        except requests.exceptions.ConnectionError:
            return {
                "status": "error",
                "error": "Keine Verbindung zum Whisper-Server (http://127.0.0.1:9090)"
            }
        except Exception as e:
            logger.error(f"Transkriptionsfehler: {e}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def transcribe(self, audio_data: bytes, language: Optional[str] = None) -> Dict[str, Any]:
        """Transkribiert Audio-Daten (Bytes)"""
        import tempfile
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name
        
        try:
            result = self.transcribe_file(tmp_path, language)
            return result
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

# Singleton-Instanz
_whisper_client = None

def get_whisper_client():
    global _whisper_client
    if _whisper_client is None:
        _whisper_client = WhisperClient()
    return _whisper_client