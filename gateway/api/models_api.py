# gateway/api/models_api.py
"""Models API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
import logging

from auth import verify_token
from gateway.ollama_client import ollama_client
from config import config
from gateway.utils.model_helpers import _infer_model_capabilities

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/models", tags=["Models"])


@router.get("")
async def list_available_models(_api_key: str = Depends(verify_token)):
    """Listet alle verfügbaren Modelle."""
    try:
        models_info = ollama_client.list_models()
        models = []
        
        for m in models_info.get("models", []):
            name = m.get("name")
            models.append({
                "name": name,
                "size": m.get("size", 0),
                "modified": m.get("modified", ""),
                "details": m.get("details", {}),
                "capabilities": _infer_model_capabilities(name or "", m.get("details", {}))
            })
        
        current_model = config.get("ollama.default_model", "llama2:latest")
        
        return {
            "status": "success",
            "current_model": current_model,
            "models": models,
            "count": len(models),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"List models error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/current")
async def get_current_model(_api_key: str = Depends(verify_token)):
    """Gibt das aktuell verwendete Modell zurück."""
    return {
        "status": "success",
        "current_model": ollama_client.default_model,
        "timestamp": datetime.now().isoformat()
    }


@router.post("/switch")
async def switch_model(
    payload: dict,
    _api_key: str = Depends(verify_token)
):
    """Wechselt das aktive Modell."""
    model_name = payload.get("model")
    if not model_name:
        raise HTTPException(status_code=400, detail="Model name required")
    
    try:
        models_info = ollama_client.list_models()
        available_models = [m.get("name") for m in models_info.get("models", [])]
        
        if model_name not in available_models:
            raise HTTPException(status_code=404, detail=f"Model '{model_name}' not found")
        
        config.set("ollama.default_model", model_name)
        ollama_client.default_model = model_name
        
        return {
            "status": "success",
            "message": f"Modell gewechselt zu: {model_name}",
            "current_model": model_name,
            "timestamp": datetime.now().isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Switch model error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/running")
async def get_running_models(_api_key: str = Depends(verify_token)):
    """Listet laufende Modelle."""
    try:
        running = ollama_client.get_running_models()
        return {
            "status": "success",
            "models": running,
            "count": len(running),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Get running models error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop/{model}")
async def stop_model(
    model: str,
    _api_key: str = Depends(verify_token)
):
    """Stoppt ein laufendes Modell."""
    try:
        result = ollama_client.stop_model(model)
        return {
            "status": "success" if result.get("status") == "success" else "error",
            "data": result,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Stop model error: {e}")
        raise HTTPException(status_code=500, detail=str(e))