# brain_left.py - GABIs linke Gehirnhälfte (analytisch, logisch, Code)
"""
🧠 GABI Left Hemisphere - Logic & Code Processing
Zuständig für: Shell-Befehle, Code-Generierung, Berechnungen, System-Analyse
"""

import logging
from typing import Dict, Any, Optional
import subprocess
import re

logger = logging.getLogger("GABI.brain_left")

class LeftHemisphere:
    """Die linke, analytische Gehirnhälfte von GABI"""
    
    def __init__(self):
        self.name = "🧠 GABI Left (Analytical)"
        self.specialties = ["code", "shell", "math", "system", "logic", "search", "analysis"]
        # FIX: Verwende default_model aus Config statt hartcodiert
        from config import config
        self.active_model = config.get("ollama.default_model", "llama2:latest")
        logger.info(f"🔵 {self.name} initialisiert mit Modell: {self.active_model}")
    
    def process(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Verarbeitet Input mit der linken Hemisphäre"""
        task_type = input_data.get("type", "unknown")

        if task_type == "shell":
            return self._handle_shell(input_data)
        elif task_type == "code":
            return self._handle_code(input_data)
        elif task_type == "analysis":
            return self._handle_analysis(input_data)
        elif task_type == "search":
            return self._handle_search(input_data)
        else:
            # Fallback: Bridge entscheidet
            return {"success": False, "error": "Nicht für linke Hemisphäre geeignet"}

    def _handle_search(self, data):
        """Web-Suche ausführen"""
        import asyncio
        from gateway.integrations.shell_executor import shell_executor
        content = data.get("content", "")

        # Extrahiere Suchbegriff
        search_triggers = ["suche nach", "such nach", "finde heraus", "recherchiere",
            "google mal", "such mal", "was ist", "wer ist", "informationen über",
            "infos zu", "news zu", "artikel über", "erzähl mir von", "was bedeutet",
            "wie funktioniert", "erkläre mir"]

        search_term = content
        for trigger in search_triggers:
            if trigger in content.lower():
                search_term = content.lower().split(trigger)[-1].strip()
                break

        if not search_term:
            search_term = content

        # Führe Web-Suche aus
        safe_term = search_term.replace('"', "'")
        cmd = f'python tools/web_search.py "{safe_term}"'

        logger.info(f"🔍 Führe Web-Suche aus: {search_term}")

        try:
            result = shell_executor.execute(cmd)
            if result.get("success"):
                reply = result.get("stdout", "") or "Keine Suchergebnisse"
            else:
                reply = f"Fehler bei der Suche: {result.get('stderr', 'Unbekannt')}"
        except Exception as e:
            reply = f"Fehler: {str(e)}"

        return {
            "reply": reply,
            "success": True,
            "tool_used": "web_search"
        }
    
    def _handle_shell(self, data):
        """Shell-Befehle ausführen"""
        from gateway.integrations.shell_executor import shell_executor
        # Unterstütze sowohl "command" als auch "content"
        cmd = data.get("command") or data.get("content", "")
        result = shell_executor.execute(cmd)
        # Erstelle reply aus stdout/stderr
        if result.get("success"):
            reply = result.get("stdout", "") or "Befehl ausgeführt"
        else:
            reply = f"Fehler: {result.get('stderr', result.get('stdout', 'Unbekannt'))}"
        return {
            "reply": reply,
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "success": result.get("success", True)
        }
    
    def _handle_code(self, data):
        """Analytische Aufgaben: Code-Generierung & Logik mit korrektem Modell"""
        prompt = data.get("prompt") or data.get("content", "")
        context = data.get("context", []) or data.get("hemisphere_history", [])
        
        # FIX: Verwende Code-spezifisches Modell aus Config, nicht hartcodiert
        from config import config
        preferred_code_models = config.get("ollama.preferred_code_models", [])
        if preferred_code_models and isinstance(preferred_code_models, list):
            code_model = preferred_code_models[0]  # Nimm das erste bevorzugte Code-Modell
        else:
            code_model = self.active_model  # Fallback auf default model
        
        # Verwendung des Self-Correction Loops
        from gateway.self_correction_loop import get_correction_loop
        correction = get_correction_loop()
        
        # Explizit das Code-Modell übergeben
        result = correction.process(
            prompt=prompt,
            task_type="code",
            context=context,
            model_hint=code_model  # Falls self_correction_loop das unterstützt
        )
        
        # Fallback: Wenn correction keinen Erfolg hatte, direkt mit Code-Modell generieren
        if not result.get("success", False):
            from gateway.ollama_client import ollama_client
            response = ollama_client.chat(
                model=code_model,
                messages=[{"role": "user", "content": prompt}]
            )
            reply_text = response.get("message", {}).get("content", "")
            return {
                "reply": reply_text,
                "response": reply_text,
                "success": True,
                "model_used": code_model,
                "correction_score": 0.0,
                "iterations": 0
            }

        reply_text = result.get("response", "")
        
        return {
            "reply": reply_text,
            "response": reply_text,
            "success": True,
            "model_used": result.get("model_used", code_model),
            "correction_score": result.get("best_score", 0.0),
            "iterations": result.get("iterations_used", 0)
        }
        
    def _handle_analysis(self, data):
        """System-Analyse"""
        import psutil
        import platform
        
        return {
            "cpu": psutil.cpu_percent(),
            "memory": psutil.virtual_memory()._asdict(),
            "disk": psutil.disk_usage('/')._asdict(),
            "os": platform.system(),
            "hostname": platform.node()
        }
    
    def health_check(self) -> bool:
        """Prüft ob linke Hemisphäre funktioniert"""
        try:
            # Prüfe Shell-Zugriff
            subprocess.run(["echo", "test"], capture_output=True, timeout=2)
            return True
        except:
            return False