"""Gmail client with OAuth2 authentication."""
import base64
import json
import logging
from pathlib import Path
from typing import Any

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from gateway.config import config

logger = logging.getLogger(__name__)

# OAuth2 scopes for Gmail
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]


class GmailClient:
    """Gmail API client with OAuth2 authentication."""

    def __init__(self):
        self.credentials_path = config.get("gmail.credentials_path", "credentials.json")
        self.token_path = config.get("gmail.token_path", "token.json")
        self.service = None
        self._authenticate()

    def _authenticate(self):
        """Authenticate using OAuth2 flow."""
        creds = None
        token_path = Path(self.token_path)

        # Load existing token (try both pickle and JSON formats)
        if token_path.exists():
            try:
                # Try pickle first (legacy format)
                import pickle
                with open(token_path, "rb") as token:
                    creds = pickle.load(token)
            except Exception:
                # Try JSON format (current google-auth-oauthlib format)
                import pickle
                try:
                    import google.oauth2.credentials
                    with open(token_path, "r") as token:
                        token_data = json.load(token)
                        creds = google.oauth2.credentials.Credentials.from_authorized_user_info(token_data, SCOPES)
                except Exception as e:
                    logger.warning(f"Could not load token: {e}")

        # If no valid credentials, run OAuth flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                creds_path = Path(self.credentials_path)
                if not creds_path.exists():
                    raise FileNotFoundError(
                        f"Gmail credentials not found: {self.credentials_path}. "
                        "Please download OAuth2 credentials from Google Cloud Console."
                    )

                flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
                creds = flow.run_local_server(port=0)

            # Save token in JSON format
            import pickle
            try:
                # Try to save as JSON (google-auth-oauthlib standard)
                import google.oauth2.credentials
                token_data = {
                    "token": creds.token,
                    "refresh_token": creds.refresh_token,
                    "token_uri": creds.token_uri,
                    "client_id": creds.client_id,
                    "client_secret": creds.client_secret,
                    "scopes": creds.scopes,
                }
                with open(token_path, "w") as token:
                    json.dump(token_data, token)
            except Exception:
                # Fallback to pickle if JSON fails
                with open(token_path, "wb") as token:
                    pickle.dump(creds, token)

        # Build Gmail service
        self.service = build("gmail", "v1", credentials=creds)
        logger.info("Gmail client authenticated successfully")

    def list_messages(self, max_results: int = 10, query: str = "") -> list[dict]:
        """List recent messages."""
        results = (
            self.service.users()
            .messages()
            .list(userId="me", maxResults=max_results, q=query)
            .execute()
        )

        messages = results.get("messages", [])
        logger.info(f"Listed {len(messages)} messages")

        return messages

    def get_message(self, message_id: str) -> dict:
        """Get a specific message by ID."""
        message = (
            self.service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )

        logger.info(f"Retrieved message: {message_id}")
        return message

    def get_message_body(self, message: dict) -> str:
        """Extract plain text body from message."""
        payload = message.get("payload", {})
        body = ""
        headers = payload.get("headers", [])

        # Get subject
        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")

        # Get body from parts
        parts = payload.get("parts", [])
        if parts:
            for part in parts:
                if part.get("mimeType") == "text/plain":
                    data = part.get("body", {}).get("data", "")
                    if data:
                        body = base64.urlsafe_b64decode(data).decode("utf-8")
                        break
        else:
            # Direct body
            data = payload.get("body", {}).get("data", "")
            if data:
                body = base64.urlsafe_b64decode(data).decode("utf-8")

        return f"Subject: {subject}\n\n{body}"

    def send_message(
        self, to: str, subject: str, body: str, thread_id: str | None = None
    ) -> dict:
        """Send an email message."""
        from email.mime.text import MIMEText
        import email
        import mimetypes

        # Create message
        msg = email.message.EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)

        # Encode
        encoded_msg = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

        # Send
        body_msg = {"raw": encoded_msg}
        if thread_id:
            body_msg["threadId"] = thread_id

        sent_message = (
            self.service.users()
            .messages()
            .send(userId="me", body=body_msg)
            .execute()
        )

        logger.info(f"Sent message: {sent_message['id']}")
        return sent_message

    def modify_message(self, message_id: str, add_labels: list[str] | None = None, remove_labels: list[str] | None = None) -> dict:
        """Modify message labels (archive, star, etc.)."""
        body = {}
        if add_labels:
            body["addLabelIds"] = add_labels
        if remove_labels:
            body["removeLabelIds"] = remove_labels

        result = (
            self.service.users()
            .messages()
            .modify(userId="me", id=message_id, body=body)
            .execute()
        )

        logger.info(f"Modified message: {message_id}")
        return result


gmail_client = None


def get_gmail_client() -> "GmailClient":
    """Get or create Gmail client instance (lazy initialization)."""
    global gmail_client
    if gmail_client is None:
        gmail_client = GmailClient()
    return gmail_client
