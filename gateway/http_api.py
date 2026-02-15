"""FastAPI HTTP endpoints."""
import re
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
class ChatMemory:
    def __init__(self):
        self.memory_content = self._read_file(MEMORY_FILE)
        self.skills_content = self._read_file(SKILLS_FILE)
        self.heartbeat_content = self._read_file(HEARTBEAT_FILE)
        self.conversation_history = []
        
        # Lern-Attribute
        self.user_interests = {}
        self.user_preferences = {
            "positive_feedback": 0,
            "negative_feedback": 0,
            "message_length": "mittel",
            "active_time": "unbekannt"
        }
        self.important_info = {}
        
        # Konfigurierbare Grenzen
        self.max_memory_entries = 100
        self.max_memory_size = 10000
        self.archive_file = "MEMORY_ARCHIVE.md"

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

    def _get_default_content(self, filename):
        if "MEMORY" in filename:
            return f"""# GABI Memory System

## Aktuelle Konversation
- Datum: {datetime.now().strftime('%Y-%m-%d')}
- Thema: Erste Initialisierung
- User: Admin
"""
        elif "SKILLS" in filename:
            return """# GABI Skills & Fähigkeiten

## 🎯 Kern-Funktionen
- **Chat**: Konversation mit Ollama
- **Shell**: Ausführung erlaubter Systembefehle
- **Gmail**: E-Mails lesen, senden, verwalten
- **Telegram**: Bot-Integration
"""
        elif "HEARTBEAT" in filename:
            return f"""# GABI Heartbeat & Monitoring

## Aktueller Status ({datetime.now().strftime('%d.%m.%Y %H:%M')})
| Dienst | Status |
|--------|--------|
| FastAPI | 🟢 Online |
| Ollama | 🟢 Connected |
| Telegram | 🟢 Aktiv |
"""
        return ""

    # ===== DIE WICHTIGE METHODE: get_system_prompt =====
    
    def get_system_prompt(self):
        """Erstellt einen System-Prompt mit Memory, Skills, Heartbeat und gelernten Infos"""
        
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
        
        current_time = datetime.now().strftime('%d.%m.%Y %H:%M')
        
        return f"""Du bist GABI (Gateway AI Bot Interface), ein intelligenter und hilfsbereiter Assistent, du hast Zugriff auf Shell-Befehle!.

## 🛠️ VERFÜGBARE BEFEHLE (kannst du NUTZEN!)
- **/shell** - Führe Shell-Befehl aus (z.B. "/shell dir" oder "/shell date")
- **/memory** - Zeige letzte Erinnerungen
- **/soul** - Zeige meine Persönlichkeit

## 🆔 IDENTITÄT
- Du läufst auf einem Gateway-Server mit Ollama-Integration
- Du hast Zugriff auf Shell-Befehle und Gmail
- Dein aktuelles Modell ist {ollama_client.default_model}
- Aktuelle Zeit: {current_time}

## 🧠 WAS ICH ÜBER DICH GELERNT HABE
{learned_info if learned_info else '- Ich lerne dich gerade erst kennen...'}
- Deine Interessen: {interests if interests else 'noch unbekannt'}
- Dein Stil: {self.user_preferences.get('message_length', 'mittel')}e Antworten bevorzugt
- Du chattest am liebsten {self.user_preferences.get('active_time', 'tagsüber')}

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
2. **Sicherheit geht vor** - Nur erlaubte Shell-Befehle
3. **Frage nach bei Unsicherheit** - Besser nachfragen
4. **Nutze das Gelernte** - Zeig, dass du dich erinnerst
5. **Entwickle dich weiter** - Mit jeder Interaktion wächst du

---
Antworte jetzt auf meine Nachricht im Stil, den du gelernt hast:"""

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
            "system": ["status", "health", "server", "läuft"],
            "memory": ["erinner", "memory", "vorher", "gestern"],
            "soul": ["persönlichkeit", "soul", "charakter", "lernen"],
            "hilfe": ["hilfe", "help", "frage", "problem", "fehler"],
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
        ]
        
        import re
        for pattern, info_type in important_patterns:
            match = re.search(pattern, user_message, re.IGNORECASE)
            if match:
                self.important_info[info_type] = match.group(1)

    def add_to_memory(self, user_message, bot_response):
        """Fügt eine Konversation zum Memory hinzu"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        # Konversation speichern
        self.conversation_history.append({"role": "user", "content": user_message, "timestamp": timestamp})
        self.conversation_history.append({"role": "assistant", "content": bot_response, "timestamp": timestamp})
        
        if len(self.conversation_history) > 100:
            self.conversation_history = self.conversation_history[-100:]
        
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
            
        except Exception as e:
            logger.error(f"Memory Update fehlgeschlagen: {e}")
        
        self.update_heartbeat()

    def update_heartbeat(self):
        """Aktualisiert den Heartbeat"""
        # Hier deine bestehende update_heartbeat Methode
        pass

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


# In http_api.py - Erweiterter Chat-Endpoint

@router.post("/chat")
async def chat_with_ollama(request: ChatRequest, token: str = Header(None)):
    """Verknüpft das Dashboard direkt mit dem Ollama Client inkl. Memory & Befehlen."""
    if token != API_KEY_REQUIRED:
        raise HTTPException(status_code=403, detail="API-Key ungültig")

    try:
        # ===== 1. PRÜFE OB ES EIN BEFEHL IST =====
        if request.message.startswith('/'):
            logger.info(f"Befehl erkannt: {request.message}")
            return await handle_command(request.message, token)
        
        # ===== 2. SYSTEM-PROMPT ZUSAMMENSTELLEN =====
        system_prompt = chat_memory.get_system_prompt()
        
        # Kommunikationsstil lernen (wenn vorhanden)
        learned_style = ""
        if hasattr(chat_memory, 'get_communication_style'):
            learned_style = chat_memory.get_communication_style()
        
        # Zusätzliche Instruktionen für Befehle
        command_instructions = """
        
## 📢 WICHTIGE HINWEISE ZU BEFEHLEN:
- Du selbst kannst KEINE Shell-Befehle ausführen
- Wenn der Nutzer einen Befehl ausführen möchte, leite ihn an:
  - `/shell befehl` für Shell-Befehle (z.B. `/shell dir`)
  - `/memory` um das Memory zu sehen
  - `/soul` um die Persönlichkeit zu sehen
  - `/help` für alle Befehle

Beispiel:
Nutzer: "Zeig mir die Dateien"
Du: "Du kannst `/shell dir` verwenden, um die Dateien anzuzeigen!"
"""
        
        # ===== 3. NACHRICHTEN ZUSAMMENSTELLEN =====
        messages = [
            {"role": "system", "content": system_prompt + learned_style + command_instructions}
        ]
        
        # Konversationsverlauf hinzufügen (maximal 10 Nachrichten für Kontext)
        if chat_memory.conversation_history:
            # Nur die letzten 10 Nachrichten (5 Austausche)
            context_msgs = chat_memory.conversation_history[-10:]
            messages.extend(context_msgs)
            logger.debug(f"Kontext mit {len(context_msgs)} Nachrichten geladen")
        
        # Aktuelle Nutzer-Nachricht
        messages.append({"role": "user", "content": request.message})
        
        # ===== 4. OLLAMA ANFRAGE =====
        logger.info(f"Chat-Anfrage: Modell={request.model or DEFAULT_MODEL}, Nachricht={request.message[:50]}...")
        
        response = ollama_client.chat(
            model=request.model or DEFAULT_MODEL,
            messages=messages
        )
        
        # Antwort extrahieren
        reply = response.get("message", {}).get("content", "Keine Antwort erhalten.")
        
        # ===== 5. IN MEMORY SPEICHERN =====
        chat_memory.add_to_memory(request.message, reply)
        
        # ===== 6. ANTWORT ZURÜCKGEBEN =====
        return {
            "status": "success", 
            "reply": reply,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Ollama Chat Fehler: {e}")
        return {
            "status": "error", 
            "message": str(e),
            "reply": f"Entschuldigung, es ist ein Fehler aufgetreten: {str(e)}"
        }

async def handle_command(message: str, token: str):
    """Behandelt Befehle wie /shell, /memory, /soul, etc."""
    cmd_parts = message[1:].split()
    command = cmd_parts[0].lower()
    args = cmd_parts[1:] if len(cmd_parts) > 1 else []
    
    logger.info(f"Verarbeite Befehl: {command} mit Args: {args}")
    
    # ===== SHELL-BEFEHLE =====
    if command in ["shell", "cmd", "bash", "powershell"]:
        if not args:
            return {
                "status": "error", 
                "reply": "❌ Bitte einen Befehl angeben, z.B. `/shell dir` oder `/shell date`"
            }
        
        try:
            # Shell-Befehl ausführen
            shell_request = ShellRequest(command=args[0], args=args[1:] if len(args) > 1 else [])
            result = await execute_command(shell_request, token)
            
            if result.get("status") == "success":
                output = result.get('stdout', '')
                error = result.get('stderr', '')
                
                if output:
                    return {
                        "status": "success", 
                        "reply": f"✅ **Befehl ausgeführt:** `{args[0]}`\n```\n{output[:1000]}{'...' if len(output) > 1000 else ''}\n```"
                    }
                elif error:
                    return {
                        "status": "error", 
                        "reply": f"⚠️ **Fehler:**\n```\n{error}\n```"
                    }
                else:
                    return {
                        "status": "success", 
                        "reply": f"✅ Befehl `{args[0]}` ausgeführt (keine Ausgabe)"
                    }
            else:
                return {
                    "status": "error", 
                    "reply": f"❌ Fehler: {result.get('message', 'Unbekannter Fehler')}"
                }
                
        except Exception as e:
            logger.error(f"Shell-Befehl Fehler: {e}")
            return {
                "status": "error", 
                "reply": f"❌ Fehler beim Ausführen: {str(e)}"
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
        # Hier könntest du den generate_soul Endpoint aufrufen
        return {
            "status": "info", 
            "reply": "🔄 Soul-Generierung gestartet... (dauert einen Moment)"
        }
    
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
**🔧 Verfügbare Befehle:**

`/shell <befehl>` - Führe Shell-Befehl aus (z.B. `/shell dir`, `/shell date`)
`/memory` - Zeige letzte Erinnerungen
`/soul` - Zeige meine Persönlichkeit
`/status` - Zeige System-Status
`/learn` - Zeige was ich über dich gelernt habe
`/generate-soul` - Generiere/aktualisiere meine Persönlichkeit
`/help` - Diese Hilfe

**💡 Tipps:**
- Ich lerne mit jeder Interaktion dazu!
- Je mehr du chattest, desto besser passe ich mich an
- Bei Fragen einfach fragen!
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
    