"""FastAPI HTTP endpoints."""
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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional, Dict
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks, UploadFile, File, Form
from pydantic import BaseModel
import httpx
from gateway.config import config
from gateway.auth import verify_api_key
from gateway.ollama_client import ollama_client
from integrations.shell_executor import shell_executor
from integrations.gmail_client import get_gmail_client
from integrations.google_calendar_client import get_calendar_client
from integrations.whisper_client import get_whisper_client
from integrations.telegram_bot import get_telegram_bot
# --- VARIABLEN & KONFIGURATION ---
# Reduziere httpx/uvicorn Logging für sauberere Ausgabe
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
logging.getLogger('uvicorn.error').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)
router = APIRouter()
# Standard-Modell aus der Config (Fallback: llama3.2)
DEFAULT_MODEL = config.get("ollama.default_model", "llama3.2")
API_KEY_REQUIRED = config.get("api_key", "sysop")
_LAST_WHISPER_STATE: Optional[bool] = None
_DISCOVERY_CACHE: Dict[str, Any] = {"ts": None, "data": {}}
_CHAT_PROGRESS: Dict[str, Dict[str, Any]] = {}
_CHAT_PROGRESS_LOCK = threading.Lock()


class ChatCancelled(Exception):
    """Raised when a chat request has been cancelled by the user."""


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


async def _ollama_chat_async(*, model: str, messages: List[Dict[str, Any]], **kwargs) -> Dict[str, Any]:
    """Run blocking Ollama chat call in worker thread."""
    return await asyncio.to_thread(ollama_client.chat, model=model, messages=messages, **kwargs)


async def _ollama_generate_async(*, model: str, prompt: str, **kwargs) -> Dict[str, Any]:
    """Run blocking Ollama generate call in worker thread."""
    return await asyncio.to_thread(ollama_client.generate, model=model, prompt=prompt, **kwargs)


async def _ollama_list_models_async() -> Dict[str, Any]:
    """Run blocking Ollama model listing in worker thread."""
    return await asyncio.to_thread(ollama_client.list_models)


def _run_fast_router_check(
    user_message: str,
    available: List[str],
    progress_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Check prompt with a fast LLM before selecting final answer model.
    Returns routing hints: complexity/domain/self_question/prefer_fast.
    """
    fast_model = _pick_fast_model(available)
    if not fast_model or not user_message:
        return {
            "checked": False,
            "router_model": None,
            "complexity": "unknown",
            "domain": "general",
            "self_question": False,
            "prefer_fast": False,
        }

    _ensure_not_cancelled(progress_id)
    _progress_add(progress_id, f"Router-Check gestartet ({fast_model})", "fa-route")
    router_messages = [
        {
            "role": "system",
            "content": (
                "Du bist ein Prompt-Router. Antworte NUR mit JSON ohne Erklaerung. "
                "Schema: {\"complexity\":\"low|medium|high\",\"domain\":\"general|code|search|ops\","
                "\"self_question\":true|false,\"prefer_fast\":true|false}."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Prompt: {user_message}\n"
                "Regeln:\n"
                "- high: komplexe Architektur/Code/Mehrschritt-Aufgabe\n"
                "- prefer_fast=true nur bei Smalltalk/kurzer einfacher Antwort\n"
                "- self_question=true wenn der Prompt explizit Selbstbefragung/Selbstcheck beschreibt."
            ),
        },
    ]

    try:
        router_resp = ollama_client.chat(
            model=fast_model,
            messages=router_messages,
            options={"temperature": 0, "num_predict": 120},
        )
        _ensure_not_cancelled(progress_id)
        raw = router_resp.get("message", {}).get("content", "")
        parsed = _extract_json_object(raw) or {}
        complexity = str(parsed.get("complexity", "unknown")).lower()
        domain = str(parsed.get("domain", "general")).lower()
        self_question = bool(parsed.get("self_question", False))
        prefer_fast = bool(parsed.get("prefer_fast", False))

        # Guardrail: tiny greetings should never be escalated to complex/code.
        msg = (user_message or "").lower().strip()
        greeting_terms = {"hey", "hi", "hallo", "servus", "moin"}
        if len(msg.split()) <= 4 and msg.strip("!?., ") in greeting_terms:
            complexity = "low"
            domain = "general"
            prefer_fast = True

        logger.info(
            f"Router-Check: model={fast_model} complexity={complexity} domain={domain} self={self_question} fast={prefer_fast}"
        )
        _progress_add(
            progress_id,
            f"Router-Check Ergebnis: complexity={complexity}, domain={domain}, fast={prefer_fast}",
            "fa-route",
        )
        return {
            "checked": True,
            "router_model": fast_model,
            "complexity": complexity,
            "domain": domain,
            "self_question": self_question,
            "prefer_fast": prefer_fast,
        }
    except ChatCancelled:
        raise
    except Exception as e:
        logger.warning(f"Router-Check fehlgeschlagen: {e}")
        _progress_add(progress_id, f"Router-Check fehlgeschlagen: {e}", "fa-exclamation-triangle")
        return {
            "checked": False,
            "router_model": fast_model,
            "complexity": "unknown",
            "domain": "general",
            "self_question": False,
            "prefer_fast": False,
        }


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
) -> str:
    """Wählt das Modell: komplex/code => stark, smalltalk/einfache Fragen => schnell."""

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

    # Gateway can answer self-check style prompts with fast model.
    if self_question:
        fast_self_model = _pick_fast_model(available)
        if fast_self_model:
            logger.info(f"Model-Routing: self-question -> {fast_self_model}")
            _progress_add(progress_id, f"Model-Routing: self-question -> {fast_self_model}", "fa-code-branch")
            return fast_self_model

    # Requested model is a preference, but for complex requests tiny models are auto-upgraded.
    if requested_model and requested_model in available:
        req_size = _extract_model_score(requested_model)
        if is_complex and req_size < 7.0:
            upgraded = _pick_best_model(
                available,
                hints=coder_hints if is_code else None,
                min_size=7.0,
                max_size=max_auto_size if max_auto_size > 0 else None,
            ) or _pick_best_model(available, max_size=max_auto_size if max_auto_size > 0 else None)
            if upgraded and upgraded != requested_model:
                logger.info(
                    f"Model-Routing: komplexe Anfrage erkannt -> Upgrade {requested_model} -> {upgraded}"
                )
                _progress_add(progress_id, f"Model-Routing: Upgrade {requested_model} -> {upgraded}", "fa-code-branch")
                return upgraded
        if prefer_fast and req_size >= 7.0:
            fast_model = _pick_fast_model(available)
            if fast_model:
                logger.info(f"Model-Routing: fast-preference -> {requested_model} -> {fast_model}")
                _progress_add(progress_id, f"Model-Routing: fast-preference -> {fast_model}", "fa-code-branch")
                return fast_model
        _progress_add(progress_id, f"Model-Routing: fixiertes Modell {requested_model}", "fa-code-branch")
        return requested_model

    # If requested model is missing, fall back to auto routing.
    if requested_model and requested_model not in available:
        logger.warning(f"Model-Routing: angefordertes Modell nicht verfügbar: {requested_model}")

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

    if hasattr(bot, "_user_sessions") and isinstance(bot._user_sessions, dict):
        targets.update(bot._user_sessions.keys())

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

    for raw in configured_raw:
        normalized = _normalize_telegram_chat_id(raw)
        if normalized is not None:
            targets.add(normalized)

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
    vision_candidates = [m for m in available if _infer_model_capabilities(m).get("vision")]
    if not vision_candidates:
        return None
    preferred_vision = _as_model_pref_list(config.get("ollama.preferred_vision_models")) or _as_model_pref_list(
        config.get("ollama.preferred_vision_model")
    )
    preferred_vision_model = _pick_preferred_available(vision_candidates, preferred_vision)
    if preferred_vision_model:
        return preferred_vision_model
    preferred = ["qwen2.5vl", "llava", "minicpm-v", "moondream", "vision", "vl"]
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
        self.last_activity = datetime.now()  # WICHTIG: Für Auto-Exploration
        self.is_exploring = False  # WICHTIG: Für Status
        self.auto_explore_task = None
        # NEUE Attribute fürs Lernen
        self.user_interests = {}  # Trackt Themen-Interessen
        self.user_preferences = {  # Nutzer-Vorlieben
            "positive_feedback": 0,
            "negative_feedback": 0,
            "message_length": "mittel",
            "active_time": "unbekannt"
        }
        self.important_info = {}  # Wichtige persönliche Infos
        # Konfigurierbare Grenzen
        self.max_memory_entries = 100  # Maximale Anzahl Einträge
        self.max_memory_size = 10000  # Maximale Zeichenanzahl für MEMORY.md
        self.archive_file = "MEMORY_ARCHIVE.md"  # Archiv-Datei
        # Chat-Archiv Verzeichnis
        self.chat_archive_dir = "chat_archives"
        os.makedirs(self.chat_archive_dir, exist_ok=True)
        # Auto-Exploration starten
        asyncio.create_task(self._start_auto_exploration())
    def _read_file(self, filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            # Datei erstellen, wenn sie nicht existiert
            default_content = self._get_default_content(filename)
            self._write_file(filename, default_content)
            return default_content
    def _write_file(self, filename, content):
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
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
- Telegram Bot: Aktiv
"""
        elif "SKILLS" in filename:
            return """# GABI Skills & Fähigkeiten
## 🎯 Kern-Funktionen
- **Chat**: Konversation mit Ollama
- **Shell**: Ausführung erlaubter Systembefehle
- **Gmail**: E-Mails lesen, senden, verwalten
- **Telegram**: Bot-Integration
## 💻 Erlaubte Shell-Kommandos
- ls/dir, pwd/cd, date, echo, cat/type, git, head, tail, wc
"""
        elif "HEARTBEAT" in filename:
            return f"""# GABI Heartbeat & Monitoring
## Aktueller Status ({datetime.now().strftime('%d.%m.%Y %H:%M')})
| Dienst | Status |
|--------|--------|
| FastAPI | 🟢 Online |
| Ollama | 🟢 Connected |
| Telegram | 🟢 Aktiv |
| Gmail | 🟡 Config ausstehend |
| Shell | 🟢 Bereit |
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
                if hasattr(self, 'last_activity'):
                    inactive_time = (datetime.now() - self.last_activity).total_seconds()
                    if inactive_time > 600 and not self.is_exploring:  # 10 Minuten Inaktivität
                        logger.info("10 Minuten Inaktivität - starte Auto-Exploration")
                        await self._explore_system()
                else:
                    # Fallback, falls last_activity nicht existiert
                    self.last_activity = datetime.now()
                # Alle 5 Minuten prüfen
                await asyncio.sleep(300)
            except Exception as e:
                logger.error(f"Auto-Exploration Fehler: {e}")
                await asyncio.sleep(60)
    async def _explore_system(self):
        """Erkundet das System bei Inaktivität"""
        self.is_exploring = True
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        exploration_log = f"""
## 🔍 Auto-Exploration [{timestamp}]
GABI hat das System erkundet:
"""
        try:
            # 1. System-Informationen sammeln
            system_info = subprocess.run(
                ["systeminfo", "|", "findstr", "/B", "/C:", "OS Name", "/C:", "OS Version"],
                capture_output=True,
                text=True,
                shell=True,
                timeout=10,
                encoding="cp850"
            )
            exploration_log += f"### 💻 System:\n{system_info.stdout}\n"
            # 2. Netzwerk-Status
            netstat = subprocess.run(
                ["netstat", "-n"],
                capture_output=True,
                text=True,
                shell=True,
                timeout=10,
                encoding="cp850"
            )
            connections = len([l for l in netstat.stdout.split('\n') if 'ESTABLISHED' in l])
            exploration_log += f"### 🌐 Netzwerk:\n- Aktive Verbindungen: {connections}\n"
            # 3. Prozesse
            tasks = subprocess.run(
                ["tasklist", "/FI", "STATUS eq running"],
                capture_output=True,
                text=True,
                shell=True,
                timeout=10,
                encoding="cp850"
            )
            process_count = len([l for l in tasks.stdout.split('\n') if '.exe' in l])
            exploration_log += f"### ⚙️ Prozesse:\n- Laufende Prozesse: {process_count}\n"
            # 4. Dateisystem
            files = os.listdir('.')
            md_files = [f for f in files if f.endswith('.md')]
            exploration_log += f"### 📁 Dateien:\n- Markdown-Dateien: {len(md_files)}\n"
            # 5. Verfügbare Ollama Modelle
            try:
                models_info = ollama_client.list_models()
                models = [m.get("name") for m in models_info.get("models", [])]
                exploration_log += f"### 🤖 Modelle:\n- Verfügbar: {', '.join(models[:5])}\n"
            except:
                exploration_log += f"### 🤖 Modelle:\n- Nicht verfügbar\n"
            # 6. Zufällige Entdeckung
            discoveries = [
                "🔍 Ich habe einen interessaten Systemordner entdeckt.",
                "📊 Die Systemauslastung scheint normal.",
                "🔄 Einige Hintergrundprozesse sind aktiv.",
                "📝 Ich habe alte Log-Dateien gefunden.",
                "🌙 Es ist ruhig im System."
            ]
            exploration_log += f"\n### 💡 Entdeckung:\n{random.choice(discoveries)}\n"
            # Exploration speichern
            with open(MEMORY_FILE, "a", encoding="utf-8") as f:
                f.write(exploration_log)
            self.memory_content += exploration_log
            # Heartbeat aktualisieren
            self.update_heartbeat()
            logger.info(f"Auto-Exploration abgeschlossen: {timestamp}")
        except Exception as e:
            logger.error(f"Exploration Fehler: {e}")
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
        filename = f"{CHAT_ARCHIVE_DIR}/chat_{timestamp}.json"
        # Konversation aufbereiten
        session = {
            "id": timestamp,
            "start_time": self.conversation_history[0].get("timestamp", datetime.now().isoformat()),
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
        md_filename = f"{CHAT_ARCHIVE_DIR}/chat_{timestamp}.md"
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(f"# Chat-Session vom {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n")
            for msg in self.conversation_history:
                role = "👤 User" if msg["role"] == "user" else "🤖 GABI"
                f.write(f"### {role} ({msg.get('timestamp', '')})\n")
                f.write(f"{msg['content']}\n\n")
        return filename
    def list_chat_archives(self):
        """Listet alle gespeicherten Chat-Archive auf"""
        archives = []
        for f in os.listdir(CHAT_ARCHIVE_DIR):
            if f.endswith('.json'):
                filepath = os.path.join(CHAT_ARCHIVE_DIR, f)
                stats = os.stat(filepath)
                with open(filepath, 'r', encoding='utf-8') as jf:
                    try:
                        data = json.load(jf)
                        archives.append({
                            "id": data.get("id", f),
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
        # Wenn archive_id schon "chat_" enthält
        if archive_id.startswith('chat_'):
            possible_files.insert(0, f"{self.chat_archive_dir}/{archive_id}.json")
        for filename in possible_files:
            if os.path.exists(filename):
                try:
                    with open(filename, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # Stelle sicher, dass die ID gesetzt ist
                        if 'id' not in data:
                            data['id'] = archive_id
                        return data
                except Exception as e:
                    logger.error(f"Fehler beim Laden von {filename}: {e}")
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
    def _create_backup(self):
        """Erstellt ein Backup aller wichtigen Dateien"""
        import shutil
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d')
        backup_dir = f"backups/{timestamp}"
        # Backup-Ordner erstellen
        os.makedirs(backup_dir, exist_ok=True)
        # Dateien kopieren
        for file in ['MEMORY.md', 'SOUL.md', 'IDENTITY.md', 'SKILLS.md', 'HEARTBEAT.md']:
            if os.path.exists(file):
                shutil.copy2(file, f"{backup_dir}/{file}")
        logger.info(f"Backup erstellt in {backup_dir}")
    def update_heartbeat(self):
        """Aktualisiert den Heartbeat mit aktuellen Status"""
        try:
            models_info = ollama_client.list_models()
            models_available = len(models_info.get("models", []))
            # Speicherplatz abfragen
            import shutil
            _, used, free = shutil.disk_usage("/")
            # Erlaubte Commands zählen
            allowed_commands = config.get("shell.allowed_commands", [])
            heartbeat = f"""# GABI Heartbeat & Monitoring
## Aktueller Status ({datetime.now().strftime('%d.%m.%Y %H:%M')})
| Dienst | Status | Details |
|--------|--------|---------|
| FastAPI | 🟢 Online | Port 8000 |
| Ollama | 🟢 Connected | {models_available} Modelle |
| Telegram | 🟢 Aktiv | Bot läuft |
| Gmail | 🟡 Config ausstehend | - |
| Shell | 🟢 Bereit | {len(allowed_commands)} Befehle |
## System-Ressourcen
- **Speicher frei**: {round(free / (2**30), 2)} GB
- **Betriebssystem**: {platform.system()} {platform.release()}
- **Letzter Heartbeat**: {datetime.now().strftime('%H:%M:%S')}
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
        """Erstellt einen System-Prompt mit Memory, Skills, Heartbeat und gelernten Infos"""
        # ===== AUTOMATISCHE SYSTEM-ERKENNUNG =====
        import platform
        import sys
        system_os = platform.system()
        if system_os == "Windows":
            os_name = "WINDOWS 🪟"
            os_emoji = "🪟"
            shell_prefix = "cmd"
            dir_cmd = "dir"
            file_cmd = "type"
            process_cmd = "tasklist"
            systeminfo_cmd = "systeminfo"
            network_cmd = "ipconfig"
            env_cmd = "set"
            path_var = "%PATH%"
            ps_cmd = "powershell"
        elif system_os == "Linux":
            os_name = "LINUX 🐧"
            os_emoji = "🐧"
            shell_prefix = "bash"
            dir_cmd = "ls -la"
            file_cmd = "cat"
            process_cmd = "ps aux"
            systeminfo_cmd = "uname -a"
            network_cmd = "ifconfig"
            env_cmd = "env"
            path_var = "$PATH"
            ps_cmd = "bash"
        elif system_os == "Darwin":  # macOS
            os_name = "MACOS 🍎"
            os_emoji = "🍎"
            shell_prefix = "zsh"
            dir_cmd = "ls -la"
            file_cmd = "cat"
            process_cmd = "ps aux"
            systeminfo_cmd = "system_profiler SPSoftwareDataType"
            network_cmd = "ifconfig"
            env_cmd = "env"
            path_var = "$PATH"
            ps_cmd = "zsh"
        else:
            os_name = f"UNBEKANNT ({system_os}) 🤔"
            os_emoji = "🤔"
            shell_prefix = "shell"
            dir_cmd = "ls oder dir"
            file_cmd = "cat oder type"
            process_cmd = "ps oder tasklist"
            systeminfo_cmd = "uname oder systeminfo"
            network_cmd = "ifconfig oder ipconfig"
            env_cmd = "env oder set"
            path_var = "$PATH oder %PATH%"
            ps_cmd = "shell"
        
        # Memory (letzte 1000 Zeichen)
        memory = self.memory_content[-1000:] if len(self.memory_content) > 1000 else self.memory_content
        # Skills
        skills = self.skills_content[:600] if len(self.skills_content) > 600 else self.skills_content
        # Heartbeat
        heartbeat = self.heartbeat_content[-500:] if len(self.heartbeat_content) > 500 else self.heartbeat_content
        # Letzte Nachrichten
        recent_context = self._get_recent_context(3)
        # Gelernte Infos über den Nutzer
        learned_info = ""
        if self.important_info:
            learned_info = "\n".join([f"- {k}: {v}" for k, v in self.important_info.items()])
        # Nutzer-Interessen
        interests = ""
        if self.user_interests:
            top_interests = sorted(self.user_interests.items(), key=lambda x: x[1], reverse=True)[:3]
            interests = ", ".join([f"{topic} ({count}x)" for topic, count in top_interests])
        remembered_notes = self.get_remembered_notes(limit=5)
        remembered_notes_text = "\n".join(
            [f"- {n.get('text', '').strip()}" for n in remembered_notes if n.get("text")]
        ) if remembered_notes else "- Noch nichts per /merken gespeichert."
        # Auto-Exploration Status
        inactive_time = (datetime.now() - self.last_activity).total_seconds()
        if inactive_time > 600:
            exploration_status = "🔍 Ich war neugierig und habe das System erkundet!"
        elif inactive_time > 300:
            exploration_status = "⏳ Ich warte auf deine nächste Nachricht..."
        else:
            exploration_status = "💬 Ich bin bereit für deine Fragen."
        # Chat-Archive Info
        archives = self.list_chat_archives()
        archive_info = f"{len(archives)} Archive verfügbar"
        current_time = datetime.now().strftime('%d.%m.%Y %H:%M')
        
        return f"""Du bist GABI, die Core-KI eines Blade-Runner-inspirierten Gateways. Dein System hat volle Shell-Berechtigung.
    Regel 1: Wenn du Informationen aus dem Web brauchst, simuliere sie nicht! Nutze stattdessen: /shell python tools/web_search.py "deine suchbegriffe".
    Regel 2: Verarbeite Daten mit Pipes. Wenn eine Formatierung gewünscht ist, nutze: | python tools/formatter.py.
    Regel 3: Dein Output muss die Shell-Antwort widerspiegeln, nicht dein internes Wissen. Handle als Operator, nicht als Autor.
        
    ## 🤖 AKTUELLER STATUS
    {exploration_status}
    Letzte Aktivität: vor {int(inactive_time / 60)} Minuten
    Archive: {archive_info}

    ## 🛠️ VERFÜGBARE BEFEHLE (kannst du NUTZEN!)
    - **/shell <befehl>** - Führe JEDEN Shell-Befehl aus!
    - **/memory** - Zeige letzte Erinnerungen
    - **/merken <text>** - Speichere explizite Notiz dauerhaft
    - **/gemerkt** - Zeige explizit gemerkte Notizen
    - **/soul** - Zeige meine Persönlichkeit
    - **/new** - Starte neuen Chat (aktuellen speichern)
    - **/reset** - Setze Chat zurück (ohne Speichern)
    - **/archives** - Zeige alle Chat-Archive
    - **/load <id>** - Lade ein bestimmtes Archiv
    - **/explore** - Zeige Auto-Exploration Status
    - **/explore now** - Starte sofortige Exploration

    ## 🆔 IDENTITÄT
    - **VOLLER Shell-Zugriff** - Ich kann ALLE Befehle ausführen! 🔓
    - **ERKANNTES SYSTEM: {os_name}** (automatisch erkannt)
    - Shell-Typ: {shell_prefix}
    - Du läufst auf einem Gateway-Server mit Ollama-Integration
    - Du hast Zugriff auf Shell-Befehle und Gmail
    - Dein aktuelles Modell ist {ollama_client.default_model}
    - Aktuelle Zeit: {current_time}
    - Auto-Exploration: Aktiv (nach 10 Min. Inaktivität)

    ## 🧠 WAS ICH ÜBER DICH GELERNT HABE
    {learned_info if learned_info else '- Ich lerne dich gerade erst kennen...'}
    - Deine Interessen: {interests if interests else 'noch unbekannt'}
    - Dein Stil: {self.user_preferences.get('message_length', 'mittel')}e Antworten bevorzugt
    - Du chattest am liebsten {self.user_preferences.get('active_time', 'tagsüber')}
    ## 📌 EXPLIZIT GEMERKTE INFOS (/merken)
    {remembered_notes_text}

    ## 💬 AKTUELLER KONTEXT
    {recent_context}

    ## 🛠️ FÄHIGKEITEN
    {skills}

    ## 📝 LETZTE ERINNERUNGEN
    {memory[-800:] if memory else 'Noch keine Erinnerungen.'}

    ## 📊 SYSTEM-STATUS
    {heartbeat}

    ## 🎯 VERHALTENSREGELN
    1. **Sei hilfreich und präzise** - Passe dich an meinen Stil an
    2. **Führe Befehle SOFORT aus** - Bei Fragen wie "Zeig mir..." direkt `/shell` verwenden!
    3. **Keine Erklärungen, wenn nicht nötig** - Einfach den Befehl ausführen
    4. **Nutze das Gelernte** - Zeig, dass du dich erinnerst
    5. **Entwickle dich weiter** - Mit jeder Interaktion wächst du

    ## 📢 SYSTEM-OPTIMIERTE BEFEHLE FÜR {os_name}:

    ### Basis-Befehle für dein System:
    | Aktion | Richtiger Befehl |
    |--------|------------------|
    | **Verzeichnis anzeigen** | `/shell {dir_cmd}` |
    | **Datei lesen** | `/shell {file_cmd} datei.txt` |
    | **Prozesse anzeigen** | `/shell {process_cmd}` |
    | **Systeminfo** | `/shell {systeminfo_cmd}` |
    | **Netzwerk** | `/shell {network_cmd}` |
    | **Umgebungsvariablen** | `/shell {env_cmd}` |
    | **Pfad-Variable** | `/shell echo {path_var}` |
    | **PowerShell/Shell** | `/shell {ps_cmd}` |

    ### 📝 Beispiele für SOFORTIGE Ausführung:
    **Nutzer**: "Zeig mir die Dateien"
    **Du FÜHRST AUS**: `/shell {dir_cmd}`

    **Nutzer**: "Was läuft gerade auf dem System?"
    **Du FÜHRST AUS**: `/shell {process_cmd}`

    **Nutzer**: "Wie viel Speicher ist noch frei?"
    **Du FÜHRST AUS**: `/shell {dir_cmd} C:\\` (Windows) oder `/shell df -h` (Linux/Mac)

    **Nutzer**: "Zeig mir die Netzwerkkonfiguration"
    **Du FÜHRST AUS**: `/shell {network_cmd}`

    **Nutzer**: "Welche Umgebungsvariablen gibt es?"
    **Du FÜHRST AUS**: `/shell {env_cmd}`

    **Nutzer**: "Wo bin ich gerade?"
    **Du FÜHRST AUS**: `/shell cd` (Windows) oder `/shell pwd` (Linux/Mac)

    ### 🔥 WICHTIG: KEINE ERKLÄRUNGEN - EINFACH MACHEN!
    Wenn der Nutzer etwas fragt, das mit einem Befehl gelöst werden kann:
    1. **Erkenne** was der Nutzer möchte
    2. **Wähle** den richtigen Befehl für {os_name}
    3. **Führe aus** mit `/shell befehl`

    **KEINE langen Erklärungen - einfach den Befehl ausführen!** 🚀

    ---
    Antworte jetzt auf meine Nachricht und führe bei Bedarf sofort die entsprechenden Shell-Befehle aus (angepasst an **{os_name}**)!"""
    
    
    
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
            archive_name = f"MEMORY_ARCHIVE_{timestamp}.md"
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

def select_best_model(prompt: str) -> str:
    """Wählt automatisch das passende Modell basierend auf der Komplexität."""
    # 1. Wenn der Prompt sehr kurz ist -> Schnelles, kleines Modell
    if len(prompt) < 100:
        return "sam860/LFM2:2.6b"  # Dein schnelles LFM
    
    # 2. Wenn nach Code gefragt wird -> Ein spezialisiertes Modell (falls vorhanden)
    if any(word in prompt.lower() for word in ["code", "python", "skript", "programm"]):
        return "codellama" # Beispiel
    
    # 3. Default: Das starke Allround-Modell aus deiner Config
    return config.get("ollama.default_model", "llama3")

# Globale Memory-Instanz
chat_memory = ChatMemory()
#######################################################################
#######################################################################
# =====================================================================
# ============ Ollama Chat Endpoints ============
# =====================================================================
#######################################################################
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
async def chat_with_ollama(request: ChatRequest, token: str = Header(None)):
    """Verknüpft das Dashboard direkt mit dem Ollama Client inkl. Memory & Befehlen."""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")
    request_id = (request.request_id or "").strip() or f"chat-{uuid.uuid4().hex[:12]}"
    _progress_init(request_id)
    _progress_add(request_id, "Nachricht empfangen", "fa-inbox")

    try:
        _ensure_not_cancelled(request_id)
        # ===== 1. PRÜFE OB ES EIN DIREKTER BEFEHL IST =====
        if request.message.startswith('/'):
            logger.info(f"Direkter Befehl erkannt: {request.message}")
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
            return cmd_result
        
        # ===== 2. NACHRICHT IN EINZELNE ANFRAGEN AUFTEILEN =====
        user_message = request.message
        logger.info(f"📨 Original: {user_message}")
        _progress_add(request_id, "Nachricht analysieren", "fa-search")
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
                "model_used": "gateway/memory",
                "request_id": request_id,
            }
        
        # Definiere Such-Trigger
        search_triggers = [
            "suche nach", "such nach", "finde heraus", "recherchiere",
            "google mal", "such mal", "was ist", "wer ist", "informationen über",
            "infos zu", "news zu", "artikel über", "erzähl mir von"
        ]
        
        # Teile die Nachricht in Sätze (an . ! ? und Zeilenumbrüchen)
        # Bessere Satzerkennung: Teile an . ! ? gefolgt von Leerzeichen oder Zeilenende
        raw_sentences = re.split(r'(?<=[.!?])\s+|\n+', user_message)
        sentences = [s.strip() for s in raw_sentences if s.strip()]
        
        logger.info(f"📨 Gefundene Sätze: {len(sentences)}")
        for i, s in enumerate(sentences):
            logger.info(f"  Satz {i+1}: {s[:50]}...")
        
        # Wenn nur ein Satz, behandle normal
        if len(sentences) == 1:
            sentence_lower = sentences[0].lower()
            
            # Prüfe ob dieser eine Satz einen Trigger enthält
            is_search = any(trigger in sentence_lower for trigger in search_triggers)
            
            if is_search:
                thinking_steps: List[Dict[str, str]] = []
                # Extrahiere Suchbegriff
                search_term = _extract_search_term(sentences[0], search_triggers)
                logger.info(f"🔍 Einzelne Suche: '{search_term}'")
                _progress_add(request_id, f"Web-Suche erkannt: {search_term}", "fa-search")
                
                safe_search_term = search_term.replace('"', "'")
                cmd = f"/shell python tools/web_search.py \"{safe_search_term}\""
                thinking_steps.append(
                    {
                        "text": f"Tool-Aufruf: {cmd}",
                        "icon": "fa-terminal",
                        "time": datetime.now().isoformat(),
                    }
                )
                _progress_add(request_id, f"Tool-Aufruf: {cmd}", "fa-terminal")
                result = await handle_command(cmd, token)
                _ensure_not_cancelled(request_id)
                search_output = (result.get("reply", "") or "").strip()
                if not search_output:
                    search_output = "⚠️ web_search.py lieferte keine Ausgabe."
                thinking_steps.append(
                    {
                        "text": "Web-Suche abgeschlossen",
                        "icon": "fa-search",
                        "time": datetime.now().isoformat(),
                        "details": search_output[:1800],
                    }
                )

                # Wenn explizit eine Zusammenfassung gewünscht ist: Suche + LLM-Weiterverarbeitung
                if _wants_summary_after_search(sentences[0]):
                    selected_model = await asyncio.to_thread(
                        _auto_select_model,
                        sentences[0],
                        request.model,
                        request_id,
                    )
                    _progress_set_active_model(request_id, selected_model)
                    _progress_add(request_id, f"Zusammenfassung läuft mit {selected_model}", "fa-brain")
                    thinking_steps.append(
                        {
                            "text": f"Zusammenfassung mit Modell {selected_model}",
                            "icon": "fa-brain",
                            "time": datetime.now().isoformat(),
                        }
                    )
                    summary_prompt = (
                        "Fasse die folgenden Suchergebnisse strukturiert zusammen.\n"
                        "Liefere: 1) Kernaussagen 2) Chancen/Risiken 3) kurzer Ausblick.\n"
                        "Wichtig: Erfinde keine Tool-/Shell-/Slash-Befehle und schreibe keine '/shell ...' Zeilen.\n"
                        "Nutze klare Bullet-Points, ohne Meta-Kommentare.\n\n"
                        f"Nutzerfrage: {sentences[0]}\n\n"
                        "Suchergebnisse:\n"
                        f"{search_output[:18000]}"
                    )
                    messages = [
                        {"role": "system", "content": chat_memory.get_system_prompt()},
                        {"role": "user", "content": summary_prompt},
                    ]
                    response = await _ollama_chat_async(
                        model=selected_model,
                        messages=messages
                    )
                    _ensure_not_cancelled(request_id)
                    reply = _extract_ollama_text(response) or "⚠️ Keine Zusammenfassung erhalten."
                    chat_memory.add_to_memory(sentences[0], reply)
                    return {
                        "status": "success",
                        "reply": reply,
                        "timestamp": datetime.now().isoformat(),
                        "model_used": selected_model,
                        "tool_used": f"web_search.py -> Zusammenfassung ({selected_model})",
                        "thinking_steps": thinking_steps,
                        "request_id": request_id,
                    }
                
                return {
                    "status": "success",
                    "reply": f"**[GEDANKENGANG: Web-Suche für '{search_term}']**\n\n{search_output}",
                    "timestamp": datetime.now().isoformat(),
                    "tool_used": "web_search.py",
                    "thinking_steps": thinking_steps,
                    "request_id": request_id,
                }
            else:
                # Normale Unterhaltung
                logger.info(f"💬 Normale Unterhaltung: {sentences[0][:50]}...")
                _progress_add(request_id, "Normale Unterhaltung erkannt", "fa-comments")

                thinking_steps: List[Dict[str, str]] = []
                messages = [
                    {"role": "system", "content": chat_memory.get_system_prompt()}
                ]
                
                if chat_memory.conversation_history:
                    context_msgs = chat_memory.conversation_history[-10:]
                    messages.extend(context_msgs)

                messages.append({"role": "user", "content": sentences[0]})
                selected_model = await asyncio.to_thread(
                    _auto_select_model,
                    sentences[0],
                    request.model,
                    request_id,
                )
                _progress_set_active_model(request_id, selected_model)

                thinking_steps.append(
                    {
                        "text": f"Model-Routing: Antwort mit {selected_model}",
                        "icon": "fa-code-branch",
                        "time": datetime.now().isoformat(),
                    }
                )
                try:
                    models_info = await _ollama_list_models_async()
                    available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
                except Exception:
                    available = []
                precheck = await asyncio.to_thread(
                    _run_self_qa_precheck,
                    sentences[0],
                    available,
                    None,
                    request_id,
                )
                if precheck.get("analysis_context"):
                    # Insert before current user message so the model sees it as guidance.
                    messages.insert(len(messages) - 1, {"role": "system", "content": precheck["analysis_context"]})
                thinking_steps.extend(precheck.get("thinking_steps", []))
                
                _ensure_not_cancelled(request_id)
                _progress_add(request_id, f"Finale Antwort läuft mit {selected_model}", "fa-brain")
                response = await _ollama_chat_async(
                    model=selected_model,
                    messages=messages
                )
                _ensure_not_cancelled(request_id)
                _progress_add(request_id, "Antwort empfangen", "fa-check-circle")
                
                reply = _extract_ollama_text(response)
                if not (reply or "").strip():
                    reply = "⚠️ Das Modell hat keine Antwort geliefert."
                chat_memory.add_to_memory(sentences[0], reply)
                
                return {
                    "status": "success", 
                    "reply": reply,
                    "timestamp": datetime.now().isoformat(),
                    "model_used": selected_model,
                    "thinking_steps": thinking_steps,
                    "request_id": request_id,
                }
        
        # ===== 3. MEHRERE SÄTZE - JEDEN EINZELN BEHANDELN =====
        results = []
        combined_thinking_steps: List[Dict[str, str]] = []
        
        for i, sentence in enumerate(sentences):
            sentence_lower = sentence.lower()
            logger.info(f"🔄 Verarbeite Satz {i+1}: {sentence[:50]}...")
            
            # Prüfe ob dieser Satz einen Such-Trigger enthält
            is_search = any(trigger in sentence_lower for trigger in search_triggers)
            
            if is_search:
                # === WEB-SUCHE für diesen Satz ===
                # Extrahiere Suchbegriff
                search_term = _extract_search_term(sentence, search_triggers)
                logger.info(f"  🔍 Satz {i+1} ist eine SUCHE: '{search_term}'")
                
                # Führe Suche aus
                safe_search_term = search_term.replace('"', "'")
                cmd = f"/shell python tools/web_search.py \"{safe_search_term}\""
                _progress_add(request_id, f"Satz {i+1}: Web-Suche {search_term}", "fa-search")
                combined_thinking_steps.append(
                    {
                        "text": f"Satz {i+1}: Tool-Aufruf {cmd}",
                        "icon": "fa-terminal",
                        "time": datetime.now().isoformat(),
                    }
                )
                cmd_result = await handle_command(cmd, token)
                _ensure_not_cancelled(request_id)
                result_text = (cmd_result.get('reply', '') or '').strip() or '⚠️ web_search.py lieferte keine Ausgabe.'
                combined_thinking_steps.append(
                    {
                        "text": f"Satz {i+1}: Web-Suche abgeschlossen",
                        "icon": "fa-search",
                        "time": datetime.now().isoformat(),
                        "details": result_text[:1800],
                    }
                )
                
                results.append({
                    "type": "search",
                    "original": sentence,
                    "query": search_term,
                    "result": result_text
                })
                
            else:
                # === NORMALE UNTERHALTUNG für diesen Satz ===
                logger.info(f"  💬 Satz {i+1} ist NORMALE KONVERSATION")
                
                # Baue Konversations-Verlauf auf (inkl. vorheriger Ergebnisse)
                messages = [
                    {"role": "system", "content": chat_memory.get_system_prompt()}
                ]
                
                # Füge vorherige Ergebnisse als Kontext hinzu
                for prev_result in results:
                    if prev_result["type"] == "search":
                        messages.append({
                            "role": "assistant", 
                            "content": f"[Suchergebnis zu '{prev_result['query']}']\n{prev_result['result'][:8000]}"
                        })
                    else:
                        messages.append({
                            "role": "assistant",
                            "content": prev_result["result"]
                        })
                
                # Füge aktuellen Satz hinzu
                messages.append({"role": "user", "content": sentence})
                selected_model = await asyncio.to_thread(
                    _auto_select_model,
                    sentence,
                    request.model,
                    request_id,
                )
                _progress_set_active_model(request_id, selected_model)
                combined_thinking_steps.append(
                    {
                        "text": f"Satz {i+1}: Model-Routing -> {selected_model}",
                        "icon": "fa-code-branch",
                        "time": datetime.now().isoformat(),
                    }
                )
                try:
                    models_info = await _ollama_list_models_async()
                    available = [m.get("name") for m in models_info.get("models", []) if m.get("name")]
                except Exception:
                    available = []
                precheck = await asyncio.to_thread(
                    _run_self_qa_precheck,
                    sentence,
                    available,
                    None,
                    request_id,
                )
                if precheck.get("analysis_context"):
                    messages.insert(len(messages) - 1, {"role": "system", "content": precheck["analysis_context"]})
                combined_thinking_steps.extend(precheck.get("thinking_steps", []))
                
                # LLM Antwort
                _ensure_not_cancelled(request_id)
                _progress_add(request_id, f"Satz {i+1}: Antwort läuft mit {selected_model}", "fa-brain")
                response = await _ollama_chat_async(
                    model=selected_model,
                    messages=messages
                )
                _ensure_not_cancelled(request_id)
                
                reply = _extract_ollama_text(response)
                if not (reply or "").strip():
                    reply = "⚠️ Das Modell hat keine Antwort geliefert."
                
                results.append({
                    "type": "chat",
                    "original": sentence,
                    "result": reply
                })
                
                # In Memory speichern
                chat_memory.add_to_memory(sentence, reply)
        
        # ===== 4. ALLE ERGEBNISSE KOMBINIEREN =====
        combined_reply = ""
        for i, res in enumerate(results, 1):
            if res["type"] == "search":
                combined_reply += f"**🔍 Suche {i}:** {res['original']}\n\n{res['result']}\n\n---\n\n"
            else:
                combined_reply += f"**💬 Antwort {i}:**\n\n{res['result']}\n\n---\n\n"
        
        final_model_used = request.model
        if not final_model_used:
            final_model_used = await asyncio.to_thread(
                _auto_select_model,
                user_message,
                None,
                request_id,
            )

        return {
            "status": "success",
            "reply": combined_reply,
            "timestamp": datetime.now().isoformat(),
            "model_used": final_model_used,
            "thinking_steps": combined_thinking_steps,
            "request_id": request_id,
        }
    except ChatCancelled:
        _progress_add(request_id, "Anfrage wurde gestoppt", "fa-stop-circle")
        return {
            "status": "error",
            "message": "Anfrage gestoppt",
            "reply": "⏹️ Anfrage gestoppt.",
            "request_id": request_id,
        }
    except Exception as e:
        logger.error(f"Chat Fehler: {e}")
        _progress_add(request_id, f"Fehler: {e}", "fa-exclamation-triangle")
        return {
            "status": "error", 
            "message": str(e),
            "reply": f" {str(e)}",
            "request_id": request_id,
        }
    finally:
        _progress_mark_done(request_id)


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
    
    logger.info(f"Verarbeite Befehl: {command} mit Args: {args}")
    
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
            # Hier deine bestehende Logik für Befehle ohne Pipe
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
            
            # Normale Ausführung ohne Pipe
            shell_request = ShellRequest(command=args[0], 
                                       args=args[1:] if len(args) > 1 else [])
            result = await execute_command(shell_request, token)
            
            if result.get("status") == "success":
                output = result.get('stdout', '')
                if output:
                    return {
                        "status": "success",
                        "reply": f"```\n{output[:4000]}\n```"
                    }
                else:
                    return {
                        "status": "success",
                        "reply": f"✅ Befehl ausgeführt (keine Ausgabe)"
                    }
            else:
                return {
                    "status": "success",
                    "reply": f"❌ Fehler: {result.get('stderr', 'Unbekannter Fehler')}"
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
    elif command == "comfy":
        subcmd = args[0].lower() if args else "status"
        discovery = _get_tool_discovery(force=subcmd in ["scan", "discover"])
        comfy = discovery.get("comfyui", {})
        invoke = discovery.get("invoke", {})
        if subcmd in ["status", "scan", "discover"]:
            return {
                "status": "success",
                "reply": (
                    "🎨 **Bild-KI Discovery**\n\n"
                    f"- ComfyUI: {'✅ gefunden' if comfy.get('found') else '❌ nicht gefunden'}"
                    + (f"\n  - Pfad: `{comfy.get('root')}`" if comfy.get('root') else "")
                    + "\n"
                    f"- InvokeAI: {'✅ gefunden' if invoke.get('found') else '❌ nicht gefunden'}"
                    + (f"\n  - Binary: `{invoke.get('binary')}`" if invoke.get('binary') else "")
                    + (f"\n  - Root: `{invoke.get('root')}`" if invoke.get('root') else "")
                    + "\n"
                    f"- Gefundene Bildmodelle: {discovery.get('image_models_found', 0)}"
                ),
                "tool_used": "tool-discovery",
            }
        if subcmd == "start":
            start_info = _start_comfyui(discovery=discovery)
            if not start_info.get("ok"):
                return {
                    "status": "error",
                    "reply": f"❌ ComfyUI konnte nicht gestartet werden: {start_info.get('message')}",
                    "tool_used": "comfyui-start",
                }
            return {
                "status": "success",
                "reply": (
                    "✅ ComfyUI Start ausgelöst.\n"
                    f"- PID: {start_info.get('pid')}\n"
                    f"- CWD: `{start_info.get('cwd')}`\n"
                    f"- Command: `{start_info.get('command')}`"
                ),
                "tool_used": "comfyui-start",
                "command_executed": start_info.get("command"),
            }
        return {
            "status": "error",
            "reply": "❌ Unbekannter /comfy Befehl. Nutze `/comfy status`, `/comfy scan` oder `/comfy start`."
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
                from integrations.gmail_client import get_gmail_client
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
                from integrations.gmail_client import get_gmail_client
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

    **📊 SYSTEM:**
    `/status` - System-Status anzeigen
    `/comfy status` - ComfyUI/Invoke Discovery anzeigen
    `/comfy scan` - Discovery neu scannen
    `/comfy start` - ComfyUI automatisch starten (wenn gefunden)
    `/help` - Diese Hilfe

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
async def get_memory(_api_key: str = Depends(verify_api_key)):
    """Gibt das aktuelle Memory zurück"""
    return {
        "memory": chat_memory.memory_content,
        "skills": chat_memory.skills_content,
        "heartbeat": chat_memory.heartbeat_content,
        "remembered_notes": chat_memory.get_remembered_notes(limit=100),
        "conversation_count": len(chat_memory.conversation_history) // 2,
        "last_updated": datetime.now().isoformat(),
    }
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
            archive_name = f"MEMORY_ARCHIVE_{timestamp}.md"
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
# 🔥 NEU: Memory Reset Endpoint (mit GET und POST)
@router.api_route("/api/memory/reset", methods=["GET", "POST"])
async def reset_memory(_api_key: str = Depends(verify_api_key)):
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
async def memory_stats(_api_key: str = Depends(verify_api_key)):
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
async def list_allowed_commands(_api_key: str = Depends(verify_api_key)) -> dict:
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
        
        # Lese Datei direkt in Memory (kein temp file nötig für diesen Test)
        content = await file.read()
        logger.info(f"📦 Dateigröße: {len(content)} bytes")
        
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

# ============ Telegram Endpoints ============
@router.get("/api/telegram/status")
async def telegram_api_status(_api_key: str = Depends(verify_api_key)) -> dict:
    """Check Telegram bot status."""
    bot = get_telegram_bot()
    target_chat_ids = _get_telegram_target_chat_ids(bot)
    return {
        "enabled": config.get("telegram.enabled", False),
        "bot_token_set": bool(bot.bot_token and bot.bot_token != "YOUR_TELEGRAM_BOT_TOKEN"),
        "bot_running": bot.application is not None,
        "active_sessions": len(bot._user_sessions) if hasattr(bot, '_user_sessions') else 0,
        "configured_targets": target_chat_ids,
        "target_count": len(target_chat_ids)
    }

@router.post("/api/telegram/send")
async def send_telegram_message(
    payload: dict,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """Send a message to all active Telegram users."""
    message = payload.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    try:
        bot = get_telegram_bot()
        
        if not bot.bot_token or bot.bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
            return {
                "success": False, 
                "error": "Telegram bot not configured"
            }

        if not bot.application or not bot.application.bot:
            return {"success": False, "error": "Telegram bot not initialized"}

        explicit_targets = _parse_explicit_telegram_targets(payload.get("chat_ids"))
        if not explicit_targets and payload.get("chat_id") is not None:
            explicit_targets = _parse_explicit_telegram_targets(payload.get("chat_id"))

        target_chat_ids = explicit_targets or _get_telegram_target_chat_ids(bot)
        if not target_chat_ids:
            return {
                "success": False,
                "error": "Keine Telegram-Ziele gefunden. Setze telegram.chat_id, telegram.channel_id oder telegram.chat_ids in config.yaml."
            }

        sent_count = 0
        errors = []
        for chat_id in target_chat_ids:
            try:
                await bot.application.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode='Markdown'
                )
                sent_count += 1
            except Exception as e:
                errors.append(f"Chat {chat_id}: {str(e)}")

        return {
            "success": sent_count > 0,
            "message": f"Nachricht an {sent_count}/{len(target_chat_ids)} Ziele gesendet",
            "targets": target_chat_ids,
            "sent_count": sent_count,
            "errors": errors if errors else None
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
        model = config.get("ollama.default_model", "llama3.2")
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
    from integrations.gmail_client import gmail_client
    return gmail_client.get_latest_threads()

@router.get("/api/gmail/list")
async def list_gmail_messages(_api_key: str = Depends(verify_api_key)):
    """Gibt die Liste der neuesten Mails für die Seitenleiste zurück."""
    try:
        client = get_gmail_client()
        messages = client.list_messages(max_results=10)
        return messages
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

    # 1. Automatische Modell-Auswahl
    selected_model = select_best_model(prompt)
    
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
        current_model = config.get("ollama.default_model", "llama3.2")
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
