# integrations/gabi_vision.py
"""GABI Vision module for webcam and YOLO object detection."""

import cv2
import numpy as np
import logging
import asyncio
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

try:
    import torch
    import torchvision
    YOLO_AVAILABLE = False
    try:
        from ultralytics import YOLO
        YOLO_AVAILABLE = True
    except ImportError:
        logger.warning("Ultralytics not installed. YOLO disabled.")
except ImportError:
    logger.warning("PyTorch not installed. YOLO disabled.")


class GabiVision:
    """GABI Vision for webcam and object detection."""
    
    def __init__(self):
        self.camera = None
        self.yolo_model = None
        self._webcam_active = False
        self._last_yolo_objects = []
        self._yolo_thread = None
        self._yolo_running = False
        self._init_yolo()
    
    def _init_yolo(self):
        """Initialize YOLO model."""
        if YOLO_AVAILABLE:
            try:
                # Try to load YOLO model
                self.yolo_model = YOLO("yolov8n.pt")
                logger.info("✅ YOLO model initialized")
            except Exception as e:
                logger.error(f"YOLO init error: {e}")
    
    def is_webcam_available(self) -> bool:
        """Check if webcam is available."""
        try:
            cap = cv2.VideoCapture(0)
            if cap.isOpened():
                cap.release()
                return True
            return False
        except:
            return False
    
    def is_yolo_available(self) -> bool:
        """Check if YOLO is available."""
        return self.yolo_model is not None
    
    def capture_webcam(self) -> Dict[str, Any]:
        """Capture image from webcam."""
        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return {"success": False, "error": "Webcam not available"}
            
            ret, frame = cap.read()
            cap.release()
            
            if not ret:
                return {"success": False, "error": "Failed to capture frame"}
            
            # Save image
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"webcam_{timestamp}.jpg"
            filepath = f"screenshots/vision/{filename}"
            
            Path("screenshots/vision").mkdir(parents=True, exist_ok=True)
            cv2.imwrite(filepath, frame)
            
            # Convert to base64
            import base64
            _, buffer = cv2.imencode('.jpg', frame)
            img_base64 = base64.b64encode(buffer).decode('utf-8')
            
            return {
                "success": True,
                "path": filepath,
                "base64": img_base64,
                "width": frame.shape[1],
                "height": frame.shape[0]
            }
        except Exception as e:
            logger.error(f"Webcam capture error: {e}")
            return {"success": False, "error": str(e)}
    
    def detect_objects(self, image_path: str) -> Dict[str, Any]:
        """Detect objects in image using YOLO."""
        if not self.yolo_model:
            return {"success": False, "error": "YOLO not available"}
        
        try:
            results = self.yolo_model(image_path)
            
            objects = []
            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        cls = int(box.cls[0])
                        conf = float(box.conf[0])
                        name = self.yolo_model.names[cls]
                        
                        objects.append({
                            "class": name,
                            "confidence": conf,
                            "bbox": box.xyxy[0].tolist()
                        })
            
            self._last_yolo_objects = objects[:10]
            
            return {
                "success": True,
                "objects": objects,
                "count": len(objects)
            }
        except Exception as e:
            logger.error(f"YOLO detect error: {e}")
            return {"success": False, "error": str(e)}
    
    def start_yolo_stream(self, interval: float = 2.0) -> Dict[str, Any]:
        """Start continuous YOLO detection stream."""
        if self._yolo_running:
            return {"success": False, "error": "Stream already running"}
        
        self._yolo_running = True
        self._webcam_active = True
        
        def yolo_loop():
            while self._yolo_running:
                try:
                    result = self.capture_webcam()
                    if result.get("success"):
                        detect = self.detect_objects(result["path"])
                        if detect.get("success") and detect.get("objects"):
                            self._last_yolo_objects = detect["objects"]
                            logger.debug(f"Detected: {[o['class'] for o in detect['objects'][:5]]}")
                except Exception as e:
                    logger.error(f"YOLO stream error: {e}")
                
                import time
                time.sleep(interval)
        
        self._yolo_thread = threading.Thread(target=yolo_loop, daemon=True)
        self._yolo_thread.start()
        
        return {"success": True, "message": f"YOLO stream started (interval: {interval}s)"}
    
    def stop_yolo_stream(self) -> Dict[str, Any]:
        """Stop YOLO stream."""
        self._yolo_running = False
        self._webcam_active = False
        
        if self._yolo_thread:
            self._yolo_thread.join(timeout=2)
            self._yolo_thread = None
        
        return {"success": True, "message": "YOLO stream stopped"}
    
    def get_motion_status(self) -> Dict[str, Any]:
        """Get motion detection status."""
        return {
            "active": self._webcam_active,
            "last_objects": self._last_yolo_objects[:5],
            "timestamp": datetime.now().isoformat()
        }


_gabi_vision = None

def get_gabi_vision() -> GabiVision:
    global _gabi_vision
    if _gabi_vision is None:
        _gabi_vision = GabiVision()
    return _gabi_vision