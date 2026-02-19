# integrations/gui_controller.py
"""
Windows GUI Controller für GABI
Ermöglicht die Steuerung der Windows 11 GUI mittels pyautogui.

Funktionen:
- screen_capture(): Screenshot erstellen
- win_search_and_open(app_name): App via Windows-Suche öffnen
- get_window_titles(): Offene Fenster auflisten
- safe_click(x, y): Sichere Mausklicks

SICHERHEIT: GUI-Aktionen werden nur ausgeführt wenn:
- Security-Score >= 90 (siehe security_gate.py)
- Gefährliche Tastenkombinationen sind blockiert (Alt+F4, Win+L)
"""
import logging
import os
import sys
import time
import base64
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
from PIL import ImageGrab

logger = logging.getLogger("GATEWAY.gui")

# === PYAUTOGUI SETUP ===
try:
    import pyautogui
    # Fail-Safe aktivieren: Maus in Ecke bewegen bricht ab
    pyautogui.FAILSAFE = True
    # Pausen zwischen Aktionen für Stabilität
    pyautogui.PAUSE = 0.5
    PYAUTOGUI_AVAILABLE = True
    logger.info("PyAutoGUI erfolgreich geladen (FAILSAFE=True)")
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    logger.warning("PyAutoGUI nicht verfügbar - GUI-Steuerung deaktiviert")
    pyautogui = None

# === OPENCV FÜR BILDERKENNUNG ===
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
    logger.info("OpenCV erfolgreich geladen")
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None
    np = None
    logger.warning("OpenCV nicht verfügbar - Bilderkennung deaktiviert")

# === PILLOW FÜR SCREENSHOTS ===
try:
    from PIL import Image, ImageGrab
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None
    ImageGrab = None
    logger.warning("Pillow nicht verfügbar")


# === KONFIGURATION ===
SCREENSHOT_DIR = Path(__file__).parent.parent / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

# Blockierte Tastenkombinationen (Sicherheit)
BLOCKED_KEY_COMBOS = [
    "alt+f4",  # Fenster schließen
    "win+l",   # Windows sperren
    "ctrl+alt+delete",  # Security-Screen
    "win+ctrl+delete",  # Task-Manager
    "win+x",   # Quick Link Menu
    "alt+tab",  # Window Switcher (erlaubt mit Vorsicht)
    "win+d",   # Desktop anzeigen
    "win+m",   # Alle minimieren
    "win+tab", # Task View
]

# Erlaubte Aktionen ( whitelist )
ALLOWED_ACTIONS = [
    "click",
    "doubleclick",
    "rightclick",
    "move",
    "type",
    "press",
    "screenshot",
    "open_app",
    "find_icon",
]


class GUIController:
    """
    Hauptklasse für Windows GUI-Steuerung.
    """

    def __init__(self):
        self.pyautogui = pyautogui
        self.cv2 = cv2
        self.np = np
        self.screenshot_dir = SCREENSHOT_DIR
        self._security_override = False  # Nur für Notfälle

    def check_available(self) -> Dict[str, bool]:
        """Gibt zurück welche Module verfügbar sind."""
        return {
            "pyautogui": PYAUTOGUI_AVAILABLE,
            "opencv": CV2_AVAILABLE,
            "pillow": PIL_AVAILABLE,
            "ready": PYAUTOGUI_AVAILABLE
        }

    def screen_capture(self, filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Erstellt einen Screenshot und gibt ihn als Base64 zurück.

        Args:
            filename: Optionaler Dateiname (default: screenshot_TIMESTAMP.png)

        Returns:
            Dict mit 'success', 'path', 'base64', 'size'
        """
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "PyAutoGUI nicht verfügbar"}

        try:
            # Screenshot aufnehmen
            # screenshot = pyautogui.screenshot()
            screenshot = ImageGrab.grab(all_screens=True)

            # Dateiname generieren
            if not filename:
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"screenshot_{timestamp}.png"

            filepath = self.screenshot_dir / filename

            # Speichern
            screenshot.save(str(filepath))

            # Als Base64 für API-Response
            with open(filepath, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")

            logger.info(f"Screenshot gespeichert: {filepath}")

            return {
                "success": True,
                "path": str(filepath),
                "filename": filename,
                "base64": b64,
                "size": {"width": screenshot.width, "height": screenshot.height}
            }

        except Exception as e:
            logger.error(f"Screenshot-Fehler: {e}")
            return {"success": False, "error": str(e)}

    def win_search_and_open(self, app_name: str) -> Dict[str, Any]:
        """
        Öffnet eine App über die Windows-Suche.

        Args:
            app_name: Name der Anwendung (z.B. "Notepad", "Calculator")

        Returns:
            Dict mit 'success' und 'message'
        """
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "PyAutoGUI nicht verfügbar"}

        try:
            # Schritt 1: Windows-Taste drücken (Startmenü öffnen)
            pyautogui.press("win")
            time.sleep(0.5)

            # Schritt 2: App-Namen eintippen
            pyautogui.write(app_name, interval=0.1)
            time.sleep(0.5)

            # Schritt 3: Enter drücken
            pyautogui.press("enter")
            time.sleep(1)

            logger.info(f"App gestartet: {app_name}")

            return {
                "success": True,
                "message": f"'{app_name}' wurde gestartet",
                "action": "win_search_open",
                "app": app_name
            }

        except Exception as e:
            logger.error(f"Fehler beim Öffnen von {app_name}: {e}")
            return {"success": False, "error": str(e)}

    def get_window_titles(self) -> Dict[str, Any]:
        """
        Listet alle aktuell offenen Fenster auf.
        Nutzt PowerShell für Window-Enumeration.
        """
        try:
            import subprocess

            # PowerShell-Script für Fenster-Titel
            ps_script = '''
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public class WindowEnumerator {
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
    [DllImport("user32.dll")] public static extern int GetWindowTextLength(IntPtr hWnd);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
}
"@
$windows = @()
$callback = [WindowEnumerator+EnumWindowsProc]{
    param($hwnd, $lparam)
    if ([WindowEnumerator]::IsWindowVisible($hwnd)) {
        $len = [WindowEnumerator]::GetWindowTextLength($hwnd)
        if ($len -gt 0) {
            $sb = New-Object System.Text.StringBuilder($len + 1)
            [WindowEnumerator]::GetWindowText($hwnd, $sb, $sb.Capacity) | Out-Null
            $title = $sb.ToString()
            if ($title) { $script:windows += $title }
        }
    }
    return $true
}
[WindowEnumerator]::EnumWindows($callback, [IntPtr]::Zero) | Out-Null
$windows | Where-Object { $_ -ne "" } | Select-Object -Unique
'''

            result = subprocess.run(
                ["powershell", "-Command", ps_script],
                capture_output=True,
                text=True,
                timeout=10
            )

            windows = [w.strip() for w in result.stdout.splitlines() if w.strip()]

            return {
                "success": True,
                "windows": windows,
                "count": len(windows)
            }

        except Exception as e:
            logger.error(f"Fehler beim Auflisten der Fenster: {e}")
            return {"success": False, "error": str(e), "windows": []}

    def safe_click(self, x: int, y: int, button: str = "left", double: bool = False) -> Dict[str, Any]:
        """
        Führt einen sicheren Mausklick aus.

        Args:
            x: X-Koordinate
            y: Y-Koordinate
            button: "left", "right", "middle"
            double: True für Doppelklick

        Returns:
            Dict mit 'success' und 'position'
        """
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "PyAutoGUI nicht verfügbar"}

        try:
            # Bildschirmgröße für Validierung
            screen_width, screen_height = pyautogui.size()

            # Koordinaten validieren
            if x < 0 or y < 0 or x > screen_width or y > screen_height:
                return {
                    "success": False,
                    "error": f"Koordinaten außerhalb des Bildschirms (max: {screen_width}x{screen_height})"
                }

            # Klick ausführen
            if double:
                pyautogui.doubleClick(x, y, button=button)
                action = "doubleclick"
            else:
                pyautogui.click(x, y, button=button)
                action = "click"

            logger.info(f"Safe click bei ({x}, {y})")

            return {
                "success": True,
                "action": action,
                "position": {"x": x, "y": y},
                "button": button
            }

        except Exception as e:
            logger.error(f"Click-Fehler: {e}")
            return {"success": False, "error": str(e)}

    def move_to_and_click(self, x: int, y: int) -> Dict[str, Any]:
        """Bewegt Maus und klickt (sanft)."""
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "PyAutoGUI nicht verfügbar"}

        try:
            pyautogui.moveTo(x, y, duration=0.5)
            time.sleep(0.2)
            pyautogui.click()
            return {"success": True, "position": {"x": x, "y": y}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def type_text(self, text: str, interval: float = 0.05) -> Dict[str, Any]:
        """Tippt Text ein."""
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "PyAutoGUI nicht verfügbar"}

        try:
            pyautogui.write(text, interval=interval)
            return {"success": True, "text": text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def press_key(self, key: str) -> Dict[str, Any]:
        """Drückt eine einzelne Taste."""
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "PyAutoGUI nicht verfügbar"}

        # Sicherheitscheck für blockierte Tasten
        key_combo = key.lower().replace(" ", "")
        if key_combo in BLOCKED_KEY_COMBOS:
            if not self._security_override:
                return {
                    "success": False,
                    "error": f"Tastenkombination '{key}' ist aus Sicherheitsgründen blockiert"
                }

        try:
            pyautogui.press(key)
            return {"success": True, "key": key}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def hotkey(self, *keys) -> Dict[str, Any]:
        """
        Führt eine Tastenkombination aus.
        Beispiel: hotkey("ctrl", "c") für Copy.
        """
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "PyAutoGUI nicht verfügbar"}

        # Prüfen ob Kombination blockiert ist
        combo = "+".join(keys).lower()
        if combo in BLOCKED_KEY_COMBOS:
            if not self._security_override:
                return {
                    "success": False,
                    "error": f"Tastenkombination '{combo}' ist blockiert"
                }

        try:
            pyautogui.hotkey(*keys)
            return {"success": True, "combo": combo}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def find_icon_on_screen(self, template_path: str, threshold: float = 0.8) -> Dict[str, Any]:
        """
        Findet ein Icon auf dem Bildschirm mittels Template-Matching.

        Args:
            template_path: Pfad zum Referenz-Bild (Icon)
            threshold: Ähnlichkeitsschwelle (0.0 - 1.0)

        Returns:
            Dict mit 'success', 'position' (x, y) oder 'error'
        """
        if not CV2_AVAILABLE or not PIL_AVAILABLE:
            return {"success": False, "error": "OpenCV oder Pillow nicht verfügbar"}

        try:
            # Screenshot aufnehmen
            screenshot = pyautogui.screenshot()
            screen_cv = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)
            screen_gray = cv2.cvtColor(screen_cv, cv2.COLOR_BGR2GRAY)

            # Template laden
            template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
            if template is None:
                return {"success": False, "error": f"Template nicht gefunden: {template_path}"}

            # Template-Matching
            result = cv2.matchTemplate(screen_gray, template, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            if max_val >= threshold:
                # Position des Centers berechnen
                h, w = template.shape
                center_x = max_loc[0] + w // 2
                center_y = max_loc[1] + h // 2

                logger.info(f"Icon gefunden bei ({center_x}, {center_y}) mit Confidence {max_val:.2f}")

                return {
                    "success": True,
                    "position": {"x": center_x, "y": center_y},
                    "confidence": float(max_val),
                    "template_size": {"width": w, "height": h}
                }
            else:
                return {
                    "success": False,
                    "error": f"Icon nicht gefunden (best confidence: {max_val:.2f})"
                }

        except Exception as e:
            logger.error(f"Icon-Suche Fehler: {e}")
            return {"success": False, "error": str(e)}

    def click_icon(self, template_path: str, threshold: float = 0.8) -> Dict[str, Any]:
        """Findet ein Icon und klickt darauf."""
        result = self.find_icon_on_screen(template_path, threshold)

        if result.get("success"):
            pos = result["position"]
            return self.safe_click(pos["x"], pos["y"], double=True)

        return result

    def get_screen_size(self) -> Dict[str, Any]:
        """Gibt die Bildschirmgröße zurück."""
        if not PYAUTOGUI_AVAILABLE:
            return {"success": False, "error": "PyAutoGUI nicht verfügbar"}

        width, height = pyautogui.size()
        return {
            "success": True,
            "size": {"width": width, "height": height}
        }

    def enable_security_override(self):
        """Erlaubt blockierte Tastenkombinationen (NOTFALL nur!)."""
        self._security_override = True
        logger.warning("Sicherheits-Override aktiviert - blockierte Kombinationen erlaubt!")

    def disable_security_override(self):
        """Deaktiviert den Security-Override."""
        self._security_override = False
        logger.info("Sicherheits-Override deaktiviert")


# === SINGLETON ===
_gui_controller: Optional[GUIController] = None


def get_gui_controller() -> GUIController:
    """Gibt die Singleton-Instanz zurück."""
    global _gui_controller
    if _gui_controller is None:
        _gui_controller = GUIController()
    return _gui_controller


# === CONVENIENCE FUNCTIONS ===
def screen_capture(filename: Optional[str] = None) -> Dict[str, Any]:
    """Shortcut für Screenshot."""
    return get_gui_controller().screen_capture(filename)


def win_search_and_open(app_name: str) -> Dict[str, Any]:
    """Shortcut für App-Öffnen."""
    return get_gui_controller().win_search_and_open(app_name)


def get_window_titles() -> Dict[str, Any]:
    """Shortcut für Fenster-Liste."""
    return get_gui_controller().get_window_titles()


def safe_click(x: int, y: int, button: str = "left", double: bool = False) -> Dict[str, Any]:
    """Shortcut für sicheren Klick."""
    return get_gui_controller().safe_click(x, y, button, double)


def find_icon(template_path: str, threshold: float = 0.8) -> Dict[str, Any]:
    """Shortcut für Icon-Suche."""
    return get_gui_controller().find_icon_on_screen(template_path, threshold)


if __name__ == "__main__":
    # Test
    controller = get_gui_controller()
    print("GUI Controller geladen")
    print(f"Verfügbarkeit: {controller.check_available()}")
    print(f"Bildschirmgröße: {controller.get_screen_size()}")
