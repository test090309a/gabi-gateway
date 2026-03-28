# gateway/api/brain_api.py
"""Brain (Corpus Callosum) API endpoints."""

import logging
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException

from gateway.auth import verify_token
from gateway.core.brain import get_brain, reset_brain

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/brain", tags=["Brain"])


@router.get("/status")
async def brain_status(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """🧠 Zeigt den Status von GABIs Gehirnhälften."""
    try:
        brain = get_brain()
        brain.initialize_hemispheres()
        
        status = brain.get_status()
        
        return {
            "status": "success",
            "brain": status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Brain-Status Fehler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/hemisphere")
async def switch_hemisphere(
    payload: dict,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """🔄 Wechselt die aktive Hemisphäre für Tests."""
    hemisphere = payload.get("hemisphere", "auto")
    
    if hemisphere not in ["left", "right", "auto", "bridge"]:
        raise HTTPException(status_code=400, detail="Ungültige Hemisphäre. Erlaubt: left, right, auto, bridge")
    
    brain = get_brain()
    result = brain.set_hemisphere_mode(hemisphere)
    
    return {
        "status": "success",
        "message": f"Hemisphäre auf '{hemisphere}' gesetzt",
        "active": hemisphere,
        "timestamp": datetime.now().isoformat()
    }


@router.post("/reset")
async def reset_brain_endpoint(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """🔄 Setzt das Gehirn zurück."""
    try:
        new_brain = reset_brain()
        return {
            "status": "success",
            "message": "Brain erfolgreich zurückgesetzt",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Brain-Reset Fehler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/left/status")
async def left_hemisphere_status(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Zeigt Status der linken Hemisphäre."""
    brain = get_brain()
    brain.initialize_hemispheres()
    
    return {
        "status": "success",
        "hemisphere": "left",
        "available": brain.left is not None,
        "capabilities": brain.left.capabilities if brain.left else [],
        "timestamp": datetime.now().isoformat()
    }


@router.get("/right/status")
async def right_hemisphere_status(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Zeigt Status der rechten Hemisphäre."""
    brain = get_brain()
    brain.initialize_hemispheres()
    
    return {
        "status": "success",
        "hemisphere": "right",
        "available": brain.right is not None,
        "capabilities": brain.right.capabilities if brain.right else [],
        "timestamp": datetime.now().isoformat()
    }