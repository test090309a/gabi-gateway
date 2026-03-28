# gateway/api/gui.py
"""GUI Controller API endpoints."""

import os
import sys
import asyncio
import logging
import platform
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel

from gateway.auth import verify_token
from gateway.config import config
from gateway.core.memory import chat_memory

logger = logging.getLogger(__name__)

router = APIRouter()


# ===== PYDANTIC MODELS =====

class GuiClickRequest(BaseModel):
    """Mausklick-Anfrage."""
    x: int
    y: int
    button: str = "left"
    double: bool = False


class GuiTypeRequest(BaseModel):
    """Texteingabe-Anfrage."""
    text: str


class GuiPressRequest(BaseModel):
    """Tastendruck-Anfrage."""
    key: str


class GuiHotkeyRequest(BaseModel):
    """Hotkey-Anfrage."""
    keys: List[str]


class GuiOpenRequest(BaseModel):
    """Programm öffnen-Anfrage."""
    program: str


class GuiGotoRequest(BaseModel):
    """URL öffnen-Anfrage."""
    url: str
    browser: Optional[str] = "chrome"


# ===== GUI CONTROLLER WRAPPER =====

class GuiControllerWrapper:
    """
    Wrapper für den GUI Controller mit Lazy-Import.
    Vermeidet Import-Fehler wenn PyAutoGUI nicht installiert ist.
    """
    
    _controller = None
    _available = None
    
    @classmethod
    def get_controller(cls):
        """Get or create GUI controller instance."""
        if cls._controller is None and cls._available is not False:
            try:
                from gateway.integrations.gui_controller import get_gui_controller
                cls._controller = get_gui_controller()
                cls._available = True
                logger.info("✅ GUI controller initialized")
            except ImportError as e:
                logger.warning(f"⚠️ GUI controller not available: {e}")
                cls._available = False
            except Exception as e:
                logger.error(f"❌ GUI controller error: {e}")
                cls._available = False
        return cls._controller
    
    @classmethod
    def is_available(cls):
        """Check if GUI controller is available."""
        if cls._available is None:
            cls.get_controller()
        return cls._available is True


def get_gui_controller():
    """Get GUI controller instance."""
    return GuiControllerWrapper.get_controller()


def is_gui_available() -> bool:
    """Check if GUI controller is available."""
    return GuiControllerWrapper.is_available()


# ===== HELPER FUNCTIONS =====

def _find_program(program_name: str) -> Optional[str]:
    """
    Findet ein Programm auf dem System (Windows, Linux, macOS, Android).
    
    Args:
        program_name: Name des Programms
        
    Returns:
        Pfad zum Programm oder None
    """
    system = platform.system().lower()
    program_name_lower = program_name.lower()
    
    # 1. Zuerst mit shutil.which (PATH-Suche)
    found = shutil.which(program_name)
    if found:
        return found
    
    # 2. Bekannte Alternativen/Alternativnamen
    alternatives = {
        "chrome": ["chrome", "google-chrome", "google-chrome-stable", "chromium"],
        "firefox": ["firefox", "firefox.exe"],
        "edge": ["edge", "microsoft-edge", "msedge"],
        "opera": ["opera", "opera.exe"],
        "browser": ["chrome", "firefox", "edge", "opera", "brave", "vivaldi"],
        "notepad": ["notepad", "notepad.exe", "gedit", "nano", "vim", "vi"],
        "editor": ["code", "notepad++", "sublime_text", "gedit", "vim", "nano"],
        "code": ["code", "codium", "vscode", "visual-studio-code"],
        "vscode": ["code", "codium", "vscode"],
        "cmd": ["cmd", "cmd.exe"],
        "terminal": ["gnome-terminal", "konsole", "xterm", "termux", "cmd.exe"],
        "powershell": ["powershell", "pwsh", "powershell.exe"],
        "explorer": ["explorer", "explorer.exe", "nautilus", "dolphin", "thunar"],
        "calculator": ["calc", "gnome-calculator", "kcalc"],
        "paint": ["mspaint", "paint", "pinta", "kolourpaint"],
        "word": ["winword", "word", "libreoffice-writer", "writer"],
        "excel": ["excel", "libreoffice-calc", "calc"],
    }
    
    if program_name_lower in alternatives:
        for alt in alternatives[program_name_lower]:
            found = shutil.which(alt)
            if found:
                logger.info(f"🔧 Programm '{program_name}' gefunden als '{alt}' → {found}")
                return found
    
    # 3. Windows: Suche in Program Files
    if system == "windows":
        program_files = [
            os.environ.get("ProgramFiles", "C:\\Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", "C:\\Users\\Default\\AppData\\Local"),
        ]
        
        exe_names = [f"{program_name}.exe", program_name]
        if program_name_lower in alternatives:
            exe_names.extend([f"{alt}.exe" for alt in alternatives[program_name_lower]])
        
        for pf in program_files:
            if not pf:
                continue
            pf_path = Path(pf)
            if not pf_path.exists():
                continue
            
            for exe_name in set(exe_names):
                for exe_path in pf_path.rglob(exe_name):
                    if exe_path.is_file():
                        logger.info(f"🔧 Programm '{program_name}' gefunden: {exe_path}")
                        return str(exe_path)
    
    # 4. Linux/macOS
    elif system in ["linux", "darwin"]:
        search_paths = ["/usr/bin", "/usr/local/bin", "/opt", "/snap/bin"]
        
        if system == "darwin":
            search_paths.append("/opt/homebrew/bin")
            search_paths.append("/usr/local/opt")
        
        for search_path in search_paths:
            search_dir = Path(search_path)
            if not search_dir.exists():
                continue
            
            for exe_path in search_dir.rglob(program_name):
                if exe_path.is_file() and os.access(exe_path, os.X_OK):
                    logger.info(f"🔧 Programm '{program_name}' gefunden: {exe_path}")
                    return str(exe_path)
            
            if program_name_lower in alternatives:
                for alt in alternatives[program_name_lower]:
                    for exe_path in search_dir.rglob(alt):
                        if exe_path.is_file() and os.access(exe_path, os.X_OK):
                            logger.info(f"🔧 Programm '{program_name}' gefunden als '{alt}': {exe_path}")
                            return str(exe_path)
    
    logger.warning(f"⚠️ Programm '{program_name}' nicht gefunden auf {system}")
    return None


def _log_gui_action(action: str, target: str, result: dict) -> None:
    """
    Dokumentiert GUI-Aktionen in MEMORY.md.
    
    Args:
        action: Die ausgeführte Aktion
        target: Das Ziel der Aktion
        result: Ergebnis der Aktion
    """
    try:
        memory_path = Path("MEMORY.md")
        if not memory_path.exists():
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if memory_path.stat().st_size > 10_000_000:  # 10MB Limit
            logger.warning("MEMORY.md zu groß, keine neuen Einträge")
            return
        
        content = memory_path.read_text(encoding="utf-8")
        
        entry = f"""
## GUI-Aktion [{timestamp}]
- **Aktion**: {action}
- **Ziel**: {target}
- **Erfolg**: {'Ja' if result.get('success') else 'Nein'}
- **Details**: {result.get('message', result.get('error', 'N/A'))}
"""
        memory_path.write_text(content + entry, encoding="utf-8")
        logger.info(f"GUI-Aktion dokumentiert: {action} -> {target}")
        
    except Exception as e:
        logger.error(f"Fehler beim Dokumentieren der GUI-Aktion: {e}")


# ===== API ENDPOINTS =====

@router.get("/gui/status")
async def gui_status(
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Gibt den Status des GUI Controllers zurück.
    """
    if not is_gui_available():
        return {
            "status": "error",
            "available": False,
            "message": "GUI Controller nicht verfügbar. PyAutoGUI nicht installiert?",
            "screen_width": 0,
            "screen_height": 0
        }
    
    try:
        gui = get_gui_controller()
        status = gui.check_available()
        
        return {
            "status": "success",
            "available": status.get("ready", False),
            "screen_width": status.get("width", 0),
            "screen_height": status.get("height", 0),
            "virtual_width": status.get("virtual_width"),
            "virtual_height": status.get("virtual_height"),
            "monitor_count": status.get("monitor_count", 1),
            "monitors": status.get("monitors", []),
            "os": status.get("os", platform.system()),
            "message": "GUI Controller bereit" if status.get("ready") else "GUI Controller nicht verfügbar"
        }
    except Exception as e:
        logger.error(f"GUI Status Fehler: {e}")
        return {
            "status": "error",
            "available": False,
            "error": str(e),
            "screen_width": 0,
            "screen_height": 0
        }


@router.get("/gui/screensize")
async def gui_screen_size(
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Gibt die Bildschirmgröße zurück.
    """
    if not is_gui_available():
        return {"success": False, "error": "GUI Controller nicht verfügbar"}
    
    try:
        gui = get_gui_controller()
        return gui.get_screen_size()
    except Exception as e:
        logger.error(f"GUI screensize error: {e}")
        return {"success": False, "error": str(e)}


@router.post("/gui/screenshot")
async def gui_screenshot(
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Macht einen Screenshot.
    """
    if not is_gui_available():
        return {"success": False, "error": "GUI Controller nicht verfügbar"}
    
    try:
        gui = get_gui_controller()
        
        # Ordner erstellen
        target_dir = "screenshots/gui"
        os.makedirs(target_dir, exist_ok=True)
        
        # Dateiname
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"gui_{timestamp}.png"
        full_path = os.path.join(os.getcwd(), target_dir, filename)
        
        # Screenshot machen
        result = gui.screen_capture(full_path)
        
        if result.get("success"):
            web_path = f"{target_dir}/{filename}"
            _log_gui_action("screenshot", web_path, result)
            
            return {
                "success": True,
                "path": web_path,
                "full_path": full_path,
                "filename": filename
            }
        else:
            return {"success": False, "error": result.get("error")}
            
    except Exception as e:
        logger.error(f"GUI Screenshot Fehler: {e}")
        return {"success": False, "error": str(e)}


@router.post("/gui/open")
async def gui_open_app(
    request: GuiOpenRequest,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Öffnet ein Programm.
    """
    if not is_gui_available():
        return {"success": False, "error": "GUI Controller nicht verfügbar"}
    
    try:
        gui = get_gui_controller()
        
        # Programm finden
        program_path = _find_program(request.program)
        
        if program_path:
            result = gui.open_program(program_path)
        else:
            # Fallback: Windows Search
            result = gui.win_search_and_open(request.program)
        
        if result.get("success"):
            _log_gui_action("open_app", request.program, result)
        
        return result
        
    except Exception as e:
        logger.error(f"GUI open error: {e}")
        return {"success": False, "error": str(e)}


@router.post("/gui/goto")
async def gui_goto_url(
    request: GuiGotoRequest,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Öffnet eine URL im Browser.
    """
    if not is_gui_available():
        return {"success": False, "error": "GUI Controller nicht verfügbar"}
    
    try:
        url = request.url.strip().strip('"\'')
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        browser = request.browser.lower()
        
        # 1. Browser öffnen
        open_result = await gui_open_app(GuiOpenRequest(program=browser))
        
        if not open_result.get("success"):
            return {
                "success": False,
                "error": f"Browser '{browser}' konnte nicht gestartet werden: {open_result.get('error', 'Unbekannter Fehler')}"
            }
        
        await asyncio.sleep(1.0)
        
        # 2. URL-Leiste fokussieren
        gui = get_gui_controller()
        gui.hotkey("ctrl", "l")
        await asyncio.sleep(0.3)
        
        # 3. URL eingeben
        gui.type_text(url)
        await asyncio.sleep(0.2)
        
        # 4. Enter drücken
        gui.press_key("enter")
        
        _log_gui_action("goto_url", url, {"success": True})
        
        return {
            "success": True,
            "message": f"Navigiere zu {url} mit {browser}",
            "url": url,
            "browser": browser
        }
        
    except Exception as e:
        logger.error(f"GUI goto error: {e}")
        return {"success": False, "error": str(e)}


@router.post("/gui/click")
async def gui_click(
    request: GuiClickRequest,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Führt einen Mausklick aus.
    """
    if not is_gui_available():
        return {"success": False, "error": "GUI Controller nicht verfügbar"}
    
    try:
        gui = get_gui_controller()
        result = gui.safe_click(
            x=request.x,
            y=request.y,
            button=request.button,
            double=request.double
        )
        
        if result.get("success"):
            _log_gui_action("click", f"Koord: {request.x},{request.y}", result)
        
        return result
        
    except Exception as e:
        logger.error(f"GUI click error: {e}")
        return {"success": False, "error": str(e)}


@router.post("/gui/type")
async def gui_type_text(
    request: GuiTypeRequest,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Tippt Text über die Tastatur ein.
    """
    if not is_gui_available():
        return {"success": False, "error": "GUI Controller nicht verfügbar"}
    
    try:
        gui = get_gui_controller()
        result = gui.type_text(request.text)
        
        if result.get("success"):
            _log_gui_action("type", request.text[:20] + "...", result)
        
        return result
        
    except Exception as e:
        logger.error(f"GUI type error: {e}")
        return {"success": False, "error": str(e)}


@router.post("/gui/press")
async def gui_press_key(
    request: GuiPressRequest,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Drückt eine Taste.
    """
    if not is_gui_available():
        return {"success": False, "error": "GUI Controller nicht verfügbar"}
    
    try:
        gui = get_gui_controller()
        result = gui.press_key(request.key)
        
        if result.get("success"):
            _log_gui_action("press_key", request.key, result)
        
        return result
        
    except Exception as e:
        logger.error(f"GUI press error: {e}")
        return {"success": False, "error": str(e)}


@router.post("/gui/hotkey")
async def gui_hotkey(
    request: GuiHotkeyRequest,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Drückt eine Tastenkombination.
    """
    if not is_gui_available():
        return {"success": False, "error": "GUI Controller nicht verfügbar"}
    
    try:
        gui = get_gui_controller()
        result = gui.hotkey(*request.keys)
        
        if result.get("success"):
            _log_gui_action("hotkey", '+'.join(request.keys), result)
        
        return result
        
    except Exception as e:
        logger.error(f"GUI hotkey error: {e}")
        return {"success": False, "error": str(e)}


@router.get("/gui/windows")
async def gui_windows(
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Listet alle offenen Fenster auf.
    """
    if not is_gui_available():
        return {"success": False, "error": "GUI Controller nicht verfügbar"}
    
    try:
        gui = get_gui_controller()
        result = gui.get_window_titles()
        
        if result.get("success"):
            windows = result.get("windows", [])
            reply = f"🖥️ **{len(windows)} Fenster gefunden:**\n\n"
            for w in windows[:20]:
                reply += f"• {w.get('title')}\n"
            result["reply"] = reply
        
        return result
        
    except Exception as e:
        logger.error(f"GUI windows error: {e}")
        return {"success": False, "error": str(e)}


@router.post("/gui/find-icon")
async def gui_find_icon(
    template_path: str,
    threshold: float = 0.8,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Sucht ein Icon auf dem Bildschirm.
    """
    if not is_gui_available():
        return {"success": False, "error": "GUI Controller nicht verfügbar"}
    
    try:
        gui = get_gui_controller()
        return gui.find_icon_on_screen(template_path, threshold)
        
    except Exception as e:
        logger.error(f"GUI find icon error: {e}")
        return {"success": False, "error": str(e)}


@router.post("/gui/click-icon")
async def gui_click_icon(
    template_path: str,
    threshold: float = 0.8,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Sucht ein Icon und klickt es an.
    """
    if not is_gui_available():
        return {"success": False, "error": "GUI Controller nicht verfügbar"}
    
    try:
        gui = get_gui_controller()
        result = gui.click_icon(template_path, threshold)
        
        if result.get("success"):
            _log_gui_action("click_icon", template_path, result)
        
        return result
        
    except Exception as e:
        logger.error(f"GUI click icon error: {e}")
        return {"success": False, "error": str(e)}


@router.get("/gui/help")
async def gui_help(
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Zeigt Hilfe für GUI-Befehle an.
    """
    help_text = """🖥️ **GUI Controller Befehle:**

**Programm öffnen:**
`/gui open <programm>` - Öffnet ein Programm
Beispiele: `/gui open chrome`, `/gui open notepad`, `/gui open calculator`

**URL öffnen:**
`/gui goto <url>` - Öffnet URL im Browser
Beispiel: `/gui goto google.com`

**Maussteuerung:**
`/gui click <x> <y>` - Klick an Position
`/gui click <x> <y> right` - Rechtsklick
`/gui click <x> <y> double` - Doppelklick

**Tastatursteuerung:**
`/gui type <text>` - Text eingeben
`/gui press <taste>` - Taste drücken (enter, tab, esc, etc.)
`/gui hotkey <taste1> <taste2>` - Tastenkombination (z.B. ctrl l)

**Screenshots:**
`/gui screenshot` - Screenshot machen

**Fenster:**
`/gui windows` - Liste aller Fenster

**Icon-Erkennung:**
`/gui find-icon <template_path>` - Icon suchen
`/gui click-icon <template_path>` - Icon suchen und klicken

**Status:**
`/gui status` - GUI Controller Status"""

    return {
        "status": "success",
        "help": help_text
    }


# ===== EXPORTS =====

__all__ = [
    "router",
    "get_gui_controller",
    "is_gui_available",
    "_find_program",
    "_log_gui_action",
]