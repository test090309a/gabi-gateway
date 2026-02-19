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
        self.specialties = ["code", "shell", "math", "system", "logic"]
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
        else:
            # Fallback: Bridge entscheidet
            return {"success": False, "error": "Nicht für linke Hemisphäre geeignet"}
    
    def _handle_shell(self, data):
        """Shell-Befehle ausführen"""
        from integrations.shell_executor import shell_executor
        # Unterstütze sowohl "command" als auch "content"
        cmd = data.get("command") or data.get("content", "")
        return shell_executor.execute(cmd)
    
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
        return {"result": response}
    
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