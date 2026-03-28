# gateway/api/chat.py
"""Chat-bezogene API-Endpunkte."""
# debug start
import traceback
try:
    # Dein bestehender Code
    pass
except Exception as e:
    print("=" * 50)
    print("FEHLER-STACKTRACE:")
    traceback.print_exc()
    print("=" * 50)
    raise
# debug ende

import os
import re
import platform # hat den re fehler, bei einer chatanfrage behoben.
import uuid
import base64
import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Header, HTTPException, Depends, Form, UploadFile, File
from pydantic import BaseModel

from gateway.config import config
from gateway.auth import verify_api_key
from gateway.ollama_client import ollama_client
from gateway.core.memory import chat_memory
from gateway.core.router import (
    _classify_intent_enhanced,
    _auto_select_model,
    _extract_entities,
    _pick_vision_model,
    _pick_fast_model,
    _as_model_pref_list,
    _pick_preferred_available,
    _pick_best_model
)
from gateway.core.commands import handle_command
from gateway.core.brain import get_brain
from gateway.utils.model_helpers import (
    _extract_ollama_text,
    _extract_json_object
)
from gateway.core.progress import (
    _progress_init,
    _progress_add,
    _progress_mark_done,
    _progress_set_active_model,
    _ensure_not_cancelled,
    ChatCancelled
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Konstanten
API_KEY_REQUIRED = config.get("api_key", "sysop")
DEFAULT_MODEL = config.get("ollama.default_model", "llama2:latest")


class ChatRequest(BaseModel):
    """Chat-Anfrage-Modell."""
    message: str
    model: Optional[str] = None
    context: Optional[List[dict]] = []
    request_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat-Antwort-Modell."""
    status: str
    reply: str
    timestamp: str
    model_used: Optional[str] = None
    request_id: Optional[str] = None
    thinking_steps: Optional[List[Dict[str, str]]] = None
    hemisphere: Optional[str] = None
    tool_used: Optional[str] = None


async def _ollama_chat_async(*, model: str, messages: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """Run blocking Ollama chat call in worker thread."""
    return await asyncio.to_thread(ollama_client.chat, model=model, messages=messages, **kwargs)


async def _ollama_generate_async(*, model: str, prompt: str, **kwargs) -> Dict[str, Any]:
    """Run blocking Ollama generate call in worker thread."""
    return await asyncio.to_thread(ollama_client.generate, model=model, prompt=prompt, **kwargs)


async def _ollama_list_models_async() -> Dict[str, Any]:
    """Run blocking Ollama model listing in worker thread."""
    return await asyncio.to_thread(ollama_client.list_models)


def _extract_search_term(text: str, triggers: List[str]) -> str:
    """Extrahiert Suchbegriff aus Text."""
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
    """Prüft ob nach der Suche eine Zusammenfassung gewünscht wird."""
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


async def _detect_and_execute_gui_command(message: str, token: str) -> Optional[Dict]:
    """Erkennt GUI-Befehle in natürlicher Sprache."""
    
    msg_lower = message.lower()
    
    # Vision-Patterns
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
            return await handle_command("/vision", token)
    
    # URL öffnen
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
    
    # Screenshot
    if re.search(r'(?:mach|erstelle|take|make)\s+(?:einen\s+)?screenshot', msg_lower, re.IGNORECASE):
        logger.info(f"🔧 GUI-Erkennung (Screenshot): '{message}' → /gui screenshot")
        return await handle_command("/gui screenshot", token)
    
    # Programme öffnen
    open_pattern = re.search(r'(?:öffne|starte|open|launch)\s+([a-zA-Z0-9\s\-]+?)(?:\s|$)', msg_lower, re.IGNORECASE)
    if open_pattern:
        program_name = open_pattern.group(1).strip()
        program_name = re.sub(r'\s*(?:bitte|mal|jetzt|schnell)$', '', program_name)
        
        if program_name:
            logger.info(f"🔧 GUI-Erkennung (Programm): '{message}' → /gui open {program_name}")
            return await handle_command(f"/gui open {program_name}", token)
    
    return None


async def _detect_and_execute_shell_command(message: str, token: str) -> Optional[Dict]:
    """Plattformunabhängige Shell-Erkennung."""
    import platform
    
    system_os = platform.system().lower()
    
    # Plattform-Erkennung
    if system_os == "windows":
        dir_cmd = "dir"
        file_cmd = "type"
        del_cmd = "del"
    else:
        dir_cmd = "ls -la"
        file_cmd = "cat"
        del_cmd = "rm"
    
    msg_lower = message.lower()
    
    # Befehls-Mapping
    command_map = {
        # Dateien anzeigen
        r'(?:zeig|list|show)\s+(?:mir\s+)?(?:alle\s+)?python\s+dateien': 
            f"{dir_cmd} *.py",
        r'(?:zeig|list|show)\s+(?:mir\s+)?(?:alle\s+)?dateien': 
            dir_cmd,
        r'(?:was\s+ist\s+)?(?:im\s+)?aktuellen\s+ordner': 
            dir_cmd,
        
        # Datei lesen
        r'(?:zeig|lies|read)\s+(?:mir\s+)?(?:die\s+)?datei\s+(\S+)': 
            f"{file_cmd} {{}}",
        
        # Datei erstellen
        r'(?:erstelle|create)\s+(?:die\s+)?datei\s+(\S+)(?!\s+mit\s+inhalt)': 
            f"echo '' > {{}}",
        
        # Datei erstellen mit Inhalt
        r'(?:erstelle|create)\s+(?:die\s+)?datei\s+(\S+)\s+mit\s+inhalt\s+(.+)': 
            f"echo {{}} > {{}}",
        
        # Datei löschen
        r'(?:lösche|delete|remove)\s+(?:die\s+)?datei\s+(\S+)': 
            f"{del_cmd} {{}}",
        
        # Aktuelles Verzeichnis
        r'(?:wo\s+bin\s+ich|aktuelles\s+verzeichnis)': 
            "cd" if system_os == "windows" else "pwd",
    }
    
    for pattern, cmd_template in command_map.items():
        match = re.search(pattern, msg_lower, re.IGNORECASE)
        if match:
            if "{}" in cmd_template:
                groups = match.groups()
                groups = [g for g in groups if g is not None]
                
                if len(groups) == 1:
                    cmd = cmd_template.format(groups[0])
                elif len(groups) == 2:
                    if "echo" in cmd_template and ">" in cmd_template:
                        cmd = cmd_template.format(groups[1], groups[0])
                    else:
                        cmd = cmd_template.format(groups[0], groups[1])
                else:
                    cmd = cmd_template
            else:
                cmd = cmd_template
            
            logger.info(f"🔧 Shell-Erkennung: '{message}' → /shell {cmd}")
            result = await handle_command(f"/shell {cmd}", token)
            if isinstance(result, dict):
                result["auto_detected"] = True
                result["executed_command"] = cmd
            return result
    
    return None


async def _execute_llm_shell_commands(reply: str, token: str, thinking_steps: list, request_id: str) -> str:
    """
    Scannt die LLM-Antwort auf /shell-Befehle, /gui-Befehle UND ```shell Code-Blöcke und führt sie aus.
    Ersetzt die Befehle durch ihre tatsächliche Ausgabe.
    """
    import platform

    DANGEROUS = ["rm -rf /", "format c:", "del /f /s /q c:\\", "mkfs", ":(){ :|: & };:"]

    async def _run_cmd(cmd: str, is_gui: bool = False) -> str:
        """Führt einen Shell- oder GUI-Befehl aus"""
        cmd = cmd.strip()
        if not cmd:
            return ""
        
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

    # Pattern für Shell-Befehle (inline) - Jetzt mit 're' statt '_re'
    inline_pattern = re.compile(r'(?:(?<!\w)/execute\s+)?/shell\s+(.+?)(?=\n|$)', re.IGNORECASE)

    # Pattern für GUI-Befehle
    gui_pattern = re.compile(r'/gui\s+(.+?)(?=\n|$)', re.IGNORECASE)

    # Pattern für Code-Blöcke
    block_pattern = re.compile(r'```(?:shell|bash|cmd|powershell|batch)\s*\n(.*?)```', re.DOTALL | re.IGNORECASE)

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


@router.post("/chat")
async def chat_with_gabi(request: ChatRequest, token: str = Header(None, alias="token")):
    """
    🧠 GABI Chat-Endpunkt mit voller Gehirn-Integration.
    
    Verarbeitet Chat-Anfragen mit:
    - Intent-Erkennung
    - Automatischer Modell-Auswahl
    - Hemisphären-Routing (Corpus Callosum)
    - Shell/GUI-Befehlsausführung
    - Smart SoM Agent Integration (intelligente Web-Suche)
    """
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    
    request_id = (request.request_id or "").strip() or f"gabi-{uuid.uuid4().hex[:12]}"
    _progress_init(request_id)
    _progress_add(request_id, "🧠 GABI Gehirn aktiviert", "fa-brain")

    try:
        _ensure_not_cancelled(request_id)

        logger.info(f"📥 ChatRequest empfangen - model: {request.model!r}")

        user_message = request.message

        # ===== PRÜFE AUF TELEGRAM PREFIX =====
        if user_message.startswith("__TELEGRAM__"):
            # Telegram-Nachricht senden
            telegram_msg = user_message.replace("__TELEGRAM__", "").strip()
            # ... Telegram senden Code ...
            return

        # ===== PRÜFE AUF SEARCH PREFIX =====
        if user_message.startswith("__SEARCH__"):
            # Entferne Prefix und führe Web-Suche aus
            search_query = user_message.replace("__SEARCH__", "").strip()
            user_message = search_query
            # Force Web-Suche
            intent_result = {"intent": "som_search", "confidence": 1.0, "query": search_query}

        # ===== 1. DIREKTE BEFEHLE =====
        if user_message.startswith('/'):
            logger.info(f"⚡ Direkter Befehl erkannt: {user_message}")
            _progress_add(request_id, f"Linke Hemisphäre: Verarbeite Befehl", "fa-terminal")
            cmd_result = await handle_command(user_message, token)
            if isinstance(cmd_result, dict):
                cmd_result["request_id"] = request_id
                cmd_result["hemisphere"] = "left"
            return cmd_result

        # ===== 2. GUI-BEFEHLE =====
        gui_result = await _detect_and_execute_gui_command(user_message, token)
        if gui_result:
            if isinstance(gui_result, dict):
                gui_result["request_id"] = request_id
                gui_result["priority"] = "gui"
                _progress_add(request_id, f"🖥️ GUI-Befehl erkannt", "fa-desktop")
            return gui_result

        # ===== 3. SEMANTISCHE INTENT-ERKENNUNG =====
        intent_result = _classify_intent_enhanced(user_message)
        logger.info(f"🎯 Intent erkannt: {intent_result['intent']} (Confidence: {intent_result['confidence']:.2f})")


        # ===== NEU: PRÜFE OB WIRKLICH INTERNET-SUCHE GEWÜNSCHT IST =====
        EXPLICIT_SEARCH_KEYWORDS = [
            "suche im internet", "such im internet", "google nach", 
            "web suche", "im internet suchen", "finde im internet",
            "recherchiere", "such nach"
        ]

        is_explicit_search = any(kw in user_message.lower() for kw in EXPLICIT_SEARCH_KEYWORDS)

        # Wetter, Kino, Nachrichten sind auch Suchanfragen (können aber auch lokal sein)
        is_weather = "wetter" in user_message.lower()
        is_movies = "kino" in user_message.lower() or "film" in user_message.lower()
        is_news = "nachrichten" in user_message.lower()

        # Nur wenn explizit gesucht wird ODER es sich um Wetter/Kino/Nachrichten handelt
        should_search = is_explicit_search or is_weather or is_movies or is_news

        
        # ===== 4. SoM INTENTS AUSFÜHREN =====
        # if intent_result.get("intent", "").startswith("som_"):
        if intent_result.get("intent", "").startswith("som_") and should_search:
            intent = intent_result["intent"]
            
            if intent == "som_search":
                query = intent_result.get("query", user_message)
                logger.info(f"🔍 SoM Search: {query}")
                _progress_add(request_id, f"🔍 Web-Suche: {query}", "fa-search")
                
                from gateway.integrations.smart_som_agent import get_smart_agent
                
                try:
                    logger.info(f"🌐 Starte Smart SoM Agent für Suche: {query}")
                    agent = get_smart_agent(headless=True, keep_alive=True)
                    
                    # Suche ausführen
                    results = await agent.search(query)
                    thinking_steps = agent.get_thinking_steps()
                    
                    for step in thinking_steps:
                        _progress_add(request_id, step.get("text", ""), step.get("icon", "fa-brain"))
                    
                    if results:
                        logger.info(f"📊 {len(results)} Ergebnisse gefunden")
                        
                        # Für LLM formatieren (mit Volltext bei komplexen Fragen)
                        search_context = agent.format_for_llm(max_results=5)
                        
                        extraction_prompt = f"""Du bist ein präziser Informations-Extraktor.

                    **FRAGE:** {query}

                    **VERFÜGBARE INFORMATIONEN (nur diese verwenden!):**
                    {search_context}

                    **REGELN:**
                    1. Beantworte die Frage AUSSCHLIESSLICH mit Informationen aus den Quellen
                    2. Markiere jede Information mit der Quellen-Nummer, z.B. (Quelle 1)
                    3. ERFINDE NICHTS
                    4. Bei komplexen Fragen nutze die VOLLSTÄNDIGEN INHALTE der Quellen

                    **ANTWORT (nur basierend auf den Quellen):**"""
                        
                        _progress_add(request_id, f"🤖 Analysiere {len(results)} Suchergebnisse...", "fa-brain")
                        
                        # Modell-Auswahl
                        models_info = ollama_client.list_models()
                        available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
                        extraction_model = "qwen2.5:1.5b" if "qwen2.5:7b" in available else "llama3.1:8b"
                        
                        _progress_set_active_model(request_id, extraction_model)
                        
                        # Kontext für LLM aufbauen
                        search_context = ""
                        for i, res in enumerate(results[:6], 1):
                            search_context += f"""
            [QUELLE {i}]
            Titel: {res.title}
            URL: {res.url}
            Auszug: {res.snippet}
            ---"""
                        
                        extraction_prompt = f"""Du bist ein präziser Informations-Extraktor.

            **FRAGE:** {query}

            **VERFÜGBARE INFORMATIONEN (nur diese verwenden!):**
            {search_context}

            **REGELN:**
            1. Beantworte die Frage AUSSCHLIESSLICH mit Informationen aus den Quellen
            2. Markiere jede Information mit der Quellen-Nummer, z.B. (Quelle 1)
            3. ERFINDE NICHTS

            **ANTWORT (nur basierend auf den Quellen):**"""
                        
                        try:
                            response = await _ollama_chat_async(
                                model=extraction_model,
                                messages=[{"role": "user", "content": extraction_prompt}],
                                options={"temperature": 0.1, "num_predict": 600}
                            )
                            summary = _extract_ollama_text(response) or "Keine Zusammenfassung erhalten."
                            
                            # ===== WICHTIG: ANTWORT ZURÜCKGEBEN! =====
                            final_reply = agent.format_results_markdown(max_results=5)
                            reply = f"## 🔍 Suchergebnisse für '{query}'\n\n{summary}\n\n{final_reply}"
                            
                            return {
                                "status": "success",
                                "reply": reply,
                                "timestamp": datetime.now().isoformat(),
                                "tool_used": "smart_som_search",
                                "model_used": extraction_model,
                                "thinking_steps": thinking_steps,
                                "request_id": request_id,
                                "intent": intent
                            }
                            
                        except Exception as e:
                            logger.error(f"Extraktion fehlgeschlagen: {e}")
                            # Fallback: Nur Ergebnisse anzeigen
                            reply = agent.format_results_markdown(max_results=10)
                            return {
                                "status": "success",
                                "reply": reply,
                                "timestamp": datetime.now().isoformat(),
                                "tool_used": "smart_som_search_raw",
                                "thinking_steps": thinking_steps,
                                "request_id": request_id,
                                "intent": intent
                            }
                    else:
                        logger.warning(f"Keine Suchergebnisse für '{query}'")
                        return {
                            "status": "success",
                            "reply": f"🔍 Keine Suchergebnisse für '{query}' gefunden.\n\n💡 Tipp: Versuche es mit einem anderen Suchbegriff.",
                            "thinking_steps": thinking_steps if 'thinking_steps' in locals() else [],
                            "request_id": request_id
                        }
                        
                except Exception as e:
                    logger.error(f"Smart SoM Agent Fehler: {e}")
                    import traceback
                    traceback.print_exc()
                    return {
                        "status": "error",
                        "reply": f"❌ Suche fehlgeschlagen: {str(e)}",
                        "request_id": request_id
                    }
                
                # ===== ALTER CODE WIRD HIER NICHT MEHR AUSGEFÜHRT =====
                # Der neue SmartSoMAgent ersetzt den alten komplett
                # (Der alte Selenium-Code ist entfernt)

        # ===== 5. SHELL-ERKENNUNG =====
        if intent_result.get("intent") == "chat" or intent_result.get("confidence", 0) < 0.6:
            shell_result = await _detect_and_execute_shell_command(user_message, token)
            if shell_result:
                if isinstance(shell_result, dict):
                    shell_result["request_id"] = request_id
                    shell_result["priority"] = "shell"
                    _progress_add(request_id, f"💻 Shell-Befehl erkannt", "fa-terminal")
                return shell_result

        # ===== 6. CORPUS CALLOSUM + NORMALE CHAT-VERARBEITUNG =====
        brain = get_brain()
        brain.initialize_hemispheres()
        
        _progress_add(request_id, "Corpus Callosum aktiv - Verbinde Hemisphären", "fa-link")
        
        # Prüfe auf /merken Befehl
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
                }
            action = "gemerkt" if created else "bereits gemerkt"
            reply = f"✅ {action.capitalize()}: {entry['text']}\nAbrufbar mit `/gemerkt`."
            chat_memory.add_to_memory(user_message, reply)
            return {
                "status": "success",
                "reply": reply,
                "timestamp": datetime.now().isoformat(),
                "model_used": "gabi/memory",
                "request_id": request_id,
            }
        
        # ===== 7. BRAIN ROUTING =====
        task = {
            "content": user_message,
            "type": "auto",
            "request_id": request_id,
            "intent_result": intent_result,
            "context": chat_memory.conversation_history[-10:] if chat_memory.conversation_history else []
        }
        
        routing_result = brain.route_task(task)
        hemisphere = routing_result.get("hemisphere", "bridge")
        detected_type = routing_result.get("detected_type", "chat")

        _progress_add(request_id, f"Corpus Callosum: Routing zu {hemisphere} Hemisphäre (Typ: {detected_type})",
                      "fa-code-branch" if hemisphere == "left" else "fa-paint-brush")
        
        # ===== 8. BRAIN ANTWORT ODER LLM-FALLBACK =====
        brain_reply = routing_result.get("reply") or routing_result.get("response") or routing_result.get("result")
        brain_success = routing_result.get("success", True)
        
        # Prüfe ob Brain eine Suche ausgeführt hat, obwohl der User keine wollte
        EXPLICIT_SEARCH_KEYWORDS = [
            "suche nach", "such nach", "google", "such mir", "recherchiere",
            "finde im internet", "web search", "im internet suchen",
        ]
        _msg_lower = user_message.lower()
        _brain_did_search = detected_type == "search" or routing_result.get("tool_used") == "web_search"
        _user_wanted_search = any(kw in _msg_lower for kw in EXPLICIT_SEARCH_KEYWORDS)
        
        if _brain_did_search and not _user_wanted_search:
            logger.info(f"🚫 Brain-Suche ignoriert (kein Such-Keyword)")
            brain_reply = None
            brain_success = False
        
        if brain_reply and brain_success:
            chat_memory.add_to_memory(user_message, str(brain_reply))
            return {
                "status": "success",
                "reply": str(brain_reply),
                "timestamp": datetime.now().isoformat(),
                "hemisphere": hemisphere,
                "task_type": detected_type,
                "model_used": routing_result.get("model_used", "brain"),
                "request_id": request_id,
            }
        
        # ===== 9. LLM FALLBACK =====
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
            "hemisphere": hemisphere,
            "task_type": detected_type,
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


@router.post("/v1/chat/completions")
async def chat_completions(
    payload: dict,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """
    OpenAI-kompatibler /v1/chat/completions Endpunkt.
    """
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
    """
    Listet verfügbare Ollama Modelle auf.
    """
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


@router.post("/api/chat/image/analyze")
async def analyze_image_with_vlm(
    file: UploadFile = File(...),
    prompt: str = Form(""),
    model: Optional[str] = Form(None),
    request_id: Optional[str] = Form(None),
    token: str = Header(None),
):
    """
    Analysiert ein hochgeladenes Bild mit einem Vision-Modell.
    """
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


@router.get("/api/chat/progress/{request_id}")
async def get_chat_progress(request_id: str, since: int = 0, token: str = Header(None)):
    """Poll live progress steps for a running chat request."""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    
    from gateway.core.progress import _progress_get
    return _progress_get(request_id, since=since)


@router.post("/api/chat/stop")
async def stop_chat(payload: dict, token: str = Header(None)):
    """Stop an active chat request and try to abort running Ollama generation."""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    
    from gateway.core.progress import _progress_cancel, _stop_ollama_model, _list_running_ollama_models, _CHAT_PROGRESS, _CHAT_PROGRESS_LOCK
    
    request_id = str((payload or {}).get("request_id") or "").strip()
    stopped_models: List[Dict[str, Any]] = []
    target_models: List[str] = []
    
    if request_id:
        _progress_cancel(request_id)
        from gateway.core.progress import _progress_add
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