# gateway/api/vision.py
"""Vision API endpoints (Webcam, Bildanalyse, YOLO)."""

import os
import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from fastapi import APIRouter, Header, HTTPException, Depends, Form, UploadFile, File
from fastapi.responses import FileResponse

from auth import verify_token
from config import config
from gateway.ollama_client import ollama_client
from gateway.core.memory import chat_memory
from gateway.utils.model_helpers import _extract_ollama_text, _pick_preferred_available, _pick_best_model, _as_model_pref_list

logger = logging.getLogger(__name__)

router = APIRouter()


class VisionWrapper:
    """Wrapper für GABI Vision mit Lazy-Import."""
    
    _vision = None
    _available = None
    
    @classmethod
    def get_vision(cls):
        if cls._vision is None and cls._available is not False:
            try:
                from gateway.integrations.gabi_vision import get_gabi_vision
                cls._vision = get_gabi_vision()
                cls._available = True
                logger.info("✅ GABI Vision initialized")
            except ImportError as e:
                logger.warning(f"⚠️ GABI Vision not available: {e}")
                cls._available = False
        return cls._vision
    
    @classmethod
    def is_available(cls):
        if cls._available is None:
            cls.get_vision()
        return cls._available is True


def get_vision():
    return VisionWrapper.get_vision()


@router.get("/vision/status")
async def vision_status(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Gibt den Status der Vision-Komponente zurück."""
    vision = get_vision()
    available = VisionWrapper.is_available()
    
    return {
        "status": "success",
        "available": available,
        "webcam_available": vision.is_webcam_available() if vision else False,
        "yolo_available": vision.is_yolo_available() if vision else False,
        "timestamp": datetime.now().isoformat()
    }


@router.post("/vision/webcam")
async def vision_webcam(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Macht ein Foto mit der Webcam."""
    vision = get_vision()
    if not vision:
        return {"status": "error", "message": "Vision nicht verfügbar"}
    
    result = vision.capture_webcam()
    
    if result.get("success"):
        return {
            "status": "success",
            "image_path": result.get("path"),
            "base64": result.get("base64"),
            "message": "📷 Webcam-Foto aufgenommen!"
        }
    else:
        return {"status": "error", "message": result.get("error", "Unbekannter Fehler")}


@router.post("/vision/analyze")
async def vision_analyze(
    file: UploadFile = File(...),
    prompt: str = Form("Beschreibe was du auf diesem Bild siehst."),
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """Analysiert ein hochgeladenes Bild mit einem Vision-Modell."""
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="Keine Bilddatei übergeben")
    
    content_type = (file.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Datei ist kein Bild")
    
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Leere Bilddatei")
    
    img_b64 = base64.b64encode(raw).decode("utf-8")
    
    # Vision-Modell auswählen
    models_info = ollama_client.list_models()
    available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
    
    preferred_vision = _as_model_pref_list(config.get("ollama.preferred_vision_models")) or ["qwen3-vl:8b"]
    vision_model = _pick_preferred_available(available, preferred_vision)
    
    if not vision_model:
        vision_hints = ["vl", "vision", "llava", "moondream", "minicpm-v", "qwen2.5vl"]
        vision_model = _pick_best_model(available, hints=vision_hints)
    
    if not vision_model:
        return {"status": "error", "message": "Kein Vision-Modell verfügbar."}
    
    try:
        response = await asyncio.to_thread(
            ollama_client.chat,
            model=vision_model,
            messages=[{"role": "user", "content": prompt, "images": [img_b64]}]
        )
        analysis = _extract_ollama_text(response) or "Keine Analyse erhalten"
        
        return {
            "status": "success",
            "analysis": analysis,
            "model_used": vision_model,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Vision analyze error: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/vision/detect")
async def vision_detect(
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """Erkennt Objekte mit YOLO auf dem aktuellen Webcam-Bild."""
    vision = get_vision()
    if not vision:
        return {"status": "error", "message": "Vision nicht verfügbar"}
    
    result = vision.capture_webcam()
    if not result.get("success"):
        return {"status": "error", "message": result.get("error")}
    
    detect_result = vision.detect_objects(result["path"])
    
    if detect_result.get("success"):
        objects = detect_result.get("objects", [])
        if objects:
            obj_list = ", ".join([f"{o['class']} ({o['confidence']:.0%})" for o in objects[:10]])
            return {"status": "success", "objects": objects, "summary": f"Erkannt: {obj_list}"}
        return {"status": "success", "objects": [], "summary": "Keine Objekte erkannt."}
    else:
        return {"status": "error", "message": detect_result.get("error")}


@router.post("/vision/stream/start")
async def vision_stream_start(
    interval: float = Form(2.0),
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """Startet den kontinuierlichen YOLO-Stream."""
    vision = get_vision()
    if not vision:
        return {"status": "error", "message": "Vision nicht verfügbar"}
    
    result = vision.start_yolo_stream(interval=interval)
    return result


@router.post("/vision/stream/stop")
async def vision_stream_stop(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Stoppt den YOLO-Stream."""
    vision = get_vision()
    if not vision:
        return {"status": "error", "message": "Vision nicht verfügbar"}
    
    return vision.stop_yolo_stream()


@router.get("/vision/stream/status")
async def vision_stream_status(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Gibt den Status des YOLO-Streams zurück."""
    vision = get_vision()
    if not vision:
        return {"active": False, "objects": [], "error": "Vision nicht verfügbar"}
    
    return {
        "active": getattr(vision, '_webcam_active', False),
        "objects": getattr(vision, '_last_yolo_objects', []),
        "timestamp": datetime.now().isoformat()
    }


@router.get("/vision/help")
async def vision_help(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Zeigt Hilfe für Vision-Befehle an."""
    help_text = """📷 **Vision Befehle:**

**Webcam:**
`/vision webcam` - Foto mit Webcam aufnehmen
`/vision analyze` - Bild analysieren (mit Upload)

**Objekterkennung:**
`/vision detect` - Objekte auf Webcam-Bild erkennen
`/vision stream/start` - Kontinuierliche Erkennung starten
`/vision stream/stop` - Erkennung stoppen

**Status:**
`/vision status` - Vision-Status anzeigen
`/vision stream/status` - Stream-Status anzeigen

**Beispiele:**
- `/vision webcam` - Foto machen
- `/vision detect` - Objekte erkennen
- `/vision stream/start` - Dauerhafte Erkennung starten"""
    
    return {"status": "success", "help": help_text}