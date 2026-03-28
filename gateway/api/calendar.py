# gateway/api/calendar.py
"""Google Calendar API endpoints."""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Header, HTTPException, Depends, Query

from gateway.auth import verify_token
from gateway.config import config
from gateway.core.memory import chat_memory

logger = logging.getLogger(__name__)

router = APIRouter()


class CalendarClientWrapper:
    """
    Wrapper für den Google Calendar Client mit Lazy-Import.
    Vermeidet Import-Fehler wenn Calendar nicht installiert ist.
    """
    
    _client = None
    _available = None
    
    @classmethod
    def get_client(cls):
        """Get or create Calendar client."""
        if cls._client is None and cls._available is not False:
            try:
                from gateway.integrations.google_calendar_client import get_calendar_client
                cls._client = get_calendar_client()
                cls._available = True
                logger.info("✅ Google Calendar client initialized")
            except ImportError as e:
                logger.warning(f"⚠️ Google Calendar client not available: {e}")
                cls._available = False
            except Exception as e:
                logger.error(f"❌ Google Calendar client error: {e}")
                cls._available = False
        return cls._client
    
    @classmethod
    def is_available(cls):
        """Check if Calendar client is available."""
        if cls._available is None:
            cls.get_client()
        return cls._available is True


def get_calendar_client():
    """Get Calendar client instance."""
    return CalendarClientWrapper.get_client()


def is_calendar_enabled() -> bool:
    """Check if Calendar is enabled in config."""
    return config.get("calendar.enabled", False)


@router.get("/calendar/events")
async def list_events(
    max_results: int = Query(10, ge=1, le=50, description="Maximale Anzahl der Termine"),
    days_ahead: int = Query(7, ge=1, le=30, description="Tage in die Zukunft"),
    show_all: bool = Query(False, description="Alle Termine anzeigen (auch abgeschlossene)"),
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Zeigt bevorstehende Google Calendar Termine an.
    
    Args:
        max_results: Maximale Anzahl der Termine (1-50)
        days_ahead: Wie viele Tage in die Zukunft geschaut wird (1-30)
        show_all: Ob alle Termine (auch vergangene) angezeigt werden sollen
    """
    if not is_calendar_enabled():
        return {
            "status": "error",
            "message": "Google Calendar ist nicht aktiviert. Setze calendar.enabled=true in der config.yaml"
        }
    
    client = get_calendar_client()
    if not client:
        return {
            "status": "error",
            "message": "Google Calendar Client nicht verfügbar. Bitte überprüfe die Installation."
        }
    
    try:
        if show_all:
            # Alle Termine (auch vergangene) abrufen
            events = client.list_events(max_results=max_results, show_deleted=False)
            title = "📅 **Alle Kalendertermine:**\n\n"
        else:
            # Nur bevorstehende Termine
            events = client.list_upcoming_events(max_results=max_results, days_ahead=days_ahead)
            title = f"📅 **Bevorstehende Termine (nächste {days_ahead} Tage):**\n\n"
        
        if not events:
            if show_all:
                message = "📭 Keine Termine im Kalender gefunden."
            else:
                message = f"📭 Keine bevorstehenden Termine in den nächsten {days_ahead} Tagen."
            
            return {
                "status": "success",
                "events": [],
                "count": 0,
                "message": message
            }
        
        # Formatierte Antwort
        reply = title
        for i, event in enumerate(events, 1):
            summary = event.get('summary', '(Kein Titel)')
            start = event.get('start', 'Unbekannt')
            end = event.get('end', '')
            location = event.get('location', '')
            description = event.get('description', '')
            event_id = event.get('id', '')
            
            # Datum formatieren
            start_formatted = _format_datetime(start)
            end_formatted = _format_datetime(end) if end else ""
            
            reply += f"**{i}.** {summary}\n"
            reply += f"   🕒 {start_formatted}"
            if end_formatted:
                reply += f" - {end_formatted}"
            reply += "\n"
            
            if location:
                reply += f"   📍 {location}\n"
            
            if description:
                # Beschreibung auf 100 Zeichen kürzen
                desc_short = description[:100] + "..." if len(description) > 100 else description
                reply += f"   📝 {desc_short}\n"
            
            reply += f"   🆔 `{event_id}`\n\n"
        
        return {
            "status": "success",
            "events": events,
            "count": len(events),
            "reply": reply
        }
        
    except Exception as e:
        logger.error(f"Calendar list events error: {e}")
        return {
            "status": "error",
            "message": f"Fehler beim Abrufen der Termine: {str(e)}",
            "events": []
        }


@router.get("/calendar/event/{event_id}")
async def get_event(
    event_id: str,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Zeigt einen bestimmten Termin mit vollständigen Details an.
    
    Args:
        event_id: Die ID des Termins
    """
    if not is_calendar_enabled():
        return {
            "status": "error",
            "message": "Google Calendar ist nicht aktiviert."
        }
    
    client = get_calendar_client()
    if not client:
        return {
            "status": "error",
            "message": "Google Calendar Client nicht verfügbar."
        }
    
    try:
        event = client.get_event(event_id)
        
        if not event:
            return {
                "status": "error",
                "message": f"Termin mit ID '{event_id}' nicht gefunden."
            }
        
        # Details extrahieren
        summary = event.get('summary', '(Kein Titel)')
        start = event.get('start', 'Unbekannt')
        end = event.get('end', '')
        location = event.get('location', '')
        description = event.get('description', '')
        status = event.get('status', 'confirmed')
        created = event.get('created', '')
        updated = event.get('updated', '')
        html_link = event.get('htmlLink', '')
        
        # Teilnehmer
        attendees = event.get('attendees', [])
        
        # Datum formatieren
        start_formatted = _format_datetime(start)
        end_formatted = _format_datetime(end) if end else ""
        
        # Antwort formatieren
        reply = f"📅 **{summary}**\n\n"
        reply += f"**Start:** {start_formatted}\n"
        if end_formatted:
            reply += f"**Ende:** {end_formatted}\n"
        if location:
            reply += f"**Ort:** {location}\n"
        reply += f"**Status:** {_format_status(status)}\n"
        
        if attendees:
            reply += f"\n**Teilnehmer ({len(attendees)}):**\n"
            for attendee in attendees[:10]:
                email = attendee.get('email', '')
                response = attendee.get('responseStatus', 'needsAction')
                name = attendee.get('displayName', email.split('@')[0])
                status_icon = _get_attendee_status_icon(response)
                reply += f"   {status_icon} {name}\n"
            if len(attendees) > 10:
                reply += f"   ... und {len(attendees) - 10} weitere\n"
        
        if description:
            reply += f"\n**Beschreibung:**\n{description}\n"
        
        if created:
            reply += f"\n**Erstellt:** {_format_datetime(created)}\n"
        if updated:
            reply += f"**Aktualisiert:** {_format_datetime(updated)}\n"
        
        if html_link:
            reply += f"\n🔗 [In Google Calendar öffnen]({html_link})\n"
        
        return {
            "status": "success",
            "event": event,
            "reply": reply
        }
        
    except Exception as e:
        logger.error(f"Calendar get event error: {e}")
        return {
            "status": "error",
            "message": f"Fehler beim Abrufen des Termins: {str(e)}"
        }


@router.post("/calendar/event/create")
async def create_event(
    payload: dict,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Erstellt einen neuen Kalendertermin.
    
    Request Body:
    {
        "summary": "Meeting Titel",
        "start": "2024-01-15T10:00:00",
        "end": "2024-01-15T11:00:00",
        "location": "Büro",
        "description": "Besprechung über Projekt",
        "attendees": ["email1@example.com", "email2@example.com"]
    }
    """
    if not is_calendar_enabled():
        return {
            "status": "error",
            "message": "Google Calendar ist nicht aktiviert."
        }
    
    summary = payload.get("summary", "").strip()
    start = payload.get("start", "")
    end = payload.get("end", "")
    location = payload.get("location", "")
    description = payload.get("description", "")
    attendees = payload.get("attendees", [])
    
    if not summary:
        return {"status": "error", "message": "❌ Titel (summary) ist erforderlich."}
    
    if not start:
        return {"status": "error", "message": "❌ Startzeit (start) ist erforderlich."}
    
    client = get_calendar_client()
    if not client:
        return {
            "status": "error",
            "message": "Google Calendar Client nicht verfügbar."
        }
    
    try:
        event = {
            "summary": summary,
            "location": location,
            "description": description,
            "start": _parse_datetime(start),
            "end": _parse_datetime(end) if end else _parse_datetime(start, duration_hours=1),
        }
        
        if attendees:
            event["attendees"] = [{"email": email} for email in attendees]
        
        result = client.create_event(event)
        
        if result.get("error"):
            return {
                "status": "error",
                "message": f"❌ Erstellung fehlgeschlagen: {result.get('error')}"
            }
        
        # Zu Memory hinzufügen
        if 'chat_memory' in globals():
            chat_memory.update_activity()
        
        return {
            "status": "success",
            "message": f"✅ Termin erstellt: {summary}",
            "event_id": result.get("id"),
            "html_link": result.get("htmlLink")
        }
        
    except Exception as e:
        logger.error(f"Calendar create event error: {e}")
        return {
            "status": "error",
            "message": f"❌ Fehler beim Erstellen: {str(e)}"
        }


@router.post("/calendar/event/{event_id}/update")
async def update_event(
    event_id: str,
    payload: dict,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Aktualisiert einen bestehenden Termin.
    
    Args:
        event_id: Die ID des Termins
        
    Request Body:
    {
        "summary": "Neuer Titel",
        "start": "2024-01-15T10:00:00",
        "end": "2024-01-15T11:00:00",
        "location": "Neuer Ort",
        "description": "Neue Beschreibung"
    }
    """
    if not is_calendar_enabled():
        return {
            "status": "error",
            "message": "Google Calendar ist nicht aktiviert."
        }
    
    client = get_calendar_client()
    if not client:
        return {
            "status": "error",
            "message": "Google Calendar Client nicht verfügbar."
        }
    
    try:
        # Bestehenden Termin abrufen
        existing = client.get_event(event_id)
        if not existing:
            return {
                "status": "error",
                "message": f"Termin mit ID '{event_id}' nicht gefunden."
            }
        
        # Updates vorbereiten
        updates = {}
        
        if "summary" in payload:
            updates["summary"] = payload["summary"]
        if "location" in payload:
            updates["location"] = payload["location"]
        if "description" in payload:
            updates["description"] = payload["description"]
        if "start" in payload:
            updates["start"] = _parse_datetime(payload["start"])
        if "end" in payload:
            updates["end"] = _parse_datetime(payload["end"])
        
        if not updates:
            return {"status": "error", "message": "❌ Keine Änderungen angegeben."}
        
        result = client.update_event(event_id, updates)
        
        if result.get("error"):
            return {
                "status": "error",
                "message": f"❌ Aktualisierung fehlgeschlagen: {result.get('error')}"
            }
        
        return {
            "status": "success",
            "message": f"✅ Termin aktualisiert",
            "event_id": event_id
        }
        
    except Exception as e:
        logger.error(f"Calendar update event error: {e}")
        return {
            "status": "error",
            "message": f"❌ Fehler beim Aktualisieren: {str(e)}"
        }


@router.delete("/calendar/event/{event_id}")
async def delete_event(
    event_id: str,
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Löscht einen Termin.
    
    Args:
        event_id: Die ID des Termins
    """
    if not is_calendar_enabled():
        return {
            "status": "error",
            "message": "Google Calendar ist nicht aktiviert."
        }
    
    client = get_calendar_client()
    if not client:
        return {
            "status": "error",
            "message": "Google Calendar Client nicht verfügbar."
        }
    
    try:
        result = client.delete_event(event_id)
        
        if result.get("error"):
            return {
                "status": "error",
                "message": f"❌ Löschen fehlgeschlagen: {result.get('error')}"
            }
        
        return {
            "status": "success",
            "message": f"✅ Termin gelöscht",
            "event_id": event_id
        }
        
    except Exception as e:
        logger.error(f"Calendar delete event error: {e}")
        return {
            "status": "error",
            "message": f"❌ Fehler beim Löschen: {str(e)}"
        }


@router.get("/calendar/today")
async def get_today_events(
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Zeigt alle Termine für heute an.
    """
    if not is_calendar_enabled():
        return {
            "status": "error",
            "message": "Google Calendar ist nicht aktiviert."
        }
    
    client = get_calendar_client()
    if not client:
        return {
            "status": "error",
            "message": "Google Calendar Client nicht verfügbar."
        }
    
    try:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        
        events = client.list_events(
            time_min=today.isoformat() + 'Z',
            time_max=tomorrow.isoformat() + 'Z',
            max_results=50
        )
        
        today_str = today.strftime("%d.%m.%Y")
        
        if not events:
            return {
                "status": "success",
                "events": [],
                "count": 0,
                "message": f"📭 Keine Termine für heute ({today_str})."
            }
        
        reply = f"📅 **Termine für heute ({today_str}):**\n\n"
        for i, event in enumerate(events, 1):
            summary = event.get('summary', '(Kein Titel)')
            start = event.get('start', '')
            location = event.get('location', '')
            
            start_formatted = _format_time(start) if start else "?"
            
            reply += f"**{i}.** {start_formatted} - {summary}\n"
            if location:
                reply += f"   📍 {location}\n"
            reply += "\n"
        
        return {
            "status": "success",
            "events": events,
            "count": len(events),
            "reply": reply
        }
        
    except Exception as e:
        logger.error(f"Calendar today events error: {e}")
        return {
            "status": "error",
            "message": f"Fehler beim Abrufen: {str(e)}"
        }


@router.get("/calendar/status")
async def calendar_status(
    _api_key: str = Depends(verify_token)
) -> Dict[str, Any]:
    """
    Gibt den Status des Google Calendar Clients zurück.
    """
    enabled = is_calendar_enabled()
    client = get_calendar_client()
    available = client is not None
    
    status = {
        "status": "success",
        "enabled": enabled,
        "available": available,
        "configured": bool(config.get("calendar.credentials_file")),
        "timestamp": datetime.now().isoformat()
    }
    
    if not enabled:
        status["message"] = "Google Calendar ist in der config.yaml nicht aktiviert."
    elif not available:
        status["message"] = "Google Calendar Client nicht verfügbar. Bitte überprüfe die Installation."
    else:
        status["message"] = "Google Calendar Client bereit."
    
    return status


# ===== HELPER FUNCTIONS =====

def _format_datetime(dt_str: str) -> str:
    """
    Formatiert einen Datums-String lesbar.
    
    Args:
        dt_str: ISO-Format Datumsstring
        
    Returns:
        Formatierter String (z.B. "15.01.2024 10:00")
    """
    if not dt_str:
        return ""
    
    try:
        # Entferne Zeitzonen-Info
        dt_str = dt_str.replace('Z', '+00:00')
        
        # Parsen
        if 'T' in dt_str:
            dt = datetime.fromisoformat(dt_str)
            return dt.strftime("%d.%m.%Y %H:%M")
        else:
            dt = datetime.fromisoformat(dt_str)
            return dt.strftime("%d.%m.%Y")
    except:
        return dt_str


def _format_time(dt_str: str) -> str:
    """
    Formatiert nur die Uhrzeit.
    
    Args:
        dt_str: ISO-Format Datumsstring
        
    Returns:
        Formatierte Uhrzeit (z.B. "10:00")
    """
    if not dt_str:
        return ""
    
    try:
        dt_str = dt_str.replace('Z', '+00:00')
        if 'T' in dt_str:
            dt = datetime.fromisoformat(dt_str)
            return dt.strftime("%H:%M")
        return dt_str
    except:
        return dt_str


def _parse_datetime(dt_str: str, duration_hours: int = 1) -> Dict[str, str]:
    """
    Parst einen Datums-String in das Calendar-Format.
    
    Args:
        dt_str: Datumsstring (ISO oder lesbares Format)
        duration_hours: Dauer in Stunden wenn nur Start angegeben
        
    Returns:
        Dict mit 'dateTime' und 'timeZone'
    """
    try:
        # Versuche ISO-Format
        if 'T' in dt_str:
            dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        else:
            # Versuche deutsches Format
            try:
                dt = datetime.strptime(dt_str, "%d.%m.%Y %H:%M")
            except:
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
        
        return {
            "dateTime": dt.isoformat(),
            "timeZone": "Europe/Berlin"
        }
    except:
        # Fallback: aktueller Zeitpunkt + Dauer
        dt = datetime.now()
        return {
            "dateTime": dt.isoformat(),
            "timeZone": "Europe/Berlin"
        }


def _format_status(status: str) -> str:
    """
    Formatiert den Status eines Termins.
    
    Args:
        status: Status-String (confirmed, cancelled, etc.)
        
    Returns:
        Formatierter Status mit Emoji
    """
    status_map = {
        "confirmed": "✅ Bestätigt",
        "cancelled": "❌ Abgesagt",
        "tentative": "❓ Vorläufig",
    }
    return status_map.get(status, status)


def _get_attendee_status_icon(status: str) -> str:
    """
    Gibt ein Icon für den Teilnehmer-Status zurück.
    
    Args:
        status: Status (accepted, declined, tentative, needsAction)
        
    Returns:
        Emoji-String
    """
    status_map = {
        "accepted": "✅",
        "declined": "❌",
        "tentative": "❓",
        "needsAction": "⏳",
    }
    return status_map.get(status, "👤")


# Export für andere Module
__all__ = [
    "router",
    "get_calendar_client",
    "is_calendar_enabled",
    "_format_datetime",
    "_parse_datetime",
]