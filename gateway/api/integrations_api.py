# gateway/api/integrations_api.py
"""Integrations API endpoints for hot-reload management."""

import logging
from datetime import datetime
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException

from auth import verify_token
from gateway.core.integration_watcher import (
    get_integration_status,
    reload_single_integration,
    force_rescan,
    get_loaded_integrations
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["Integrations"])


@router.get("/status")
async def integrations_status(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Status aller Integrationen."""
    try:
        status = get_integration_status()
        return {
            "status": "success",
            "data": status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Integrations status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/loaded")
async def loaded_integrations(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Listet alle geladenen Integrationen."""
    try:
        loaded = get_loaded_integrations()
        return {
            "status": "success",
            "integrations": loaded,
            "count": len(loaded),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Loaded integrations error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reload/{module_name}")
async def reload_integration(
    module_name: str,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """Lädt eine Integration neu."""
    try:
        result = reload_single_integration(module_name)
        return {
            "status": "success" if result.get("success") else "error",
            "data": result,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Reload integration error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rescan")
async def rescan_integrations(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Erzwingt einen Rescan des Integrations-Verzeichnisses."""
    try:
        result = force_rescan()
        return {
            "status": "success",
            "data": result,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Rescan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))