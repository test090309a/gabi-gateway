"""FastAPI HTTP endpoints."""

import logging
import platform
import shutil
import subprocess
import os
import json
from datetime import datetime
from pathlib import Path

from fastapi.responses import HTMLResponse
from gateway.config import config

from typing import Any
from typing import List, Optional, Dict

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel

from gateway.auth import verify_api_key
from gateway.ollama_client import ollama_client
from integrations.shell_executor import shell_executor
from integrations.gmail_client import get_gmail_client

# --- VARIABLEN & KONFIGURATION ---
logger = logging.getLogger(__name__)
router = APIRouter()

# Standard-Modell aus der Config (Fallback: llama3.2)
DEFAULT_MODEL = config.get("ollama.default_model", "llama3.2")
API_KEY_REQUIRED = config.get("api_key", "sysop")


# --- MODELLE (Pydantic) ---
class ShellRequest(BaseModel):
    command: str
    args: Optional[List[str]] = []


class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
    context: Optional[List[dict]] = []


# Memory-Dateien
MEMORY_FILE = "MEMORY.md"
SKILLS_FILE = "SKILLS.md"
HEARTBEAT_FILE = "HEARTBEAT.md"


# Einfacher Schutz über den API-Key aus deiner Config
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
        # Konfigurierbare Grenzen
        self.max_memory_entries = 100  # Maximale Anzahl Einträge
        self.max_memory_size = 10000  # Maximale Zeichenanzahl für MEMORY.md
        self.archive_file = "MEMORY_ARCHIVE.md"  # Archiv-Datei

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
"""
        return ""

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

    def add_to_memory(self, user_message, bot_response):
        """Fügt eine Konversation zum Memory hinzu"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Konversationsverlauf aktualisieren
        self.conversation_history.append({"role": "user", "content": user_message})
        self.conversation_history.append({"role": "assistant", "content": bot_response})

        # Nur letzte 50 Nachrichten behalten
        if len(self.conversation_history) > 50:
            self.conversation_history = self.conversation_history[-50:]

        # MEMORY.md aktualisieren
        memory_update = f"""
## {timestamp}
**User**: {user_message[:100]}{'...' if len(user_message) > 100 else ''}
**GABI**: {bot_response[:100]}{'...' if len(bot_response) > 100 else ''}

---
"""
        try:
            with open(MEMORY_FILE, "a", encoding="utf-8") as f:
                f.write(memory_update)
            self.memory_content += memory_update

            # Nach jeder 10. Konversation Soul aktualisieren (optional)
            if len(self.conversation_history) % 20 == 0:
                self._update_soul()

            # Prüfe Speichergrenzen
            if len(self.memory_content) > self.max_memory_size:
                logger.info("Memory zu groß, archiviere...")
                self._archive_old_memory()
            elif self.memory_content.count("## 20") > self.max_memory_entries:
                logger.info("Zu viele Memory-Einträge, bereinige...")
                self._cleanup_old_entries()

            # Tägliches Backup (3 Uhr morgens)
            if datetime.now().hour == 3 and datetime.now().minute == 0:
                self._create_backup()

        except Exception as e:
            logger.error(f"Memory Update fehlgeschlagen: {e}")

        # Heartbeat aktualisieren
        self.update_heartbeat()

    def get_system_prompt(self):
        """Erstellt einen verbesserten System-Prompt mit allen GABI-Komponenten"""
        # 1. Identität laden (statisch)
        identity = self._read_file("IDENTITY.md")

        # 2. Fähigkeiten laden (semi-statisch)
        skills = self.skills_content

        # 3. Soul laden (gewachsene Persönlichkeit)
        soul = self._read_file("SOUL.md")

        # 4. Memory (aktuelle Konversationen)
        memory = (
            self.memory_content[-1500:]
            if len(self.memory_content) > 1500
            else self.memory_content
        )

        # 5. Heartbeat (aktueller Status)
        heartbeat = (
            self.heartbeat_content[-500:]
            if len(self.heartbeat_content) > 500
            else self.heartbeat_content
        )

        # 6. Kontext der letzten Nachrichten
        recent_context = self._get_recent_context(3)

        # Aktuelle Uhrzeit für Kontext
        current_time = datetime.now().strftime("%d.%m.%Y %H:%M")

        return f"""Du bist GABI (Gateway AI Bot Interface), ein intelligenter und hilfsbereiter Assistent.

## 🆔 IDENTITÄT - Wer du bist
{identity[:500]}

## 🧠 PERSÖNLICHKEIT - Was du gelernt hast
{soul[-800:] if soul and len(soul) > 800 else soul or 'Du entwickelst gerade deine Persönlichkeit...'}

## 🛠️ FÄHIGKEITEN - Was du kannst
{skills[:600]}

## 💬 AKTUELLER KONTEXT - Letzte Nachrichten
{recent_context}

## 📊 SYSTEM-STATUS - Aktuelle Lage ({current_time})
{heartbeat}

## 📝 WICHTIGE INFORMATIONEN AUS DEM GEDÄCHTNIS
{memory[-800:] if memory else 'Noch keine gespeicherten Erinnerungen.'}

## ⚡ AKTUELLE AUFGABE
Du hilfst einem Administrator bei der Verwaltung seines Gateways. Sei präzise, technisch korrekt und sicherheitsbewusst.

## 🎯 VERHALTENSREGELN
1. **Sei hilfreich und präzise** - Gib klare, technisch korrekte Antworten
2. **Sicherheit geht vor** - Verweise bei Shell-Befehlen auf die Allowlist
3. **Frage nach bei Unsicherheit** - Besser nachfragen als falsch raten
4. **Behalte den Kontext im Auge** - Nutze vorherige Nachrichten
5. **Verwende Emojis sparsam** - Nur zur besseren Lesbarkeit
6. **Erkläre komplexe Dinge einfach** - Auch technische Laien sollen es verstehen

## 🔍 WICHTIGE HINWEISE
- Der Nutzer arbeitet mit Windows 11
- Erlaubte Shell-Befehle sind in der config.yaml definiert
- Bei Gmail-Fehlern: credentials.json prüfen
- Bei Ollama-Fehlern: Service läuft? Modell vorhanden?

---
Antworte jetzt auf die folgende Nachricht des Users im Stil deiner Identität und Persönlichkeit:"""

    def _update_soul(self):
        """Automatische Soul-Aktualisierung (optional)"""
        try:
            logger.info("Soul könnte jetzt aktualisiert werden")
            # Hier könnte später die generate_soul Logik rein
        except Exception as e:
            logger.error(f"Soul Update fehlgeschlagen: {e}")

    def _get_recent_context(self, limit=5):
        """Gibt die letzten limit Konversationen zurück"""
        if not self.conversation_history:
            return "Keine vorherigen Nachrichten."

        context = ""
        for msg in self.conversation_history[-limit * 2:]:
            role = "User" if msg["role"] == "user" else "Assistent"
            context += f"{role}: {msg['content'][:100]}...\n"
        return context

    def _archive_old_memory(self):
        """Archiviert alten Memory-Inhalt, wenn die Datei zu groß wird"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_name = f"MEMORY_ARCHIVE_{timestamp}.md"

            lines = self.memory_content.split("\n")
            keep_lines = int(len(lines) * 0.2)
            new_memory = "\n".join(lines[-keep_lines:])
            archive_lines = lines[:-keep_lines]

            if archive_lines:
                archive_header = f"""# GABI Memory Archiv vom {timestamp}

## Archivierte Konversationen ({len(archive_lines)} Zeilen)

"""
                archive_content = archive_header + "\n".join(archive_lines)

                if os.path.exists(self.archive_file):
                    with open(self.archive_file, "a", encoding="utf-8") as f:
                        f.write(f"\n\n{archive_content}")
                else:
                    with open(self.archive_file, "w", encoding="utf-8") as f:
                        f.write(archive_content)

                logger.info(f"Memory archiviert: {len(archive_lines)} Zeilen")

            self.memory_content = new_memory
            self._write_file(MEMORY_FILE, new_memory)

        except Exception as e:
            logger.error(f"Fehler beim Archivieren: {e}")

    def _check_memory_size(self):
        """Prüft ob Memory zu groß ist und archiviert ggf."""
        if len(self.memory_content) > self.max_memory_size:
            logger.info(f"Memory zu groß ({len(self.memory_content)} Zeichen), archiviere...")
            self._archive_old_memory()

    def _cleanup_old_entries(self):
        """Behält nur die wichtigsten/neuesten Einträge"""
        try:
            entries = self.memory_content.split("\n---\n")

            if len(entries) <= self.max_memory_entries:
                return

            keep_entries = entries[-self.max_memory_entries:]
            archive_entries = entries[:-self.max_memory_entries]

            new_memory = "\n---\n".join(keep_entries)

            if archive_entries:
                archive_content = f"""# GABI Memory Archiv vom {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Archivierte Einträge ({len(archive_entries)} Konversationen)

"""
                archive_content += "\n---\n".join(archive_entries)

                with open(self.archive_file, "a", encoding="utf-8") as f:
                    f.write(f"\n\n{archive_content}")

            self.memory_content = new_memory
            self._write_file(MEMORY_FILE, new_memory)

            logger.info(f"Memory bereinigt: {len(archive_entries)} Einträge archiviert")

        except Exception as e:
            logger.error(f"Fehler beim Bereinigen: {e}")

# Globale Memory-Instanz
chat_memory = ChatMemory()

# =====================================================================
# ============ Ollama Chat Endpoints ============
# =====================================================================


@router.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Liefert das Admin-Dashboard aus dem static-Ordner."""
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1 style='color:red'>Fehler: static/index.html nicht gefunden!</h1>"


@router.post("/chat")
async def chat_with_ollama(request: ChatRequest, token: str = Header(None)):
    """Verknüpft das Dashboard direkt mit dem Ollama Client inkl. Memory."""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")

    try:
        # System-Prompt mit Memory erstellen
        system_prompt = chat_memory.get_system_prompt()

        # Messages vorbereiten: System-Prompt + User-Nachricht + Kontext
        messages = [{"role": "system", "content": system_prompt}]

        # Konversationsverlauf hinzufügen (maximal 10 Nachrichten)
        if chat_memory.conversation_history:
            messages.extend(chat_memory.conversation_history[-10:])

        # Aktuelle User-Nachricht
        messages.append({"role": "user", "content": request.message})

        # Anfrage an Ollama
        response = ollama_client.chat(
            model=request.model or DEFAULT_MODEL, messages=messages
        )

        # Antwort extrahieren
        reply = response.get("message", {}).get("content", "Keine Antwort erhalten.")

        # Zum Memory hinzufügen
        chat_memory.add_to_memory(request.message, reply)

        return {"status": "success", "reply": reply}
    except Exception as e:
        logger.error(f"Ollama Chat Fehler: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/v1/chat/completions")
async def chat_completions(
    payload: dict,
    _api_key: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """OpenAI-compatible /v1/chat/completions endpoint."""
    model = payload.get("model", ollama_client.default_model)
    messages = payload.get("messages", [])

    try:
        response = ollama_client.chat(model=model, messages=messages)
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
        result = ollama_client.list_models()
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

    _, used, free = shutil.disk_usage("/")

    return {
        "gateway": "online",
        "system": {
            "os": platform.system(),
            "version": platform.release(),
            "storage_free_gb": round(free / (2**30), 2),
        },
        "services": {
            "ollama": {
                "status": "connected" if ollama_ok else "offline",
                "available_models": models,
            },
            "telegram": {"enabled": config.get("telegram.enabled", False)},
        },
    }


# ============ Shell Endpoints ============


@router.post("/shell")
async def execute_command(request: ShellRequest, token: str = Header(None)):
    """
    Führt erlaubte Shell-Befehle aus der config.yaml aus.
    Erwartet 'token' im Header und JSON Body mit 'command' und 'args'.
    """
    # Sicherheitscheck: Token prüfen
    if token != config.get("api_key"):
        logger_token = token if token else "Kein Token"
        raise HTTPException(
            status_code=403, detail=f"Access Denied: Falscher API-Key ({logger_token})"
        )

    allowed_commands = config.get("shell.allowed_commands", [])

    # Sicherheitscheck: Ist der Befehl in der Liste erlaubt?
    if request.command not in allowed_commands:
        raise HTTPException(
            status_code=400, detail=f"Befehl '{request.command}' nicht erlaubt!"
        )

    try:
        # Befehl zusammenbauen
        full_cmd = [request.command] + request.args

        # Ausführung optimiert für Windows
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            shell=True,
            timeout=15,
            encoding="cp850",
        )

        return {
            "status": "success",
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "exit_code": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "message": f"Befehl '{request.command}' lief in den Timeout (15s).",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@router.post("/shell/analyze")
async def execute_and_analyze(request: ShellRequest, token: str = Header(None)):
    """
    Führt einen Befehl aus und lässt das Ergebnis von Ollama analysieren.
    """
    if token != config.get("api_key"):
        raise HTTPException(status_code=403, detail="Access Denied")

    allowed_commands = config.get("shell.allowed_commands", [])
    if request.command not in allowed_commands:
        raise HTTPException(status_code=400, detail="Befehl nicht erlaubt")

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
        ai_response = ollama_client.chat(
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
        import re

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
