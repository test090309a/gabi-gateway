"""
GABI Vision & Webcam Integration
Ermöglicht GABI zu sehen und visuell zu reagieren.

Funktionen:
- Webcam: Live-Bildaufnahme, Bewegungserkennung, Gesichts-/Objekterkennung
- Screenshot + Vision: Screenshots analysieren mit KI
- Click-Position: Automatische Erkennung via Vision
- Audio-Zuhören: Kontinuierliches Mikrofon-Monitoring

Voraussetzungen:
- opencv-python (für Webcam/Bilderkennung)
- numpy
- pyautogui (für Screenshots)
-Für Objekterkennung: ultralytics (YOLO)
- Für Audio: sounddevice, scipy
"""
import logging
import os
import time
import base64
import threading
import queue
from typing import Optional, List, Dict, Any, Tuple, Callable
from pathlib import Path
from datetime import datetime
import json

logger = logging.getLogger("GATEWAY.vision")

# === OPENCV IMPORT ===
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
    logger.info("OpenCV für Vision geladen")
except ImportError:
    CV2_AVAILABLE = False
    cv2 = None
    np = None
    logger.warning("OpenCV nicht verfügbar - Vision deaktiviert")

# === YOLO FÜR OBJEKTERKENNUNG ===
try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
    logger.info("YOLO für Objekterkennung geladen")
except ImportError:
    YOLO_AVAILABLE = False
    YOLO = None
    logger.warning("YOLO nicht verfügbar - Objekterkennung deaktiviert")

# === AUDIO IMPORTS ===
try:
    import sounddevice as sd
    import scipy.signal as signal
    AUDIO_AVAILABLE = True
    logger.info("Sounddevice für Audio-Zuhören geladen")
except ImportError:
    AUDIO_AVAILABLE = False
    sd = None
    logger.warning("Sounddevice nicht verfügbar - Audio-Zuhören deaktiviert")

# === KONFIGURATION ===
SCREENSHOT_DIR = Path(__file__).parent.parent / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

WEBCAM_DIR = SCREENSHOT_DIR / "webcam"
WEBCAM_DIR.mkdir(exist_ok=True)

VISION_CLICK_CONFIDENCE_THRESHOLD = 0.75


class GABIVision:
    """
    GABIs Seh-Fähigkeiten: Screenshots + Webcam + Vision-basierte Klicks
    """

    def __init__(self):
        self.cv2 = cv2
        self.np = np
        self.screenshot_dir = SCREENSHOT_DIR
        self.webcam_dir = WEBCAM_DIR
        self._webcam_active = False
        self._webcam_thread: Optional[threading.Thread] = None
        self._motion_callback = None
        self._yolo_callback = None
        self._last_yolo_objects = []  # Letzte YOLO-Erkennungen für Chat
        self._last_motion_time = 0
        self._motion_detected = False

        # Webcam-Objekt
        self._capture: Optional[Any] = None

        # YOLO für Objekterkennung
        self._yolo_model = None
        if YOLO_AVAILABLE:
            try:
                # Lade YOLO Modell (klein für Speed)
                self._yolo_model = YOLO("yolov8n.pt")
                logger.info("YOLO Modell geladen (yolov8n)")
            except Exception as e:
                logger.warning(f"YOLO konnte nicht geladen werden: {e}")

        # Audio-Zuhören
        self._audio_listening = False
        self._audio_thread: Optional[threading.Thread] = None
        self._audio_callback: Optional[Callable] = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._last_audio_time = 0

        logger.info("👁️ GABI Vision initialisiert")

    def check_available(self) -> Dict[str, bool]:
        """Gibt zurück welche Vision-Features verfügbar sind."""
        return {
            "opencv": CV2_AVAILABLE,
            "yolo": YOLO_AVAILABLE,
            "audio": AUDIO_AVAILABLE,
            "webcam": self.is_webcam_available(),
            "screenshot": True,  # Immer verfügbar via pyautogui
            "ready": CV2_AVAILABLE
        }

    # ==================== SCREENSHOT + VISION ====================

    def take_screenshot(self, filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Nimmt einen Screenshot auf und speichert ihn.

        Returns:
            Dict mit 'success', 'path', 'base64', 'size'
        """
        try:
            import pyautogui
            screenshot = pyautogui.screenshot()

            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"gabi_screenshot_{timestamp}.png"

            filepath = self.screenshot_dir / filename
            screenshot.save(str(filepath))

            # Base64 für API
            with open(filepath, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")

            logger.info(f"📸 Screenshot gespeichert: {filepath}")

            return {
                "success": True,
                "path": str(filepath),
                "filename": filename,
                "base64": b64,
                "size": {"width": screenshot.width, "height": screenshot.height},
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"❌ Screenshot-Fehler: {e}")
            return {"success": False, "error": str(e)}

    async def analyze_screenshot_with_ai(self, image_path: Optional[str] = None,
                                          prompt: str = "Beschreibe was du auf diesem Bild siehst.") -> Dict[str, Any]:
        """
        Analysiert einen Screenshot mit Ollama Vision (falls verfügbar).

        Args:
            image_path: Pfad zum Bild (None = neuer Screenshot)
            prompt: Frage an die KI

        Returns:
            Dict mit 'success', 'analysis'
        """
        # Erst Screenshot falls nötig
        if not image_path:
            screenshot_result = self.take_screenshot()
            if not screenshot_result.get("success"):
                return screenshot_result
            image_path = screenshot_result["path"]
            base64_image = screenshot_result.get("base64")
        else:
            # Bild zu Base64 konvertieren
            try:
                with open(image_path, "rb") as f:
                    base64_image = base64.b64encode(f.read()).decode("utf-8")
            except Exception as e:
                return {"success": False, "error": f"Konnte Bild nicht laden: {e}"}

        # Prüfe ob Ollama Vision unterstützt
        try:
            from gateway.ollama_client import ollama_client

            # Ollama Vision Prompt
            vision_prompt = f'[img-64]{base64_image}[/img-64]\n\n{prompt}'

            # Versuche mit Vision-Modell
            response = ollama_client.chat(
                model="llama3.2-vision",  # Vision-Modell
                messages=[{"role": "user", "content": vision_prompt}],
                options={"temperature": 0.3}
            )

            analysis = ""
            if isinstance(response, dict):
                analysis = response.get('message', {}).get('content', str(response))
            else:
                analysis = str(response)

            return {
                "success": True,
                "analysis": analysis,
                "image_path": image_path,
                "prompt": prompt
            }

        except Exception as e:
            logger.warning(f"Vision-Analyse fehlgeschlagen: {e}")
            # Fallback: Nur Bildbeschreibung ohne KI
            return {
                "success": True,
                "analysis": f"(Vision nicht verfügbar) Screenshot gespeichert: {image_path}\n\nFehler: {str(e)}",
                "image_path": image_path,
                "prompt": prompt
            }

    # ==================== WEBCAM FUNKTIONEN ====================

    def is_webcam_available(self) -> bool:
        """Prüft ob eine Webcam verfügbar ist."""
        if not CV2_AVAILABLE:
            return False

        try:
            cap = cv2.VideoCapture(0)
            if cap.isOpened():
                cap.release()
                return True
        except:
            pass
        return False

    def capture_webcam(self, filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Nimmt ein Webcam-Foto auf.

        Returns:
            Dict mit 'success', 'path', 'base64', 'timestamp'
        """
        if not CV2_AVAILABLE:
            return {"success": False, "error": "OpenCV nicht verfügbar"}

        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return {"success": False, "error": "Webcam konnte nicht geöffnet werden"}

            # Mehrere Frames lesen für bessere Qualität und Webcam-Aufwärmung
            frame = None
            for i in range(15):  # Mehr Frames für Webcam-Aufwärmung
                ret, frame = cap.read()
                if ret and frame is not None and frame.mean() > 10:  # Warte bis Bild hell genug
                    break
            cap.release()

            if not ret or frame is None:
                return {"success": False, "error": "Kein Bild von Webcam empfangen"}

            if frame.mean() < 5:
                return {"success": False, "error": "Webcam liefert schwarze Bilder - ist sie abgedeckt?"}

            # Bild NICHT drehen (falls nötig, einkommentieren)

            # Farbe für Anzeige konvertieren
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            # Speichern
            if not filename:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"webcam_{timestamp}.png"

            filepath = self.webcam_dir / filename
            cv2.imwrite(str(filepath), frame)

            # Base64
            with open(filepath, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("utf-8")

            logger.info(f"📷 Webcam-Foto gespeichert: {filepath}")

            return {
                "success": True,
                "path": str(filepath),
                "filename": filename,
                "base64": b64,
                "timestamp": datetime.now().isoformat(),
                "size": {"width": frame.shape[1], "height": frame.shape[0]}
            }

        except Exception as e:
            logger.error(f"❌ Webcam-Fehler: {e}")
            return {"success": False, "error": str(e)}

    def start_motion_detection(self, callback=None, threshold: int = 25) -> Dict[str, Any]:
        """
        Startet Bewegungserkennung mit Webcam.

        Args:
            callback: Funktion die bei Bewegung aufgerufen wird
            threshold: Empfindlichkeit (niedriger = empfindlicher)

        Returns:
            Dict mit 'success'
        """
        if not CV2_AVAILABLE:
            return {"success": False, "error": "OpenCV nicht verfügbar"}

        if self._webcam_active:
            return {"success": False, "error": "Bewegungserkennung bereits aktiv"}

        self._motion_callback = callback
        self._motion_detected = False
        self._webcam_active = True

        def motion_loop():
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                logger.error("Webcam für Bewegungserkennung konnte nicht geöffnet werden")
                self._webcam_active = False
                return

            # Erstes Bild als Referenz
            ret, frame1 = cap.read()
            if not ret:
                cap.release()
                self._webcam_active = False
                return

            frame1 = cv2.cvtColor(frame1, cv2.COLOR_BGR2GRAY)
            frame1 = cv2.GaussianBlur(frame1, (21, 21), 0)

            logger.info("🔍 Bewegungserkennung gestartet")

            while self._webcam_active:
                ret, frame2 = cap.read()
                if not ret:
                    break

                frame2_gray = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
                frame2_gray = cv2.GaussianBlur(frame2_gray, (21, 21), 0)

                # Differenz berechnen
                diff = cv2.absdiff(frame1, frame2_gray)
                thresh = cv2.threshold(diff, threshold, 255, cv2.THRESH_BINARY)[1]

                # Konturen finden
                contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                # Bewegung erkannt?
                motion_detected = False
                for contour in contours:
                    if cv2.contourArea(contour) > 500:  # Mindestgröße
                        motion_detected = True
                        break

                if motion_detected and not self._motion_detected:
                    self._motion_detected = True
                    self._last_motion_time = time.time()
                    logger.info("👁️ Bewegung erkannt!")

                    # Callback aufrufen
                    if self._motion_callback:
                        try:
                            self._motion_callback({
                                "type": "motion",
                                "timestamp": datetime.now().isoformat(),
                                "frame": frame2
                            })
                        except Exception as e:
                            logger.error(f"Bewegungs-Callback Fehler: {e}")

                elif not motion_detected:
                    self._motion_detected = False

                # Alle 30 Frames Referenz aktualisieren
                if int(cap.get(cv2.CAP_PROP_POS_FRAMES)) % 30 == 0:
                    frame1 = frame2_gray

                time.sleep(0.1)

            cap.release()
            logger.info("🛑 Bewegungserkennung gestoppt")

        self._webcam_thread = threading.Thread(target=motion_loop, daemon=True)
        self._webcam_thread.start()

        return {
            "success": True,
            "message": "Bewegungserkennung gestartet"
        }

    def stop_motion_detection(self) -> Dict[str, Any]:
        """Stoppt die Bewegungserkennung."""
        self._webcam_active = False
        if self._webcam_thread:
            self._webcam_thread.join(timeout=2)
        return {"success": True, "message": "Bewegungserkennung gestoppt"}

    def start_yolo_stream(self, interval: float = 2.0, callback=None) -> Dict[str, Any]:
        """
        Startet kontinuierliche YOLO-Objekterkennung im Hintergrund.

        Args:
            interval: Zeit zwischen Erkennungen in Sekunden
            callback: Funktion die bei jeder Erkennung aufgerufen wird (objekte, bild)

        Returns:
            Dict mit 'success'
        """
        if not CV2_AVAILABLE:
            return {"success": False, "error": "OpenCV nicht verfügbar"}

        if not YOLO_AVAILABLE:
            return {"success": False, "error": "YOLO nicht verfügbar"}

        if self._webcam_active:
            return {"success": False, "error": "Erkennung bereits aktiv"}

        self._webcam_active = True
        self._yolo_callback = callback

        def yolo_loop():
            import cv2
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                logger.error("Webcam konnte nicht geöffnet werden")
                self._webcam_active = False
                return

            model = self._yolo_model
            if model is None:
                logger.error("YOLO-Modell nicht geladen")
                self._webcam_active = False
                return

            logger.info("🔍 YOLO-Stream gestartet")
            last_detection_time = 0

            while self._webcam_active:
                ret, frame = cap.read()
                if not ret:
                    break

                # Zeitsteuerung
                current_time = time.time()
                if current_time - last_detection_time < interval:
                    time.sleep(0.1)
                    continue

                last_detection_time = current_time

                # YOLO Erkennung
                try:
                    results = model(frame, verbose=False)
                    objects = []
                    if len(results) > 0:
                        result = results[0]
                        boxes = result.boxes
                        for box in boxes:
                            cls = int(box.cls[0])
                            conf = float(box.conf[0])
                            if conf > 0.3:  # Mindestkonfidenz
                                name = result.names[cls]
                                objects.append({"class": name, "confidence": conf})

                    # Callback aufrufen wenn Objekte erkannt
                    if objects and self._yolo_callback:
                        try:
                            self._yolo_callback(objects, frame)
                        except Exception as e:
                            logger.error(f"YOLO Callback Fehler: {e}")

                    # Speichere Erkennungen für Chat-Status
                    if objects:
                        self._last_yolo_objects = objects
                        obj_names = [f"{o['class']}" for o in objects[:5]]
                        logger.info(f"🔍 Erkannt: {', '.join(obj_names)}")

                except Exception as e:
                    logger.error(f"YOLO Stream Fehler: {e}")

            cap.release()
            logger.info("🔍 YOLO-Stream beendet")

        self._webcam_thread = threading.Thread(target=yolo_loop, daemon=True)
        self._webcam_thread.start()
        return {"success": True, "message": "YOLO-Stream gestartet"}

    def stop_yolo_stream(self) -> Dict[str, Any]:
        """Stoppt den YOLO-Stream."""
        self._webcam_active = False
        if self._webcam_thread:
            self._webcam_thread.join(timeout=3)
        return {"success": True, "message": "YOLO-Stream gestoppt"}

    def get_motion_status(self) -> Dict[str, Any]:
        """Gibt den Status der Bewegungserkennung zurück."""
        return {
            "active": self._webcam_active,
            "last_motion": self._last_motion_time,
            "time_since_motion": time.time() - self._last_motion_time if self._last_motion_time > 0 else None
        }

    def start_yolo_stream(self, interval: float = 2.0) -> Dict[str, Any]:
        """
        Startet kontinuierliche YOLO-Objekterkennung.

        Args:
            interval: Zeit zwischen Erkennungen in Sekunden

        Returns:
            Dict mit 'success'
        """
        if not CV2_AVAILABLE:
            return {"success": False, "error": "OpenCV nicht verfügbar"}

        if not YOLO_AVAILABLE:
            return {"success": False, "error": "YOLO nicht verfügbar"}

        if self._webcam_active:
            return {"success": False, "error": "Eine Überwachung läuft bereits"}

        self._webcam_active = True
        self._last_objects = []

        def yolo_loop():
            import asyncio
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                logger.error("Webcam konnte nicht geöffnet werden")
                self._webcam_active = False
                return

            model = self._yolo_model
            if model is None:
                logger.error("YOLO-Modell nicht geladen")
                self._webcam_active = False
                return

            logger.info("🔍 YOLO-Stream gestartet")

            while self._webcam_active:
                ret, frame = cap.read()
                if not ret:
                    break

                # YOLO Erkennung
                results = model(frame, verbose=False)
                objects = []

                if len(results) > 0:
                    result = results[0]
                    boxes = result.boxes
                    for box in boxes:
                        cls_id = int(box.cls[0])
                        conf = float(box.conf[0])
                        if conf > 0.3:  # Nur Objekte mit >30% Konfidenz
                            name = result.names[cls_id]
                            objects.append({"class": name, "confidence": conf})

                self._last_objects = objects
                logger.info(f"🔍 Erkannt: {objects}")

                # Warten
                time.sleep(interval)

            cap.release()
            logger.info("🔍 YOLO-Stream gestoppt")

        self._webcam_thread = threading.Thread(target=yolo_loop, daemon=True)
        self._webcam_thread.start()

        return {
            "success": True,
            "message": "YOLO-Stream gestartet"
        }

    def get_yolo_objects(self) -> list:
        """Gibt die letzten erkannten Objekte zurück."""
        return self._last_objects

    # ==================== AUTO-CLICK via VISION ====================

    async def find_and_click_element(self, description: str,
                                      reference_image: Optional[str] = None) -> Dict[str, Any]:
        """
        Findet ein Element auf dem Bildschirm durch:
        1. Bildanalyse (falls Referenzbild gegeben)
        2. KI-Vision (falls Beschreibung gegeben)

        Args:
            description: Textuelle Beschreibung des Elements ("der Play-Button", "das Suchfeld")
            reference_image: Optionaler Pfad zu einem Referenzbild

        Returns:
            Dict mit 'success', 'position' (x, y), 'action'
        """
        if not CV2_AVAILABLE:
            return {"success": False, "error": "OpenCV nicht verfügbar"}

        try:
            # 1. Screenshot machen
            screenshot_result = self.take_screenshot()
            if not screenshot_result.get("success"):
                return screenshot_result

            screenshot_path = screenshot_result["path"]

            # 2. Element finden
            position = None
            method = ""

            # Fall A: Template-Matching mit Referenzbild
            if reference_image and os.path.exists(reference_image):
                result = self._template_match(screenshot_path, reference_image)
                if result.get("success"):
                    position = result["position"]
                    method = "template_match"

            # Fall B: KI-Vision basierte Suche
            if not position and description:
                # KI fragt wo das Element ist
                vision_result = await self.analyze_screenshot_with_ai(
                    image_path=screenshot_path,
                    prompt=f"""Ich suche auf diesem Bildschirmfoto nach: "{description}"

                    Findest du dieses Element? Wenn ja, gib mir die Koordinaten als JSON zurück:
                    {{"found": true/false, "x": position_x, "y": position_y, "description": "was du gesehen hast"}}

                    Der Bildschirm ist {screenshot_result['size']['width']}x{screenshot_result['size']['height']} Pixel groß.
                    Antworte NUR mit dem JSON, keine Erklärung."""
                )

                if vision_result.get("success"):
                    # Versuche JSON zu parsen
                    try:
                        import re
                        json_match = re.search(r'\{[^}]+\}', vision_result["analysis"])
                        if json_match:
                            data = json.loads(json_match.group())
                            if data.get("found"):
                                position = (data.get("x"), data.get("y"))
                                method = "vision_ai"
                    except:
                        pass

            # 3. Klicken falls gefunden
            if position:
                x, y = position
                import pyautogui
                pyautogui.click(x, y)
                logger.info(f"👆 Geklickt bei ({x}, {y}) via {method}")

                return {
                    "success": True,
                    "position": {"x": x, "y": y},
                    "method": method,
                    "screenshot": screenshot_path,
                    "action": f"Geklickt auf {description}"
                }

            return {
                "success": False,
                "error": f"Element nicht gefunden: {description}"
            }

        except Exception as e:
            logger.error(f"Auto-Click Fehler: {e}")
            return {"success": False, "error": str(e)}

    def _template_match(self, screenshot_path: str, template_path: str) -> Dict[str, Any]:
        """Template-Matching für Icon-Suche."""
        try:
            screenshot = cv2.imread(screenshot_path)
            template = cv2.imread(template_path)

            if screenshot is None or template is None:
                return {"success": False, "error": "Bild konnte nicht geladen werden"}

            # Graustufen
            gray_s = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)
            gray_t = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

            # Template-Matching
            result = cv2.matchTemplate(gray_s, gray_t, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            if max_val >= VISION_CLICK_CONFIDENCE_THRESHOLD:
                h, w = template.shape[:2]
                center_x = max_loc[0] + w // 2
                center_y = max_loc[1] + h // 2

                return {
                    "success": True,
                    "position": (center_x, center_y),
                    "confidence": float(max_val)
                }

            return {"success": False, "error": f"Nicht gefunden (Confidence: {max_val:.2f})"}

        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==================== OBJEKTERKENNUNG (YOLO) ====================

    def detect_objects(self, image_path: Optional[str] = None,
                      source: str = "webcam") -> Dict[str, Any]:
        """
        Erkennt Objekte mit YOLO in Webcam oder Screenshot.
        """
        if not YOLO_AVAILABLE:
            return {"success": False, "error": "YOLO nicht verfügbar. Installiere: pip install ultralytics"}

        try:
            model = self._yolo_model
            if model is None:
                return {"success": False, "error": "YOLO-Modell nicht geladen"}

            # Bildquelle bestimmen
            if source == "webcam" or image_path is None:
                cap = cv2.VideoCapture(0)
                # Mehrere Frames für Webcam-Aufwärmung
                frame = None
                for i in range(15):
                    ret, frame = cap.read()
                    if ret and frame is not None and frame.mean() > 10:
                        break
                cap.release()
                if not ret or frame is None:
                    return {"success": False, "error": "Kein Bild von Webcam"}
                if frame.mean() < 5:
                    return {"success": False, "error": "Webcam liefert schwarze Bilder"}
                temp_path = self.webcam_dir / "temp_detect.png"
                cv2.imwrite(str(temp_path), frame)
                image_path = str(temp_path)
            elif source == "screenshot" and image_path is None:
                ss = self.take_screenshot()
                if not ss.get("success"):
                    return ss
                image_path = ss["path"]

            # Objekterkennung
            results = model(image_path, verbose=False)

            objects = []
            if len(results) > 0:
                result = results[0]
                boxes = result.boxes
                for box in boxes:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    cls_id = int(box.cls[0].cpu().numpy())
                    conf = float(box.conf[0].cpu().numpy())
                    class_name = result.names[cls_id]
                    objects.append({
                        "class": class_name,
                        "confidence": round(conf, 3),
                        "center": {"x": int((x1 + x2) / 2), "y": int((y1 + y2) / 2)}
                    })

            class_counts = {}
            for obj in objects:
                cls = obj["class"]
                class_counts[cls] = class_counts.get(cls, 0) + 1

            summary = ", ".join([f"{k} ({v}x)" for k, v in class_counts.items()]) if class_counts else "Keine Objekte erkannt"

            return {
                "success": True,
                "objects": objects,
                "summary": summary,
                "total": len(objects),
                "class_counts": class_counts
            }

        except Exception as e:
            logger.error(f"Objekterkennung Fehler: {e}")
            return {"success": False, "error": str(e)}

    def detect_faces(self, source: str = "webcam") -> Dict[str, Any]:
        """Erkennt Gesichter mit OpenCV."""
        if not CV2_AVAILABLE:
            return {"success": False, "error": "OpenCV nicht verfügbar"}

        try:
            if source == "webcam":
                cap = cv2.VideoCapture(0)
                ret, frame = cap.read()
                cap.release()
                if not ret:
                    return {"success": False, "error": "Kein Webcam-Bild"}
            else:
                ss = self.take_screenshot()
                if not ss.get("success"):
                    return ss
                frame = cv2.imread(ss["path"])

            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
            faces = face_cascade.detectMultiScale(gray, 1.1, 4)

            face_list = [{"x": int(x), "y": int(y), "w": int(w), "h": int(h)} for (x, y, w, h) in faces]

            return {
                "success": True,
                "faces": face_list,
                "count": len(face_list),
                "summary": f"{len(face_list)} Gesicht(er) erkannt" if face_list else "Keine Gesichter"
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==================== AUDIO-ZUHÖREN ====================

    def start_audio_listening(self, callback=None, threshold: float = 0.01) -> Dict[str, Any]:
        """Startet kontinuierliches Audio-Zuhören."""
        if not AUDIO_AVAILABLE:
            return {"success": False, "error": "Audio nicht verfügbar. Installiere: pip install sounddevice scipy"}

        if self._audio_listening:
            return {"success": False, "error": "Bereits aktiv"}

        self._audio_callback = callback
        self._audio_threshold = threshold
        self._audio_listening = True

        def audio_callback(indata, frames, time_info, status):
            if status:
                logger.warning(f"Audio: {status}")
            volume = np.linalg.norm(indata) / len(indata)
            if volume > threshold:
                if self._audio_callback:
                    self._audio_callback({"type": "sound", "volume": float(volume)})

        try:
            self._audio_stream = sd.InputStream(channels=1, samplerate=16000, callback=audio_callback)
            self._audio_stream.start()
            logger.info("🎤 Audio-Zuhören gestartet")
            return {"success": True, "message": "GABI hört zu!"}
        except Exception as e:
            self._audio_listening = False
            return {"success": False, "error": str(e)}

    def stop_audio_listening(self) -> Dict[str, Any]:
        """Stoppt Audio-Zuhören."""
        if not self._audio_listening:
            return {"success": False, "error": "Nicht aktiv"}
        try:
            if hasattr(self, '_audio_stream'):
                self._audio_stream.stop()
                self._audio_stream.close()
            self._audio_listening = False
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_audio_status(self) -> Dict[str, Any]:
        """Gibt Audio-Status zurück."""
        return {
            "listening": self._audio_listening,
            "threshold": self._audio_threshold
        }

    async def listen_for_command(self, timeout: float = 5.0) -> Dict[str, Any]:
        """Lauscht auf Sprachbefehl und transkribiert mit Whisper."""
        if not AUDIO_AVAILABLE:
            return {"success": False, "error": "Audio nicht verfügbar"}

        try:
            audio_data = []
            start_time = time.time()

            def callback(indata, frames, time_info, status):
                audio_data.append(indata.copy())

            with sd.InputStream(channels=1, samplerate=16000, callback=callback):
                while time.time() - start_time < timeout:
                    if len(audio_data) > 0:
                        vol = np.linalg.norm(audio_data[-1]) / len(audio_data[-1])
                        if vol > 0.02:
                            break
                    time.sleep(0.1)

            if not audio_data:
                return {"success": False, "error": "Keine Sprache erkannt"}

            audio_combined = np.concatenate(audio_data)
            audio_path = self.webcam_dir / "voice_command.wav"
            import scipy.io.wavfile as wav
            wav.write(str(audio_path), 16000, (audio_combined * 32767).astype(np.int16))

            # Mit Whisper transkribieren
            try:
                from integrations.whisper_client import get_whisper_client
                whisper = get_whisper_client()
                result = whisper.transcribe_file(str(audio_path))
                return {
                    "success": True,
                    "text": result.get("text", ""),
                    "audio_path": str(audio_path)
                }
            except Exception as e:
                return {"success": True, "text": "(Whisper nicht verfügbar)", "error": str(e)}

        except Exception as e:
            return {"success": False, "error": str(e)}

    # ==================== OBJEKTERKENNUNG (YOLO) ====================

    def detect_objects(self, image_path: Optional[str] = None,
                      source: str = "webcam") -> Dict[str, Any]:
        """
        Erkennt Objekte in einem Bild oder Webcam-Stream.

        Args:
            image_path: Pfad zum Bild (None = neuer Webcam-Schnappschuss)
            source: "webcam", "screenshot" oder "file"

        Returns:
            Dict mit erkannten Objekten, Koordinaten, Konfidenz
        """
        if not YOLO_AVAILABLE:
            return {"success": False, "error": "YOLO nicht verfügbar. Installiere: pip install ultralytics"}

        try:
            model = self._yolo_model
            if model is None:
                return {"success": False, "error": "YOLO-Modell konnte nicht geladen werden"}

            # Bildquelle bestimmen
            if source == "webcam" or (image_path is None and source == "webcam"):
                cap = cv2.VideoCapture(0)
                # Webcam-Aufwärmung
                frame = None
                for i in range(15):
                    ret, frame = cap.read()
                    if ret and frame is not None and frame.mean() > 10:
                        break
                cap.release()
                if not ret or frame is None:
                    return {"success": False, "error": "Kein Bild von Webcam"}
                if frame.mean() < 5:
                    return {"success": False, "error": "Webcam liefert schwarze Bilder"}
                # Frame temporär speichern
                temp_path = self.webcam_dir / "temp_detect.png"
                cv2.imwrite(str(temp_path), frame)
                image_path = str(temp_path)
            elif source == "screenshot" and image_path is None:
                ss = self.take_screenshot()
                if not ss.get("success"):
                    return ss
                image_path = ss["path"]

            # Objekterkennung durchführen
            results = model(image_path, verbose=False)

            # Ergebnisse parsen
            objects = []
            if len(results) > 0:
                result = results[0]
                boxes = result.boxes

                for box in boxes:
                    # Koordinaten
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    # Klasse und Konfidenz
                    cls_id = int(box.cls[0].cpu().numpy())
                    conf = float(box.conf[0].cpu().numpy())
                    class_name = result.names[cls_id]

                    objects.append({
                        "class": class_name,
                        "confidence": round(conf, 3),
                        "bbox": {
                            "x1": int(x1), "y1": int(y1),
                            "x2": int(x2), "y2": int(y2)
                        },
                        "center": {
                            "x": int((x1 + x2) / 2),
                            "y": int((y1 + y2) / 2)
                        }
                    })

            # Zusammenfassung
            class_counts = {}
            for obj in objects:
                cls = obj["class"]
                class_counts[cls] = class_counts.get(cls, 0) + 1

            summary = ", ".join([f"{k} ({v}x)" for k, v in class_counts.items()]) if class_counts else "Keine Objekte erkannt"

            return {
                "success": True,
                "image_path": image_path,
                "objects": objects,
                "summary": summary,
                "total_objects": len(objects),
                "class_counts": class_counts
            }

        except Exception as e:
            logger.error(f"Objekterkennung Fehler: {e}")
            return {"success": False, "error": str(e)}

    def detect_faces(self, image_path: Optional[str] = None,
                     source: str = "webcam") -> Dict[str, Any]:
        """
        Erkennt Gesichter mit OpenCV Haar Cascades.

        Args:
            image_path: Pfad zum Bild
            source: "webcam" oder "screenshot"

        Returns:
            Dict mit Gesichtspositionen
        """
        if not CV2_AVAILABLE:
            return {"success": False, "error": "OpenCV nicht verfügbar"}

        try:
            # Bild laden
            if source == "webcam" or image_path is None:
                cap = cv2.VideoCapture(0)
                ret, frame = cap.read()
                cap.release()
                if not ret:
                    return {"success": False, "error": "Kein Webcam-Bild"}
                image = frame
            else:
                image = cv2.imread(image_path)

            # Graustufen für Erkennung
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # Haar Cascade für Gesichter
            face_cascade = cv2.CascadeClassifier(
                cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            )

            faces = face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(30, 30)
            )

            face_list = []
            for (x, y, w, h) in faces:
                face_list.append({
                    "bbox": {"x": int(x), "y": int(y), "w": int(w), "h": int(h)},
                    "center": {"x": int(x + w/2), "y": int(y + h/2)}
                })

            return {
                "success": True,
                "faces": face_list,
                "count": len(face_list),
                "summary": f"{len(face_list)} Gesicht(er) erkannt" if face_list else "Keine Gesichter erkannt"
            }

        except Exception as e:
            logger.error(f"Gesichtserkennung Fehler: {e}")
            return {"success": False, "error": str(e)}

    # ==================== AUDIO-ZUHÖREN ====================

    def start_audio_listening(self, callback: Optional[Callable] = None,
                              threshold: float = 0.01) -> Dict[str, Any]:
        """
        Startet kontinuierliches Audio-Zuhören.

        Args:
            callback: Funktion die bei erkannter Sprache aufgerufen wird
            threshold: Empfindlichkeit (0.0-1.0)

        Returns:
            Dict mit Status
        """
        if not AUDIO_AVAILABLE:
            return {"success": False, "error": "Audio nicht verfügbar. Installiere: pip install sounddevice scipy"}

        if self._audio_listening:
            return {"success": False, "error": "Audio-Zuhören bereits aktiv"}

        self._audio_callback = callback

        def audio_callback(indata, frames, time_info, status):
            """Callback für Sounddevice."""
            if status:
                logger.warning(f"Audio Status: {status}")

            # Lautstärke berechnen
            volume = np.linalg.norm(indata) / len(indata)

            # Wenn Lautstärke über Threshold
            if volume > threshold:
                self._audio_queue.put({
                    "type": "audio",
                    "volume": float(volume),
                    "timestamp": datetime.now().isoformat()
                })

                # Callback aufrufen
                if self._audio_callback:
                    try:
                        self._audio_callback({
                            "type": "sound_detected",
                            "volume": float(volume),
                            "timestamp": datetime.now().isoformat()
                        })
                    except Exception as e:
                        logger.error(f"Audio-Callback Fehler: {e}")

        try:
            # Audio-Queue initialisieren
            self._audio_queue = queue.Queue()

            # Stream starten
            self._audio_stream = sd.InputStream(
                channels=1,
                samplerate=16000,
                blocksize=1024,
                callback=audio_callback
            )
            self._audio_stream.start()
            self._audio_listening = True

            logger.info("🎤 Audio-Zuhören gestartet")
            return {
                "success": True,
                "message": "GABI hört zu! Sprich mit mir.",
                "threshold": threshold
            }

        except Exception as e:
            logger.error(f"Audio-Start Fehler: {e}")
            return {"success": False, "error": str(e)}

    def stop_audio_listening(self) -> Dict[str, Any]:
        """Stoppt das Audio-Zuhören."""
        if not self._audio_listening:
            return {"success": False, "error": "Audio-Zuhören nicht aktiv"}

        try:
            if hasattr(self, '_audio_stream'):
                self._audio_stream.stop()
                self._audio_stream.close()
            self._audio_listening = False
            logger.info("🛑 Audio-Zuhören gestoppt")
            return {"success": True, "message": "Audio-Zuhören gestoppt"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_audio_status(self) -> Dict[str, Any]:
        """Gibt den Status des Audio-Zuhörens zurück."""
        return {
            "listening": self._audio_listening,
            "threshold": getattr(self, '_audio_threshold', 0.01),
            "queue_size": self._audio_queue.qsize() if hasattr(self, '_audio_queue') and self._audio_listening else 0
        }

    async def listen_for_command(self, timeout: float = 5.0) -> Dict[str, Any]:
        """
        Lauscht auf Sprachbefehl und transkribiert mit Whisper.

        Args:
            timeout: Maximale Wartezeit in Sekunden

        Returns:
            Dict mit transkribiertem Text
        """
        if not AUDIO_AVAILABLE:
            return {"success": False, "error": "Audio nicht verfügbar"}

        try:
            # Audio aufnehmen
            logger.info("🎤 Warte auf Sprachbefehl...")
            audio_data = []
            start_time = time.time()

            def callback(indata, frames, time_info, status):
                audio_data.append(indata.copy())

            with sd.InputStream(channels=1, samplerate=16000, callback=callback):
                while time.time() - start_time < timeout:
                    if len(audio_data) > 0:
                        # Prüfe ob genug Lautstärke
                        vol = np.linalg.norm(audio_data[-1]) / len(audio_data[-1])
                        if vol > 0.02:  # Sprachschwelle
                            break
                    time.sleep(0.1)

            if not audio_data:
                return {"success": False, "error": "Keine Sprache erkannt"}

            # Audio kombinieren
            audio_combined = np.concatenate(audio_data)

            # Als WAV speichern
            import scipy.io.wavfile as wav
            audio_path = self.webcam_dir / "voice_command.wav"
            wav.write(str(audio_path), 16000, (audio_combined * 32767).astype(np.int16))

            # Mit Whisper transkribieren
            try:
                from integrations.whisper_client import get_whisper_client
                whisper = get_whisper_client()

                result = whisper.transcribe_file(str(audio_path))
                return {
                    "success": True,
                    "text": result.get("text", ""),
                    "audio_path": str(audio_path),
                    "duration": result.get("duration", 0)
                }
            except Exception as e:
                return {
                    "success": True,
                    "text": "(Whisper nicht verfügbar)",
                    "audio_path": str(audio_path),
                    "whisper_error": str(e)
                }

        except Exception as e:
            logger.error(f"Sprachbefehl Fehler: {e}")
            return {"success": False, "error": str(e)}

    # ==================== HILFSMETHODEN ====================

    def list_screenshots(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Liste letzte Screenshots auf."""
        try:
            files = sorted(self.screenshot_dir.glob("*.png"), key=lambda x: x.stat().st_mtime, reverse=True)
            return [
                {
                    "filename": f.name,
                    "path": str(f),
                    "size": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                }
                for f in files[:limit]
            ]
        except Exception as e:
            return []

    def list_webcam_captures(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Liste letzte Webcam-Aufnahmen auf."""
        try:
            files = sorted(self.webcam_dir.glob("*.png"), key=lambda x: x.stat().st_mtime, reverse=True)
            return [
                {
                    "filename": f.name,
                    "path": str(f),
                    "size": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                }
                for f in files[:limit]
            ]
        except Exception as e:
            return []


# === SINGLETON ===
_gabi_vision: Optional[GABIVision] = None


def get_gabi_vision() -> GABIVision:
    """Gibt die Singleton-Instanz zurück."""
    global _gabi_vision
    if _gabi_vision is None:
        _gabi_vision = GABIVision()
    return _gabi_vision


# === CONVENIENCE FUNCTIONS ===
def take_screenshot(filename: Optional[str] = None) -> Dict[str, Any]:
    return get_gabi_vision().take_screenshot(filename)


def capture_webcam(filename: Optional[str] = None) -> Dict[str, Any]:
    return get_gabi_vision().capture_webcam(filename)


async def analyze_screenshot(prompt: str = "Beschreibe was du siehst") -> Dict[str, Any]:
    return await get_gabi_vision().analyze_screenshot_with_ai(prompt=prompt)


if __name__ == "__main__":
    vision = get_gabi_vision()
    print("👁️ GABI Vision geladen")
    print(f"Verfügbarkeit: {vision.check_available()}")

    # Test Screenshot
    result = vision.take_screenshot()
    print(f"Screenshot: {result.get('success')}")

    # Test Webcam
    if vision.is_webcam_available():
        result = vision.capture_webcam()
        print(f"Webcam: {result.get('success')}")
