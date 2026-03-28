# gateway/api/gmail.py
"""Gmail API endpoints."""

import logging
import base64
import re
from datetime import datetime
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Header, HTTPException, Depends, Query

from gateway.auth import verify_token
from gateway.config import config
from gateway.core.memory import chat_memory

logger = logging.getLogger(__name__)

router = APIRouter()


class GmailClientWrapper:
    """
    Wrapper für den Gmail Client mit Lazy-Import.
    Vermeidet Import-Fehler wenn Gmail nicht installiert ist.
    """
    
    _client = None
    _available = None
    
    @classmethod
    def get_client(cls):
        """Get or create Gmail client."""
        if cls._client is None and cls._available is not False:
            try:
                from gateway.integrations.gmail_client import get_gmail_client
                cls._client = get_gmail_client()
                cls._available = True
                logger.info("✅ Gmail client initialized")
            except ImportError as e:
                logger.warning(f"⚠️ Gmail client not available: {e}")
                cls._available = False
            except Exception as e:
                logger.error(f"❌ Gmail client error: {e}")
                cls._available = False
        return cls._client
    
    @classmethod
    def is_available(cls):
        """Check if Gmail client is available."""
        if cls._available is None:
            cls.get_client()
        return cls._available is True


def get_gmail_client():
    """Get Gmail client instance."""
    return GmailClientWrapper.get_client()


def is_gmail_enabled() -> bool:
    """Check if Gmail is enabled in config."""
    return config.get("gmail.enabled", False)


@router.get("/gmail/inbox")
async def get_inbox(
    max_results: int = Query(10, ge=1, le=50),
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Zeigt die neuesten E-Mails aus dem Posteingang an.
    
    Args:
        max_results: Maximale Anzahl der E-Mails (1-50)
    """
    if not is_gmail_enabled():
        return {
            "status": "error",
            "message": "Gmail ist nicht aktiviert. Setze gmail.enabled=true in der config.yaml"
        }
    
    client = get_gmail_client()
    if not client:
        return {
            "status": "error",
            "message": "Gmail-Client nicht verfügbar. Bitte überprüfe die Installation."
        }
    
    try:
        messages = client.list_messages(max_results=max_results)
        
        if not messages:
            return {
                "status": "success",
                "messages": [],
                "count": 0,
                "message": "📭 Keine E-Mails im Posteingang gefunden."
            }
        
        # Formatierte Antwort
        reply = "📬 **Deine neuesten E-Mails:**\n\n"
        for i, msg in enumerate(messages, 1):
            subject = msg.get('subject', 'kein Betreff')
            from_addr = msg.get('from', 'unbekannt')
            date = msg.get('date', 'unbekannt')
            msg_id = msg.get('id', '')
            
            reply += f"**{i}.** {subject}\n"
            reply += f"   📅 {date}\n"
            reply += f"   👤 {from_addr}\n"
            reply += f"   🆔 `{msg_id}`\n\n"
        
        return {
            "status": "success",
            "messages": messages,
            "count": len(messages),
            "reply": reply
        }
        
    except Exception as e:
        logger.error(f"Gmail inbox error: {e}")
        return {
            "status": "error",
            "message": f"Fehler beim Abrufen der E-Mails: {str(e)}",
            "messages": []
        }


@router.get("/gmail/message/{message_id}")
async def get_message(
    message_id: str,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Zeigt eine bestimmte E-Mail mit vollständigem Inhalt an.
    
    Args:
        message_id: Die ID der E-Mail
    """
    if not is_gmail_enabled():
        return {
            "status": "error",
            "message": "Gmail ist nicht aktiviert."
        }
    
    client = get_gmail_client()
    if not client:
        return {
            "status": "error",
            "message": "Gmail-Client nicht verfügbar."
        }
    
    try:
        # Nachricht abrufen
        message = client.get_message(message_id)
        if not message:
            return {
                "status": "error",
                "message": f"E-Mail mit ID '{message_id}' nicht gefunden."
            }
        
        # Header extrahieren
        headers = message.get('payload', {}).get('headers', [])
        header_map = {h.get('name', '').lower(): h.get('value', '') for h in headers}
        
        subject = header_map.get('subject', 'kein Betreff')
        from_addr = header_map.get('from', 'unbekannt')
        to_addr = header_map.get('to', 'unbekannt')
        date = header_map.get('date', 'unbekannt')
        
        # Body extrahieren
        try:
            body = client.get_message_body(message)
        except Exception:
            body = message.get('snippet', '(Inhalt konnte nicht dekodiert werden)')
        
        # Antwort formatieren
        reply = f"📧 **{subject}**\n\n"
        reply += f"**Von:** {from_addr}\n"
        reply += f"**An:** {to_addr}\n"
        reply += f"**Datum:** {date}\n\n"
        reply += f"**Inhalt:**\n{body}"
        
        # Zu Memory hinzufügen
        if 'chat_memory' in globals():
            chat_memory.update_activity()
        
        return {
            "status": "success",
            "id": message_id,
            "subject": subject,
            "from": from_addr,
            "to": to_addr,
            "date": date,
            "body": body,
            "snippet": message.get('snippet', ''),
            "reply": reply
        }
        
    except Exception as e:
        logger.error(f"Gmail get message error: {e}")
        return {
            "status": "error",
            "message": f"Fehler beim Abrufen der E-Mail: {str(e)}"
        }


@router.post("/gmail/send")
async def send_message(
    payload: dict,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Sendet eine neue E-Mail.
    
    Request Body:
    {
        "to": "empfaenger@example.com",
        "subject": "Betreff",
        "body": "Nachrichtentext"
    }
    """
    if not is_gmail_enabled():
        return {
            "status": "error",
            "message": "Gmail ist nicht aktiviert."
        }
    
    to = payload.get("to", "").strip()
    subject = payload.get("subject", "").strip()
    body = payload.get("body", "").strip()
    
    if not to:
        return {"status": "error", "message": "❌ Empfänger (to) ist erforderlich."}
    
    if not body:
        return {"status": "error", "message": "❌ Nachrichtentext (body) ist erforderlich."}
    
    client = get_gmail_client()
    if not client:
        return {
            "status": "error",
            "message": "Gmail-Client nicht verfügbar."
        }
    
    try:
        result = client.send_message(to, subject, body)
        
        if result.get("error"):
            return {
                "status": "error",
                "message": f"❌ Senden fehlgeschlagen: {result.get('error')}"
            }
        
        # Zu Memory hinzufügen
        if 'chat_memory' in globals():
            chat_memory.update_activity()
        
        return {
            "status": "success",
            "message": f"✅ E-Mail gesendet an {to}",
            "message_id": result.get("id")
        }
        
    except Exception as e:
        logger.error(f"Gmail send error: {e}")
        return {
            "status": "error",
            "message": f"❌ Fehler beim Senden: {str(e)}"
        }


@router.post("/gmail/reply/{message_id}")
async def reply_to_message(
    message_id: str,
    payload: dict,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Antwortet auf eine bestehende E-Mail.
    
    Args:
        message_id: ID der E-Mail, auf die geantwortet wird
        
    Request Body:
    {
        "body": "Antworttext"
    }
    """
    if not is_gmail_enabled():
        return {
            "status": "error",
            "message": "Gmail ist nicht aktiviert."
        }
    
    body = payload.get("body", "").strip()
    
    if not body:
        return {"status": "error", "message": "❌ Antworttext (body) ist erforderlich."}
    
    client = get_gmail_client()
    if not client:
        return {
            "status": "error",
            "message": "Gmail-Client nicht verfügbar."
        }
    
    try:
        result = client.send_reply(message_id, body)
        
        if result.get("error"):
            return {
                "status": "error",
                "message": f"❌ Antwort fehlgeschlagen: {result.get('error')}"
            }
        
        # Zu Memory hinzufügen
        if 'chat_memory' in globals():
            chat_memory.update_activity()
        
        return {
            "status": "success",
            "message": f"✅ Antwort gesendet (ID: {result.get('id', 'unbekannt')})",
            "message_id": result.get("id")
        }
        
    except Exception as e:
        logger.error(f"Gmail reply error: {e}")
        return {
            "status": "error",
            "message": f"❌ Fehler beim Antworten: {str(e)}"
        }


@router.post("/gmail/message/{message_id}/modify")
async def modify_message(
    message_id: str,
    payload: dict,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Ändert Labels einer E-Mail (archivieren, sternen, etc.).
    
    Args:
        message_id: ID der E-Mail
        
    Request Body:
    {
        "add_labels": ["STARRED", "IMPORTANT"],
        "remove_labels": ["UNREAD", "INBOX"]
    }
    """
    if not is_gmail_enabled():
        return {
            "status": "error",
            "message": "Gmail ist nicht aktiviert."
        }
    
    add_labels = payload.get("add_labels", [])
    remove_labels = payload.get("remove_labels", [])
    
    if not add_labels and not remove_labels:
        return {
            "status": "error",
            "message": "❌ Bitte mindestens add_labels oder remove_labels angeben."
        }
    
    client = get_gmail_client()
    if not client:
        return {
            "status": "error",
            "message": "Gmail-Client nicht verfügbar."
        }
    
    try:
        result = client.modify_message(message_id, add_labels, remove_labels)
        
        if result.get("error"):
            return {
                "status": "error",
                "message": f"❌ Änderung fehlgeschlagen: {result.get('error')}"
            }
        
        return {
            "status": "success",
            "message": f"✅ Labels aktualisiert",
            "added": add_labels,
            "removed": remove_labels
        }
        
    except Exception as e:
        logger.error(f"Gmail modify error: {e}")
        return {
            "status": "error",
            "message": f"❌ Fehler beim Ändern: {str(e)}"
        }


@router.get("/gmail/search")
async def search_messages(
    query: str = Query(..., description="Suchbegriff"),
    max_results: int = Query(10, ge=1, le=50),
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Durchsucht E-Mails nach einem Suchbegriff.
    
    Args:
        query: Suchbegriff (z.B. "from:user@example.com", "subject:test")
        max_results: Maximale Anzahl der Ergebnisse
    """
    if not is_gmail_enabled():
        return {
            "status": "error",
            "message": "Gmail ist nicht aktiviert."
        }
    
    client = get_gmail_client()
    if not client:
        return {
            "status": "error",
            "message": "Gmail-Client nicht verfügbar."
        }
    
    try:
        messages = client.list_messages(query=query, max_results=max_results)
        
        if not messages:
            return {
                "status": "success",
                "messages": [],
                "count": 0,
                "message": f"🔍 Keine E-Mails gefunden für '{query}'."
            }
        
        reply = f"🔍 **Suchergebnisse für '{query}':**\n\n"
        for i, msg in enumerate(messages, 1):
            subject = msg.get('subject', 'kein Betreff')
            from_addr = msg.get('from', 'unbekannt')
            date = msg.get('date', 'unbekannt')
            msg_id = msg.get('id', '')
            
            reply += f"**{i}.** {subject}\n"
            reply += f"   📅 {date}\n"
            reply += f"   👤 {from_addr}\n"
            reply += f"   🆔 `{msg_id}`\n\n"
        
        return {
            "status": "success",
            "messages": messages,
            "count": len(messages),
            "query": query,
            "reply": reply
        }
        
    except Exception as e:
        logger.error(f"Gmail search error: {e}")
        return {
            "status": "error",
            "message": f"❌ Fehler bei der Suche: {str(e)}"
        }


@router.get("/gmail/status")
async def gmail_status(
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Gibt den Status des Gmail-Clients zurück.
    """
    enabled = is_gmail_enabled()
    client = get_gmail_client()
    available = client is not None
    
    status = {
        "status": "success",
        "enabled": enabled,
        "available": available,
        "configured": bool(config.get("gmail.credentials_file")),
        "timestamp": datetime.now().isoformat()
    }
    
    if not enabled:
        status["message"] = "Gmail ist in der config.yaml nicht aktiviert."
    elif not available:
        status["message"] = "Gmail-Client nicht verfügbar. Bitte überprüfe die Installation."
    else:
        status["message"] = "Gmail-Client bereit."
    
    return status


# ===== HELPER FUNCTIONS =====

def extract_email_body(raw_body: str) -> str:
    """
    Extrahiert den Text aus einer HTML-E-Mail.
    
    Args:
        raw_body: HTML- oder Text-Body
        
    Returns:
        Reiner Text
    """
    if not raw_body:
        return ""
    
    # Entferne HTML-Tags
    body = re.sub(r'<[^>]+>', ' ', raw_body)
    
    # Entferne HTML-Entities
    body = body.replace('&nbsp;', ' ')
    body = body.replace('&amp;', '&')
    body = body.replace('&lt;', '<')
    body = body.replace('&gt;', '>')
    body = body.replace('&quot;', '"')
    
    # Entferne mehrfache Leerzeichen
    body = re.sub(r'\s+', ' ', body)
    
    # Entferne führende/nachfolgende Leerzeichen
    body = body.strip()
    
    return body


def format_email_address(address: str) -> str:
    """
    Formatiert eine E-Mail-Adresse lesbar.
    
    Args:
        address: E-Mail-Adresse (z.B. "Name <email@example.com>")
        
    Returns:
        Formatierte Adresse
    """
    if not address:
        return ""
    
    # Extrahiere Name und E-Mail
    match = re.match(r'^(.*?)\s*<(.+?)>$', address)
    if match:
        name = match.group(1).strip()
        email = match.group(2).strip()
        if name and name != email:
            return f"{name} <{email}>"
        return email
    
    return address


# Export für andere Module
__all__ = [
    "router",
    "get_gmail_client",
    "is_gmail_enabled",
    "extract_email_body",
    "format_email_address",
]