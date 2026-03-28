# brain_right.py - GABIs rechte Gehirnhälfte (kreativ, Vision, Audio, Sprache)
"""
🎨 GABI Right Hemisphere - Creativity & Perception
Zuständig für: Vision, Audio, Sprache, Kreativität, Emotionen
"""

import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from gateway.self_correction_loop import get_correction_loop



logger = logging.getLogger("GABI.brain_right")

class RightHemisphere:
    """Die rechte, kreative Gehirnhälfte von GABI"""
    
    def __init__(self):
        self.name = "🎨 GABI Right (Creative)"
        self.specialties = ["vision", "audio", "language", "creativity", "emotion"]
        from gateway.config import config        
        self.active_model = "llama2:latest"  # granite4:tiny-h, Bevorzugt allgemeine Modelle
        self._vision = None
        self._whisper = None
        logger.info(f"🟣 {self.name} initialisiert")
    
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Verarbeitet Input mit der rechten Hemisphäre"""
        task_type = input_data.get("type", "unknown")
        
        if task_type == "vision":
            return self._handle_vision(input_data)
        elif task_type == "audio":
            return self._handle_audio(input_data)
        elif task_type == "chat":
            return self._handle_chat(input_data)
        elif task_type == "creative":
            return self._handle_creative(input_data)
        else:
            return {"success": False, "error": "Nicht für rechte Hemisphäre geeignet"}
    
    def _get_vision(self):
        """Lazy loading für Vision-Modul"""
        if self._vision is None:
            try:
                from gateway.integrations.gabi_vision import get_gabi_vision
                self._vision = get_gabi_vision()
            except:
                logger.warning("Vision nicht verfügbar")
        return self._vision
    
    def _get_whisper(self):
        """Lazy loading für Whisper"""
        if self._whisper is None:
            try:
                from gateway.integrations.whisper_client import get_whisper_client
                self._whisper = get_whisper_client()
            except:
                logger.warning("Whisper nicht verfügbar")
        return self._whisper
    
    def _handle_vision(self, data):
        """Bildverarbeitung und Objekterkennung"""
        vision = self._get_vision()
        if not vision:
            return {"success": False, "error": "Vision nicht verfügbar"}
        
        action = data.get("action", "capture")
        if action == "capture":
            return vision.capture_webcam()
        elif action == "analyze":
            return asyncio.run(vision.analyze_screenshot_with_ai(
                prompt=data.get("prompt", "Was siehst du?")
            ))
        elif action == "detect":
            return vision.detect_objects()
        else:
            return {"success": False, "error": f"Unbekannte Aktion: {action}"}
    
    def _handle_audio(self, data):
        """Audio-Verarbeitung und Transkription"""
        whisper = self._get_whisper()
        if not whisper:
            return {"success": False, "error": "Whisper nicht verfügbar"}
        
        action = data.get("action", "transcribe")
        if action == "transcribe":
            file_path = data.get("file_path")
            if not file_path:
                return {"success": False, "error": "Keine Datei angegeben"}
            return whisper.transcribe_file(file_path)
        elif action == "listen":
            # Für Sprachbefehle
            return {"success": True, "message": "Höre zu..."}
        else:
            return {"success": False, "error": f"Unbekannte Aktion: {action}"}
    
    def _handle_chat(self, data):
        """Normale Konversation"""
        from gateway.ollama_client import ollama_client
        from gateway.http_api import _auto_select_model

        # Unterstütze sowohl "message" als auch "content" (für Corpus Callosum)
        message = data.get("message") or data.get("content", "")
        context = data.get("context", []) or data.get("hemisphere_history", [])
        
        # FIX: Auto-Modell-Auswahl basierend auf der Nachricht
        requested_model = data.get("model")  # Optional vom Caller
        selected_model = _auto_select_model(message, requested_model, None)
        
        messages = [{"role": "system", "content": self._get_system_prompt()}]
        if isinstance(context, list):
            messages.extend(context[-10:])  # Letzte 10 Nachrichten
        messages.append({"role": "user", "content": message})

        response = ollama_client.chat(
            model=selected_model,
            messages=messages
        )
        reply_text = response.get("message", {}).get("content", "") if isinstance(response, dict) else str(response)
        return {"reply": reply_text, "response": reply_text, "success": True, "model_used": selected_model}
    
    # Update für Self-Correction
    def _handle_creative(self, data):
            """Kreative Aufgaben mit Self-Correction Loop (OpenClaw Style)"""
            prompt = data.get("prompt") or data.get("content", "")
            style = data.get("style", "normal")
            context = data.get("context", []) or data.get("hemisphere_history", [])

            # Self-Correction Loop laden
            from gateway.self_correction_loop import get_correction_loop
            correction = get_correction_loop()

            # Prompt verfeinern
            enriched_prompt = f"Stilvorgabe: {style}\nAufgabe: {prompt}"

            # Prozess starten
            result = correction.process(
                prompt=enriched_prompt,
                task_type="creative", 
                context=context
            )

            reply_text = result.get("response", "")
            
            return {
                "reply": reply_text,
                "success": True,
                "model_used": result.get("model_used", "multi-model-ensemble"),
                "score": result.get("best_score", 0.0),
                "iterations": result.get("iterations_used", 0)
            }
    
    def _get_system_prompt(self):
        """Holt den System-Prompt aus dem Memory"""
        try:
            from gateway.http_api import chat_memory
            return chat_memory.get_system_prompt()
        except:
            return "Du bist GABIs rechte, kreative Gehirnhälfte. Du bist kreativ, einfühlsam und sprachgewandt."
    
    def health_check(self) -> bool:
        """Prüft ob rechte Hemisphäre funktioniert"""
        try:
            # Prüfe Ollama
            from gateway.ollama_client import ollama_client
            ollama_client.list_models()
            return True
        except:
            return False