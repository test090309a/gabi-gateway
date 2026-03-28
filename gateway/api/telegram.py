# gateway/api/telegram.py
"""Telegram Bot API endpoints."""

import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Union
from fastapi import APIRouter, Header, HTTPException, Depends, Query

from gateway.auth import verify_token
from gateway.config import config
from gateway.core.memory import chat_memory

logger = logging.getLogger(__name__)

router = APIRouter()

# ===== Globale Variable für den Bot-Singleton =====
_shared_bot = None 

class TelegramBotWrapper:
    """
    Wrapper für den Telegram Bot mit Lazy-Import.
    Vermeidet Import-Fehler wenn Telegram nicht installiert ist.
    """
    
    _bot = None
    _available = None
    
    @classmethod
    def get_bot(cls):
        """Get or create Telegram bot instance."""
        if cls._bot is None and cls._available is not False:
            try:
                from gateway.integrations.telegram_bot import get_telegram_bot
                cls._bot = get_telegram_bot()
                cls._available = True
                logger.info("✅ Telegram bot initialized")
            except ImportError as e:
                logger.warning(f"⚠️ Telegram bot not available: {e}")
                cls._available = False
            except Exception as e:
                logger.error(f"❌ Telegram bot error: {e}")
                cls._available = False
        return cls._bot
    
    @classmethod
    def is_available(cls):
        """Check if Telegram bot is available."""
        if cls._available is None:
            cls.get_bot()
        return cls._available is True


def get_telegram_bot():
    """Get Telegram bot instance - uses the sync singleton."""
    from gateway.integrations.telegram_bot import get_telegram_bot_sync
    return get_telegram_bot_sync()

def is_telegram_enabled() -> bool:
    """Check if Telegram is enabled in config."""
    return config.get("telegram.enabled", False)


def _normalize_telegram_chat_id(raw_id: Any) -> Optional[Union[int, str]]:
    """
    Normalize chat id from config/session to int or @name string.
    
    Args:
        raw_id: Raw chat ID from config
        
    Returns:
        Normalized chat ID or None
    """
    if raw_id is None:
        return None
    
    if isinstance(raw_id, int):
        return raw_id
    
    text = str(raw_id).strip()
    if not text:
        return None
    
    # Numeric ID (positive or negative)
    if text.lstrip("-").isdigit():
        return int(text)
    
    # Channel/Group username
    if text.startswith("@"):
        return text
    
    return f"@{text}"


def _get_telegram_target_chat_ids(bot) -> List[Union[int, str]]:
    """
    Collect Telegram targets from active sessions and config.
    
    Args:
        bot: Telegram bot instance
        
    Returns:
        List of valid chat IDs
    """
    targets = set()
    
    # Active sessions (these are always valid user IDs)
    if hasattr(bot, "_user_sessions") and isinstance(bot._user_sessions, dict):
        targets.update(bot._user_sessions.keys())
    
    # Configured targets
    configured_raw: List[Any] = []
    for key in ("telegram.chat_id", "telegram.channel_id"):
        value = config.get(key)
        if value:
            configured_raw.append(value)
    
    # Legacy fallback
    telegram_cfg = config.data.get("telegram", {}) if isinstance(config.data, dict) else {}
    legacy_chat_id = telegram_cfg.get("telegram.chat_id") if isinstance(telegram_cfg, dict) else None
    if legacy_chat_id:
        configured_raw.append(legacy_chat_id)
    
    # Multiple chat IDs
    chat_ids_value = config.get("telegram.chat_ids", [])
    if isinstance(chat_ids_value, list):
        configured_raw.extend(chat_ids_value)
    elif isinstance(chat_ids_value, str) and chat_ids_value.strip():
        configured_raw.extend([part.strip() for part in chat_ids_value.split(",") if part.strip()])
    
    # Normalize and validate
    for raw in configured_raw:
        normalized = _normalize_telegram_chat_id(raw)
        if normalized is not None:
            t_str = str(normalized).strip()
            is_valid = (
                isinstance(normalized, int) or
                t_str.startswith("@") or
                t_str.replace("-", "").isdigit()
            )
            
            if is_valid:
                targets.add(normalized)
            else:
                logger.debug(f"Invalid Telegram target ignored: {raw} -> {normalized}")
    
    return list(targets)


def _parse_explicit_telegram_targets(raw_targets: Any) -> List[Union[int, str]]:
    """
    Parse explicit Telegram targets from API payload.
    
    Args:
        raw_targets: Raw targets from request
        
    Returns:
        List of parsed targets
    """
    parsed: List[Union[int, str]] = []
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


@router.get("/telegram/status")
async def telegram_status(
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Gibt den Status des Telegram Bots zurück.
    """
    enabled = is_telegram_enabled()
    bot = get_telegram_bot() if enabled else None
    
    status = {
        "status": "success",
        "enabled": enabled,
        "available": bot is not None if enabled else False,
        "bot_token_set": False,
        "bot_running": False,
        "active_sessions": 0,
        "configured_targets": [],
        "timestamp": datetime.now().isoformat()
    }
    
    if enabled and bot:
        status["bot_token_set"] = bool(bot.bot_token and bot.bot_token != "YOUR_TELEGRAM_BOT_TOKEN")
        status["bot_running"] = bot.application is not None
        status["active_sessions"] = len(bot._user_sessions) if hasattr(bot, '_user_sessions') else 0
        status["configured_targets"] = _get_telegram_target_chat_ids(bot)
    
    if not enabled:
        status["message"] = "Telegram ist in der config.yaml nicht aktiviert."
    elif not bot:
        status["message"] = "Telegram Bot nicht verfügbar."
    elif not status["bot_token_set"]:
        status["message"] = "Telegram Bot Token ist nicht konfiguriert."
    else:
        status["message"] = f"Telegram Bot bereit. {status['active_sessions']} aktive Session(s)."
    
    return status


@router.get("/telegram/users")
async def telegram_users(
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Zeigt alle aktiven Telegram-Benutzer an.
    """
    if not is_telegram_enabled():
        return {
            "status": "error",
            "message": "Telegram ist nicht aktiviert."
        }
    
    bot = get_telegram_bot()
    if not bot:
        return {
            "status": "error",
            "message": "Telegram Bot nicht verfügbar."
        }
    
    if not hasattr(bot, '_user_sessions') or not bot._user_sessions:
        return {
            "status": "success",
            "users": [],
            "count": 0,
            "message": "📭 Keine aktiven Telegram-Benutzer.\n\nBenutzer müssen dem Bot zuerst eine Nachricht schreiben."
        }
    
    reply = "👥 **Aktive Telegram-Benutzer:**\n\n"
    users_list = []
    
    for i, (user_id, session) in enumerate(bot._user_sessions.items(), 1):
        msg_count = len(session) // 2
        users_list.append({
            "id": user_id,
            "message_count": msg_count
        })
        
        reply += f"**{i}.** Benutzer ID: `{user_id}`\n"
        reply += f"   💬 {msg_count} Unterhaltungen\n"
        
        if session:
            last_msg = session[-1].get('content', '')[:50]
            reply += f"   📝 Letzte: {last_msg}...\n"
        reply += "\n"
    
    return {
        "status": "success",
        "users": users_list,
        "count": len(users_list),
        "reply": reply
    }


@router.post("/telegram/send")
async def send_telegram_message(
    payload: dict,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Sendet eine Nachricht an Telegram-Benutzer.
    
    Request Body:
    {
        "message": "Hallo Welt!",
        "chat_ids": ["123456789", "@channel"]  // Optional
    }
    """
    if not is_telegram_enabled():
        return {
            "status": "error",
            "message": "Telegram ist nicht aktiviert."
        }
    
    message = payload.get("message", "").strip()
    if not message:
        return {"status": "error", "message": "❌ Nachricht (message) ist erforderlich."}
    
    bot = get_telegram_bot()
    if not bot:
        return {
            "status": "error",
            "message": "Telegram Bot nicht verfügbar."
        }
    
    if not bot.application or not bot.application.bot:
        return {
            "status": "error",
            "message": "Telegram Bot nicht initialisiert."
        }
    
    # Parse targets
    raw_targets = payload.get("chat_ids") or payload.get("chat_id")
    explicit_targets = _parse_explicit_telegram_targets(raw_targets)
    
    # Validate targets
    valid_targets = []
    if explicit_targets:
        for t in explicit_targets:
            t_str = str(t).strip()
            if t_str.replace("-", "").isdigit() or t_str.startswith("@"):
                valid_targets.append(t_str)
    
    # Fallback to configured targets
    if not valid_targets:
        valid_targets = _get_telegram_target_chat_ids(bot)
    
    if not valid_targets:
        return {
            "status": "error",
            "message": "Keine gültigen Telegram-Ziele gefunden.\n\nSetze telegram.chat_id, telegram.channel_id oder telegram.chat_ids in der config.yaml."
        }
    
    # Send messages
    sent_count = 0
    failed_count = 0
    errors = []
    
    for chat_id in valid_targets:
        try:
            await bot.application.bot.send_message(
                chat_id=chat_id,
                text=message,
                parse_mode='Markdown'
            )
            sent_count += 1
        except Exception as e:
            failed_count += 1
            errors.append(f"Chat {chat_id}: {str(e)}")
    
    # Memory update
    if 'chat_memory' in globals():
        chat_memory.update_activity()
    
    if sent_count > 0 and failed_count == 0:
        return {
            "status": "success",
            "message": f"✅ Nachricht an {sent_count} Benutzer gesendet",
            "sent_count": sent_count,
            "failed_count": 0
        }
    elif sent_count > 0:
        return {
            "status": "success",
            "message": f"✅ Nachricht an {sent_count} Benutzer gesendet\n❌ Fehlgeschlagen: {failed_count}",
            "sent_count": sent_count,
            "failed_count": failed_count,
            "errors": errors[:5]
        }
    else:
        return {
            "status": "error",
            "message": f"❌ Konnte an keinen Benutzer senden",
            "sent_count": 0,
            "failed_count": failed_count,
            "errors": errors[:5]
        }


@router.post("/telegram/broadcast")
async def telegram_broadcast(
    payload: dict,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Sendet eine Broadcast-Nachricht an alle aktiven Telegram-Benutzer.
    Alias für /telegram/send.
    """
    return await send_telegram_message(payload, _api_key)


@router.get("/telegram/messages")
async def get_telegram_messages(
    since: int = Query(0, description="Timestamp in ms"),
    limit: int = Query(50, ge=1, le=200, description="Maximale Anzahl Nachrichten"),
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Ruft die letzten Telegram-Nachrichten ab.
    """
    if not is_telegram_enabled():
        return {
            "status": "error",
            "message": "Telegram ist nicht aktiviert."
        }
    
    bot = get_telegram_bot()
    if not bot:
        return {
            "status": "error",
            "message": "Telegram Bot nicht verfügbar."
        }
    
    # ===== DEBUG: Log Bot-Info =====
    # logger.info(f"📊 get_telegram_messages called")
    # logger.info(f"   bot id: {id(bot)}")
    # logger.info(f"   bot._user_sessions keys: {list(bot._user_sessions.keys()) if hasattr(bot, '_user_sessions') else 'no _user_sessions'}")
    # logger.info(f"   bot._running: {bot._running}")
    # logger.info(f"   bot.application: {bot.application is not None}")
    # ===============================
    
    try:
        all_messages = []
        message_counter = 0
        
        for user_id, session in bot._user_sessions.items():
            for msg in session:
                # Create unique ID
                unique_id = f"{user_id}-{message_counter}-{hash(msg.get('content', '')) % 10000}"
                
                msg_date = msg.get("timestamp", datetime.now().isoformat())
                
                # Filter by since timestamp
                if since > 0:
                    try:
                        msg_ts = datetime.fromisoformat(msg_date).timestamp() * 1000
                        if msg_ts < since:
                            continue
                    except:
                        pass
                
                message_entry = {
                    "id": unique_id,
                    "user_id": user_id,
                    "role": msg.get("role", "unknown"),
                    "from": f"User {user_id}" if msg.get("role") == "user" else "GABI Bot",
                    "text": msg.get("content", ""),
                    "date": msg_date
                }
                all_messages.append(message_entry)
                message_counter += 1
        
        # Sort by date (newest first)
        all_messages.sort(key=lambda x: x["date"], reverse=True)
        
        # Apply limit
        all_messages = all_messages[:limit]
        
        return {
            "status": "success",
            "messages": all_messages,
            "count": len(all_messages),
            "active_sessions": len(bot._user_sessions) if hasattr(bot, '_user_sessions') else 0
        }
        
    except Exception as e:
        logger.error(f"Telegram get messages error: {e}")
        return {
            "status": "error",
            "message": f"Fehler beim Abrufen: {str(e)}",
            "messages": [],
            "count": 0
        }


@router.post("/telegram/clear/{user_id}")
async def clear_user_session(
    user_id: str,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Löscht die Session eines Telegram-Benutzers.
    
    Args:
        user_id: Die ID des Benutzers
    """
    if not is_telegram_enabled():
        return {
            "status": "error",
            "message": "Telegram ist nicht aktiviert."
        }
    
    bot = get_telegram_bot()
    if not bot:
        return {
            "status": "error",
            "message": "Telegram Bot nicht verfügbar."
        }
    
    try:
        # Try as int
        try:
            user_id_int = int(user_id)
        except ValueError:
            user_id_int = user_id
        
        if hasattr(bot, '_user_sessions') and user_id_int in bot._user_sessions:
            del bot._user_sessions[user_id_int]
            return {
                "status": "success",
                "message": f"✅ Session für Benutzer {user_id} gelöscht"
            }
        else:
            return {
                "status": "error",
                "message": f"Benutzer {user_id} nicht gefunden"
            }
            
    except Exception as e:
        logger.error(f"Telegram clear session error: {e}")
        return {
            "status": "error",
            "message": f"Fehler beim Löschen: {str(e)}"
        }


@router.get("/telegram/help")
async def telegram_help(
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Zeigt Hilfe für Telegram-Befehle an.
    """
    help_text = """📱 **Telegram Bot Hilfe:**

**Was ist der Telegram Bot?**
Der Bot läuft als interaktiver Bot. Benutzer können ihm schreiben und er antwortet mit Ollama.

**Als Admin kannst du:**
• `/telegram status` - Bot-Status und Konfiguration prüfen
• `/telegram users` - Alle aktiven Benutzer anzeigen
• `/telegram send Hallo` - Nachricht an ALLE aktiven Benutzer senden
• `/telegram send --to 123456789 Hallo` - Direkt an eine Chat-ID senden
• `/telegram send --to @meinchannel Hallo` - Direkt an Kanal/Gruppe senden
• `/telegram messages` - Letzte Nachrichten abrufen
• `/telegram clear <user_id>` - Session eines Benutzers löschen

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

    return {
        "status": "success",
        "help": help_text
    }


# ===== HELPER FUNCTIONS =====

def format_telegram_message(text: str, max_length: int = 4096) -> str:
    """
    Formatiert eine Nachricht für Telegram.
    
    Args:
        text: Der Nachrichtentext
        max_length: Maximale Länge (Telegram Limit: 4096)
        
    Returns:
        Formatierte Nachricht
    """
    if not text:
        return ""
    
    # Telegram hat ein Limit von 4096 Zeichen pro Nachricht
    if len(text) > max_length:
        text = text[:max_length - 100] + "\n\n... (Nachricht gekürzt)"
    
    return text


def escape_markdown(text: str) -> str:
    """
    Escaped spezielle Markdown-Zeichen für Telegram.
    
    Args:
        text: Der zu escapende Text
        
    Returns:
        Escapeter Text
    """
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    
    return text


# Export für andere Module
__all__ = [
    "router",
    "get_telegram_bot",
    "is_telegram_enabled",
    "_normalize_telegram_chat_id",
    "_get_telegram_target_chat_ids",
    "format_telegram_message",
    "escape_markdown",
]