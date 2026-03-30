# gateway/api/web.py
"""Web Automation API endpoints."""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Header, HTTPException, Depends

from auth import verify_token
from config import config

logger = logging.getLogger(__name__)

router = APIRouter()


class WebAutomationWrapper:
    """Wrapper für Web Automation mit Lazy-Import."""
    
    _automation = None
    _available = None
    
    @classmethod
    def get_automation(cls, headless: bool = True):
        if cls._automation is None and cls._available is not False:
            try:
                from gateway.integrations.web_automation import get_web_automation
                cls._automation = get_web_automation(headless=headless)
                cls._available = True
                logger.info("✅ Web automation initialized")
            except ImportError as e:
                logger.warning(f"⚠️ Web automation not available: {e}")
                cls._available = False
        return cls._automation
    
    @classmethod
    def is_available(cls):
        if cls._available is None:
            cls.get_automation()
        return cls._available is True


def get_web_automation(headless: bool = True):
    return WebAutomationWrapper.get_automation(headless)


@router.post("/web/goto")
async def web_goto(
    payload: dict,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """Öffnet eine URL im Headless-Browser und analysiert."""
    url = payload.get("url", "")
    headless = payload.get("headless", True)
    
    if not url:
        return {"status": "error", "reply": "❌ Keine URL angegeben"}
    
    web = get_web_automation(headless=headless)
    if not web:
        return {"status": "error", "reply": "❌ Web Automation nicht verfügbar"}
    
    try:
        result = await web.goto(url)
        
        if not result.get("success"):
            return {"status": "error", "reply": f"❌ Fehler: {result.get('error')}"}
        
        return {
            "status": "success",
            "reply": f"✅ **Webseite analysiert:** {result.get('title', url)}",
            "data": result
        }
    except Exception as e:
        logger.error(f"Web goto error: {e}")
        return {"status": "error", "reply": f"❌ Fehler: {str(e)}"}


@router.post("/web/click")
async def web_click(
    payload: dict,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """Klickt auf ein Element auf der aktuellen Seite."""
    selector = payload.get("selector", "")
    if not selector:
        return {"status": "error", "reply": "❌ Kein Selektor angegeben"}
    
    web = get_web_automation()
    if not web:
        return {"status": "error", "reply": "❌ Web Automation nicht verfügbar"}
    
    try:
        result = await web.click(selector)
        
        if result.get("success"):
            return {"status": "success", "reply": f"✅ Geklickt auf: {selector}"}
        else:
            return {"status": "error", "reply": f"❌ Fehler: {result.get('error')}"}
    except Exception as e:
        return {"status": "error", "reply": f"❌ Fehler: {str(e)}"}


@router.post("/web/type")
async def web_type(
    payload: dict,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """Gibt Text in ein Eingabefeld ein."""
    selector = payload.get("selector", "")
    text = payload.get("text", "")
    
    if not selector:
        return {"status": "error", "reply": "❌ Kein Selektor angegeben"}
    if not text:
        return {"status": "error", "reply": "❌ Kein Text angegeben"}
    
    web = get_web_automation()
    if not web:
        return {"status": "error", "reply": "❌ Web Automation nicht verfügbar"}
    
    try:
        result = await web.type_text(selector, text)
        
        if result.get("success"):
            return {"status": "success", "reply": f"✅ Text eingegeben in: {selector}"}
        else:
            return {"status": "error", "reply": f"❌ Fehler: {result.get('error')}"}
    except Exception as e:
        return {"status": "error", "reply": f"❌ Fehler: {str(e)}"}


@router.post("/web/screenshot")
async def web_screenshot(
    payload: dict,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """Macht einen Screenshot der aktuellen Seite."""
    web = get_web_automation()
    if not web:
        return {"status": "error", "reply": "❌ Web Automation nicht verfügbar"}
    
    try:
        result = await web.screenshot()
        
        if result.get("success"):
            return {
                "status": "success",
                "reply": f"✅ Screenshot gespeichert: {result.get('path')}",
                "path": result.get("path")
            }
        else:
            return {"status": "error", "reply": f"❌ Fehler: {result.get('error')}"}
    except Exception as e:
        return {"status": "error", "reply": f"❌ Fehler: {str(e)}"}


@router.get("/web/help")
async def web_help(_api_key: str = Depends(verify_token)) -> Dict[str, Any]:
    """Zeigt Hilfe für Web-Automation-Befehle an."""
    help_text = """🌐 **Web Automation Befehle:**

**Navigation:**
`/web/goto <url>` - Seite im Headless-Browser öffnen

**Interaktion:**
`/web/click <selector>` - Auf Element klicken
`/web/type <selector> <text>` - Text in Feld eingeben

**Screenshots:**
`/web/screenshot` - Screenshot der aktuellen Seite machen

**Beispiele:**
- `/web/goto https://example.com`
- `/web/click #submit-button`
- `/web/type #search "Python Tutorial"`"""
    
    return {"status": "success", "help": help_text}