"""Gmail client with ADC (Application Default Credentials) authentication."""
import base64
import logging
from email.message import EmailMessage
from typing import Any, Optional

import google.auth
from googleapiclient.discovery import build

logger = logging.getLogger("gmail")


class GmailClient:
    """Gmail API client using Application Default Credentials."""

    def __init__(self):
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate using Google Application Default Credentials."""
        try:
            creds, project = google.auth.default(
                scopes=[
                    "https://www.googleapis.com/auth/gmail.readonly",
                    "https://www.googleapis.com/auth/gmail.send",
                    "https://www.googleapis.com/auth/gmail.modify",
                ]
            )
            self.service = build("gmail", "v1", credentials=creds)
            logger.info(f"Gmail: Authentifiziert via ADC (Project: {project})")
        except Exception as e:
            logger.error(f"Gmail: Auth-Fehler - {e}")
            self.service = None

    def _decode_data(self, data: str) -> str:
        if not data:
            return ""
        try:
            return base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")
        except Exception:
            return ""

    def _extract_part_text(self, payload: dict, mime_types: Optional[list[str]] = None) -> str:
        """Extract first matching body text recursively from payload parts."""
        mime_types = mime_types or ["text/plain", "text/html"]
        if not payload:
            return ""

        mime_type = payload.get("mimeType", "")
        body_data = payload.get("body", {}).get("data", "")
        if mime_type in mime_types and body_data:
            return self._decode_data(body_data)

        for part in payload.get("parts", []) or []:
            text = self._extract_part_text(part, mime_types)
            if text:
                return text
        return ""

    def get_message(self, message_id: str, fmt: str = "full") -> dict:
        """Fetch a Gmail message by id."""
        if not self.service:
            raise RuntimeError("Gmail service not available")
        return self.service.users().messages().get(userId="me", id=message_id, format=fmt).execute()

    def get_message_body(self, message: dict) -> str:
        """Extract readable message body from Gmail API message."""
        payload = message.get("payload", {})
        body = self._extract_part_text(payload, ["text/plain"])
        if not body:
            body = self._extract_part_text(payload, ["text/html"])
        if not body:
            body = message.get("snippet", "")
        return body

    def list_messages(self, max_results: int = 10, query: str = "") -> list[dict]:
        """List newest messages with metadata for UI."""
        if not self.service:
            return []
        try:
            results = self.service.users().messages().list(
                userId="me", maxResults=max_results, q=query
            ).execute()
            messages = results.get("messages", [])
            detailed_messages: list[dict] = []
            for msg in messages:
                meta = self.get_message(msg["id"], fmt="metadata")
                headers = meta.get("payload", {}).get("headers", [])
                header_map = {h.get("name", "").lower(): h.get("value", "") for h in headers}
                detailed_messages.append(
                    {
                        "id": msg["id"],
                        "thread_id": meta.get("threadId"),
                        "subject": header_map.get("subject", "Kein Betreff"),
                        "from": header_map.get("from", "Unbekannt"),
                        "to": header_map.get("to", ""),
                        "date": header_map.get("date", ""),
                        "snippet": meta.get("snippet", ""),
                    }
                )
            return detailed_messages
        except Exception as e:
            logger.error(f"Gmail List Fehler: {e}")
            return []

    def get_latest_threads(self, max_results: int = 10) -> list[dict]:
        """Compatibility helper for legacy endpoint."""
        return self.list_messages(max_results=max_results)

    def get_message_content(self, message_id: str) -> str:
        """Return plain message body for quick use."""
        try:
            message = self.get_message(message_id, fmt="full")
            return self.get_message_body(message)
        except Exception as e:
            logger.error(f"Gmail Read Fehler: {e}")
            return ""

    def send_message(self, to: str, subject: str, body: str) -> dict:
        """Send a standard email."""
        if not self.service:
            return {"error": "Gmail service not available"}
        try:
            msg = EmailMessage()
            msg.set_content(body)
            msg["To"] = to
            msg["Subject"] = subject
            raw_msg = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            return self.service.users().messages().send(userId="me", body={"raw": raw_msg}).execute()
        except Exception as e:
            logger.error(f"Gmail Send Fehler: {e}")
            return {"error": str(e)}

    def send_reply(self, message_id: str, body: str, subject_prefix: str = "Re:") -> dict:
        """Reply to an existing Gmail message."""
        if not self.service:
            return {"error": "Gmail service not available"}
        try:
            original = self.get_message(message_id, fmt="metadata")
            headers = original.get("payload", {}).get("headers", [])
            header_map = {h.get("name", "").lower(): h.get("value", "") for h in headers}
            original_subject = header_map.get("subject", "Kein Betreff")
            recipient = header_map.get("reply-to") or header_map.get("from")
            if not recipient:
                return {"error": "Kein Reply-Empfänger gefunden"}

            subject = original_subject if original_subject.lower().startswith("re:") else f"{subject_prefix} {original_subject}"

            msg = EmailMessage()
            msg.set_content(body)
            msg["To"] = recipient
            msg["Subject"] = subject
            msg["In-Reply-To"] = original.get("id")
            references = header_map.get("references", "").strip()
            msg["References"] = f"{references} {original.get('id')}".strip() if references else original.get("id")

            raw_msg = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            payload = {"raw": raw_msg, "threadId": original.get("threadId")}
            return self.service.users().messages().send(userId="me", body=payload).execute()
        except Exception as e:
            logger.error(f"Gmail Reply Fehler: {e}")
            return {"error": str(e)}

    def modify_message(self, message_id: str, add_labels: Optional[list[str]] = None, remove_labels: Optional[list[str]] = None) -> dict:
        """Modify labels on a message."""
        if not self.service:
            return {"error": "Gmail service not available"}
        try:
            body = {
                "addLabelIds": add_labels or [],
                "removeLabelIds": remove_labels or [],
            }
            return self.service.users().messages().modify(userId="me", id=message_id, body=body).execute()
        except Exception as e:
            logger.error(f"Gmail Modify Fehler: {e}")
            return {"error": str(e)}

# Singleton Instance
gmail_client = None

def get_gmail_client() -> GmailClient:
    global gmail_client
    if gmail_client is None:
        gmail_client = GmailClient()
    return gmail_client
