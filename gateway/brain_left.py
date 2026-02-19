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
        self.active_model = "codellama"  # Bevorzugt Code-Modelle
        logger.info(f"🔵 {self.name} initialisiert")
    
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
        from integrations.shell_executor import shell_executor
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
        from integrations.shell_executor import shell_executor
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
        """Code-Generierung und -Analyse"""
        # Unterstütze sowohl "prompt" als auch "content" (für Corpus Callosum)
        prompt = data.get("prompt") or data.get("content", "")
        # Verwende Code-spezifisches Modell
        from gateway.ollama_client import ollama_client
        response = ollama_client.chat(
            model="codellama",  # Speziell für Code
            messages=[{"role": "user", "content": prompt}]
        )
        reply_text = response.get("message", {}).get("content", "") if isinstance(response, dict) else str(response)
        return {"reply": reply_text, "response": reply_text, "success": True, "model_used": "codellama"}
    
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