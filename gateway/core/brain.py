# gateway/core/brain.py
"""Corpus Callosum - Die Brücke zwischen den Hemisphären."""

import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class LeftHemisphere:
    """Linke Hemisphäre - Analytisch, logisch, präzise."""
    
    def __init__(self):
        self.name = "Left Hemisphere"
        self.capabilities = ["logic", "analysis", "code", "math", "shell"]
        
    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verarbeitet eine Aufgabe mit der linken Hemisphäre.
        
        Args:
            task: Aufgabe mit Inhalt und Typ
            
        Returns:
            Verarbeitungsergebnis
        """
        content = task.get("content", "")
        task_type = task.get("type", "auto")
        request_id = task.get("request_id")
        
        logger.info(f"🧠 Linke Hemisphäre verarbeitet: {content[:50]}... (Typ: {task_type})")
        
        # Je nach Aufgabentyp unterschiedlich verarbeiten
        if task_type == "shell":
            return {
                "success": True,
                "hemisphere": "left",
                "response": f"[Linke Hemisphäre] Shell-Befehl erkannt: {content}",
                "task_type": "shell"
            }
        elif task_type == "code":
            return {
                "success": True,
                "hemisphere": "left",
                "response": f"[Linke Hemisphäre] Code-Anfrage erkannt: {content}",
                "task_type": "code"
            }
        elif task_type == "analysis":
            return {
                "success": True,
                "hemisphere": "left",
                "response": f"[Linke Hemisphäre] Analyse-Anfrage erkannt: {content}",
                "task_type": "analysis"
            }
        else:
            return {
                "success": False,
                "hemisphere": "left",
                "error": f"Unbekannter Aufgabentyp: {task_type}",
                "task_type": task_type
            }


class RightHemisphere:
    """Rechte Hemisphäre - Kreativ, intuitiv, kontextuell."""
    
    def __init__(self):
        self.name = "Right Hemisphere"
        self.capabilities = ["creativity", "context", "vision", "audio", "chat"]
        
    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verarbeitet eine Aufgabe mit der rechten Hemisphäre.
        
        Args:
            task: Aufgabe mit Inhalt und Typ
            
        Returns:
            Verarbeitungsergebnis
        """
        content = task.get("content", "")
        task_type = task.get("type", "auto")
        request_id = task.get("request_id")
        
        logger.info(f"🧠 Rechte Hemisphäre verarbeitet: {content[:50]}... (Typ: {task_type})")
        
        # Je nach Aufgabentyp unterschiedlich verarbeiten
        if task_type == "search":
            return {
                "success": True,
                "hemisphere": "right",
                "response": f"[Rechte Hemisphäre] Such-Anfrage erkannt: {content}",
                "task_type": "search"
            }
        elif task_type == "vision":
            return {
                "success": True,
                "hemisphere": "right",
                "response": f"[Rechte Hemisphäre] Vision-Anfrage erkannt: {content}",
                "task_type": "vision"
            }
        elif task_type == "creative":
            return {
                "success": True,
                "hemisphere": "right",
                "response": f"[Rechte Hemisphäre] Kreative Anfrage erkannt: {content}",
                "task_type": "creative"
            }
        elif task_type == "chat":
            return {
                "success": True,
                "hemisphere": "right",
                "response": f"[Rechte Hemisphäre] Chat-Anfrage erkannt: {content}",
                "task_type": "chat"
            }
        else:
            return {
                "success": False,
                "hemisphere": "right",
                "error": f"Unbekannter Aufgabentyp: {task_type}",
                "task_type": task_type
            }


class CorpusCallosum:
    """
    Corpus Callosum - Die Brücke zwischen den Hemisphären.
    Entscheidet welche Hemisphäre für welche Aufgabe zuständig ist.
    """
    
    def __init__(self):
        self.left = None
        self.right = None
        self._initialized = False
        
        # Intent-Mapping für Routing
        self.intent_mapping = {
            # Linke Hemisphäre (analytisch)
            "shell": "left",
            "code": "left",
            "system": "left",
            "system_analysis": "left",
            "math": "left",
            "analysis": "left",
            
            # Rechte Hemisphäre (kreativ)
            "search": "right",
            "som_search": "right",
            "som_navigate": "right",
            "som_learned": "right",
            "som_stats": "right",
            "som_answer": "right",
            "vision": "right",
            "creative": "right",
            "chat": "right",
            "definition": "right",
            "gmail": "right",
            "calendar": "right",
            "telegram": "right",
            
            # Bridge (beide Hemisphären)
            "general": "bridge",
            "auto": "bridge"
        }
        
    def initialize_hemispheres(self) -> None:
        """Initialisiert die beiden Hemisphären."""
        if not self._initialized:
            self.left = LeftHemisphere()
            self.right = RightHemisphere()
            self._initialized = True
            logger.info("🧠 Corpus Callosum: Hemisphären initialisiert")
    
    def detect_task_type(self, content: str, intent_result: Optional[Dict[str, Any]] = None) -> str:
        """
        Erkennt den Aufgabentyp basierend auf Inhalt und Intent.
        
        Args:
            content: Der Nachrichteninhalt
            intent_result: Optionales Intent-Erkennungs-Ergebnis
            
        Returns:
            Erkannte Aufgabentyp
        """
        content_lower = content.lower()
        
        # Wenn Intent-Ergebnis vorhanden, verwende es
        if intent_result and intent_result.get("intent"):
            intent = intent_result.get("intent", "")
            confidence = intent_result.get("confidence", 0)
            
            if confidence > 0.6:
                # Map Intent zu Task-Typ
                if intent in ["shell", "code"]:
                    return intent
                elif intent in ["system", "system_analysis"]:
                    return "analysis"
                elif intent in ["search", "som_search"]:
                    return "search"
                elif intent in ["vision"]:
                    return "vision"
                elif intent in ["creative"]:
                    return "creative"
                elif intent in ["som_navigate"]:
                    return "navigation"
                elif intent in ["som_answer", "som_learned", "som_stats"]:
                    return "memory"
                elif intent in ["chat"]:
                    return "chat"
                elif intent in ["gmail", "calendar", "telegram"]:
                    return "integration"
        
        # Keyword-basierte Erkennung (Fallback)
        # Shell/Code
        if any(word in content_lower for word in ["/shell", "/cmd", "/bash", "befehl", "ausführen"]):
            return "shell"
        if any(word in content_lower for word in ["code", "python", "html", "skript", "programm"]):
            return "code"
        
        # Analyse
        if any(word in content_lower for word in ["analyse", "system", "status", "cpu", "memory", "prozess"]):
            return "analysis"
        
        # Suche
        if any(word in content_lower for word in ["suche", "google", "recherche", "finde", "information"]):
            return "search"
        
        # Vision
        if any(word in content_lower for word in ["webcam", "bild", "foto", "screenshot", "siehst du"]):
            return "vision"
        
        # Kreativ
        if any(word in content_lower for word in ["gedicht", "geschichte", "kreativ", "erzähl"]):
            return "creative"
        
        # Navigation
        if any(word in content_lower for word in ["gehe zu", "öffne", "navigiere", "goto"]):
            return "navigation"
        
        # Standard: Chat
        return "chat"
    
    def route_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Routet eine Aufgabe an die passende Hemisphäre.
        
        Args:
            task: Aufgabe mit content, type und optional context
            
        Returns:
            Routing-Ergebnis mit Hemisphäre und evtl. Antwort
        """
        content = task.get("content", "")
        task_type = task.get("type", "auto")
        intent_result = task.get("intent_result")
        request_id = task.get("request_id")
        
        if not self._initialized:
            self.initialize_hemispheres()
        
        # Erkenne Task-Typ falls nicht angegeben
        if task_type == "auto" or not task_type:
            task_type = self.detect_task_type(content, intent_result)
        
        # Bestimme Ziel-Hemisphäre
        hemisphere = self.intent_mapping.get(task_type, "bridge")
        
        # Bei Bridge: Beide Hemisphären arbeiten zusammen
        if hemisphere == "bridge":
            return {
                "success": True,
                "hemisphere": "bridge",
                "detected_type": task_type,
                "message": "Bridge-Modus: Beide Hemisphären arbeiten zusammen",
                "task_type": task_type
            }
        
        # Bei bestimmter Hemisphäre
        if hemisphere == "left" and self.left:
            return {
                "success": True,
                "hemisphere": "left",
                "detected_type": task_type,
                "task_type": task_type
            }
        elif hemisphere == "right" and self.right:
            return {
                "success": True,
                "hemisphere": "right",
                "detected_type": task_type,
                "task_type": task_type
            }
        else:
            # Fallback
            return {
                "success": True,
                "hemisphere": "bridge",
                "detected_type": task_type,
                "task_type": task_type,
                "warning": f"Hemisphäre {hemisphere} nicht initialisiert"
            }
    
    async def process_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Verarbeitet eine Aufgabe mit der entsprechenden Hemisphäre.
        
        Args:
            task: Aufgabe mit Inhalt und Typ
            
        Returns:
            Verarbeitungsergebnis
        """
        if not self._initialized:
            self.initialize_hemispheres()
        
        # Route die Aufgabe
        route = self.route_task(task)
        hemisphere = route.get("hemisphere")
        task_type = route.get("task_type", "auto")
        
        # Bridge-Modus: Beide Hemisphären
        if hemisphere == "bridge":
            # Linke Hemisphäre für Analyse, rechte für Kontext
            left_task = {**task, "type": "analysis"}
            right_task = {**task, "type": "chat"}
            
            left_result = await self.left.process(left_task) if self.left else None
            right_result = await self.right.process(right_task) if self.right else None
            
            return {
                "success": True,
                "hemisphere": "bridge",
                "detected_type": task_type,
                "left_result": left_result,
                "right_result": right_result,
                "combined": f"{left_result.get('response', '') if left_result else ''}\n\n{right_result.get('response', '') if right_result else ''}".strip()
            }
        
        # Linke Hemisphäre
        elif hemisphere == "left" and self.left:
            result = await self.left.process(task)
            return {
                **result,
                "detected_type": task_type,
                "hemisphere": "left"
            }
        
        # Rechte Hemisphäre
        elif hemisphere == "right" and self.right:
            result = await self.right.process(task)
            return {
                **result,
                "detected_type": task_type,
                "hemisphere": "right"
            }
        
        # Fallback
        return {
            "success": False,
            "error": f"Keine Hemisphäre für Typ {task_type} verfügbar",
            "detected_type": task_type,
            "hemisphere": "none"
        }
    
    def get_status(self) -> Dict[str, Any]:
        """
        Gibt den Status beider Hemisphären zurück.
        
        Returns:
            Status-Dict mit Informationen über beide Hemisphären
        """
        return {
            "initialized": self._initialized,
            "left": {
                "available": self.left is not None,
                "name": self.left.name if self.left else None,
                "capabilities": self.left.capabilities if self.left else []
            },
            "right": {
                "available": self.right is not None,
                "name": self.right.name if self.right else None,
                "capabilities": self.right.capabilities if self.right else []
            },
            "intent_mapping": self.intent_mapping,
            "timestamp": datetime.now().isoformat()
        }
    
    def set_hemisphere_mode(self, mode: str) -> Dict[str, Any]:
        """
        Setzt den Modus für die Hemisphären (für Tests).
        
        Args:
            mode: "left", "right", "auto", "bridge"
            
        Returns:
            Ergebnis der Konfiguration
        """
        if mode not in ["left", "right", "auto", "bridge"]:
            return {"success": False, "error": f"Ungültiger Modus: {mode}"}
        
        # Temporär die Mapping-Strategie ändern
        # Hier könnte eine globale Einstellung gespeichert werden
        logger.info(f"🔄 Hemisphären-Modus geändert: {mode}")
        
        return {
            "success": True,
            "mode": mode,
            "message": f"Hemisphären-Modus auf '{mode}' gesetzt"
        }


# Globale Instanz
_brain: Optional[CorpusCallosum] = None


def get_brain() -> CorpusCallosum:
    """
    Singleton für das Gehirn.
    
    Returns:
        Die globale Brain-Instanz
    """
    global _brain
    if _brain is None:
        _brain = CorpusCallosum()
    return _brain


def reset_brain() -> CorpusCallosum:
    """
    Setzt das Gehirn zurück und erstellt eine neue Instanz.
    
    Returns:
        Neue Brain-Instanz
    """
    global _brain
    _brain = CorpusCallosum()
    _brain.initialize_hemispheres()
    logger.info("🧠 Brain wurde zurückgesetzt")
    return _brain


# ===== ERWEITERTE HEMISPHÄREN-FUNKTIONEN =====

class EnhancedLeftHemisphere(LeftHemisphere):
    """Erweiterte linke Hemisphäre mit mehr Fähigkeiten."""
    
    def __init__(self):
        super().__init__()
        self.capabilities.extend(["database", "api", "system"])
        
    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Erweiterte Verarbeitung mit mehr Kontext."""
        content = task.get("content", "")
        context = task.get("context", [])
        
        # Basis-Verarbeitung
        result = await super().process(task)
        
        # Wenn Code-Aufgabe, füge mehr Details hinzu
        if task.get("type") == "code":
            result["code_context"] = self._extract_code_context(content, context)
        
        return result
    
    def _extract_code_context(self, content: str, context: List) -> str:
        """Extrahiert Code-Kontext aus der Anfrage."""
        # Hier könnte eine komplexere Code-Analyse stehen
        if "python" in content.lower():
            return "Python-Code-Kontext erkannt"
        elif "html" in content.lower():
            return "HTML/CSS-Kontext erkannt"
        return "Allgemeiner Code-Kontext"


class EnhancedRightHemisphere(RightHemisphere):
    """Erweiterte rechte Hemisphäre mit mehr Fähigkeiten."""
    
    def __init__(self):
        super().__init__()
        self.capabilities.extend(["emotion", "context", "memory"])
        
    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Erweiterte Verarbeitung mit mehr Kontext."""
        content = task.get("content", "")
        context = task.get("context", [])
        
        # Basis-Verarbeitung
        result = await super().process(task)
        
        # Füge Kontext aus dem Verlauf hinzu
        if context:
            result["context_used"] = len(context)
        
        # Erkenne emotionale Töne
        result["emotional_tone"] = self._detect_emotion(content)
        
        return result
    
    def _detect_emotion(self, content: str) -> str:
        """Erkennt emotionale Töne in der Nachricht."""
        content_lower = content.lower()
        
        if any(word in content_lower for word in ["danke", "super", "toll", "großartig"]):
            return "positiv"
        elif any(word in content_lower for word in ["fehler", "problem", "kaputt", "schlecht"]):
            return "negativ"
        elif any(word in content_lower for word in ["?", "warum", "wie", "was"]):
            return "neugierig"
        elif any(word in content_lower for word in ["!", "wichtig", "dringend"]):
            return "dringend"
        
        return "neutral"


def get_enhanced_brain(use_enhanced: bool = True) -> CorpusCallosum:
    """
    Gibt das Gehirn zurück, optional mit erweiterten Hemisphären.
    
    Args:
        use_enhanced: Ob erweiterte Hemisphären verwendet werden sollen
        
    Returns:
        Brain-Instanz
    """
    brain = get_brain()
    
    if use_enhanced:
        # Ersetze mit erweiterten Hemisphären
        brain.left = EnhancedLeftHemisphere()
        brain.right = EnhancedRightHemisphere()
        brain._initialized = True
        logger.info("🧠 Erweiterte Hemisphären aktiviert")
    
    return brain