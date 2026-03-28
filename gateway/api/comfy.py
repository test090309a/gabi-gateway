# gateway/api/comfy.py
"""ComfyUI API endpoints for image generation."""

import os
import json
import uuid
import random
import logging
import requests
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Header, HTTPException, Depends, Form
from fastapi.responses import FileResponse

from gateway.auth import verify_token
from gateway.config import config
from gateway.core.memory import chat_memory

logger = logging.getLogger(__name__)

router = APIRouter()


class ComfyUIWrapper:
    """Wrapper für ComfyUI mit Lazy-Import."""
    
    _generator = None
    _available = None
    
    @classmethod
    def get_generator(cls):
        if cls._generator is None and cls._available is not False:
            try:
                from gateway.comfyui_generator import ComfyUIGenerator
                cls._generator = ComfyUIGenerator()
                cls._available = cls._generator.is_available()
                if cls._available:
                    logger.info("✅ ComfyUI generator initialized")
                else:
                    logger.warning("⚠️ ComfyUI server not available")
            except ImportError as e:
                logger.warning(f"⚠️ ComfyUI not available: {e}")
                cls._available = False
        return cls._generator
    
    @classmethod
    def is_available(cls):
        if cls._available is None:
            cls.get_generator()
        return cls._available is True


def get_comfyui():
    return ComfyUIWrapper.get_generator()


@router.get("/comfy/status")
async def comfy_status(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Prüft den ComfyUI Server Status."""
    comfy = get_comfyui()
    if not comfy:
        return {"running": False, "url": config.get_comfyui_url(), "message": "ComfyUI nicht verfügbar"}
    
    try:
        running = comfy.is_available()
        return {
            "running": running,
            "url": config.get_comfyui_url(),
            "message": "ComfyUI läuft" if running else "ComfyUI läuft nicht"
        }
    except Exception as e:
        return {"running": False, "url": config.get_comfyui_url(), "error": str(e)}


@router.post("/comfy/generate")
async def comfy_generate(
    prompt: str = Form(...),
    negative_prompt: str = Form(""),
    width: int = Form(512),
    height: int = Form(512),
    steps: int = Form(20),
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """Generiert ein Bild mit ComfyUI."""
    comfy = get_comfyui()
    if not comfy:
        return {"status": "error", "reply": "❌ ComfyUI nicht verfügbar"}
    
    if not comfy.is_available():
        return {"status": "error", "reply": "❌ ComfyUI Server läuft nicht"}
    
    try:
        image_data = comfy.generate_image(prompt, negative_prompt, width, height, steps)
        
        if image_data:
            # Bild speichern
            folder = "comfy"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"comfy_{timestamp}.png"
            relative_path = f"{folder}/{filename}"
            filepath = f"screenshots/{relative_path}"
            
            os.makedirs(f"screenshots/{folder}", exist_ok=True)
            with open(filepath, "wb") as f:
                f.write(image_data)
            
            # Metadaten speichern
            metadata = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": width,
                "height": height,
                "steps": steps,
                "created": datetime.now().isoformat(),
                "filename": filename
            }
            json_path = f"screenshots/{folder}/{filename.replace('.png', '.json')}"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            img_base64 = base64.b64encode(image_data).decode('utf-8')
            
            return {
                "status": "success",
                "reply": f"✅ **Bild generiert!**\n\n📝 **Prompt:** {prompt}\n📐 **Größe:** {width}x{height}",
                "image_path": filepath,
                "relative_path": relative_path,
                "filename": filename,
                "folder": folder,
                "image_base64": img_base64
            }
        else:
            return {"status": "error", "reply": "❌ Kein Bild erhalten. ComfyUI Workflow fehlgeschlagen?"}
    
    except Exception as e:
        logger.error(f"Comfy generate error: {e}")
        return {"status": "error", "reply": f"❌ Fehler: {str(e)}"}


@router.get("/comfy/gallery")
async def comfy_gallery(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Listet alle generierten ComfyUI Bilder auf."""
    try:
        comfy_dir = Path("screenshots/comfy")
        images = []
        
        if comfy_dir.exists():
            for img_file in sorted(comfy_dir.glob("*.png"), key=lambda x: x.stat().st_mtime, reverse=True):
                stat = img_file.stat()
                prompt_file = img_file.with_suffix('.json')
                prompt_text = ""
                if prompt_file.exists():
                    try:
                        with open(prompt_file, 'r', encoding='utf-8') as f:
                            meta = json.load(f)
                            prompt_text = meta.get('prompt', '')
                    except:
                        pass
                
                images.append({
                    "filename": img_file.name,
                    "path": f"comfy/{img_file.name}",
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "prompt": prompt_text[:100]
                })
        
        return {"status": "success", "images": images, "count": len(images)}
    except Exception as e:
        return {"status": "error", "message": str(e), "images": []}


@router.delete("/comfy/delete/{filename}")
async def comfy_delete_image(
    filename: str,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """Löscht ein generiertes Bild."""
    try:
        filepath = Path("screenshots/comfy") / filename
        if not filepath.exists():
            return {"status": "error", "message": "Datei nicht gefunden"}
        
        filepath.unlink()
        
        # JSON löschen
        json_file = filepath.with_suffix('.json')
        if json_file.exists():
            json_file.unlink()
        
        return {"status": "success", "message": f"Bild gelöscht: {filename}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/comfy/delete-all")
async def comfy_delete_all(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Löscht alle ComfyUI Bilder."""
    try:
        comfy_dir = Path("screenshots/comfy")
        deleted = 0
        
        if comfy_dir.exists():
            for img_file in comfy_dir.glob("*.png"):
                try:
                    img_file.unlink()
                    deleted += 1
                    json_file = img_file.with_suffix('.json')
                    if json_file.exists():
                        json_file.unlink()
                except:
                    pass
        
        return {"status": "success", "message": f"{deleted} Bilder gelöscht", "count": deleted}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.get("/comfy/help")
async def comfy_help(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Zeigt Hilfe für ComfyUI-Befehle an."""
    help_text = """🎨 **ComfyUI Bildgenerierung:**

**Status:**
`/comfy status` - ComfyUI Server Status prüfen

**Bilder generieren:**
`/comfy generate <prompt>` - Bild generieren
`/comfy generate <prompt> --width 1024 --height 768` - Mit Größe
`/comfy generate <prompt> --steps 30` - Mit Schritten

**Galerie:**
`/comfy gallery` - Generierte Bilder anzeigen
`/comfy delete <filename>` - Einzelnes Bild löschen
`/comfy delete-all` - Alle Bilder löschen

**Beispiele:**
- `/comfy generate a cute cat`
- `/comfy generate cyberpunk city --width 1024 --height 576`
- `/comfy generate beautiful landscape, mountains, sunset`"""
    
    return {"status": "success", "help": help_text}