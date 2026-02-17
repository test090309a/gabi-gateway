"""Google Calendar client using ADC credentials."""
import logging
from datetime import datetime, timezone
from typing import Any

import google.auth
from googleapiclient.discovery import build

logger = logging.getLogger("calendar")


class GoogleCalendarClient:
    """Simple Google Calendar API client."""

    def __init__(self):
        self.service = None
        self._authenticate()

    def _authenticate(self) -> None:
        try:
            creds, project = google.auth.default(
                scopes=["https://www.googleapis.com/auth/calendar.readonly"]
            )
            self.service = build("calendar", "v3", credentials=creds)
            logger.info(f"Calendar: Authentifiziert via ADC (Project: {project})")
        except Exception as e:
            logger.error(f"Calendar Auth Fehler: {e}")
            self.service = None

    def list_upcoming_events(self, max_results: int = 10, calendar_id: str = "primary") -> list[dict[str, Any]]:
        if not self.service:
            return []
        now = datetime.now(timezone.utc).isoformat()
        events_result = (
            self.service.events()
            .list(
                calendarId=calendar_id,
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])
        parsed: list[dict[str, Any]] = []
        for event in events:
            start = event.get("start", {}).get("dateTime") or event.get("start", {}).get("date")
            end = event.get("end", {}).get("dateTime") or event.get("end", {}).get("date")
            parsed.append(
                {
                    "id": event.get("id"),
                    "summary": event.get("summary", "(Ohne Titel)"),
                    "description": event.get("description", ""),
                    "location": event.get("location", ""),
                    "start": start,
                    "end": end,
                    "htmlLink": event.get("htmlLink", ""),
                }
            )
        return parsed


_calendar_client = None


def get_calendar_client() -> GoogleCalendarClient:
    global _calendar_client
    if _calendar_client is None:
        _calendar_client = GoogleCalendarClient()
    return _calendar_client

