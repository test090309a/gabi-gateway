# gateway/core/router.py
"""Intent-Erkennung, Model-Routing und semantische Klassifizierung."""

import re
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

from gateway.config import config
from gateway.utils.model_helpers import (
    _extract_model_score,
    _pick_best_model,
    _pick_fast_model,
    _pick_preferred_available,
    _as_model_pref_list,
    _infer_model_capabilities
)

logger = logging.getLogger(__name__)

# Globale Instanz für semantische Intent-Erkennung
_semantic_intent = None

# Standard-Modell aus der Config
DEFAULT_MODEL = config.get("ollama.default_model", "llama2:latest")


def get_semantic_intent():
    """Singleton für semantische Intent-Erkennung."""
    global _semantic_intent
    if _semantic_intent is None:
        # from gateway.integrations.semantic_memory import SemanticMemory
        from gateway.integrations.semantic_memory import SemanticMemory
        _semantic_intent = SemanticMemory()
        _init_intent_examples(_semantic_intent)
    return _semantic_intent


def _init_intent_examples(semantic) -> None:
    """Initialisiert die Intent-Beispiele im semantischen Speicher."""
    intents = {
        # ===== EXISTIERENDE INTENTS =====
        "gmail": [
            "zeig mir meine emails",
            "posteingang anzeigen",
            "welche mails habe ich",
            "neue nachrichten",
            "inbox anzeigen",
            "zeig meine gmails",
            "email posteingang",
            "hatte ich neue mails",
            "zeig mir die neuesten emails",
            "gmail posteingang",
            "zeig ungelesene mails",
            "mail von heute"
        ],
        
        "calendar": [
            "zeig mir meine termine",
            "kalender anzeigen",
            "was habe ich heute vor",
            "nächste termine",
            "kalendereinträge",
            "mein tagesplan",
            "wochenkalender",
            "termine morgen",
            "was steht an"
        ],
        
        "definition": [
            "was ist ein",
            "erkläre mir",
            "definiere",
            "bedeutung von",
            "wissenschaftliche grundlagen",
            "was bedeutet",
            "beschreibe",
            "was versteht man unter",
            "set of mark prompting",
            "architektur beschreibung",
            "was heißt",
            "was meint"
        ],
        
        "system_analysis": [
            "systemanalyse",
            "systemstatus anzeigen",
            "cpu auslastung",
            "ram auslastung",
            "wie ist die systemauslastung",
            "tasklist anzeigen",
            "prozesse anzeigen",
            "systeminfo",
            "hardware auslastung",
            "system monitor",
            "ressourcen anzeigen",
            "leistung"
        ],
        
        "shell": [
            "zeig dateien",
            "liste dateien",
            "erstelle datei",
            "lösche datei",
            "verzeichnis anzeigen",
            "ordner anzeigen",
            "python dateien",
            "welche dateien",
            "zeig mir alle txt dateien",
            "aktuelles verzeichnis",
            "wo bin ich"
        ],
        
        "code": [
            "schreib code",
            "programmiere",
            "python script",
            "funktion schreiben",
            "html generieren",
            "implementiere",
            "erstelle ein skript",
            "code generieren",
            "programmieren"
        ],
        
        "vision": [
            "was siehst du",
            "webcam",
            "bild analysieren",
            "foto machen",
            "kamera",
            "screenshot",
            "mach ein foto",
            "was erkennst du",
            "webcam foto"
        ],
        
        "creative": [
            "erzähl geschichte",
            "gedicht",
            "kreative idee",
            "schreib ein gedicht",
            "erzähl mir was",
            "lustige idee"
        ],
        
        # ===== SoM INTENTS =====
        "som_search": [
            "suche nach python tutorial",
            "such mir informationen über ki",
            "google nach maschinen lernen",
            "recherchiere wetter morgen in wien",
            "finde im internet news",
            "was ist thorium",
            "wer ist albert einstein",
            "erkläre mir quantenmechanik",
            "wie wird das wetter morgen",
            "informationen über black holes",
            "such wetterbericht",
            "google nach rezepten",
            "suche nach dem wetter in berlin",
            "wie ist das wetter heute",
            "was ist künstliche intelligenz",
            "was bedeutet openclaw",
            "wer ist der erfinder des internets",
            "was ist ein schwarzes loch",
            "was ist künstliche intelligenz",
            "was ist ein neutronenstern",
            "was bedeutet quantenmechanik",
            "wer ist albert einstein",
            "wer war marie curie",
            "was ist die wurzel aus 4568",
            "wieviele planeten hat das universum",
            "was ist ein schwarzes loch einfach erklärt",
            "erkläre mir die relativitätstheorie",
            "was ist der unterschied zwischen python und java",
            "wie ist das wetter in wien",
            "wetter heute",
            "wettervorhersage für berlin",
            "wird es morgen regnen"
        ],
        
        "som_navigate": [
            "gehe zu wikipedia",
            "öffne startpage",
            "besuche die seite",
            "navigiere zu example.com",
            "rufe die webseite auf",
            "zeig mir github",
            "geh auf google",
            "öffne die seite"
        ],
        
        "som_learned": [
            "was hast du gelernt",
            "zeig mir dein wissen",
            "was weißt du über mich",
            "erinnerungen anzeigen",
            "was hast du gemerkt",
            "was weißt du schon",
            "zeig gelerntes",
            "dein wissen"
        ],
        
        "som_stats": [
            "wie viele suchen hattest du",
            "som statistiken",
            "zeig mir die statistik",
            "anzahl besuchter webseiten",
            "wie oft habe ich gesucht",
            "statistik anzeigen"
        ],
        
        "som_answer": [
            "erinnerst du dich",
            "erinnerst du",
            "erinnere dich",
            "weißt du noch",
            "kannst du dich erinnern",
            "im memory",
            "aus dem memory",
            "aus deinem wissen",
            "aus dem gelernten",
            "was hast du gelernt",
            "was weißt du über",
            "was weißt du noch",
            "was weißt du bereits",
            "hast du schon gelernt",
            "hast du gespeichert",
            "gelerntes wissen",
            "dein wissen",
            "deine erinnerung",
            "deine erinnerungen"
        ],
        
        # ===== WETTER-SUCHE (wichtig!) =====
        "som_search": [
            # Bestehende Such-Beispiele
            "suche nach python tutorial",
            "google nach maschinen lernen",
            "recherchiere wetter morgen in wien",
            "finde im internet news",
            
            # ===== NEU: Wetter-spezifisch =====
            "such nach dem wetter in wien",
            "wettervorhersage für berlin",
            "wie wird das wetter morgen",
            "wetterbericht heute",
            "wetter in wien im internet suchen",
            "such wetter in wien",
            "wie ist das wetter in wien",
            "wetter morgen wien",
            "wettervorhersage wien",
            
            # ===== NEU: Allgemeine Suchen =====
            "suche im internet nach",
            "google wetter",
            "finde wetter info",
            "recherchiere wetter",
            "such mir das wetter",
        ],
        
        # ===== GMAIL mit niedrigerer Priorität =====
        "gmail": [
            "zeig mir meine emails",
            "posteingang anzeigen",
            "welche mails habe ich",
            "neue nachrichten",
            "inbox anzeigen",
            "zeig meine gmails",
            "email posteingang",
            "hatte ich neue mails",
        ],
    }
    
    for intent, examples in intents.items():
        for example in examples:
            semantic.add_knowledge(
                text=example,
                metadata={"intent": intent, "type": "intent_example"}
            )
    
    # Zusätzliche Variationen für bessere Erkennung
    extra_examples = [
        ("som_search", "wetter morgen {}"),
        ("som_search", "wie wird das wetter in {}"),
        ("som_search", "wettervorhersage für {}"),
        ("som_search", "was bedeutet {}"),
        ("som_search", "was ist {} einfach erklärt"),
        ("som_search", "erkläre {}"),
        ("som_search", "such {}"),
        ("som_search", "finde {}"),
        ("som_search", "recherchiere {}"),
    ]
    
    placeholders = ["wien", "berlin", "python", "ki", "maschinen lernen", "thorium"]
    for intent, template in extra_examples:
        for placeholder in placeholders:
            example = template.format(placeholder)
            semantic.add_knowledge(
                text=example,
                metadata={"intent": intent, "type": "intent_example"}
            )
    
    logger.info(f"✅ {sum(len(examples) for examples in intents.values()) + len(extra_examples) * len(placeholders)} Intent-Beispiele initialisiert")


def _classify_intent_enhanced(user_message: str) -> Dict[str, Any]:
    """
    Erweiterte Intent-Erkennung - EXPLIZITE SUCHEN zuerst!
    """
    msg = user_message.lower().strip()
    
    # ===== PRIO 1: EXPLIZITE SUCH-ANFRAGEN (MUSS zuerst kommen!) =====
    # Diese Keywords lösen IMMER eine Web-Suche aus
    explicit_search_keywords = [
        "suche nach", "such nach", "suche im internet", "such im internet",
        "google", "recherchiere", "finde im internet", "web search",
        "such mir", "finde heraus", "suche auf startpage"
    ]
    
    for kw in explicit_search_keywords:
        if kw in msg:
            logger.info(f"🔍 Explizite Such-Anfrage: {user_message[:50]}...")
            # Extrahiere Suchbegriff
            query = user_message
            for k in explicit_search_keywords:
                if k in msg:
                    query = user_message[msg.find(k) + len(k):].strip()
                    break
            return {
                "intent": "som_search",
                "confidence": 0.98,
                "method": "explicit_search",
                "query": query if query else user_message
            }
    
    # ===== PRIO 2: MEMORY-FRAGEN =====
    memory_keywords = [
        "erinnerst du dich", "erinnerst du", "erinnere dich",
        "weißt du noch", "kannst du dich erinnern",
        "im memory", "aus dem memory", "aus deinem wissen",
        "was hast du gelernt", "was weißt du über",
        "hast du gespeichert", "deine erinnerung"
    ]
    
    if any(kw in msg for kw in memory_keywords):
        logger.info(f"📚 Memory-Frage erkannt: {user_message[:50]}...")
        return {
            "intent": "som_answer",
            "confidence": 0.9,
            "method": "memory_keyword",
            "query": user_message
        }
    
    # ===== PRIO 3: URL-NAVIGATION =====
    url_pattern = re.search(r'(https?://[^\s]+|[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', msg)
    if url_pattern:
        url = url_pattern.group(1)
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        nav_words = ["gehe", "öffne", "besuche", "rufe", "zeig", "geh", "navigiere"]
        if any(word in msg for word in nav_words):
            return {
                "intent": "som_navigate",
                "confidence": 0.85,
                "method": "url_detection",
                "url": url
            }
    
    # ===== PRIO 4: SEMANTISCHE ERKENNUNG (mit Korrektur) =====
    try:
        semantic_result = _classify_intent_semantic(user_message)
        
        # Korrektur: Wenn semantisch "calendar" erkannt wird, aber Such-Keywords fehlen
        if semantic_result.get("intent") == "calendar":
            # Prüfe ob es wirklich ein Kalender-Befehl ist
            calendar_keywords = ["kalender", "termin", "meine termine", "wochenplan", "tagesplan"]
            if not any(kw in msg for kw in calendar_keywords):
                # Falsch-positiv, korrigiere zu chat
                logger.info(f"⚠️ Korrigiere falsche Kalender-Erkennung → chat")
                return {
                    "intent": "chat",
                    "confidence": 0.6,
                    "method": "semantic_corrected"
                }
        
        if semantic_result.get("confidence", 0) > 0.7:
            logger.info(f"🎯 Semantischer Intent: {semantic_result['intent']} (Confidence: {semantic_result['confidence']:.3f})")
            return semantic_result
            
    except Exception as e:
        logger.warning(f"Semantische Erkennung fehlgeschlagen: {e}")
    
    # ===== FALLBACK =====
    return _classify_intent(user_message)


def _classify_intent_semantic(user_message: str) -> Dict[str, Any]:
    """
    Semantische Intent-Erkennung mit Vector Search.
    """
    msg = user_message.lower().strip()
    
    try:
        semantic = get_semantic_intent()
        results = semantic.search(msg, top_k=5)
        
        intent_scores = {}
        for result in results:
            metadata = result.get("metadata", {})
            intent = metadata.get("intent")
            if intent:
                score = 1 - min(result.get("score", 1), 0.99)
                
                # Gewichtung anpassen
                if intent == "som_search":
                    score = score * 1.3  # +30% für Suche
                elif intent == "calendar":
                    # Kalender nur bei echten Kalender-Keywords
                    calendar_keywords = ["kalender", "termin", "meine termine", "wochenplan"]
                    if not any(kw in msg for kw in calendar_keywords):
                        score = score * 0.3  # -70% für falsche Kalender-Erkennung
                elif intent == "gmail":
                    gmail_keywords = ["gmail", "email", "mail", "posteingang"]
                    if not any(kw in msg for kw in gmail_keywords):
                        score = score * 0.5
                
                intent_scores[intent] = max(intent_scores.get(intent, 0), score)
        
        if intent_scores:
            best_intent = max(intent_scores, key=intent_scores.get)
            best_score = intent_scores[best_intent]
            
            if best_score > 0.65:
                return {
                    "intent": best_intent,
                    "confidence": best_score,
                    "method": "semantic",
                    "matched_examples": [r.get("text", "")[:50] for r in results[:3]]
                }
        
        return {
            "intent": "chat",
            "confidence": 0.5,
            "method": "fallback"
        }
        
    except Exception as e:
        logger.error(f"Semantische Intent-Erkennung fehlgeschlagen: {e}")
        return {
            "intent": "chat",
            "confidence": 0.5,
            "method": "error_fallback"
        }

def _classify_intent(user_message: str) -> Dict[str, Any]:
    """
    Präzise Intent-Erkennung mit Kontext-Bewusstsein.
    
    Args:
        user_message: Die Benutzernachricht
        
    Returns:
        Dict mit intent, confidence und scores
    """
    msg = user_message.lower().strip()
    
    intents = {
        "gmail": {
            "keywords": [
                "zeig mails", "zeig emails", "posteingang", "inbox",
                "meine mails", "meine emails", "gmail", "email", "mail",
                "nachrichten", "ungelesene mails", "neue mails",
                "zeig mir mails", "zeig mir emails", "mail posteingang",
                "email posteingang", "gmail posteingang", "mail anzeigen"
            ],
            "patterns": [r"^/gmail", r"^/mail"]
        },
        "calendar": {
            "keywords": [
                "kalender", "termine", "termin", "meine termine",
                "kalender anzeigen", "was habe ich heute", "heutige termine",
                "nächste termine", "kalendereinträge", "tagesplan",
                "wochenplan", "mein kalender"
            ],
            "patterns": [r"^/calendar", r"^/termine"]
        },
        "telegram": {
            "keywords": [
                "telegram", "tg", "telegram bot", "telegram nachricht",
                "telegram senden", "telegram broadcast"
            ],
            "patterns": [r"^/telegram", r"^/tg"]
        },
        "shell": {
            "keywords": [
                "zeig dateien", "list dateien", "zeig mir", "erstelle datei",
                "lösche datei", "shell", "cmd", "befehl", "terminal",
                "verzeichnis", "ordner", "datei erstellen", "datei löschen",
                "python dateien", "alle dateien"
            ],
            "patterns": [r"^/shell", r"^/cmd", r"^/bash"]
        },
        "code": {
            "keywords": [
                "schreib code", "programmiere", "python script", "html",
                "funktion", "klasse", "algorithmus", "implementiere",
                "code generieren", "skript schreiben"
            ],
            "patterns": []
        },
        "vision": {
            "keywords": [
                "was siehst du", "webcam", "bild analysieren", "foto machen",
                "kamera", "siehst", "erkennst", "visuell"
            ],
            "patterns": [r"^/vision", r"^/webcam"]
        },
        "search": {
            "keywords": [
                "suche nach", "google", "recherchiere", "finde heraus",
                "such nach", "was ist", "wer ist", "informationen über"
            ],
            "patterns": []
        },
        "creative": {
            "keywords": [
                "erzähl geschichte", "gedicht", "kreative idee",
                "schreib ein gedicht", "erzähl mir"
            ],
            "patterns": []
        },
        "system": {
            "keywords": [
                "systemanalyse", "system analyse", "systemstatus", "system status",
                "zeig systeminfo", "zeig system info", "hardware auslastung",
                "cpu auslastung", "ram auslastung", "systemauslastung",
                "system info", "systeminfo"
            ],
            "patterns": [r"^/system", r"^/status"]
        }
    }
    
    scores = {intent: 0.0 for intent in intents}
    
    for intent, config in intents.items():
        for keyword in config.get("keywords", []):
            if keyword in msg:
                scores[intent] += 0.3
        
        for pattern in config.get("patterns", []):
            if re.search(pattern, user_message, re.IGNORECASE):
                scores[intent] += 0.5
    
    definition_indicators = [
        "definition", "was ist", "was bedeutet", "erkläre", "bedeutung",
        "wissenschaftliche basis", "architektur beschreibung", "set of mark prompting",
        "beschreibe die architektur", "was ist ein", "definiere",
        "was heißt", "was meint", "was versteht man unter"
    ]
    is_definition_request = any(ind in msg for ind in definition_indicators)
    system_word_in_definition = ("system" in msg or "architektur" in msg) and is_definition_request
    
    best_intent = max(scores, key=scores.get)
    best_score = scores[best_intent]
    confidence = min(best_score, 1.0)
    
    if best_intent == "system" and (confidence < 0.6 or system_word_in_definition):
        best_intent = "chat"
        confidence = 0.7
    
    if best_intent == "gmail" and confidence < 0.5:
        strong_gmail = any(kw in msg for kw in ["gmail", "email", "mail", "posteingang"])
        if not strong_gmail:
            best_intent = "chat"
            confidence = 0.6
    
    if best_intent == "calendar" and confidence < 0.5:
        strong_calendar = any(kw in msg for kw in ["kalender", "termine", "termin"])
        if not strong_calendar:
            best_intent = "chat"
            confidence = 0.6
    
    if best_score < 0.2:
        best_intent = "chat"
        msg_len = len(user_message)
        if msg_len < 10:
            confidence = 0.3
        elif msg_len < 50:
            confidence = 0.6
        else:
            confidence = 0.8
    
    return {
        "intent": best_intent,
        "confidence": confidence,
        "scores": scores,
        "matched_keywords": []
    }


def _extract_entities(user_message: str) -> Dict[str, List[str]]:
    """
    Extrahiert wichtige Entities aus der Nachricht.
    
    Args:
        user_message: Die Benutzernachricht
        
    Returns:
        Dict mit extrahierten Entities
    """
    msg = user_message.lower()
    entities = {}
    
    file_match = re.search(r'([\w\-\.]+\.(?:py|txt|md|json|yaml|html|css|js))', msg)
    if file_match:
        entities["file"] = [file_match.group(1)]
    
    url_match = re.search(r'(https?://[^\s]+)', user_message)
    if url_match:
        entities["url"] = [url_match.group(1)]
    
    numbers = re.findall(r'\b\d+\b', user_message)
    if numbers:
        entities["numbers"] = numbers[:3]
    
    return entities


def _is_complex_request(msg: str) -> bool:
    """
    Prüft ob eine Anfrage komplex ist.
    
    Args:
        msg: Die Nachricht
        
    Returns:
        True wenn komplex
    """
    if not msg:
        return False
    
    text = msg.lower().strip()
    complexity_signals = [
        "architektur", "design", "konzept", "implementierung", "code", "cms", "api",
        "datenbank", "auth", "rbac", "migration", "refactor", "performance",
        "sicherheit", "test", "pipeline", "backend", "frontend", "fullstack",
        "gerüst", "struktur", "framework", "komplex", "mehrstufig",
    ]
    long_text = len(text) > 140 or len(text.split()) > 22
    return long_text or any(sig in text for sig in complexity_signals)


def _should_enable_self_qa(user_message: str, router_hint: Optional[Dict[str, Any]] = None) -> bool:
    """
    Prüft ob Self-QA aktiviert werden soll.
    
    Args:
        user_message: Die Nachricht
        router_hint: Optionaler Router-Hint
        
    Returns:
        True wenn Self-QA aktiviert werden soll
    """
    msg = (user_message or "").lower().strip()
    if not msg:
        return False
    
    explicit_terms = [
        "perfekt", "gründlich", "genau", "denke", "denk",
        "schritt", "plan", "strategie", "analys", "prüf",
    ]
    explicit = any(t in msg for t in explicit_terms)
    complex_hint = bool((router_hint or {}).get("complexity") == "high")
    return explicit or complex_hint or _is_complex_request(msg)


def _run_fast_router_check(
    user_message: str, 
    available: List[str], 
    progress_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Verbesserter Router-Check mit Intent-Erkennung.
    
    Args:
        user_message: Die Benutzernachricht
        available: Verfügbare Modelle
        progress_id: Optionaler Progress-ID
        
    Returns:
        Dict mit Routing-Informationen
    """
    if not user_message:
        return {"checked": False}
    
    intent_result = _classify_intent_enhanced(user_message)
    logger.debug(f"Intent: {intent_result['intent']} ({intent_result['confidence']:.2f}) - {user_message[:50]}")
    
    logger.info(f"{'='*50}")
    logger.info(f"📝 USER: {user_message}")
    logger.info(f"🎯 INTENT: {intent_result['intent']} (Confidence: {intent_result['confidence']:.2f})")
    logger.info(f"{'='*50}")
    
    entities = _extract_entities(user_message)
    
    if intent_result.get("confidence", 0) > 0.6:
        domain = intent_result["intent"]
        
        complexity_map = {
            "shell": "low", "creative": "low", "chat": "low",
            "vision": "medium", "code": "medium", "search": "medium"
        }
        
        prefer_fast_map = {
            "shell": True, "creative": True, "chat": True,
            "vision": False, "code": False, "search": False
        }
        
        logger.info(f"🎯 Intent erkannt: {domain} (Confidence: {intent_result['confidence']:.2f})")
        if entities:
            logger.info(f"📌 Entities: {entities}")
        
        return {
            "checked": True,
            "router_model": "intent_classifier",
            "complexity": complexity_map.get(domain, "low"),
            "domain": domain,
            "confidence": intent_result["confidence"],
            "entities": entities,
            "prefer_fast": prefer_fast_map.get(domain, False)
        }
    
    msg = (user_message or "").lower().strip()
    
    SHELL_KEYWORDS = [
        "erstelle datei", "zeig dateien", "verzeichnis", "zeig mir alle", 
        "lösche", "kopiere", "verschiebe", "installiere", "starte", 
        "stoppe", "prozesse", "systeminfo", "create file", "list files", 
        "show files", "zeig python dateien", "zeig alle dateien", 
        "welche dateien", "liste dateien", "zeig mir python dateien"
    ]
    
    if any(kw in msg for kw in SHELL_KEYWORDS):
        return {
            "checked": True, 
            "router_model": "keyword", 
            "complexity": "low",
            "domain": "ops", 
            "self_question": False, 
            "prefer_fast": True
        }
    
    CODE_KEYWORDS = [
        "schreib code", "programmiere", "erstelle ein skript", "html", 
        "python script", "funktion", "klasse", "algorithmus", "implementiere"
    ]
    
    if any(kw in msg for kw in CODE_KEYWORDS):
        return {
            "checked": True, 
            "router_model": "keyword", 
            "complexity": "medium",
            "domain": "code", 
            "self_question": False, 
            "prefer_fast": False
        }
    
    if len(msg.split()) < 8:
        return {
            "checked": True, 
            "router_model": "keyword", 
            "complexity": "low",
            "domain": "general", 
            "self_question": False, 
            "prefer_fast": True
        }
    
    return {
        "checked": False, 
        "router_model": None, 
        "complexity": "medium",
        "domain": "general", 
        "self_question": False, 
        "prefer_fast": False
    }


def _auto_select_model(
    user_message: str,
    requested_model: Optional[str] = None,
    progress_id: Optional[str] = None,
) -> str:
    """
    Wählt das Modell basierend auf Komplexität und Intent.
    
    Args:
        user_message: Die Benutzernachricht
        requested_model: Explizit angefordertes Modell
        progress_id: Optionaler Progress-ID
        
    Returns:
        Ausgewählter Modell-Name
    """
    logger.info(f"_auto_select_model aufgerufen - requested_model: {requested_model!r}")
    
    # User-Wahl respektieren
    if requested_model and requested_model.strip() not in ("__AUTO__", "auto", ""):
        selected = requested_model.strip()
        logger.info(f"Model-Routing: User-Wahl respektiert -> {selected}")
        _progress_add(progress_id, f"Gateway Model-Routing: {selected}", "fa-code-branch")
        return selected
    
    msg_lower = (user_message or "").lower().strip()
    
    # Vision-Priorisierung bei expliziten Bild-Befehlen
    is_explicit_vision = any(kw in msg_lower for kw in [
        "webcam", "foto machen", "bild analysieren", "screenshot",
        "was siehst du auf dem bild", "erkennst du auf dem bild",
        "mach ein foto", "webcam foto"
    ])
    
    if is_explicit_vision:
        try:
            from gateway.ollama_client import ollama_client
            models_info = ollama_client.list_models()
            available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
        except Exception:
            available = []
        
        preferred_vision = _as_model_pref_list(config.get("ollama.preferred_vision_models")) or []
        
        if preferred_vision:
            vision_model = _pick_preferred_available(available, preferred_vision)
            if vision_model:
                logger.info(f"Model-Routing: vision request -> {vision_model}")
                _progress_add(progress_id, f"Gateway Model-Routing (Vision): {vision_model}", "fa-eye")
                return vision_model
        
        vision_hints = [
            "llava", "bakllava", "vision", "cambrian", "minicpm-v", 
            "moondream", "qwen2.5vl", "qwen2-vl", "phi3-vision", 
            "llama3.2-vision", "paligemma", "cogvlm", "glm-4v"
        ]
        vision_model = _pick_best_model(available, hints=vision_hints)
        if vision_model:
            logger.info(f"Model-Routing: vision request (detected) -> {vision_model}")
            _progress_add(progress_id, f"Gateway Model-Routing (Vision): {vision_model}", "fa-eye")
            return vision_model
        
        logger.warning(f"No vision model found for request: {user_message}")
        _progress_add(progress_id, "⚠️ Kein Vision-Modell verfügbar, verwende Standard-Modell", "fa-exclamation-triangle")
    
    # Auto-Modus
    try:
        from gateway.ollama_client import ollama_client
        models_info = ollama_client.list_models()
        available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
    except Exception:
        available = []
    
    if not available:
        return DEFAULT_MODEL
    
    try:
        max_auto_size = float(config.get("ollama.auto_max_model_size_b", 12.0) or 0)
    except Exception:
        max_auto_size = 12.0
    
    router_hint = _run_fast_router_check(user_message, available, progress_id=progress_id)
    msg = (user_message or "").lower().strip()
    
    code_signals = [
        "code", "cms", "python", "html", "script", "programm", "css", "sql", "api",
        "backend", "frontend", "landingpage", "landing page", "webseite", "website",
        "ui", "layout", "design",
    ]
    coder_hints = ["coder", "code", "codellama", "starcoder", "deepseek-coder", "qwen2.5-coder", "mistral", "llama"]
    is_code = any(sig in msg for sig in code_signals) or router_hint.get("domain") == "code"
    is_complex = _is_complex_request(msg) or router_hint.get("complexity") == "high"
    prefer_fast = bool(router_hint.get("prefer_fast"))
    self_question = bool(router_hint.get("self_question"))
    
    is_short_general_question = (
        msg.endswith("?")
        and len(msg.split()) <= 12
        and not is_code
        and not is_complex
    )
    
    greeting_terms = {"hey", "hi", "hallo", "servus", "moin"}
    is_smalltalk = len(msg.split()) <= 4 and msg.strip("!?., ") in greeting_terms
    
    if is_smalltalk:
        prefer_fast = True
    
    if self_question:
        fast_self_model = _pick_fast_model(available)
        if fast_self_model:
            logger.info(f"Model-Routing: self-question -> {fast_self_model}")
            _progress_add(progress_id, f"Gateway Model-Routing: self-question -> {fast_self_model}", "fa-code-branch")
            return fast_self_model
    
    preferred_code = _as_model_pref_list(config.get("ollama.preferred_code_models")) or _as_model_pref_list(
        config.get("ollama.preferred_code_model")
    )
    preferred_general = _as_model_pref_list(config.get("ollama.preferred_general_models")) or _as_model_pref_list(
        config.get("ollama.preferred_general_model")
    )
    
    if is_code:
        preferred_code_model = _pick_preferred_available(available, preferred_code)
        if preferred_code_model:
            _progress_add(progress_id, f"Model-Routing: code-preferred -> {preferred_code_model}", "fa-code-branch")
            return preferred_code_model
        
        best_code = _pick_best_model(
            available,
            hints=coder_hints,
            min_size=7.0,
            max_size=max_auto_size if max_auto_size > 0 else None,
        ) or _pick_best_model(
            available,
            hints=coder_hints,
            max_size=max_auto_size if max_auto_size > 0 else None,
        )
        if best_code:
            _progress_add(progress_id, f"Model-Routing: code -> {best_code}", "fa-code-branch")
            return best_code
    
    if is_complex:
        best_complex = _pick_best_model(
            available,
            min_size=7.0,
            max_size=max_auto_size if max_auto_size > 0 else None,
        ) or _pick_best_model(
            available,
            max_size=max_auto_size if max_auto_size > 0 else None,
        )
        if best_complex:
            _progress_add(progress_id, f"Model-Routing: complex -> {best_complex}", "fa-code-branch")
            return best_complex
    
    if prefer_fast or is_short_general_question:
        best_fast = _pick_fast_model(available)
        if best_fast:
            _progress_add(progress_id, f"Model-Routing: fast -> {best_fast}", "fa-code-branch")
            return best_fast
    
    smalltalk_keywords = ["hallo", "hi", "hey", "wie geht", "wer bist du"]
    if len(msg) < 50 and any(word in msg for word in smalltalk_keywords):
        best_fast = _pick_fast_model(available)
        if best_fast:
            _progress_add(progress_id, f"Model-Routing: smalltalk -> {best_fast}", "fa-code-branch")
            return best_fast
    
    if DEFAULT_MODEL in available:
        _progress_add(progress_id, f"Model-Routing: default -> {DEFAULT_MODEL}", "fa-code-branch")
        return DEFAULT_MODEL
    
    preferred_general_model = _pick_preferred_available(available, preferred_general)
    if preferred_general_model:
        _progress_add(progress_id, f"Model-Routing: general-preferred -> {preferred_general_model}", "fa-code-branch")
        return preferred_general_model
    
    final_model = _pick_best_model(available, max_size=max_auto_size if max_auto_size > 0 else None) or DEFAULT_MODEL
    _progress_add(progress_id, f"Model-Routing: fallback -> {final_model}", "fa-code-branch")
    return final_model


def _get_suggested_model(user_message: str, current_model: str) -> Optional[str]:
    """
    Prüft ob ein anderes Modell besser geeignet wäre.
    
    Args:
        user_message: Die Benutzernachricht
        current_model: Aktuelles Modell
        
    Returns:
        Vorgeschlagenes Modell oder None
    """
    try:
        from gateway.ollama_client import ollama_client
        models_info = ollama_client.list_models()
        available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
    except Exception:
        return None
    
    if not available:
        return None
    
    msg = (user_message or "").lower().strip()
    
    code_signals = [
        "code", "python", "html", "script", "programm", "css", "sql", "api",
        "backend", "frontend", "webseite", "website", "ui", "layout",
    ]
    is_code = any(sig in msg for sig in code_signals)
    is_complex = _is_complex_request(msg)
    
    coder_hints = ["coder", "code", "starcoder", "deepseek-coder", "qwen2.5-coder"]
    current_is_code = any(hint in current_model.lower() for hint in coder_hints)
    
    if is_code and not current_is_code:
        preferred = _as_model_pref_list(config.get("ollama.preferred_code_models"))
        suggested = _pick_preferred_available(available, preferred)
        return suggested
    
    if is_complex:
        complex_models = [m for m in available if any(x in m.lower() for x in ["70b", "32b", "8b", "coder", "mistral"])]
        if complex_models and current_model not in complex_models:
            return complex_models[0]
    
    return None


def _pick_vision_model(available: List[str], requested_model: Optional[str] = None) -> Optional[str]:
    """
    Wählt ein Vision-fähiges Modell.
    
    Args:
        available: Verfügbare Modelle
        requested_model: Explizit angefordertes Modell
        
    Returns:
        Vision-Modell oder None
    """
    if not available:
        return None
    
    if requested_model and requested_model in available:
        if _infer_model_capabilities(requested_model).get("vision"):
            return requested_model
    
    vision_candidates = [m for m in available if _infer_model_capabilities(m).get("vision")]
    if not vision_candidates:
        return None
    
    preferred_vision = _as_model_pref_list(config.get("ollama.preferred_vision_models")) or _as_model_pref_list(
        config.get("ollama.preferred_vision_model")
    )
    preferred_vision_model = _pick_preferred_available(vision_candidates, preferred_vision)
    if preferred_vision_model:
        return preferred_vision_model
    
    preferred = [
        "qwen2.5vl", "qwen2-vl", "llava", "minicpm-v", "moondream", 
        "bakllava", "cambrian", "phi3-vision", "llama3.2-vision", "vision", "vl"
    ]
    for hint in preferred:
        hinted = [m for m in vision_candidates if hint in m.lower()]
        if hinted:
            return sorted(hinted, key=_extract_model_score, reverse=True)[0]
    
    return sorted(vision_candidates, key=_extract_model_score, reverse=True)[0]


def _progress_add(request_id: Optional[str], text: str, icon: str = "fa-brain", details: str = "") -> None:
    """Helper für Progress-Add (wird in main definiert)."""
    # Diese Funktion wird später durch die tatsächliche Implementation ersetzt
    pass


# Exportierte Funktionen für andere Module
def classify_intent(user_message: str) -> Dict[str, Any]:
    """Public wrapper für Intent-Erkennung."""
    return _classify_intent_enhanced(user_message)


def auto_select_model(user_message: str, requested_model: Optional[str] = None) -> str:
    """Public wrapper für Modell-Auswahl."""
    return _auto_select_model(user_message, requested_model)


def is_complex_request(user_message: str) -> bool:
    """Public wrapper für Komplexitätsprüfung."""
    return _is_complex_request(user_message)


def extract_entities(user_message: str) -> Dict[str, List[str]]:
    """Public wrapper für Entity-Extraktion."""
    return _extract_entities(user_message)