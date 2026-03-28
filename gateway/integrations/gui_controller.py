# integrations/gui_controller.py
"""GUI Controller for mouse/keyboard automation."""

import logging
import platform
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    import pyautogui
    PYAutoGUI_AVAILABLE = True
except ImportError:
    PYAutoGUI_AVAILABLE = False
    logger.warning("PyAutoGUI not installed. GUI features disabled.")


class GUIController:
    """Controller for GUI automation (mouse, keyboard, screenshots)."""
    
    def __init__(self):
        self.available = PYAutoGUI_AVAILABLE
        self.os = platform.system()
        
        if self.available:
            # Safety settings
            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.1
            logger.info(f"✅ GUI Controller initialized on {self.os}")
    
    def check_available(self) -> Dict[str, Any]:
        """Check if GUI controller is available."""
        if not self.available:
            return {"ready": False, "error": "PyAutoGUI not installed"}
        
        try:
            screen = pyautogui.size()
            return {
                "ready": True,
                "width": screen.width,
                "height": screen.height,
                "os": self.os,
                "monitor_count": 1
            }
        except Exception as e:
            return {"ready": False, "error": str(e)}
    
    def get_screen_size(self) -> Dict[str, Any]:
        """Get screen dimensions."""
        if not self.available:
            return {"success": False, "error": "PyAutoGUI not installed"}
        
        try:
            screen = pyautogui.size()
            return {
                "success": True,
                "width": screen.width,
                "height": screen.height
            }
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def screen_capture(self, path: str = None) -> Dict[str, Any]:
        """Capture screenshot."""
        if not self.available:
            return {"success": False, "error": "PyAutoGUI not installed"}
        
        try:
            screenshot = pyautogui.screenshot()
            
            if path:
                screenshot.save(path)
                return {"success": True, "path": path}
            else:
                import io
                import base64
                img_bytes = io.BytesIO()
                screenshot.save(img_bytes, format='PNG')
                img_base64 = base64.b64encode(img_bytes.getvalue()).decode('utf-8')
                return {"success": True, "base64": img_base64}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def safe_click(self, x: int, y: int, button: str = "left", double: bool = False) -> Dict[str, Any]:
        """Click at position with safety check."""
        if not self.available:
            return {"success": False, "error": "PyAutoGUI not installed"}
        
        try:
            screen = pyautogui.size()
            if x < 0 or x > screen.width or y < 0 or y > screen.height:
                return {"success": False, "error": f"Coordinates out of bounds: ({x}, {y})"}
            
            if double:
                pyautogui.doubleClick(x, y, button=button)
            else:
                pyautogui.click(x, y, button=button)
            
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def type_text(self, text: str) -> Dict[str, Any]:
        """Type text."""
        if not self.available:
            return {"success": False, "error": "PyAutoGUI not installed"}
        
        try:
            pyautogui.write(text)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def press_key(self, key: str) -> Dict[str, Any]:
        """Press a single key."""
        if not self.available:
            return {"success": False, "error": "PyAutoGUI not installed"}
        
        try:
            pyautogui.press(key)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def hotkey(self, *keys) -> Dict[str, Any]:
        """Press hotkey combination."""
        if not self.available:
            return {"success": False, "error": "PyAutoGUI not installed"}
        
        try:
            pyautogui.hotkey(*keys)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def open_program(self, program_path: str) -> Dict[str, Any]:
        """Open a program by path."""
        import subprocess
        import os
        
        try:
            if self.os == "Windows":
                subprocess.Popen(program_path, shell=True)
            else:
                subprocess.Popen(["open" if self.os == "Darwin" else "xdg-open", program_path])
            return {"success": True, "message": f"Started: {program_path}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def win_search_and_open(self, program: str) -> Dict[str, Any]:
        """Open program via Windows Search."""
        if self.os != "Windows":
            return {"success": False, "error": "Windows Search only on Windows"}
        
        try:
            pyautogui.hotkey('win', 's')
            import time
            time.sleep(0.5)
            pyautogui.write(program)
            time.sleep(0.5)
            pyautogui.press('enter')
            return {"success": True, "message": f"Searching for: {program}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_window_titles(self) -> Dict[str, Any]:
        """Get list of open window titles."""
        if self.os == "Windows":
            try:
                import win32gui
                windows = []
                
                def callback(hwnd, windows):
                    if win32gui.IsWindowVisible(hwnd):
                        title = win32gui.GetWindowText(hwnd)
                        if title:
                            rect = win32gui.GetWindowRect(hwnd)
                            windows.append({
                                "title": title,
                                "hwnd": hwnd,
                                "x": rect[0],
                                "y": rect[1],
                                "width": rect[2] - rect[0],
                                "height": rect[3] - rect[1]
                            })
                
                win32gui.EnumWindows(callback, windows)
                return {"success": True, "windows": windows}
            except ImportError:
                return {"success": False, "error": "win32gui not installed"}
        else:
            # Linux/macOS fallback
            import subprocess
            try:
                result = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True)
                windows = []
                for line in result.stdout.splitlines():
                    parts = line.split(maxsplit=3)
                    if len(parts) >= 4:
                        windows.append({"title": parts[3], "id": parts[0]})
                return {"success": True, "windows": windows}
            except Exception as e:
                return {"success": False, "error": str(e)}
    
    def find_icon_on_screen(self, template_path: str, threshold: float = 0.8) -> Dict[str, Any]:
        """Find icon on screen using image matching."""
        if not self.available:
            return {"success": False, "error": "PyAutoGUI not installed"}
        
        try:
            location = pyautogui.locateOnScreen(template_path, confidence=threshold)
            if location:
                return {
                    "success": True,
                    "found": True,
                    "x": location.left + location.width // 2,
                    "y": location.top + location.height // 2,
                    "bbox": (location.left, location.top, location.width, location.height)
                }
            return {"success": True, "found": False}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def click_icon(self, template_path: str, threshold: float = 0.8) -> Dict[str, Any]:
        """Find and click an icon."""
        result = self.find_icon_on_screen(template_path, threshold)
        
        if result.get("found"):
            return self.safe_click(result["x"], result["y"])
        elif result.get("success"):
            return {"success": False, "error": "Icon not found"}
        else:
            return result


_gui_controller = None

def get_gui_controller() -> GUIController:
    global _gui_controller
    if _gui_controller is None:
        _gui_controller = GUIController()
    return _gui_controller