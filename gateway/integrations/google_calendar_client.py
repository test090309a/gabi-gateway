# integrations/google_calendar_client.py
"""Google Calendar API client."""

import os
import pickle
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from gateway.config import config

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/calendar']


class GoogleCalendarClient:
    """Google Calendar API client."""
    
    def __init__(self):
        self.service = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Google Calendar API."""
        creds_file = config.get("calendar.credentials_file", "calendar_credentials.json")
        token_file = config.get("calendar.token_file", "calendar_token.pickle")
        
        if os.path.exists(token_file):
            with open(token_file, 'rb') as token:
                self.credentials = pickle.load(token)
        
        if not self.credentials or not self.credentials.valid:
            if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                self.credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
                self.credentials = flow.run_local_server(port=0)
            
            with open(token_file, 'wb') as token:
                pickle.dump(self.credentials, token)
        
        self.service = build('calendar', 'v3', credentials=self.credentials)
        logger.info("✅ Google Calendar authenticated")
    
    def list_upcoming_events(self, max_results: int = 10, days_ahead: int = 7) -> List[Dict[str, Any]]:
        """List upcoming events."""
        now = datetime.utcnow().isoformat() + 'Z'
        time_max = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + 'Z'
        
        try:
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=now,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            formatted_events = []
            
            for event in events:
                start = event['start'].get('dateTime', event['start'].get('date'))
                end = event['end'].get('dateTime', event['end'].get('date'))
                
                formatted_events.append({
                    'id': event['id'],
                    'summary': event.get('summary', ''),
                    'start': start,
                    'end': end,
                    'location': event.get('location', ''),
                    'description': event.get('description', ''),
                    'status': event.get('status', '')
                })
            
            return formatted_events
        except Exception as e:
            logger.error(f"Calendar list error: {e}")
            return []
    
    def list_events(self, max_results: int = 10, time_min: str = None, time_max: str = None) -> List[Dict[str, Any]]:
        """List events with custom time range."""
        try:
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            return [{
                'id': e['id'],
                'summary': e.get('summary', ''),
                'start': e['start'].get('dateTime', e['start'].get('date')),
                'end': e['end'].get('dateTime', e['end'].get('date')),
                'location': e.get('location', ''),
                'description': e.get('description', '')
            } for e in events]
        except Exception as e:
            logger.error(f"Calendar list error: {e}")
            return []
    
    def get_event(self, event_id: str) -> Dict[str, Any]:
        """Get a specific event."""
        try:
            event = self.service.events().get(
                calendarId='primary',
                eventId=event_id
            ).execute()
            
            return {
                'id': event['id'],
                'summary': event.get('summary', ''),
                'start': event['start'].get('dateTime', event['start'].get('date')),
                'end': event['end'].get('dateTime', event['end'].get('date')),
                'location': event.get('location', ''),
                'description': event.get('description', ''),
                'status': event.get('status', ''),
                'created': event.get('created', ''),
                'updated': event.get('updated', ''),
                'htmlLink': event.get('htmlLink', ''),
                'attendees': event.get('attendees', [])
            }
        except Exception as e:
            logger.error(f"Calendar get event error: {e}")
            return {}
    
    def create_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new event."""
        try:
            result = self.service.events().insert(
                calendarId='primary',
                body=event
            ).execute()
            return {'id': result.get('id'), 'htmlLink': result.get('htmlLink')}
        except Exception as e:
            logger.error(f"Calendar create error: {e}")
            return {'error': str(e)}
    
    def update_event(self, event_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing event."""
        try:
            event = self.service.events().get(
                calendarId='primary',
                eventId=event_id
            ).execute()
            
            for key, value in updates.items():
                if value:
                    event[key] = value
            
            result = self.service.events().update(
                calendarId='primary',
                eventId=event_id,
                body=event
            ).execute()
            return {'id': result.get('id')}
        except Exception as e:
            logger.error(f"Calendar update error: {e}")
            return {'error': str(e)}
    
    def delete_event(self, event_id: str) -> Dict[str, Any]:
        """Delete an event."""
        try:
            self.service.events().delete(
                calendarId='primary',
                eventId=event_id
            ).execute()
            return {'success': True}
        except Exception as e:
            logger.error(f"Calendar delete error: {e}")
            return {'error': str(e)}


_calendar_client = None

def get_calendar_client() -> GoogleCalendarClient:
    global _calendar_client
    if _calendar_client is None:
        _calendar_client = GoogleCalendarClient()
    return _calendar_client