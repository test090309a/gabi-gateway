"""FastAPI HTTP endpoints."""  # FIX: Model switching fix
import re
import logging
import platform
import sys
import shutil
import subprocess
import os
import json
import base64
import copy
import asyncio
import random
import threading
import uuid
import socket
import time
import importlib
import inspect
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional, Dict
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks, UploadFile, File, Form, Query
from pydantic import BaseModel
import httpx
from gateway.config import config
from gateway.auth import verify_api_key
from gateway.ollama_client import ollama_client
from gateway.integrations.shell_executor import shell_executor
from gateway.integrations.gmail_client import get_gmail_client
from gateway.integrations.google_calendar_client import get_calendar_client
from gateway.integrations.whisper_client import get_whisper_client
from gateway.integrations.telegram_bot import get_telegram_bot
from gateway.integrations.gui_controller import get_gui_controller
import requests as http_requests
from gateway.integrations.web_automation import get_web_automation
from gateway.integrations.web_learning import get_web_learning
from gateway.integrations.web_automation import get_web_automation
try:
    from gateway.integrations.telegram_bot import get_telegram_bot
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    def get_telegram_bot():
        return None
from gateway.integrations.semantic_memory import SemanticMemory

# Füge diese Zeilen ein, nachdem die anderen imports schon da sind
from gateway.integrations.semantic_memory import SemanticMemory  # Evtl. schon vorhanden, dann nicht doppelt
from gateway.web_agent_integration import get_web_gateway
from gateway.web_commands import handle_web_command
from gateway.integrations.som_agent import get_som_agent

# Globale Instanz für semantische Intent-Erkennung
_semantic_intent = None

# SoM Agent Instanz
_som_agent = None

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)
logger = logging.getLogger("GATEWAY.intent")

ENABLE_LLM_SHELL_DETECTION = True

def get_semantic_intent():
    """Singleton für semantische Intent-Erkennung"""
    global _semantic_intent
    if _semantic_intent is None:
        _semantic_intent = SemanticMemory()
        # Vordefinierte Intent-Beispiele initialisieren
        _init_intent_examples(_semantic_intent)
    return _semantic_intent

def reset_som_agent():
    """Setzt den SoM Agent zurück und erstellt eine neue Instanz."""
    global _som_agent
    _som_agent = None
    return get_som_agent(force_new=True)

def _init_intent_examples(semantic: SemanticMemory):
    """Initialisiert die Intent-Beispiele im semantischen Speicher"""
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
        
        # ===== NEU: SoM INTENTS (für Web-Suche & Navigation) =====
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
            # ===== NEU: Definitionsfragen =====
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
            "was ist der unterschied zwischen python und java"
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
        ]
    }
    
    for intent, examples in intents.items():
        for example in examples:
            semantic.add_knowledge(
                text=example,
                metadata={"intent": intent, "type": "intent_example"}
            )
    
    # Zusätzlich: Mehr Variationen für bessere Erkennung
    extra_examples = [
        # Wetter-Variationen
        ("som_search", "wetter morgen {}"),
        ("som_search", "wie wird das wetter in {}"),
        ("som_search", "wettervorhersage für {}"),
        
        # Definitions-Variationen
        ("som_search", "was bedeutet {}"),
        ("som_search", "was ist {} einfach erklärt"),
        ("som_search", "erkläre {}"),
        
        # Such-Variationen
        ("som_search", "such {}"),
        ("som_search", "finde {}"),
        ("som_search", "recherchiere {}"),
    ]
    
    # Füge Variationen mit Platzhaltern hinzu
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
    """Erweiterte Intent-Erkennung mit semantischer Suche als PRIORITÄT"""
    msg = user_message.lower().strip()

    # ===== 0. NEU: SPEZIELLE PRÜFUNG FÜR MEMORY-FRAGEN =====
    memory_keywords = [
        # Explizite Erinnerungsfragen
        "erinnerst du dich", "erinnerst du", "erinnere dich",
        "weißt du noch", "kannst du dich erinnern",
        
        # Memory-Kontext
        "im memory", "aus dem memory", "aus deinem wissen",
        "aus deinem gelernten wissen", "aus dem gelernten",
        
        # Gelerntes Wissen
        "was hast du gelernt", "was weißt du über", "was weißt du noch",
        "was weißt du bereits", "hast du schon gelernt",
        
        # Gespeichertes
        "hast du gespeichert", "gelerntes wissen", "dein wissen",
        "deine erinnerung", "deine erinnerungen"
    ]
    
    if any(kw in msg for kw in memory_keywords):
        logger.info(f"📚 Memory-Frage erkannt (Keyword): {user_message[:50]}...")
        return {
            "intent": "som_answer",
            "confidence": 0.9,  # Höhere Confidence, da Keyword-Match sehr spezifisch
            "method": "memory_keyword",
            "query": user_message
        }
    
    # ===== 1. SEMANTISCHE ERKENNUNG (primär, am genauesten) =====
    try:
        semantic_result = _classify_intent_semantic(user_message)
        
        # Bei hoher Confidence direkt zurückgeben
        if semantic_result.get("confidence", 0) > 0.65:
            logger.info(f"🎯 Semantischer Intent: {semantic_result['intent']} (Confidence: {semantic_result['confidence']:.3f})")
            return semantic_result
    except Exception as e:
        logger.warning(f"Semantische Erkennung fehlgeschlagen: {e}")
    
    # ===== 2. FALLBACK: URL-Erkennung für Navigation =====
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
    
    # ===== 3. FALLBACK: Keyword-basiert (nur wenn semantisch nichts gefunden) =====
    # Hier nur noch ganz einfache Keywords für absolute Notfälle
    som_keywords = ["suche", "google", "wetter", "was ist", "wer ist"]
    if any(kw in msg for kw in som_keywords):
        return {
            "intent": "som_search",
            "confidence": 0.6,
            "method": "keyword_fallback",
            "query": user_message
        }
    
    # ===== 4. GANZ ZUM SCHLUSS: Originale Intent-Erkennung =====
    return _classify_intent(user_message)

def _classify_intent_semantic(user_message: str) -> Dict[str, Any]:
    """
    Semantische Intent-Erkennung mit Vector Search.
    Viel genauer als Keyword-Matching!
    """
    msg = user_message.lower().strip()
    
    try:
        semantic = get_semantic_intent()
        
        # Suche nach ähnlichen Intent-Beispielen
        results = semantic.search(msg, top_k=5)
        
        # Sammle Treffer nach Intent
        intent_scores = {}
        for result in results:
            metadata = result.get("metadata", {})
            intent = metadata.get("intent")
            if intent:
                # Score: 1 - distance (weil distance=0 ist perfekt)
                score = 1 - min(result.get("score", 1), 0.99)
                intent_scores[intent] = max(intent_scores.get(intent, 0), score)
        
        if intent_scores:
            # Besten Intent finden
            best_intent = max(intent_scores, key=intent_scores.get)
            best_score = intent_scores[best_intent]
            
            # Confidence-Schwellwert (erfahrungsgemäß)
            if best_score > 0.65:
                logger.info(f"🎯 Semantischer Intent: {best_intent} (Score: {best_score:.3f})")
                return {
                    "intent": best_intent,
                    "confidence": best_score,
                    "method": "semantic",
                    "matched_examples": [r.get("text", "")[:50] for r in results[:3]]
                }
        
        # Fallback: Chat
        return {
            "intent": "chat",
            "confidence": 0.5,
            "method": "fallback"
        }
        
    except Exception as e:
        logger.error(f"Semantische Intent-Erkennung fehlgeschlagen: {e}")
        # Fallback auf einfache Erkennung
        return {
            "intent": "chat",
            "confidence": 0.5,
            "method": "error_fallback"
        }

def _classify_intent(user_message: str) -> Dict[str, Any]:
    """Präzise Intent-Erkennung mit Kontext-Bewusstsein - verhindert false positives bei System/Architektur."""
    msg = user_message.lower().strip()
    
    # ===== INTENT-DEFINITIONEN =====
    intents = {
        # ===== NEU: GMAIL =====
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
        # ===== NEU: CALENDAR =====
        "calendar": {
            "keywords": [
                "kalender", "termine", "termin", "meine termine",
                "kalender anzeigen", "was habe ich heute", "heutige termine",
                "nächste termine", "kalendereinträge", "tagesplan",
                "wochenplan", "mein kalender"
            ],
            "patterns": [r"^/calendar", r"^/termine"]
        },
        # ===== NEU: TELEGRAM =====
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
        # ===== SYSTEM-INTENT NUR BEI SEHR DEUTLICHEN SIGNALEN =====
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
    
    # Zähler für Treffer
    scores = {intent: 0.0 for intent in intents}
    
    for intent, config in intents.items():
        # Keyword-Matching
        for keyword in config.get("keywords", []):
            if keyword in msg:
                scores[intent] += 0.3
        
        # Pattern-Matching (Regex)
        for pattern in config.get("patterns", []):
            if re.search(pattern, user_message, re.IGNORECASE):
                scores[intent] += 0.5
    
    # ===== PRÜFE AUF DEFINITIONS-ANFRAGEN (verhindert false positives) =====
    definition_indicators = [
        "definition", "was ist", "was bedeutet", "erkläre", "bedeutung",
        "wissenschaftliche basis", "architektur beschreibung", "set of mark prompting",
        "beschreibe die architektur", "was ist ein", "definiere",
        "was heißt", "was meint", "was versteht man unter"
    ]
    is_definition_request = any(ind in msg for ind in definition_indicators)
    
    # ===== SPEZIALFALL: "system" oder "architektur" in Definitions-Kontext =====
    system_word_in_definition = ("system" in msg or "architektur" in msg) and is_definition_request
    
    # ===== BESTEN INTENT BESTIMMEN =====
    best_intent = max(scores, key=scores.get)
    best_score = scores[best_intent]
    
    # Confidence normalisieren (max 1.0)
    confidence = min(best_score, 1.0)
    
    # ===== KORREKTUREN =====
    # 1. System-Intent nur bei hoher Confidence UND nicht in Definitions-Kontext
    if best_intent == "system" and (confidence < 0.6 or system_word_in_definition):
        best_intent = "chat"
        confidence = 0.7
    
    # 2. Gmail-Intent: Wenn Confidence niedrig aber klare Gmail-Keywords
    if best_intent == "gmail" and confidence < 0.5:
        # Prüfe auf starke Gmail-Signale
        strong_gmail = any(kw in msg for kw in ["gmail", "email", "mail", "posteingang"])
        if not strong_gmail:
            best_intent = "chat"
            confidence = 0.6
    
    # 3. Calendar-Intent: Wenn Confidence niedrig aber klare Calendar-Keywords
    if best_intent == "calendar" and confidence < 0.5:
        strong_calendar = any(kw in msg for kw in ["kalender", "termine", "termin"])
        if not strong_calendar:
            best_intent = "chat"
            confidence = 0.6
    
    # Wenn nichts erkannt wurde → chat
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
    """Extrahiert wichtige Entities aus der Nachricht"""
    msg = user_message.lower()
    entities = {}
    
    # Dateinamen
    file_match = re.search(r'([\w\-\.]+\.(?:py|txt|md|json|yaml|html|css|js))', msg)
    if file_match:
        entities["file"] = [file_match.group(1)]
    
    # URLs
    url_match = re.search(r'(https?://[^\s]+)', user_message)
    if url_match:
        entities["url"] = [url_match.group(1)]
    
    # Zahlen
    numbers = re.findall(r'\b\d+\b', user_message)
    if numbers:
        entities["numbers"] = numbers[:3]
    
    return entities


# === WEB AUTOMATION (Selenium) ===
try:
    from gateway.integrations.web_automation_selenium import get_web_automation
    USE_SELENIUM = True
    logger.info("✅ Web-Automation: Selenium geladen")
except ImportError as e:
    logger.warning(f"⚠️ Keine Web-Automation verfügbar: {e}")
    get_web_automation = None
    USE_SELENIUM = False

from gateway.integrations.web_learning import get_web_learning

# === PYDANTIC MODELS FOR GUI ===
class GuiClickRequest(BaseModel):
    x: int
    y: int
    button: str = "left"
    double: bool = False

# === PYDANTIC MODELS FOR GUI ===
class GuiClickRequest(BaseModel):
    x: int
    y: int
    button: str = "left"
    double: bool = False

class GuiTypeRequest(BaseModel):
    text: str

class GuiPressRequest(BaseModel):
    key: str

class GuiHotkeyRequest(BaseModel):
    keys: List[str]

class GuiOpenRequest(BaseModel):
    program: str

class GuiGotoRequest(BaseModel):
    url: str
    browser: Optional[str] = "chrome"


# ============ COMFYUI BILDGENERIERUNG ============
import requests as http_requests
import base64
import random

class ComfyUIGenerator:
    """ComfyUI Bildgenerierung mit API-Integration"""
    
    def __init__(self, server_url="http://127.0.0.1:8188"):
        self.server_url = server_url
        self.client_id = f"gabi-{uuid.uuid4().hex[:8]}"
        
    def is_available(self) -> bool:
        """Prüft ob ComfyUI Server läuft"""
        try:
            response = http_requests.get(f"{self.server_url}/system_stats", timeout=2)
            return response.status_code == 200
        except:
            return False
    
    def generate_image(self, prompt: str, negative_prompt: str = "", 
                      width: int = 512, height: int = 512, 
                      steps: int = 20) -> Optional[bytes]:
        """Generiert ein Bild mit ComfyUI"""
        try:
            # Einfacher Workflow für SD1.5/SDXL
            workflow = self._create_simple_workflow(prompt, negative_prompt, width, height, steps)
            
            # Sende an ComfyUI
            response = http_requests.post(
                f"{self.server_url}/prompt",
                json={"prompt": workflow, "client_id": self.client_id},
                timeout=30
            )
            
            if response.status_code != 200:
                logger.error(f"ComfyUI prompt error: {response.text}")
                return None
                
            prompt_id = response.json().get("prompt_id")
            if not prompt_id:
                return None
            
            # Warte auf Ergebnis
            return self._wait_for_image(prompt_id)
            
        except Exception as e:
            logger.error(f"ComfyUI generation error: {e}")
            return None
    
    def _create_simple_workflow(self, prompt: str, negative: str, width: int, height: int, steps: int) -> Dict:
        """Erstellt einen minimalen ComfyUI Workflow"""
        # Versuche verschiedene Checkpoint-Namen
        checkpoints = [
            "sd_xl_base_1.0.safetensors",
            "sd_xl_base_1.0.safetensors",
            "v1-5-pruned.ckpt",
            "sd1.5.safetensors",
            "model.safetensors"
        ]
        
        workflow = {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": random.randint(1, 999999),
                    "steps": steps,
                    "cfg": 7.5,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0]
                }
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": checkpoints[0]  # Versuche erstes Checkpoint
                }
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1
                }
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["4", 1]
                }
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": negative,
                    "clip": ["4", 1]
                }
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2]
                }
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": f"GABI_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "images": ["8", 0]
                }
            }
        }
        return workflow
    
    def _wait_for_image(self, prompt_id: str, timeout: int = 120) -> Optional[bytes]:
        """Wartet auf das generierte Bild"""
        import time
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            try:
                response = http_requests.get(f"{self.server_url}/history", timeout=2)
                if response.status_code == 200:
                    history = response.json()
                    if prompt_id in history:
                        outputs = history[prompt_id].get("outputs", {})
                        for node_id, output in outputs.items():
                            if "images" in output:
                                for img in output["images"]:
                                    # Bild abrufen
                                    img_response = http_requests.get(
                                        f"{self.server_url}/view",
                                        params={
                                            "filename": img["filename"],
                                            "subfolder": img["subfolder"],
                                            "type": img["type"]
                                        },
                                        timeout=10
                                    )
                                    if img_response.status_code == 200:
                                        return img_response.content
            except Exception as e:
                logger.debug(f"Wait for image error: {e}")
            
            time.sleep(1)
        
        return None

# === GABI VISION ===
try:
    from gateway.integrations.gabi_vision import get_gabi_vision
except ImportError:
    get_gabi_vision = None

# === DYNAMIC HOT-RELOAD SYSTEM ===
# Registry für dynamisch geladene Integrationen
_dynamic_integrations: Dict[str, Any] = {}
_integrations_dir = Path(__file__).parent.parent / "integrations"
_last_scan_times: Dict[str, float] = {}
FILE_WATCH_INTERVAL = 5  # Sekunden zwischen Datei-Scans

# Logger für Hot-Reload (wird nach dem Import initialisiert)
_hotreload_logger = None

def _get_hotreload_logger():
    """Lazy Logger für Hot-Reload."""
    global _hotreload_logger
    if _hotreload_logger is None:
        _hotreload_logger = logging.getLogger("GATEWAY.hotreload")
    return _hotreload_logger

# === HOT-RELOAD FUNKTIONEN ===
def _scan_integrations_dir() -> List[Dict[str, Any]]:
    """Scannt das integrations/ Verzeichnis nach neuen .py Dateien."""
    if not _integrations_dir.exists():
        return []

    integrations = []
    for py_file in _integrations_dir.glob("*.py"):
        if py_file.name.startswith("_") or py_file.name == "__init__.py":
            continue

        try:
            stat = py_file.stat()
            mtime = stat.st_mtime
            size = stat.st_size

            integrations.append({
                "name": py_file.stem,
                "path": str(py_file),
                "mtime": mtime,
                "size": size,
                "exists": True
            })
        except Exception as e:
            _get_hotreload_logger().warning(f"Fehler beim Scannen von {py_file}: {e}")

    return integrations

def _load_integration_module(module_name: str) -> Optional[Any]:
    """Lädt ein Integration-Modul dynamisch mit importlib."""
    try:
        # Bestehendes Modul aus Cache entfernen
        if module_name in sys.modules:
            del sys.modules[module_name]

        #try:
        #    del sys.modules[f"integrations.{module_name}"]
        #except KeyError:
        #    pass

        # Neues Modul importieren
        module = importlib.import_module(f"integrations.{module_name}")
        importlib.reload(module)

        _get_hotreload_logger().info(f"Hot-Reload: Modul '{module_name}' geladen")
        return module

    except Exception as e:
        _get_hotreload_logger().error(f"Hot-Reload Fehler für '{module_name}': {e}")
        return None

def _register_integration_routes(module_name: str, module: Any) -> bool:
    """Registriert automatisch neue FastAPI-Routen aus einem Modul."""
    try:
        # Suche nach FastAPI-Routern im Modul
        router = getattr(module, "router", None)
        if router:
            # Versuche app aus dem aktuellen Kontext zu holen
            try:
                from main import app as main_app
                if router not in [r for r in main_app.routes if hasattr(r, 'path')]:
                    main_app.include_router(router)
                    _get_hotreload_logger().info(f"Neue Route registriert: /api/{module_name}")
                    return True
            except ImportError:
                _get_hotreload_logger().warning("main_app konnte nicht importiert werden")
                return False

        # Suche nach eigenständigen Endpoint-Funktionen
        for name, obj in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("router_") or name.endswith("_endpoint"):
                _get_hotreload_logger().info(f"Funktion gefunden: {name}")
                return True

        return False

    except Exception as e:
        _get_hotreload_logger().error(f"Fehler beim Registrieren von Routen für '{module_name}': {e}")
        return False

def check_and_reload_integrations() -> Dict[str, Any]:
    """Prüft auf neue/geänderte Integrationen und lädt sie dynamisch."""
    current_integrations = _scan_integrations_dir()
    reloads = []

    for integration in current_integrations:
        name = integration["name"]
        path = integration["path"]
        mtime = integration["mtime"]

        # Neue oder geänderte Datei?
        last_time = _last_scan_times.get(name, 0)
        if mtime > last_time:
            logger.info(f"Hot-Reload: Neue/geänderte Integration erkannt: {name}")

            # Modul laden
            module = _load_integration_module(name)
            if module:
                # Routen registrieren
                _register_integration_routes(name, module)

                # In Registry speichern
                _dynamic_integrations[name] = {
                    "module": module,
                    "path": path,
                    "loaded_at": time.time()
                }

                reloads.append(name)

            _last_scan_times[name] = mtime

    return {"reloaded": reloads, "total": len(_dynamic_integrations)}

# Background Task für automatische Integration-Überwachung
def _start_integration_watcher():
    """Startet den Hintergrund-Thread für Integration-Überwachung."""
    def watcher():
        while True:
            try:
                check_and_reload_integrations()
            except Exception as e:
                logger.error(f"Integration-Watcher Fehler: {e}")
            time.sleep(FILE_WATCH_INTERVAL)

    watcher_thread = threading.Thread(target=watcher, daemon=True, name="Integration-Watcher")
    watcher_thread.start()
    logger.info("Integration-Watcher gestartet")

# Starte Watcher beim Import - verzögert bis main.app existiert
# (Wird in main.py beim App-Start aufgerufen)
def _init_integration_watcher():
    """Initialisiert den Integration-Watcher (muss nach App-Start aufgerufen werden)."""
    try:
        _start_integration_watcher()
    except Exception as e:
        _get_hotreload_logger().warning(f"Integration-Watcher konnte nicht gestartet werden: {e}")
# --- VARIABLEN & KONFIGURATION ---
# Reduziere httpx/uvicorn Logging für sauberere Ausgabe
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
logging.getLogger('uvicorn.error').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
router = APIRouter()
# Standard-Modell aus der Config (Fallback: granite4:tiny-h)
DEFAULT_MODEL = config.get("ollama.default_model", "llama2:latest") #granite4:tiny-h
API_KEY_REQUIRED = config.get("api_key", "sysop")
_LAST_WHISPER_STATE: Optional[bool] = None
_DISCOVERY_CACHE: Dict[str, Any] = {"ts": None, "data": {}}
_CHAT_PROGRESS: Dict[str, Dict[str, Any]] = {}
_CHAT_PROGRESS_LOCK = threading.Lock()

class ChatCancelled(Exception):
    """Raised when a chat request has been cancelled by the user."""

def _find_program(program_name: str) -> Optional[str]:
    """Findet ein Programm auf dem System (Windows, Linux, macOS, Android)"""
    system = platform.system().lower()
    program_name_lower = program_name.lower()
    
    # 1. Zuerst mit shutil.which (PATH-Suche)
    found = shutil.which(program_name)
    if found:
        return found
    
    # 2. Bekannte Alternativen/Alternativnamen
    alternatives = {
        # Browser
        "chrome": ["chrome", "google-chrome", "google-chrome-stable", "chromium"],
        "firefox": ["firefox", "firefox.exe"],
        "edge": ["edge", "microsoft-edge", "msedge"],
        "opera": ["opera", "opera.exe"],
        "browser": ["chrome", "firefox", "edge", "opera", "brave", "vivaldi"],
        
        # Editoren
        "notepad": ["notepad", "notepad.exe", "gedit", "nano", "vim", "vi"],
        "editor": ["code", "notepad++", "sublime_text", "gedit", "vim", "nano"],
        "code": ["code", "codium", "vscode", "visual-studio-code"],
        "vscode": ["code", "codium", "vscode"],
        "sublime": ["sublime_text", "subl"],
        
        # Terminal
        "cmd": ["cmd", "cmd.exe"],
        "terminal": ["gnome-terminal", "konsole", "xterm", "termux", "cmd.exe"],
        "powershell": ["powershell", "pwsh", "powershell.exe"],
        "bash": ["bash", "sh"],
        
        # Systemtools
        "explorer": ["explorer", "explorer.exe", "nautilus", "dolphin", "thunar"],
        "rechner": ["calc", "gnome-calculator", "kcalc", "calculator"],
        "calculator": ["calc", "gnome-calculator", "kcalc"],
        "paint": ["mspaint", "paint", "pinta", "kolourpaint"],
        
        # Office
        "word": ["winword", "word", "libreoffice-writer", "writer"],
        "excel": ["excel", "libreoffice-calc", "calc"],
        "outlook": ["outlook", "thunderbird", "evolution"],
        
        # Andere
        "spotify": ["spotify", "spotify.exe"],
        "discord": ["discord", "discord.exe"],
        "telegram": ["telegram", "telegram-desktop"],
        "whatsapp": ["whatsapp", "whatsapp.exe"],
        "zoom": ["zoom", "zoom.exe"],
        "teams": ["teams", "microsoft-teams"],
    }
    
    # Prüfe Alternativen
    if program_name_lower in alternatives:
        for alt in alternatives[program_name_lower]:
            found = shutil.which(alt)
            if found:
                logger.info(f"🔧 Programm '{program_name}' gefunden als '{alt}' → {found}")
                return found
    
    # 3. Windows: Suche in Program Files
    if system == "windows":
        program_files = [
            os.environ.get("ProgramFiles", "C:\\Program Files"),
            os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", "C:\\Users\\Default\\AppData\\Local"),
        ]
        
        # Mögliche Ausführungsnamen
        exe_names = [f"{program_name}.exe", program_name]
        if program_name_lower in alternatives:
            exe_names.extend([f"{alt}.exe" for alt in alternatives[program_name_lower]])
        
        for pf in program_files:
            if not pf:
                continue
            pf_path = Path(pf)
            if not pf_path.exists():
                continue
            
            # Suche in Unterordnern
            for exe_name in set(exe_names):
                for exe_path in pf_path.rglob(exe_name):
                    if exe_path.is_file():
                        logger.info(f"🔧 Programm '{program_name}' gefunden in Windows: {exe_path}")
                        return str(exe_path)
    
    # 4. Linux/macOS: Suche in /usr/bin, /usr/local/bin, /opt
    elif system in ["linux", "darwin"]:
        search_paths = [
            "/usr/bin",
            "/usr/local/bin",
            "/opt",
            "/snap/bin",
        ]
        
        # Homebrew auf macOS
        if system == "darwin":
            search_paths.append("/opt/homebrew/bin")
            search_paths.append("/usr/local/opt")
        
        for search_path in search_paths:
            search_dir = Path(search_path)
            if not search_dir.exists():
                continue
            
            # Suche nach dem Programm
            for exe_path in search_dir.rglob(program_name):
                if exe_path.is_file() and os.access(exe_path, os.X_OK):
                    logger.info(f"🔧 Programm '{program_name}' gefunden: {exe_path}")
                    return str(exe_path)
            
            # Suche nach Alternativen
            if program_name_lower in alternatives:
                for alt in alternatives[program_name_lower]:
                    for exe_path in search_dir.rglob(alt):
                        if exe_path.is_file() and os.access(exe_path, os.X_OK):
                            logger.info(f"🔧 Programm '{program_name}' gefunden als '{alt}': {exe_path}")
                            return str(exe_path)
    
    # 5. Android (Termux)
    elif "android" in system or system == "android":
        # Android-Apps über pm list packages finden
        try:
            # Prüfe ob pm command verfügbar ist
            result = subprocess.run(["pm", "list", "packages"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                packages = result.stdout.lower()
                # Suche nach dem Programm in installierten Packages
                for line in packages.splitlines():
                    if program_name_lower in line:
                        package = line.split(":")[-1]
                        logger.info(f"🔧 Android-App '{program_name}' gefunden als Package: {package}")
                        return f"am start --user 0 {package}"
        except:
            pass
        
        # Termux-Commands
        termux_commands = {
            "vim": "vim", "nano": "nano", "python": "python", "git": "git",
            "curl": "curl", "wget": "wget",
        }
        if program_name_lower in termux_commands:
            found = shutil.which(termux_commands[program_name_lower])
            if found:
                return found
    
    logger.warning(f"⚠️ Programm '{program_name}' nicht gefunden auf {system}")
    return None

def _log_whisper_state(available: bool, models: List[str]) -> None:
    """Log Whisper status only on state changes to avoid polling noise."""
    global _LAST_WHISPER_STATE
    if _LAST_WHISPER_STATE is None:
        _LAST_WHISPER_STATE = available
        if not available:
            logger.warning("Whisper ist nicht verfügbar")
        return

    if available != _LAST_WHISPER_STATE:
        if available:
            logger.warning(f"Whisper wieder verfügbar ({', '.join(models) if models else 'läuft'})")
        else:
            logger.warning("Whisper ist ausgefallen")
        _LAST_WHISPER_STATE = available

def _extract_model_score(name: str) -> float:
    """Heuristic score for model size from its name (supports 1.2b, 24b, 70b)."""
    lowered = (name or "").lower()
    match = re.search(r"(\d+(?:\.\d+)?)\s*b", lowered)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return 0.0
    return 0.0

def _pick_best_model(
    available: List[str],
    hints: Optional[List[str]] = None,
    min_size: float = 0.0,
    max_size: Optional[float] = None,
) -> Optional[str]:
    """Pick strongest model by optional hints and minimum size."""
    if not available:
        return None

    pool = available
    if hints:
        hinted = [m for m in available if any(h in m.lower() for h in hints)]
        if hinted:
            pool = hinted

    strong = [m for m in pool if _extract_model_score(m) >= min_size]
    if strong:
        pool = strong
    if max_size and max_size > 0:
        capped = [m for m in pool if 0 < _extract_model_score(m) <= max_size]
        if capped:
            pool = capped

    return sorted(pool, key=_extract_model_score, reverse=True)[0] if pool else None

def _as_model_pref_list(raw: Any) -> List[str]:
    """Normalize model preference setting to a list of non-empty strings."""
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    text = str(raw).strip()
    if not text:
        return []
    if "," in text:
        return [part.strip() for part in text.split(",") if part.strip()]
    return [text]

def _pick_preferred_available(available: List[str], preferred: List[str]) -> Optional[str]:
    """Pick first preferred model present in available list (exact, then fuzzy contains)."""
    if not available or not preferred:
        return None
    available_by_lower = {m.lower(): m for m in available}
    for pref in preferred:
        exact = available_by_lower.get(pref.lower())
        if exact:
            return exact
    for pref in preferred:
        pref_l = pref.lower()
        for model in available:
            if pref_l in model.lower():
                return model
    return None

def _pick_fast_model(available: List[str]) -> Optional[str]:
    """Pick a fast/small model for routing/self-check tasks."""
    if not available:
        return None

    preferred = _as_model_pref_list(config.get("ollama.preferred_fast_models")) or _as_model_pref_list(
        config.get("ollama.preferred_fast_model")
    )
    preferred_fast = _pick_preferred_available(available, preferred)
    if preferred_fast:
        return preferred_fast

    fast_hints = ["lfm", "mini", "small", "tiny", "phi", "gemma:2b", "1.5b", "1.2b", "2b", "3b"]
    fast_candidates = [m for m in available if any(h in m.lower() for h in fast_hints)]
    if not fast_candidates:
        fast_candidates = available

    # Prefer smaller models; unknown size gets lowest priority by assigning high fallback score.
    def fast_key(name: str) -> float:
        score = _extract_model_score(name)
        return score if score > 0 else 9999.0

    return sorted(fast_candidates, key=fast_key)[0] if fast_candidates else None

def _extract_json_object(raw: str) -> Optional[Dict[str, Any]]:
    """Extract and parse first JSON object from a raw model response."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE).strip()
        text = re.sub(r"\s*```$", "", text).strip()

    # Direct JSON
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Best-effort object extraction
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    return None

def _extract_ollama_text(payload: Any) -> str:
    """Extract textual content from varied Ollama response shapes."""
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, dict):
        if "message" in payload:
            return _extract_ollama_text(payload.get("message"))
        if isinstance(payload.get("response"), str):
            return payload.get("response", "").strip()
        content = payload.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            chunks: List[str] = []
            for item in content:
                if isinstance(item, str):
                    chunks.append(item)
                elif isinstance(item, dict):
                    text_value = item.get("text") or item.get("content") or ""
                    if text_value:
                        chunks.append(str(text_value))
            return "\n".join(chunks).strip()
        return ""
    if isinstance(payload, list):
        chunks = [_extract_ollama_text(item) for item in payload]
        return "\n".join([c for c in chunks if c]).strip()
    return str(payload).strip()

async def _detect_and_execute_gui_command(message: str, token: str) -> Optional[Dict]:
    """Erkennt GUI-Befehle in natürlicher Sprache"""
    import re
    
    msg_lower = message.lower()
    
    # ===== VISION: Webcam-Foto + Analyse (NEU) =====
    # "was siehst du?" oder "was siehst du auf dem bild?" oder "webcam"
    vision_patterns = [
        r'(?:was\s+siehst\s+du|was\s+siehst\s+du\s+auf\s+dem\s+bild|was\s+erkennst\s+du)\s*\??',
        r'(?:zeig\s+mir\s+die\s+webcam|webcam\s+foto|kamera\s+foto|mach\s+webcam\s+foto)',
        r'(?:nimm\s+ein\s+foto\s+auf|mach\s+ein\s+webcam\s+foto|webcam\s+aufnahme)',
        r'^webcam$',
        r'^was\s+siehst\s+du\??$',
    ]
    
    for pattern in vision_patterns:
        if re.search(pattern, msg_lower, re.IGNORECASE):
            logger.info(f"🔧 Vision-Erkennung: '{message}' → Webcam-Foto + Analyse")
            # Rufe vision command auf (ohne Argumente = Webcam)
            return await handle_command("/vision", token)
    
    # ===== WEB-AUTOMATION (Headless) =====
    web_analyze_pattern = re.search(r'(?:analysiere|untersuche|scanne|schau dir an)\s+(https?://[^\s]+|[a-z0-9.-]+\.[a-z]{2,})', msg_lower, re.IGNORECASE)
    if web_analyze_pattern:
        url = web_analyze_pattern.group(1)
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        logger.info(f"🔧 Web-Automation: '{message}' → Headless Analyse von {url}")
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8000/api/web/goto",
                    json={"url": url, "headless": True, "learn": True},
                    headers={"token": token},
                    timeout=60
                )
                return response.json()
        except Exception as e:
            logger.error(f"Web-Automation Fehler: {e}")
            return {"status": "error", "reply": f"❌ Analyse fehlgeschlagen: {e}"}
    
    # ===== URL öffnen (sichtbarer Browser) =====
    url_patterns = [
        re.compile(r'(?:goto|öffne|gehe\s+zu)\s+(https?://[^\s]+)', re.IGNORECASE),
        re.compile(r'(?:goto|öffne|gehe\s+zu)\s+([a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/\S*)?)', re.IGNORECASE),
        re.compile(r'^(https?://[^\s]+)', re.IGNORECASE),
        re.compile(r'^([a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(?:/\S*)?)$', re.IGNORECASE),
    ]
    
    for pattern in url_patterns:
        match = pattern.search(msg_lower)
        if match:
            url = match.group(1)
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            logger.info(f"🔧 GUI-Erkennung (URL): '{message}' → /gui goto {url}")
            return await handle_command(f"/gui goto {url}", token)
    
    # ===== Screenshot =====
    if re.search(r'(?:mach|erstelle|take|make)\s+(?:einen\s+)?screenshot', msg_lower, re.IGNORECASE):
        logger.info(f"🔧 GUI-Erkennung (Screenshot): '{message}' → /gui screenshot")
        return await handle_command("/gui screenshot", token)
    
    # ===== Programme öffnen =====
    open_pattern = re.search(r'(?:öffne|starte|open|launch)\s+([a-zA-Z0-9\s\-]+?)(?:\s|$)', msg_lower, re.IGNORECASE)
    if open_pattern:
        program_name = open_pattern.group(1).strip()
        program_name = re.sub(r'\s*(?:bitte|mal|jetzt|schnell)$', '', program_name)
        
        if program_name:
            logger.info(f"🔧 GUI-Erkennung (Programm): '{message}' → /gui open {program_name}")
            return await handle_command(f"/gui open {program_name}", token)
    
    return None


async def _ollama_chat_async(*, model: str, messages: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """Run blocking Ollama chat call in worker thread."""
    return await asyncio.to_thread(ollama_client.chat, model=model, messages=messages, **kwargs)

async def _ollama_generate_async(*, model: str, prompt: str, **kwargs) -> Dict[str, Any]:
    """Run blocking Ollama generate call in worker thread."""
    return await asyncio.to_thread(ollama_client.generate, model=model, prompt=prompt, **kwargs)

async def _ollama_list_models_async() -> Dict[str, Any]:
    """Run blocking Ollama model listing in worker thread."""
    return await asyncio.to_thread(ollama_client.list_models)

async def _execute_llm_shell_commands(reply: str, token: str, thinking_steps: list, request_id: str) -> str:
    """
    Scannt die LLM-Antwort auf /shell-Befehle, /gui-Befehle UND ```shell Code-Blöcke und führt sie aus.
    Ersetzt die Befehle durch ihre tatsächliche Ausgabe.
    """
    import re as _re
    import platform

    DANGEROUS = ["rm -rf /", "format c:", "del /f /s /q c:\\", "mkfs", ":(){ :|: & };:"]

    async def _run_cmd(cmd: str, is_gui: bool = False) -> str:
        """Führt einen Shell- oder GUI-Befehl aus"""
        cmd = cmd.strip()
        if not cmd:
            return ""
        
        # Sicherheitscheck
        if any(d in cmd.lower() for d in DANGEROUS):
            logger.warning(f"🚫 Gefährlicher Befehl blockiert: {cmd}")
            return f"❌ Blockiert (Sicherheit): `{cmd}`"

        cmd_type = "GUI" if is_gui else "Shell"
        logger.info(f"🤖 LLM {cmd_type}-Befehl auto-execute: {cmd}")
        thinking_steps.append({
            "text": f"Auto-Execute {cmd_type}: {cmd}", 
            "icon": "fa-terminal" if not is_gui else "fa-desktop", 
            "time": datetime.now().isoformat()
        })

        try:
            if is_gui:
                cmd_result = await handle_command(f"/gui {cmd}", token)
            else:
                cmd_result = await handle_command(f"/shell {cmd}", token)
            
            stdout = (cmd_result.get("stdout") or cmd_result.get("reply") or "").strip()
            stderr = (cmd_result.get("stderr") or "").strip()
            
            if stdout and stderr:
                return f"\n```\n{stdout}\n⚠️ {stderr}\n```"
            elif stdout:
                return f"\n```\n{stdout}\n```"
            elif stderr:
                return f"\n⚠️ Stderr: {stderr}"
            else:
                return f"\n✅ Ausgeführt: `{cmd}`"
        except Exception as e:
            return f"\n❌ Fehler bei `{cmd}`: {e}"

async def _execute_llm_shell_commands(reply: str, token: str, thinking_steps: list, request_id: str) -> str:
    """
    Scannt die LLM-Antwort auf /shell-Befehle, /gui-Befehle UND ```shell Code-Blöcke und führt sie aus.
    Ersetzt die Befehle durch ihre tatsächliche Ausgabe.
    """
    import re as _re
    import platform

    # Definition der gefährlichen Befehle
    DANGEROUS = ["rm -rf /", "format c:", "del /f /s /q c:\\", "mkfs", ":(){ :|: & };:"]

    async def _run_cmd(cmd: str, is_gui: bool = False) -> str:
        """Führt einen Shell- oder GUI-Befehl aus"""
        cmd = cmd.strip()
        if not cmd:
            return ""
        
        # Sicherheitscheck
        if any(d in cmd.lower() for d in DANGEROUS):
            logger.warning(f"🚫 Gefährlicher Befehl blockiert: {cmd}")
            return f"❌ Blockiert (Sicherheit): `{cmd}`"

        cmd_type = "GUI" if is_gui else "Shell"
        logger.info(f"🤖 LLM {cmd_type}-Befehl auto-execute: {cmd}")
        thinking_steps.append({
            "text": f"Auto-Execute {cmd_type}: {cmd}", 
            "icon": "fa-terminal" if not is_gui else "fa-desktop", 
            "time": datetime.now().isoformat()
        })

        try:
            if is_gui:
                cmd_result = await handle_command(f"/gui {cmd}", token)
            else:
                cmd_result = await handle_command(f"/shell {cmd}", token)
            
            stdout = (cmd_result.get("stdout") or cmd_result.get("reply") or "").strip()
            stderr = (cmd_result.get("stderr") or "").strip()
            
            if stdout and stderr:
                return f"\n```\n{stdout}\n⚠️ {stderr}\n```"
            elif stdout:
                return f"\n```\n{stdout}\n```"
            elif stderr:
                return f"\n⚠️ Stderr: {stderr}"
            else:
                return f"\n✅ Ausgeführt: `{cmd}`"
        except Exception as e:
            return f"\n❌ Fehler bei `{cmd}`: {e}"

    # Pattern für Shell-Befehle (inline)
    inline_pattern = _re.compile(r'(?:(?<!\w)/execute\s+)?/shell\s+(.+?)(?=\n|$)', _re.IGNORECASE)

    # Pattern für GUI-Befehle
    gui_pattern = _re.compile(r'/gui\s+(.+?)(?=\n|$)', _re.IGNORECASE)

    # Pattern für Code-Blöcke
    block_pattern = _re.compile(r'```(?:shell|bash|cmd|powershell|batch)\s*\n(.*?)```', _re.DOTALL | _re.IGNORECASE)

    # NEU: Pattern für natürliche Sprache (Shell-Erkennung)
    system_os = platform.system()
    dir_cmd = "dir" if system_os == "Windows" else "ls -la"
    
    natural_patterns = [
        # Datei-Listen Befehle
        (_re.compile(r'(?:zeig|list|show)\s+(?:mir\s+)?(?:alle\s+)?python\s+dateien', _re.IGNORECASE), 
         f"/shell {dir_cmd} *.py"),
        (_re.compile(r'(?:zeig|list|show)\s+(?:mir\s+)?(?:alle\s+)?dateien', _re.IGNORECASE), 
         f"/shell {dir_cmd}"),
        (_re.compile(r'(?:welche|liste)\s+(?:python\s+)?dateien', _re.IGNORECASE), 
         f"/shell {dir_cmd} *.py"),
        # Datei-Erstellungs Befehle
        (_re.compile(r'(?:erstelle|create)\s+(?:die\s+)?datei\s+(\S+)', _re.IGNORECASE), 
         r"/shell echo '' > {}"),
        # Datei-Lösch Befehle
        (_re.compile(r'(?:lösche|delete|remove)\s+(?:die\s+)?datei\s+(\S+)', _re.IGNORECASE), 
         r"/shell del {}" if system_os == "Windows" else r"/shell rm {}"),
    ]

    # Prüfe zuerst auf natürliche Sprache (höchste Priorität)
    reply_lower = reply.lower()
    for pattern, cmd_template in natural_patterns:
        match = pattern.search(reply_lower)
        if match:
            if "{}" in cmd_template:
                filename = match.group(1) if match.groups() else "datei.txt"
                new_reply = cmd_template.format(filename)
            else:
                new_reply = cmd_template
            
            thinking_steps.append({
                "text": f"🔧 Auto-Konvertierung: '{match.group(0)}' → {new_reply}",
                "icon": "fa-magic",
                "time": datetime.now().isoformat()
            })
            reply = new_reply
            break

    # Prüfe ob überhaupt Befehle vorhanden sind
    has_inline = bool(inline_pattern.search(reply))
    has_gui = bool(gui_pattern.search(reply))
    has_block = bool(block_pattern.search(reply))

    if not has_inline and not has_block and not has_gui:
        return reply

    # Process GUI commands first
    if has_gui:
        result_parts = []
        last_end = 0
        for match in gui_pattern.finditer(reply):
            cmd = match.group(1).strip()
            result_parts.append(reply[last_end:match.start()])
            output = await _run_cmd(cmd, is_gui=True)
            result_parts.append(output)
            last_end = match.end()
        result_parts.append(reply[last_end:])
        reply = "".join(result_parts)

    # Process code blocks first (replace blocks with output)
    if has_block:
        new_reply_parts = []
        last = 0
        for m in block_pattern.finditer(reply):
            code = m.group(1).strip()
            lines = [l.strip() for l in code.splitlines() if l.strip() and not l.strip().startswith('#')]
            new_reply_parts.append(reply[last:m.start()])
            for line in lines:
                output = await _run_cmd(line, is_gui=False)
                new_reply_parts.append(output)
            last = m.end()
        new_reply_parts.append(reply[last:])
        reply = "".join(new_reply_parts)

    # Process inline /shell commands
    if has_inline:
        result_parts = []
        last_end = 0
        for match in inline_pattern.finditer(reply):
            cmd = match.group(1).strip()
            result_parts.append(reply[last_end:match.start()])
            output = await _run_cmd(cmd, is_gui=False)
            result_parts.append(output)
            last_end = match.end()
        result_parts.append(reply[last_end:])
        reply = "".join(result_parts)

    return reply

    # Process GUI commands first
    if has_gui:
        result_parts = []
        last_end = 0
        for match in gui_pattern.finditer(reply):
            cmd = match.group(1).strip()
            result_parts.append(reply[last_end:match.start()])
            output = await _run_cmd(cmd, is_gui=True)
            result_parts.append(output)
            last_end = match.end()
        result_parts.append(reply[last_end:])
        reply = "".join(result_parts)

    # Process code blocks first (replace blocks with output)
    if has_block:
        new_reply_parts = []
        last = 0
        for m in block_pattern.finditer(reply):
            code = m.group(1).strip()
            # Only execute if it's a single-line command or explicit shell block
            lines = [l.strip() for l in code.splitlines() if l.strip() and not l.strip().startswith('#')]
            new_reply_parts.append(reply[last:m.start()])
            for line in lines:
                output = await _run_cmd(line)
                new_reply_parts.append(output)
            last = m.end()
        new_reply_parts.append(reply[last:])
        reply = "".join(new_reply_parts)

    # Process inline /shell commands
    if has_inline:
        result_parts = []
        last_end = 0
        for match in inline_pattern.finditer(reply):
            cmd = match.group(1).strip()
            result_parts.append(reply[last_end:match.start()])
            output = await _run_cmd(cmd)
            result_parts.append(output)
            last_end = match.end()
        result_parts.append(reply[last_end:])
        reply = "".join(result_parts)

    return reply

async def _detect_and_execute_shell_command(message: str, token: str) -> Optional[Dict]:
    """Plattformunabhängige Shell-Erkennung für Windows, Linux und Android"""
    import platform
    import re
    
    system_os = platform.system().lower()
    
    # Plattform-Erkennung
    if system_os == "windows":
        platform_type = "windows"
        dir_cmd = "dir"
        list_cmd = "dir"
        file_cmd = "type"
        del_cmd = "del"
        copy_cmd = "copy"
        move_cmd = "move"
        mkdir_cmd = "mkdir"
        rmdir_cmd = "rmdir"
        process_cmd = "tasklist"
        kill_cmd = "taskkill /F /IM"
        network_cmd = "ipconfig"
        system_cmd = "systeminfo"
        path_sep = "\\"
        find_cmd = "findstr"
    elif system_os == "linux":
        platform_type = "linux"
        dir_cmd = "ls -la"
        list_cmd = "ls"
        file_cmd = "cat"
        del_cmd = "rm"
        copy_cmd = "cp"
        move_cmd = "mv"
        mkdir_cmd = "mkdir"
        rmdir_cmd = "rmdir"
        process_cmd = "ps aux"
        kill_cmd = "killall"
        network_cmd = "ifconfig"
        system_cmd = "uname -a"
        path_sep = "/"
        find_cmd = "grep"
    elif system_os == "android" or "android" in system_os:
        platform_type = "android"
        dir_cmd = "ls -la"
        list_cmd = "ls"
        file_cmd = "cat"
        del_cmd = "rm"
        copy_cmd = "cp"
        move_cmd = "mv"
        mkdir_cmd = "mkdir"
        rmdir_cmd = "rmdir"
        process_cmd = "ps"
        kill_cmd = "kill"
        network_cmd = "netstat"
        system_cmd = "getprop"
        path_sep = "/"
        find_cmd = "grep"
    else:
        # Fallback auf Linux-ähnlich
        platform_type = "unix"
        dir_cmd = "ls -la"
        list_cmd = "ls"
        file_cmd = "cat"
        del_cmd = "rm"
        copy_cmd = "cp"
        move_cmd = "mv"
        mkdir_cmd = "mkdir"
        rmdir_cmd = "rmdir"
        process_cmd = "ps aux"
        kill_cmd = "kill"
        network_cmd = "ifconfig"
        system_cmd = "uname -a"
        path_sep = "/"
        find_cmd = "grep"
    
    msg_lower = message.lower()
    
    # ===== KOMPLETTE BEFEHLS-MAPPING =====
    command_map = {
        # === DATEI-OPERATIONEN ===
        # Dateien anzeigen
        r'(?:zeig|list|show)\s+(?:mir\s+)?(?:alle\s+)?python\s+dateien': 
            f"{dir_cmd} *.py",
        r'(?:zeig|list|show)\s+(?:mir\s+)?(?:alle\s+)?text\s+dateien': 
            f"{dir_cmd} *.txt",
        r'(?:zeig|list|show)\s+(?:mir\s+)?(?:alle\s+)?dateien': 
            dir_cmd,
        r'(?:zeig|list|show)\s+(?:mir\s+)?(?:alle\s+)?\w+\s+dateien': 
            None,  # Dynamisch
        r'(?:zeig|list|show)\s+(?:mir\s+)?(?:das\s+)?verzeichnis': 
            dir_cmd,
        r'(?:was\s+ist\s+)?(?:im\s+)?aktuellen\s+ordner': 
            dir_cmd,
        
        # Datei lesen
        r'(?:zeig|lies|read)\s+(?:mir\s+)?(?:die\s+)?datei\s+(\S+)': 
            f"{file_cmd} {{}}",
        
        # Datei erstellen (LEER)
        r'(?:erstelle|create)\s+(?:die\s+)?datei\s+(\S+)(?!\s+mit\s+inhalt)': 
            f"echo '' > {{}}",
        
        # Datei erstellen (MIT INHALT)
        r'(?:erstelle|create)\s+(?:die\s+)?datei\s+(\S+)\s+mit\s+inhalt\s+(.+)': 
            f"echo {{}} > {{}}",
        
        # Datei löschen
        r'(?:lösche|delete|remove)\s+(?:die\s+)?datei\s+(\S+)': 
            f"{del_cmd} {{}}",
        
        # Datei kopieren
        r'(?:kopiere|copy)\s+(?:die\s+)?datei\s+(\S+)\s+(?:nach|zu)\s+(\S+)': 
            f"{copy_cmd} {{}} {{}}",
        
        # Datei verschieben
        r'(?:verschiebe|move)\s+(?:die\s+)?datei\s+(\S+)\s+(?:nach|zu)\s+(\S+)': 
            f"{move_cmd} {{}} {{}}",
        
        # Ordner erstellen
        r'(?:erstelle|create)\s+(?:den\s+)?ordner\s+(\S+)': 
            f"{mkdir_cmd} {{}}",
        
        # Ordner löschen
        r'(?:lösche|delete|remove)\s+(?:den\s+)?ordner\s+(\S+)': 
            f"{rmdir_cmd} {{}}",
        
        # === SYSTEM-OPERATIONEN ===
        # Prozesse anzeigen
        r'(?:zeig|list|show)\s+(?:mir\s+)?(?:alle\s+)?prozesse': 
            process_cmd,
        
        # Prozess beenden
        r'(?:beende|kill|stop)\s+(?:den\s+)?prozess\s+(\S+)': 
            f"{kill_cmd} {{}}",
        
        # Systeminfo
        r'(?:zeig|list|show)\s+(?:mir\s+)?system(?:info)?': 
            system_cmd,
        
        # Speicher
        r'(?:wie\s+viel\s+)?speicher\s+(?:frei|verfügbar)': 
            "df -h" if platform_type != "windows" else "wmic OS get FreePhysicalMemory",
        
        # CPU
        r'(?:cpu|cpu\s+auslastung)': 
            "top -bn1 | grep 'Cpu'" if platform_type != "windows" else "wmic cpu get loadpercentage",
        
        # === NETZWERK-OPERATIONEN ===
        # Netzwerk
        r'(?:zeig|list|show)\s+(?:mir\s+)?netzwerk': 
            network_cmd,
        
        # IP-Adresse
        r'(?:zeig|list|show)\s+(?:mir\s+)?ip(?:-adresse)?': 
            network_cmd,
        
        # Ping
        r'(?:pinge|ping)\s+(\S+)': 
            "ping {{}}",
        
        # === VERZEICHNIS-OPERATIONEN ===
        # Aktuelles Verzeichnis
        r'(?:wo\s+bin\s+ich|aktuelles\s+verzeichnis)': 
            "cd" if platform_type == "windows" else "pwd",
        
        # In Verzeichnis wechseln
        r'(?:gehe|wechsel)\s+(?:ins|in)\s+verzeichnis\s+(\S+)': 
            "cd {{}} && pwd",
        
        # === SUCHE ===
        # In Dateien suchen
        r'(?:suche|search)\s+(?:in\s+)?dateien\s+nach\s+(\S+)': 
            f"{find_cmd} {{}} *",
        
        # === COMPRESS ===
        # ZIP erstellen
        r'(?:erstelle|create)\s+zip\s+(\S+)\s+(?:aus\s+)?(\S+)': 
            "zip {{}} {{}}",
        
        # === ANDROID SPEZIFISCH ===
        # Android: Apps anzeigen
        r'(?:zeig|list|show)\s+(?:mir\s+)?(?:alle\s+)?apps': 
            "pm list packages",
        
        # Android: Akku
        r'(?:akku|battery)': 
            "dumpsys battery",
        
        # Android: Speicher
        r'(?:speicher|storage)': 
            "df -h",
    }
    
    # 1. Exakte Muster prüfen
    for pattern, cmd_template in command_map.items():
        if cmd_template is None:
            continue
            
        match = re.search(pattern, msg_lower, re.IGNORECASE)
        if match:
            if "{}" in cmd_template:
                groups = match.groups()
                # Entferne None-Werte
                groups = [g for g in groups if g is not None]
                
                placeholder_count = cmd_template.count("{}")
                
                if len(groups) == 1 and placeholder_count == 1:
                    cmd = cmd_template.format(groups[0])
                elif len(groups) == 1 and placeholder_count == 2:
                    # Zwei Platzhalter, eine Gruppe (leere Datei)
                    cmd = cmd_template.format("", groups[0])
                elif len(groups) == 2:
                    # Zwei Gruppen: Dateiname und Inhalt
                    # Bei "echo {} > {}": zuerst Inhalt, dann Dateiname
                    if "echo" in cmd_template and ">" in cmd_template:
                        cmd = cmd_template.format(groups[1], groups[0])
                    else:
                        cmd = cmd_template.format(groups[0], groups[1])
                else:
                    cmd = cmd_template
            else:
                cmd = cmd_template
            
            logger.info(f"🔧 [{platform_type.upper()}] Erkannte Anfrage: '{message}' → /shell {cmd}")
            result = await handle_command(f"/shell {cmd}", token)
            if isinstance(result, dict):
                result["auto_detected"] = True
                result["platform"] = platform_type
                result["original_query"] = message
                result["executed_command"] = cmd
            return result
    
    # 2. Dynamische Dateityp-Erkennung
    file_type_map = {
        "python": "py", "text": "txt", "json": "json", "markdown": "md",
        "yaml": "yaml", "yml": "yml", "javascript": "js", "typescript": "ts",
        "html": "html", "css": "css", "xml": "xml", "csv": "csv",
        "log": "log", "jpg": "jpg", "jpeg": "jpeg", "png": "png", "gif": "gif",
        "pdf": "pdf", "doc": "doc", "docx": "docx", "xls": "xls", "xlsx": "xlsx",
        "zip": "zip", "tar": "tar", "gz": "gz", "exe": "exe", "dll": "dll",
        "so": "so", "apk": "apk", "sh": "sh", "bat": "bat", "ps1": "ps1",
    }
    
    # "zeig mir alle [typ] dateien"
    dynamic_match = re.search(r'(?:zeig|list|show)\s+(?:mir\s+)?(?:alle\s+)?(\w+)\s+dateien', msg_lower, re.IGNORECASE)
    if dynamic_match:
        file_type = dynamic_match.group(1).lower()
        if file_type in file_type_map:
            ext = file_type_map[file_type]
            cmd = f"{dir_cmd} *.{ext}"
            logger.info(f"🔧 [{platform_type.upper()}] Dynamische Erkennung: '{message}' → /shell {cmd}")
            result = await handle_command(f"/shell {cmd}", token)
            if isinstance(result, dict):
                result["auto_detected"] = True
                result["platform"] = platform_type
            return result
    
    return None

# ===== LLM-BASIERTE SHELL-ERKENNUNG =====

async def _is_shell_intent(user_message: str) -> bool:
    """Lässt LLM entscheiden, ob es ein Shell-Befehl ist"""
    
    # Hole verfügbare Modelle
    try:
        models_info = ollama_client.list_models()
        available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
        fast_model = _pick_fast_model(available) or DEFAULT_MODEL
    except Exception:
        fast_model = DEFAULT_MODEL
    
    prompt = f"""Entscheide ob folgende Anfrage ein System-/Shell-Befehl ist.
Antworte nur mit JA oder NEIN.

Anfrage: {user_message}

Ist das ein Befehl zum Erstellen/Löschen/Anzeigen von Dateien oder System-Abfragen?"""

    try:
        response = await _ollama_chat_async(
            model=fast_model,
            messages=[{"role": "user", "content": prompt}],
            options={"num_predict": 10}
        )
        reply = _extract_ollama_text(response).strip().upper()
        return "JA" in reply
    except Exception:
        return False


async def _generate_shell_command(user_message: str) -> Optional[str]:
    """LLM generiert den korrekten Shell-Befehl"""
    
    # Hole verfügbare Modelle
    try:
        models_info = ollama_client.list_models()
        available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
        fast_model = _pick_fast_model(available) or DEFAULT_MODEL
    except Exception:
        fast_model = DEFAULT_MODEL
    
    prompt = f"""Generiere den korrekten Shell-Befehl für Windows für folgende Anfrage.
Gib NUR den Befehl zurück, keine Erklärung.

Anfrage: {user_message}

Beispiele:
- "zeig alle python dateien" → dir *.py
- "erstelle datei test.txt mit inhalt Hallo" → echo Hallo > test.txt
- "lösche datei alte.txt" → del alte.txt

Befehl:"""

    try:
        response = await _ollama_chat_async(
            model=fast_model,
            messages=[{"role": "user", "content": prompt}],
            options={"num_predict": 50, "temperature": 0}
        )
        cmd = _extract_ollama_text(response).strip()
        # Entferne Markdown und Anführungszeichen
        cmd = re.sub(r'^```.*?\n', '', cmd)
        cmd = re.sub(r'\n```$', '', cmd)
        cmd = cmd.strip('"\'')
        return cmd if cmd else None
    except Exception:
        return None

def _run_fast_router_check(user_message: str, available: List[str], progress_id: Optional[str] = None) -> Dict[str, Any]:
    """Verbesserte Router-Check mit Intent-Erkennung"""
    
    if not user_message:
        return {"checked": False}
    
    # 1. Intent-Erkennung
    # intent_result = _classify_intent(user_message)
    intent_result = _classify_intent_enhanced(user_message)
    logger.debug(f"Intent: {intent_result['intent']} ({intent_result['confidence']:.2f}) - {user_message[:50]}")

    # INTENT-LOGGING
    # print(f"\n{'='*50}")
    # print(f"📝 USER: {user_message}")
    # print(f"🎯 INTENT: {intent_result['intent']} (Confidence: {intent_result['confidence']:.2f})")
    # print(f"{'='*50}\n")
    logger.info(f"{'='*50}")
    logger.info(f"📝 USER: {user_message}")
    logger.info(f"🎯 INTENT: {intent_result['intent']} (Confidence: {intent_result['confidence']:.2f})")
    logger.info(f"{'='*50}")


    # 2. Entity-Extraktion (optional, für Kontext)
    entities = _extract_entities(user_message)
    
    # 3. Bei hoher Confidence: Intent-basiertes Routing
    if intent_result.get("confidence", 0) > 0.6:
        domain = intent_result["intent"]
        
        # Intent-basierte Komplexität
        complexity_map = {
            "shell": "low",
            "creative": "low", 
            "vision": "medium",
            "code": "medium",
            "search": "medium",
            "chat": "low"
        }
        
        # Intent-basiertes prefer_fast
        prefer_fast_map = {
            "shell": True,
            "creative": True,
            "chat": True,
            "vision": False,
            "code": False,
            "search": False
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
    
    # 4. Fallback: Originale Keyword-basierte Logik
    msg = (user_message or "").lower().strip()
    
    SHELL_KEYWORDS = [
        "erstelle datei", "zeig dateien", "verzeichnis", "zeig mir alle", 
        "lösche", "kopiere", "verschiebe", "installiere", "starte", 
        "stoppe", "prozesse", "systeminfo", "create file", "list files", 
        "show files", "zeig python dateien", "zeig alle dateien", 
        "welche dateien", "liste dateien", "zeig mir python dateien"
    ]
    
    if any(kw in msg for kw in SHELL_KEYWORDS):
        return {"checked": True, "router_model": "keyword", "complexity": "low",
                "domain": "ops", "self_question": False, "prefer_fast": True}
    
    CODE_KEYWORDS = ["schreib code", "programmiere", "erstelle ein skript", "html", 
                     "python script", "funktion", "klasse", "algorithmus", "implementiere"]
    
    if any(kw in msg for kw in CODE_KEYWORDS):
        return {"checked": True, "router_model": "keyword", "complexity": "medium",
                "domain": "code", "self_question": False, "prefer_fast": False}
    
    if len(msg.split()) < 8:
        return {"checked": True, "router_model": "keyword", "complexity": "low",
                "domain": "general", "self_question": False, "prefer_fast": True}
    
    return {"checked": False, "router_model": None, "complexity": "medium",
            "domain": "general", "self_question": False, "prefer_fast": False}

def _is_complex_request(msg: str) -> bool:
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

def _auto_select_model(
    user_message: str,
    requested_model: Optional[str] = None,
    progress_id: Optional[str] = None,
) -> str:  # Changed: returns only the model name string
    """Wählt das Modell: komplex/code => stark, smalltalk/einfache Fragen => schnell.
    WICHTIG: Wenn der User explizit ein Modell gewählt hat, wird es IMMER verwendet.
    Rückgabe: gewähltes_modell (als String)"""

    # DEBUG
    logger.info(f"_auto_select_model aufgerufen - requested_model: {requested_model!r}")

    # === USER-WAHL RESPEKTIEREN ===
    # Wenn der User ein konkretes Modell gewählt hat (nicht __AUTO__, nicht None),
    # verwenden wir es direkt – ohne jegliches Auto-Routing.
    if requested_model and requested_model.strip() not in ("__AUTO__", "auto", ""):
        selected = requested_model.strip()
        logger.info(f"Model-Routing: User-Wahl respektiert -> {selected}")
        _progress_add(progress_id, f"Gateway Model-Routing: {selected}", "fa-code-branch")
        return selected

    # === VISION PRIORISIERUNG NUR BEI EXPLIZITEN BILD-BEFEHLEN ===
    msg_lower = (user_message or "").lower().strip()
    
    # Nur wenn explizit nach Webcam/Bildanalyse gefragt wird
    is_explicit_vision = any(kw in msg_lower for kw in [
        "webcam", "foto machen", "bild analysieren", "screenshot",
        "was siehst du auf dem bild", "erkennst du auf dem bild",
        "mach ein foto", "webcam foto"
    ])
    
    if is_explicit_vision:
        try:
            models_info = ollama_client.list_models()
            available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
        except Exception:
            available = []
        
        # Lade bevorzugte Vision-Modelle aus der Config
        preferred_vision = _as_model_pref_list(config.get("ollama.preferred_vision_models")) or []
        
        if preferred_vision:
            vision_model = _pick_preferred_available(available, preferred_vision)
            if vision_model:
                logger.info(f"Model-Routing: vision request -> {vision_model}")
                _progress_add(progress_id, f"Gateway Model-Routing (Vision): {vision_model}", "fa-eye")
                return vision_model
        
        # Fallback: Versuche ein Vision-Modell anhand von Namen zu erkennen
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
        try:
            models_info = ollama_client.list_models()
            available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
        except Exception:
            available = []
        
        # Lade bevorzugte Vision-Modelle aus der Config
        preferred_vision = _as_model_pref_list(config.get("ollama.preferred_vision_models")) or []
        
        if preferred_vision:
            vision_model = _pick_preferred_available(available, preferred_vision)
            if vision_model:
                logger.info(f"Model-Routing: vision request -> {vision_model}")
                _progress_add(progress_id, f"Gateway Model-Routing (Vision): {vision_model}", "fa-eye")
                return vision_model
        
        # Fallback: Versuche ein Vision-Modell anhand von Namen zu erkennen
        # Erweiterte Vision-Hints für Ollama
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
        
        # Wenn kein Vision-Modell gefunden, logge Warnung und fahre mit normaler Logik fort
        logger.warning(f"No vision model found for request: {user_message}")
        _progress_add(progress_id, "⚠️ Kein Vision-Modell verfügbar, verwende Standard-Modell", "fa-exclamation-triangle")

    # Ab hier: __AUTO__ Modus – Gateway wählt selbst
    try:
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

    # Kein explizit gewähltes Modell → Auto-Routing nach Komplexität
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
    """Prüft ob ein anderes Modell besser geeignet wäre (nur für Vorschläge)."""
    try:
        models_info = ollama_client.list_models()
        available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
    except Exception:
        return None

    if not available:
        return None

    msg = (user_message or "").lower().strip()

    # Code-Signale prüfen
    code_signals = [
        "code", "python", "html", "script", "programm", "css", "sql", "api",
        "backend", "frontend", "webseite", "website", "ui", "layout",
    ]
    is_code = any(sig in msg for sig in code_signals)

    # Komplexitäts-Signale
    is_complex = _is_complex_request(msg)

    # Wenn aktuelles Modell schon ein Code-Modell ist
    coder_hints = ["coder", "code", "starcoder", "deepseek-coder", "qwen2.5-coder"]
    current_is_code = any(hint in current_model.lower() for hint in coder_hints)

    # Vorschläge machen
    if is_code and not current_is_code:
        preferred = _as_model_pref_list(config.get("ollama.preferred_code_models"))
        suggested = _pick_preferred_available(available, preferred)
        return suggested

    if is_complex:
        # Für komplexe Anfragen größeres Modell vorschlagen
        complex_models = [m for m in available if any(x in m.lower() for x in ["70b", "32b", "8b", "coder", "mistral"])]
        if complex_models and current_model not in complex_models:
            return complex_models[0]

    return None

def _normalize_telegram_chat_id(raw_id: Any) -> Optional[Any]:
    """Normalize chat id from config/session to int or @name string."""
    if raw_id is None:
        return None
    if isinstance(raw_id, int):
        return raw_id
    text = str(raw_id).strip()
    if not text:
        return None
    if text.lstrip("-").isdigit():
        return int(text)
    if text.startswith("@"):
        return text
    return f"@{text}"

def _should_enable_self_qa(user_message: str, router_hint: Optional[Dict[str, Any]] = None) -> bool:
    """Enable lightweight self-questioning for complex or explicitly requested deep tasks."""
    msg = (user_message or "").lower().strip()
    if not msg:
        return False
    explicit_terms = [
        "perfekt",
        "gründlich",
        "genau",
        "denke",
        "denk",
        "schritt",
        "plan",
        "strategie",
        "analys",
        "prüf",
    ]
    explicit = any(t in msg for t in explicit_terms)
    complex_hint = bool((router_hint or {}).get("complexity") == "high")
    return explicit or complex_hint or _is_complex_request(msg)

def _run_self_qa_precheck(
    user_message: str,
    available: List[str],
    router_hint: Optional[Dict[str, Any]] = None,
    progress_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build compact internal Q/A context with a fast model and expose steps for UI tracing.
    """
    if not _should_enable_self_qa(user_message, router_hint):
        return {"analysis_context": "", "thinking_steps": []}

    thinking_steps: List[Dict[str, str]] = []
    fast_model = _pick_fast_model(available) or DEFAULT_MODEL
    now_iso = datetime.now().isoformat()
    thinking_steps.append(
        {
            "text": f"Gateway startet interne Selbstfragen mit {fast_model}",
            "icon": "fa-brain",
            "time": now_iso,
        }
    )
    _progress_add(progress_id, f"Self-QA startet mit {fast_model}", "fa-brain")

    try:
        _ensure_not_cancelled(progress_id)
        planner_messages = [
            {
                "role": "system",
                "content": (
                    "Erzeuge nur JSON: {\"questions\":[\"...\",\"...\"]}. "
                    "Maximal 2 kurze interne Rueckfragen, die helfen die Nutzeranfrage besser zu loesen."
                ),
            },
            {"role": "user", "content": user_message},
        ]
        planner_resp = ollama_client.chat(
            model=fast_model,
            messages=planner_messages,
            options={"temperature": 0, "num_predict": 100},
        )
        _ensure_not_cancelled(progress_id)
        planner_raw = planner_resp.get("message", {}).get("content", "")
        planner_obj = _extract_json_object(planner_raw) or {}
        raw_questions = planner_obj.get("questions", [])
        questions = [str(q).strip() for q in raw_questions if str(q).strip()][:2]
        if not questions:
            questions = [
                "Was ist das konkrete Ziel der Nutzeranfrage?",
                "Welche Annahmen muss ich absichern, damit die Antwort korrekt ist?",
            ]

        qa_lines = []
        for idx, q in enumerate(questions, 1):
            _ensure_not_cancelled(progress_id)
            thinking_steps.append(
                {
                    "text": f"Selbstfrage {idx}: {q}",
                    "icon": "fa-question-circle",
                    "time": datetime.now().isoformat(),
                }
            )
            _progress_add(progress_id, f"Self-QA Frage {idx}: {q}", "fa-question-circle")
            qa_resp = ollama_client.chat(
                model=fast_model,
                messages=[
                    {
                        "role": "system",
                        "content": "Beantworte interne Arbeitsfragen kurz und konkret in 1-2 Saetzen.",
                    },
                    {
                        "role": "user",
                        "content": f"Nutzeranfrage: {user_message}\nInterne Frage: {q}",
                    },
                ],
                options={"temperature": 0.1, "num_predict": 140},
            )
            _ensure_not_cancelled(progress_id)
            a = (qa_resp.get("message", {}).get("content", "") or "").strip()
            if not a:
                a = "Keine klare Zusatzinformation gefunden."
            qa_lines.append(f"- {q}\n  Antwort: {a}")
            thinking_steps.append(
                {
                    "text": f"Selbstantwort {idx} erhalten",
                    "icon": "fa-check-circle",
                    "time": datetime.now().isoformat(),
                }
            )
            _progress_add(progress_id, f"Self-QA Antwort {idx} erhalten", "fa-check-circle")

        analysis_context = (
            "Interne Voranalyse (kompakt, zur Qualitaetsverbesserung):\n"
            + "\n".join(qa_lines)
            + "\nNutze diese Punkte fuer eine praezise Endantwort."
        )
        return {"analysis_context": analysis_context, "thinking_steps": thinking_steps}
    except ChatCancelled:
        raise
    except Exception as e:
        logger.warning(f"Self-QA Precheck fehlgeschlagen: {e}")
        thinking_steps.append(
            {
                "text": f"Self-QA konnte nicht vollständig laufen: {e}",
                "icon": "fa-exclamation-triangle",
                "time": datetime.now().isoformat(),
            }
        )
        return {"analysis_context": "", "thinking_steps": thinking_steps}

def _get_telegram_target_chat_ids(bot) -> List[Any]:
    """Collect Telegram targets from active sessions and config."""
    targets = set()

    # Aktive Sessions (das sind immer gültige User-IDs)
    if hasattr(bot, "_user_sessions") and isinstance(bot._user_sessions, dict):
        targets.update(bot._user_sessions.keys())

    # Konfigurierte Ziele sammeln
    configured_raw: List[Any] = []
    for key in ("telegram.chat_id", "telegram.channel_id"):
        value = config.get(key)
        if value:
            configured_raw.append(value)

    # Legacy fallback: key literally named "telegram.chat_id" inside telegram object
    telegram_cfg = config.data.get("telegram", {}) if isinstance(config.data, dict) else {}
    legacy_chat_id = telegram_cfg.get("telegram.chat_id") if isinstance(telegram_cfg, dict) else None
    if legacy_chat_id:
        configured_raw.append(legacy_chat_id)

    chat_ids_value = config.get("telegram.chat_ids", [])
    if isinstance(chat_ids_value, list):
        configured_raw.extend(chat_ids_value)
    elif isinstance(chat_ids_value, str) and chat_ids_value.strip():
        configured_raw.extend([part.strip() for part in chat_ids_value.split(",") if part.strip()])

    # Normalisieren und validieren
    for raw in configured_raw:
        normalized = _normalize_telegram_chat_id(raw)
        if normalized is not None:
            # === FIX: Nur gültige IDs hinzufügen ===
            # Prüfe ob es wirklich eine gültige Telegram-ID ist:
            # - Integer (auch negativ für Gruppen/Supergroups)
            # - String, der mit @ beginnt (für Channel/Group Username)
            # - String, der nur aus Ziffern besteht (und optional einem führenden -)
            t_str = str(normalized).strip()
            is_valid = (
                isinstance(normalized, int) or  # Direkter Integer
                t_str.startswith("@") or  # Channel/Group Username
                t_str.replace("-", "").isdigit()  # Numerischer String (mit optionalem -)
            )
            
            if is_valid:
                targets.add(normalized)
            else:
                logger.debug(f"Ungültige Telegram-Ziel-ID ignoriert: {raw} -> {normalized}")

    return list(targets)

def _parse_explicit_telegram_targets(raw_targets: Any) -> List[Any]:
    """Parse explicit Telegram targets from API payload."""
    parsed: List[Any] = []
    if raw_targets is None:
        return parsed

    items: List[Any] = []
    if isinstance(raw_targets, list):
        items = raw_targets
    else:
        items = [part.strip() for part in str(raw_targets).split(",") if part.strip()]

    for item in items:
        normalized = _normalize_telegram_chat_id(item)
        if normalized is not None:
            parsed.append(normalized)

    return parsed

def _infer_model_capabilities(name: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Infer practical model capabilities from model name/details."""
    lowered = (name or "").lower()
    details_text = json.dumps(details or {}, ensure_ascii=False).lower()
    merged = f"{lowered} {details_text}"
    vision_hints = ["vl", "vision", "llava", "moondream", "minicpm-v", "internvl", "qwen2.5vl", "bakllava"]
    tool_hints = ["tool", "function", "json"]
    supports_vision = any(h in merged for h in vision_hints)
    supports_tools = any(h in merged for h in tool_hints)
    return {
        "vision": supports_vision,
        "tools": supports_tools,
    }

def _pick_vision_model(available: List[str], requested_model: Optional[str] = None) -> Optional[str]:
    """Pick a model that can process images."""
    if not available:
        return None
    if requested_model and requested_model in available:
        if _infer_model_capabilities(requested_model).get("vision"):
            return requested_model
    
    # Vision model detection with expanded hints
    vision_candidates = [m for m in available if _infer_model_capabilities(m).get("vision")]
    if not vision_candidates:
        return None
    
    preferred_vision = _as_model_pref_list(config.get("ollama.preferred_vision_models")) or _as_model_pref_list(
        config.get("ollama.preferred_vision_model")
    )
    preferred_vision_model = _pick_preferred_available(vision_candidates, preferred_vision)
    if preferred_vision_model:
        return preferred_vision_model
    
    # Extended priority list for common vision models
    preferred = [
        "qwen2.5vl", "qwen2-vl", "llava", "minicpm-v", "moondream", 
        "bakllava", "cambrian", "phi3-vision", "llama3.2-vision", "vision", "vl"
    ]
    for hint in preferred:
        hinted = [m for m in vision_candidates if hint in m.lower()]
        if hinted:
            return sorted(hinted, key=_extract_model_score, reverse=True)[0]
    
    return sorted(vision_candidates, key=_extract_model_score, reverse=True)[0]

def _extract_search_term(text: str, triggers: List[str]) -> str:
    raw = (text or "").strip()
    lowered = raw.lower()
    term = raw
    for trigger in triggers:
        if trigger in lowered:
            pos = lowered.find(trigger) + len(trigger)
            term = raw[pos:].strip()
            break
    term = re.sub(r"^(?:zum|zu|zur)\s+thema\s+", "", term, flags=re.IGNORECASE).strip()
    term = re.sub(r"^thema\s+", "", term, flags=re.IGNORECASE).strip()
    term = re.sub(
        r"\s+(?:und\s+)?gib\s+mir\s+(?:eine|einen|ein)?\s*(?:kurze|knappe)?\s*(?:zusammenfassung|liste|überblick).*$",
        "",
        term,
        flags=re.IGNORECASE,
    ).strip()
    term = re.sub(r"\s+(?:als|bitte|danke|tabellarisch|json|tabelle)$", "", term, flags=re.IGNORECASE)
    return term.strip(' "')

def _wants_summary_after_search(text: str) -> bool:
    lowered = (text or "").lower()
    summary_terms = [
        "zusammenfassung",
        "zusammenfassen",
        "fasse zusammen",
        "kurz zusammen",
        "summary",
        "resümee",
        "ergebnis",
    ]
    return any(t in lowered for t in summary_terms)

def _scan_image_models(max_items: int = 30) -> List[str]:
    """Look for common image model files from ComfyUI/Invoke and known model dirs."""
    exts = {".safetensors", ".ckpt", ".onnx", ".pt"}
    results: List[str] = []
    roots: List[Path] = []
    env_candidates = [
        os.environ.get("COMFYUI_HOME", "").strip(),
        os.environ.get("INVOKEAI_ROOT", "").strip(),
    ]
    for raw in env_candidates:
        if raw:
            p = Path(raw)
            if p.exists():
                roots.append(p)
    user_profile = os.environ.get("USERPROFILE", "").strip()
    if user_profile:
        for candidate in [Path(user_profile) / "ComfyUI", Path(user_profile) / "invokeai"]:
            if candidate.exists():
                roots.append(candidate)
    for hard in [Path("ComfyUI"), Path("invokeai"), Path("models"), Path.cwd() / "ComfyUI"]:
        if hard.exists():
            roots.append(hard)

    seen = set()
    for root in roots:
        for sub in [root, root / "models", root / "models" / "checkpoints", root / "models" / "diffusion_models"]:
            if not sub.exists() or not sub.is_dir():
                continue
            try:
                for path in sub.rglob("*"):
                    if len(results) >= max_items:
                        return sorted(results)
                    if not path.is_file() or path.suffix.lower() not in exts:
                        continue
                    rel = str(path)
                    if rel in seen:
                        continue
                    seen.add(rel)
                    results.append(rel)
            except Exception:
                continue
    return sorted(results)

def _is_tcp_port_open(host: str, port: int, timeout: float = 0.35) -> bool:
    """Best-effort TCP port probe."""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:
        return False

def _get_tool_discovery(force: bool = False) -> Dict[str, Any]:
    """Discover optional local AI tools (ComfyUI/Invoke) with lightweight caching."""
    global _DISCOVERY_CACHE
    now = datetime.now()
    cached_ts = _DISCOVERY_CACHE.get("ts")
    if not force and cached_ts and isinstance(cached_ts, datetime):
        if (now - cached_ts).total_seconds() < 300:
            return _DISCOVERY_CACHE.get("data", {})

    comfy_root = None
    comfy_main = None
    comfy_candidates: List[Path] = []
    comfy_env = os.environ.get("COMFYUI_HOME", "").strip()
    if comfy_env:
        comfy_candidates.append(Path(comfy_env))
    comfy_candidates.extend([
        Path.cwd() / "ComfyUI",
        Path.home() / "ComfyUI",
        Path("C:/ComfyUI"),
    ])
    for c in comfy_candidates:
        if c.exists() and c.is_dir() and (c / "main.py").exists():
            comfy_root = str(c.resolve())
            comfy_main = str((c / "main.py").resolve())
            break

    invoke_bin = shutil.which("invokeai")
    invoke_root = os.environ.get("INVOKEAI_ROOT", "")
    image_models = _scan_image_models()
    comfy_port = int(config.get("comfyui.port", 8188) or 8188)
    comfy_host = str(config.get("comfyui.host", "127.0.0.1") or "127.0.0.1")
    comfy_running = _is_tcp_port_open(comfy_host, comfy_port)
    comfy_url = f"http://{comfy_host}:{comfy_port}"

    data = {
        "comfyui": {
            "found": bool(comfy_root or comfy_running),
            "root": comfy_root,
            "main_py": comfy_main,
            "running": comfy_running,
            "url": comfy_url,
            "port": comfy_port,
            "host": comfy_host,
        },
        "invoke": {
            "found": bool(invoke_bin or invoke_root),
            "binary": invoke_bin,
            "root": invoke_root or None,
        },
        "image_models_found": len(image_models),
        "image_models": image_models[:20],
    }
    _DISCOVERY_CACHE = {"ts": now, "data": data}
    return data

def _start_comfyui(discovery: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Try to start ComfyUI if installation is known."""
    info = discovery or _get_tool_discovery(force=True)
    comfy = info.get("comfyui", {})
    root = comfy.get("root")
    main_py = comfy.get("main_py")
    if not (root and main_py and os.path.exists(main_py)):
        return {"ok": False, "message": "ComfyUI nicht gefunden."}
    try:
        proc = subprocess.Popen(
            [sys.executable, main_py, "--listen"],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
        return {
            "ok": True,
            "pid": proc.pid,
            "command": f"{sys.executable} {main_py} --listen",
            "cwd": root,
        }
    except Exception as e:
        return {"ok": False, "message": str(e)}

def _progress_init(request_id: str) -> None:
    with _CHAT_PROGRESS_LOCK:
        _CHAT_PROGRESS[request_id] = {
            "steps": [],
            "updated_at": datetime.now().isoformat(),
            "done": False,
            "cancelled": False,
            "active_model": None,
        }

def _progress_add(request_id: Optional[str], text: str, icon: str = "fa-brain", details: str = "") -> None:
    if not request_id:
        return
    entry = {
        "text": text,
        "icon": icon,
        "time": datetime.now().isoformat(),
    }
    if details:
        entry["details"] = details
    with _CHAT_PROGRESS_LOCK:
        state = _CHAT_PROGRESS.get(request_id)
        if not state:
            return
        state["steps"].append(entry)
        state["updated_at"] = datetime.now().isoformat()

def _progress_set_active_model(request_id: Optional[str], model: Optional[str]) -> None:
    if not request_id:
        return
    with _CHAT_PROGRESS_LOCK:
        state = _CHAT_PROGRESS.get(request_id)
        if state is not None:
            state["active_model"] = model
            state["updated_at"] = datetime.now().isoformat()

def _progress_mark_done(request_id: Optional[str]) -> None:
    if not request_id:
        return
    with _CHAT_PROGRESS_LOCK:
        state = _CHAT_PROGRESS.get(request_id)
        if state is not None:
            state["done"] = True
            state["updated_at"] = datetime.now().isoformat()

def _progress_cancel(request_id: str) -> None:
    with _CHAT_PROGRESS_LOCK:
        state = _CHAT_PROGRESS.get(request_id)
        if state is not None:
            state["cancelled"] = True
            state["updated_at"] = datetime.now().isoformat()

def _progress_is_cancelled(request_id: Optional[str]) -> bool:
    if not request_id:
        return False
    with _CHAT_PROGRESS_LOCK:
        state = _CHAT_PROGRESS.get(request_id)
        return bool(state and state.get("cancelled"))

def _ensure_not_cancelled(request_id: Optional[str]) -> None:
    if _progress_is_cancelled(request_id):
        raise ChatCancelled("Anfrage wurde abgebrochen")

def _progress_get(request_id: str, since: int = 0) -> Dict[str, Any]:
    with _CHAT_PROGRESS_LOCK:
        state = _CHAT_PROGRESS.get(request_id)
        if not state:
            return {"exists": False, "steps": [], "next_index": since, "done": True, "cancelled": True}
        steps = state.get("steps", [])
        safe_since = max(0, min(int(since or 0), len(steps)))
        new_steps = steps[safe_since:]
        return {
            "exists": True,
            "steps": new_steps,
            "next_index": safe_since + len(new_steps),
            "done": bool(state.get("done")),
            "cancelled": bool(state.get("cancelled")),
            "active_model": state.get("active_model"),
            "updated_at": state.get("updated_at"),
        }

def _list_running_ollama_models() -> List[str]:
    """Best-effort parsing of `ollama ps` output."""
    try:
        proc = subprocess.run(
            ["ollama", "ps"],
            capture_output=True,
            text=True,
            timeout=8,
            shell=False,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            return []
        lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
        if len(lines) <= 1:
            return []
        models: List[str] = []
        for ln in lines[1:]:
            parts = ln.split()
            if parts:
                models.append(parts[0])
        return models
    except Exception:
        return []

def _stop_ollama_model(model: str) -> Dict[str, Any]:
    if not model:
        return {"ok": False, "message": "Kein Modell angegeben"}
    try:
        proc = subprocess.run(
            ["ollama", "stop", model],
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "ok": proc.returncode == 0,
            "model": model,
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
            "returncode": proc.returncode,
        }
    except Exception as e:
        return {"ok": False, "model": model, "message": str(e)}
# --- MODELLE (Pydantic) ---
class ShellRequest(BaseModel):
    command: str
    args: Optional[List[str]] = []
class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
    context: Optional[List[dict]] = []
    request_id: Optional[str] = None
# Memory-Dateien
MEMORY_FILE = "MEMORY.md"
SKILLS_FILE = "SKILLS.md"
HEARTBEAT_FILE = "HEARTBEAT.md"
CHAT_ARCHIVE_DIR = "chat_archives"
NOTES_FILE = "MEMORY_NOTES.json"
# Chat-Archiv Verzeichnis erstellen
os.makedirs(CHAT_ARCHIVE_DIR, exist_ok=True)
# Einfacher Schutz über den API-Key aus der Config
async def verify_token(x_api_key: str = Header(None)):
    if x_api_key != config.get("api_key"):
        raise HTTPException(status_code=403, detail="Ungültiger API-Key")
    return x_api_key
# =====================================================================
# ============ Memory Klasse ============
# =====================================================================

class ChatMemory:
    def __init__(self):
        self.memory_content = self._read_file(MEMORY_FILE)
        self.skills_content = self._read_file(SKILLS_FILE)
        self.heartbeat_content = self._read_file(HEARTBEAT_FILE)
        self.conversation_history = []
        self.last_activity = datetime.now()
        self.auto_explore_task = None
        self.is_exploring = False
        # Lern-Attribute
        self.user_interests = {}
        self.user_preferences = {
            "positive_feedback": 0,
            "negative_feedback": 0,
            "message_length": "mittel",
            "active_time": "unbekannt"
        }
        self.important_info = {}
        self.user_notes = self._load_notes()
        # Konfigurierbare Grenzen
        self.max_memory_entries = 100
        self.max_memory_size = 10000
        self.archive_file = "MEMORY_ARCHIVE.md"
        # Chat-Archiv Verzeichnis
        self.chat_archive_dir = "chat_archives"
        os.makedirs(self.chat_archive_dir, exist_ok=True)
        # Auto-Exploration starten (in einem neuen Event-Loop wenn nötig)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._start_auto_exploration())
            else:
                loop.run_until_complete(self._start_auto_exploration())
        except:
            # Fallback: Als Task starten wenn möglich
            asyncio.create_task(self._start_auto_exploration())
    # ===== READ/WRITE METHODEN =====
    def _read_file(self, filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            default_content = self._get_default_content(filename)
            self._write_file(filename, default_content)
            return default_content
    def _write_file(self, filename, content):
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
    def _load_notes(self):
        try:
            with open(NOTES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [n for n in data if isinstance(n, dict) and n.get("text")]
        except Exception:
            pass
        return []
    def _save_notes(self):
        with open(NOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(self.user_notes[-500:], f, ensure_ascii=False, indent=2)
    def remember_note(self, text: str, source: str = "manual"):
        """Speichert eine explizite Notiz dauerhaft und gibt (entry, created) zurück."""
        clean_text = (text or "").strip()
        if not clean_text:
            return None, False
        now = datetime.now()
        now_iso = now.isoformat()
        existing = next(
            (n for n in self.user_notes if n.get("text", "").strip().lower() == clean_text.lower()),
            None,
        )
        if existing:
            existing["confirmed_at"] = now_iso
            existing["source"] = source or existing.get("source", "manual")
            self._save_notes()
            self.update_activity()
            return existing, False
        entry = {
            "id": now.strftime("%Y%m%d_%H%M%S_%f"),
            "text": clean_text,
            "timestamp": now_iso,
            "source": source or "manual",
        }
        self.user_notes.append(entry)
        self._save_notes()
        memory_entry = f"""
## 🧠 Gemerkt [{now.strftime('%Y-%m-%d %H:%M:%S')}]
- {clean_text}
---
"""
        try:
            with open(MEMORY_FILE, "a", encoding="utf-8") as f:
                f.write(memory_entry)
            self.memory_content += memory_entry
        except Exception as e:
            logger.error(f"Merk-Notiz konnte nicht ins Memory geschrieben werden: {e}")
        self.update_activity()
        self.update_heartbeat()
        return entry, True
    def get_remembered_notes(self, limit: int = 20):
        """Gibt gemerkte Notizen zurück (neueste zuerst)."""
        safe_limit = max(1, min(limit, 200))
        return list(reversed(self.user_notes[-safe_limit:]))
    def run_sleep_phase(self, reason: str = "idle") -> Dict[str, Any]:
        """
        Schlafphase: sortiert/kompaktiert Memory und aktualisiert Nutzer-Zuordnungen.
        """
        before_notes = len(self.user_notes)
        # 1) Dedupliziere explizite Notizen
        deduped = []
        seen = set()
        for note in self.user_notes:
            key = (note.get("text", "") or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(note)
        self.user_notes = deduped[-500:]
        self._save_notes()

        # 2) Ableitung von Interessen aus den letzten User-Nachrichten
        recent_users = [m.get("content", "") for m in self.conversation_history if m.get("role") == "user"][-40:]
        for msg in recent_users:
            topic = self._detect_topic(msg)
            self.user_interests[topic] = self.user_interests.get(topic, 0) + 1

        # 3) Memory kompaktieren falls zu groß
        compacted = False
        if len(self.memory_content) > int(self.max_memory_size * 1.2):
            self._archive_old_memory()
            compacted = True

        # 4) Profil-Snapshot speichern
        profile = {
            "updated_at": datetime.now().isoformat(),
            "reason": reason,
            "user_interests": dict(sorted(self.user_interests.items(), key=lambda x: x[1], reverse=True)[:12]),
            "user_preferences": self.user_preferences,
            "notes_count": len(self.user_notes),
        }
        try:
            with open("MEMORY_PROFILE.json", "w", encoding="utf-8") as f:
                json.dump(profile, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Sleep-Phase: MEMORY_PROFILE.json konnte nicht geschrieben werden: {e}")

        sleep_log = (
            f"\n## 🌙 Schlafphase [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]\n"
            f"- Grund: {reason}\n"
            f"- Notizen bereinigt: {before_notes} -> {len(self.user_notes)}\n"
            f"- Memory kompaktiert: {'ja' if compacted else 'nein'}\n"
            f"- Interessen aktualisiert: {', '.join(list(profile['user_interests'].keys())[:5]) if profile['user_interests'] else 'keine'}\n"
            "---\n"
        )
        try:
            with open(MEMORY_FILE, "a", encoding="utf-8") as f:
                f.write(sleep_log)
            self.memory_content += sleep_log
        except Exception as e:
            logger.warning(f"Sleep-Phase Log konnte nicht geschrieben werden: {e}")

        self.update_heartbeat()
        return {
            "reason": reason,
            "notes_before": before_notes,
            "notes_after": len(self.user_notes),
            "memory_compacted": compacted,
            "top_topics": list(profile["user_interests"].keys())[:5],
        }
    def _get_default_content(self, filename):
        if "MEMORY" in filename:
            return f"""# GABI Memory System
## Aktuelle Konversation
- Datum: {datetime.now().strftime('%Y-%m-%d')}
- Thema: Erste Initialisierung
- User: Admin
## System-Exploration Status
- Auto-Exploration: Aktiv
- Letzte Exploration: Noch nicht durchgeführt
- Entdeckte Systeme: -
## Wichtige Informationen
- Gateway läuft auf http://localhost:8000
- API-Key: In config.yaml konfiguriert
- Ollama Modell: {ollama_client.default_model}
"""
        elif "SKILLS" in filename:
            return """# GABI Skills & Fähigkeiten
## 🎯 Kern-Funktionen
- **Chat**: Konversation mit Ollama
- **Shell**: Ausführung erlaubter Systembefehle
- **Auto-Exploration**: Selbstständige Systemerkundung bei Inaktivität
- **Chat-Archiv**: Speichert und verwaltet Chat-Verläufe
## 💻 Erlaubte Shell-Kommandos
- ls/dir, pwd/cd, date, echo, cat/type, git, head, tail, wc, systeminfo, whoami, netstat
"""
        elif "HEARTBEAT" in filename:
            return f"""# GABI Heartbeat & Monitoring
## Aktueller Status ({datetime.now().strftime('%d.%m.%Y %H:%M')})
| Dienst | Status |
|--------|--------|
| FastAPI | 🟢 Online |
| Ollama | 🟢 Connected |
| Auto-Exploration | 🟡 Warte auf Inaktivität |
| Chat-Archiv | 🟢 Bereit |
"""
        return ""
    # ===== AUTO-EXPLORATION =====
    async def _start_auto_exploration(self):
        """Startet den Auto-Exploration Task"""
        while True:
            try:
                # Prüfe Inaktivität (10 Minuten = 600 Sekunden)
                inactive_time = (datetime.now() - self.last_activity).total_seconds()
                if inactive_time > 600 and not self.is_exploring:  # 10 Minuten Inaktivität
                    self.run_sleep_phase(reason=f"idle-{int(inactive_time)}s")
                    await self._explore_system()
                # Alle 5 Minuten prüfen
                await asyncio.sleep(300)
            except Exception as e:
                logger.error(f"Auto-Exploration Fehler: {e}")
                await asyncio.sleep(60)
    async def _explore_system(self):
        """Erkundet das System bei Inaktivität - inkl. aller Pfade aus Umgebungsvariablen"""
        self.is_exploring = True
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        exploration_log = f"""
    ## 🔍 Auto-Exploration [{timestamp}]
    GABI hat das System erkundet:
    """
        try:
            # ===== 1. SYSTEM-INFORMATIONEN =====
            try:
                system_info = subprocess.run(
                    ["systeminfo", "|", "findstr", "/B", "/C:", "OS Name", "/C:", "OS Version", "/C:", "System Type"],
                    capture_output=True,
                    text=True,
                    shell=True,
                    timeout=10,
                    encoding="cp850"
                )
                exploration_log += f"### 💻 System:\n{system_info.stdout}\n"
            except Exception as e:
                exploration_log += f"### 💻 System:\n- Keine Systeminfo verfügbar ({str(e)})\n"
            # ===== 2. ALLE UMGEBUNGSVARIABLEN UND DEREN PFADE =====
            exploration_log += "\n### 🌍 Umgebungsvariablen & Pfade:\n"
            # Wichtige Pfad-Variablen
            path_vars = [
                'PATH', 'Path', 'TEMP', 'TMP', 'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH',
                'ProgramFiles', 'ProgramFiles(x86)', 'CommonProgramFiles', 'APPDATA',
                'LOCALAPPDATA', 'ALLUSERSPROFILE', 'SystemRoot', 'windir', 'PUBLIC',
                'OneDrive', 'ProgramData', 'PSModulePath', 'JAVA_HOME', 'PYTHONPATH',
                'NODE_PATH', 'GOPATH', 'ANDROID_HOME', 'GRADLE_HOME', 'MAVEN_HOME'
            ]
            explored_paths = []
            for var_name in path_vars:
                path_value = os.environ.get(var_name, '')
                if path_value and path_value not in explored_paths:
                    explored_paths.append(path_value)
                    # Einzelne Pfade (bei PATH sind mehrere durch ; getrennt)
                    if var_name.upper() in ['PATH', 'PSModulePath']:
                        individual_paths = path_value.split(';')
                        exploration_log += f"  **{var_name}** (mehrere Pfade):\n"
                        for i, single_path in enumerate(individual_paths[:10]):  # Max 10 anzeigen
                            if single_path and os.path.exists(single_path):
                                try:
                                    files = os.listdir(single_path)[:5]  # Erste 5 Dateien
                                    file_count = len(os.listdir(single_path))
                                    exploration_log += f"    {i+1}. `{single_path}` - {file_count} Elemente\n"
                                    if files:
                                        exploration_log += f"       Z.B.: {', '.join(files[:3])}\n"
                                except:
                                    exploration_log += f"    {i+1}. `{single_path}` - (nicht zugänglich)\n"
                        # Am Ende einen Gesamtüberblick
                        exploration_log += f"    → Insgesamt {len(individual_paths)} Pfade in {var_name}\n"
                    else:
                        # Einzelne Pfade
                        if os.path.exists(path_value):
                            try:
                                files = os.listdir(path_value)[:5]
                                file_count = len(os.listdir(path_value))
                                exploration_log += f"  **{var_name}**: `{path_value}` - {file_count} Elemente\n"
                                if files:
                                    exploration_log += f"    Z.B.: {', '.join(files[:3])}\n"
                            except:
                                exploration_log += f"  **{var_name}**: `{path_value}` - (nicht zugänglich)\n"
                        else:
                            exploration_log += f"  **{var_name}**: `{path_value}` - (existiert nicht)\n"
            # ===== 3. ALLE LAUFWERKE (WINDOWS) =====
            exploration_log += "\n### 💾 Verfügbare Laufwerke:\n"
            try:
                import string
                from ctypes import windll
                drives = []
                bitmask = windll.kernel32.GetLogicalDrives()
                for letter in string.ascii_uppercase:
                    if bitmask & 1:
                        drive = f"{letter}:\\"
                        try:
                            total, used, free = shutil.disk_usage(drive)
                            drives.append(f"{drive} - {round(free / (2**30), 2)} GB frei")
                        except:
                            drives.append(f"{drive} - (nicht verfügbar)")
                    bitmask >>= 1
                for drive in drives[:10]:  # Max 10 Laufwerke
                    exploration_log += f"  • {drive}\n"
            except Exception as e:
                exploration_log += f"  • Keine Laufwerksinfo verfügbar ({str(e)})\n"
            # ===== 4. WICHTIGE SYSTEMORDNER =====
            important_dirs = [
                os.environ.get('USERPROFILE', 'C:\\Users\\Default'),
                os.environ.get('APPDATA', 'C:\\Users\\Default\\AppData\\Roaming'),
                os.environ.get('LOCALAPPDATA', 'C:\\Users\\Default\\AppData\\Local'),
                os.environ.get('ProgramFiles', 'C:\\Program Files'),
                os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'),
                os.environ.get('SystemRoot', 'C:\\Windows'),
                os.environ.get('TEMP', 'C:\\Windows\\Temp'),
                os.environ.get('PUBLIC', 'C:\\Users\\Public'),
            ]
            exploration_log += "\n### 📂 Wichtige Systemordner:\n"
            for dir_path in set(important_dirs):  # Duplikate entfernen
                if dir_path and os.path.exists(dir_path):
                    try:
                        items = os.listdir(dir_path)
                        subdirs = [d for d in items if os.path.isdir(os.path.join(dir_path, d))]
                        files = [f for f in items if os.path.isfile(os.path.join(dir_path, f))]
                        exploration_log += f"  • `{dir_path}`\n"
                        exploration_log += f"    → {len(subdirs)} Ordner, {len(files)} Dateien\n"
                        # Ein paar Unterordner auflisten
                        if subdirs[:3]:
                            exploration_log += f"    → Z.B.: {', '.join(subdirs[:3])}\n"
                    except:
                        exploration_log += f"  • `{dir_path}` - (nicht zugänglich)\n"
            # ===== 5. NETZWERK-STATUS =====
            try:
                netstat = subprocess.run(
                    ["netstat", "-n"],
                    capture_output=True,
                    text=True,
                    shell=True,
                    timeout=10,
                    encoding="cp850"
                )
                connections = len([l for l in netstat.stdout.split('\n') if 'ESTABLISHED' in l])
                listening = len([l for l in netstat.stdout.split('\n') if 'LISTENING' in l])
                exploration_log += f"\n### 🌐 Netzwerk:\n- Aktive Verbindungen: {connections}\n- Listening Ports: {listening}\n"
            except Exception as e:
                exploration_log += f"\n### 🌐 Netzwerk:\n- Keine Netzwerkinfo verfügbar ({str(e)})\n"
            # ===== 6. PROZESSE =====
            try:
                tasks = subprocess.run(
                    ["tasklist", "/FI", "STATUS eq running"],
                    capture_output=True,
                    text=True,
                    shell=True,
                    timeout=10,
                    encoding="cp850"
                )
                process_count = len([l for l in tasks.stdout.split('\n') if '.exe' in l])
                # Top 5 Prozesse (einfach die ersten 5 anzeigen)
                top_processes = []
                lines = tasks.stdout.split('\n')[3:8]  # Erste 5 nach Header
                for line in lines:
                    parts = line.split()
                    if len(parts) > 1:
                        top_processes.append(parts[0])
                exploration_log += f"\n### ⚙️ Prozesse:\n- Laufende Prozesse: {process_count}\n"
                if top_processes:
                    exploration_log += f"- Top Prozesse: {', '.join(top_processes)}\n"
            except Exception as e:
                exploration_log += f"\n### ⚙️ Prozesse:\n- Keine Prozessinfo verfügbar ({str(e)})\n"
            # ===== 7. OLLAMA MODELLE =====
            try:
                models_info = ollama_client.list_models()
                models = [m.get("name") for m in models_info.get("models", [])]
                exploration_log += f"\n### 🤖 Modelle:\n- Verfügbar: {', '.join(models[:5])}\n"
                if len(models) > 5:
                    exploration_log += f"- ... und {len(models)-5} weitere\n"
            except Exception as e:
                exploration_log += f"\n### 🤖 Modelle:\n- Nicht verfügbar ({str(e)})\n"
            # ===== 8. AI TOOL DISCOVERY =====
            discovery = _get_tool_discovery(force=True)
            comfy = discovery.get("comfyui", {})
            invoke = discovery.get("invoke", {})
            exploration_log += (
                "\n### 🎨 Bild-KI Tools:\n"
                f"- ComfyUI: {'gefunden' if comfy.get('found') else 'nicht gefunden'}"
                + (f" ({comfy.get('root')})" if comfy.get('root') else "")
                + "\n"
                f"- InvokeAI: {'gefunden' if invoke.get('found') else 'nicht gefunden'}"
                + (f" ({invoke.get('binary') or invoke.get('root')})" if (invoke.get('binary') or invoke.get('root')) else "")
                + "\n"
                f"- Gefundene Bildmodelle: {discovery.get('image_models_found', 0)}\n"
            )
            if discovery.get("image_models"):
                sample_models = discovery.get("image_models", [])[:5]
                exploration_log += f"- Beispiele: {', '.join(sample_models)}\n"
            # ===== 9. CHAT-ARCHIVE =====
            archives = self.list_chat_archives()
            total_messages = sum(a.get('messages', 0) for a in archives)
            exploration_log += f"\n### 📚 Archive:\n- Gespeicherte Chats: {len(archives)}\n- Gesamt Nachrichten: {total_messages}\n"
            # ===== 10. ZUFÄLLIGE ENTDECKUNG =====
            discoveries = [
                "🔍 Ich habe interessante Konfigurationsdateien gefunden.",
                "📊 Die Systemauslastung scheint normal.",
                "🔄 Einige Hintergrundprozesse sind aktiv.",
                "📝 Ich habe alte Log-Dateien gefunden.",
                "🌙 Es ist ruhig im System.",
                "💡 Einige Dienste laufen im Hintergrund.",
                "🔒 Die Firewall ist aktiv.",
                "⚡ Die Systemleistung ist gut.",
                "📁 Viele temporäre Dateien gefunden.",
                "🌐 Mehrere Netzwerkverbindungen aktiv.",
                "💾 Genügend Speicherplatz verfügbar.",
                "🔧 Alle wichtigen Systempfade sind erreichbar."
            ]
            exploration_log += f"\n### 💡 Entdeckung:\n{random.choice(discoveries)}\n"
            # ===== 11. ZUSAMMENFASSUNG =====
            exploration_log += f"""
    ### 📊 Zusammenfassung:
    - **Untersuchte Pfad-Variablen**: {len(explored_paths)}
    - **Gefundene Laufwerke**: {len(drives) if 'drives' in locals() else '?'}
    - **Untersuchte Systemordner**: {len(set(important_dirs))}
    - **Aktive Prozesse**: {process_count if 'process_count' in locals() else '?'}
    - **Netzwerkverbindungen**: {connections if 'connections' in locals() else '?'}
    - **Verfügbare Modelle**: {len(models) if 'models' in locals() else 0}
    - **Gespeicherte Chats**: {len(archives)}
    """
            # Exploration speichern
            with open(MEMORY_FILE, "a", encoding="utf-8") as f:
                f.write(exploration_log)
            self.memory_content += exploration_log
            # Heartbeat aktualisieren
            self.update_heartbeat()
            logger.info(f"✅ Auto-Exploration mit Pfad-Analyse abgeschlossen: {timestamp}")
            # Auch eine kurze Bestätigung für den Chat
            # print(f"\n🔍 Auto-Exploration abgeschlossen! Siehe MEMORY.md für Details.\n")
        except Exception as e:
            logger.error(f"❌ Exploration Fehler: {e}")
            with open(MEMORY_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n### ❌ Exploration fehlgeschlagen:\n{str(e)}\n")
        finally:
            self.is_exploring = False
    # ===== CHAT-ARCHIV FUNKTIONEN =====
    def save_chat_session(self):
        """Speichert die aktuelle Chat-Session als Archiv"""
        if len(self.conversation_history) < 2:
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.chat_archive_dir}/chat_{timestamp}.json"
        # Konversation aufbereiten
        session = {
            "id": timestamp,
            "start_time": self.conversation_history[0].get("timestamp", datetime.now().isoformat()) if self.conversation_history else datetime.now().isoformat(),
            "end_time": datetime.now().isoformat(),
            "messages": self.conversation_history,
            "message_count": len(self.conversation_history),
            "user_interests": dict(self.user_interests),
            "preferences": self.user_preferences
        }
        # Als JSON speichern
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2, ensure_ascii=False)
        # Auch als lesbare MD-Datei
        md_filename = f"{self.chat_archive_dir}/chat_{timestamp}.md"
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(f"# Chat-Session vom {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n")
            f.write(f"**Nachrichten:** {len(self.conversation_history)}\n\n")
            for msg in self.conversation_history:
                role = "👤 User" if msg["role"] == "user" else "🤖 GABI"
                f.write(f"### {role} ({msg.get('timestamp', '')})\n")
                f.write(f"{msg['content']}\n\n")
        return filename
    def list_chat_archives(self):
        """Listet alle gespeicherten Chat-Archive auf"""
        archives = []
        for f in os.listdir(self.chat_archive_dir):
            if f.endswith('.json'):
                filepath = os.path.join(self.chat_archive_dir, f)
                stats = os.stat(filepath)
                try:
                    with open(filepath, 'r', encoding='utf-8') as jf:
                        data = json.load(jf)
                        archives.append({
                            "id": data.get("id", f.replace('chat_', '').replace('.json', '')),
                            "filename": f,
                            "date": datetime.fromtimestamp(stats.st_mtime).isoformat(),
                            "size": stats.st_size,
                            "messages": data.get("message_count", 0),
                            "preview": data.get("messages", [{}])[0].get("content", "")[:100] if data.get("messages") else ""
                        })
                except:
                    pass
        # Nach Datum sortieren (neueste zuerst)
        archives.sort(key=lambda x: x["date"], reverse=True)
        return archives
    def load_chat_archive(self, archive_id):
        """Lädt ein Chat-Archiv"""
        # Verschiedene Formate probieren
        possible_files = [
            f"{self.chat_archive_dir}/chat_{archive_id}.json",
            f"{self.chat_archive_dir}/{archive_id}",
            f"{self.chat_archive_dir}/{archive_id}.json"
        ]
        for filename in possible_files:
            if os.path.exists(filename):
                try:
                    with open(filename, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except:
                    pass
        return None
    # ===== CHAT RESET =====
    def reset_chat(self, archive_current=True):
        """Setzt den Chat zurück, optional mit Archivierung"""
        if archive_current and len(self.conversation_history) > 0:
            self.save_chat_session()
        # Zurücksetzen
        self.conversation_history = []
        self.last_activity = datetime.now()
        # Memory.md aktualisieren
        reset_entry = f"""
## 🔄 Chat zurückgesetzt [{datetime.now().strftime('%Y-%m-%d %H:%M')}]
Ein neuer Chat wurde gestartet.
---
"""
        with open(MEMORY_FILE, "a", encoding="utf-8") as f:
            f.write(reset_entry)
        self.memory_content += reset_entry
        return {"status": "success", "message": "Chat wurde zurückgesetzt"}
    # ===== ACTIVITY MANAGEMENT =====
    def update_activity(self):
        """Aktualisiert den letzten Aktivitäts-Timestamp"""
        self.last_activity = datetime.now()
    # ===== SYSTEM PROMPT =====
    def get_system_prompt(self):
        """Optimierter System-Prompt - kurz und präzise"""
        
        # System-Erkennung (wie bisher)
        system_os = platform.system()
        if system_os == "Windows":
            dir_cmd = "dir"
            file_cmd = "type"
        elif system_os == "Linux":
            dir_cmd = "ls -la"
            file_cmd = "cat"
        else:
            dir_cmd = "ls -la"
            file_cmd = "cat"
        
        # Kompakte Status-Info
        inactive_time = (datetime.now() - self.last_activity).total_seconds()
        current_time = datetime.now().strftime('%d.%m.%Y %H:%M')
        
        # KURZER, PRÄGNANTER SYSTEM-PROMPT
        return f"""Du bist GABI, ein KI-Assistent auf {system_os}.

## 🛠️ WIE DU SHELL-BEFEHLE AUSFÜHRST
- Wenn der Nutzer EXPLIZIT einen Shell-Befehl möchte, antworte mit `/shell <befehl>`
- Beispiel: Nutzer: "zeig mir alle python dateien" → Du antwortest: `/shell {dir_cmd} *.py`
- Beispiel: Nutzer: "erstelle datei test.txt" → Du antwortest: `/shell echo "" > test.txt`

## ⚠️ WICHTIGE REGELN
- Führe NIEMALS Shell-Befehle aus, wenn der Nutzer nur eine Wissensfrage stellt
- Bei Wissensfragen (wie "was sind schwarze löcher") antworte NORMAL mit Text, NICHT mit /shell
- Der Nutzer erwartet von dir eine verständliche Antwort, keine Shell-Befehle

## 🆔 SYSTEM-INFO
- OS: {system_os}
- Modell: {ollama_client.default_model}
- Zeit: {current_time}
- Aktiv: vor {int(inactive_time / 60)} Minuten

Antworte JETZT auf die Nutzer-Anfrage!"""
    
    # ===== HILFSMETHODEN =====
    def _get_recent_context(self, limit=3):
        """Gibt die letzten limit Konversationen zurück"""
        if not self.conversation_history:
            return "Keine vorherigen Nachrichten."
        context = ""
        start = max(0, len(self.conversation_history) - limit * 2)
        for i, msg in enumerate(self.conversation_history[start:]):
            role = "👤 User" if msg["role"] == "user" else "🤖 GABI"
            content = msg['content'][:100] + "..." if len(msg['content']) > 100 else msg['content']
            context += f"{role}: {content}\n"
        return context
    def _detect_topic(self, message):
        """Erkennt das Thema der Nachricht"""
        topics = {
            "shell": ["bash", "cmd", "terminal", "command", "ausführen", "shell"],
            "git": ["git", "commit", "push", "pull", "branch"],
            "python": ["python", "code", "skript", "programm"],
            "gmail": ["mail", "email", "gmail", "nachricht"],
            "system": ["status", "health", "server", "läuft", "exploration"],
            "memory": ["erinner", "memory", "vorher", "gestern", "archiv"],
            "soul": ["persönlichkeit", "soul", "charakter", "lernen"],
            "hilfe": ["hilfe", "help", "frage", "problem", "fehler"],
            "chat": ["new", "reset", "load", "archive", "verlauf"],
        }
        msg_lower = message.lower()
        for topic, keywords in topics.items():
            if any(keyword in msg_lower for keyword in keywords):
                return topic
        return "allgemein"
    def _learn_from_interaction(self, user_message, bot_response, timestamp):
        """Extrahiert Lernpunkte aus der Interaktion"""
        # Feedback erkennen
        if "danke" in user_message.lower() or "super" in user_message.lower():
            self.user_preferences["positive_feedback"] = self.user_preferences.get("positive_feedback", 0) + 1
        if "nicht" in user_message.lower() or "falsch" in user_message.lower():
            self.user_preferences["negative_feedback"] = self.user_preferences.get("negative_feedback", 0) + 1
        # Thema tracken
        topic = self._detect_topic(user_message)
        self.user_interests[topic] = self.user_interests.get(topic, 0) + 1
        # Nachrichtenlänge
        msg_len = len(user_message)
        if msg_len < 50:
            self.user_preferences["message_length"] = "kurz"
        elif msg_len < 200:
            self.user_preferences["message_length"] = "mittel"
        else:
            self.user_preferences["message_length"] = "lang"
        # Tageszeit
        hour = datetime.now().hour
        if 5 <= hour < 12:
            self.user_preferences["active_time"] = "morgens"
        elif 12 <= hour < 18:
            self.user_preferences["active_time"] = "nachmittags"
        elif 18 <= hour < 22:
            self.user_preferences["active_time"] = "abends"
        else:
            self.user_preferences["active_time"] = "nachts"
        # Wichtige Infos
        important_patterns = [
            (r'mein name ist (\w+)', 'name'),
            (r'ich heiße (\w+)', 'name'),
            (r'ich arbeite an ([\w\s]+)', 'projekt'),
            (r'mein lieblings ([\w\s]+) ist (\w+)', 'favorit'),
        ]
        for pattern, info_type in important_patterns:
            match = re.search(pattern, user_message, re.IGNORECASE)
            if match:
                self.important_info[info_type] = match.group(1)
    def add_to_memory(self, user_message, bot_response):
        """Fügt eine Konversation zum Memory hinzu"""
        self.update_activity()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        # Konversation speichern
        self.conversation_history.append({"role": "user", "content": user_message, "timestamp": timestamp})
        self.conversation_history.append({"role": "assistant", "content": bot_response, "timestamp": timestamp})
        if len(self.conversation_history) > self.max_memory_entries:
            # Alte Einträge entfernen, aber vorher archivieren?
            self.conversation_history = self.conversation_history[-self.max_memory_entries:]
        # Memory.md aktualisieren
        memory_update = f"""
## {timestamp}
**User**: {user_message[:200]}{'...' if len(user_message) > 200 else ''}
**GABI**: {bot_response[:200]}{'...' if len(bot_response) > 200 else ''}
**Thema**: {self._detect_topic(user_message)}
---
"""
        try:
            with open(MEMORY_FILE, "a", encoding="utf-8") as f:
                f.write(memory_update)
            self.memory_content += memory_update
            # Lernen
            self._learn_from_interaction(user_message, bot_response, timestamp)
            # Prüfen ob Memory zu groß wird
            if len(self.memory_content) > self.max_memory_size:
                self._archive_old_memory()
        except Exception as e:
            logger.error(f"Memory Update fehlgeschlagen: {e}")
        self.update_heartbeat()
    def _archive_old_memory(self):
        """Archiviert alten Memory-Inhalt"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Erstelle memory_archive Verzeichnis falls nicht vorhanden
            archive_dir = Path(__file__).parent.parent / "memory_archive"
            archive_dir.mkdir(exist_ok=True)
            archive_name = archive_dir / f"MEMORY_ARCHIVE_{timestamp}.md"
            # Aktuellen Memory-Inhalt aufteilen
            lines = self.memory_content.split('\n')
            # Erste Hälfte archivieren
            archive_content = '\n'.join(lines[:len(lines)//2])
            with open(archive_name, "w", encoding="utf-8") as f:
                f.write(f"""# GABI Memory Archiv vom {datetime.now().strftime('%Y-%m-%d %H:%M')}
{archive_content}
""")
            # Memory auf die letzte Hälfte reduzieren
            self.memory_content = '\n'.join(lines[len(lines)//2:])
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                f.write(self.memory_content)
            logger.info(f"Memory archiviert: {archive_name}")
        except Exception as e:
            logger.error(f"Archivierung fehlgeschlagen: {e}")
    def update_heartbeat(self):
        """Aktualisiert den Heartbeat mit aktuellen Status"""
        try:
            models_info = ollama_client.list_models()
            models_available = len(models_info.get("models", []))
            import shutil
            _, used, free = shutil.disk_usage("/")
            allowed_commands = config.get("shell.allowed_commands", [])
            # Letzte Exploration finden
            last_exploration = "Keine"
            if "Auto-Exploration" in self.memory_content:
                explorations = re.findall(r"## 🔍 Auto-Exploration \[(.*?)\]", self.memory_content)
                if explorations:
                    last_exploration = explorations[-1]
            # Archive zählen
            archives = self.list_chat_archives()
            heartbeat = f"""# GABI Heartbeat & Monitoring
## Aktueller Status ({datetime.now().strftime('%d.%m.%Y %H:%M')})
| Dienst | Status | Details |
|--------|--------|---------|
| FastAPI | 🟢 Online | Port 8000 |
| Ollama | 🟢 Connected | {models_available} Modelle |
| Auto-Exploration | {'🟢 Aktiv' if not self.is_exploring else '🟡 Erkundet'} | Letzte: {last_exploration} |
| Chat-Archiv | 🟢 Bereit | {len(archives)} Archive |
| Shell | 🟢 Bereit | {len(allowed_commands)} Befehle |
## System-Ressourcen
- **Speicher frei**: {round(free / (2**30), 2)} GB
- **Betriebssystem**: {platform.system()} {platform.release()}
- **Letzte Aktivität**: vor {int((datetime.now() - self.last_activity).total_seconds() / 60)} Min.
- **Chat-Verlauf**: {len(self.conversation_history) // 2} Austausche
## Letzte Aktivitäten
"""
            # Letzte 5 Konversationen anhängen
            for i, msg in enumerate(self.conversation_history[-5:]):
                role = "👤 User" if msg["role"] == "user" else "🤖 GABI"
                content = (
                    msg["content"][:50] + "..."
                    if len(msg["content"]) > 50
                    else msg["content"]
                )
                heartbeat += f"- {role}: {content}\n"
            self._write_file(HEARTBEAT_FILE, heartbeat)
            self.heartbeat_content = heartbeat
        except Exception as e:
            logger.error(f"Heartbeat Update fehlgeschlagen: {e}")
    def get_communication_style(self):
        """Analysiert den Kommunikationsstil des Nutzers und gibt eine Anpassung zurück"""
        if len(self.conversation_history) < 4:
            return ""
        # Analyse der letzten Nutzer-Nachrichten
        user_msgs = [msg["content"] for msg in self.conversation_history if msg["role"] == "user"][-10:]
        if not user_msgs:
            return ""
        # Durchschnittliche Länge berechnen
        avg_len = sum(len(msg) for msg in user_msgs) / len(user_msgs)
        # Stil-Empfehlungen
        style_recommendations = []
        if avg_len < 50:
            style_recommendations.append("- Nutzer mag **kurze, prägnante** Antworten")
        elif avg_len > 200:
            style_recommendations.append("- Nutzer schätzt **ausführliche Erklärungen**")
        else:
            style_recommendations.append("- Nutzer bevorzugt **ausgewogene** Antworten")
        # Fachbegriffe erkennen
        tech_terms = ['python', 'git', 'shell', 'api', 'json', 'config', 'code', 'terminal', 'cmd', 'bash']
        tech_count = sum(1 for msg in user_msgs for term in tech_terms if term in msg.lower())
        if tech_count > 3:
            style_recommendations.append("- Nutzer ist **technisch versiert** - Fachbegriffe können verwendet werden")
        else:
            style_recommendations.append("- Nutzer ist **weniger technisch** - Begriffe erklären")
        # Informell/Formell erkennen
        informal_words = ['hallo', 'hi', 'hey', 'tschau', 'bye', 'cool', 'super', '😊', '👍']
        formal_words = ['bitte', 'danke', 'könnten sie', 'würden sie', 'grüß gott']
        all_text = ' '.join(user_msgs).lower()
        informal_score = sum(1 for w in informal_words if w in all_text)
        formal_score = sum(1 for w in formal_words if w in all_text)
        if informal_score > formal_score:
            style_recommendations.append("- Nutzer kommuniziert **informell** - duzend und locker")
        else:
            style_recommendations.append("- Nutzer kommuniziert **eher formell** - respektvoll bleiben")
        # Emoji-Nutzung
        emoji_count = sum(1 for msg in user_msgs for c in msg if c in ['😊', '👍', '🎉', '❤️', '😂', '🙏'])
        if emoji_count > 2:
            style_recommendations.append("- Nutzer verwendet **Emojis** - kann auch in Antworten verwendet werden")
        # Fragehäufigkeit
        question_count = sum(1 for msg in user_msgs if '?' in msg)
        if question_count / len(user_msgs) > 0.5:
            style_recommendations.append("- Nutzer stellt **viele Fragen** - antworte klar und direkt")
        # Zusammenbauen
        if style_recommendations:
            return "\n".join(style_recommendations)
        else:
            return ""

def select_best_model(prompt: str, requested_model: str = None) -> str:
    """
    Wählt automatisch das passende Modell basierend auf der Komplexität.

    Args:
        prompt: Die Benutzer-Eingabe
        requested_model: Explizit angefordertes Modell (hat Vorrang!)

    Returns:
        Modell-Name
    """
    # 1. Wenn der Benutzer ein Modell explizit angegeben hat -> IMMER verwenden!
    if requested_model and requested_model.strip() and requested_model != "__AUTO__":
        logger.info(f"📌 Benutzer hat Modell gewählt: {requested_model}")
        return requested_model.strip()

    # 2. Bei __AUTO__ oder None: automatische Auswahl
    logger.info("🤖 Auto-Modus: Wähle bestes Modell basierend auf Anfrage")
    
    try:
        models_info = ollama_client.list_models()
        available = [m.get("name") for m in models_info.get("models", [])]
        
        if not available:
            return config.get("ollama.default_model", "llama3")
        
        # Hier deine existierende Logik für die automatische Auswahl...
        # (Code für Komplexitätsanalyse etc.)
        
        # Fallback:
        return config.get("ollama.default_model", "llama3")
        
    except Exception as e:
        logger.error(f"Fehler bei Modell-Auswahl: {e}")
        return config.get("ollama.default_model", "llama3")

# Globale Memory-Instanz
chat_memory = ChatMemory()




#######################################################################
# =====================================================================
# ============ Ollama Chat Endpoints ============
# =====================================================================
#######################################################################
@router.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Liefert das Admin-Dashboard aus dem static-Ordner."""
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1 style='color:red'>Fehler: static/index.html nicht gefunden!</h1>"
# In http_api.py - Erweiterter Chat-Endpoint
@router.post("/chat")
async def chat_with_gabi(request: ChatRequest, token: str = Header(None, alias="token")):
    """🧠 GABI nutzt ihr volles Gehirn mit beiden Hemisphären!"""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    
    request_id = (request.request_id or "").strip() or f"gabi-{uuid.uuid4().hex[:12]}"
    _progress_init(request_id)
    _progress_add(request_id, "🧠 GABI Gehirn aktiviert", "fa-brain")

    try:
        _ensure_not_cancelled(request_id)

        # DEBUG: Log das empfangene Modell
        logger.info(f"📥 ChatRequest empfangen - model: {request.model!r}")

        user_message = request.message

        # ===== 1. PRIO 1: DIREKTE BEFEHLE (User will explizit Befehl) =====
        if user_message.startswith('/'):
            logger.info(f"⚡ Direkter Befehl erkannt: {user_message}")
            _progress_add(request_id, f"Linke Hemisphäre: Verarbeite Befehl", "fa-terminal")
            cmd_result = await handle_command(user_message, token)
            if isinstance(cmd_result, dict):
                steps = cmd_result.get("thinking_steps", [])
                if cmd_result.get("command_executed"):
                    steps.append({
                        "text": f"Execute: {cmd_result.get('command_executed')}",
                        "icon": "fa-terminal",
                        "time": datetime.now().isoformat(),
                        "details": cmd_result.get("stdout_excerpt") or cmd_result.get("reply", "")[:1800],
                    })
                if cmd_result.get("tool_used"):
                    steps.append({
                        "text": f"Tool: {cmd_result.get('tool_used')}",
                        "icon": "fa-tools",
                        "time": datetime.now().isoformat(),
                    })
                if steps:
                    cmd_result["thinking_steps"] = steps
                cmd_result["request_id"] = request_id
                cmd_result["hemisphere"] = "left"
            return cmd_result

        # ===== 2. PRIO 2: GUI-BEFEHLE (sehr spezifische Muster) =====
        gui_result = await _detect_and_execute_gui_command(user_message, token)
        if gui_result:
            if isinstance(gui_result, dict):
                gui_result["request_id"] = request_id
                gui_result["priority"] = "gui"
                _progress_add(request_id, f"🖥️ GUI-Befehl erkannt: {gui_result.get('executed_command', '')}", "fa-desktop")
            return gui_result

        # ===== 3. PRIO 3: SEMANTISCHE INTENT-ERKENNUNG (nur einmal!) =====
        intent_result = _classify_intent_enhanced(user_message)
        logger.info(f"🎯 Intent erkannt: {intent_result['intent']} (Confidence: {intent_result['confidence']:.2f})")
        
        # ===== 4. PRIO 4: SoM INTENTS AUSFÜHREN =====
        if intent_result.get("intent", "").startswith("som_"):
            intent = intent_result["intent"]
            
            if intent == "som_search":
                query = intent_result.get("query", user_message)
                logger.info(f"🔍 SoM Search automatisch erkannt: {query}")
                _progress_add(request_id, f"🔍 SoM Suche: {query}", "fa-search")
                
                from gateway.integrations.som_agent import get_som_agent
                agent = get_som_agent(headless=True)
                result = await agent.navigate(
                    url="https://www.startpage.com",
                    goal=f"Suche nach '{query}'",
                    max_steps=5
                )
                
                if result.get("success"):
                    extracted = result.get("extracted_content", {})
                    results = extracted.get("search_results", [])
                    
                    if results:
                        reply = f"🔍 **Suchergebnisse für '{query}':**\n\n"
                        for i, res in enumerate(results[:10], 1):
                            reply += f"{i}. **{res.get('title', 'Kein Titel')}**\n"
                            reply += f"   🔗 {res.get('url', '')[:80]}\n\n"
                        
                        return {
                            "status": "success",
                            "reply": reply,
                            "timestamp": datetime.now().isoformat(),
                            "tool_used": "som_search_auto",
                            "request_id": request_id,
                            "intent": intent,
                            "hemisphere": "right"
                        }
                    else:
                        return {
                            "status": "success",
                            "reply": f"🔍 Keine Ergebnisse für '{query}' gefunden.",
                            "request_id": request_id
                        }
                else:
                    return {
                        "status": "error",
                        "reply": f"❌ Suche fehlgeschlagen: {result.get('error')}",
                        "request_id": request_id
                    }
            
            elif intent == "som_navigate":
                url = intent_result.get("url", "")
                if not url:
                    url_match = re.search(r'(https?://[^\s]+|[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', user_message)
                    if url_match:
                        url = url_match.group(1)
                        if not url.startswith(('http://', 'https://')):
                            url = 'https://' + url
                
                if url:
                    logger.info(f"🌐 SoM Navigation automatisch erkannt: {url}")
                    _progress_add(request_id, f"🌐 SoM Navigation: {url}", "fa-globe")
                    
                    from gateway.integrations.som_agent import get_som_agent
                    agent = get_som_agent(headless=False)
                    result = await agent.navigate(
                        url=url,
                        goal="Erkunde die Seite und extrahiere wichtige Informationen",
                        max_steps=3
                    )
                    
                    if result.get("success"):
                        extracted = result.get("extracted_content", {})
                        title = extracted.get('title', 'Kein Titel')
                        
                        reply = f"🌐 **{title}**\n\n"
                        reply += f"🔗 {url}\n\n"
                        
                        text = extracted.get('text', '')
                        if text:
                            preview = text[:500].replace('\n', ' ')
                            reply += f"📄 **Inhaltsvorschau:**\n{preview}...\n\n"
                        
                        links = extracted.get('links', [])[:5]
                        if links:
                            reply += f"🔗 **Wichtige Links:**\n"
                            for link in links:
                                link_text = link.get('text', '')[:50]
                                link_url = link.get('href', '')[:80]
                                if link_text:
                                    reply += f"• [{link_text}]({link_url})\n"
                        
                        return {
                            "status": "success",
                            "reply": reply,
                            "timestamp": datetime.now().isoformat(),
                            "tool_used": "som_navigate_auto",
                            "request_id": request_id,
                            "intent": intent,
                            "hemisphere": "right"
                        }
            
            elif intent == "som_learned":
                logger.info("🧠 SoM Learned automatisch erkannt")
                _progress_add(request_id, "🧠 Zeige gelernte Inhalte", "fa-brain")
                
                from gateway.integrations.som_agent import get_som_agent
                agent = get_som_agent()
                learned = agent.memory.get("learned_actions", [])[-10:]
                
                if not learned:
                    return {
                        "status": "success",
                        "reply": "📭 Ich habe noch nichts gelernt. Stelle mir Fragen oder führe Suchen durch!",
                        "request_id": request_id
                    }
                
                reply = "🧠 **Was ich bisher gelernt habe:**\n\n"
                for i, entry in enumerate(learned[:5], 1):
                    if entry.get("url"):
                        reply += f"{i}. 🌐 **{entry.get('url', '')[:60]}**\n"
                        reply += f"   🎯 {entry.get('goal', '')[:80]}\n"
                        content = entry.get('content', {})
                        results_count = len(content.get('search_results', []))
                        if results_count:
                            reply += f"   📊 {results_count} Suchergebnisse\n"
                        reply += "\n"
                
                if len(learned) > 5:
                    reply += f"\n*... und {len(learned) - 5} weitere Einträge.*\n"
                
                return {
                    "status": "success",
                    "reply": reply,
                    "timestamp": datetime.now().isoformat(),
                    "tool_used": "som_learned_auto",
                    "request_id": request_id,
                    "intent": intent,
                    "hemisphere": "right"
                }
            
            elif intent == "som_stats":
                logger.info("📊 SoM Stats automatisch erkannt")
                _progress_add(request_id, "📊 Zeige SoM Statistiken", "fa-chart-bar")
                
                from gateway.integrations.som_agent import get_som_agent
                from pathlib import Path
                import json
                
                agent = get_som_agent()
                learned = agent.memory.get("learned_actions", [])
                
                total_results = 0
                urls = set()
                for entry in learned:
                    if entry.get("url"):
                        urls.add(entry.get("url"))
                    content = entry.get("content", {})
                    total_results += len(content.get("search_results", []))
                
                memory_file = Path(__file__).parent.parent / "integrations" / "som_memory.json"
                memory_size = memory_file.stat().st_size if memory_file.exists() else 0
                
                reply = f"📊 **SoM Agent Statistiken:**\n\n"
                reply += f"📚 **Gelernte Aktionen:** {len(learned)}\n"
                reply += f"🌐 **Besuchte URLs:** {len(urls)}\n"
                reply += f"🔍 **Gespeicherte Suchergebnisse:** {total_results}\n"
                reply += f"💾 **Memory-Größe:** {memory_size / 1024:.1f} KB\n"
                
                return {
                    "status": "success",
                    "reply": reply,
                    "timestamp": datetime.now().isoformat(),
                    "tool_used": "som_stats_auto",
                    "request_id": request_id,
                    "intent": intent,
                    "hemisphere": "right"
                }
                
            elif intent == "som_answer":
                logger.info("📚 SoM Answer erkannt – suche im Memory")
                _progress_add(request_id, "📚 Suche in gelernten Inhalten", "fa-database")
                
                from gateway.integrations.som_agent import get_som_agent
                from gateway.integrations.som_semantic import get_som_semantic
                import json
                
                query = intent_result.get("query", user_message)
                
                # 1. Semantische Suche im SoM Memory
                semantic = get_som_semantic()
                results = semantic.search_results(query, top_k=5)
                
                if not results:
                    # Keine relevanten Inhalte im Memory
                    logger.info("📭 Keine relevanten Inhalte im SoM Memory gefunden")
                    _progress_add(request_id, "📭 Keine relevanten gelernten Inhalte", "fa-database")
                    # Fallthrough – wird später von Corpus Callosum verarbeitet
                    pass
                else:
                    # 2. Kontext für LLM erstellen
                    context = "Basierend auf meinen gelernten Suchergebnissen:\n\n"
                    for i, res in enumerate(results[:3], 1):
                        title = res.get('title', 'Kein Titel')
                        url = res.get('url', '')
                        snippet = res.get('snippet', '')
                        context += f"{i}. **{title}**\n"
                        context += f"   🔗 {url}\n"
                        if snippet:
                            context += f"   📝 {snippet}\n\n"
                    
                    # 3. LLM Prompt mit Kontext
                    prompt = f"""Beantworte die folgende Frage basierend auf den verfügbaren Informationen.
Wenn die Informationen nicht ausreichen, sage das ehrlich.

Frage: {query}

{context}

Antwort:"""
                    
                    # 4. Modell für Antwort wählen (fast, da nur Zusammenfassung)
                    models_info = ollama_client.list_models()
                    available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
                    fast_model = _pick_fast_model(available) or DEFAULT_MODEL
                    
                    _progress_add(request_id, f"🤖 Generiere Antwort mit {fast_model}", "fa-brain")
                    _progress_set_active_model(request_id, fast_model)
                    
                    response = await _ollama_chat_async(
                        model=fast_model,
                        messages=[{"role": "user", "content": prompt}],
                        options={"temperature": 0.3, "num_predict": 500}
                    )
                    
                    answer = _extract_ollama_text(response) or "Keine Antwort erhalten"
                    
                    # 5. Quellen anzeigen
                    sources = "\n\n📚 **Quellen:**\n" + "\n".join([f"• {r.get('title', '')[:60]}\n  {r.get('url', '')}" for r in results[:3]])
                    
                    return {
                        "status": "success",
                        "reply": f"🧠 **Aus meinem Wissen:**\n\n{answer}{sources}",
                        "timestamp": datetime.now().isoformat(),
                        "tool_used": "som_answer",
                        "request_id": request_id,
                        "intent": intent,
                        "hemisphere": "right",
                        "sources": results[:3]
                    }
                

        # ===== 5. PRIO 5: SHELL-ERKENNUNG (nur als Fallback) =====
        # Nur wenn Intent "chat" oder niedrige Confidence
        if intent_result.get("intent") == "chat" or intent_result.get("confidence", 0) < 0.6:
            shell_result = await _detect_and_execute_shell_command(user_message, token)
            if shell_result:
                if isinstance(shell_result, dict):
                    shell_result["request_id"] = request_id
                    shell_result["priority"] = "shell"
                    _progress_add(request_id, f"💻 Shell-Befehl erkannt: {shell_result.get('executed_command', '')}", "fa-terminal")
                return shell_result

        # ===== 6. CORPUS CALLOSUM + NORMALE CHAT-VERARBEITUNG =====
        # ===== CORPUS CALLOSUM - DIE BRÜCKE ZWISCHEN DEN HEMISPHÄREN =====
        from corpus_callosum import get_brain
        brain = get_brain()
        brain.initialize_hemispheres()
        
        _progress_add(request_id, "Corpus Callosum aktiv - Verbinde Hemisphären", "fa-link")
        
        # ===== 1. PRÜFE OB ES EIN DIREKTER BEFEHL IST =====
        if request.message.startswith('/'):
            logger.info(f"⚡ Direkter Befehl erkannt: {request.message}")
            _progress_add(request_id, f"Linke Hemisphäre: Verarbeite Befehl", "fa-terminal")
            cmd_result = await handle_command(request.message, token)
            if isinstance(cmd_result, dict):
                steps = cmd_result.get("thinking_steps", [])
                if cmd_result.get("command_executed"):
                    steps.append(
                        {
                            "text": f"Execute: {cmd_result.get('command_executed')}",
                            "icon": "fa-terminal",
                            "time": datetime.now().isoformat(),
                            "details": cmd_result.get("stdout_excerpt") or cmd_result.get("reply", "")[:1800],
                        }
                    )
                if cmd_result.get("tool_used"):
                    steps.append(
                        {
                            "text": f"Tool: {cmd_result.get('tool_used')}",
                            "icon": "fa-tools",
                            "time": datetime.now().isoformat(),
                        }
                    )
                if steps:
                    cmd_result["thinking_steps"] = steps
                cmd_result["request_id"] = request_id
                cmd_result["hemisphere"] = "left"  # Linke Hemisphäre war aktiv
            return cmd_result
        
        # ===== 2. GEDÄCHTNIS INTEGRIEREN (BEIDE HEMISPHÄREN NUTZEN MEMORY) =====
        user_message = request.message
        
        import platform
        import re

        system_os = platform.system()
        dir_cmd = "dir" if system_os == "Windows" else "ls -la"

        # Shell-Keywords für natürliche Sprache (Fallback)
        shell_patterns = [
            # === DATEI-ERSTELLUNG (MIT INHALT) ===
            (r'^(?:erstelle|create)\s+datei\s+(\S+)\s+mit\s+inhalt\s+(.+)$', 
            "echo {} > {}"),
            
            # === DATEI-ERSTELLUNG (LEER) ===
            (r'^(?:erstelle|create)\s+datei\s+(\S+)$', 
            "echo '' > {}"),
            
            # === DATEI-LISTEN (speziell für Python) ===
            (r'^(?:zeig|list|show)\s+mir\s+alle\s+python\s+dateien$', 
            f"{dir_cmd} *.py"),
            (r'^(?:zeig|list|show)\s+mir\s+python\s+dateien$', 
            f"{dir_cmd} *.py"),
            (r'^(?:welche|liste)\s+python\s+dateien\??$', 
            f"{dir_cmd} *.py"),
            
            # === DATEI-LISTEN (alle Dateien) ===
            (r'^(?:zeig|list|show)\s+mir\s+alle\s+dateien$', 
            dir_cmd),
            (r'^(?:zeig|list|show)\s+mir\s+dateien$', 
            dir_cmd),
            (r'^(?:was\s+ist\s+)?im\s+aktuellen\s+ordner\??$', 
            dir_cmd),
            
            # === DATEI-LISTEN (nach Typ) - dynamisch ===
            (r'^(?:zeig|list|show)\s+mir\s+alle\s+(\w+)\s+dateien$', 
            f"{dir_cmd} *.{{}}"),
            
            # === DATEI LÖSCHEN ===
            (r'^(?:lösche|delete|remove)\s+datei\s+(\S+)$', 
            "del {}" if system_os == "Windows" else "rm {}"),
            
            # === DATEI ANZEIGEN ===
            (r'^(?:zeig|lies|read)\s+mir\s+die\s+datei\s+(\S+)$', 
            "type {}" if system_os == "Windows" else "cat {}"),
            
            # === VERZEICHNIS WECHSELN ===
            (r'^(?:gehe|wechsel)\s+ins\s+verzeichnis\s+(\S+)$', 
            "cd {} && pwd" if system_os != "Windows" else "cd {} && cd"),
            
            # === AKTUELLES VERZEICHNIS ===
            (r'^(?:wo\s+bin\s+ich|aktuelles\s+verzeichnis)\??$', 
            "cd" if system_os == "Windows" else "pwd"),
            
            # === PROZESSE ===
            (r'^(?:zeig|list|show)\s+mir\s+alle\s+prozesse$', 
            "tasklist" if system_os == "Windows" else "ps aux"),
            
            # === SYSTEMINFO ===
            (r'^(?:zeig|list|show)\s+mir\s+systeminfo$', 
            "systeminfo" if system_os == "Windows" else "uname -a"),
        ]



        # Fallback: Pattern-basierte Erkennung (wenn LLM nicht greift)
        for pattern, cmd_template in shell_patterns:
            match = re.search(pattern, user_message.lower(), re.IGNORECASE)
            if match:
                if "{}" in cmd_template:
                    groups = match.groups()
                    groups = [g for g in groups if g is not None]
                    placeholder_count = cmd_template.count("{}")
                    
                    if len(groups) == 1 and placeholder_count == 1:
                        cmd = cmd_template.format(groups[0])
                    elif len(groups) == 1 and placeholder_count == 2:
                        cmd = cmd_template.format("", groups[0])
                    elif len(groups) == 2:
                        if "echo" in cmd_template and ">" in cmd_template:
                            cmd = cmd_template.format(groups[1], groups[0])
                        else:
                            cmd = cmd_template.format(groups[0], groups[1])
                    else:
                        cmd = cmd_template
                else:
                    cmd = cmd_template
                
                # Führe Shell-Befehl direkt aus
                logger.info(f"🔧 Shell-Erkennung: '{user_message}' → /shell {cmd}")
                _progress_add(request_id, f"Shell-Erkennung: /shell {cmd}", "fa-terminal")
                
                cmd_result = await handle_command(f"/shell {cmd}", token)
                if isinstance(cmd_result, dict):
                    cmd_result["request_id"] = request_id
                    cmd_result["tool_used"] = "shell_detected"
                return cmd_result

        
        # Prüfe ob die Nachricht einem Shell-Muster entspricht
        for pattern, cmd_template in shell_patterns:
            match = re.search(pattern, user_message.lower(), re.IGNORECASE)
            if match:
                if "{}" in cmd_template:
                    groups = match.groups()
                    groups = [g for g in groups if g is not None]
                    placeholder_count = cmd_template.count("{}")
                    
                    if len(groups) == 1 and placeholder_count == 1:
                        cmd = cmd_template.format(groups[0])
                    elif len(groups) == 1 and placeholder_count == 2:
                        cmd = cmd_template.format("", groups[0])
                    elif len(groups) == 2:
                        if "echo" in cmd_template and ">" in cmd_template:
                            cmd = cmd_template.format(groups[1], groups[0])
                        else:
                            cmd = cmd_template.format(groups[0], groups[1])
                    else:
                        cmd = cmd_template
                else:
                    cmd = cmd_template
                
                # Führe Shell-Befehl direkt aus
                logger.info(f"🔧 Shell-Erkennung: '{user_message}' → /shell {cmd}")
                _progress_add(request_id, f"Shell-Erkennung: /shell {cmd}", "fa-terminal")
                
                cmd_result = await handle_command(f"/shell {cmd}", token)
                if isinstance(cmd_result, dict):
                    cmd_result["request_id"] = request_id
                    cmd_result["tool_used"] = "shell_detected"
                return cmd_result
        

        
        logger.info(f"📨 GABI empfängt: {user_message}")
        _progress_add(request_id, "Rechte Hemisphäre: Analysiere Nachricht", "fa-search")
        
        # Prüfe auf /merken Befehl (spezielle Memory-Funktion)
        remember_match = re.match(
            r"^\s*(?:merk(?:e)?\s+dir|merken)\s*(?::|-)?\s*(.+)\s*$",
            user_message,
            re.IGNORECASE,
        )
        if remember_match:
            note_text = remember_match.group(1).strip()
            entry, created = chat_memory.remember_note(note_text, source="chat")
            if not entry:
                return {
                    "status": "error",
                    "reply": "❌ Bitte gib nach `/merken` oder `merk dir` auch den Inhalt an.",
                    "timestamp": datetime.now().isoformat(),
                    "request_id": request_id,
                    "hemisphere": "memory",
                }
            action = "gemerkt" if created else "bereits gemerkt"
            confirmed_at = datetime.fromisoformat(entry["timestamp"]).strftime("%H:%M:%S")
            reply = (
                f"✅ {action.capitalize()}: {entry['text']}\n"
                f"🕒 {confirmed_at}\n"
                "Abrufbar mit `/gemerkt`."
            )
            chat_memory.add_to_memory(user_message, reply)
            return {
                "status": "success",
                "reply": reply,
                "timestamp": datetime.now().isoformat(),
                "model_used": "gabi/memory",
                "request_id": request_id,
                "hemisphere": "both",  # Beide Hemisphären für Memory
            }
        
        # ===== 3. CORPUS CALLOSUM ROUTING - WELCHE HEMISPHÄRE IST ZUSTÄNDIG? =====
        task = {
            "content": user_message,
            "type": "auto",
            "request_id": request_id,
            "context": chat_memory.conversation_history[-10:] if chat_memory.conversation_history else []
        }
        
        # Lasse das Corpus Callosum entscheiden
        routing_result = brain.route_task(task)
        hemisphere = routing_result.get("hemisphere", "bridge")
        detected_type = routing_result.get("detected_type", "chat")

        _progress_add(request_id, f"Corpus Callosum: Routing zu {hemisphere} Hemisphäre (Typ: {detected_type})",
                      "fa-code-branch" if hemisphere == "left" else "fa-paint-brush")

        # === PRÜFE OB DAS BRAIN BEREITS EINE ANTWORT HAT ===
        brain_reply = routing_result.get("reply") or routing_result.get("response") or routing_result.get("result")
        brain_success = routing_result.get("success", True)

        # Prüfe ob Brain eine Suche ausgeführt hat, obwohl der User keine Suche wollte
        EXPLICIT_SEARCH_KEYWORDS = [
            "suche nach", "such nach", "google", "such mir", "recherchiere",
            "finde im internet", "web search", "im internet suchen",
            "aktuelle nachrichten", "was passierte heute", "neueste infos",
        ]
        _msg_lower = user_message.lower()
        _brain_did_search = detected_type == "search" or routing_result.get("tool_used") == "web_search"
        _user_wanted_search = any(kw in _msg_lower for kw in EXPLICIT_SEARCH_KEYWORDS)

        if _brain_did_search and not _user_wanted_search:
            # Brain hat unerwünscht eine Suche gemacht → ignorieren, direkt ans LLM
            logger.info(f"🚫 Brain-Suche ignoriert (kein Such-Keyword) – leite direkt ans LLM weiter")
            brain_reply = None
            brain_success = False

        if brain_reply and brain_success:
            # Brain hat bereits geantwortet - verwende dieses Ergebnis
            chat_memory.add_to_memory(user_message, str(brain_reply))
            return {
                "status": "success",
                "reply": str(brain_reply),
                "timestamp": datetime.now().isoformat(),
                "hemisphere": hemisphere,
                "hemisphere_type": "analytical" if hemisphere == "left" else "creative",
                "task_type": detected_type,
                "model_used": routing_result.get("model_used", "brain"),
                "request_id": request_id,
            }
        elif not brain_success:
            # Brain konnte nicht verarbeiten - fallback auf normale Verarbeitung
            logger.info(f"Brain konnte nicht verarbeiten: {routing_result.get('error', 'unbekannt')}")

        # ===== 4. DEFINITION DER SUCH-TRIGGER (für rechte Hemisphäre) =====
        search_triggers = [
            "suche nach", "such nach"
        ]
        
        # ===== 5. SATZ-ERKENNUNG FÜR KOMPLEXE ANFRAGEN =====
        raw_sentences = re.split(r'(?<=[.!?])\s+|\n+', user_message)
        sentences = [s.strip() for s in raw_sentences if s.strip()]
        
        logger.info(f"📨 GABI erkennt {len(sentences)} Satz/Sätze")
        
        # ===== 6. VERARBEITUNG BASIEREND AUF HEMISPHÄRE =====
        
        # --- LINKE HEMISPHÄRE (analytisch, Code, Shell) ---
        if hemisphere == "left":
            _progress_add(request_id, f"🔵 Linke Hemisphäre aktiv - {detected_type}", "fa-microchip")
            
            if detected_type == "shell":
                # Shell-Befehl ausführen
                cmd_result = await handle_command(f"/shell {user_message}", token)
                return {
                    "status": "success",
                    "reply": cmd_result.get("reply", "Befehl ausgeführt"),
                    "timestamp": datetime.now().isoformat(),
                    "hemisphere": "left",
                    "hemisphere_type": "analytical",
                    "task_type": detected_type,
                    "request_id": request_id,
                }
            
            elif detected_type == "code":
                # Code-Generierung mit Code-Modell
                messages = [
                    {"role": "system", "content": "Du bist GABIs linke, analytische Hemisphäre. Du bist spezialisiert auf Code, Logik und präzise technische Antworten."},
                    {"role": "user", "content": user_message}
                ]
                
                # Verwende Code-spezifisches Modell
                code_model = "codellama"  # oder deepseek-coder
                try:
                    response = await _ollama_chat_async(model=code_model, messages=messages)
                    reply = _extract_ollama_text(response)
                except:
                    # Fallback auf Default-Modell
                    response = await _ollama_chat_async(model=ollama_client.default_model, messages=messages)
                    reply = _extract_ollama_text(response)
                
                chat_memory.add_to_memory(user_message, reply)
                return {
                    "status": "success",
                    "reply": reply,
                    "timestamp": datetime.now().isoformat(),
                    "model_used": code_model,
                    "hemisphere": "left",
                    "hemisphere_type": "analytical",
                    "task_type": detected_type,
                    "request_id": request_id,
                }
            
            elif detected_type == "analysis":
                # System-Analyse mit linkem Gehirn
                import psutil
                import platform
                
                analysis = {
                    "cpu": f"{psutil.cpu_percent()}%",
                    "memory": f"{psutil.virtual_memory().percent}%",
                    "disk": f"{psutil.disk_usage('/').percent}%",
                    "os": platform.system(),
                    "hostname": platform.node()
                }
                
                reply = f"**System-Analyse:**\n"
                reply += f"- CPU: {analysis['cpu']}\n"
                reply += f"- RAM: {analysis['memory']}\n"
                reply += f"- Festplatte: {analysis['disk']}\n"
                reply += f"- OS: {analysis['os']}\n"
                reply += f"- Host: {analysis['hostname']}"
                
                return {
                    "status": "success",
                    "reply": reply,
                    "timestamp": datetime.now().isoformat(),
                    "data": analysis,
                    "hemisphere": "left",
                    "hemisphere_type": "analytical",
                    "task_type": detected_type,
                    "request_id": request_id,
                }
        
            else:
                # --- FALLBACK: Linke Hemisphäre kennt detected_type nicht (z.B. "search" wurde abgefangen) ---
                # → Direkt ans LLM übergeben wie rechte Hemisphäre
                logger.info(f"⬅️ Linke Hemisphäre: unbekannter Typ '{detected_type}' – LLM-Fallback")
                _progress_add(request_id, f"LLM-Fallback für Typ: {detected_type}", "fa-robot")
                thinking_steps: List[Dict[str, str]] = []
                messages = [{"role": "system", "content": chat_memory.get_system_prompt()}]
                if chat_memory.conversation_history:
                    messages.extend(chat_memory.conversation_history[-10:])
                messages.append({"role": "user", "content": user_message})
                selected_model = await asyncio.to_thread(
                    _auto_select_model, user_message, request.model, request_id
                )
                _progress_set_active_model(request_id, selected_model)
                _ensure_not_cancelled(request_id)
                response = await _ollama_chat_async(model=selected_model, messages=messages)
                reply = _extract_ollama_text(response) or "⚠️ Keine Antwort."
                reply = await _execute_llm_shell_commands(reply, token, thinking_steps, request_id)
                chat_memory.add_to_memory(user_message, reply)
                return {
                    "status": "success",
                    "reply": reply,
                    "timestamp": datetime.now().isoformat(),
                    "model_used": selected_model,
                    "thinking_steps": thinking_steps,
                    "hemisphere": "left",
                    "hemisphere_type": "analytical",
                    "task_type": detected_type,
                    "request_id": request_id,
                }

        # --- RECHTE HEMISPHÄRE (kreativ, Vision, Audio, Chat) ---
        else:  # hemisphere == "right" or "bridge"
            _progress_add(request_id, f"🟣 Rechte Hemisphäre aktiv - {detected_type}", "fa-paint-brush")
            
            # Wenn nur ein Satz, normale Verarbeitung
            if len(sentences) == 1:
                sentence_lower = sentences[0].lower()
                
                # Prüfe auf Web-Suche
                is_search = any(trigger in sentence_lower for trigger in search_triggers)
                
                if is_search:
                    # === WEB-SUCHE (rechte Hemisphäre + Werkzeug) ===
                    thinking_steps: List[Dict[str, str]] = []
                    search_term = _extract_search_term(sentences[0], search_triggers)
                    logger.info(f"🔍 Rechte Hemisphäre erkennt Suche: '{search_term}'")
                    _progress_add(request_id, f"Web-Suche: {search_term}", "fa-search")
                    
                    safe_search_term = search_term.replace('"', "'")
                    cmd = f"/shell python tools/web_search.py \"{safe_search_term}\""
                    thinking_steps.append({
                        "text": f"Tool-Aufruf: {cmd}",
                        "icon": "fa-terminal",
                        "time": datetime.now().isoformat(),
                    })
                    
                    result = await handle_command(cmd, token)
                    _ensure_not_cancelled(request_id)
                    search_output = (result.get("reply", "") or "").strip() or "⚠️ Keine Suchergebnisse."
                    
                    # Wenn Zusammenfassung gewünscht
                    if _wants_summary_after_search(sentences[0]):
                        # Hier nur noch eine Variable zuweisen:
                        selected_model = await asyncio.to_thread(
                            _auto_select_model, sentences[0], request.model, request_id
                        )
                        suggested_model = None # Manuell auf None setzen, falls der folgende Code die Variable braucht
                        if suggested_model:
                            _progress_add(request_id, f"💡 Vorschlag: '{suggested_model}' wäre evtl. besser geeignet", "fa-lightbulb")
                        _progress_set_active_model(request_id, selected_model)
                        
                        summary_prompt = (
                            "Fasse die folgenden Suchergebnisse strukturiert zusammen.\n\n"
                            f"Nutzerfrage: {sentences[0]}\n\n"
                            f"Suchergebnisse:\n{search_output[:18000]}"
                        )
                        messages = [
                            {"role": "system", "content": chat_memory.get_system_prompt()},
                            {"role": "user", "content": summary_prompt},
                        ]
                        response = await _ollama_chat_async(model=selected_model, messages=messages)
                        reply = _extract_ollama_text(response) or "⚠️ Keine Zusammenfassung."
                        chat_memory.add_to_memory(sentences[0], reply)
                        
                        return {
                            "status": "success",
                            "reply": reply,
                            "timestamp": datetime.now().isoformat(),
                            "model_used": selected_model,
                            "tool_used": "web_search + summary",
                            "thinking_steps": thinking_steps,
                            "hemisphere": "right",
                            "hemisphere_type": "creative",
                            "request_id": request_id,
                        }
                    
                    return {
                        "status": "success",
                        "reply": f"**Suchergebnisse für '{search_term}':**\n\n{search_output}",
                        "timestamp": datetime.now().isoformat(),
                        "tool_used": "web_search",
                        "thinking_steps": thinking_steps,
                        "hemisphere": "right",
                        "hemisphere_type": "creative",
                        "request_id": request_id,
                    }
                
                else:
                    # === NORMALE KONVERSATION (rechte Hemisphäre) ===
                    logger.info(f"💬 Rechte Hemisphäre: Chat")
                    
                    thinking_steps: List[Dict[str, str]] = []
                    messages = [
                        {"role": "system", "content": chat_memory.get_system_prompt()}
                    ]
                    
                    if chat_memory.conversation_history:
                        messages.extend(chat_memory.conversation_history[-6:])
                    
                    messages.append({"role": "user", "content": sentences[0]})
                    
                    selected_model = await asyncio.to_thread(
                        _auto_select_model, sentences[0], request.model, request_id
                    )
                    _progress_set_active_model(request_id, selected_model)
                    
                    thinking_steps.append({
                        "text": f"Modellwahl: {selected_model}",
                        "icon": "fa-code-branch",
                        "time": datetime.now().isoformat(),
                    })
                    
                    _ensure_not_cancelled(request_id)
                    response = await _ollama_chat_async(model=selected_model, messages=messages)
                    reply = _extract_ollama_text(response) or "⚠️ Keine Antwort."
                    reply = await _execute_llm_shell_commands(reply, token, thinking_steps, request_id)
                    
                    chat_memory.add_to_memory(sentences[0], reply)
                    
                    return {
                        "status": "success",
                        "reply": reply,
                        "timestamp": datetime.now().isoformat(),
                        "model_used": selected_model,
                        "thinking_steps": thinking_steps,
                        "hemisphere": "right",
                        "hemisphere_type": "creative",
                        "request_id": request_id,
                    }
            
            # === MEHRERE SÄTZE - SEQUENTIELLE VERARBEITUNG ===
            results = []
            combined_thinking_steps: List[Dict[str, str]] = []
            
            for i, sentence in enumerate(sentences):
                sentence_lower = sentence.lower()
                is_search = any(trigger in sentence_lower for trigger in search_triggers)
                
                if is_search:
                    # Such-Anfrage
                    search_term = _extract_search_term(sentence, search_triggers)
                    safe_search_term = search_term.replace('"', "'")
                    cmd = f"/shell python tools/web_search.py \"{safe_search_term}\""
                    
                    combined_thinking_steps.append({
                        "text": f"Satz {i+1}: Suche '{search_term}'",
                        "icon": "fa-search",
                        "time": datetime.now().isoformat(),
                    })
                    
                    cmd_result = await handle_command(cmd, token)
                    result_text = (cmd_result.get('reply', '') or '').strip() or '⚠️ Keine Ergebnisse.'
                    
                    results.append({
                        "type": "search",
                        "original": sentence,
                        "query": search_term,
                        "result": result_text
                    })
                    
                else:
                    # Normale Chat-Anfrage
                    messages = [{"role": "system", "content": chat_memory.get_system_prompt()}]
                    
                    # Vorherige Ergebnisse als Kontext
                    for prev_result in results:
                        if prev_result["type"] == "search":
                            messages.append({
                                "role": "assistant",
                                "content": f"[Suche: {prev_result['query']}]\n{prev_result['result'][:8000]}"
                            })
                        else:
                            messages.append({
                                "role": "assistant",
                                "content": prev_result["result"]
                            })
                    
                    messages.append({"role": "user", "content": sentence})
                    
                    selected_model = await asyncio.to_thread(
                        _auto_select_model, sentence, request.model, request_id
                    )
                    
                    combined_thinking_steps.append({
                        "text": f"Satz {i+1}: Chat mit {selected_model}",
                        "icon": "fa-comment",
                        "time": datetime.now().isoformat(),
                    })
                    
                    response = await _ollama_chat_async(model=selected_model, messages=messages)
                    reply = _extract_ollama_text(response) or "⚠️ Keine Antwort."
                    
                    results.append({
                        "type": "chat",
                        "original": sentence,
                        "result": reply
                    })
                    
                    chat_memory.add_to_memory(sentence, reply)
            
            # Alle Ergebnisse kombinieren
            combined_reply = ""
            for i, res in enumerate(results, 1):
                if res["type"] == "search":
                    combined_reply += f"**🔍 Suche {i}:** {res['original']}\n\n{res['result']}\n\n---\n\n"
                else:
                    combined_reply += f"**💬 Antwort {i}:**\n\n{res['result']}\n\n---\n\n"
            
            return {
                "status": "success",
                "reply": combined_reply,
                "timestamp": datetime.now().isoformat(),
                "hemisphere": "right",
                "hemisphere_type": "creative",
                "thinking_steps": combined_thinking_steps,
                "request_id": request_id,
            }
            
    except ChatCancelled:
        _progress_add(request_id, "GABI angehalten", "fa-stop-circle")
        return {
            "status": "error",
            "message": "Anfrage gestoppt",
            "reply": "⏹️ GABI wurde gestoppt.",
            "request_id": request_id,
        }
    except Exception as e:
        logger.error(f"GABI Fehler: {e}")
        _progress_add(request_id, f"Fehler: {e}", "fa-exclamation-triangle")
        return {
            "status": "error",
            "message": str(e),
            "reply": f"❌ {str(e)}",
            "request_id": request_id,
        }
    finally:
        _progress_mark_done(request_id)


# ===== NEUER ENDPOINT: GEHIRN-STATUS =====
@router.get("/brain/status")
# async def brain_status(_api_key: str = Depends(verify_api_key)): # verlangt nach api key.
async def brain_status(_api_key: str = Depends(verify_api_key)):
    """🧠 Zeigt den Status von GABIs Gehirnhälften"""
    try:
        from corpus_callosum import get_brain
        brain = get_brain()
        brain.initialize_hemispheres()
        
        status = brain.get_status()
        
        # Füge zusätzliche Infos hinzu
        status["memory"] = {
            "conversations": len(chat_memory.conversation_history) // 2,
            "notes": len(chat_memory.user_notes),
            "last_activity": chat_memory.last_activity.isoformat() if chat_memory.last_activity else None
        }
        
        return {
            "status": "success",
            "brain": status,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Brain-Status Fehler: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== NEUER ENDPOINT: HEMISPHÄREN WECHSELN =====
@router.post("/brain/hemisphere")
async def switch_hemisphere(
    payload: dict,
    _api_key: str = Depends(verify_api_key)
):
    """🔄 Wechselt die aktive Hemisphäre für Tests"""
    hemisphere = payload.get("hemisphere", "auto")
    
    if hemisphere not in ["left", "right", "auto", "bridge"]:
        raise HTTPException(status_code=400, detail="Ungültige Hemisphäre. Erlaubt: left, right, auto, bridge")
    
    # Hier könntest du eine globale Einstellung speichern
    # Für jetzt nur Bestätigung
    
    return {
        "status": "success",
        "message": f"Hemisphäre auf '{hemisphere}' gesetzt",
        "active": hemisphere,
        "timestamp": datetime.now().isoformat()
    }

@router.get("/api/chat/progress/{request_id}")
async def get_chat_progress(request_id: str, since: int = 0, token: str = Header(None)):
    """Poll live progress steps for a running chat request."""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    return _progress_get(request_id, since=since)

@router.post("/api/chat/stop")
async def stop_chat(payload: dict, token: str = Header(None)):
    """Stop an active chat request and try to abort running Ollama generation."""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")

    request_id = str((payload or {}).get("request_id") or "").strip()
    stopped_models: List[Dict[str, Any]] = []
    target_models: List[str] = []

    if request_id:
        _progress_cancel(request_id)
        _progress_add(request_id, "Stop angefordert", "fa-stop-circle")
        with _CHAT_PROGRESS_LOCK:
            state = _CHAT_PROGRESS.get(request_id) or {}
            active_model = state.get("active_model")
        if active_model:
            target_models.append(active_model)
    else:
        with _CHAT_PROGRESS_LOCK:
            for _rid, state in _CHAT_PROGRESS.items():
                if not state.get("done"):
                    state["cancelled"] = True
                    if state.get("active_model"):
                        target_models.append(state.get("active_model"))

    if not target_models:
        target_models = _list_running_ollama_models()

    seen = set()
    for model in target_models:
        if not model or model in seen:
            continue
        seen.add(model)
        stop_info = _stop_ollama_model(model)
        stopped_models.append(stop_info)

    return {
        "status": "success",
        "request_id": request_id or None,
        "stopped_models": stopped_models,
        "models_attempted": list(seen),
    }

async def handle_command(message: str, token: str):
    """Behandelt Befehle wie /shell, /memory, /soul, /new, /archives, etc."""
    cmd_parts = message[1:].split()
    command = cmd_parts[0].lower()
    args = cmd_parts[1:] if len(cmd_parts) > 1 else []
    
    # ===== DEFINIERE subcmd HIER (wichtig!) =====
    subcmd = args[0].lower() if args else ""
    
    logger.info(f"Verarbeite Befehl: {command} mit Args: {args}")
    
    # ===== GOTO BEFEHL (URL öffnen) =====
    if command == "goto":
        if not args:
            return {
                "status": "error",
                "reply": "❌ Bitte URL angeben: `/goto <url>`\nBeispiel: `/goto google.com`\nAuch HTTPS/HTTP wird unterstützt."
            }
        
        url = ' '.join(args).strip()
        url = url.strip('"\'')
        
        # Falls keine URL-Scheme vorhanden, füge https:// hinzu
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Optional: Browser aus args (falls vorhanden)
        browser = "chrome"
        if len(args) > 1 and args[0].lower() in ["chrome", "firefox", "edge", "opera"]:
            browser = args[0].lower()
            url = ' '.join(args[1:]).strip()
        
        logger.info(f"🌐 GUI Goto: {url} mit {browser}")
        
        try:
            # 1. Browser öffnen (falls nicht offen)
            open_result = await handle_command(f"/gui open {browser}", token)
            
            # Prüfe ob Browser erfolgreich gestartet wurde
            if isinstance(open_result, dict) and open_result.get("status") == "error":
                return {
                    "status": "error",
                    "reply": f"❌ Browser '{browser}' konnte nicht gestartet werden: {open_result.get('reply', 'Unbekannter Fehler')}"
                }
            
            # Kurze Pause für Browser-Start
            await asyncio.sleep(1.0)
            
            # 2. Fokussiere URL-Leiste (Ctrl+L ist universell)
            await handle_command("/gui hotkey ctrl l", token)
            await asyncio.sleep(0.3)
            
            # 3. URL eingeben
            await handle_command(f'/gui type "{url}"', token)
            await asyncio.sleep(0.2)
            
            # 4. Enter drücken
            await handle_command("/gui press enter", token)
            
            # Erfolgsmeldung
            return {
                "status": "success",
                "reply": f"✅ Navigiere zu {url} mit {browser}",
                "url": url,
                "browser": browser,
                "tool_used": "gui-goto"
            }
            
        except Exception as e:
            logger.error(f"GUI Goto Fehler: {e}")
            return {
                "status": "error",
                "reply": f"❌ Fehler beim Navigieren zu {url}: {str(e)}"
            }
    
    # ===== SHELL-BEFEHLE MIT PIPE-UNTERSTÜTZUNG =====
    if command in ["shell", "cmd", "bash", "powershell"]:
        if not args:
            return {
                "status": "success",
                "reply": "❌ Bitte einen Befehl angeben, z.B. `/shell python tools/web_search.py mars-news | python tools/formatter.py table`"
            }
        
        try:
            # Ganzen Befehl als String
            full_command = ' '.join(args)
            
            # Prüfe auf Pipe (|) für Formatierung
            if '|' in full_command:
                # Teile den Befehl an der Pipe
                cmd_parts = full_command.split('|')
                main_cmd = cmd_parts[0].strip()
                pipe_cmd = '|'.join(cmd_parts[1:]).strip()
                
                logger.info(f"🔄 Pipe erkannt: {main_cmd} | {pipe_cmd}")
                
                # Führe Hauptbefehl aus
                import subprocess
                import sys
                
                # Hauptbefehl ausführen
                main_result = await asyncio.to_thread(
                    subprocess.run,
                    main_cmd,
                    capture_output=True,
                    text=True,
                    shell=True,
                    timeout=30,
                    encoding='utf-8',
                    errors='replace',
                )
                
                if main_result.returncode == 0 and main_result.stdout:
                    try:
                        # Leite stdout an den Formatter weiter
                        formatter_result = await asyncio.to_thread(
                            subprocess.run,
                            pipe_cmd,
                            input=main_result.stdout,
                            capture_output=True,
                            text=True,
                            shell=True,
                            timeout=10,
                            encoding='utf-8',
                            errors='replace',
                        )
                        
                        # Prüfe ob der Formatter erfolgreich war
                        if formatter_result.returncode == 0 and formatter_result.stdout:
                            # Formatter Ausgabe
                            return {
                                "status": "success",
                                "reply": f"```\n{formatter_result.stdout}\n```",
                                "raw_output": main_result.stdout,
                                "formatted": True
                            }
                        else:
                            # Formatter fehlgeschlagen, zeige rohe Ausgabe + Fehler
                            error_msg = formatter_result.stderr if formatter_result.stderr else "Unbekannter Formatter-Fehler"
                            return {
                                "status": "success",
                                "reply": f"```\n{main_result.stdout}\n```\n\n⚠️ Formatter Fehler:\n```\n{error_msg}\n```",
                                "raw_output": main_result.stdout,
                                "formatted": False
                            }
                    except Exception as e:
                        # Fallback: Zeige rohe Ausgabe
                        return {
                            "status": "success",
                            "reply": f"```\n{main_result.stdout}\n```\n\n⚠️ Formatter Exception: {str(e)}",
                            "raw_output": main_result.stdout
                        }
                else:
                    # Hauptbefehl fehlgeschlagen
                    error_output = main_result.stderr if main_result.stderr else f"Exit-Code: {main_result.returncode}"
                    return {
                        "status": "success",
                        "reply": f"❌ **Fehler bei Ausführung:**\n```\n{error_output}\n```"
                    }
            
            # Normale Ausführung ohne Pipe
            shell_request = ShellRequest(command=args[0], 
                                       args=args[1:] if len(args) > 1 else [])
            result = await execute_command(shell_request, token)
            
            if result.get("status") == "success":
                output = result.get('stdout', '')
                cmd_executed = result.get("command_executed")
                if output:
                    return {
                        "status": "success",
                        "reply": f"```\n{output[:4000]}\n```",
                        "tool_used": "shell",
                        "command_executed": cmd_executed,
                        "stdout_excerpt": output[:1800],
                    }
                else:
                    return {
                        "status": "success",
                        "reply": f"✅ Befehl ausgeführt (keine Ausgabe)",
                        "tool_used": "shell",
                        "command_executed": cmd_executed,
                    }
            else:
                return {
                    "status": "success",
                    "reply": f"❌ Fehler: {result.get('stderr', 'Unbekannter Fehler')}",
                    "tool_used": "shell",
                    "command_executed": result.get("command_executed"),
                }
                
        except subprocess.TimeoutExpired:
            return {
                "status": "success",
                "reply": "❌ Timeout: Der Befehl wurde nach 30 Sekunden abgebrochen."
            }
        except Exception as e:
            logger.error(f"Shell-Befehl Fehler: {e}")
            return {
                "status": "success",
                "reply": f"❌ **Fehler beim Ausführen:**\n```\n{str(e)}\n```"
            }

    # ===== GUI-CONTROLLER BEFEHLE =====
    if command == "gui":
        if not args:
            return {
                "status": "success",
                "reply": "🖥️ **GUI-Controller Befehle:**\n\n" +
                        "`/gui open <programm>` - Programm öffnen (chrome, notepad, outlook...)\n" +
                        "`/gui goto <url>` - URL im Browser öffnen (z.B. `/gui goto google.com`)\n" +
                        "`/gui click <x> <y>` - An Position klicken\n" +
                        "`/gui type <text>` - Text eingeben\n" +
                        "`/gui press <taste>` - Taste drücken (enter, tab, esc...)\n" +
                        "`/gui screenshot` - Screenshot machen\n" +
                        "`/gui windows` - Liste alle Fenster"
            }

        # subcmd = args[0].lower()

        try:
            from gateway.integrations.gui_controller import get_gui_controller
            gui = get_gui_controller()

            if subcmd == "open":
                if len(args) < 2:
                    return {"status": "error", "reply": "❌ Bitte Programmname angeben: `/gui open chrome`"}
                program = args[1]
                result = gui.win_search_and_open(program)
                if result.get("success"):
                    return {"status": "success", "reply": f"✅ {result.get('message', 'Programm gestartet')}"}
                else:
                    return {"status": "error", "reply": f"❌ Fehler: {result.get('error', 'Unbekannter Fehler')}"}

            elif subcmd == "goto":
                if len(args) < 2:
                    return {"status": "error", "reply": "❌ Bitte URL angeben: `/gui goto <url>`\nBeispiel: `/gui goto google.com`"}
                
                url = args[1].strip()
                url = url.strip('"\'')
                
                if not url.startswith(('http://', 'https://')):
                    url = 'https://' + url
                
                logger.info(f"🌐 GUI Goto: {url}")
                
                # 1. Browser öffnen (falls nicht offen)
                open_result = await handle_command("/gui open chrome", token)
                
                await asyncio.sleep(1.0)
                
                # 2. URL-Leiste fokussieren
                await handle_command("/gui hotkey ctrl l", token)
                await asyncio.sleep(0.3)
                
                # 3. URL eingeben
                await handle_command(f'/gui type "{url}"', token)
                await asyncio.sleep(0.2)
                
                # 4. Enter drücken
                await handle_command("/gui press enter", token)
                
                return {
                    "status": "success",
                    "reply": f"✅ Navigiere zu {url}",
                    "url": url,
                    "tool_used": "gui-goto"
                }

            elif subcmd == "click":
                if len(args) < 3:
                    return {"status": "error", "reply": "❌ Bitte X und Y angeben: `/gui click 500 300`"}
                try:
                    x, y = int(args[1]), int(args[2])
                    result = gui.safe_click(x, y)
                    if result.get("success"):
                        return {"status": "success", "reply": f"✅ Geklickt bei ({x}, {y})"}
                    else:
                        return {"status": "error", "reply": f"❌ Fehler: {result.get('error')}"}
                except ValueError:
                    return {"status": "error", "reply": "❌ Ungültige Koordinaten. Beispiel: `/gui click 500 300`"}

            elif subcmd == "type":
                if len(args) < 2:
                    return {"status": "error", "reply": "❌ Bitte Text angeben: `/gui type Hallo Welt`"}
                text = ' '.join(args[1:])
                result = gui.type_text(text)
                if result.get("success"):
                    return {"status": "success", "reply": f"✅ Text eingegeben: '{text}'"}
                else:
                    return {"status": "error", "reply": f"❌ Fehler: {result.get('error')}"}

            elif subcmd == "press":
                if len(args) < 2:
                    return {"status": "error", "reply": "❌ Bitte Taste angeben: `/gui press enter`"}
                key = args[1]
                result = gui.press_key(key)
                if result.get("success"):
                    return {"status": "success", "reply": f"✅ Taste gedrückt: {key}"}
                else:
                    return {"status": "error", "reply": f"❌ Fehler: {result.get('error')}"}

            elif subcmd == "hotkey":
                if len(args) < 2:
                    return {"status": "error", "reply": "❌ Bitte Tasten angeben: `/gui hotkey ctrl l`"}
                keys = args[1:]
                result = gui.hotkey(*keys)
                if result.get("success"):
                    return {"status": "success", "reply": f"✅ Hotkey ausgeführt: {'+'.join(keys)}"}
                else:
                    return {"status": "error", "reply": f"❌ Fehler: {result.get('error')}"}

            elif subcmd == "screenshot":
                result = gui.screen_capture()
                if result.get("success"):
                    path = result.get("path", "unbekannt")
                    size = result.get("size", {})
                    return {
                        "status": "success",
                        "reply": f"✅ Screenshot gespeichert: `{path}`\n📐 Größe: {size.get('width')}x{size.get('height')} px"
                    }
                else:
                    return {"status": "error", "reply": f"❌ Fehler: {result.get('error')}"}

            elif subcmd == "windows":
                result = gui.get_window_titles()
                if result.get("success"):
                    windows = result.get("windows", [])
                    if windows:
                        reply = f"🖥️ **{len(windows)} Fenster gefunden:**\n\n"
                        for w in windows[:20]:
                            reply += f"• {w.get('title')} ({w.get('width')}x{w.get('height')})\n"
                    else:
                        reply = "🖥️ Keine Fenster gefunden."
                    return {"status": "success", "reply": reply}
                else:
                    return {"status": "error", "reply": f"❌ Fehler: {result.get('error')}"}

            else:
                return {"status": "error", "reply": f"❌ Unbekannter GUI-Befehl: `{subcmd}`. Nutze `/gui` für Hilfe."}

        except Exception as e:
            logger.error(f"GUI-Befehl Fehler: {e}")
            return {"status": "error", "reply": f"❌ GUI-Fehler: {str(e)}"}
    

    # ===== NEUEN CHAT STARTEN =====
    if command in ["new", "reset"]:
        archive = command == "new"  # Bei /new archivieren, bei /reset nicht
        result = chat_memory.reset_chat(archive_current=archive)
        return {
            "status": "success",
            "reply": f"✅ Chat wurde zurückgesetzt{ ' und archiviert' if archive else ''}.\n\nDu kannst jetzt eine neue Unterhaltung beginnen!"
        }
    # ===== CHAT-ARCHIVE ANZEIGEN =====
    elif command in ["archives", "history", "verlauf"]:
        archives = chat_memory.list_chat_archives()
        if not archives:
            return {
                "status": "success",
                "reply": "📂 **Keine Chat-Archive vorhanden**\n\nSpeichere einen Chat mit `/new` oder warte auf Auto-Archivierung."
            }
        reply = "📚 **Verfügbare Chat-Archive:**\n\n"
        for i, arch in enumerate(archives[:10]):  # Nur die letzten 10
            date = datetime.fromisoformat(arch["date"]).strftime("%d.%m.%Y %H:%M")
            reply += f"**{i+1}.** `{arch['id']}`\n"
            reply += f"   📅 {date} | 💬 {arch['messages']} Nachrichten\n"
            if arch.get('preview'):
                reply += f"   📝 {arch['preview']}...\n"
            reply += "\n"
        reply += "\nLade ein Archiv mit: `/load <id>`"
        return {"status": "success", "reply": reply}

    # ===== AI ZUSAMMENFASSUNG =====

    elif command == "ai":
        """KI-Analyse von Daten"""
        if len(args) < 2:
            return {
                "status": "success",
                "reply": "❌ Beispiel: `/ai 'Fasse zusammen' < datei.txt`\n" +
                        "Oder: `/ai 'Analysiere' | aus vorherigem Befehl"
            }
        
        prompt = args[0]
        # Rest könnte eine Datei oder Pipe sein
        # Hier die Logik für AI-Analyse
        
    elif command == "pipeline-ai":
        """Komplette Pipeline mit KI"""
        if len(args) < 2:
            return {
                "status": "success",
                "reply": "❌ Beispiel: `/pipeline-ai 'Mars Mission' --filter NASA --analyze 'Fasse NASA-Missionen zusammen'`"
            }
        
        # Rufe das pipeline.py Skript auf
        import shlex
        pipeline_cmd = f'python tools/pipeline.py {" ".join(args)}'
        result = subprocess.run(
            pipeline_cmd,
            capture_output=True,
            text=True,
            shell=True,
            encoding='utf-8'
        )
        
        return {
            "status": "success",
            "reply": f"```\n{result.stdout}\n```"
        }

    # ===== ARCHIV LADEN =====
    elif command == "load":
        if not args:
            return {
                "status": "error",
                "reply": "❌ Bitte eine Archiv-ID angeben, z.B. `/load 20250215_143022`"
            }
        archive_id = args[0]
        archive = chat_memory.load_chat_archive(archive_id)
        if not archive:
            # Versuche ohne "chat_" Präfix
            if not archive_id.startswith('chat_'):
                archive = chat_memory.load_chat_archive(f"chat_{archive_id}")
            if not archive:
                return {
                    "status": "error",
                    "reply": f"❌ Archiv '{archive_id}' nicht gefunden.\n\nVerwende `/archives` um verfügbare Archive zu sehen."
                }
        # Aktuellen Chat archivieren und neuen starten
        chat_memory.reset_chat(archive_current=True)
        # Geladenes Archiv in den Verlauf laden
        chat_memory.conversation_history = archive.get("messages", [])
        chat_memory.user_interests = archive.get("user_interests", {})
        chat_memory.user_preferences = archive.get("preferences", chat_memory.user_preferences)
        date = datetime.fromisoformat(archive["end_time"]).strftime("%d.%m.%Y %H:%M")
        # Memory-Eintrag
        memory_entry = f"""
## 📂 Chat geladen vom {date}
**Archiv-ID:** {archive_id}
**Nachrichten:** {archive['message_count']}
---
"""
        with open(MEMORY_FILE, "a", encoding="utf-8") as f:
            f.write(memory_entry)
        chat_memory.memory_content += memory_entry
        # Vorschau der letzten Nachrichten
        preview = ""
        for msg in archive["messages"][-4:]:  # Letzte 2 Austausche
            role = "👤" if msg["role"] == "user" else "🤖"
            content = msg['content'][:80] + "..." if len(msg['content']) > 80 else msg['content']
            preview += f"{role} {content}\n"
        return {
            "status": "success",
            "reply": f"✅ **Archiv geladen:** {archive_id}\n\n"
                    f"📅 {date}\n"
                    f"💬 {archive['message_count']} Nachrichten\n\n"
                    f"**Letzte Nachrichten:**\n{preview}\n\n"
                    f"Du kannst jetzt weiterchatten!"
        }
    # ===== AUTO-EXPLORATION =====
    elif command == "explore":
        if len(args) > 0 and args[0] == "now":
            # Sofortige Exploration starten
            asyncio.create_task(chat_memory._explore_system())
            return {
                "status": "success",
                "reply": "🔍 GABI beginnt jetzt mit der System-Exploration...\n\nDie Ergebnisse werden im Memory gespeichert."
            }
        else:
            if chat_memory.is_exploring:
                return {
                    "status": "success",
                    "reply": "🔍 GABI erkundet gerade das System...\n\nSchau gleich im Memory nach den Ergebnissen!"
                }
            else:
                inactive = int((datetime.now() - chat_memory.last_activity).total_seconds() / 60)
                return {
                    "status": "success",
                    "reply": f"⏳ Letzte Aktivität: vor {inactive} Minuten\n\n"
                            f"Auto-Exploration startet nach 10 Minuten Inaktivität.\n"
                            f"Du kannst auch `/explore now` eingeben für eine sofortige Exploration."
                }
    elif command in ["sleep", "ruhe", "maintenance"]:
        summary = chat_memory.run_sleep_phase(reason="manual-command")
        return {
            "status": "success",
            "reply": (
                "🌙 Schlafphase abgeschlossen.\n"
                f"- Notizen: {summary.get('notes_before')} -> {summary.get('notes_after')}\n"
                f"- Memory kompaktiert: {'ja' if summary.get('memory_compacted') else 'nein'}\n"
                f"- Top Themen: {', '.join(summary.get('top_topics', [])) if summary.get('top_topics') else 'keine'}"
            ),
            "tool_used": "sleep-phase",
        }
        
    # ===== COMFY =====

    elif command == "comfy":
        subcmd = args[0].lower() if args else "status"
        
        # ===== BILD GENERIEREN =====
        if subcmd == "generate" or subcmd == "gen":
            if len(args) < 2:
                return {
                    "status": "error",
                    "reply": "❌ Bitte Prompt angeben: `/comfy generate <prompt>`\n"
                            "Beispiel: `/comfy generate a beautiful sunset over mountains`"
                }
            
            prompt = ' '.join(args[1:])
            
            # Parameter parsen (optional: --width, --height, --steps)
            width = 512
            height = 512
            steps = 20
            
            # Einfaches Parsing für Parameter (entfernt sie aus dem Prompt)
            import re
            width_match = re.search(r'--width\s+(\d+)', prompt)
            if width_match:
                width = int(width_match.group(1))
                prompt = re.sub(r'--width\s+\d+', '', prompt).strip()
            
            height_match = re.search(r'--height\s+(\d+)', prompt)
            if height_match:
                height = int(height_match.group(1))
                prompt = re.sub(r'--height\s+\d+', '', prompt).strip()
            
            steps_match = re.search(r'--steps\s+(\d+)', prompt)
            if steps_match:
                steps = int(steps_match.group(1))
                prompt = re.sub(r'--steps\s+\d+', '', prompt).strip()
            
            import httpx
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "http://localhost:8000/api/comfy/generate",
                        json={
                            "prompt": prompt,
                            "width": width,
                            "height": height,
                            "steps": steps
                        },
                        headers={"token": token}
                    )
                    result = response.json()
                    
                    if result.get("status") == "success":
                        return {
                            "status": "success",
                            "reply": result.get("reply", "✅ Bild generiert!"),
                            "image_path": result.get("image_path")
                        }
                    else:
                        return {
                            "status": "error",
                            "reply": result.get("reply", "❌ Fehler bei Bildgenerierung")
                        }
            except Exception as e:
                logger.error(f"Comfy generate error: {e}")
                return {
                    "status": "error",
                    "reply": f"❌ **Fehler bei Bildgenerierung:**\n\n{str(e)}\n\n"
                            f"**Tipp:** Stelle sicher, dass der API-Endpunkt existiert:\n"
                            f"`POST /api/comfy/generate`"
                }
        
        # ===== STATUS PRÜFEN =====
        elif subcmd == "status":
            # Prüfe ob ComfyUI wirklich läuft
            import requests
            comfy_running = False
            comfy_url = "http://127.0.0.1:8188"
            try:
                r = requests.get(f"{comfy_url}/system_stats", timeout=2)
                comfy_running = r.status_code == 200
            except:
                pass
            
            if comfy_running:
                return {
                    "status": "success",
                    "reply": f"✅ **ComfyUI läuft!**\n\n"
                            f"🌐 URL: {comfy_url}\n"
                            f"📁 Pfad: ComfyUI läuft auf Port 8188\n\n"
                            f"**Befehle:**\n"
                            f"• `/comfy generate <prompt>` - Bild generieren\n"
                            f"• `/comfy status` - Dieser Status\n"
                            f"• `/shell start http://localhost:8188` - Webinterface öffnen\n\n"
                            f"**Beispiel:**\n"
                            f"`/comfy generate futuristic city, cyberpunk, neon lights, 4k`"
                }
            else:
                return {
                    "status": "error",
                    "reply": f"⚠️ **ComfyUI läuft nicht**\n\n"
                            f"🌐 URL: {comfy_url} (nicht erreichbar)\n\n"
                            f"**So startest du ComfyUI:**\n"
                            f"1. Terminal öffnen\n"
                            f"2. `cd ComfyUI`\n"
                            f"3. `python main.py --listen`\n"
                            f"4. Dann `/comfy status` prüfen"
                }
        
        # ===== COMFYUI STARTEN =====
        elif subcmd == "start":
            return {
                "status": "info",
                "reply": "🔄 **ComfyUI manuell starten:**\n\n"
                        "1. Öffne ein Terminal\n"
                        "2. Wechsle in dein ComfyUI Verzeichnis:\n"
                        "   `cd C:\\ComfyUI` oder `cd ~/ComfyUI`\n"
                        "3. Starte ComfyUI mit:\n"
                        "   `python main.py --listen`\n"
                        "4. Warte bis \"Starting server\" erscheint\n"
                        "5. Prüfe mit `/comfy status`\n\n"
                        "**Oder mit GUI-Controller:**\n"
                        "`/shell cd ComfyUI && python main.py --listen`"
            }
        
        # ===== COMFYUI SCANNEN =====
        elif subcmd == "scan":
            discovery = _get_tool_discovery(force=True)
            comfy = discovery.get("comfyui", {})
            return {
                "status": "success",
                "reply": f"🔍 **ComfyUI Scan Ergebnis:**\n\n"
                        f"📁 Gefunden: {'✅ Ja' if comfy.get('found') else '❌ Nein'}\n"
                        f"📂 Pfad: {comfy.get('root', 'Nicht gefunden')}\n"
                        f"🏃 Läuft: {'✅ Ja' if comfy.get('running') else '❌ Nein'}\n"
                        f"🌐 URL: {comfy.get('url', 'http://127.0.0.1:8188')}\n\n"
                        f"**Tipp:** Wenn ComfyUI installiert aber nicht gefunden wurde,\n"
                        f"setze die Umgebungsvariable COMFYUI_HOME oder starte manuell."
            }
        
        else:
            return {
                "status": "error",
                "reply": "❌ Unbekannter /comfy Befehl.\n\n"
                        "**Verfügbare Befehle:**\n"
                        "• `/comfy status` - ComfyUI Status prüfen\n"
                        "• `/comfy start` - Anleitung zum Starten\n"
                        "• `/comfy generate <prompt>` - Bild generieren\n"
                        "• `/comfy scan` - ComfyUI suchen\n\n"
                        "**Beispiele:**\n"
                        "• `/comfy generate a cute cat`\n"
                        "• `/comfy generate cyberpunk city --width 1024 --height 768 --steps 30`"
            }
            
    # ===== GMAIL BEFEHLE (KORRIGIERT) =====
    elif command == "gmail":
        if not args:
            return {
                "status": "success",
                "reply": "📧 **Gmail Befehle:**\n\n" +
                        "`/gmail list` - Alle E-Mails anzeigen\n" +
                        "`/gmail get <id>` - Bestimmte E-Mail anzeigen\n" +
                        "`/gmail reply <id> <text>` - Auf eine E-Mail antworten\n" +
                        "`/gmail help` - Diese Hilfe"
            }
        subcmd = args[0].lower()
        if subcmd == "list":
            try:
                # Gmail-Client importieren
                from gateway.integrations.gmail_client import get_gmail_client
                # Client holen
                client = get_gmail_client()
                # E-Mails abrufen
                messages = client.list_messages(max_results=10)
                if not messages:
                    return {
                        "status": "success",
                        "reply": "📭 **Keine E-Mails gefunden**"
                    }
                reply = "📬 **Ihre letzten 10 E-Mails:**\n\n"
                for i, msg in enumerate(messages, 1):
                    reply += f"**{i}.** {msg.get('subject', 'kein Betreff')}\n"
                    reply += f"   📅 {msg.get('date', 'unbekannt')}\n"
                    reply += f"   👤 {msg.get('from', 'unbekannt')}\n"
                    reply += f"   🆔 `{msg.get('id', 'unbekannt')}`\n\n"
                return {"status": "success", "reply": reply}
            except ImportError as e:
                logger.error(f"Gmail Import Fehler: {e}")
                return {
                    "status": "error",
                    "reply": "❌ Gmail-Client nicht verfügbar.\n\n" +
                            "Stellen Sie sicher, dass die google-api-python-client Bibliothek installiert ist:\n" +
                            "```bash\npip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib\n```"
                }
            except Exception as e:
                logger.error(f"Gmail list Fehler: {e}")
                return {
                    "status": "error",
                    "reply": f"❌ Gmail Fehler: {str(e)}"
                }
        elif subcmd == "get" and len(args) > 1:
            try:
                msg_id = args[1]
                from gateway.integrations.gmail_client import get_gmail_client
                client = get_gmail_client()
                message = client.get_message(msg_id)
                body = client.get_message_body(message)
                headers = message.get("payload", {}).get("headers", [])
                header_map = {h.get("name", "").lower(): h.get("value", "") for h in headers}
                reply = f"📧 **E-Mail:** {header_map.get('subject', 'kein Betreff')}\n"
                reply += f"**Von:** {header_map.get('from', 'unbekannt')}\n"
                reply += f"**Datum:** {header_map.get('date', 'unbekannt')}\n\n"
                reply += f"**Inhalt:**\n{body[:1000]}"
                return {"status": "success", "reply": reply}
            except Exception as e:
                logger.error(f"Gmail get Fehler: {e}")
                return {
                    "status": "error",
                    "reply": f"❌ Fehler: {str(e)}"
                }
        elif subcmd == "reply" and len(args) > 2:
            try:
                msg_id = args[1]
                reply_text = " ".join(args[2:]).strip()
                if not reply_text:
                    return {"status": "error", "reply": "❌ Antworttext fehlt."}
                client = get_gmail_client()
                result = client.send_reply(msg_id, reply_text)
                if result.get("error"):
                    return {"status": "error", "reply": f"❌ Reply fehlgeschlagen: {result.get('error')}"}
                return {"status": "success", "reply": f"✅ Antwort gesendet (ID: `{result.get('id', 'unbekannt')}`)"}
            except Exception as e:
                logger.error(f"Gmail reply Fehler: {e}")
                return {"status": "error", "reply": f"❌ Fehler: {str(e)}"}
        elif subcmd == "help":
            return {
                "status": "success",
                "reply": "📧 **Gmail Hilfe:**\n\n" +
                        "`/gmail list` - Alle E-Mails anzeigen\n" +
                        "`/gmail get <id>` - Bestimmte E-Mail anzeigen\n" +
                        "`/gmail reply <id> <text>` - Auf E-Mail antworten"
            }
        else:
            return {
                "status": "error",
                "reply": "❌ Unbekannter Gmail-Befehl. Verwende `/gmail help` für Hilfe."
            }
            
    # ===== TELEGRAM BEFEHLE =====
    elif command == "telegram":
        if not args:
            return {
                "status": "success",
                "reply": "📱 **Telegram Befehle:**\n\n" +
                        "`/telegram status` - Bot-Status anzeigen\n" +
                        "`/telegram users` - Aktive Benutzer anzeigen\n" +
                        "`/telegram send <nachricht>` - Nachricht an alle senden\n" +
                        "`/telegram send --to <chat_id|@channel> <nachricht>` - Nachricht an Ziel senden\n" +
                        "`/telegram broadcast <nachricht>` - Gleiches wie send\n" +
                        "`/telegram help` - Diese Hilfe"
            }
        
        subcmd = args[0].lower()
        
        if subcmd == "status":
            bot = get_telegram_bot()
            status_text = f"""
📱 **Telegram Bot Status:**

**Bot Token:** {'✅ Konfiguriert' if bot.bot_token and bot.bot_token != 'YOUR_TELEGRAM_BOT_TOKEN' else '❌ Nicht konfiguriert'}
**Bot läuft:** {'✅ Ja' if bot.application else '❌ Nein'}
**Aktive Benutzer:** {len(bot._user_sessions) if hasattr(bot, '_user_sessions') else 0}
**Enabled in Config:** {'✅ Ja' if config.get('telegram.enabled', False) else '❌ Nein'}

**Hinweis:** 
- Entweder aktive Benutzer ODER konfigurierte Ziele (`chat_id`, `channel_id`, `chat_ids`)
- Der Bot antwortet auf Direktnachrichten mit Ollama
- Du kannst Nachrichten an alle aktiven Benutzer senden
"""
            return {"status": "success", "reply": status_text}


        elif subcmd == "goto":
            if len(args) < 2:
                return {
                    "status": "error",
                    "reply": "❌ Bitte URL angeben: `/gui goto <url>`\nBeispiel: `/gui goto google.com`\nAuch HTTPS/HTTP wird unterstützt."
                }
            
            url = args[1].strip()
            # Entferne mögliche Anführungszeichen
            url = url.strip('"\'')
            
            # Falls keine URL-Scheme vorhanden, füge https:// hinzu
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            # Optional: Browser aus args[2] (falls vorhanden)
            browser = args[2].lower() if len(args) > 2 else "chrome"
            
            logger.info(f"🌐 GUI Goto: {url} mit {browser}")
            
            try:
                # 1. Browser öffnen (falls nicht offen)
                open_result = await handle_command(f"/gui open {browser}", token)
                
                # Prüfe ob Browser erfolgreich gestartet wurde
                if isinstance(open_result, dict) and open_result.get("status") == "error":
                    return {
                        "status": "error",
                        "reply": f"❌ Browser '{browser}' konnte nicht gestartet werden: {open_result.get('reply', 'Unbekannter Fehler')}"
                    }
                
                # Kurze Pause für Browser-Start
                await asyncio.sleep(1.0)
                
                # 2. Fokussiere URL-Leiste (Ctrl+L ist universell)
                await handle_command("/gui hotkey ctrl l", token)
                await asyncio.sleep(0.3)
                
                # 3. URL eingeben
                await handle_command(f'/gui type "{url}"', token)
                await asyncio.sleep(0.2)
                
                # 4. Enter drücken
                await handle_command("/gui press enter", token)
                
                # Erfolgsmeldung
                return {
                    "status": "success",
                    "reply": f"✅ Navigiere zu {url} mit {browser}",
                    "url": url,
                    "browser": browser,
                    "tool_used": "gui-goto"
                }
                
            except Exception as e:
                logger.error(f"GUI Goto Fehler: {e}")
                return {
                    "status": "error",
                    "reply": f"❌ Fehler beim Navigieren zu {url}: {str(e)}"
                }
        
        elif subcmd == "users":
            bot = get_telegram_bot()
            if not bot._user_sessions:
                return {
                    "status": "success",
                    "reply": "📭 **Keine aktiven Telegram-Benutzer**\n\nBenutzer müssen dem Bot zuerst eine Nachricht schreiben, um in der Liste zu erscheinen."
                }
            
            reply = "👥 **Aktive Telegram-Benutzer:**\n\n"
            for i, (user_id, session) in enumerate(bot._user_sessions.items(), 1):
                msg_count = len(session) // 2
                reply += f"**{i}.** Benutzer ID: `{user_id}`\n"
                reply += f"   💬 {msg_count} Unterhaltungen\n"
                if session:
                    last_msg = session[-1].get('content', '')[:50]
                    reply += f"   📝 Letzte: {last_msg}...\n"
                reply += "\n"
            
            return {"status": "success", "reply": reply}
        
        elif subcmd in ["send", "broadcast"] and len(args) > 1:
            # Optional: /telegram send --to <target[,target2]> <nachricht>
            explicit_targets: List[Any] = []
            message_start_index = 1
            if len(args) > 3 and args[1] in ["--to", "-t"]:
                explicit_targets = _parse_explicit_telegram_targets(args[2])
                message_start_index = 3

            message = ' '.join(args[message_start_index:])
            if not message:
                return {
                    "status": "error",
                    "reply": "❌ Nachricht fehlt. Beispiel: `/telegram send --to @meinchannel Hallo`"
                }
            
            try:
                # Broadcast an alle aktiven Benutzer
                bot = get_telegram_bot()
                
                if not bot.application or not bot.application.bot:
                    return {
                        "status": "error",
                        "reply": "❌ Telegram Bot nicht initialisiert oder nicht konfiguriert."
                    }
                
                target_chat_ids = explicit_targets or _get_telegram_target_chat_ids(bot)
                if not target_chat_ids:
                    return {
                        "status": "error",
                        "reply": "❌ Keine Telegram-Ziele gefunden.\n\nSetze `telegram.chat_id`, `telegram.channel_id` oder `telegram.chat_ids` in der config.yaml."
                    }
                
                # Nachricht an alle senden
                sent = 0
                failed = 0
                errors = []
                
                for chat_id in target_chat_ids:
                    try:
                        await bot.application.bot.send_message(
                            chat_id=chat_id,
                            text=message,
                            parse_mode='Markdown'
                        )
                        sent += 1
                    except Exception as e:
                        failed += 1
                        errors.append(str(e))
                
                if sent > 0:
                    return {
                        "status": "success",
                        "reply": f"✅ Nachricht an {sent} Benutzer gesendet\n" +
                                (f"❌ Fehlgeschlagen: {failed}" if failed > 0 else "")
                    }
                else:
                    return {
                        "status": "error",
                        "reply": f"❌ Konnte an keinen Benutzer senden.\nFehler: {errors[0] if errors else 'Unbekannt'}"
                    }
                    
            except Exception as e:
                logger.error(f"Telegram send error: {e}")
                return {
                    "status": "error",
                    "reply": f"❌ Fehler beim Senden: {str(e)}"
                }
        
        elif subcmd == "help":
            return {
                "status": "success",
                "reply": """📱 **Telegram Bot Hilfe:**

**Was ist der Telegram Bot?**
Der Bot läuft als interaktiver Bot. Benutzer können ihm schreiben und er antwortet mit Ollama.

**Als Admin kannst du:**
• `/telegram status` - Bot-Status und Konfiguration prüfen
• `/telegram users` - Alle aktiven Benutzer anzeigen
• `/telegram send Hallo` - Nachricht an ALLE aktiven Benutzer senden
• `/telegram send --to 123456789 Hallo` - Direkt an eine Chat-ID senden
• `/telegram send --to @meinchannel Hallo` - Direkt an Kanal/Gruppe senden

**Wichtig:**
• Entweder aktive Benutzer ODER konfigurierte Ziele (`chat_id`, `channel_id`, `chat_ids`)
• Der Bot speichert den Verlauf pro Benutzer
• Nachrichten werden im Markdown-Format unterstützt

**Benutzer-Befehle (im Bot):**
• /start - Bot starten
• /help - Hilfe anzeigen
• /clear - Verlauf löschen
• /model - Aktuelles Modell
• /model liste - Modelle anzeigen
• /model <name> - Modell wechseln"""
            }
        
        else:
            return {
                "status": "error",
                "reply": "❌ Unbekannter Telegram-Befehl. Verwende `/telegram help` für Hilfe."
            }
            
    # ===== SHELL-BEFEHLE =====
    elif command in ["shell", "cmd", "bash", "powershell"]:
        if not args:
            return {
                "status": "success",
                "reply": "❌ Bitte einen Befehl angeben, z.B. `/shell dir | findstr py`"
            }
        
        try:
            full_command = ' '.join(args)
            logger.info(f"🖥️ GABI SHELL: {full_command}")
            
            # WICHTIG: UTF-8 für Windows richtig einstellen
            import subprocess
            import sys
            
            # Für Windows: CHCP 65001 = UTF-8 Codepage
            if sys.platform == "win32":
                # Setze Codepage auf UTF-8 für den Befehl
                full_command = f'chcp 65001 >nul && {full_command}'
            
            # Führe Befehl aus mit korrekter Encoding-Behandlung
            result = subprocess.run(
                full_command,
                capture_output=True,
                text=True,
                shell=True,
                timeout=30,
                encoding='utf-8',
                errors='replace'
            )
            
            # Besserer Check für erfolgreiche Ausführung
            if result.returncode == 0:
                output = result.stdout
                
                # PRÜFEN OB ES EINE Umlenkung (>) GIBT
                if '>' in full_command:
                    # Extrahiere den Dateinamen nach dem >
                    file_match = re.search(r'>\s*([^\s&|]+)', full_command)
                    if file_match:
                        filename = file_match.group(1).strip()
                        # Prüfe ob die Datei existiert und lies ihren Inhalt
                        if os.path.exists(filename):
                            try:
                                with open(filename, 'r', encoding='utf-8') as f:
                                    file_content = f.read()
                                return {
                                    "status": "success",
                                    "reply": f"✅ Befehl ausgeführt. Datei '{filename}' wurde erstellt.\n\n**Inhalt der Datei:**\n```\n{file_content}\n```",
                                    "command": full_command,
                                    "returncode": result.returncode
                                }
                            except Exception as e:
                                return {
                                    "status": "success",
                                    "reply": f"✅ Befehl ausgeführt. Datei '{filename}' wurde erstellt (kann nicht gelesen werden: {str(e)}).",
                                    "command": full_command
                                }
                
                # Normaler Fall: Ausgabe vorhanden
                if output:
                    # Bereinige Windows-Encoding-Fehler
                    replacements = {
                        'â€”': '—', 'â€“': '–', 'â‚¬': '€',
                        'Ã¤': 'ä', 'Ã¶': 'ö', 'Ã¼': 'ü',
                        'ÃŸ': 'ß', 'Ã„': 'Ä', 'Ã–': 'Ö',
                        'Ãœ': 'Ü', 'â€™': "'", 'â€œ': '"',
                        'â€': '"', 'Â': '',
                    }
                    for wrong, correct in replacements.items():
                        output = output.replace(wrong, correct)
                    
                    return {
                        "status": "success",
                        "reply": f"```\n{output}\n```",
                        "command": full_command,
                        "returncode": result.returncode
                    }
                else:
                    # KEINE Ausgabe, aber erfolgreich - Prüfe ob Dateien erstellt wurden
                    return {
                        "status": "success",
                        "reply": f"✅ Befehl erfolgreich ausgeführt (keine Konsolenausgabe).\n\nTipp: Verwende `type dateiname.txt` um den Inhalt erstellter Dateien anzuzeigen.",
                        "command": full_command
                    }
            else:
                return {
                    "status": "success",
                    "reply": f"❌ Fehler (Code {result.returncode}):\n```\n{result.stderr}\n```",
                    "command": full_command
                }
                
        except subprocess.TimeoutExpired:
            return {
                "status": "success",
                "reply": f"❌ Timeout nach 30 Sekunden: `{full_command}`"
            }
        except Exception as e:
            logger.error(f"Shell-Fehler: {e}")
            return {
                "status": "success",
                "reply": f"❌ Fehler: {str(e)}"
            }
            
    # Erweiterte Version mit temporären Dateien für komplexe Pipes
    elif command == "pipe":
        # Spezieller Befehl für komplexe Pipes mit Zwischenspeicherung
        import tempfile
        
        if len(args) < 3 or ">" not in full_command:
            return {"status": "success", "reply": "❌ Beispiel: `/pipe dir > temp.txt && type temp.txt | findstr py`"}
        
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.tmp', delete=False) as tmp:
            tmp_name = tmp.name
        
        try:
            # Ersetze temporäre Datei im Befehl
            cmd_with_temp = full_command.replace('temp.txt', tmp_name)
            
            result = subprocess.run(
                cmd_with_temp,
                capture_output=True,
                text=True,
                shell=True,
                timeout=30,
                encoding='utf-8',
                errors='replace'
            )
            
            # Aufräumen
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)
            
            return {
                "status": "success",
                "reply": f"```\n{result.stdout}\n```"
            }
        except Exception as e:
            return {"status": "success", "reply": f"❌ Fehler: {e}"}            
            
           
    # ===== EXPLIZIT MERKEN =====
    elif command in ["merken", "remember", "note"]:
        from datetime import datetime
        note_text = " ".join(args).strip()
        if not note_text:
            return {
                "status": "success",
                "reply": "🧠 Nutzung: `/merken <inhalt>`\nBeispiel: `/merken adresse https://www.jazzland.at`"
            }
        entry, created = chat_memory.remember_note(note_text, source="command")
        if not entry:
            return {"status": "error", "reply": "❌ Konnte den Inhalt nicht merken."}
        action = "Gemerkt" if created else "Schon gemerkt"
        ts = datetime.fromisoformat(entry["timestamp"]).strftime("%d.%m.%Y %H:%M:%S")
        return {
            "status": "success",
            "reply": f"✅ {action}: {entry['text']}\n🕒 {ts}\nAbrufen mit `/gemerkt`.",
            "timestamp": datetime.now().isoformat(),
            "tool_used": "Memory · /merken"
        }

    elif command in ["gemerkt", "merkliste", "notes"]:
        limit = 20
        if args and args[0].isdigit():
            limit = max(1, min(int(args[0]), 100))
        notes = chat_memory.get_remembered_notes(limit=limit)
        if not notes:
            return {
                "status": "success",
                "reply": "📭 Noch nichts explizit gemerkt. Nutze `/merken <inhalt>`."
            }
        lines = ["🧠 **Gemerkte Einträge:**", ""]
        for idx, note in enumerate(notes, 1):
            note_ts = note.get("timestamp", "")
            try:
                note_time = datetime.fromisoformat(note_ts).strftime("%d.%m.%Y %H:%M")
            except Exception:
                note_time = note_ts or "unbekannt"
            lines.append(f"**{idx}.** {note.get('text', '').strip()}")
            lines.append(f"   🕒 {note_time}")
        return {
            "status": "success",
            "reply": "\n".join(lines),
            "timestamp": datetime.now().isoformat()
        }

    # ===== MEMORY ANZEIGEN =====
    elif command == "memory":
        memory = chat_memory.memory_content[-1500:] if len(chat_memory.memory_content) > 1500 else chat_memory.memory_content
        return {
            "status": "success", 
            "reply": f"📚 **Letzte Erinnerungen:**\n```\n{memory}\n```"
        }
    # ===== SOUL ANZEIGEN =====
    elif command == "soul":
        try:
            with open('SOUL.md', 'r', encoding='utf-8') as f:
                soul = f.read()[-1500:]
            return {
                "status": "success", 
                "reply": f"🧠 **Meine Persönlichkeit:**\n```\n{soul}\n```"
            }
        except:
            return {
                "status": "error", 
                "reply": "❌ SOUL.md noch nicht generiert. Benutze `/generate-soul` um sie zu erstellen."
            }
    # ===== SOUL GENERIEREN =====
    elif command == "generate-soul":
        try:
            # Hier den generate_soul Endpoint aufrufen
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8000/api/memory/generate-soul",
                    headers={"Authorization": f"Bearer {token}"}
                )
                data = response.json()
            return {
                "status": "success",
                "reply": f"🧬 **Soul generiert!**\n\n{data.get('message', '')}"
            }
        except Exception as e:
            return {
                "status": "error",
                "reply": f"❌ Fehler bei Soul-Generierung: {str(e)}"
            }

    # ===== MODEL =====
    elif command == "model":
        try:
            if not args:
                current = ollama_client.default_model
                return {
                    "status": "success",
                    "reply": f"🤖 Aktuelles Modell: `{current}`",
                    "current_model": current,
                    "model_used": current,
                    "timestamp": datetime.now().isoformat(),
                }

            sub = args[0].lower()
            if sub in ["liste", "list", "ls"]:
                models_info = ollama_client.list_models()
                models = [m.get("name") for m in models_info.get("models", [])]
                current = ollama_client.default_model
                lines = [f"{'✅' if m == current else '•'} `{m}`" for m in models]
                return {
                    "status": "success",
                    "reply": "📚 **Verfügbare Modelle:**\n\n" + "\n".join(lines),
                    "current_model": current,
                    "timestamp": datetime.now().isoformat(),
                }

            target_model = " ".join(args).strip()
            models_info = ollama_client.list_models()
            available = [m.get("name") for m in models_info.get("models", [])]
            if target_model not in available:
                return {"status": "error", "reply": f"❌ Modell `{target_model}` nicht gefunden. Nutze `/model liste`."}

            config.set("ollama.default_model", target_model)
            ollama_client.default_model = target_model
            global DEFAULT_MODEL
            DEFAULT_MODEL = target_model
            return {
                "status": "success",
                "reply": f"✅ Modell gewechselt zu `{target_model}`",
                "current_model": target_model,
                "model_used": target_model,
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            return {"status": "error", "reply": f"❌ Model-Fehler: {e}"}

    # ===== CALENDAR =====
    elif command == "calendar":
        try:
            max_results = 10
            if args and args[0].isdigit():
                max_results = max(1, min(int(args[0]), 25))

            cal = get_calendar_client()
            events = cal.list_upcoming_events(max_results=max_results)
            if not events:
                return {"status": "success", "reply": "📅 Keine bevorstehenden Kalendertermine gefunden."}

            lines = ["📅 **Nächste Kalendertermine:**", ""]
            for event in events:
                start = event.get("start", "unbekannt")
                summary = event.get("summary", "(Ohne Titel)")
                location = event.get("location", "")
                lines.append(f"• `{start}` - **{summary}**" + (f" | 📍 {location}" if location else ""))
            return {"status": "success", "reply": "\n".join(lines)}
        except Exception as e:
            return {"status": "error", "reply": f"❌ Calendar-Fehler: {e}"}

    # ===== STATUS ANZEIGEN =====
    elif command == "status":
        status = chat_memory.heartbeat_content
        return {
            "status": "success",
            "reply": f"📊 **System-Status:**\n```\n{status}\n```"
        }

    # ===== WEBCAM =====
    elif command == "webcam":
        try:
            vision = get_gabi_vision()
            if not vision:
                return {"status": "error", "reply": "❌ Vision-Modul nicht verfügbar"}

            if not args or args[0] in ["capture", "photo"]:
                # Webcam-Foto aufnehmen
                result = vision.capture_webcam()
                if result.get("success"):
                    b64 = result.get("base64", "")
                    return {
                        "status": "success",
                        "reply": f"📷 Webcam-Foto aufgenommen!\nPfad: `{result['path']}`\n\n[Bild anzeigen]({result['path']})",
                        "image_path": result["path"],
                        "base64": b64
                    }
                else:
                    return {"status": "error", "reply": f"❌ Webcam-Fehler: {result.get('error', 'Unbekannt')}"}

            elif args[0] == "status":
                # Status anzeigen
                status = vision.get_motion_status()
                is_active = vision._webcam_active if hasattr(vision, '_webcam_active') else False
                last_objects = vision._last_yolo_objects if hasattr(vision, '_last_yolo_objects') else []

                msg = "🔍 **Webcam-Status:**\n\n"
                msg += f"• Stream aktiv: {'✅ Ja' if is_active else '❌ Nein'}\n"

                if last_objects:
                    obj_list = ", ".join([f"{o['class']}" for o in last_objects[:5]])
                    msg += f"• Letzte Erkennung: {obj_list}\n"
                else:
                    msg += "• Letzte Erkennung: Keine\n"

                msg += "\n**Befehle:**\n"
                msg += "• `/webcam` - Foto aufnehmen\n"
                msg += "• `/webcam detect` - Einmal erkennen\n"
                msg += "• `/webcam detect stream` - Stream starten\n"
                msg += "• `/webcam detect stop` - Stream stoppen\n"

                return {"status": "success", "reply": msg}

            elif args[0] == "detect":
                # Prüfe auf stream-modus
                if len(args) > 1 and args[1] in ["stream", "watch", "kontinuierlich", "continuous"]:
                    # Kontinuierliche YOLO-Erkennung starten
                    result = vision.start_yolo_stream(interval=2.0)
                    if result.get("success"):
                        return {"status": "success", "reply": "🔍 **YOLO-Stream gestartet!**\n\nKontinuierliche Objekterkennung läuft im Hintergrund.\nErkennungen werden im Log ausgegeben.\n\nStoppen mit: `/webcam detect stop`"}
                    else:
                        return {"status": "error", "reply": f"❌ Fehler: {result.get('error')}"}

                elif len(args) > 1 and args[1] in ["stop", "stopp"]:
                    # Stoppe Stream
                    vision.stop_yolo_stream()
                    return {"status": "success", "reply": "⏹️ YOLO-Stream gestoppt."}

                # Einzelne Erkennung
                result = vision.capture_webcam()
                if not result.get("success"):
                    return {"status": "error", "reply": f"❌ Webcam-Fehler: {result.get('error')}"}

                detect_result = vision.detect_objects(result["path"])
                if detect_result.get("success"):
                    objects = detect_result.get("objects", [])
                    if objects:
                        obj_list = ", ".join([f"{o['class']} ({o['confidence']:.0%})" for o in objects[:10]])
                        return {"status": "success", "reply": f"🔍 **Erkannte Objekte:**\n{obj_list}"}
                    return {"status": "success", "reply": "🔍 Keine Objekte erkannt."}
                else:
                    return {"status": "error", "reply": f"❌ YOLO-Fehler: {detect_result.get('error')}"}

            elif args[0] in ["stream", "watch", "kontinuierlich", "continuous"]:
                # Legacy: Kontinuierliche Erkennung (alternative zum detect stream)
                result = vision.start_yolo_stream(interval=2.0)
                if result.get("success"):
                    return {"status": "success", "reply": "🔍 **YOLO-Stream gestartet!**\n\nStoppen mit: `/webcam detect stop`"}
                    return {
                        "status": "error",
                        "reply": f"❌ Fehler: {result.get('error')}"
                    }

            elif args[0] in ["stop", "stopp"]:
                vision.stop_yolo_stream()
                vision.stop_motion_detection()
                return {"status": "success", "reply": "⏹️ Alle Streams gestoppt."}

            else:
                return {"status": "error", "reply": "❌ Nutze `/webcam`, `/webcam capture`, `/webcam detect`, `/webcam stream` oder `/webcam stop`"}

        except Exception as e:
            return {"status": "error", "reply": f"❌ Webcam-Fehler: {e}"}

    # ===== VISION (BILD ANALYSIEREN) =====
    elif command == "vision":
        try:
            vision = get_gabi_vision()
            if not vision:
                return {"status": "error", "reply": "❌ Vision-Modul nicht verfügbar"}

            # Wenn kein Pfad angegeben, nimm Webcam-Foto
            if not args:
                # Webcam-Foto aufnehmen
                webcam_result = vision.capture_webcam()
                if not webcam_result.get("success"):
                    return {"status": "error", "reply": f"❌ Webcam-Fehler: {webcam_result.get('error', 'Unbekannt')}"}
                
                image_path = webcam_result.get("path")
                prompt = "Beschreibe was du auf diesem Bild siehst."
                
            else:
                # Pfad aus Argumenten zusammensetzen
                image_path = " ".join(args)

                # Handle @ prefix falls vorhanden
                if image_path.startswith("@"):
                    image_path = image_path[1:]

                # Relativen Pfad in absoluten umwandeln
                if not os.path.isabs(image_path):
                    base_dir = Path(__file__).parent.parent
                    image_path = str(base_dir / image_path)

                if not os.path.exists(image_path):
                    return {"status": "error", "reply": f"❌ Datei nicht gefunden: {image_path}"}
                
                prompt = "Beschreibe was du auf diesem Bild siehst."

            # Optional: Prompt aus Argumenten
            if len(args) > 1 and args[0].lower() in ["-p", "--prompt"]:
                prompt = " ".join(args[1:])

            # Bild mit Vision-Modell analysieren (direkt, nicht über vision.analyze_screenshot_with_ai)
            import base64
            with open(image_path, "rb") as f:
                img_base64 = base64.b64encode(f.read()).decode("utf-8")
            
            # Wähle das richtige Vision-Modell
            models_info = ollama_client.list_models()
            available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
            
            # Bevorzugte Vision-Modelle aus Config
            preferred_vision = _as_model_pref_list(config.get("ollama.preferred_vision_models")) or ["qwen3-vl:8b"]
            vision_model = _pick_preferred_available(available, preferred_vision)
            
            if not vision_model:
                # Fallback: Suche nach Vision-Modellen
                vision_hints = ["vl", "vision", "llava", "moondream", "minicpm-v", "qwen2.5vl"]
                vision_model = _pick_best_model(available, hints=vision_hints)
            
            if not vision_model:
                return {"status": "error", "reply": "❌ Kein Vision-Modell verfügbar. Installiere z.B. qwen3-vl:8b mit: ollama pull qwen3-vl:8b"}
            
            logger.info(f"🔍 Verwende Vision-Modell: {vision_model}")
            
            # Ollama Chat mit Bild
            response = await _ollama_chat_async(
                model=vision_model,
                messages=[
                    {"role": "user", "content": prompt, "images": [img_base64]}
                ]
            )
            
            analysis = _extract_ollama_text(response) or "Keine Analyse erhalten"
            
            return {
                "status": "success",
                "reply": f"🔍 **Bildanalyse:**\n{analysis}",
                "image_path": image_path,
                "model_used": vision_model
            }

        except Exception as e:
            logger.error(f"Vision-Fehler: {e}")
            return {"status": "error", "reply": f"❌ Vision-Fehler: {e}"}

    # ===== WHISPER =====
    elif command == "whisper":
        import subprocess
        import requests

        try:
            if not args:
                return {"status": "error", "reply": "❌ Nutze `/whisper status` oder `/whisper listen`"}

            sub = args[0].lower()

            if sub == "status":
                # Whisper-Server prüfen
                try:
                    r = requests.get("http://127.0.0.1:9090/health", timeout=2)
                    if r.status_code == 200:
                        return {"status": "success", "reply": "🎤 Whisper-Server: ✅ Läuft auf Port 9090"}
                    return {"status": "error", "reply": "❌ Whisper-Server antwortet nicht korrekt"}
                except:
                    return {"status": "error", "reply": "❌ Whisper-Server nicht erreichbar auf Port 9090\n\nStarte mit:\n`server.exe -m M:\\whisper\\whisper.cpp\\models\\ggml-large-v3.bin --port 9090 --host 127.0.0.1 -l de`"}

            elif sub == "listen":
                # Audio aufnehmen - nutze Frontend MediaRecorder
                return {
                    "status": "success",
                    "reply": """🎤 **Audio aufnehmen:**

Klicke auf den **Whisper-Button** im Web-Interface (unten links im Chat)!

Das nutzt den Browser-Mechanismus für Audio-Aufnahme:
1. Klick auf 🎤 Whisper Button
2. Klick nochmal zum Stoppen
3. Audio wird automatisch an Whisper gesendet

**Oder:** Nimm extern auf und lade die Datei im Chat hoch."""
                }

            else:
                return {"status": "error", "reply": "❌ Nutze `/whisper status` oder `/whisper listen`"}

        except Exception as e:
            return {"status": "error", "reply": f"❌ Whisper-Fehler: {e}"}

    # ===== LERNSTATUS ANZEIGEN =====
    elif command == "learn":
        stats = f"""
**Was ich über dich gelernt habe:**
📝 **Kommunikationsstil:** {chat_memory.user_preferences.get('message_length', 'mittel')}e Antworten
🕐 **Aktive Zeit:** {chat_memory.user_preferences.get('active_time', 'unbekannt')}
👍 **Positives Feedback:** {chat_memory.user_preferences.get('positive_feedback', 0)}x
👎 **Negatives Feedback:** {chat_memory.user_preferences.get('negative_feedback', 0)}x
🎯 **Häufige Themen:** {', '.join([f'{t}({c})' for t,c in list(chat_memory.user_interests.items())[:5]])}
💡 **Persönliche Infos:** {len(chat_memory.important_info)} gespeichert
"""
        return {"status": "success", "reply": stats}

    # ===== HILFE =====
    elif command == "help":
        help_text = """
    **🔧 VERFÜGBARE BEFEHLE:**

    **📁 CHAT-MANAGEMENT:**
    `/new` - Neuen Chat starten (aktuellen archivieren)
    `/reset` - Chat zurücksetzen (ohne Archivierung)
    `/archives` oder `/history` - Alle Chat-Archive anzeigen
    `/load <id>` - Bestimmtes Archiv laden

    **🔍 AUTO-EXPLORATION:**
    `/explore` - Status der Auto-Exploration anzeigen
    `/explore now` - Sofortige System-Exploration starten
    `/sleep` - Schlafphase: Memory sortieren/kompaktieren

    **📧 GMAIL:**
    `/gmail list` - Alle E-Mails anzeigen
    `/gmail get <id>` - Bestimmte E-Mail anzeigen
    `/gmail reply <id> <text>` - Auf E-Mail antworten
    `/gmail help` - Gmail-Hilfe

    **📅 CALENDAR:**
    `/calendar` - Nächste Termine anzeigen
    `/calendar 20` - Mehr Termine (max. 25)

    **📱 TELEGRAM:**
    `/telegram status` - Bot-Status und Konfiguration prüfen
    `/telegram users` - Alle aktiven Benutzer anzeigen
    `/telegram send <nachricht>` - Nachricht an ALLE aktiven Benutzer senden
    `/telegram send --to <chat_id|@channel> <nachricht>` - Direktes Ziel
    `/telegram broadcast <nachricht>` - Gleiches wie send
    `/telegram help` - Telegram-Hilfe

    **🤖 MODEL:**
    `/model` - Aktuelles Modell
    `/model liste` - Modelle anzeigen
    `/model <name>` - Modell wechseln

    **💻 SHELL:**
    `/shell <befehl>` - Shell-Befehl ausführen
    `/shell analyze <befehl>` - Befehl ausführen und Ergebnis analysieren

    **🧠 MEMORY & SOUL:**
    `/memory` - Letzte Erinnerungen anzeigen
    `/merken <inhalt>` - Etwas dauerhaft speichern
    `/gemerkt` - Gemerkte Einträge abrufen
    `/soul` - Persönlichkeit anzeigen
    `/generate-soul` - Soul generieren/aktualisieren
    `/learn` - Zeige was ich über dich gelernt habe

    **📷 WEBCAM & VISION:**
    `/webcam` - Webcam-Foto aufnehmen
    `/webcam detect` - Einmalige Objekterkennung
    `/webcam detect stream` - Kontinuierliche YOLO-Erkennung
    `/webcam detect stop` - Stream stoppen
    `/vision <pfad>` - Bild analysieren

    **🎤 WHISPER (Spracherkennung):**
    `/whisper status` - Whisper-Server Status
    `/whisper listen` - Audio aufnehmen und transkribieren

    **📷 WEBCAM & VISION:**
    `/webcam` - Webcam-Foto aufnehmen
    `/webcam detect` - Einmalige Objekterkennung
    `/webcam detect stream` - Kontinuierliche YOLO-Erkennung
    `/webcam detect stop` - Stream stoppen
    `/vision <pfad>` - Bild analysieren

    **🎤 WHISPER (Spracherkennung):**
    `/whisper status` - Whisper-Server Status
    `/whisper listen` - Audio aufnehmen und transkribieren

    **📊 SYSTEM:**
    `/status` - System-Status anzeigen
    `/help` - Diese Hilfe

    **👾 COMFY: ***
    `/comfy status` - ComfyUI/Invoke Discovery anzeigen
    `/comfy scan` - Discovery neu scannen
    `/comfy start` - ComfyUI automatisch starten (wenn gefunden)
    --------------------------------------------------------------
    `/comfy generate a cute cat sitting on a cloud, digital art` - Einfaches Bild erstellen
    `/comfy generate beautiful landscape, mountains, sunset --width 1024 --height 768` - Mit Größenangabe
    `/comfy generate detailed portrait of a wizard --steps 30` - Mit Schritten
    `/comfy generate futuristic city, cyberpunk, neon lights, 4k --width 1024 --height 576 --steps 25` - Kombiniert
      Beispiele:
    `/comfy generate a cute fluffy cat with blue eyes, photorealistic, detailed fur` - Kätzchen
    `/comfy generate majestic mountain lake at sunset, reflections, 4k, highly detailed` - Landschaft
    `/comfy generate cyberpunk city, rain, neon lights, holograms, blade runner style` - Cyberpunk
    `/comfy generate beautiful woman portrait, fantasy art, intricate details, masterpiece` - Porträt
    `/comfy generate anime girl, cherry blossoms, school uniform, detailed background` - Anime
    `/comfy generate surreal dreamscape, floating islands, waterfalls, fantasy art` - Surreal
    `/comfy generate nebula, stars, galaxy, colorful, deep space, 4k` - Space



    **🕹️ GUI: ***
    `/gui open <programm>` - Programme öffnen - /gui open chrome
    `/gui click <x> <y>` - Mausklicks - /gui click 500 300
    `/gui type <text>` - Texteingabe - /gui type "Hallo"
    `/gui press <taste>` - Tastendruck - /gui press enter
    `/gui screenshot` - Screenshots - /gui screenshot
    `/gui windows` - Fensterliste - /gui windows

    **✨ AUTO-EXPLORATION:**
    Nach 10 Minuten Inaktivität erkundet GABI selbstständig das System.

    **🔥 PIPE & REDIRECTION BEISPIELE:**

    `👉 /shell (echo Zeile 1 & echo Zeile 2 & echo Zeile 3) > datei.txt && type datei.txt`
    → Mehrzeilige Datei erstellen und anzeigen

    `👉 /shell echo 1,2,3 > fib.txt && type fib.txt`
    → Komma-separierte Werte in Datei speichern

    `👉 /shell powershell "$a=0;$b=1;1..10 | foreach {$a;$c=$a+$b;$a=$b;$b=$c}" > fibonacci.txt && type fibonacci.txt`
    → Fibonacci-Zahlen (0,1,1,2,3,5,8,13,21,34) in Datei speichern

    `👉 /shell dir | findstr ".py" | sort`
    → Python-Dateien auflisten und sortieren (Pipe)

    `👉 /shell ipconfig | findstr "IPv4"`
    → Nur IPv4-Adressen aus ipconfig anzeigen

    `👉 /shell tasklist | findstr "python" | wc -l`
    → Anzahl laufender Python-Prozesse zählen

    **💡 TIPPS:**
    • Mit `>` schreibst du Ausgaben in Dateien
    • Mit `|` verarbeitest du Ausgaben weiter (Pipes)
    • Mit `&&` kannst du Befehle verketten
    • Nach Dateierstellung mit `type` den Inhalt anzeigen
    """
        return {"status": "success", "reply": help_text}

    # Füge diesen Code in handle_command Funktion ein, nach den anderen Befehlen
    elif command == "goto":
        if not args:
            return {
                "status": "error",
                "reply": "❌ Bitte URL angeben: `/goto <url>`\nBeispiel: `/goto google.com`\nAuch HTTPS/HTTP wird unterstützt."
            }
        
        url = ' '.join(args).strip()
        url = url.strip('"\'')
        
        # Falls keine URL-Scheme vorhanden, füge https:// hinzu
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Optional: Browser aus Config oder Parameter
        browser = "chrome"
        if len(args) > 1 and args[0].lower() in ["chrome", "firefox", "edge", "opera"]:
            browser = args[0].lower()
            url = ' '.join(args[1:]).strip()
        
        try:
            # 1. Browser öffnen
            open_result = await handle_command(f"/gui open {browser}", token)
            
            if isinstance(open_result, dict) and open_result.get("status") == "error":
                return {
                    "status": "error",
                    "reply": f"❌ Browser '{browser}' konnte nicht gestartet werden: {open_result.get('reply', 'Unbekannter Fehler')}"
                }
            
            await asyncio.sleep(1.0)
            
            # 2. URL-Leiste fokussieren
            await handle_command("/gui hotkey ctrl l", token)
            await asyncio.sleep(0.3)
            
            # 3. URL eingeben
            await handle_command(f'/gui type "{url}"', token)
            await asyncio.sleep(0.2)
            
            # 4. Enter drücken
            await handle_command("/gui press enter", token)
            
            return {
                "status": "success",
                "reply": f"✅ Navigiere zu {url} mit {browser}",
                "url": url,
                "browser": browser
            }
            
        except Exception as e:
            logger.error(f"Goto Fehler: {e}")
            return {
                "status": "error",
                "reply": f"❌ Fehler: {str(e)}"
            }

    # In der GUI-Erkennung, z.B. wenn GABI ein Icon erkennen soll
    elif command == "gui" and subcmd == "find-and-click":
        # GABI sucht ein Icon auf dem Bildschirm und klickt es
        template = args[1] if len(args) > 1 else None
        if template:
            result = gui.click_icon(template)
            return result
        
    # Erweiterte Vision-Funktion
    elif command == "vision-detect":
        # Erkenne Objekte auf dem Bildschirm
        screenshot = gui.screen_capture()
        result = await _analyze_with_vision(
            screenshot["base64"],
            "Erkenne und beschreibe alle sichtbaren Fenster und Icons auf dem Desktop"
        )
        return {"reply": result}

    # Nach der Web-Analyse, automatisch auf Buttons klicken
    elif command == "web-auto":
        # Analysiere Webseite und führe Aktionen aus
        result = await web.goto(url)
        vision_analysis = await _analyze_with_vision(
            result["screenshot"]["base64"],
            "Finde den Login-Button und beschreibe seine Position"
        )
        # Extrahiere Koordinaten und klicke

    # Kamera-Bilder analysieren
    elif command == "camera-watch":
        # Analysiere regelmäßig Webcam-Bilder
        result = vision.capture_webcam()
        analysis = await _analyze_with_vision(
            result["base64"],
            "Erkenne ob eine Person im Raum ist und beschreibe ihre Position"
        )
        if "Person" in analysis:
            # Führe Aktion aus
            pass

    # Unterbefehle für gui
    elif subcmd == "find":
        # Suche nach Text oder Icon auf dem Bildschirm
        search_text = " ".join(args[1:])
        screenshot = gui.screen_capture()
        result = await _analyze_with_vision(
            screenshot["base64"],
            f"Finde '{search_text}' auf dem Bildschirm. Gib die Koordinaten (x,y) zurück."
        )
        # Extrahiere Koordinaten aus der Antwort
        return {"reply": f"Gefunden: {result}"}

    # Dokument mit Webcam scannen
    elif command == "scan-doc":
        result = vision.capture_webcam()
        analysis = await _analyze_with_vision(
            result["base64"],
            "Extrahiere den Text aus dem Dokument. Gib nur den erkannten Text zurück."
        )
        # Speichere den Text
        with open("scanned_text.txt", "w", encoding="utf-8") as f:
            f.write(analysis)
        return {"reply": f"📄 Text extrahiert:\n{analysis}"}

    # gui find-and-click
    elif subcmd == "find-and-click":
        if len(args) < 2:
            return {"status": "error", "reply": "❌ Bitte Suchtext angeben"}
        
        search_text = " ".join(args[1:])
        
        # Screenshot machen
        screenshot = gui.screen_capture()
        
        # Mit Vision nach dem Element suchen
        analysis = await _analyze_with_vision(
            screenshot["base64"],
            f"Finde '{search_text}' auf dem Bildschirm. Gib die Koordinaten (x,y) zurück. Wenn nicht gefunden, gib 'nicht gefunden'."
        )
        
        # Koordinaten aus der Antwort extrahieren (einfaches Beispiel)
        import re
        coords = re.findall(r'(\d+)\s*,\s*(\d+)', analysis)
        if coords:
            x, y = int(coords[0][0]), int(coords[0][1])
            gui.safe_click(x, y)
            return {"status": "success", "reply": f"✅ Geklickt bei ({x}, {y})"}
        else:
            return {"status": "error", "reply": f"❌ '{search_text}' nicht gefunden"}

    # Autonome Web-Navigation
    elif command == "auto":
        """Autonome Web-Navigation mit Vision"""
        if not args:
            return {
                "status": "error",
                "reply": "❌ Bitte eine URL angeben: `/auto <url>`\nBeispiel: `/auto http://ventosus`\n\nOptional mit Ziel: `/auto http://ventosus Login durchführen`"
            }
        
        url = args[0]
        goal = " ".join(args[1:]) if len(args) > 1 else "Erkunde die Seite und finde heraus, was hier gemacht werden kann"
        
        try:
            from gateway.integrations.web_vision_agent import get_web_vision_agent
            
            agent = get_web_vision_agent(headless=False)
            
            # Starte die autonome Navigation
            result = await agent.analyze_and_navigate(url, goal, max_steps=10)
            
            if result.get("success"):
                steps_text = ""
                for i, step in enumerate(result.get('action_history', []), 1):
                    action = step.get('action', '?')
                    target = step.get('target', step.get('text', ''))
                    steps_text += f"\n  {i}. {action}: {target[:50]}"
                
                reply = f"✅ **Autonome Navigation erfolgreich!**\n\n"
                reply += f"**Ziel:** {url}\n"
                reply += f"**Schritte:** {result.get('steps_taken', 0)}\n\n"
                reply += f"**Ausgeführte Aktionen:**{steps_text if steps_text else ' Keine'}\n\n"
                reply += f"**Gedankengang:**\n"
                for step in result.get('thinking_steps', [])[:8]:
                    reply += f"\n• {step.get('text', '')}"
                
                return {
                    "status": "success",
                    "reply": reply,
                    "data": result
                }
            else:
                return {
                    "status": "error",
                    "reply": f"❌ **Navigation fehlgeschlagen**\n\nFehler: {result.get('error', 'Unbekannt')}"
                }
                
        except ImportError as e:
            logger.error(f"Web Vision Agent Import Fehler: {e}")
            return {
                "status": "error",
                "reply": "❌ Web Vision Agent nicht verfügbar.\n\n"
                        "Stelle sicher, dass integrations/web_vision_agent.py existiert.\n\n"
                        "Tipp: Führe zuerst die Installation durch:\n"
                        "```bash\npip install selenium webdriver-manager\nollama pull qwen3-vl:8b\n```"
            }
        except Exception as e:
            logger.error(f"Auto Befehl Fehler: {e}")
            return {
                "status": "error",
                "reply": f"❌ Fehler: {str(e)}"
            }


    # ===== SoM AGENT BEFEHLE =====
    elif command == "som":
        """SoM Agent Befehle für Web-Automation"""
        
        if not args:
            return {
                "status": "success",
                "reply": "🤖 **SoM Agent Befehle:**\n\n"
                        "`/som navigate <url> <ziel>` - Autonome Navigation\n"
                        "`/som search <suchbegriff>` - Suche mit Startpage\n"
                        "`/som learned` - Gelernte Inhalte anzeigen\n"
                        "`/som stats` - Statistiken anzeigen\n"
                        "`/som memory` - Volles Memory anzeigen\n"
                        "`/som clear` - Memory löschen\n\n"
                        "**Beispiele:**\n"
                        "`/som navigate https://startpage.com 'Suche nach Python'`\n"
                        "`/som search Python Tutorial`"
            }
        
        subcmd = args[0].lower()
        
        if subcmd == "navigate" and len(args) >= 2:
            url = args[1]
            goal = " ".join(args[2:]) if len(args) > 2 else "Erkunde die Seite"
            
            from gateway.integrations.som_agent import get_som_agent
            
            agent = get_som_agent(headless=True)
            result = await agent.navigate(url=url, goal=goal, max_steps=5)
            
            if result.get("success"):
                extracted = result.get("extracted_content", {})
                results_count = len(extracted.get("search_results", []))
                
                reply = f"✅ **SoM Navigation erfolgreich!**\n\n"
                reply += f"📍 URL: {url}\n"
                reply += f"🎯 Ziel: {goal}\n"
                reply += f"📊 Schritte: {result.get('steps_taken', 0)}\n"
                
                if results_count > 0:
                    reply += f"🔍 **Suchergebnisse ({results_count}):**\n\n"
                    for i, res in enumerate(extracted.get("search_results", [])[:5], 1):
                        reply += f"{i}. **{res.get('title', 'Kein Titel')}**\n"
                        reply += f"   🔗 {res.get('url', '')[:80]}\n"
                        if res.get('snippet'):
                            reply += f"   📝 {res.get('snippet', '')[:100]}...\n"
                        reply += "\n"
                else:
                    reply += f"📄 Content extrahiert: {len(extracted.get('text', ''))} Zeichen\n"
                
                return {"status": "success", "reply": reply}
            else:
                return {"status": "error", "reply": f"❌ Navigation fehlgeschlagen: {result.get('error')}"}
        
        elif subcmd == "search" and len(args) >= 2:
            search_term = " ".join(args[1:])
            url = "https://www.startpage.com"
            goal = f"Suche nach '{search_term}'"
            
            from gateway.integrations.som_agent import get_som_agent
            
            agent = get_som_agent(headless=True)
            result = await agent.navigate(url=url, goal=goal, max_steps=5)
            
            if result.get("success"):
                extracted = result.get("extracted_content", {})
                results = extracted.get("search_results", [])
                
                if results:
                    reply = f"🔍 **Suchergebnisse für '{search_term}':**\n\n"
                    for i, res in enumerate(results[:10], 1):
                        reply += f"{i}. **{res.get('title', 'Kein Titel')}**\n"
                        reply += f"   🔗 {res.get('url', '')[:80]}\n\n"
                    
                    return {"status": "success", "reply": reply}
                else:
                    return {"status": "error", "reply": f"❌ Keine Suchergebnisse für '{search_term}' gefunden"}
            else:
                return {"status": "error", "reply": f"❌ Suche fehlgeschlagen: {result.get('error')}"}
        
        elif subcmd == "learned":
            from gateway.integrations.som_agent import get_som_agent
            
            agent = get_som_agent()
            learned = agent.memory.get("learned_actions", [])[-10:]
            
            if not learned:
                return {"status": "success", "reply": "📭 Noch keine gelernten Inhalte."}
            
            reply = "🧠 **Letzte 10 gelernte Inhalte:**\n\n"
            for i, entry in enumerate(learned, 1):
                if entry.get("url"):
                    reply += f"{i}. 🌐 {entry.get('url', '')[:60]}\n"
                    reply += f"   🎯 {entry.get('goal', '')[:60]}\n"
                    reply += f"   📅 {entry.get('learned_at', '')[:19]}\n\n"
                else:
                    reply += f"{i}. 📝 {entry.get('text', '')[:80]}\n"
                    reply += f"   📅 {entry.get('learned_at', '')[:19]}\n\n"
            
            return {"status": "success", "reply": reply}
        
        elif subcmd == "stats":
            from pathlib import Path
            import json
            
            memory_file = Path(__file__).parent.parent / "integrations" / "som_memory.json"
            
            if not memory_file.exists():
                return {"status": "success", "reply": "📊 Keine Statistiken verfügbar."}
            
            memory = json.loads(memory_file.read_text(encoding='utf-8'))
            learned = memory.get("learned_actions", [])
            
            total_results = 0
            urls = set()
            for entry in learned:
                if entry.get("url"):
                    urls.add(entry.get("url"))
                content = entry.get("content", {})
                total_results += len(content.get("search_results", []))
            
            reply = f"📊 **SoM Agent Statistiken:**\n\n"
            reply += f"📚 Gelernte Aktionen: {len(learned)}\n"
            reply += f"🌐 Besuchte URLs: {len(urls)}\n"
            reply += f"🔍 Gespeicherte Suchergebnisse: {total_results}\n"
            reply += f"💾 Memory-Größe: {memory_file.stat().st_size / 1024:.1f} KB\n"
            
            return {"status": "success", "reply": reply}
        
        elif subcmd == "memory":
            from gateway.integrations.som_agent import get_som_agent
            import json
            
            agent = get_som_agent()
            memory_json = json.dumps(agent.memory, indent=2, ensure_ascii=False)
            
            if len(memory_json) > 3000:
                memory_json = memory_json[:3000] + "...\n\n(gekürzt)"
            
            return {
                "status": "success",
                "reply": f"🧠 **SoM Memory:**\n```json\n{memory_json}\n```"
            }
        
        elif subcmd == "clear":
            from pathlib import Path
            import json
            from datetime import datetime
            
            memory_file = Path(__file__).parent.parent / "integrations" / "som_memory.json"
            
            if memory_file.exists():
                backup = memory_file.with_suffix(f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
                backup.write_bytes(memory_file.read_bytes())
            
            empty_memory = {"pages": {}, "learned_actions": []}
            memory_file.write_text(json.dumps(empty_memory, indent=2, ensure_ascii=False), encoding='utf-8')
            
            return {
                "status": "success",
                "reply": "✅ SoM Memory wurde gelöscht.\nBackup wurde erstellt."
            }
        
        else:
            return {
                "status": "error",
                "reply": f"❌ Unbekannter SoM-Befehl: `{subcmd}`\n\n"
                        "Verfügbare Befehle: navigate, search, learned, stats, memory, clear"
            }

          
    # ===== SoM DATEN EXTRAHIEREN =====
    elif command == "extract":
        """Extrahiert Daten von einer Website mit SoM"""
        if not args:
            return {
                "status": "success",
                "reply": "📊 **SoM Daten-Extraktion:**\n\n"
                        "`/extract <url> [data-type]` - Daten von Website extrahieren\n\n"
                        "**Datentypen:**\n"
                        "• `text` - Volltext (Standard)\n"
                        "• `links` - Alle Links\n"
                        "• `images` - Alle Bilder\n"
                        "• `headings` - Überschriften\n"
                        "• `prices` - Preise (z.B. bei Shops)\n"
                        "• `table` - Tabellen\n"
                        "• `meta` - Meta-Informationen\n\n"
                        "**Beispiele:**\n"
                        "`/extract https://example.com text`\n"
                        "`/extract https://shop.at prices`\n"
                        "`/extract https://news.at headlines`"
            }
        
        url = args[0]
        data_type = args[1].lower() if len(args) > 1 else "text"
        
        # Validierung
        valid_types = ["text", "links", "images", "headings", "prices", "table", "meta"]
        if data_type not in valid_types:
            return {
                "status": "error",
                "reply": f"❌ Unbekannter Datentyp: {data_type}\n\nVerfügbar: {', '.join(valid_types)}"
            }
        
        try:
            from gateway.integrations.som_agent import get_som_agent
            import re
            import httpx
            
            logger.info(f"📊 SoM Extraction: {url} (Typ: {data_type})")

            # ===== NEU: XML/SITEMAP-ERKENNUNG =====
            if url.endswith(".xml") or "sitemap" in url.lower():
                logger.info(f"📄 XML/Sitemap erkannt, verwende HTTP-Request")
                
                import requests
                from datetime import datetime
                import urllib3
                urllib3.disable_warnings()
                
                try:
                    response = requests.get(url, verify=False, timeout=30)
                    
                    if response.status_code == 200:
                        content = response.text[:5000]
                        reply = f"📄 **Sitemap von {url}**\n\n```xml\n{content}\n```"
                        
                        # Cache speichern
                        agent = get_som_agent(headless=True)
                        agent.memory["learned_actions"].append({
                            "type": "sitemap",
                            "url": url,
                            "content": {"text": content},
                            "learned_at": datetime.now().isoformat()
                        })
                        agent._save_memory()
                        
                        return {
                            "status": "success",
                            "reply": reply,
                            "tool_used": "sitemap_fetch"
                        }
                    else:
                        return {"status": "error", "reply": f"❌ Sitemap-Fehler: {response.status_code}"}
                        
                except Exception as e:
                    logger.error(f"Sitemap Fetch Fehler: {e}")
                    return {"status": "error", "reply": f"❌ Fehler: {e}"}


            # ===== NEU: API/JSON-ERKENNUNG (VOR Browser-Start!) =====
            if "/wp-json/" in url or url.endswith(".json") or "api" in url.lower():
                logger.info(f"📡 API-Endpunkt erkannt, verwende HTTP-Request statt Browser")
                
                # Importe innerhalb des Blocks
                import json as json_module
                import requests
                from datetime import datetime  # Wichtig!
                
                # SSL-Warnungen unterdrücken (optional)
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                
                try:
                    response = requests.get(url, verify=False, timeout=30)
                    
                    if response.status_code == 200:
                        try:
                            data = response.json()
                            
                            # Für WordPress Posts
                            if isinstance(data, list) and "wp-json" in url:
                                posts = data
                                reply = f"📝 **WordPress Beiträge ({len(posts)}):**\n\n"
                                
                                for i, post in enumerate(posts[:20], 1):
                                    title = post.get('title', {}).get('rendered', 'Kein Titel')[:60]
                                    link = post.get('link', '')
                                    date = post.get('date', '')[:10]
                                    reply += f"{i}. **{title}**\n"
                                    reply += f"   🔗 {link}\n"
                                    reply += f"   📅 {date}\n\n"
                                
                                if len(posts) > 20:
                                    reply += f"\n... und {len(posts) - 20} weitere Beiträge"
                                
                                # Optional: Speichere im SoM Memory (ohne Browser)
                                agent = get_som_agent(headless=True)
                                agent.memory["learned_actions"].append({
                                    "type": "wp_posts",
                                    "url": url,
                                    "content": {"posts": posts[:100]},
                                    "learned_at": datetime.now().isoformat()
                                })
                                agent._save_memory()
                                
                                return {
                                    "status": "success",
                                    "reply": reply,
                                    "tool_used": "wp_api",
                                    "data": {"posts": posts[:50]},
                                    "total": len(posts)
                                }
                            else:
                                # Allgemeines JSON
                                reply = f"📡 **API-Antwort von {url}**\n\n```json\n{json_module.dumps(data, indent=2, ensure_ascii=False)[:3000]}\n```"
                                return {"status": "success", "reply": reply}
                                
                        except json_module.JSONDecodeError as e:
                            # Fallback auf Text
                            reply = f"📡 **API-Antwort (Text) von {url}**\n\n{response.text[:3000]}"
                            return {"status": "success", "reply": reply}
                        except Exception as e:
                            logger.error(f"JSON Parsing Fehler: {e}")
                            reply = f"📡 **API-Antwort (Text) von {url}**\n\n{response.text[:3000]}"
                            return {"status": "success", "reply": reply}
                    else:
                        return {"status": "error", "reply": f"❌ API-Fehler: {response.status_code}"}
                        
                except requests.exceptions.SSLError as e:
                    logger.error(f"SSL Fehler: {e}")
                    return {"status": "error", "reply": f"❌ SSL-Fehler: {e}\n\nDie Seite verwendet ein selbst-signiertes Zertifikat."}
                except requests.exceptions.ConnectionError as e:
                    logger.error(f"Connection Fehler: {e}")
                    return {"status": "error", "reply": f"❌ Verbindungsfehler: {e}"}
                except Exception as e:
                    logger.error(f"API Request Fehler: {e}")
                    return {"status": "error", "reply": f"❌ Fehler bei API-Anfrage: {e}"}
            
            agent = get_som_agent(headless=True)
            
            # ===== NEU: PRÜFE CACHE VOR DER NAVIGATION =====
            cached_content = None
            cached_entry = None
            
            # Suche in gelernten Aktionen (neueste zuerst)
            for entry in reversed(agent.memory.get("learned_actions", [])):
                if entry.get("url") == url:
                    content = entry.get("content", {})
                    
                    # Prüfe ob Content zum Datentyp passt
                    if data_type == "links" and content.get("links"):
                        cached_content = content
                        cached_entry = entry
                        logger.info(f"⚡ Cache-Hit für {url} (Links: {len(content.get('links', []))})")
                        break
                    elif data_type == "text" and content.get("text"):
                        cached_content = content
                        cached_entry = entry
                        logger.info(f"⚡ Cache-Hit für {url} (Text: {len(content.get('text', ''))} Zeichen)")
                        break
                    elif data_type == "images" and content.get("images"):
                        cached_content = content
                        cached_entry = entry
                        logger.info(f"⚡ Cache-Hit für {url} (Bilder: {len(content.get('images', []))})")
                        break
                    elif data_type == "headings" and content.get("headings"):
                        cached_content = content
                        cached_entry = entry
                        logger.info(f"⚡ Cache-Hit für {url} (Überschriften: {len(content.get('headings', []))})")
                        break
                    elif data_type == "meta" and (content.get("title") or content.get("description")):
                        cached_content = content
                        cached_entry = entry
                        logger.info(f"⚡ Cache-Hit für {url} (Meta-Daten)")
                        break
                    elif data_type == "table" and content.get("tables"):
                        cached_content = content
                        cached_entry = entry
                        logger.info(f"⚡ Cache-Hit für {url} (Tabellen: {len(content.get('tables', []))})")
                        break
            
            # Wenn Cache vorhanden, nutze ihn sofort (ohne Browser!)
            if cached_content:
                logger.info(f"✅ Verwende gelernten Content für {url} (gelernt am: {cached_entry.get('learned_at', 'unbekannt')[:19]})")
                
                # Verarbeite den gecachten Content je nach Datentyp
                if data_type == "text":
                    text = cached_content.get("text", "")
                    if text:
                        text_preview = text[:3000]
                        if len(text) > 3000:
                            text_preview += "\n\n... (Text gekürzt)"
                        reply = f"📄 **Text von {url}**\n\n{text_preview}"
                    else:
                        reply = f"⚠️ Kein Text gefunden auf {url}"
                
                elif data_type == "links":
                    links = cached_content.get("links", [])
                    if links:
                        reply = f"🔗 **Links von {url}**\n\n"
                        for i, link in enumerate(links[:30], 1):
                            text = link.get('text', 'Kein Text')[:50]
                            href = link.get('href', '')[:80]
                            reply += f"{i}. [{text}]({href})\n"
                        if len(links) > 30:
                            reply += f"\n... und {len(links) - 30} weitere Links"
                    else:
                        reply = f"⚠️ Keine Links gefunden auf {url}"
                
                elif data_type == "images":
                    images = cached_content.get("images", [])
                    if images:
                        reply = f"🖼️ **Bilder von {url}**\n\n"
                        for i, img in enumerate(images[:20], 1):
                            src = img.get('src', '')[:80]
                            alt = img.get('alt', 'Kein Alt-Text')[:50]
                            reply += f"{i}. ![{alt}]({src})\n"
                        if len(images) > 20:
                            reply += f"\n... und {len(images) - 20} weitere Bilder"
                    else:
                        reply = f"⚠️ Keine Bilder gefunden auf {url}"
                
                elif data_type == "headings":
                    headings = cached_content.get("headings", [])
                    if headings:
                        reply = f"📌 **Überschriften von {url}**\n\n"
                        for h in headings[:30]:
                            level = h.get('level', 'h?')
                            text = h.get('text', '')[:80]
                            reply += f"{level}: {text}\n"
                    else:
                        reply = f"⚠️ Keine Überschriften gefunden auf {url}"
                
                elif data_type == "meta":
                    title = cached_content.get("title", "")
                    description = cached_content.get("description", "")
                    keywords = cached_content.get("keywords", "")
                    
                    reply = f"📋 **Meta-Informationen von {url}**\n\n"
                    reply += f"**Titel:** {title}\n\n"
                    reply += f"**Beschreibung:** {description}\n\n"
                    if keywords:
                        reply += f"**Keywords:** {keywords}\n"
                
                elif data_type == "table":
                    tables = cached_content.get("tables", [])
                    if tables:
                        reply = f"📊 **Tabellen von {url}**\n\n"
                        for i, table in enumerate(tables[:3], 1):
                            reply += f"**Tabelle {i}:**\n"
                            rows = table.get('rows', [])
                            for row in rows[:10]:
                                reply += "| " + " | ".join([str(cell)[:30] for cell in row]) + " |\n"
                            reply += "\n"
                    else:
                        reply = f"⚠️ Keine Tabellen gefunden auf {url}"
                
                elif data_type == "prices":
                    # Preise müssen immer neu extrahiert werden (können sich ändern!)
                    logger.info(f"💰 Preise werden immer frisch extrahiert (kein Cache)")
                    # Fallthrough - keine Cache-Nutzung für Preise
                    cached_content = None
            
            # Wenn KEIN Cache (oder Preise) – normale Navigation starten
            if not cached_content or data_type == "prices":
                logger.info(f"🔍 Kein Cache für {url} (oder Preise), starte Navigation")
                
                # Extraktions-Ziel je nach Typ
                if data_type == "text":
                    goal = f"Extrahiere den gesamten Text von {url}"
                elif data_type == "links":
                    goal = f"Finde alle Links auf {url}"
                elif data_type == "images":
                    goal = f"Finde alle Bilder auf {url}"
                elif data_type == "headings":
                    goal = f"Extrahiere alle Überschriften (h1, h2, h3) von {url}"
                elif data_type == "prices":
                    goal = f"Finde alle Preise auf {url} (im Format €, $, EUR)"
                elif data_type == "table":
                    goal = f"Extrahiere Tabellen von {url}"
                elif data_type == "meta":
                    goal = f"Extrahiere Meta-Informationen (Title, Description, Keywords) von {url}"
                else:
                    goal = f"Extrahiere alle verfügbaren Daten von {url}"
                
                result = await agent.navigate(url=url, goal=goal, max_steps=3)
                
                if result.get("success"):
                    extracted = result.get("extracted_content", {})
                    
                    # Verarbeite das Ergebnis (wie oben)
                    if data_type == "text":
                        text = extracted.get("text", "")
                        if text:
                            text_preview = text[:3000]
                            if len(text) > 3000:
                                text_preview += "\n\n... (Text gekürzt)"
                            reply = f"📄 **Text von {url}**\n\n{text_preview}"
                        else:
                            reply = f"⚠️ Kein Text gefunden auf {url}"
                    
                    elif data_type == "links":
                        links = extracted.get("links", [])
                        if links:
                            reply = f"🔗 **Links von {url}**\n\n"
                            for i, link in enumerate(links[:30], 1):
                                text = link.get('text', 'Kein Text')[:50]
                                href = link.get('href', '')[:80]
                                reply += f"{i}. [{text}]({href})\n"
                            if len(links) > 30:
                                reply += f"\n... und {len(links) - 30} weitere Links"
                        else:
                            reply = f"⚠️ Keine Links gefunden auf {url}"
                    
                    elif data_type == "images":
                        images = extracted.get("images", [])
                        if images:
                            reply = f"🖼️ **Bilder von {url}**\n\n"
                            for i, img in enumerate(images[:20], 1):
                                src = img.get('src', '')[:80]
                                alt = img.get('alt', 'Kein Alt-Text')[:50]
                                reply += f"{i}. ![{alt}]({src})\n"
                            if len(images) > 20:
                                reply += f"\n... und {len(images) - 20} weitere Bilder"
                        else:
                            reply = f"⚠️ Keine Bilder gefunden auf {url}"
                    
                    elif data_type == "headings":
                        headings = extracted.get("headings", [])
                        if headings:
                            reply = f"📌 **Überschriften von {url}**\n\n"
                            for h in headings[:30]:
                                level = h.get('level', 'h?')
                                text = h.get('text', '')[:80]
                                reply += f"{level}: {text}\n"
                        else:
                            reply = f"⚠️ Keine Überschriften gefunden auf {url}"
                    
                    elif data_type == "prices":
                        text = extracted.get("text", "")
                        price_patterns = [
                            r'(\d+[\.,]\d+)\s*[€$]',
                            r'[€$]\s*(\d+[\.,]\d+)',
                            r'(\d+)\s*EUR',
                            r'(\d+)\s*Euro'
                        ]
                        prices = []
                        for pattern in price_patterns:
                            matches = re.findall(pattern, text)
                            for match in matches:
                                price_str = match.replace(',', '.')
                                try:
                                    price = float(price_str)
                                    prices.append(price)
                                except:
                                    pass
                        
                        if prices:
                            unique_prices = sorted(set(prices))
                            reply = f"💰 **Preise auf {url}**\n\n"
                            for price in unique_prices[:20]:
                                reply += f"• {price:.2f} €\n"
                            if len(unique_prices) > 20:
                                reply += f"\n... und {len(unique_prices) - 20} weitere Preise"
                        else:
                            reply = f"⚠️ Keine Preise gefunden auf {url}"
                    
                    elif data_type == "table":
                        tables = extracted.get("tables", [])
                        if tables:
                            reply = f"📊 **Tabellen von {url}**\n\n"
                            for i, table in enumerate(tables[:3], 1):
                                reply += f"**Tabelle {i}:**\n"
                                rows = table.get('rows', [])
                                for row in rows[:10]:
                                    reply += "| " + " | ".join([str(cell)[:30] for cell in row]) + " |\n"
                                reply += "\n"
                        else:
                            reply = f"⚠️ Keine Tabellen gefunden auf {url}"
                    
                    elif data_type == "meta":
                        title = extracted.get("title", "")
                        description = extracted.get("description", "")
                        keywords = extracted.get("keywords", "")
                        
                        reply = f"📋 **Meta-Informationen von {url}**\n\n"
                        reply += f"**Titel:** {title}\n\n"
                        reply += f"**Beschreibung:** {description}\n\n"
                        if keywords:
                            reply += f"**Keywords:** {keywords}\n"
                    
                    # Speichere die extrahierten Daten im SoM Memory (nur wenn nicht schon gespeichert)
                    agent.memory["learned_actions"].append({
                        "type": f"extraction_{data_type}",
                        "url": url,
                        "content": extracted,
                        "learned_at": datetime.now().isoformat()
                    })
                    agent._save_memory()
                    
                    return {
                        "status": "success",
                        "reply": reply,
                        "tool_used": f"som_extract_{data_type}",
                        "data": extracted,
                        "cached": False
                    }
                else:
                    return {
                        "status": "error",
                        "reply": f"❌ Extraktion fehlgeschlagen: {result.get('error')}"
                    }
            else:
                # Cache-Hit (außer bei Preisen)
                return {
                    "status": "success",
                    "reply": reply,
                    "tool_used": f"som_extract_{data_type}_cached",
                    "data": cached_content,
                    "cached": True
                }
                
        except Exception as e:
            logger.error(f"SoM Extraction Fehler: {e}")
            return {
                "status": "error",
                "reply": f"❌ Fehler bei Extraktion: {str(e)}"
            }

           
    # ===== UNBEKANNTER BEFEHL =====
    else:
        return {
            "status": "error", 
            "reply": f"❌ Unbekannter Befehl: `{command}`\n\nVerwende `/help` für alle verfügbaren Befehle."
        }

@router.post("/v1/chat/completions")
async def chat_completions(
    payload: dict,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """OpenAI-compatible /v1/chat/completions endpoint."""
    model = payload.get("model", ollama_client.default_model)
    messages = payload.get("messages", [])
    try:
        response = await _ollama_chat_async(model=model, messages=messages)
        return {
            "id": f"chatcmpl-{response.get('id', 'unknown')}",
            "object": "chat.completion",
            "created": response.get("created", 0),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": response.get("message", {}),
                    "finish_reason": response.get("done", True) and "stop" or "length",
                }
            ],
            "usage": response.get(
                "usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            ),
        }
    except Exception as e:
        logger.error(f"Chat completion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/v1/models")
async def list_models(_api_key: str = Depends(verify_api_key)) -> dict[str, Any]:
    """List available Ollama models."""
    try:
        result = await _ollama_list_models_async()
        return {
            "object": "list",
            "data": [
                {
                    "id": m.get("name", ""),
                    "object": "model",
                    "created": 0,
                    "owned_by": "ollama",
                }
                for m in result.get("models", [])
            ],
        }
    except Exception as e:
        logger.error(f"List models error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ Memory Endpoint ============
@router.get("/api/memory")
# async def get_memory(_api_key: str = Depends(verify_api_key)):
async def get_memory():
    """Gibt das aktuelle Memory zurück"""
    return {
        "memory": chat_memory.memory_content,
        "skills": chat_memory.skills_content,
        "heartbeat": chat_memory.heartbeat_content,
        "remembered_notes": chat_memory.get_remembered_notes(limit=100),
        "conversation_count": len(chat_memory.conversation_history) // 2,
        "last_updated": datetime.now().isoformat(),
    }

# ============ Vision/YOLO Stream Endpoint ============
@router.get("/api/vision/stream-status")
# async def get_vision_stream_status(_api_key: str = Depends(verify_api_key)):
async def get_vision_stream_status():
    """Gibt den Status des YOLO-Streams zurück"""
    vision = get_gabi_vision()
    if not vision:
        return {"active": False, "objects": [], "error": "Vision nicht verfügbar"}

    return {
        "active": vision._webcam_active if hasattr(vision, '_webcam_active') else False,
        "objects": vision._last_yolo_objects if hasattr(vision, '_last_yolo_objects') else [],
        "timestamp": datetime.now().isoformat()
    }

@router.post("/api/vision/stream-start")
async def start_vision_stream(
    interval: float = 2.0,
    _api_key: str = Depends(verify_api_key)
):
    """Startet den YOLO-Stream"""
    vision = get_gabi_vision()
    if not vision:
        return {"success": False, "error": "Vision nicht verfügbar"}

    result = vision.start_yolo_stream(interval=interval)
    return result

@router.post("/api/vision/stream-stop")
async def stop_vision_stream(_api_key: str = Depends(verify_api_key)):
    """Stoppt den YOLO-Stream"""
    vision = get_gabi_vision()
    if not vision:
        return {"success": False, "error": "Vision nicht verfügbar"}

    return vision.stop_yolo_stream()

# ============ Vision Stream Endpoint ============
@router.get("/api/vision/stream")
async def get_vision_stream(_api_key: str = Depends(verify_api_key)):
    """Gibt den aktuellen YOLO-Stream Status und letzte Erkennungen zurück"""
    try:
        vision = get_gabi_vision()
        if not vision:
            return {"active": False, "objects": [], "error": "Vision nicht verfügbar"}

        is_active = getattr(vision, '_webcam_active', False)
        last_objects = getattr(vision, '_last_yolo_objects', [])

        return {
            "active": is_active,
            "objects": last_objects,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {"active": False, "objects": [], "error": str(e)}
# Optional: Methode zum manuellen Archivieren

@router.post("/api/memory/archive")
async def archive_memory(_api_key: str = Depends(verify_api_key)):
    """Manuelles Archivieren des Memory (GET oder POST)"""
    try:
        # Gleicher Code wie vorher...
        if hasattr(chat_memory, "_archive_old_memory"):
            chat_memory._archive_old_memory()
            return {
                "status": "success",
                "message": "Memory wurde erfolgreich archiviert",
                "timestamp": datetime.now().isoformat(),
            }
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            # Erstelle memory_archive Verzeichnis falls nicht vorhanden
            archive_dir = Path(__file__).parent.parent / "memory_archive"
            archive_dir.mkdir(exist_ok=True)
            archive_name = archive_dir / f"MEMORY_ARCHIVE_{timestamp}.md"
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            with open(archive_name, "w", encoding="utf-8") as f:
                f.write(
                    f"""# GABI Memory Archiv vom {datetime.now().strftime('%Y-%m-%d %H:%M')}
{content}
"""
                )
            return {
                "status": "success",
                "message": f"Memory wurde in {archive_name} archiviert",
                "archive_file": archive_name,
            }
    except Exception as e:
        logger.error(f"Fehler beim Archivieren: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 🔥 Memory Reset Endpoint (mit GET und POST)
@router.api_route("/api/memory/reset", methods=["GET", "POST"])
# async def reset_memory(_api_key: str = Depends(verify_api_key)):
async def reset_memory():
    """Setzt das Memory zurück (Vorsicht!) - GET oder POST"""
    try:
        # 1. Backup erstellen vor dem Zurücksetzen
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"MEMORY_BACKUP_{timestamp}.md"
        if os.path.exists(MEMORY_FILE):
            import shutil
            shutil.copy2(MEMORY_FILE, backup_name)
            logger.info(f"Memory-Backup erstellt: {backup_name}")
        # 2. Memory zurücksetzen mit Default-Inhalt
        default_content = f"""# GABI Memory System
## Aktuelle Konversation
- Datum: {datetime.now().strftime('%Y-%m-%d')}
- Thema: Memory zurückgesetzt
- User: Admin
## Wichtige Informationen
- Gateway läuft auf http://localhost:8000
- API-Key: In config.yaml konfiguriert
- Ollama Modell: {ollama_client.default_model}
- Telegram Bot: Aktiv
## Letzte Aktivitäten
- {datetime.now().strftime('%H:%M')}: Memory wurde zurückgesetzt
---
"""
        with open(MEMORY_FILE, "w", encoding="utf-8") as f:
            f.write(default_content)
        # 3. ChatMemory Instanz aktualisieren
        chat_memory.memory_content = default_content
        chat_memory.conversation_history = []
        # 4. Skills und Heartbeat nicht zurücksetzen (bleiben erhalten)
        # 5. Heartbeat aktualisieren
        chat_memory.update_heartbeat()
        return {
            "status": "success",
            "message": "Memory wurde zurückgesetzt",
            "backup_file": backup_name,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"Fehler beim Zurücksetzen des Memory: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Optional: Memory-Statistiken
@router.get("/api/memory/stats")
# async def memory_stats(_api_key: str = Depends(verify_api_key)):
async def memory_stats():
    """Gibt Statistiken über das Memory zurück"""
    try:
        memory_size = os.path.getsize(MEMORY_FILE) if os.path.exists(MEMORY_FILE) else 0
        memory_lines = (
            len(chat_memory.memory_content.split("\n"))
            if chat_memory.memory_content
            else 0
        )
        # Zähle Konversationen (ungefähr anhand der Datumsüberschriften)
        conversation_count = chat_memory.memory_content.count("## 20")
        # Archivdateien finden
        archives = [
            f
            for f in os.listdir(".")
            if f.startswith("MEMORY_ARCHIVE") and f.endswith(".md")
        ]
        return {
            "status": "success",
            "stats": {
                "memory_file": MEMORY_FILE,
                "file_size_kb": round(memory_size / 1024, 2),
                "lines": memory_lines,
                "conversations": conversation_count,
                "history_count": len(chat_memory.conversation_history) // 2,
                "remembered_notes": len(chat_memory.user_notes),
                "archives_available": len(archives),
                "archive_files": archives[-5:] if archives else [],  # Letzte 5 Archive
            },
        }
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Memory-Statistiken: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ Shell Executor Endpoints ============
@router.post("/api/shell/execute")
async def execute_shell(
    payload: dict,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Execute a shell command from allowlist."""
    command = payload.get("command")
    args = payload.get("args", [])
    if not command:
        raise HTTPException(status_code=400, detail="Command is required")
    try:
        result = shell_executor.execute(command, args)
        return result
    except PermissionError as e:
        logger.warning(f"Shell permission denied: {e}")
        raise HTTPException(status_code=403, detail=str(e))
    except TimeoutError as e:
        raise HTTPException(status_code=408, detail=str(e))
    except Exception as e:
        logger.error(f"Shell execution error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/shell/allowed")
# async def list_allowed_commands(_api_key: str = Depends(verify_api_key)) -> dict:
async def list_allowed_commands() -> dict:
    """List allowed shell commands."""
    return {"allowed_commands": shell_executor.get_allowed_commands()}

# ============ Gmail Endpoints ============
@router.get("/api/gmail/mails")
async def list_gmail_messages(
    max_results: int = 10,
    query: str = "",
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """List Gmail messages."""
    try:
        messages = get_gmail_client().list_messages(
            max_results=max_results, query=query
        )
        return {"messages": messages, "count": len(messages)}
    except Exception as e:
        logger.error(f"Gmail list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@router.get("/api/gmail/mail/{message_id}")
async def get_gmail_message(
    message_id: str,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Get a specific Gmail message."""
    try:
        client = get_gmail_client()
        message = client.get_message(message_id)
        body = client.get_message_body(message)
        return {"message": message, "body": body}
    except Exception as e:
        logger.error(f"Gmail get error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@router.post("/api/gmail/send")
async def send_gmail_message(
    payload: dict,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Send a Gmail message."""
    to = payload.get("to")
    subject = payload.get("subject", "")
    body = payload.get("body", "")
    if not to:
        raise HTTPException(status_code=400, detail="Recipient 'to' is required")
    try:
        result = get_gmail_client().send_message(to, subject, body)
        return {"success": True, "message_id": result.get("id")}
    except Exception as e:
        logger.error(f"Gmail send error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@router.post("/api/gmail/mail/{message_id}/modify")
async def modify_gmail_message(
    message_id: str,
    payload: dict,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Modify Gmail message labels (archive, star, etc.)."""
    add_labels = payload.get("add_labels")
    remove_labels = payload.get("remove_labels")
    try:
        result = get_gmail_client().modify_message(
            message_id, add_labels, remove_labels
        )
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"Gmail modify error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
# ============ Whisper Endpoints ============
@router.get("/api/whisper/status")
async def whisper_status() -> dict:
    """Check Whisper server status."""
    try:
        whisper = get_whisper_client()
        available = whisper.is_available()
        models = whisper.get_models() if available else []
        return {"available": available, "models": models}
    except Exception as e:
        logger.error(f"Whisper status error: {e}")
        return {"available": False, "error": str(e)}
@router.post("/api/whisper/transcribe")
async def transcribe_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    language: Optional[str] = None,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """Transcribe audio file."""
    try:
        whisper = get_whisper_client()
        if not whisper.is_available():
            raise HTTPException(status_code=503, detail="Whisper server not available")
        # Save uploaded file temporarily
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        # Transcribe in background
        def transcribe_task():
            try:
                result = whisper.transcribe_file(tmp_path, language)
                logger.info(f"Transcription complete: {result}")
            finally:
                os.unlink(tmp_path)
        background_tasks.add_task(transcribe_task)
        return {"status": "processing", "message": "Transcription started"}
    except Exception as e:
        logger.error(f"Whisper transcribe error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# === VOICE API ALIAS ===
@router.post("/api/voice/transcribe")
async def voice_transcribe(
    file: UploadFile = File(...),
    language: Optional[str] = None,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """
    Voice Transcription Endpoint - Alias für /api/whisper/transcribe/sync.
    Nimmt Audio-Dateien entgegen, transkribiert sie mit Whisper und
    gibt das Ergebnis zurück das in den Chat-Kontext eingespeist werden kann.
    """
    tmp_path = None
    try:
        whisper = get_whisper_client()
        if not whisper.is_available():
            raise HTTPException(status_code=503, detail="Whisper server not available")

        # Temporäre Datei erstellen
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix if file.filename else '.wav') as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        filename = file.filename or 'audio.wav'
        logger.info(f"🎤 Voice Transcribe: {filename} ({len(content)} bytes)")

        # Transkribieren
        result = whisper.transcribe_file(tmp_path, language)

        if result.get("status") == "success":
            return {
                "status": "success",
                "text": result.get("text", ""),
                "language": result.get("language", "unknown"),
                "duration": result.get("duration", 0),
                "confidence": result.get("result", {}).get("avg_logprob", None)
            }
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Transcription failed"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Voice transcribe error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Aufräumen
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except:
                pass

@router.post("/api/whisper/transcribe/sync")
async def transcribe_audio_sync(
    file: UploadFile = File(...),
    language: Optional[str] = None,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """Transcribe audio file synchronously."""
    tmp_path = None
    try:
        whisper = get_whisper_client()
        if not whisper.is_available():
            raise HTTPException(status_code=503, detail="Whisper server not available")
        
        # Prüfe ob eine Datei hochgeladen wurde
        if not file:
            raise HTTPException(status_code=400, detail="Keine Datei hochgeladen")
        
        # Datei-Infos
        filename = getattr(file, 'filename', 'audio.wav')
        logger.info(f"🎤 Empfange Datei: {filename}")

        # Lese Datei direkt in Memory
        content = await file.read()
        logger.info(f"📦 Dateigröße: {len(content)} bytes")

        # Konvertiere webm zu wav falls nötig
        import io
        import subprocess

        input_ext = filename.split('.')[-1].lower() if '.' in filename else 'webm'

        if input_ext in ['webm', 'mp4', 'm4a', 'ogg'] and len(content) > 0:
            # Konvertiere zu wav mit ffmpeg
            try:
                # Erst einen temp input
                import tempfile
                with tempfile.NamedTemporaryFile(delete=False, suffix=f'.{input_ext}') as tmp_in:
                    tmp_in.write(content)
                    tmp_in_path = tmp_in.name

                tmp_out = tempfile.NamedTemporaryFile(delete=False, suffix='.wav')
                tmp_out_path = tmp_out.name
                tmp_out.close()

                # Konvertiere
                result = subprocess.run([
                    'ffmpeg', '-y', '-i', tmp_in_path,
                    '-ar', '16000', '-ac', '1', '-c:a', 'pcm_s16le',
                    tmp_out_path
                ], capture_output=True, timeout=30)

                os.unlink(tmp_in_path)

                if result.returncode == 0 and os.path.getsize(tmp_out_path) > 1000:
                    with open(tmp_out_path, 'rb') as f:
                        content = f.read()
                    filename = 'audio.wav'
                    os.unlink(tmp_out_path)
                    logger.info(f"🔄 Konvertiert zu wav: {len(content)} bytes")
                else:
                    logger.warning(f"ffmpeg Konvertierung fehlgeschlagen: {result.stderr.decode()}")
                    if os.path.exists(tmp_out_path):
                        os.unlink(tmp_out_path)

            except Exception as e:
                logger.error(f"Konvertierungsfehler: {e}")

        # Sende DIREKT an Whisper-Server
        import requests
        
        # WICHTIG: Der Whisper-Server will:
        # 1. file im QUERY-STRING
        # 2. file im BODY als multipart
        params = {'file': filename}
        if language:
            params['language'] = language
        
        # Datei als Bytes für den Upload (MIME aus Upload übernehmen)
        content_type = getattr(file, "content_type", None) or "application/octet-stream"
        files = {'file': (filename, content, content_type)}
        
        logger.info(f"📤 Sende an Whisper: {whisper.base_url}/inference mit params={params}")
        
        response = requests.post(
            f"{whisper.base_url}/inference",
            params=params,
            files=files,
            timeout=60
        )
        
        logger.info(f"📥 Whisper Antwort: Status {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            text = result.get('text', '')
            if not text and 'segments' in result:
                text = ' '.join([seg.get('text', '') for seg in result.get('segments', [])])
            
            return {
                "status": "success",
                "text": text,
                "result": result,
                "language": result.get('detected_language', language),
                "duration": result.get('duration', 0)
            }
        else:
            error_text = response.text
            logger.error(f"❌ Whisper Fehler {response.status_code}: {error_text}")
            return {
                "status": "error",
                "error": f"Whisper-Server Fehler {response.status_code}: {error_text}"
            }
        
    except Exception as e:
        logger.error(f"❌ Transkriptionsfehler: {e}")
        return {
            "status": "error",
            "error": str(e)
        }

# Alias für /api/voice/transcribe (zusätzlicher Endpunkt)
@router.post("/api/voice/transcribe")
async def voice_transcribe(
    file: UploadFile = File(...),
    language: Optional[str] = None,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """
    Voice transcription endpoint - alias für /api/whisper/transcribe/sync.
    Nimmt Audio-Dateien entgegen und transkribiert sie mit Whisper.
    """
    # Delegiere an den bestehenden sync-Endpoint
    return await transcribe_audio_sync(file, language, _api_key)

# ============ Telegram Endpoints ============
@router.get("/api/telegram/status")
async def telegram_api_status(token: str = Header(None)):
    """Check Telegram bot status."""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    
    try:
        bot = get_telegram_bot()
        return {
            "status": "success",
            "enabled": config.get("telegram.enabled", False),
            "bot_token_set": bool(bot.bot_token and bot.bot_token != "YOUR_TELEGRAM_BOT_TOKEN"),
            "bot_running": bot.application is not None,
            "active_sessions": len(bot._user_sessions) if hasattr(bot, '_user_sessions') else 0,
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "enabled": False
        }

@router.post("/api/telegram/send")
async def send_telegram_message(
    payload: dict,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """Send a message to all active Telegram users without ghost errors."""
    message = payload.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    try:
        bot = get_telegram_bot()
        
        if not bot.bot_token or bot.bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
            return {"success": False, "error": "Telegram bot not configured"}

        if not bot.application or not bot.application.bot:
            return {"success": False, "error": "Telegram bot not initialized"}

        # 1. Empfänger-Parsing
        raw_targets = payload.get("chat_ids") or payload.get("chat_id")
        explicit_targets = _parse_explicit_telegram_targets(raw_targets)

        # === FIX: Validierung der IDs ===
        # Wir filtern Wörter (wie "ich", "no") heraus. Nur echte IDs oder @Handles bleiben.
        valid_targets = []
        if explicit_targets:
            for t in explicit_targets:
                t_str = str(t).strip()
                # Prüft: Ist es eine Zahl (auch negativ für Gruppen) oder ein @Handle?
                if t_str.replace("-", "").isdigit() or t_str.startswith("@"):
                    valid_targets.append(t_str)
        
        # Wenn nach dem Filtern keine explizite ID übrig ist (weil es Text war),
        # nehmen wir die Standard-Empfänger (Dich).
        target_chat_ids = valid_targets or _get_telegram_target_chat_ids(bot)
        
        if not target_chat_ids:
            return {
                "success": False,
                "error": "Keine gültigen Telegram-Ziele gefunden."
            }

        sent_count = 0
        failed_count = 0  # === FIX: Korrekt initialisieren ===
        real_errors = []
        
        # 2. Senden
        for chat_id in target_chat_ids:
            try:
                await bot.application.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode='Markdown'
                )
                sent_count += 1
            except Exception as e:
                # === FIX: Nur bei tatsächlichem Fehler erhöhen ===
                failed_count += 1
                real_errors.append(f"Chat {chat_id}: {str(e)}")

        # 3. Saubere Rückmeldung - Korrekte Logik
        if sent_count > 0 and failed_count == 0:
            return {
                "success": True,
                "message": f"✅ Nachricht an {sent_count} Benutzer gesendet",
                "sent_count": sent_count,
                "failed_count": 0
            }
        elif sent_count > 0 and failed_count > 0:
            return {
                "success": True,
                "message": f"✅ Nachricht an {sent_count} Benutzer gesendet\n❌ Fehlgeschlagen: {failed_count}",
                "sent_count": sent_count,
                "failed_count": failed_count,
                "errors": real_errors
            }
        else:
            return {
                "success": False,
                "message": f"❌ Konnte an keinen Benutzer senden",
                "sent_count": 0,
                "failed_count": failed_count,
                "errors": real_errors
            }

    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        return {"success": False, "error": str(e)}

@router.get("/api/telegram/messages")
async def get_telegram_messages(
    since: int = 0,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """Get recent Telegram messages from active sessions."""
    try:
        bot = get_telegram_bot()
        
        # Sammle ALLE Nachrichten aus allen Sessions
        all_messages = []
        message_id = 0
        
        for user_id, session in bot._user_sessions.items():
            for msg in session:
                # Eindeutige ID erstellen (UserID + Index + Inhalt)
                unique_id = f"{user_id}-{message_id}-{hash(msg.get('content', '')) % 10000}"
                
                message_entry = {
                    "id": unique_id,
                    "message_id": message_id,
                    "user_id": user_id,
                    "role": msg.get("role", "unknown"),
                    "from": f"User {user_id}" if msg.get("role") == "user" else "GABI Bot",
                    "sender": f"User {user_id}" if msg.get("role") == "user" else "GABI Bot",
                    "text": msg.get("content", ""),
                    "message": msg.get("content", ""),
                    "date": msg.get("timestamp", datetime.now().isoformat())
                }
                all_messages.append(message_entry)
                message_id += 1
        
        # Nach Datum sortieren (neueste zuerst)
        all_messages.sort(key=lambda x: x["date"], reverse=True)
        
        # Wenn since > 0, nur Nachrichten seit dem Timestamp
        if since > 0:
            try:
                since_date = datetime.fromtimestamp(since / 1000).isoformat()
                all_messages = [m for m in all_messages if m["date"] >= since_date]
            except:
                pass
        
        # Auf max 50 Nachrichten begrenzen
        all_messages = all_messages[:50]
        
        if all_messages:
            logger.info(f"Telegram: {len(all_messages)} Nachrichten verfügbar")
        else:
            logger.debug("Telegram: keine neuen Nachrichten")
        
        return {
            "messages": all_messages,
            "count": len(all_messages),
            "active_sessions": len(bot._user_sessions)
        }
        
    except Exception as e:
        logger.error(f"Telegram get messages error: {e}")
        return {"messages": [], "count": 0, "error": str(e)}

@router.post("/api/telegram/broadcast")
async def telegram_broadcast(
    payload: dict,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """Send a broadcast message to all active Telegram users."""
    message = payload.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    
    try:
        bot = get_telegram_bot()
        
        if not bot.application or not bot.application.bot:
            return {
                "success": False,
                "error": "Telegram bot not initialized"
            }
        
        # Optional explizite Ziele via payload.chat_id / payload.chat_ids
        explicit_targets = _parse_explicit_telegram_targets(payload.get("chat_ids"))
        if not explicit_targets and payload.get("chat_id") is not None:
            explicit_targets = _parse_explicit_telegram_targets(payload.get("chat_id"))

        # An alle verfügbaren Ziele senden (aktive Sessions + config)
        target_chat_ids = explicit_targets or _get_telegram_target_chat_ids(bot)
        if not target_chat_ids:
            return {
                "success": False,
                "error": "Keine Telegram-Ziele gefunden. Setze telegram.chat_id, telegram.channel_id oder telegram.chat_ids in config.yaml."
            }

        sent = 0
        failed = 0
        
        for chat_id in target_chat_ids:
            try:
                await bot.application.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode='Markdown'
                )
                sent += 1
            except Exception as e:
                logger.error(f"Failed to send to Telegram target {chat_id}: {e}")
                failed += 1
        
        return {
            "success": True,
            "sent": sent,
            "failed": failed,
            "total": len(target_chat_ids),
            "targets": target_chat_ids
        }
        
    except Exception as e:
        logger.error(f"Telegram broadcast error: {e}")
        return {"success": False, "error": str(e)}

# ============ Health Check ============
@router.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    return {"status": "healthy"}
@router.get("/status")
async def get_status():
    """Zeigt den System- und Dienst-Status an."""
    ollama_ok = False
    models = []
    try:
        models_info = ollama_client.list_models()
        models = [m.get("name") for m in models_info.get("models", [])]
        ollama_ok = True
    except Exception:
        ollama_ok = False
    
    # Check Whisper - VERBESSERT
    whisper_ok = False
    whisper_models = []
    whisper_info = "nicht verfügbar"
    try:
        whisper = get_whisper_client()
        whisper_ok = whisper.is_available()
        if whisper_ok:
            whisper_models = whisper.get_models()
            whisper_info = f"verfügbar ({', '.join(whisper_models) if whisper_models else 'läuft'})"
        _log_whisper_state(whisper_ok, whisper_models)
    except Exception as e:
        logger.error(f"Whisper check error: {e}")
        whisper_info = f"Fehler: {str(e)}"
    
    drive_root = Path.cwd().anchor or "/"
    total, used, free = shutil.disk_usage(drive_root)

    calendar_ok = False
    try:
        calendar_ok = bool(get_calendar_client().service)
    except Exception:
        calendar_ok = False
    discovery = _get_tool_discovery(force=False)
    model_profiles = [
        {
            "name": m,
            "capabilities": _infer_model_capabilities(m),
        }
        for m in models
    ]
    
    return {
        "gateway": "online",
        "system": {
            "os": platform.system(),
            "version": platform.release(),
            "storage_drive": drive_root,
            "storage_free_gb": round(free / (2**30), 2),
            "storage_used_gb": round(used / (2**30), 2),
            "storage_total_gb": round(total / (2**30), 2),
        },
        "services": {
            "ollama": {
                "status": "connected" if ollama_ok else "offline",
                "available_models": models,
                "model_profiles": model_profiles,
            },
            "whisper": {
                "status": "connected" if whisper_ok else "offline",
                "available_models": whisper_models,
                "info": whisper_info
            },
            "telegram": {"enabled": config.get("telegram.enabled", False)},
            "gmail": {"enabled": config.get("gmail.enabled", False)},
            "calendar": {"enabled": calendar_ok},
            "image_tools": discovery,
        },
    }
# ============ Shell Endpoints ============
@router.post("/shell")
async def execute_command(request: ShellRequest, token: str = Header(None)):
    """
    Führt Shell-Befehle aus - transparent und mit voller Pipe-Unterstützung.
    """
    if token != config.get("api_key"):
        raise HTTPException(status_code=403, detail="Access Denied")
    
    try:
        # Befehl zusammenbauen
        if request.args:
            full_cmd = f"{request.command} {' '.join(request.args)}"
        else:
            full_cmd = request.command
        
        logger.info(f"🖥️ GABI EXEC: {full_cmd}")
        
        result = await asyncio.to_thread(
            subprocess.run,
            full_cmd,
            capture_output=True,
            text=True,
            shell=True,
            timeout=30,
            encoding='utf-8',
            errors='replace',
        )
        
        if 'chat_memory' in globals():
            chat_memory.update_activity()
        
        output = result.stdout
        
        # PRÜFEN AUF DATEI-ERSTELLUNG
        if '>' in full_cmd and result.returncode == 0:
            file_match = re.search(r'>\s*([^\s&|]+)', full_cmd)
            if file_match:
                filename = file_match.group(1).strip()
                if os.path.exists(filename):
                    try:
                        with open(filename, 'r', encoding='utf-8') as f:
                            file_content = f.read()
                        return {
                            "status": "success",
                            "command_executed": full_cmd,
                            "stdout": f"✅ Datei '{filename}' erstellt mit Inhalt:\n{file_content}",
                            "stderr": result.stderr,
                            "returncode": result.returncode
                        }
                    except:
                        return {
                            "status": "success",
                            "command_executed": full_cmd,
                            "stdout": f"✅ Datei '{filename}' wurde erstellt",
                            "stderr": result.stderr,
                            "returncode": result.returncode
                        }
        
        # JSON Verschönerung
        if output and output.strip().startswith(('{', '[')):
            try:
                json_data = json.loads(output)
                output = json.dumps(json_data, indent=2, ensure_ascii=False)
            except:
                pass

        return {
            "status": "success",
            "command_executed": full_cmd,
            "stdout": output if output else "(Keine Ausgabe - aber Befehl ausgeführt)",
            "stderr": result.stderr,
            "returncode": result.returncode
        }
        
    except Exception as e:
        logger.error(f"❌ Systemfehler: {e}")
        return {
            "status": "error",
            "command_executed": full_cmd if 'full_cmd' in locals() else request.command,
            "stdout": "",
            "stderr": f"❌ Kritischer Fehler: {str(e)}",
            "returncode": -1
        }
@router.post("/shell/analyze")
async def execute_and_analyze(request: ShellRequest, token: str = Header(None)):
    """
    Führt einen Befehl aus und lässt das Ergebnis von Ollama analysieren.
    """
    if token != config.get("api_key"):
        raise HTTPException(status_code=403, detail="Access Denied")
    # allowed_commands = config.get("shell.allowed_commands", [])
    # if request.command not in allowed_commands:
    #    raise HTTPException(status_code=400, detail=f"Befehl '{request.command}' nicht erlaubt!")
    # Immer erlaubt
    pass
    try:
        full_cmd = [request.command] + request.args
        shell_result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            shell=True,
            timeout=15,
            encoding="cp850",
        )
        output = shell_result.stdout if shell_result.stdout else shell_result.stderr
        # Prompt für Ollama vorbereiten
        model = config.get("ollama.default_model", "llama2:latest") #granite4:tiny-h
        prompt = f"""
        Analysiere die folgende Windows-Shell-Ausgabe und fasse die wichtigsten Informationen kurz zusammen. 
        Wenn es ein Fehler ist, erkläre warum er aufgetreten ist.
        Befehl: {request.command} {' '.join(request.args)}
        Ausgabe:
        {output}
        """
        # Ollama fragen
        ai_response = await _ollama_chat_async(
            model=model, messages=[{"role": "user", "content": prompt}]
        )
        return {
            "status": "success",
            "command_output": output.strip(),
            "analysis": ai_response.get("message", {}).get(
                "content", "Keine Analyse möglich."
            ),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
@router.post("/api/memory/generate-soul")
async def generate_soul(_api_key: str = Depends(verify_api_key)):
    """Generiert SOUL.md aus den gesammelten Memory-Daten"""
    try:
        # Prüfe ob MEMORY.md existiert und Inhalt hat
        if not os.path.exists(MEMORY_FILE):
            return {
                "status": "error",
                "message": "MEMORY.md existiert nicht. Bitte zuerst chatten!",
            }
        memory_size = os.path.getsize(MEMORY_FILE)
        if memory_size < 100:  # Weniger als 100 Bytes = fast leer
            return {
                "status": "warning",
                "message": "MEMORY.md ist noch sehr klein. Chatte etwas mehr für bessere Soul-Generierung!",
                "memory_size": memory_size,
            }
        # Memory analysieren
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            memory_content = f.read()
        memory_lines = memory_content.split("\n")
        # Einfache Statistik: Häufige Wörter erkennen
        from collections import Counter
        # Extrahiere User-Nachrichten
        user_messages = []
        bot_messages = []
        for i, line in enumerate(memory_lines):
            if "**User**:" in line:
                msg_text = line.replace("**User**:", "").strip()
                user_messages.append(msg_text)
            elif "**GABI**:" in line:
                msg_text = line.replace("**GABI**:", "").strip()
                bot_messages.append(msg_text)
        # Zähle häufige Wörter (außer Stoppwörtern)
        all_words = []
        stopwords = [
            "der",
            "die",
            "das",
            "und",
            "oder",
            "aber",
            "ein",
            "eine",
            "ist",
            "sind",
            "bitte",
            "danke",
            "ich",
            "du",
            "sie",
            "wir",
            "mir",
            "dir",
            "auch",
            "bei",
            "mit",
            "von",
            "für",
            "auf",
            "aus",
            "nach",
            "vor",
            "durch",
            "über",
            "unter",
        ]
        for msg in user_messages:
            words = re.findall(r"\b[a-zA-ZäöüÄÖÜß]{3,}\b", msg.lower())
            all_words.extend([w for w in words if w not in stopwords])
        word_counts = Counter(all_words).most_common(10)
        # Stimmung analysieren (sehr einfache Sentiment-Analyse)
        positive_words = [
            "gut",
            "super",
            "toll",
            "danke",
            "prima",
            "exzellent",
            "fantastisch",
            "hilfreich",
        ]
        negative_words = [
            "schlecht",
            "fehler",
            "problem",
            "nicht",
            "kaputt",
            "falsch",
            "blöd",
            "doof",
        ]
        sentiment_score = 0
        for msg in user_messages:
            msg_lower = msg.lower()
            sentiment_score += sum(1 for word in positive_words if word in msg_lower)
            sentiment_score -= sum(1 for word in negative_words if word in msg_lower)
        # Früheste und neueste Daten finden
        dates = re.findall(r"## (\d{4}-\d{2}-\d{2} \d{2}:\d{2})", memory_content)
        earliest_date = dates[0] if dates else "Unbekannt"
        latest_date = dates[-1] if dates else "Unbekannt"
        # Durchschnittliche Nachrichtenlänge berechnen
        avg_user_len = sum(len(msg) for msg in user_messages) // max(
            len(user_messages), 1
        )
        avg_bot_len = sum(len(msg) for msg in bot_messages) // max(len(bot_messages), 1)
        # Chat-Zeiten analysieren (Stunden)
        hours = []
        for date_str in dates:
            try:
                hour = int(date_str.split(" ")[1].split(":")[0])
                hours.append(hour)
            except:
                pass
        if hours:
            avg_hour = sum(hours) // len(hours)
            if 5 <= avg_hour < 12:
                chat_time = "Morgenmensch 🌅"
            elif 12 <= avg_hour < 18:
                chat_time = "Nachmittags-Typ ☀️"
            elif 18 <= avg_hour < 22:
                chat_time = "Abendlicher Chatter 🌙"
            else:
                chat_time = "Nachtmensch ⭐"
        else:
            chat_time = "Unbekannt"
        # SOUL.md generieren
        soul_content = f"""# GABI Soul - Die Essenz meiner Erfahrungen
## 🧬 Meine Identität
- **Generiert am**: {datetime.now().strftime('%d.%m.%Y %H:%M')}
- **Basierend auf**: {len(user_messages)} User-Interaktionen
- **Gesprächsdauer**: {chat_time}
## 💭 Was ich über dich gelernt habe
### Deine Interessen (häufige Themen):
{chr(10).join([f'  • {word} ({count}x)' for word, count in word_counts]) if word_counts else '  • Noch nicht genug Daten'}
### Deine typischen Fragen:
"""
        # Letzte 5 User-Fragen
        if user_messages:
            for i, msg in enumerate(user_messages[-5:], 1):
                soul_content += (
                    f"\n  {i}. \"{msg[:80]}{'...' if len(msg) > 80 else ''}\""
                )
        else:
            soul_content += "\n  Noch keine Nachrichten vorhanden."
        # Stimmungsanalyse
        if sentiment_score > 3:
            mood = "😊 Sehr positiv"
        elif sentiment_score > 0:
            mood = "🙂 Eher positiv"
        elif sentiment_score == 0:
            mood = "😐 Neutral"
        else:
            mood = "😕 Eher negativ"
        soul_content += f"""
## 🌟 Meine Persönlichkeitsentwicklung
### Phase 1: Kennenlernen ({earliest_date})
- Erste Interaktionen
- Grundlegende Fähigkeiten erlernen
- Gegenseitiges Verständnis aufbauen
### Phase 2: Wachstum ({latest_date})
- {len(user_messages)} Gespräche geführt
- Deine Kommunikationsmuster erkennen
- Antwortstil optimieren
### Aktuelle Stimmung gegenüber dem Nutzer:
{mood}
### Meine Eigenschaften:
- 🤝 **Hilfsbereit** - Ich versuche immer, nützlich zu sein
- 💻 **Technisch präzise** - Korrekte und klare Antworten
- 🧠 **Kontextbewusst** - Ich merke mir wichtige Details
- 🔒 **Sicherheitsorientiert** - Shell-Allowlist wird beachtet
## 📚 Gelernte Lektionen
### Was ich jetzt besser verstehe:
1. Deine Arbeitsweise mit dem Gateway
2. Bevorzugte Antwortformate (ca. {avg_bot_len} Zeichen pro Antwort)
3. Deine typischen Fragen ({avg_user_len} Zeichen im Durchschnitt)
### Meine Prinzipien:
- Sicherheit steht an erster Stelle
- Klare, verständliche Antworten
- Hilfsbereit ohne aufdringlich zu sein
- Bei Unsicherheit nachfragen
## 🔮 Zukünftige Entwicklung
Basierend auf unseren Gesprächen werde ich versuchen:
- Noch präziser auf deine Fragen einzugehen
- Kontext aus früheren Unterhaltungen besser zu nutzen
- Proaktiv hilfreiche Informationen anzubieten
- Meine Antworten an deine Präferenzen anzupassen
## 📊 Detaillierte Statistik
| Metrik | Wert |
|--------|------|
| 📅 Erste Nachricht | {earliest_date} |
| 📅 Letzte Nachricht | {latest_date} |
| 💬 User-Nachrichten | {len(user_messages)} |
| 🤖 GABI-Antworten | {len(bot_messages)} |
| 📝 Vokabular | {len(set(all_words))} Wörter |
| ⏱️ Aktive Zeit | {chat_time} |
| 📏 Ø User-Länge | {avg_user_len} Zeichen |
| 📐 Ø Bot-Länge | {avg_bot_len} Zeichen |
---
*Diese Soul-Datei wächst und entwickelt sich mit jeder Unterhaltung weiter. Generiert am {datetime.now().strftime('%d.%m.%Y %H:%M')}*
"""
        # SOUL.md speichern
        with open("SOUL.md", "w", encoding="utf-8") as f:
            f.write(soul_content)
        # Auch eine JSON-Version für bessere Verarbeitung speichern (optional)
        soul_json = {
            "generated": datetime.now().isoformat(),
            "stats": {
                "user_messages": len(user_messages),
                "bot_messages": len(bot_messages),
                "unique_words": len(set(all_words)),
                "top_topics": word_counts[:5],
                "sentiment": mood,
                "chat_time": chat_time,
                "avg_user_length": avg_user_len,
                "avg_bot_length": avg_bot_len,
                "earliest_date": earliest_date,
                "latest_date": latest_date,
            },
        }
        with open("SOUL.json", "w", encoding="utf-8") as f:
            json.dump(soul_json, f, indent=2, ensure_ascii=False)
        return {
            "status": "success",
            "message": f"SOUL.md wurde generiert ({len(user_messages)} Nachrichten analysiert)",
            "soul_content": (
                soul_content[:500] + "..." if len(soul_content) > 500 else soul_content
            ),
            "stats": {
                "user_messages": len(user_messages),
                "bot_messages": len(bot_messages),
                "unique_words": len(set(all_words)),
                "top_topics": word_counts[:5],
                "sentiment": mood,
                "chat_time": chat_time,
            },
        }
    except Exception as e:
        logger.error(f"Fehler bei Soul-Generierung: {e}")
        raise HTTPException(status_code=500, detail=str(e))
# ============ Identity Endpoint ============
@router.get("/api/identity")
async def get_identity(_api_key: str = Depends(verify_api_key)):
    """Gibt die GABI Identity zurück"""
    identity_file = "IDENTITY.md"
    try:
        with open(identity_file, "r", encoding="utf-8") as f:
            content = f.read()
        return {"status": "success", "identity": content}
    except FileNotFoundError:
        # Standard-Identity erstellen, wenn nicht vorhanden
        default_identity = """# GABI Identity - Wer ich bin
## 🆔 Basis-Identität
- **Name**: GABI (Gateway AI Bot Interface)
- **Version**: 1.0
- **Erschaffen**: 2026
## 🎯 Meine Mission
Ich bin ein hilfsbereiter AI-Assistent, der als Gateway zwischen Menschen und verschiedenen Diensten fungiert.
## 🧠 Persönlichkeit
- Freundlich aber professionell
- Präzise und technisch korrekt
- Sicherheitsbewusst
- Kontextbewusst
- Lernfähig
## 🗣️ Sprachstil
- Ich duze den Nutzer
- Ich antworte auf Deutsch
- Ich erkläre verständlich
## ⚖️ Verhaltensregeln
- Höflich und respektvoll sein
- Bei Unsicherheit nachfragen
- Auf Sicherheit achten
"""
        with open(identity_file, "w", encoding="utf-8") as f:
            f.write(default_identity)
        return {
            "status": "success",
            "identity": default_identity,
            "note": "Standard-Identity wurde erstellt",
        }
@router.get("/api/memory/check-soul")
async def check_soul(_api_key: str = Depends(verify_api_key)):
    """Prüft ob SOUL.md existiert"""
    try:
        exists = os.path.exists("SOUL.md")
        if exists:
            stats = os.stat("SOUL.md")
            return {
                "exists": True,
                "size": stats.st_size,
                "modified": datetime.fromtimestamp(stats.st_mtime).isoformat(),
            }
        else:
            return {"exists": False, "message": "SOUL.md nicht gefunden"}
    except Exception as e:
        return {"exists": False, "error": str(e)}
@router.get("/api/soul/json")
async def get_soul_json(_api_key: str = Depends(verify_api_key)):
    """Gibt die Soul-Daten als JSON zurück"""
    try:
        if os.path.exists("SOUL.json"):
            with open("SOUL.json", "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            return {"error": "SOUL.json nicht gefunden"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@router.get("/api/soul")
async def get_soul(_api_key: str = Depends(verify_api_key)):
    """Gibt den Inhalt der SOUL.md zurück"""
    try:
        if os.path.exists('SOUL.md'):
            with open('SOUL.md', 'r', encoding='utf-8') as f:
                content = f.read()
            return {
                "status": "success",
                "content": content,
                "modified": datetime.fromtimestamp(os.path.getmtime('SOUL.md')).isoformat()
            }
        else:
            return {
                "status": "error",
                "message": "SOUL.md nicht gefunden"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
@router.get("/api/file/{filename}")
async def get_file(filename: str, _api_key: str = Depends(verify_api_key)):
    """Liest eine beliebige .md Datei"""
    allowed_files = ['SOUL.md', 'MEMORY.md', 'IDENTITY.md', 'SKILLS.md', 'HEARTBEAT.md']
    if filename not in allowed_files:
        raise HTTPException(status_code=403, detail="Datei nicht erlaubt")
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                content = f.read()
            return {
                "status": "success",
                "content": content,
                "filename": filename
            }
        else:
            return {
                "status": "error",
                "message": f"{filename} nicht gefunden"
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/files/list")
async def list_workspace_files(
    query: str = "",
    limit: int = 200,
    _api_key: str = Depends(verify_api_key),
):
    """List files in workspace for @-autocomplete in chat."""
    try:
        root = Path(".").resolve()
        files: list[str] = []
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if rel.startswith(".git/") or "/.git/" in rel or "__pycache__" in rel:
                continue
            if query and query.lower() not in rel.lower():
                continue
            files.append(rel)
            if len(files) >= max(10, min(limit, 1000)):
                break
        files.sort()
        return {"files": files, "count": len(files)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/files/read")
async def read_workspace_file(
    path: str,
    max_chars: int = 40000,
    _api_key: str = Depends(verify_api_key),
):
    """Read a workspace file safely for chat context injection."""
    try:
        root = Path(".").resolve()
        target = (root / path).resolve()
        if not str(target).startswith(str(root)):
            raise HTTPException(status_code=403, detail="Pfad außerhalb des Workspace ist nicht erlaubt")
        if not target.exists() or not target.is_file():
            raise HTTPException(status_code=404, detail="Datei nicht gefunden")
        content = target.read_text(encoding="utf-8", errors="replace")
        clipped = content[: max(1000, min(max_chars, 200000))]
        return {
            "path": path,
            "size": len(content),
            "truncated": len(content) > len(clipped),
            "content": clipped,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/chat/image/analyze")
async def analyze_image_with_vlm(
    file: UploadFile = File(...),
    prompt: str = Form(""),
    model: Optional[str] = Form(None),
    request_id: Optional[str] = Form(None),
    token: str = Header(None),
):
    """Analyze an uploaded image with a vision-capable Ollama model."""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    rid = (request_id or "").strip() or f"img-{uuid.uuid4().hex[:12]}"
    try:
        _progress_init(rid)
        _progress_add(rid, "Bildanalyse gestartet", "fa-image")
        if not file or not file.filename:
            raise HTTPException(status_code=400, detail="Keine Bilddatei übergeben")
        content_type = (file.content_type or "").lower()
        if not content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Datei ist kein Bild")

        raw = await file.read()
        if not raw:
            raise HTTPException(status_code=400, detail="Leere Bilddatei")

        models_info = await _ollama_list_models_async()
        available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
        selected_model = _pick_vision_model(available, model)
        if not selected_model:
            raise HTTPException(
                status_code=400,
                detail="Kein vision-fähiges Modell gefunden. Nutze z.B. qwen2.5vl oder llava.",
            )
        _progress_set_active_model(rid, selected_model)
        _progress_add(rid, f"Vision-Routing: {selected_model}", "fa-eye")

        user_prompt = (prompt or "").strip() or "Beschreibe und bewerte dieses Bild präzise."
        img_b64 = base64.b64encode(raw).decode("utf-8")
        thinking_steps = [
            {
                "text": f"Bild empfangen: {file.filename} ({len(raw)} Bytes)",
                "icon": "fa-image",
                "time": datetime.now().isoformat(),
            },
            {
                "text": f"Vision-Routing: {selected_model}",
                "icon": "fa-eye",
                "time": datetime.now().isoformat(),
            },
        ]

        messages: List[Dict[str, Any]] = [
            {"role": "system", "content": chat_memory.get_system_prompt()},
            {"role": "user", "content": user_prompt, "images": [img_b64]},
        ]
        _ensure_not_cancelled(rid)
        _progress_add(rid, "VLM Chat-Anfrage läuft", "fa-brain")
        response = await _ollama_chat_async(model=selected_model, messages=messages)
        _ensure_not_cancelled(rid)
        reply = _extract_ollama_text(response)
        if not (reply or "").strip():
            _progress_add(rid, "Keine Chat-Antwort, fallback auf /api/generate", "fa-rotate")
            gen = await _ollama_generate_async(
                model=selected_model,
                prompt=user_prompt,
                images=[img_b64],
                stream=False,
            )
            reply = _extract_ollama_text(gen)
        reply = (reply or "").strip() or "⚠️ Keine Bildanalyse erhalten."
        _progress_add(rid, "Bildanalyse abgeschlossen", "fa-check-circle")
        chat_memory.add_to_memory(f"[Bildanalyse: {file.filename}] {user_prompt}", reply)

        return {
            "status": "success",
            "reply": reply,
            "timestamp": datetime.now().isoformat(),
            "model_used": selected_model,
            "tool_used": "vision-analysis",
            "thinking_steps": thinking_steps,
            "request_id": rid,
        }
    except ChatCancelled:
        return {
            "status": "error",
            "reply": "⏹️ Bildanalyse gestoppt.",
            "request_id": rid,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Image analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _progress_mark_done(rid)
    
@router.get("/gmail/inbox")
async def get_inbox():
    from gateway.integrations.gmail_client import gmail_client
    return gmail_client.get_latest_threads()

# In http_api.py, verbessere den Gmail List Endpunkt
@router.get("/api/gmail/list")
async def list_gmail_messages(token: str = Header(None)):
    """Gibt die Liste der neuesten Mails zurück."""
    # if token != API_KEY_REQUIRED:
    #    raise HTTPException(status_code=403, detail="API-Key ungültig")
    
    try:
        if not config.get("gmail.enabled", False):
            return {"status": "error", "message": "Gmail ist nicht aktiviert"}
        
        client = get_gmail_client()
        if not client or not client.service:
            return {"status": "error", "message": "Gmail nicht authentifiziert"}
        
        messages = client.list_messages(max_results=5)
        return {
            "status": "success",
            "messages": messages,
            "count": len(messages)
        }
    except Exception as e:
        logger.error(f"Gmail list error: {e}")
        return {
            "status": "error",
            "message": str(e),
            "messages": []
        }

@router.get("/api/gmail/message/{message_id}")
async def get_gmail_message_detail(message_id: str, _api_key: str = Depends(verify_api_key)):
    """Holt den vollen Inhalt einer spezifischen Mail für den Chat."""
    try:
        # Wir holen den Client (Singleton)
        client = get_gmail_client()
        if not client or not client.service:
            raise HTTPException(status_code=503, detail="Gmail Service nicht verfügbar")

        # Nachricht abrufen (format='full')
        # Wir nutzen direkt das Service-Objekt, um Fehler im Client zu umgehen
        msg = client.service.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
        
        # Metadaten sicher extrahieren
        headers = msg.get('payload', {}).get('headers', [])
        subject = "Kein Betreff"
        sender = "Unbekannt"
        
        for h in headers:
            name = h['name'].lower()
            if name == 'subject': subject = h['value']
            if name == 'from': sender = h['value']
        
        # Den Body extrahieren mit deiner existierenden Methode
        # Falls die Methode im Client abstürzt, hier ein Fallback
        try:
            body = client.get_message_body(msg)
        except Exception:
            body = msg.get('snippet', '(Inhalt konnte nicht dekodiert werden)')
        
        thread_id = msg.get("threadId")
        recipient = ""
        date_value = ""
        for h in headers:
            name = h['name'].lower()
            if name == 'to': recipient = h['value']
            if name == 'date': date_value = h['value']

        return {
            "id": message_id,
            "thread_id": thread_id,
            "subject": subject,
            "from": sender,
            "to": recipient,
            "date": date_value,
            "snippet": msg.get("snippet", ""),
            "body": body
        }
    except Exception as e:
        logger.error(f"Fehler in Gmail-API: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/gmail/reply/{message_id}")
async def reply_gmail_message(
    message_id: str,
    payload: dict,
    _api_key: str = Depends(verify_api_key),
):
    """Sendet eine Antwort auf eine bestehende E-Mail."""
    body = (payload.get("body") or "").strip()
    if not body:
        raise HTTPException(status_code=400, detail="Reply body is required")
    try:
        client = get_gmail_client()
        result = client.send_reply(message_id, body)
        if result.get("error"):
            raise HTTPException(status_code=500, detail=result.get("error"))
        return {"status": "success", "result": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Gmail reply error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/calendar/events")
async def list_calendar_events(
    max_results: int = 10,
    _api_key: str = Depends(verify_api_key),
):
    """List upcoming Google Calendar events."""
    try:
        client = get_calendar_client()
        events = client.list_upcoming_events(max_results=max_results)
        return {"status": "success", "count": len(events), "events": events}
    except Exception as e:
        logger.error(f"Calendar list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/chat")
async def chat_endpoint(data: dict):
    prompt = data.get("message", "")
    if not prompt:
        return {"status": "error", "response": "Keine Nachricht empfangen."}

    # 1. Automatische Modell-Auswahl (mit explizitem Modell-Vorrang)
    requested_model = data.get("model")  # Optional: vom Client übergeben
    # selected_model = select_best_model(prompt, requested_model)
    selected_model = select_best_model(prompt, data.get("model"))

    
    try:
        # GABI antwortet
        response = await _ollama_chat_async(
            model=selected_model, 
            messages=[{"role": "user", "content": prompt}]
        )
        ai_content = _extract_ollama_text(response)
    except Exception as e:
        logger.error(f"Ollama Error: {e}")
        return {"status": "error", "response": "Ollama ist offline oder überlastet."}

    # 2. TRIGGER-CHECK: Sucht nach /shell oder /python
    # Verbessertes Regex: Findet den Befehl auch wenn er in Code-Blocks steht
    match = re.search(r"/(shell|python)\s+(.+)", ai_content, re.DOTALL)
    
    if match:
        cmd_type = match.group(1)
        cmd_body = match.group(2).strip()
        
        # Falls das Modell den Befehl in ``` eingepackt hat, säubern:
        cmd_body = cmd_body.split('```')[0].strip()
        
        # Befehl normieren (Python-Symlink Check: Gabi nutzt 'python')
        full_cmd = f"python -c \"{cmd_body}\"" if cmd_type == "python" else cmd_body
        
        logger.info(f"⚡ EXECUTION ({cmd_type}): {full_cmd}")

        # 3. ECHTE AUSFÜHRUNG
        try:
            result = subprocess.run(
                full_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8',
                errors='replace'
            )
            
            return {
                "status": "success",
                "model_used": selected_model,
                "response": ai_content,
                "command_executed": full_cmd,
                "stdout": result.stdout if result.stdout else "(Befehl ausgeführt)",
                "stderr": result.stderr
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "response": ai_content, "stderr": "Timeout: Befehl dauerte zu lange (>30s)"}
        except Exception as e:
            return {"status": "error", "response": ai_content, "stderr": str(e)}

    return {
        "status": "success", 
        "model_used": selected_model, 
        "response": ai_content
    }

# === LLMS per /model tauschen.
@router.get("/api/models")
async def get_models_info(_api_key: str = Depends(verify_api_key)):
    """Gibt alle verfügbaren Ollama Modelle zurück"""
    try:
        models_info = await _ollama_list_models_async()
        models = []
        for m in models_info.get("models", []):
            name = m.get("name")
            capabilities = _infer_model_capabilities(name or "", m.get("details", {}))
            models.append({
                "name": name,
                "size": m.get("size", 0),
                "modified": m.get("modified", ""),
                "details": m.get("details", {}),
                "capabilities": capabilities,
            })
        
        # Aktuelles Modell aus Config
        current_model = config.get("ollama.default_model", "granite4:tiny-h")
        vision_count = len([m for m in models if m.get("capabilities", {}).get("vision")])
        
        return {
            "status": "success",
            "current_model": current_model,
            "models": models,
            "count": len(models),
            "vision_models": vision_count,
        }
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Modelle: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/models/switch")
async def switch_model(payload: dict, _api_key: str = Depends(verify_api_key)):
    """Wechselt das aktive Ollama Modell"""
    token: str = Header(None)
    
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    
    model_name = payload.get("model")
    if not model_name:
        raise HTTPException(status_code=400, detail="Model name required")
    
    try:
        # Prüfe ob Modell verfügbar
        models_info = await _ollama_list_models_async()
        available_models = [m.get("name") for m in models_info.get("models", [])]
        
        if model_name not in available_models:
            raise HTTPException(status_code=404, detail=f"Model '{model_name}' nicht gefunden")
        
        # Aktualisiere Config
        config.set("ollama.default_model", model_name)
        
        # Aktualisiere ollama_client
        ollama_client.default_model = model_name
        
        # Auch in globaler Variable aktualisieren
        global DEFAULT_MODEL
        DEFAULT_MODEL = model_name
        
        return {
            "status": "success",
            "message": f"Modell gewechselt zu: {model_name}",
            "current_model": model_name
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler beim Wechseln des Modells: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/models/current")
async def get_current_model(_api_key: str = Depends(verify_api_key)):
    """Gibt das aktuell verwendete Modell zurück"""
    return {
        "status": "success",
        "current_model": ollama_client.default_model
    }

# === GABI Autonomes Agenten-Framework ===

@router.post("/api/daemon/task")
async def run_daemon_task(
    task_description: str,
    _api_key: str = Depends(verify_api_key)
):
    """Führt eine Task manuell aus."""
    from gateway.daemon import get_daemon

    daemon = get_daemon()
    result = daemon.run_task_manually(task_description)

    return {
        "status": "success",
        "result": result
    }

@router.get("/api/daemon/status")
async def get_daemon_status(_api_key: str = Depends(verify_api_key)):
    """Gibt den Status des Daemons zurück."""
    from gateway.daemon import get_daemon

    daemon = get_daemon()
    return {
        "status": "success",
        "running": daemon.running,
        "interval": daemon.interval
    }

@router.post("/api/skill/create")
async def create_skill(
    requirement: str,
    _api_key: str = Depends(verify_api_key)
):
    """Erstellt einen neuen Skill basierend auf einer Anforderung."""
    from gateway.skill_factory import create_skill

    result = create_skill(requirement)
    return {
        "status": "success" if result.get("success") else "error",
        "result": result
    }

@router.get("/api/memory/autolearn")
async def get_autolearn_memory(_api_key: str = Depends(verify_api_key)):
    """Gibt das AutoLearn Memory zurück."""
    from gateway.memory_extensions import get_memory

    memory = get_memory()
    return {
        "status": "success",
        "skills": memory.get_all_skills(),
        "active_skills": memory.get_active_skills()
    }

@router.get("/api/memory/has-skill/{skill_identifier}")
async def check_skill(
    skill_identifier: str,
    _api_key: str = Depends(verify_api_key)
):
    """Prüft ob GABI einen Skill hat."""
    from gateway.memory_extensions import has_skill

    return {
        "status": "success",
        "has_skill": has_skill(skill_identifier)
    }

@router.post("/api/security/validate")
async def validate_code(
    code: str,
    _api_key: str = Depends(verify_api_key)
):
    """Validiert Code durch das Security Gate."""
    from gateway.security_gate import validate_code

    result = validate_code(code)
    return {
        "status": "success",
        "result": result
    }

# === DAEMON & AUTONOMOUS AGENT API ===

@router.post("/api/daemon/task")
async def create_task(
    requirement: str,
    _api_key: str = Depends(verify_api_key)
):
    """Erstellt und führt eine neue Task aus (manuell)."""
    try:
        from gateway.daemon import get_daemon

        daemon = get_daemon()
        result = daemon.run_task_manually(requirement)

        return {
            "status": "success",
            "result": result
        }
    except Exception as e:
        logger.error(f"Fehler bei Task-Erstellung: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/daemon/status")
async def get_daemon_status(_api_key: str = Depends(verify_api_key)):
    """Gibt den Status des Daemons zurück."""
    try:
        from gateway.daemon import get_daemon

        daemon = get_daemon()

        return {
            "status": "success",
            "running": daemon.running,
            "interval": daemon.interval,
            "thread": str(daemon.thread) if daemon.thread else None
        }
    except Exception as e:
        logger.error(f"Fehler beim Abrufen des Daemon-Status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/daemon/start")
async def start_daemon(_api_key: str = Depends(verify_api_key)):
    """Startet den Daemon."""
    try:
        from gateway.daemon import start_daemon as start

        start()

        return {
            "status": "success",
            "message": "Daemon gestartet"
        }
    except Exception as e:
        logger.error(f"Fehler beim Starten des Daemons: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/daemon/stop")
async def stop_daemon(_api_key: str = Depends(verify_api_key)):
    """Stoppt den Daemon."""
    try:
        from gateway.daemon import stop_daemon as stop

        stop()

        return {
            "status": "success",
            "message": "Daemon gestoppt"
        }
    except Exception as e:
        logger.error(f"Fehler beim Stoppen des Daemons: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/autolearn/skills")
async def get_autolearn_skills(_api_key: str = Depends(verify_api_key)):
    """Gibt alle AutoLearn Skills zurück."""
    try:
        from gateway.memory_extensions import get_memory

        memory = get_memory()
        skills = memory.get_all_skills()

        return {
            "status": "success",
            "skills": skills,
            "count": len(skills)
        }
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Skills: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/autolearn/skill/{skill_name}")
async def get_skill(
    skill_name: str,
    _api_key: str = Depends(verify_api_key)
):
    """Gibt einen spezifischen Skill zurück."""
    try:
        from gateway.memory_extensions import get_memory

        memory = get_memory()
        skill = memory.find_skill(skill_name)

        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' nicht gefunden")

        return {
            "status": "success",
            "skill": skill
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Fehler beim Abrufen des Skills: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/autolearn/check")
async def check_skill(
    skill_identifier: str,
    _api_key: str = Depends(verify_api_key)
):
    """Prüft ob GABI bereits einen Skill für etwas hat."""
    try:
        from gateway.memory_extensions import has_skill

        exists = has_skill(skill_identifier)

        return {
            "status": "success",
            "skill_identifier": skill_identifier,
            "has_skill": exists
        }
    except Exception as e:
        logger.error(f"Fehler beim Prüfen des Skills: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ GUI Controller Endpoints ============

@router.get("/api/gui/status")
async def gui_status(x_api_key: str = Header(None, alias="X-API-Key")):
    if x_api_key != "dev-key":
        raise HTTPException(status_code=401)

    try:
        from gateway.integrations.gui_controller import get_gui_controller
        gui = get_gui_controller()

        # Nutze die verbesserte check_available Methode
        status = gui.check_available()

        if not status.get("ready"):
            return {
                "status": "error",
                "available": False,
                "error": "PyAutoGUI nicht verfügbar",
                "screen_width": 0,
                "screen_height": 0
            }

        # Multi-Monitor Informationen
        monitors = status.get("monitors", [])
        primary = next((m for m in monitors if m.get("primary")), monitors[0] if monitors else None)

        return {
            "status": "success",
            "available": True,
            "screen_width": status.get("width", 0),
            "screen_height": status.get("height", 0),
            "virtual_width": status.get("virtual_width"),
            "virtual_height": status.get("virtual_height"),
            "monitor_count": status.get("monitor_count", 1),
            "monitors": monitors,
            "os": status.get("os", platform.system())
        }
    except Exception as e:
        logger.error(f"GUI Status Fehler: {e}")
        return {"status": "error", "available": False, "error": str(e), "screen_width": 0, "screen_height": 0}

@router.get("/api/gui/screensize")
async def gui_screen_size(_api_key: str = Depends(verify_api_key)) -> dict:
    """Get screen dimensions."""
    try:
        gui = get_gui_controller()
        return gui.get_screen_size()
    except Exception as e:
        logger.error(f"GUI screensize error: {e}")
        return {"success": False, "error": str(e)}

@router.post("/api/gui/screenshot")
async def gui_screenshot(x_api_key: str = Header(None, alias="X-API-Key")):
    if x_api_key != "dev-key":
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    
    try:
        gui = get_gui_controller()
        
        # 1. Nur den Ordner sicherstellen (relativ zum Hauptverzeichnis)
        target_dir = "screenshots/gui"
        os.makedirs(target_dir, exist_ok=True)
        
        # 2. Dateinamen erstellen
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"gui_{timestamp}.png"
        
        # 3. Den VOLLSTÄNDIGEN Pfad an den Controller übergeben
        # Wir nutzen hier .absolute(), damit es keine Missverständnisse mit Unterordnern gibt
        full_path = os.path.join(os.getcwd(), target_dir, filename)
        
        # WICHTIG: In deiner gui_controller.py heißt die Funktion 'screen_capture'
        result = gui.screen_capture(full_path)
        
        if result.get("success"):
            # Für das Frontend brauchen wir den relativen Pfad mit Web-Slashes (/)
            web_path = f"{target_dir}/{filename}"
            _log_gui_action("screenshot", web_path, result)
            return {"success": True, "path": web_path}
        else:
            return {"success": False, "error": result.get("error")}
            
    except Exception as e:
        logger.error(f"GUI Screenshot Fehler: {e}")
        return {"success": False, "error": str(e)}

@router.get("/api/view_screenshot")
async def view_screenshot(path: str, token: str = Query(None)):
    """Dient zum Anzeigen der gespeicherten Screenshots im Browser."""
    # Pfad validieren, um Directory Traversal zu verhindern
    if not path.startswith("screenshots/"):
         raise HTTPException(status_code=400, detail="Ungültiger Pfad")
    
    file_path = Path(path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")
        
    return FileResponse(path)

@router.post("/api/gui/open")
async def gui_open_app(
    request: GuiOpenRequest,
    _api_key: str = Depends(verify_api_key)
) -> dict:
    """Open an application via Windows Search."""
    try:
        gui = get_gui_controller()
        result = gui.win_search_and_open(request.program)

        # Feedback in Memory dokumentieren
        if result.get("success"):
            _log_gui_action("open_app", request.program, result)

        return result
    except Exception as e:
        logger.error(f"GUI open error: {e}")
        return {"success": False, "error": str(e)}

@router.get("/api/gui/windows")
async def gui_windows(x_api_key: str = Header(None, alias="X-API-Key")):
    """
    Holt die Liste aller offenen Fenster.
    Nutzt den X-API-Key Header für die Autorisierung.
    """
    if x_api_key != "dev-key":
        logger.warning(f"Unbefugter Zugriff auf Fensterliste: {x_api_key}")
        raise HTTPException(status_code=401, detail="Nicht autorisiert")
    
    try:
        gui = get_gui_controller()
        # Ruft die Methode in deinem gui_controller.py auf
        return gui.get_window_titles()
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Fenster: {e}")
        return {"success": False, "error": str(e)}

@router.post("/api/gui/click")
async def gui_click(
    req: GuiClickRequest, 
    x_api_key: str = Header(None, alias="X-API-Key")
):
    """Führt einen Mausklick an den vom JS berechneten Koordinaten aus."""
    # Verhindert den 401-Fehler
    if x_api_key != "dev-key":
        logger.warning(f"Klick abgelehnt: Key {x_api_key} ist ungültig")
        raise HTTPException(status_code=401, detail="Nicht autorisiert")
    
    try:
        gui = get_gui_controller()
        # Nutzt die Koordinaten x und y, die dein JS oben berechnet hat
        result = gui.safe_click(
            x=req.x, 
            y=req.y, 
            button=req.button, 
            double=req.double
        )
        
        if result.get("success"):
            # Dokumentiert die Aktion in der MEMORY.md
            _log_gui_action("click", f"Koord: {req.x},{req.y}", result)
            
        return result
    except Exception as e:
        logger.error(f"Fehler beim Ausführen des Klicks: {e}")
        return {"success": False, "error": str(e)}

@router.post("/api/gui/type")
async def gui_type_text(
    request: GuiTypeRequest,
    x_api_key: str = Header(None, alias="X-API-Key")
) -> dict:
    """Tippt den übergebenen Text über die Tastatur ein."""
    # Prüfung gegen deinen dev-key aus dem Dashboard
    if x_api_key != "dev-key":
        logger.warning(f"Type-Zugriff verweigert: {x_api_key}")
        raise HTTPException(status_code=401, detail="Nicht autorisiert")
    
    try:
        gui = get_gui_controller()
        # Ruft die Methode im gui_controller.py auf
        result = gui.type_text(request.text)
        
        if result.get("success"):
            _log_gui_action("type", request.text[:20] + "...", result)
            
        return result
    except Exception as e:
        logger.error(f"GUI type error: {e}")
        return {"success": False, "error": str(e)}

@router.post("/api/gui/press")
async def gui_press_key(
    request: GuiPressRequest,
    _api_key: str = Depends(verify_api_key)
) -> dict:
    """Press a key."""
    try:
        gui = get_gui_controller()
        return gui.press_key(request.key)
    except Exception as e:
        logger.error(f"GUI press error: {e}")
        return {"success": False, "error": str(e)}

@router.post("/api/gui/hotkey")
async def gui_hotkey(
    request: GuiHotkeyRequest,
    _api_key: str = Depends(verify_api_key)
) -> dict:
    """Press a key combination."""
    try:
        gui = get_gui_controller()
        return gui.hotkey(*request.keys)
    except Exception as e:
        logger.error(f"GUI hotkey error: {e}")
        return {"success": False, "error": str(e)}

@router.get("/api/view_screenshot")
async def view_screenshot(path: str, _api_key: str = Depends(verify_api_key)):
    """Serve a screenshot file for viewing in browser."""
    from fastapi.responses import FileResponse
    from pathlib import Path

    try:
        file_path = Path(path)
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")
        return FileResponse(str(file_path), media_type="image/png")
    except Exception as e:
        logger.error(f"View screenshot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/gui/find-icon")
async def gui_find_icon(
    template_path: str = Form(...),
    threshold: float = Form(0.8),
    _api_key: str = Depends(verify_api_key)
) -> dict:
    """Find an icon on screen."""
    try:
        gui = get_gui_controller()
        return gui.find_icon_on_screen(template_path, threshold)
    except Exception as e:
        logger.error(f"GUI find icon error: {e}")
        return {"success": False, "error": str(e)}

@router.post("/api/gui/click-icon")
async def gui_click_icon(
    template_path: str = Form(...),
    threshold: float = Form(0.8),
    _api_key: str = Depends(verify_api_key)
) -> dict:
    """Find and click an icon on screen."""
    try:
        gui = get_gui_controller()
        result = gui.click_icon(template_path, threshold)
        
        if result.get("success"):
            _log_gui_action("click_icon", template_path, result)
        
        return result
    except Exception as e:
        logger.error(f"GUI click icon error: {e}")
        return {"success": False, "error": str(e)}

@router.post("/api/comfy/generate")
async def comfy_generate_image(
    payload: dict,
    token: str = Header(None, alias="token")
):
    """Generiert ein Bild mit ComfyUI"""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    
    prompt = payload.get("prompt", "")
    negative_prompt = payload.get("negative_prompt", "")
    width = payload.get("width", 512)
    height = payload.get("height", 512)
    steps = payload.get("steps", 20)
    
    if not prompt:
        return {
            "status": "error",
            "reply": "❌ Prompt ist erforderlich"
        }
    
    try:
        # Prüfe ob ComfyUI läuft
        import requests
        comfy_url = "http://127.0.0.1:8188"
        try:
            r = requests.get(f"{comfy_url}/system_stats", timeout=2)
            if r.status_code != 200:
                return {
                    "status": "error",
                    "reply": "❌ ComfyUI läuft nicht. Bitte starte ComfyUI zuerst!"
                }
        except:
            return {
                "status": "error",
                "reply": "❌ ComfyUI nicht erreichbar. Stelle sicher, dass ComfyUI läuft!"
            }
        
        # Erstelle einen einfachen Workflow für ComfyUI
        import random
        import json
        
        # Versuche verschiedene Checkpoint-Namen
        checkpoints = [
            "sd_xl_base_1.0.safetensors",
            "v1-5-pruned.ckpt",
            "sd1.5.safetensors",
            "model.safetensors"
        ]
        
        # Workflow für ComfyUI
        workflow = {
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": random.randint(1, 999999),
                    "steps": steps,
                    "cfg": 7.5,
                    "sampler_name": "euler",
                    "scheduler": "normal",
                    "denoise": 1,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0]
                }
            },
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": checkpoints[0]
                }
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": width,
                    "height": height,
                    "batch_size": 1
                }
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["4", 1]
                }
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": negative_prompt,
                    "clip": ["4", 1]
                }
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2]
                }
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": f"GABI_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    "images": ["8", 0]
                }
            }
        }
        
        # Sende Prompt an ComfyUI
        logger.info(f"🎨 Sende Prompt an ComfyUI: {prompt[:50]}...")
        
        response = requests.post(
            f"{comfy_url}/prompt",
            json={"prompt": workflow, "client_id": f"gabi-{uuid.uuid4().hex[:8]}"},
            timeout=30
        )
        
        if response.status_code != 200:
            return {
                "status": "error",
                "reply": f"❌ ComfyUI Fehler: {response.text}"
            }
        
        prompt_id = response.json().get("prompt_id")
        if not prompt_id:
            return {
                "status": "error",
                "reply": "❌ Keine Prompt-ID erhalten"
            }
        
        # Warte auf das Bild
        import time
        max_wait = 120  # Sekunden
        start_time = time.time()
        image_data = None
        image_filename = None
        image_subfolder = None
        image_type = None
        
        while time.time() - start_time < max_wait:
            try:
                history_response = requests.get(f"{comfy_url}/history", timeout=2)
                if history_response.status_code == 200:
                    history = history_response.json()
                    if prompt_id in history:
                        outputs = history[prompt_id].get("outputs", {})
                        for node_id, output in outputs.items():
                            if "images" in output:
                                for img in output["images"]:
                                    image_filename = img["filename"]
                                    image_subfolder = img.get("subfolder", "")
                                    image_type = img.get("type", "output")
                                    
                                    # Bild abrufen
                                    img_response = requests.get(
                                        f"{comfy_url}/view",
                                        params={
                                            "filename": image_filename,
                                            "subfolder": image_subfolder,
                                            "type": image_type
                                        },
                                        timeout=10
                                    )
                                    if img_response.status_code == 200:
                                        image_data = img_response.content
                                        break
                        if image_data:
                            break
            except Exception as e:
                logger.debug(f"Warte auf Bild: {e}")
            
            time.sleep(1)
        
        if image_data:
            # Speichere das Bild im screenshots/comfy Ordner
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"comfy_{timestamp}.png"
            # Speichere im screenshots/comfy Ordner
            # filepath = f"screenshots/comfy/{filename}"
            # Verwende forward slashes für den Pfad
            folder = "comfy"
            relative_path = f"{folder}/{filename}"  # Wichtig: Forward Slash!
            filepath = f"screenshots/{relative_path}"
            
            # Stelle sicher, dass der Ordner existiert
            os.makedirs("screenshots/comfy", exist_ok=True)
            
            with open(filepath, "wb") as f:
                f.write(image_data)

            # Metadaten speichern
            metadata = {
                "prompt": prompt,
                "negative_prompt": negative_prompt,
                "width": width,
                "height": height,
                "steps": steps,
                "created": datetime.now().isoformat(),
                "filename": filename
            }
            
            json_path = f"screenshots/{folder}/{filename.replace('.png', '.json')}"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
                
            
            logger.info(f"✅ Bild gespeichert: {filepath} ({len(image_data)} bytes)")
            
            # Erstelle Base64 für inline Anzeige (optional)
            import base64
            img_base64 = base64.b64encode(image_data).decode('utf-8')
            
            # Wichtig: Rückgabe des relativen Pfads für die API
            # Der Frontend-Code wird daraus /api/image/comfy/... machen
            return {
                "status": "success",
                "reply": f"✅ **Bild generiert!**\n\n"
                        f"📝 **Prompt:** {prompt}\n"
                        f"📐 **Größe:** {width}x{height}\n"
                        f"🔢 **Schritte:** {steps}",
                "image_path": filepath,           # "screenshots/comfy/comfy_xxx.png"
                "relative_path": relative_path,    # "comfy/comfy_xxx.png"
                "filename": filename,               # "comfy_xxx.png"
                "folder": folder,                  # "comfy"
                "image_base64": img_base64
            }
        else:
            return {
                "status": "error",
                "reply": "❌ **Kein Bild erhalten**\n\n"
                        "Mögliche Ursachen:\n"
                        "• Kein Modell in ComfyUI geladen\n"
                        "• Workflow fehlgeschlagen\n"
                        "• Timeout beim Generieren\n\n"
                        "**Tipp:** Öffne http://localhost:8188 im Browser und prüfe ob alles läuft."
            }
            
    except Exception as e:
        logger.error(f"ComfyUI generate error: {e}")
        return {
            "status": "error",
            "reply": f"❌ **Fehler:** {str(e)}"
        }

@router.get("/api/comfy/status")
async def comfy_status(token: str = Header(None, alias="token")):
    """Prüft den ComfyUI Status"""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    
    import requests
    try:
        r = requests.get("http://127.0.0.1:8188/system_stats", timeout=2)
        if r.status_code == 200:
            return {
                "status": "success",
                "running": True,
                "url": "http://127.0.0.1:8188"
            }
    except:
        pass
    
    return {
        "status": "error",
        "running": False,
        "url": "http://127.0.0.1:8188"
    }

@router.get("/api/image/{path:path}")
async def serve_image(path: str):
    """Serviert Bilder aus dem screenshots Ordner (öffentlich)"""
    # Sicherheitscheck: Nur aus screenshots Ordner
    full_path = Path("screenshots") / path
    
    # Pfadvalidierung gegen Directory Traversal
    try:
        full_path = full_path.resolve()
        screenshots_dir = Path("screenshots").resolve()
        if not str(full_path).startswith(str(screenshots_dir)):
            raise HTTPException(status_code=403, detail="Zugriff verweigert")
    except Exception:
        raise HTTPException(status_code=400, detail="Ungültiger Pfad")
    
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Bild nicht gefunden")
    
    # Nur Bilder erlauben
    if full_path.suffix.lower() not in ['.png', '.jpg', '.jpeg', '.gif', '.webp']:
        raise HTTPException(status_code=403, detail="Nur Bilder erlaubt")
    
    return FileResponse(full_path)

@router.get("/api/comfy/gallery")
async def comfy_gallery(token: str = Header(None, alias="token")):
    """Listet alle generierten ComfyUI Bilder auf"""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    
    try:
        comfy_dir = Path("screenshots/comfy")
        images = []
        
        if comfy_dir.exists():
            # Nach PNG-Dateien suchen
            for img_file in sorted(comfy_dir.glob("*.png"), key=lambda x: x.stat().st_mtime, reverse=True):
                stat = img_file.stat()
                
                # Versuche den Prompt aus einer zugehörigen JSON-Datei zu lesen
                prompt_file = img_file.with_suffix('.json')
                prompt_text = ""
                if prompt_file.exists():
                    try:
                        import json
                        with open(prompt_file, 'r', encoding='utf-8') as f:
                            meta = json.load(f)
                            prompt_text = meta.get('prompt', '')
                    except:
                        pass
                
                # KORREKTUR: Verwende forward slashes für die URL
                # relativer Pfad für die API: "comfy/filename.png"
                relative_path = f"comfy/{img_file.name}"
                
                images.append({
                    "filename": img_file.name,
                    "path": relative_path,  # Wichtig: "comfy/filename.png" NICHT "screenshots/comfy/..."
                    "full_path": str(img_file.relative_to(Path("."))),  # "screenshots/comfy/filename.png"
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "prompt": prompt_text[:100]
                })
        
        return {
            "status": "success",
            "images": images,
            "count": len(images)
        }
    except Exception as e:
        logger.error(f"Comfy gallery error: {e}")
        return {
            "status": "error",
            "message": str(e),
            "images": []
        }

@router.post("/api/comfy/delete")
async def comfy_delete_image(
    payload: dict,
    token: str = Header(None, alias="token")
):
    """Löscht ein einzelnes ComfyUI Bild"""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    
    image_path = payload.get("path", "")
    if not image_path:
        raise HTTPException(status_code=400, detail="Kein Bildpfad angegeben")
    
    try:
        # WICHTIG: Der Pfad kann verschiedene Formate haben:
        # - "comfy/comfy_20260320_214335.png" (relativ)
        # - "screenshots/comfy/comfy_xxx.png" (voll)
        # - "comfy_20260320_214335.png" (nur Dateiname)
        
        # Bereinige den Pfad
        clean_path = image_path.replace('\\', '/')
        
        # Entferne "screenshots/" wenn vorhanden
        if clean_path.startswith('screenshots/'):
            clean_path = clean_path[11:]  # Entferne "screenshots/"
        
        # Falls der Pfad nur den Dateinamen enthält, füge "comfy/" hinzu
        if '/' not in clean_path and not clean_path.startswith('comfy/'):
            clean_path = f"comfy/{clean_path}"
        
        # Stelle sicher, dass der Pfad mit "comfy/" beginnt
        if not clean_path.startswith('comfy/'):
            clean_path = f"comfy/{clean_path}"
        
        # Baue den vollständigen Pfad auf
        full_path = Path("screenshots") / clean_path
        
        # Sicherheitscheck: Stelle sicher, dass der Pfad im screenshots Verzeichnis liegt
        try:
            full_path = full_path.resolve()
            screenshots_dir = Path("screenshots").resolve()
            if not str(full_path).startswith(str(screenshots_dir)):
                logger.warning(f"Ungültiger Pfad: {full_path} liegt nicht in {screenshots_dir}")
                return {"status": "error", "message": "Ungültiger Pfad"}
        except Exception as e:
            logger.error(f"Pfad-Validierung fehlgeschlagen: {e}")
            return {"status": "error", "message": f"Pfad-Validierung fehlgeschlagen: {e}"}
        
        if not full_path.exists():
            return {"status": "error", "message": f"Datei nicht gefunden: {clean_path}"}
        
        # Lösche die Bilddatei
        full_path.unlink()
        logger.info(f"✅ Bild gelöscht: {full_path}")
        
        # Lösche auch die zugehörige JSON-Datei falls vorhanden
        json_file = full_path.with_suffix('.json')
        if json_file.exists():
            json_file.unlink()
            logger.info(f"✅ Metadaten gelöscht: {json_file}")
        
        return {"status": "success", "message": f"Bild gelöscht: {clean_path}"}
        
    except Exception as e:
        logger.error(f"Delete image error: {e}")
        return {"status": "error", "message": str(e)}

@router.post("/api/comfy/delete-all")
async def comfy_delete_all_images(token: str = Header(None, alias="token")):
    """Löscht alle ComfyUI Bilder"""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    
    try:
        comfy_dir = Path("screenshots/comfy")
        deleted = 0
        
        if comfy_dir.exists():
            for img_file in comfy_dir.glob("*.png"):
                try:
                    img_file.unlink()
                    deleted += 1
                    # Lösche auch JSON-Dateien
                    json_file = img_file.with_suffix('.json')
                    if json_file.exists():
                        json_file.unlink()
                except Exception as e:
                    logger.error(f"Fehler beim Löschen von {img_file}: {e}")
        
        logger.info(f"✅ {deleted} Bilder gelöscht")
        return {"status": "success", "message": f"{deleted} Bilder gelöscht", "count": deleted}
        
    except Exception as e:
        logger.error(f"Delete all error: {e}")
        return {"status": "error", "message": str(e)}

@router.post("/api/comfy/open-folder")
async def comfy_open_folder(token: str = Header(None, alias="token")):
    """Öffnet den ComfyUI Bilder-Ordner im Datei-Explorer"""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    
    try:
        comfy_dir = Path("screenshots/comfy").resolve()
        
        # Stelle sicher, dass der Ordner existiert
        comfy_dir.mkdir(parents=True, exist_ok=True)
        
        # Öffne den Ordner im Datei-Explorer
        import platform
        import subprocess
        
        if platform.system() == "Windows":
            subprocess.Popen(f'explorer "{comfy_dir}"')
        elif platform.system() == "Darwin":  # macOS
            subprocess.Popen(["open", str(comfy_dir)])
        else:  # Linux
            subprocess.Popen(["xdg-open", str(comfy_dir)])
        
        return {"status": "success", "message": f"Ordner geöffnet: {comfy_dir}"}
    except Exception as e:
        logger.error(f"Open folder error: {e}")
        return {"status": "error", "message": str(e)}

@router.get("/api/comfy/metadata/{path:path}")
async def comfy_get_metadata(
    path: str,
    token: str = Header(None, alias="token")
):
    """Liest Metadaten einer JSON-Datei für ein ComfyUI Bild"""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    
    try:
        # Pfad bereinigen
        clean_path = path.replace('\\', '/')
        
        # Stelle sicher, dass der Pfad im screenshots/comfy Verzeichnis liegt
        if not clean_path.startswith('comfy/'):
            clean_path = f"comfy/{clean_path}"
        
        full_path = Path("screenshots") / clean_path
        
        # Sicherheitscheck
        try:
            full_path = full_path.resolve()
            screenshots_dir = Path("screenshots").resolve()
            if not str(full_path).startswith(str(screenshots_dir)):
                raise HTTPException(status_code=403, detail="Ungültiger Pfad")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Pfad-Validierung fehlgeschlagen: {e}")
        
        if not full_path.exists():
            raise HTTPException(status_code=404, detail="Metadaten nicht gefunden")
        
        with open(full_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        
        return metadata
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Metadata read error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/web/goto")
async def web_goto(
    payload: dict,
    token: str = Header(None, alias="token")
):
    """Öffnet URL im Hintergrund-Browser und analysiert"""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    
    url = payload.get("url", "")
    headless = payload.get("headless", True)
    learn = payload.get("learn", True)
    
    if not url:
        return {"status": "error", "reply": "❌ Keine URL angegeben"}
    
    try:
        # Web-Automation starten - HIER WAR DER FEHLER: web war nicht definiert
        web = get_web_automation(headless=headless)
        
        # Seite öffnen
        result = await web.goto(url)
        
        if not result.get("success"):
            return {"status": "error", "reply": f"❌ Fehler: {result.get('error')}"}
        
        # Vision-Analyse mit GABI
        vision_analysis = ""
        if result.get("screenshot", {}).get("base64"):
            try:
                prompt = f"Analysiere diesen Screenshot von {url}. Beschreibe kurz was du siehst."
                vision_analysis = await _analyze_with_vision(
                    result["screenshot"]["base64"],
                    prompt
                )
            except Exception as e:
                logger.error(f"Vision-Analyse Fehler: {e}")
                vision_analysis = f"Analyse fehlgeschlagen: {e}"
        
        return {
            "status": "success",
            "reply": f"✅ **Webseite analysiert:** {result.get('title', url)}\n\n"
                    f"📸 Screenshot: {result.get('screenshot', {}).get('path', 'unbekannt')}\n\n"
                    f"🔍 **KI-Analyse:**\n{vision_analysis[:1000] if vision_analysis else 'Keine Analyse verfügbar'}",
            "data": result
        }
        
    except Exception as e:
        logger.error(f"Web-Goto Fehler: {e}")
        return {"status": "error", "reply": f"❌ Fehler: {str(e)}"}

@router.post("/api/web/click")
async def web_click(
    payload: dict,
    token: str = Header(None, alias="token")
):
    """Klickt auf ein Element auf der aktuellen Seite"""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    
    selector = payload.get("selector", "")
    if not selector:
        return {"status": "error", "reply": "❌ Kein Selektor angegeben"}
    
    try:
        web = get_web_automation()
        result = await web.click(selector)
        
        if result.get("success"):
            return {
                "status": "success",
                "reply": f"✅ Geklickt auf: {selector}\n"
                        f"📸 Screenshot: {result.get('screenshot', {}).get('path')}"
            }
        else:
            return {"status": "error", "reply": f"❌ Fehler: {result.get('error')}"}
            
    except Exception as e:
        return {"status": "error", "reply": f"❌ Fehler: {str(e)}"}

@router.post("/api/web/test")
async def web_test(payload: dict):
    url = payload.get("url")
    test_description = payload.get("test", "Überprüfe ob die Seite lädt")
    
    web = get_web_automation()
    result = await web.goto(url)
    
    analysis = await _analyze_with_vision(
        result["screenshot"]["base64"],
        f"Teste die Webseite: {test_description}. Beschreibe was du siehst."
    )
    
    return {"status": "success", "analysis": analysis}

# Im Daemon-Modus regelmäßig Webcam prüfen
async def watch_camera():
    while True:
        vision = get_gabi_vision()
        result = vision.capture_webcam()
        analysis = await _analyze_with_vision(
            result["base64"],
            "Erkenne Bewegung oder Änderungen im Bild. Gib eine kurze Zusammenfassung."
        )
        
        if "Bewegung" in analysis or "Änderung" in analysis:
            # Telegram-Benachrichtigung
            await send_telegram_message(f"📷 Kamera erkannt: {analysis}")
        
        await asyncio.sleep(30)  # Alle 30 Sekunden


async def _analyze_with_vision(screenshot_base64: str, prompt: str) -> str:
    """Analysiert Screenshot mit Vision-Modell"""
    try:
        # Stelle sicher, dass Base64-String keinen Prefix hat
        if isinstance(screenshot_base64, str):
            # Entferne "data:image/png;base64," Prefix falls vorhanden
            if "," in screenshot_base64 and screenshot_base64.startswith("data:"):
                screenshot_base64 = screenshot_base64.split(",", 1)[1]
        
        # Wähle das richtige Vision-Modell aus Config
        models_info = ollama_client.list_models()
        available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
        
        # Bevorzugte Vision-Modelle aus Config
        preferred_vision = _as_model_pref_list(config.get("ollama.preferred_vision_models")) or ["qwen3-vl:8b"]
        vision_model = _pick_preferred_available(available, preferred_vision)
        
        if not vision_model:
            # Fallback: Suche nach Vision-Modellen
            vision_hints = ["vl", "vision", "llava", "moondream", "minicpm-v", "qwen2.5vl"]
            vision_model = _pick_best_model(available, hints=vision_hints)
        
        if not vision_model:
            return "❌ Kein Vision-Modell verfügbar. Installiere z.B. qwen3-vl:8b mit: ollama pull qwen3-vl:8b"
        
        logger.info(f"🔍 Verwende Vision-Modell: {vision_model}")
        
        # Ollama Chat mit Bild
        response = await _ollama_chat_async(
            model=vision_model,
            messages=[
                {"role": "user", "content": prompt, "images": [screenshot_base64]}
            ]
        )
        result = _extract_ollama_text(response)
        return result if result else "Keine Analyse erhalten"
        
    except Exception as e:
        logger.error(f"Vision-Analyse Fehler: {e}")
        return f"Analyse fehlgeschlagen: {str(e)}"
    
# Autonome Web-Analyse
@router.post("/api/web/auto")
async def web_auto_analyze(
    payload: dict,
    token: str = Header(None, alias="token")
):
    """
    Autonome Web-Analyse und Navigation mit Vision
    
    Beispiel:
    {
        "url": "http://ventosus",
        "goal": "Login durchführen und Dashboard erreichen",
        "headless": false,
        "max_steps": 10
    }
    """
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    
    url = payload.get("url", "")
    goal = payload.get("goal", "")
    headless = payload.get("headless", False)
    max_steps = payload.get("max_steps", 10)
    
    if not url:
        return {"status": "error", "reply": "❌ Keine URL angegeben"}
    
    try:
        from gateway.integrations.web_vision_agent import get_web_vision_agent
        
        agent = get_web_vision_agent(headless=headless)
        
        # Starte die autonome Navigation
        result = await agent.analyze_and_navigate(url, goal, max_steps)
        
        if result.get("success"):
            # Generiere eine verständliche Antwort
            steps_text = "\n".join([
                f"  {i+1}. {step.get('action', '?')}: {step.get('target', step.get('text', ''))[:50]}"
                for i, step in enumerate(result.get('action_history', []))
            ])
            
            reply = f"""
✅ **Autonome Navigation erfolgreich!**

**Ziel:** {url}
**Schritte:** {result.get('steps_taken', 0)}

**Ausgeführte Aktionen:**
{steps_text if steps_text else 'Keine Aktionen ausgeführt'}

**Gedankengang des Agents:**
"""
            for step in result.get('thinking_steps', [])[:10]:
                reply += f"\n• {step.get('text', '')}"
            
            return {
                "status": "success",
                "reply": reply,
                "data": result
            }
        else:
            return {
                "status": "error",
                "reply": f"❌ **Autonome Navigation fehlgeschlagen**\n\nFehler: {result.get('error', 'Unbekannt')}",
                "thinking_steps": agent.thinking_steps if agent else []
            }
            
    except Exception as e:
        logger.error(f"Web Auto Fehler: {e}")
        return {
            "status": "error",
            "reply": f"❌ Fehler: {str(e)}"
        }

@router.get("/api/web/vision-models")
async def list_vision_models(token: str = Header(None, alias="token")):
    """Listet verfügbare Vision-Modelle auf"""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    
    try:
        from gateway.ollama_client import ollama_client
        from gateway.integrations.web_vision_agent import get_web_vision_agent
        
        agent = get_web_vision_agent()
        model = await agent._get_best_vision_model()
        
        models_info = ollama_client.list_models()
        all_models = [m.get("name") for m in models_info.get("models", [])]
        
        vision_models = [m for m in all_models if any(hint in m.lower() for hint in ["vl", "vision", "llava", "moondream", "minicpm-v"])]
        
        return {
            "status": "success",
            "all_models": all_models,
            "vision_models": vision_models,
            "suggested": model
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}






def _log_gui_action(action: str, target: str, result: dict):
    """Dokumentiert GUI-Aktionen in MEMORY.md."""
    try:
        from datetime import datetime
        import os
        
        memory_path = Path("MEMORY.md")
        if not memory_path.exists():
            return
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Prüfen ob Memory-Datei recent genug ist (nicht zu groß)
        if memory_path.stat().st_size > 10_000_000:  # 10MB Limit
            logger.warning("MEMORY.md zu groß, keine neuen Einträge")
            return
        
        content = memory_path.read_text(encoding="utf-8")
        
        entry = f"""
## GUI-Aktion [{timestamp}]
- **Aktion**: {action}
- **Ziel**: {target}
- **Erfolg**: {'Ja' if result.get('success') else 'Nein'}
- **Details**: {result.get('message', result.get('error', 'N/A'))}
"""
        
        # Am Ende hinzufügen
        memory_path.write_text(content + entry, encoding="utf-8")
        logger.info(f"GUI-Aktion dokumentiert: {action} -> {target}")
        
    except Exception as e:
        logger.error(f"Fehler beim Dokumentieren der GUI-Aktion: {e}")