# Auto-generierte Integration: lerne_blender_bedienen
"""
Lerne Blender zu bedienen - mit GPU-Vision und GUI-Steuerung
Bietet Funktionen zur Blender-Steuerung, Bilderkennung und 3D-Modellierung

Erstellt: 2026-02-18 14:00:54 (erweitert)
Libraries: bpy, mathutils, torch, opencv-python, pyautogui, numpy
"""
import logging
import subprocess
import sys
import time
import os
import base64
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List
from io import BytesIO

logger = logging.getLogger("GATEWAY.lerne_blender_bedienen")

# === KONFIGURATION ===
BLENDER_PATH = "C:\\Program Files\\Blender Foundation\\Blender 4.0\\blender.exe"  # Anpassen!
TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "blender"


# === GPU-VISION MIT TORCH ===
try:
    import torch
    import torch.nn.functional as F
    import cv2
    import numpy as np
    import pyautogui
    from PIL import Image
    VISION_AVAILABLE = True
    logger.info("👁️ GPU-Vision verfügbar")
except ImportError as e:
    VISION_AVAILABLE = False
    logger.warning(f"⚠️ GPU-Vision nicht verfügbar: {e}")


class BlenderVision:
    """GPU-beschleunigte Bilderkennung für Blender"""
    
    def __init__(self):
        if not VISION_AVAILABLE:
            self.device = "cpu (fallback)"
            self.available = False
            return
            
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.available = True
        logger.info(f"👁️ Blender Vision auf: {self.device}")
        
        # Template-Verzeichnis erstellen
        TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Standard-Icons (müssen erstellt werden)
        self.templates = {
            'render': TEMPLATE_DIR / 'render.png',
            'save': TEMPLATE_DIR / 'save.png',
            'object_mode': TEMPLATE_DIR / 'object_mode.png',
            'edit_mode': TEMPLATE_DIR / 'edit_mode.png',
            'add_cube': TEMPLATE_DIR / 'add_cube.png',
            'add_sphere': TEMPLATE_DIR / 'add_sphere.png',
            'material': TEMPLATE_DIR / 'material.png',
            'texture': TEMPLATE_DIR / 'texture.png',
        }
    
    def screenshot_to_gpu(self) -> Tuple[torch.Tensor, np.ndarray]:
        """Macht Screenshot und lädt auf GPU"""
        # Screenshot mit pyautogui (schnell)
        screenshot = pyautogui.screenshot()
        img_np = np.array(screenshot)
        
        # Zu torch tensor auf GPU
        img_gpu = torch.from_numpy(img_np).to(self.device)
        
        return img_gpu, img_np
    
    def find_icon(self, icon_name: str, threshold: float = 0.8, region: Tuple[int,int,int,int] = None) -> Optional[Tuple[int, int]]:
        """
        Findet ein Icon auf dem Bildschirm (GPU-beschleunigt)
        
        Args:
            icon_name: Name des Icons (z.B. 'render')
            threshold: Ähnlichkeitsschwelle (0.0-1.0)
            region: (x, y, width, height) Suchbereich
            
        Returns:
            (x, y) Position des Icon-Zentrums oder None
        """
        if not self.available:
            logger.warning("Vision nicht verfügbar")
            return None
        
        if icon_name not in self.templates:
            logger.warning(f"Unbekanntes Icon: {icon_name}")
            return None
        
        template_path = self.templates[icon_name]
        if not template_path.exists():
            logger.warning(f"Template nicht gefunden: {template_path}")
            return None
        
        # Screenshot machen
        if region:
            screen_np = np.array(pyautogui.screenshot(region=region))
            screen_gpu = torch.from_numpy(screen_np).to(self.device)
        else:
            screen_gpu, screen_np = self.screenshot_to_gpu()
        
        # Template laden
        template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
        if template is None:
            logger.warning(f"Template konnte nicht geladen werden: {template_path}")
            return None
            
        template_gpu = torch.from_numpy(template).to(self.device)
        
        # Template Matching mit Korrelation
        # Bild und Template für Conv2D vorbereiten
        screen_float = screen_gpu.permute(2,0,1).unsqueeze(0).float()
        template_float = template_gpu.permute(2,0,1).unsqueeze(0).float()
        
        # Korrelation berechnen
        correlation = F.conv2d(screen_float, template_float)
        
        # Maximum finden
        max_val = correlation.max().item()
        max_idx = correlation.argmax().item()
        
        if max_val > threshold:
            # Position berechnen
            h, w = template.shape[:2]
            _, _, corr_h, corr_w = correlation.shape
            y = max_idx // corr_w
            x = max_idx % corr_w
            
            # Zentrum des Icons
            center_x = x + w//2
            center_y = y + h//2
            
            # Wenn region angegeben, Offset hinzufügen
            if region:
                center_x += region[0]
                center_y += region[1]
            
            logger.info(f"✓ Icon '{icon_name}' gefunden bei ({center_x}, {center_y}) | Score: {max_val:.2f}")
            return (center_x, center_y)
        
        logger.info(f"✗ Icon '{icon_name}' nicht gefunden (bester Score: {max_val:.2f})")
        return None
    
    def save_template(self, icon_name: str, region: Tuple[int,int,int,int]):
        """Speichert einen Bildausschnitt als Template"""
        screenshot = pyautogui.screenshot(region=region)
        screenshot.save(self.templates[icon_name])
        logger.info(f"📸 Template gespeichert: {self.templates[icon_name]}")
    
    def wait_for_icon(self, icon_name: str, timeout: int = 10, threshold: float = 0.8) -> Optional[Tuple[int, int]]:
        """Wartet bis ein Icon erscheint"""
        start = time.time()
        while time.time() - start < timeout:
            pos = self.find_icon(icon_name, threshold)
            if pos:
                return pos
            time.sleep(0.5)
        return None


class LerneBlenderBedienenIntegration:
    """
    Blender-Integration mit GPU-Vision und GUI-Steuerung
    """

    def __init__(self):
        self.name = "lerne_blender_bedienen"
        self.blender_path = self._find_blender()
        self.vision = BlenderVision() if VISION_AVAILABLE else None
        self.blender_window = None
        self.process = None
        logger.info(f"Initialisiere {self.name} Integration")
        
        if self.blender_path:
            logger.info(f"✓ Blender gefunden: {self.blender_path}")
        else:
            logger.warning("✗ Blender nicht gefunden")

    def _find_blender(self) -> Optional[str]:
        """Sucht nach Blender-Installation"""
        import shutil
        
        # 1. Im System-PATH suchen
        blender_in_path = shutil.which("blender")
        if blender_in_path:
            return blender_in_path
        
        # 2. Typische Installationspfade
        common_paths = [
            "C:\\Program Files\\Blender Foundation\\Blender 4.0\\blender.exe",
            "C:\\Program Files\\Blender Foundation\\Blender 3.6\\blender.exe",
            "C:\\Program Files\\Blender Foundation\\Blender 3.5\\blender.exe",
            "C:\\Program Files\\Blender Foundation\\Blender\\blender.exe",
            "C:\\Program Files\\Blender Foundation\\Blender 4.2\\blender.exe",
        ]
        
        for path in common_paths:
            if Path(path).exists():
                return path
        
        return None

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Führt Blender-Operationen aus.

        Args:
            action: "info", "start", "stop", "screenshot", "click_icon", 
                   "add_cube", "render_viewport", "run_script", "version"
            icon: Icon-Name für click_icon
            script: Python-Code für run_script
            file: .blend Datei (optional)
            region: (x,y,w,h) für Screenshot (optional)

        Returns:
            Dict mit Ergebnis
        """
        action = kwargs.get("action", "info")
        logger.info(f"🎬 Blender Aktion: {action}")
        
        # Prüfe Blender-Pfad für Aktionen, die ihn brauchen
        actions_needing_blender = ["start", "stop", "run_script", "render", "version"]
        if action in actions_needing_blender and not self.blender_path:
            return {
                "success": False,
                "error": "Blender nicht gefunden",
                "hint": "Installiere Blender oder setze BLENDER_PATH manuell"
            }

        # Action-Dispatch
        if action == "info":
            return self.get_info()
        
        elif action == "start":
            return self.start_blender()
        
        elif action == "stop":
            return self.stop_blender()
        
        elif action == "screenshot":
            return self.take_screenshot(kwargs.get("region"))
        
        elif action == "click_icon":
            icon = kwargs.get("icon", "")
            if not icon:
                return {"success": False, "error": "Kein Icon angegeben"}
            return self.click_icon(icon, kwargs.get("threshold", 0.8))
        
        elif action == "add_cube":
            return self.add_cube()
        
        elif action == "render_viewport":
            return self.render_viewport()
        
        elif action == "version":
            return self.get_version()
        
        elif action == "run_script":
            script = kwargs.get("script", "")
            if not script:
                return {"success": False, "error": "Kein Skript angegeben"}
            return self.run_blender_script(script, kwargs.get("file"))
        
        elif action == "list_windows":
            return self.list_blender_windows()
        
        elif action == "focus":
            return self.focus_blender()
        
        elif action == "save_template":
            icon = kwargs.get("icon", "")
            region = kwargs.get("region")
            if not icon or not region:
                return {"success": False, "error": "Icon-Name und Region benötigt"}
            if not self.vision:
                return {"success": False, "error": "Vision nicht verfügbar"}
            self.vision.save_template(icon, tuple(region))
            return {"success": True, "message": f"Template '{icon}' gespeichert"}
        
        else:
            return {
                "success": True,
                "skill": self.name,
                "message": f"Integration ausgeführt (Aktion: {action})",
                "data": kwargs
            }

    # ===== BLENDER PROZESS-STEUERUNG =====

    def start_blender(self) -> Dict[str, Any]:
        """Startet Blender"""
        try:
            self.process = subprocess.Popen([self.blender_path])
            logger.info("🔄 Blender gestartet, warte auf GUI...")
            time.sleep(5)
            
            # Fenster suchen
            result = self.list_blender_windows()
            if result["windows"]:
                self.blender_window = result["windows"][0]
                return {
                    "success": True,
                    "message": "Blender gestartet",
                    "window": self.blender_window
                }
            
            return {
                "success": True,
                "message": "Blender gestartet (Fenster nicht gefunden)"
            }
        except Exception as e:
            logger.error(f"Fehler beim Blender-Start: {e}")
            return {"success": False, "error": str(e)}

    def stop_blender(self) -> Dict[str, Any]:
        """Beendet Blender"""
        if self.process:
            self.process.terminate()
            self.process = None
            self.blender_window = None
            return {"success": True, "message": "Blender beendet"}
        
        # Versuche über Taskkill
        try:
            subprocess.run(["taskkill", "/f", "/im", "blender.exe"], capture_output=True)
            return {"success": True, "message": "Blender-Prozesse beendet"}
        except:
            return {"success": False, "error": "Blender läuft nicht"}

    def list_blender_windows(self) -> Dict[str, Any]:
        """Listet alle Blender-Fenster auf"""
        windows = []
        for window in pyautogui.getWindowsWithTitle('Blender'):
            windows.append({
                "title": window.title,
                "left": window.left,
                "top": window.top,
                "width": window.width,
                "height": window.height,
                "is_active": window.isActive
            })
        
        return {
            "success": True,
            "windows": windows,
            "count": len(windows)
        }

    def focus_blender(self) -> Dict[str, Any]:
        """Bringt Blender in den Vordergrund"""
        if self.blender_window:
            try:
                self.blender_window.activate()
                time.sleep(0.5)
                return {"success": True, "message": "Blender fokussiert"}
            except:
                pass
        
        # Fallback: Alle Blender-Fenster durchprobieren
        for window in pyautogui.getWindowsWithTitle('Blender'):
            try:
                window.activate()
                self.blender_window = window
                return {"success": True, "message": "Blender fokussiert"}
            except:
                continue
        
        return {"success": False, "error": "Kein Blender-Fenster gefunden"}

    # ===== GUI-STEUERUNG MIT VISION =====

    def take_screenshot(self, region: Tuple[int,int,int,int] = None) -> Dict[str, Any]:
        """Macht einen Screenshot und gibt ihn als Base64 zurück"""
        try:
            if region:
                screenshot = pyautogui.screenshot(region=region)
            else:
                screenshot = pyautogui.screenshot()
            
            # Als Base64
            buffer = BytesIO()
            screenshot.save(buffer, format='PNG')
            b64 = base64.b64encode(buffer.getvalue()).decode()
            
            # Auch als Datei speichern
            filename = f"blender_shot_{int(time.time())}.png"
            screenshot.save(filename)
            
            return {
                "success": True,
                "message": "Screenshot gespeichert",
                "filename": filename,
                "size": screenshot.size,
                "base64_preview": b64[:100] + "..."  # Gekürzt
            }
        except Exception as e:
            logger.error(f"Screenshot-Fehler: {e}")
            return {"success": False, "error": str(e)}

    def click_icon(self, icon_name: str, threshold: float = 0.8) -> Dict[str, Any]:
        """Findet und klickt ein Icon"""
        if not self.vision:
            return {"success": False, "error": "Vision nicht verfügbar"}
        
        # Blender fokussieren
        self.focus_blender()
        
        # Icon suchen
        pos = self.vision.find_icon(icon_name, threshold)
        if not pos:
            return {
                "success": False,
                "error": f"Icon '{icon_name}' nicht gefunden",
                "hint": f"Template in {TEMPLATE_DIR} prüfen"
            }
        
        # Klicken
        x, y = pos
        pyautogui.click(x, y)
        time.sleep(0.5)
        
        return {
            "success": True,
            "message": f"Icon '{icon_name}' geklickt",
            "position": {"x": x, "y": y}
        }

    def add_cube(self) -> Dict[str, Any]:
        """Fügt einen Würfel über Tastatur hinzu"""
        self.focus_blender()
        
        # Shift + A -> Mesh -> Cube
        pyautogui.hotkey('shift', 'a')
        time.sleep(0.3)
        
        # 'Cube' auswählen
        for _ in range(3):  # Runter zu Mesh
            pyautogui.press('down')
        pyautogui.press('right')  # In Mesh rein
        pyautogui.press('down')   # Zu Cube
        pyautogui.press('enter')
        
        time.sleep(0.5)
        
        return {"success": True, "message": "Würfel hinzugefügt"}

    def render_viewport(self) -> Dict[str, Any]:
        """Macht einen Viewport-Render"""
        self.focus_blender()
        
        # F12 für Render
        pyautogui.press('f12')
        time.sleep(2)
        
        # Screenshot vom Render
        return self.take_screenshot()

    # ===== BLENDER-PYTHON FUNKTIONEN =====

    def get_version(self) -> Dict[str, Any]:
        """Gibt die Blender-Version zurück"""
        try:
            result = subprocess.run(
                [self.blender_path, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            version_line = result.stdout.split('\n')[0] if result.stdout else "Unbekannt"
            
            return {
                "success": True,
                "version": version_line,
                "full_output": result.stdout
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def run_blender_script(self, script: str, blend_file: Optional[str] = None) -> Dict[str, Any]:
        """Führt ein Python-Skript in Blender aus"""
        import tempfile
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
            f.write(script)
            script_path = f.name
        
        try:
            cmd = [self.blender_path, "--background", "--python", script_path]
            if blend_file:
                cmd.insert(1, blend_file)
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        finally:
            try:
                os.unlink(script_path)
            except:
                pass

    def get_info(self) -> Dict[str, Any]:
        """Gibt Informationen über die Integration"""
        return {
            "success": True,
            "skill": self.name,
            "blender_installed": self.blender_path is not None,
            "blender_path": self.blender_path,
            "vision_available": VISION_AVAILABLE and self.vision is not None,
            "vision_device": self.vision.device if self.vision else None,
            "templates": {k: str(v) for k, v in self.vision.templates.items()} if self.vision else {},
            "templates_exist": {k: v.exists() for k, v in self.vision.templates.items()} if self.vision else {},
            "message": "Blender-Integration bereit" if self.blender_path else "Blender nicht gefunden"
        }

    def health_check(self) -> bool:
        """Prüft ob die Integration funktionsbereit ist"""
        return self.blender_path is not None


# ===== SINGLETON =====
_integration_instance: Optional[LerneBlenderBedienenIntegration] = None


def get_integration() -> LerneBlenderBedienenIntegration:
    """Gibt die Singleton-Instanz zurück."""
    global _integration_instance
    if _integration_instance is None:
        _integration_instance = LerneBlenderBedienenIntegration()
    return _integration_instance


def execute(**kwargs) -> Dict[str, Any]:
    """Führt die Integration direkt aus."""
    return get_integration().execute(**kwargs)


# ===== HILFSFUNKTIONEN FÜR TEMPLATES =====
def create_template_from_region(icon_name: str, x: int, y: int, w: int, h: int):
    """Erstellt ein Template aus einem Bildschirmausschnitt"""
    integration = get_integration()
    if not integration.vision:
        print("❌ Vision nicht verfügbar")
        return
    
    integration.vision.save_template(icon_name, (x, y, w, h))
    print(f"✅ Template '{icon_name}' erstellt")


if __name__ == "__main__":
    # Test
    integration = get_integration()
    print("="*60)
    print("🧪 BLENDER INTEGRATION TEST")
    print("="*60)
    
    info = integration.get_info()
    print(f"\n📊 Status:")
    print(f"  Blender: {'✅' if info['blender_installed'] else '❌'} {info['blender_path'] or 'nicht gefunden'}")
    print(f"  Vision:  {'✅' if info['vision_available'] else '❌'} {info.get('vision_device', '')}")
    
    if info['blender_installed']:
        print(f"\n📦 Version:")
        version = integration.get_version()
        if version['success']:
            print(f"  {version['version']}")
    
    print(f"\n🖼️ Templates:")
    for name, exists in info.get('templates_exist', {}).items():
        print(f"  {name}: {'✅' if exists else '❌'}")
    
    print("\n" + "="*60)