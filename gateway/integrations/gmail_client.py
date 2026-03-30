# integrations/gmail_client.py
"""Gmail API client."""

import os
import base64
import pickle
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from config import config

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/gmail.modify']


class GmailClient:
    """Gmail API client for reading and sending emails."""
    
    def __init__(self):
        self.service = None
        self.credentials = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Gmail API."""
        creds_file = config.get("gmail.credentials_file", "credentials.json")
        token_file = config.get("gmail.token_file", "token.pickle")
        
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
        
        self.service = build('gmail', 'v1', credentials=self.credentials)
        logger.info("✅ Gmail authenticated")
    
    def list_messages(self, max_results: int = 10, query: str = "") -> List[Dict[str, Any]]:
        """List messages from inbox."""
        try:
            results = self.service.users().messages().list(
                userId='me',
                maxResults=max_results,
                q=query
            ).execute()
            
            messages = results.get('messages', [])
            message_list = []
            
            for msg in messages:
                msg_data = self.service.users().messages().get(
                    userId='me',
                    id=msg['id'],
                    format='metadata',
                    metadataHeaders=['From', 'Subject', 'Date']
                ).execute()
                
                headers = msg_data.get('payload', {}).get('headers', [])
                message_list.append({
                    'id': msg['id'],
                    'threadId': msg_data.get('threadId'),
                    'subject': next((h['value'] for h in headers if h['name'] == 'Subject'), ''),
                    'from': next((h['value'] for h in headers if h['name'] == 'From'), ''),
                    'date': next((h['value'] for h in headers if h['name'] == 'Date'), ''),
                    'snippet': msg_data.get('snippet', '')
                })
            
            return message_list
        except Exception as e:
            logger.error(f"Gmail list error: {e}")
            return []
    
    def get_message(self, message_id: str) -> Dict[str, Any]:
        """Get full message by ID."""
        try:
            return self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
        except Exception as e:
            logger.error(f"Gmail get message error: {e}")
            return {}
    
    def get_message_body(self, message: Dict[str, Any]) -> str:
        """Extract message body from message."""
        def _get_part(parts):
            for part in parts:
                if part.get('mimeType') == 'text/plain':
                    data = part.get('body', {}).get('data', '')
                    if data:
                        return base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
                elif part.get('mimeType') == 'text/html':
                    data = part.get('body', {}).get('data', '')
                    if data:
                        html = base64.urlsafe_b64decode(data).decode('utf-8', errors='replace')
                        # Simple HTML to text conversion
                        import re
                        text = re.sub(r'<[^>]+>', ' ', html)
                        return ' '.join(text.split())
                elif 'parts' in part:
                    result = _get_part(part['parts'])
                    if result:
                        return result
            return ''
        
        payload = message.get('payload', {})
        if 'parts' in payload:
            return _get_part(payload['parts'])
        elif payload.get('body', {}).get('data'):
            return base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='replace')
        return message.get('snippet', '')
    
    def send_message(self, to: str, subject: str, body: str) -> Dict[str, Any]:
        """Send a new email."""
        try:
            message = self._create_message(to, subject, body)
            result = self.service.users().messages().send(
                userId='me',
                body={'raw': message}
            ).execute()
            return {'id': result.get('id'), 'success': True}
        except Exception as e:
            logger.error(f"Gmail send error: {e}")
            return {'error': str(e)}
    
    def send_reply(self, message_id: str, body: str) -> Dict[str, Any]:
        """Reply to an existing email."""
        try:
            original = self.get_message(message_id)
            headers = original.get('payload', {}).get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            from_addr = next((h['value'] for h in headers if h['name'] == 'From'), '')
            
            if not subject.startswith('Re:'):
                subject = f"Re: {subject}"
            
            message = self._create_message(from_addr, subject, body, in_reply_to=message_id)
            result = self.service.users().messages().send(
                userId='me',
                body={'raw': message}
            ).execute()
            return {'id': result.get('id'), 'success': True}
        except Exception as e:
            logger.error(f"Gmail reply error: {e}")
            return {'error': str(e)}
    
    def modify_message(self, message_id: str, add_labels: List[str] = None, remove_labels: List[str] = None) -> Dict[str, Any]:
        """Add or remove labels from a message."""
        try:
            body = {}
            if add_labels:
                body['addLabelIds'] = add_labels
            if remove_labels:
                body['removeLabelIds'] = remove_labels
            
            result = self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body=body
            ).execute()
            return {'success': True, 'result': result}
        except Exception as e:
            logger.error(f"Gmail modify error: {e}")
            return {'error': str(e)}
    
    def _create_message(self, to: str, subject: str, body: str, in_reply_to: str = None) -> str:
        """Create a raw email message."""
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        msg = MIMEMultipart('alternative')
        msg['To'] = to
        msg['Subject'] = subject
        
        if in_reply_to:
            msg['In-Reply-To'] = in_reply_to
            msg['References'] = in_reply_to
        
        part = MIMEText(body, 'plain', 'utf-8')
        msg.attach(part)
        
        return base64.urlsafe_b64encode(msg.as_bytes()).decode()


_gmail_client = None

def get_gmail_client() -> GmailClient:
    global _gmail_client
    if _gmail_client is None:
        _gmail_client = GmailClient()
    return _gmail_client