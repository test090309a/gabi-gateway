# corpus_callosum.py - GABIs Verbindung zwischen den Hemisphären
"""
🧩 GABI Corpus Callosum - Die Brücke zwischen den Gehirnhälften
Koordiniert Aufgaben, entscheidet welche Hemisphäre zuständig ist
mit GETRENNTEN Verläufen für jede Hemisphäre!
"""

import logging
import re
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger("GABI.corpus_callosum")

class CorpusCallosum:
    """Die Brücke zwischen GABIs linker und rechter Gehirnhälfte"""
    
    def __init__(self):
        self.name = "🧩 GABI Bridge"
        self.left = None
        self.right = None
        self.initialized = False
        
        # GETRENNTE Verläufe pro Hemisphäre!
        self.left_history = []   # Nur Nachrichten, die von linker Hemisphäre verarbeitet wurden
        self.right_history = []  # Nur Nachrichten, die von rechter Hemisphäre verarbeitet wurden
        self.max_history_per_hemisphere = 10  # Maximale Anzahl Nachrichten pro Hemisphäre
        
        logger.info(f"{self.name} initialisiert")
    
    def initialize_hemispheres(self):
        """Initialisiert beide Gehirnhälften"""
        if self.initialized:
            return
        
        try:
            # Korrekte Imports mit gateway-Prefix
            from gateway.brain_left import LeftHemisphere
            from gateway.brain_right import RightHemisphere
            
            self.left = LeftHemisphere()
            self.right = RightHemisphere()
            self.initialized = True
            logger.info(f"✅ Beide Hemisphären aktiv: {self.left.name} | {self.right.name}")
            logger.info(f"   Linke Hemisphäre: {', '.join(self.left.specialties)}")
            logger.info(f"   Rechte Hemisphäre: {', '.join(self.right.specialties)}")
        except ImportError as e:
            logger.error(f"❌ Import-Fehler: {e}")
            logger.error("   Stelle sicher, dass brain_left.py und brain_right.py im gateway/ Ordner sind")
        except Exception as e:
            logger.error(f"❌ Hemisphären-Initialisierung fehlgeschlagen: {e}")
    
    def route_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Leitet eine Aufgabe an die passende Hemisphäre weiter mit GETRENNTEM Verlauf
        """
        self.initialize_hemispheres()
        
        content = task.get("content", "")
        content_lower = content.lower()
        task_type = task.get("type", "auto")
        explicit_type = task.get("type", "auto")
        request_id = task.get("request_id", "unknown")
        global_context = task.get("context", [])

        # ===== NEU: PRÜFE AUF DEFINITIONS-ANFRAGEN (höchste Priorität) =====
        definition_indicators = [
            "definition", "was ist", "was bedeutet", "erkläre mir", "erkläre",
            "wissenschaftliche basis", "wissenschaftlich", "set of mark",
            "definiere", "beschreibe", "was heißt", "was meint",
            "architektur beschreibung", "architektur und system",
            "bedeutung von", "was versteht man unter"
        ]
        
        is_definition = any(ind in content_lower for ind in definition_indicators)
        
        # Wissenschaftliche/akademische Anfragen
        academic_indicators = [
            "wissenschaftliche", "akademische", "theoretische", "grundlagen",
            "konzept", "theorie", "prinzip", "methodik"
        ]
        is_academic = any(ind in content_lower for ind in academic_indicators)
        
        # DEFINITIONS-ANFRAGEN GEHEN DIREKT AN DIE RECHTE HEMISPHÄRE (Chat/LLM)
        if is_definition or is_academic:
            logger.info(f"📚 Definitions-/Wissenschaftsanfrage -> rechte Hemisphäre: {content[:60]}...")
            # Erstelle einen Task für die rechte Hemisphäre
            task_copy = task.copy()
            task_copy["type"] = "chat"
            task_copy["system_hint"] = "Du bist ein wissenschaftlicher Assistent. Gib eine präzise, wissenschaftlich fundierte Antwort."
            
            # Rechten Verlauf verwenden
            hemisphere_history = self.right_history[-self.max_history_per_hemisphere:]
            task_copy["hemisphere_history"] = hemisphere_history
            task_copy["global_context"] = global_context[-3:] if global_context else []
            
            start_time = datetime.now()
            result = self.right.process(task_copy)
            
            if result.get("success", True):
                self._add_to_history("right", content, result, request_id)
            
            result["hemisphere"] = "right"
            result["detected_type"] = "definition"
            result["processing_time_ms"] = int((datetime.now() - start_time).total_seconds() * 1000)
            result["hemisphere_history_size"] = len(hemisphere_history) + 1
            
            return result

        # ===== ERWEITERTE SHELL/COMMAND-ERKENNUNG =====
        # Programme/Commands ausführen (höchste Priorität nach Definitionen)
        command_indicators = [
            "führe", "starte", "öffne", "execute", "run", "start",
            "notepad", "rechner", "calc", "explorer", "cmd", "powershell",
            "chrome", "firefox", "edge", "vscode", "code"
        ]
        
        # Prüfe auf explizite Ausführungsbefehle
        is_execution = any(ind in content_lower for ind in command_indicators)
        
        # Prüfe auf Datei-Operationen (erweitert)
        file_indicators = [
            "zeig", "liste", "datei", "verzeichnis", "ordner", 
            "erstelle", "lösche", "kopiere", "verschiebe", "zeig mir",
            "welche dateien", "python dateien", "alle dateien",
            "*.md", "*.py", "*.txt"  # Wildcards
        ]
        
        is_file_operation = any(ind in content_lower for ind in file_indicators)
        
        # Prüfe auf Shell-Operatoren
        shell_operators = ["|", ">", ">>", "&&", "||"]
        has_shell_operator = any(op in content for op in shell_operators)
        
        # ===== SHELL/COMMAND-ERKENNUNG =====
        if is_execution or is_file_operation or has_shell_operator:
            logger.info(f"⚡ Shell/Command erkannt -> linke Hemisphäre: {content[:60]}...")
            return {
                "hemisphere": "left",
                "detected_type": "shell",
                "success": True,
                "reason": "Shell/Command-Operation erkannt",
                "is_execution": is_execution,
                "is_file_operation": is_file_operation,
                "has_shell_operator": has_shell_operator
            }

        # ===== WEITER MIT NORMALEM ROUTING (wie bisher) =====
        # 1. Typ erkennen
        detected_type = explicit_type
        if explicit_type == "auto":
            detected_type = self._detect_task_type(content)
        
        task["type"] = detected_type
        
        # 2. Richtigen Verlauf auswählen
        if detected_type in self.left.specialties:
            hemisphere = "left"
            hemisphere_history = self.left_history[-self.max_history_per_hemisphere:]
            logger.info(f"🧠 Routing: {detected_type} -> links (Verlauf: {len(hemisphere_history)} Nachrichten)")
        else:
            hemisphere = "right"
            hemisphere_history = self.right_history[-self.max_history_per_hemisphere:]
            logger.info(f"🧠 Routing: {detected_type} -> rechts (Verlauf: {len(hemisphere_history)} Nachrichten)")
        
        # 3. Task mit dem richtigen Verlauf anreichern
        task["hemisphere_history"] = hemisphere_history
        task["global_context"] = global_context[-3:] if global_context else []
        
        # 4. Verarbeiten durch die passende Hemisphäre
        start_time = datetime.now()
        
        if hemisphere == "left":
            result = self.left.process(task)
            if result.get("success", True):
                self._add_to_history("left", content, result, request_id)
        else:
            result = self.right.process(task)
            if result.get("success", True):
                self._add_to_history("right", content, result, request_id)
        
        # 5. Metadaten hinzufügen
        result["hemisphere"] = hemisphere
        result["detected_type"] = detected_type
        result["processing_time_ms"] = int((datetime.now() - start_time).total_seconds() * 1000)
        result["hemisphere_history_size"] = len(hemisphere_history) + 1
        
        return result
    
    def _add_to_history(self, hemisphere: str, user_content: str, result: Dict[str, Any], request_id: str):
        """
        Fügt eine Interaktion zum Verlauf der richtigen Hemisphäre hinzu
        
        Args:
            hemisphere: "left" oder "right"
            user_content: Die ursprüngliche Benutzer-Nachricht
            result: Das Verarbeitungsergebnis
            request_id: Für Tracking
        """
        timestamp = datetime.now().isoformat()
        
        # Extrahierte Antwort aus dem Resultat
        assistant_reply = ""
        if "reply" in result:
            assistant_reply = str(result["reply"]) if result["reply"] else ""
        elif "result" in result:
            assistant_reply = str(result["result"]) if result["result"] else ""
        elif "response" in result:
            assistant_reply = str(result["response"]) if result["response"] else ""
        elif "text" in result:
            assistant_reply = str(result["text"]) if result["text"] else ""
        else:
            assistant_reply = "(keine Text-Antwort)"
        
        # Eintrag für Benutzer-Nachricht
        user_entry = {
            "role": "user",
            "content": user_content[:500],  # Begrenzen auf 500 Zeichen
            "timestamp": timestamp,
            "request_id": request_id,
            "type": result.get("detected_type", "unknown")
        }
        
        # Eintrag für GABI-Antwort
        assistant_entry = {
            "role": "assistant",
            "content": assistant_reply[:1000],  # Begrenzen auf 1000 Zeichen
            "timestamp": datetime.now().isoformat(),
            "request_id": request_id,
            "hemisphere": hemisphere,
            "model_used": result.get("model_used", result.get("model", "unknown"))
        }
        
        # Zum richtigen Verlauf hinzufügen
        if hemisphere == "left":
            self.left_history.append(user_entry)
            self.left_history.append(assistant_entry)
            # Alte Einträge entfernen, wenn nötig
            if len(self.left_history) > self.max_history_per_hemisphere * 2:  # *2 wegen User+Assistant
                self.left_history = self.left_history[-(self.max_history_per_hemisphere * 2):]
            logger.debug(f"➕ Linker Verlauf: jetzt {len(self.left_history)//2} Unterhaltungen")
        else:
            self.right_history.append(user_entry)
            self.right_history.append(assistant_entry)
            if len(self.right_history) > self.max_history_per_hemisphere * 2:
                self.right_history = self.right_history[-(self.max_history_per_hemisphere * 2):]
            logger.debug(f"➕ Rechter Verlauf: jetzt {len(self.right_history)//2} Unterhaltungen")
    
    def _detect_task_type(self, content: str) -> str:
        """Erkennt den Typ einer Aufgabe anhand des Inhalts - verhindert false positives bei Definitionsfragen"""
        if not content:
            return "chat"

        content_lower = content.lower()

        # ===== PRIO 1: DEFINITIONS-ANFRAGEN (höchste Priorität!) =====
        definition_indicators = [
            "definition", "was ist", "was bedeutet", "erkläre mir", "erkläre",
            "wissenschaftliche basis", "wissenschaftlich", "set of mark",
            "definiere", "beschreibe", "was heißt", "was meint",
            "architektur beschreibung", "architektur und system",
            "bedeutung von", "was versteht man unter"
        ]
        
        is_definition = any(ind in content_lower for ind in definition_indicators)
        
        # Wissenschaftliche/akademische Anfragen (auch wenn nicht explizit "Definition")
        academic_indicators = [
            "wissenschaftliche", "akademische", "theoretische", "grundlagen",
            "konzept", "theorie", "prinzip", "methodik"
        ]
        is_academic = any(ind in content_lower for ind in academic_indicators)
        
        if is_definition or is_academic:
            logger.info(f"📚 Definitions-/Wissenschaftsanfrage erkannt: {content[:60]}...")
            return "chat"  # Geht an rechte Hemisphäre / LLM

        # ===== PRIO 2: EXPLIZITE SHELL-BEFEHLE =====
        if content.startswith('/shell') or content.startswith('shell'):
            return "shell"
        if any(word in content_lower for word in ["/shell", "cmd", "powershell", "bash", "ausführen"]):
            return "shell"
        
        # ===== PRIO 3: DATEI-/VERZEICHNIS-OPERATIONEN (nur bei expliziten Keywords) =====
        file_operation_keywords = [
            "zeig dateien", "list dateien", "erstelle datei", "lösche datei",
            "kopiere datei", "verschiebe datei", "datei erstellen", "datei löschen",
            "zeig mir dateien", "welche dateien", "alle python dateien",
            "verzeichnis anzeigen", "ordner anzeigen", "dir", "ls -la"
        ]
        
        is_file_operation = any(kw in content_lower for kw in file_operation_keywords)
        if is_file_operation:
            return "shell"
        
        # ===== PRIO 4: CODE/PROGRAMMIERUNG (nur bei eindeutigen Keywords) =====
        code_keywords = [
            "schreib code", "programmiere", "python script", "html generieren",
            "funktion schreiben", "klasse erstellen", "implementiere",
            "code generieren", "skript schreiben"
        ]
        if any(keyword in content_lower for keyword in code_keywords):
            return "code"
        
        # ===== PRIO 5: WEB-SUCHE (nur bei expliziten Such-Keywords) =====
        search_triggers = [
            "suche nach", "such nach", "finde heraus", "recherchiere",
            "google mal", "such mal", "infos zu", "news zu", "artikel über"
        ]
        if any(trigger in content_lower for trigger in search_triggers):
            return "search"
        
        # ===== PRIO 6: SYSTEM-ANALYSE (NUR bei sehr spezifischen Keywords!) =====
        # Wichtig: Einzelnes "system" oder "analyse" triggert NICHT mehr!
        system_analysis_keywords = [
            "systemanalyse", "system analyse", "systemstatus", "system status",
            "zeig systeminfo", "cpu auslastung", "ram auslastung", "hardware auslastung",
            "systemauslastung", "system info", "tasklist anzeigen", "prozesse anzeigen"
        ]
        if any(keyword in content_lower for keyword in system_analysis_keywords):
            return "analysis"
        
        # ===== PRIO 7: MATHEMATIK (einfache Rechnungen) =====
        # Nur einfache Rechnungen, keine Definitionen mit Zahlen
        if re.match(r'^\s*[\d\s\+\-\*\/\(\)]+\s*=\s*\?*\s*$', content_lower):
            return "analysis"
        
        # ===== PRIO 8: VISION/BILD (nur bei expliziten Keywords) =====
        vision_keywords = [
            "was siehst du", "webcam", "bild analysieren", "foto machen",
            "kamera", "screenshot machen", "nimm ein foto"
        ]
        if any(keyword in content_lower for keyword in vision_keywords):
            return "vision"
        
        # ===== PRIO 9: AUDIO/SPRACHE =====
        audio_keywords = ["audio", "hör", "sound", "whisper", "mikrofon", "sprachaufnahme"]
        if any(keyword in content_lower for keyword in audio_keywords):
            return "audio"
        
        # ===== PRIO 10: KREATIV =====
        creative_keywords = [
            "erzähl geschichte", "gedicht", "kreative idee",
            "schreib ein gedicht", "erzähl mir eine geschichte"
        ]
        if any(keyword in content_lower for keyword in creative_keywords):
            return "creative"
        
        # ===== DEFAULT: CHAT (rechte Hemisphäre / LLM) =====
        return "chat"
    
    def process_multimodal(self, inputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Verarbeitet multimodale Eingaben (z.B. Bild + Text)
        
        Beispiel:
        inputs = [
            {"type": "vision", "data": webcam_frame, "content": "Was siehst du?"},
            {"type": "audio", "data": audio_file, "content": "Transkribiere das"}
        ]
        """
        self.initialize_hemispheres()
        
        results = []
        for inp in inputs:
            # Stelle sicher, dass jeder Input ein "content" Feld hat
            if "content" not in inp:
                inp["content"] = inp.get("data", str(inp))
            
            result = self.route_task(inp)
            results.append(result)
        
        # Integriere Ergebnisse
        return self._integrate_results(results)
    
    def _integrate_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Integriert Ergebnisse mehrerer Hemisphären"""
        combined = {
            "success": all(r.get("success", True) for r in results),
            "timestamp": datetime.now().isoformat(),
            "responses": results,
            "hemispheres_used": list(set(r.get("hemisphere", "unknown") for r in results))
        }
        
        # Extrahiere Text für einfache Antworten
        texts = []
        for r in results:
            if "reply" in r:
                texts.append(r["reply"])
            elif "result" in r:
                texts.append(str(r["result"]))
            elif "response" in r:
                texts.append(r["response"])
            elif "text" in r:
                texts.append(r["text"])
        
        if texts:
            combined["combined_response"] = "\n\n---\n\n".join(texts)
        
        return combined
    
    def get_status(self) -> Dict[str, Any]:
        """Gibt Status beider Hemisphären zurück"""
        self.initialize_hemispheres()
        
        # Letzte Nachrichten für Debugging
        last_left = self.left_history[-2:] if self.left_history else []
        last_right = self.right_history[-2:] if self.right_history else []
        
        return {
            "left": {
                "active": self.left is not None,
                "health": self.left.health_check() if self.left and hasattr(self.left, 'health_check') else False,
                "specialties": self.left.specialties if self.left else [],
                "history_size": len(self.left_history) // 2,
                "last_interactions": [
                    {
                        "time": msg.get("timestamp", "unknown"),
                        "content": msg.get("content", "")[:50] + "..."
                    }
                    for msg in last_left if msg.get("role") == "user"
                ]
            },
            "right": {
                "active": self.right is not None,
                "health": self.right.health_check() if self.right and hasattr(self.right, 'health_check') else False,
                "specialties": self.right.specialties if self.right else [],
                "history_size": len(self.right_history) // 2,
                "last_interactions": [
                    {
                        "time": msg.get("timestamp", "unknown"),
                        "content": msg.get("content", "")[:50] + "..."
                    }
                    for msg in last_right if msg.get("role") == "user"
                ]
            },
            "bridge_active": self.initialized,
            "timestamp": datetime.now().isoformat()
        }
    
    def clear_histories(self, hemisphere: Optional[str] = None):
        """
        Löscht die Verläufe einer oder beider Hemisphären
        
        Args:
            hemisphere: "left", "right" oder None (beide)
        """
        if hemisphere == "left" or hemisphere is None:
            self.left_history = []
            logger.info("🧹 Linker Verlauf gelöscht")
        
        if hemisphere == "right" or hemisphere is None:
            self.right_history = []
            logger.info("🧹 Rechter Verlauf gelöscht")
        
        if hemisphere is None:
            logger.info("🧹 Alle Hemisphären-Verläufe gelöscht")


# Singleton-Instanz
_callosum: Optional[CorpusCallosum] = None

def get_brain() -> CorpusCallosum:
    """Gibt die Singleton-Instanz von GABIs Gehirn zurück"""
    global _callosum
    if _callosum is None:
        _callosum = CorpusCallosum()
    return _callosum


# Convenience-Funktionen für einfachen Zugriff
def route_task(task: Dict[str, Any]) -> Dict[str, Any]:
    """Leitet eine Aufgabe an GABIs Gehirn weiter"""
    return get_brain().route_task(task)

def get_brain_status() -> Dict[str, Any]:
    """Gibt Status beider Hemisphären zurück"""
    return get_brain().get_status()

def clear_brain_history(hemisphere: Optional[str] = None):
    """Löscht die Verläufe"""
    get_brain().clear_histories(hemisphere)