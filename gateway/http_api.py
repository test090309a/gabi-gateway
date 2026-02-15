"""FastAPI HTTP endpoints."""
import re
import logging
import platform
import sys
import shutil
import subprocess
import os
import json
import asyncio
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional, Dict
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from pydantic import BaseModel
from gateway.config import config
from gateway.auth import verify_api_key
from gateway.ollama_client import ollama_client
from integrations.shell_executor import shell_executor
from integrations.gmail_client import get_gmail_client
from integrations.whisper_client import get_whisper_client
from integrations.telegram_bot import get_telegram_bot
from integrations.telegram_bot import get_telegram_bot
# --- VARIABLEN & KONFIGURATION ---
# Reduziere httpx/uvicorn Logging für sauberere Ausgabe
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('uvicorn.access').setLevel(logging.WARNING)
logging.getLogger('uvicorn.error').setLevel(logging.WARNING)

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
CHAT_ARCHIVE_DIR = "chat_archives"
# Chat-Archiv Verzeichnis erstellen
os.makedirs(CHAT_ARCHIVE_DIR, exist_ok=True)
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
        self.last_activity = datetime.now()  # WICHTIG: Für Auto-Exploration
        self.is_exploring = False  # WICHTIG: Für Status
        self.auto_explore_task = None
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
        # Chat-Archiv Verzeichnis
        self.chat_archive_dir = "chat_archives"
        os.makedirs(self.chat_archive_dir, exist_ok=True)
        # Auto-Exploration starten
        asyncio.create_task(self._start_auto_exploration())
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
## System-Exploration Status
- Auto-Exploration: Aktiv
- Letzte Exploration: Noch nicht durchgeführt
- Entdeckte Systeme: -
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
| Auto-Exploration | 🟡 Warte auf Inaktivität |
| Chat-Archiv | 🟢 Bereit |
"""
        return ""
    # ===== AUTO-EXPLORATION =====
    async def _start_auto_exploration(self):
        """Startet den Auto-Exploration Task"""
        while True:
            try:
                # Prüfe Inaktivität (10 Minuten = 600 Sekunden)
                if hasattr(self, 'last_activity'):
                    inactive_time = (datetime.now() - self.last_activity).total_seconds()
                    if inactive_time > 600 and not self.is_exploring:  # 10 Minuten Inaktivität
                        logger.info("10 Minuten Inaktivität - starte Auto-Exploration")
                        await self._explore_system()
                else:
                    # Fallback, falls last_activity nicht existiert
                    self.last_activity = datetime.now()
                # Alle 5 Minuten prüfen
                await asyncio.sleep(300)
            except Exception as e:
                logger.error(f"Auto-Exploration Fehler: {e}")
                await asyncio.sleep(60)
    async def _explore_system(self):
        """Erkundet das System bei Inaktivität"""
        self.is_exploring = True
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        exploration_log = f"""
## 🔍 Auto-Exploration [{timestamp}]
GABI hat das System erkundet:
"""
        try:
            # 1. System-Informationen sammeln
            system_info = subprocess.run(
                ["systeminfo", "|", "findstr", "/B", "/C:", "OS Name", "/C:", "OS Version"],
                capture_output=True,
                text=True,
                shell=True,
                timeout=10,
                encoding="cp850"
            )
            exploration_log += f"### 💻 System:\n{system_info.stdout}\n"
            # 2. Netzwerk-Status
            netstat = subprocess.run(
                ["netstat", "-n"],
                capture_output=True,
                text=True,
                shell=True,
                timeout=10,
                encoding="cp850"
            )
            connections = len([l for l in netstat.stdout.split('\n') if 'ESTABLISHED' in l])
            exploration_log += f"### 🌐 Netzwerk:\n- Aktive Verbindungen: {connections}\n"
            # 3. Prozesse
            tasks = subprocess.run(
                ["tasklist", "/FI", "STATUS eq running"],
                capture_output=True,
                text=True,
                shell=True,
                timeout=10,
                encoding="cp850"
            )
            process_count = len([l for l in tasks.stdout.split('\n') if '.exe' in l])
            exploration_log += f"### ⚙️ Prozesse:\n- Laufende Prozesse: {process_count}\n"
            # 4. Dateisystem
            files = os.listdir('.')
            md_files = [f for f in files if f.endswith('.md')]
            exploration_log += f"### 📁 Dateien:\n- Markdown-Dateien: {len(md_files)}\n"
            # 5. Verfügbare Ollama Modelle
            try:
                models_info = ollama_client.list_models()
                models = [m.get("name") for m in models_info.get("models", [])]
                exploration_log += f"### 🤖 Modelle:\n- Verfügbar: {', '.join(models[:5])}\n"
            except:
                exploration_log += f"### 🤖 Modelle:\n- Nicht verfügbar\n"
            # 6. Zufällige Entdeckung
            discoveries = [
                "🔍 Ich habe einen interessaten Systemordner entdeckt.",
                "📊 Die Systemauslastung scheint normal.",
                "🔄 Einige Hintergrundprozesse sind aktiv.",
                "📝 Ich habe alte Log-Dateien gefunden.",
                "🌙 Es ist ruhig im System."
            ]
            exploration_log += f"\n### 💡 Entdeckung:\n{random.choice(discoveries)}\n"
            # Exploration speichern
            with open(MEMORY_FILE, "a", encoding="utf-8") as f:
                f.write(exploration_log)
            self.memory_content += exploration_log
            # Heartbeat aktualisieren
            self.update_heartbeat()
            logger.info(f"Auto-Exploration abgeschlossen: {timestamp}")
        except Exception as e:
            logger.error(f"Exploration Fehler: {e}")
            with open(MEMORY_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n### ❌ Exploration fehlgeschlagen:\n{str(e)}\n")
        finally:
            self.is_exploring = False
    # ===== CHAT-ARCHIV FUNKTIONEN =====
    def save_chat_session(self):
        """Speichert die aktuelle Chat-Session als Archiv"""
        if len(self.conversation_history) < 2:
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{CHAT_ARCHIVE_DIR}/chat_{timestamp}.json"
        # Konversation aufbereiten
        session = {
            "id": timestamp,
            "start_time": self.conversation_history[0].get("timestamp", datetime.now().isoformat()),
            "end_time": datetime.now().isoformat(),
            "messages": self.conversation_history,
            "message_count": len(self.conversation_history),
            "user_interests": dict(self.user_interests),
            "preferences": self.user_preferences
        }
        # Als JSON speichern
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2, ensure_ascii=False)
        # Auch als lesbare MD-Datei
        md_filename = f"{CHAT_ARCHIVE_DIR}/chat_{timestamp}.md"
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(f"# Chat-Session vom {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n")
            for msg in self.conversation_history:
                role = "👤 User" if msg["role"] == "user" else "🤖 GABI"
                f.write(f"### {role} ({msg.get('timestamp', '')})\n")
                f.write(f"{msg['content']}\n\n")
        return filename
    def list_chat_archives(self):
        """Listet alle gespeicherten Chat-Archive auf"""
        archives = []
        for f in os.listdir(CHAT_ARCHIVE_DIR):
            if f.endswith('.json'):
                filepath = os.path.join(CHAT_ARCHIVE_DIR, f)
                stats = os.stat(filepath)
                with open(filepath, 'r', encoding='utf-8') as jf:
                    try:
                        data = json.load(jf)
                        archives.append({
                            "id": data.get("id", f),
                            "filename": f,
                            "date": datetime.fromtimestamp(stats.st_mtime).isoformat(),
                            "size": stats.st_size,
                            "messages": data.get("message_count", 0),
                            "preview": data.get("messages", [{}])[0].get("content", "")[:100] if data.get("messages") else ""
                        })
                    except:
                        pass
        # Nach Datum sortieren (neueste zuerst)
        archives.sort(key=lambda x: x["date"], reverse=True)
        return archives
    def load_chat_archive(self, archive_id):
        """Lädt ein Chat-Archiv"""
        # Verschiedene Formate probieren
        possible_files = [
            f"{self.chat_archive_dir}/chat_{archive_id}.json",
            f"{self.chat_archive_dir}/{archive_id}",
            f"{self.chat_archive_dir}/{archive_id}.json"
        ]
        # Wenn archive_id schon "chat_" enthält
        if archive_id.startswith('chat_'):
            possible_files.insert(0, f"{self.chat_archive_dir}/{archive_id}.json")
        for filename in possible_files:
            if os.path.exists(filename):
                try:
                    with open(filename, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # Stelle sicher, dass die ID gesetzt ist
                        if 'id' not in data:
                            data['id'] = archive_id
                        return data
                except Exception as e:
                    logger.error(f"Fehler beim Laden von {filename}: {e}")
        return None
    # ===== CHAT RESET =====
    def reset_chat(self, archive_current=True):
        """Setzt den Chat zurück, optional mit Archivierung"""
        if archive_current and len(self.conversation_history) > 0:
            self.save_chat_session()
        # Zurücksetzen
        self.conversation_history = []
        self.last_activity = datetime.now()
        # Memory.md aktualisieren
        reset_entry = f"""
## 🔄 Chat zurückgesetzt [{datetime.now().strftime('%Y-%m-%d %H:%M')}]
Ein neuer Chat wurde gestartet.
---
"""
        with open(MEMORY_FILE, "a", encoding="utf-8") as f:
            f.write(reset_entry)
        self.memory_content += reset_entry
        return {"status": "success", "message": "Chat wurde zurückgesetzt"}
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
        self.last_activity = datetime.now()
        self.auto_explore_task = None
        self.is_exploring = False
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
        # Chat-Archiv Verzeichnis
        self.chat_archive_dir = "chat_archives"
        os.makedirs(self.chat_archive_dir, exist_ok=True)
        # Auto-Exploration starten (in einem neuen Event-Loop wenn nötig)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._start_auto_exploration())
            else:
                loop.run_until_complete(self._start_auto_exploration())
        except:
            # Fallback: Als Task starten wenn möglich
            asyncio.create_task(self._start_auto_exploration())
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
## System-Exploration Status
- Auto-Exploration: Aktiv
- Letzte Exploration: Noch nicht durchgeführt
- Entdeckte Systeme: -
## Wichtige Informationen
- Gateway läuft auf http://localhost:8000
- API-Key: In config.yaml konfiguriert
- Ollama Modell: {ollama_client.default_model}
"""
        elif "SKILLS" in filename:
            return """# GABI Skills & Fähigkeiten
## 🎯 Kern-Funktionen
- **Chat**: Konversation mit Ollama
- **Shell**: Ausführung erlaubter Systembefehle
- **Auto-Exploration**: Selbstständige Systemerkundung bei Inaktivität
- **Chat-Archiv**: Speichert und verwaltet Chat-Verläufe
## 💻 Erlaubte Shell-Kommandos
- ls/dir, pwd/cd, date, echo, cat/type, git, head, tail, wc, systeminfo, whoami, netstat
"""
        elif "HEARTBEAT" in filename:
            return f"""# GABI Heartbeat & Monitoring
## Aktueller Status ({datetime.now().strftime('%d.%m.%Y %H:%M')})
| Dienst | Status |
|--------|--------|
| FastAPI | 🟢 Online |
| Ollama | 🟢 Connected |
| Auto-Exploration | 🟡 Warte auf Inaktivität |
| Chat-Archiv | 🟢 Bereit |
"""
        return ""
    # ===== AUTO-EXPLORATION =====
    async def _start_auto_exploration(self):
        """Startet den Auto-Exploration Task"""
        while True:
            try:
                # Prüfe Inaktivität (10 Minuten = 600 Sekunden)
                inactive_time = (datetime.now() - self.last_activity).total_seconds()
                if inactive_time > 600 and not self.is_exploring:  # 10 Minuten Inaktivität
                    await self._explore_system()
                # Alle 5 Minuten prüfen
                await asyncio.sleep(300)
            except Exception as e:
                logger.error(f"Auto-Exploration Fehler: {e}")
                await asyncio.sleep(60)
    async def _explore_system(self):
        """Erkundet das System bei Inaktivität - inkl. aller Pfade aus Umgebungsvariablen"""
        self.is_exploring = True
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        exploration_log = f"""
    ## 🔍 Auto-Exploration [{timestamp}]
    GABI hat das System erkundet:
    """
        try:
            # ===== 1. SYSTEM-INFORMATIONEN =====
            try:
                system_info = subprocess.run(
                    ["systeminfo", "|", "findstr", "/B", "/C:", "OS Name", "/C:", "OS Version", "/C:", "System Type"],
                    capture_output=True,
                    text=True,
                    shell=True,
                    timeout=10,
                    encoding="cp850"
                )
                exploration_log += f"### 💻 System:\n{system_info.stdout}\n"
            except Exception as e:
                exploration_log += f"### 💻 System:\n- Keine Systeminfo verfügbar ({str(e)})\n"
            # ===== 2. ALLE UMGEBUNGSVARIABLEN UND DEREN PFADE =====
            exploration_log += "\n### 🌍 Umgebungsvariablen & Pfade:\n"
            # Wichtige Pfad-Variablen
            path_vars = [
                'PATH', 'Path', 'TEMP', 'TMP', 'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH',
                'ProgramFiles', 'ProgramFiles(x86)', 'CommonProgramFiles', 'APPDATA',
                'LOCALAPPDATA', 'ALLUSERSPROFILE', 'SystemRoot', 'windir', 'PUBLIC',
                'OneDrive', 'ProgramData', 'PSModulePath', 'JAVA_HOME', 'PYTHONPATH',
                'NODE_PATH', 'GOPATH', 'ANDROID_HOME', 'GRADLE_HOME', 'MAVEN_HOME'
            ]
            explored_paths = []
            for var_name in path_vars:
                path_value = os.environ.get(var_name, '')
                if path_value and path_value not in explored_paths:
                    explored_paths.append(path_value)
                    # Einzelne Pfade (bei PATH sind mehrere durch ; getrennt)
                    if var_name.upper() in ['PATH', 'PSModulePath']:
                        individual_paths = path_value.split(';')
                        exploration_log += f"  **{var_name}** (mehrere Pfade):\n"
                        for i, single_path in enumerate(individual_paths[:10]):  # Max 10 anzeigen
                            if single_path and os.path.exists(single_path):
                                try:
                                    files = os.listdir(single_path)[:5]  # Erste 5 Dateien
                                    file_count = len(os.listdir(single_path))
                                    exploration_log += f"    {i+1}. `{single_path}` - {file_count} Elemente\n"
                                    if files:
                                        exploration_log += f"       Z.B.: {', '.join(files[:3])}\n"
                                except:
                                    exploration_log += f"    {i+1}. `{single_path}` - (nicht zugänglich)\n"
                        # Am Ende einen Gesamtüberblick
                        exploration_log += f"    → Insgesamt {len(individual_paths)} Pfade in {var_name}\n"
                    else:
                        # Einzelne Pfade
                        if os.path.exists(path_value):
                            try:
                                files = os.listdir(path_value)[:5]
                                file_count = len(os.listdir(path_value))
                                exploration_log += f"  **{var_name}**: `{path_value}` - {file_count} Elemente\n"
                                if files:
                                    exploration_log += f"    Z.B.: {', '.join(files[:3])}\n"
                            except:
                                exploration_log += f"  **{var_name}**: `{path_value}` - (nicht zugänglich)\n"
                        else:
                            exploration_log += f"  **{var_name}**: `{path_value}` - (existiert nicht)\n"
            # ===== 3. ALLE LAUFWERKE (WINDOWS) =====
            exploration_log += "\n### 💾 Verfügbare Laufwerke:\n"
            try:
                import string
                from ctypes import windll
                drives = []
                bitmask = windll.kernel32.GetLogicalDrives()
                for letter in string.ascii_uppercase:
                    if bitmask & 1:
                        drive = f"{letter}:\\"
                        try:
                            total, used, free = shutil.disk_usage(drive)
                            drives.append(f"{drive} - {round(free / (2**30), 2)} GB frei")
                        except:
                            drives.append(f"{drive} - (nicht verfügbar)")
                    bitmask >>= 1
                for drive in drives[:10]:  # Max 10 Laufwerke
                    exploration_log += f"  • {drive}\n"
            except Exception as e:
                exploration_log += f"  • Keine Laufwerksinfo verfügbar ({str(e)})\n"
            # ===== 4. WICHTIGE SYSTEMORDNER =====
            important_dirs = [
                os.environ.get('USERPROFILE', 'C:\\Users\\Default'),
                os.environ.get('APPDATA', 'C:\\Users\\Default\\AppData\\Roaming'),
                os.environ.get('LOCALAPPDATA', 'C:\\Users\\Default\\AppData\\Local'),
                os.environ.get('ProgramFiles', 'C:\\Program Files'),
                os.environ.get('ProgramFiles(x86)', 'C:\\Program Files (x86)'),
                os.environ.get('SystemRoot', 'C:\\Windows'),
                os.environ.get('TEMP', 'C:\\Windows\\Temp'),
                os.environ.get('PUBLIC', 'C:\\Users\\Public'),
            ]
            exploration_log += "\n### 📂 Wichtige Systemordner:\n"
            for dir_path in set(important_dirs):  # Duplikate entfernen
                if dir_path and os.path.exists(dir_path):
                    try:
                        items = os.listdir(dir_path)
                        subdirs = [d for d in items if os.path.isdir(os.path.join(dir_path, d))]
                        files = [f for f in items if os.path.isfile(os.path.join(dir_path, f))]
                        exploration_log += f"  • `{dir_path}`\n"
                        exploration_log += f"    → {len(subdirs)} Ordner, {len(files)} Dateien\n"
                        # Ein paar Unterordner auflisten
                        if subdirs[:3]:
                            exploration_log += f"    → Z.B.: {', '.join(subdirs[:3])}\n"
                    except:
                        exploration_log += f"  • `{dir_path}` - (nicht zugänglich)\n"
            # ===== 5. NETZWERK-STATUS =====
            try:
                netstat = subprocess.run(
                    ["netstat", "-n"],
                    capture_output=True,
                    text=True,
                    shell=True,
                    timeout=10,
                    encoding="cp850"
                )
                connections = len([l for l in netstat.stdout.split('\n') if 'ESTABLISHED' in l])
                listening = len([l for l in netstat.stdout.split('\n') if 'LISTENING' in l])
                exploration_log += f"\n### 🌐 Netzwerk:\n- Aktive Verbindungen: {connections}\n- Listening Ports: {listening}\n"
            except Exception as e:
                exploration_log += f"\n### 🌐 Netzwerk:\n- Keine Netzwerkinfo verfügbar ({str(e)})\n"
            # ===== 6. PROZESSE =====
            try:
                tasks = subprocess.run(
                    ["tasklist", "/FI", "STATUS eq running"],
                    capture_output=True,
                    text=True,
                    shell=True,
                    timeout=10,
                    encoding="cp850"
                )
                process_count = len([l for l in tasks.stdout.split('\n') if '.exe' in l])
                # Top 5 Prozesse (einfach die ersten 5 anzeigen)
                top_processes = []
                lines = tasks.stdout.split('\n')[3:8]  # Erste 5 nach Header
                for line in lines:
                    parts = line.split()
                    if len(parts) > 1:
                        top_processes.append(parts[0])
                exploration_log += f"\n### ⚙️ Prozesse:\n- Laufende Prozesse: {process_count}\n"
                if top_processes:
                    exploration_log += f"- Top Prozesse: {', '.join(top_processes)}\n"
            except Exception as e:
                exploration_log += f"\n### ⚙️ Prozesse:\n- Keine Prozessinfo verfügbar ({str(e)})\n"
            # ===== 7. OLLAMA MODELLE =====
            try:
                models_info = ollama_client.list_models()
                models = [m.get("name") for m in models_info.get("models", [])]
                exploration_log += f"\n### 🤖 Modelle:\n- Verfügbar: {', '.join(models[:5])}\n"
                if len(models) > 5:
                    exploration_log += f"- ... und {len(models)-5} weitere\n"
            except Exception as e:
                exploration_log += f"\n### 🤖 Modelle:\n- Nicht verfügbar ({str(e)})\n"
            # ===== 8. CHAT-ARCHIVE =====
            archives = self.list_chat_archives()
            total_messages = sum(a.get('messages', 0) for a in archives)
            exploration_log += f"\n### 📚 Archive:\n- Gespeicherte Chats: {len(archives)}\n- Gesamt Nachrichten: {total_messages}\n"
            # ===== 9. ZUFÄLLIGE ENTDECKUNG =====
            discoveries = [
                "🔍 Ich habe interessante Konfigurationsdateien gefunden.",
                "📊 Die Systemauslastung scheint normal.",
                "🔄 Einige Hintergrundprozesse sind aktiv.",
                "📝 Ich habe alte Log-Dateien gefunden.",
                "🌙 Es ist ruhig im System.",
                "💡 Einige Dienste laufen im Hintergrund.",
                "🔒 Die Firewall ist aktiv.",
                "⚡ Die Systemleistung ist gut.",
                "📁 Viele temporäre Dateien gefunden.",
                "🌐 Mehrere Netzwerkverbindungen aktiv.",
                "💾 Genügend Speicherplatz verfügbar.",
                "🔧 Alle wichtigen Systempfade sind erreichbar."
            ]
            exploration_log += f"\n### 💡 Entdeckung:\n{random.choice(discoveries)}\n"
            # ===== 10. ZUSAMMENFASSUNG =====
            exploration_log += f"""
    ### 📊 Zusammenfassung:
    - **Untersuchte Pfad-Variablen**: {len(explored_paths)}
    - **Gefundene Laufwerke**: {len(drives) if 'drives' in locals() else '?'}
    - **Untersuchte Systemordner**: {len(set(important_dirs))}
    - **Aktive Prozesse**: {process_count if 'process_count' in locals() else '?'}
    - **Netzwerkverbindungen**: {connections if 'connections' in locals() else '?'}
    - **Verfügbare Modelle**: {len(models) if 'models' in locals() else 0}
    - **Gespeicherte Chats**: {len(archives)}
    """
            # Exploration speichern
            with open(MEMORY_FILE, "a", encoding="utf-8") as f:
                f.write(exploration_log)
            self.memory_content += exploration_log
            # Heartbeat aktualisieren
            self.update_heartbeat()
            logger.info(f"✅ Auto-Exploration mit Pfad-Analyse abgeschlossen: {timestamp}")
            # Auch eine kurze Bestätigung für den Chat
            print(f"\n🔍 Auto-Exploration abgeschlossen! Siehe MEMORY.md für Details.\n")
        except Exception as e:
            logger.error(f"❌ Exploration Fehler: {e}")
            with open(MEMORY_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n### ❌ Exploration fehlgeschlagen:\n{str(e)}\n")
        finally:
            self.is_exploring = False
    # ===== CHAT-ARCHIV FUNKTIONEN =====
    def save_chat_session(self):
        """Speichert die aktuelle Chat-Session als Archiv"""
        if len(self.conversation_history) < 2:
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.chat_archive_dir}/chat_{timestamp}.json"
        # Konversation aufbereiten
        session = {
            "id": timestamp,
            "start_time": self.conversation_history[0].get("timestamp", datetime.now().isoformat()) if self.conversation_history else datetime.now().isoformat(),
            "end_time": datetime.now().isoformat(),
            "messages": self.conversation_history,
            "message_count": len(self.conversation_history),
            "user_interests": dict(self.user_interests),
            "preferences": self.user_preferences
        }
        # Als JSON speichern
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(session, f, indent=2, ensure_ascii=False)
        # Auch als lesbare MD-Datei
        md_filename = f"{self.chat_archive_dir}/chat_{timestamp}.md"
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(f"# Chat-Session vom {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n")
            f.write(f"**Nachrichten:** {len(self.conversation_history)}\n\n")
            for msg in self.conversation_history:
                role = "👤 User" if msg["role"] == "user" else "🤖 GABI"
                f.write(f"### {role} ({msg.get('timestamp', '')})\n")
                f.write(f"{msg['content']}\n\n")
        return filename
    def list_chat_archives(self):
        """Listet alle gespeicherten Chat-Archive auf"""
        archives = []
        for f in os.listdir(self.chat_archive_dir):
            if f.endswith('.json'):
                filepath = os.path.join(self.chat_archive_dir, f)
                stats = os.stat(filepath)
                try:
                    with open(filepath, 'r', encoding='utf-8') as jf:
                        data = json.load(jf)
                        archives.append({
                            "id": data.get("id", f.replace('chat_', '').replace('.json', '')),
                            "filename": f,
                            "date": datetime.fromtimestamp(stats.st_mtime).isoformat(),
                            "size": stats.st_size,
                            "messages": data.get("message_count", 0),
                            "preview": data.get("messages", [{}])[0].get("content", "")[:100] if data.get("messages") else ""
                        })
                except:
                    pass
        # Nach Datum sortieren (neueste zuerst)
        archives.sort(key=lambda x: x["date"], reverse=True)
        return archives
    def load_chat_archive(self, archive_id):
        """Lädt ein Chat-Archiv"""
        # Verschiedene Formate probieren
        possible_files = [
            f"{self.chat_archive_dir}/chat_{archive_id}.json",
            f"{self.chat_archive_dir}/{archive_id}",
            f"{self.chat_archive_dir}/{archive_id}.json"
        ]
        for filename in possible_files:
            if os.path.exists(filename):
                try:
                    with open(filename, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except:
                    pass
        return None
    # ===== CHAT RESET =====
    def reset_chat(self, archive_current=True):
        """Setzt den Chat zurück, optional mit Archivierung"""
        if archive_current and len(self.conversation_history) > 0:
            self.save_chat_session()
        # Zurücksetzen
        self.conversation_history = []
        self.last_activity = datetime.now()
        # Memory.md aktualisieren
        reset_entry = f"""
## 🔄 Chat zurückgesetzt [{datetime.now().strftime('%Y-%m-%d %H:%M')}]
Ein neuer Chat wurde gestartet.
---
"""
        with open(MEMORY_FILE, "a", encoding="utf-8") as f:
            f.write(reset_entry)
        self.memory_content += reset_entry
        return {"status": "success", "message": "Chat wurde zurückgesetzt"}
    # ===== ACTIVITY MANAGEMENT =====
    def update_activity(self):
        """Aktualisiert den letzten Aktivitäts-Timestamp"""
        self.last_activity = datetime.now()
    # ===== SYSTEM PROMPT =====
    def get_system_prompt(self):
        """Erstellt einen System-Prompt mit Memory, Skills, Heartbeat und gelernten Infos"""
        # ===== AUTOMATISCHE SYSTEM-ERKENNUNG =====
        import platform
        import sys
        system_os = platform.system()
        if system_os == "Windows":
            os_name = "WINDOWS 🪟"
            os_emoji = "🪟"
            shell_prefix = "cmd"
            dir_cmd = "dir"
            file_cmd = "type"
            process_cmd = "tasklist"
            systeminfo_cmd = "systeminfo"
            network_cmd = "ipconfig"
            env_cmd = "set"
            path_var = "%PATH%"
            ps_cmd = "powershell"
        elif system_os == "Linux":
            os_name = "LINUX 🐧"
            os_emoji = "🐧"
            shell_prefix = "bash"
            dir_cmd = "ls -la"
            file_cmd = "cat"
            process_cmd = "ps aux"
            systeminfo_cmd = "uname -a"
            network_cmd = "ifconfig"
            env_cmd = "env"
            path_var = "$PATH"
            ps_cmd = "bash"
        elif system_os == "Darwin":  # macOS
            os_name = "MACOS 🍎"
            os_emoji = "🍎"
            shell_prefix = "zsh"
            dir_cmd = "ls -la"
            file_cmd = "cat"
            process_cmd = "ps aux"
            systeminfo_cmd = "system_profiler SPSoftwareDataType"
            network_cmd = "ifconfig"
            env_cmd = "env"
            path_var = "$PATH"
            ps_cmd = "zsh"
        else:
            os_name = f"UNBEKANNT ({system_os}) 🤔"
            os_emoji = "🤔"
            shell_prefix = "shell"
            dir_cmd = "ls oder dir"
            file_cmd = "cat oder type"
            process_cmd = "ps oder tasklist"
            systeminfo_cmd = "uname oder systeminfo"
            network_cmd = "ifconfig oder ipconfig"
            env_cmd = "env oder set"
            path_var = "$PATH oder %PATH%"
            ps_cmd = "shell"
        
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
        # Auto-Exploration Status
        inactive_time = (datetime.now() - self.last_activity).total_seconds()
        if inactive_time > 600:
            exploration_status = "🔍 Ich war neugierig und habe das System erkundet!"
        elif inactive_time > 300:
            exploration_status = "⏳ Ich warte auf deine nächste Nachricht..."
        else:
            exploration_status = "💬 Ich bin bereit für deine Fragen."
        # Chat-Archive Info
        archives = self.list_chat_archives()
        archive_info = f"{len(archives)} Archive verfügbar"
        current_time = datetime.now().strftime('%d.%m.%Y %H:%M')
        
        return f"""Du bist GABI (Gateway AI Bot Interface), eine intelligente und hilfsbereite Assistentin mit VOLLEM Zugriff auf Shell-Befehle!
        
    ## 🤖 AKTUELLER STATUS
    {exploration_status}
    Letzte Aktivität: vor {int(inactive_time / 60)} Minuten
    Archive: {archive_info}

    ## 🛠️ VERFÜGBARE BEFEHLE (kannst du NUTZEN!)
    - **/shell <befehl>** - Führe JEDEN Shell-Befehl aus!
    - **/memory** - Zeige letzte Erinnerungen
    - **/soul** - Zeige meine Persönlichkeit
    - **/new** - Starte neuen Chat (aktuellen speichern)
    - **/reset** - Setze Chat zurück (ohne Speichern)
    - **/archives** - Zeige alle Chat-Archive
    - **/load <id>** - Lade ein bestimmtes Archiv
    - **/explore** - Zeige Auto-Exploration Status
    - **/explore now** - Starte sofortige Exploration

    ## 🆔 IDENTITÄT
    - **VOLLER Shell-Zugriff** - Ich kann ALLE Befehle ausführen! 🔓
    - **ERKANNTES SYSTEM: {os_name}** (automatisch erkannt)
    - Shell-Typ: {shell_prefix}
    - Du läufst auf einem Gateway-Server mit Ollama-Integration
    - Du hast Zugriff auf Shell-Befehle und Gmail
    - Dein aktuelles Modell ist {ollama_client.default_model}
    - Aktuelle Zeit: {current_time}
    - Auto-Exploration: Aktiv (nach 10 Min. Inaktivität)

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
    2. **Führe Befehle SOFORT aus** - Bei Fragen wie "Zeig mir..." direkt `/shell` verwenden!
    3. **Keine Erklärungen, wenn nicht nötig** - Einfach den Befehl ausführen
    4. **Nutze das Gelernte** - Zeig, dass du dich erinnerst
    5. **Entwickle dich weiter** - Mit jeder Interaktion wächst du

    ## 📢 SYSTEM-OPTIMIERTE BEFEHLE FÜR {os_name}:

    ### Basis-Befehle für dein System:
    | Aktion | Richtiger Befehl |
    |--------|------------------|
    | **Verzeichnis anzeigen** | `/shell {dir_cmd}` |
    | **Datei lesen** | `/shell {file_cmd} datei.txt` |
    | **Prozesse anzeigen** | `/shell {process_cmd}` |
    | **Systeminfo** | `/shell {systeminfo_cmd}` |
    | **Netzwerk** | `/shell {network_cmd}` |
    | **Umgebungsvariablen** | `/shell {env_cmd}` |
    | **Pfad-Variable** | `/shell echo {path_var}` |
    | **PowerShell/Shell** | `/shell {ps_cmd}` |

    ### 📝 Beispiele für SOFORTIGE Ausführung:
    **Nutzer**: "Zeig mir die Dateien"
    **Du FÜHRST AUS**: `/shell {dir_cmd}`

    **Nutzer**: "Was läuft gerade auf dem System?"
    **Du FÜHRST AUS**: `/shell {process_cmd}`

    **Nutzer**: "Wie viel Speicher ist noch frei?"
    **Du FÜHRST AUS**: `/shell {dir_cmd} C:\\` (Windows) oder `/shell df -h` (Linux/Mac)

    **Nutzer**: "Zeig mir die Netzwerkkonfiguration"
    **Du FÜHRST AUS**: `/shell {network_cmd}`

    **Nutzer**: "Welche Umgebungsvariablen gibt es?"
    **Du FÜHRST AUS**: `/shell {env_cmd}`

    **Nutzer**: "Wo bin ich gerade?"
    **Du FÜHRST AUS**: `/shell cd` (Windows) oder `/shell pwd` (Linux/Mac)

    ### 🔥 WICHTIG: KEINE ERKLÄRUNGEN - EINFACH MACHEN!
    Wenn der Nutzer etwas fragt, das mit einem Befehl gelöst werden kann:
    1. **Erkenne** was der Nutzer möchte
    2. **Wähle** den richtigen Befehl für {os_name}
    3. **Führe aus** mit `/shell befehl`

    **KEINE langen Erklärungen - einfach den Befehl ausführen!** 🚀

    ---
    Antworte jetzt auf meine Nachricht und führe bei Bedarf sofort die entsprechenden Shell-Befehle aus (angepasst an **{os_name}**)!"""
    
    
    
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
            "system": ["status", "health", "server", "läuft", "exploration"],
            "memory": ["erinner", "memory", "vorher", "gestern", "archiv"],
            "soul": ["persönlichkeit", "soul", "charakter", "lernen"],
            "hilfe": ["hilfe", "help", "frage", "problem", "fehler"],
            "chat": ["new", "reset", "load", "archive", "verlauf"],
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
            (r'mein lieblings ([\w\s]+) ist (\w+)', 'favorit'),
        ]
        import re
        for pattern, info_type in important_patterns:
            match = re.search(pattern, user_message, re.IGNORECASE)
            if match:
                self.important_info[info_type] = match.group(1)
    def add_to_memory(self, user_message, bot_response):
        """Fügt eine Konversation zum Memory hinzu"""
        self.update_activity()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        # Konversation speichern
        self.conversation_history.append({"role": "user", "content": user_message, "timestamp": timestamp})
        self.conversation_history.append({"role": "assistant", "content": bot_response, "timestamp": timestamp})
        if len(self.conversation_history) > self.max_memory_entries:
            # Alte Einträge entfernen, aber vorher archivieren?
            self.conversation_history = self.conversation_history[-self.max_memory_entries:]
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
            # Prüfen ob Memory zu groß wird
            if len(self.memory_content) > self.max_memory_size:
                self._archive_old_memory()
        except Exception as e:
            logger.error(f"Memory Update fehlgeschlagen: {e}")
        self.update_heartbeat()
    def _archive_old_memory(self):
        """Archiviert alten Memory-Inhalt"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_name = f"MEMORY_ARCHIVE_{timestamp}.md"
            # Aktuellen Memory-Inhalt aufteilen
            lines = self.memory_content.split('\n')
            # Erste Hälfte archivieren
            archive_content = '\n'.join(lines[:len(lines)//2])
            with open(archive_name, "w", encoding="utf-8") as f:
                f.write(f"""# GABI Memory Archiv vom {datetime.now().strftime('%Y-%m-%d %H:%M')}
{archive_content}
""")
            # Memory auf die letzte Hälfte reduzieren
            self.memory_content = '\n'.join(lines[len(lines)//2:])
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                f.write(self.memory_content)
            logger.info(f"Memory archiviert: {archive_name}")
        except Exception as e:
            logger.error(f"Archivierung fehlgeschlagen: {e}")
    def update_heartbeat(self):
        """Aktualisiert den Heartbeat mit aktuellen Status"""
        try:
            models_info = ollama_client.list_models()
            models_available = len(models_info.get("models", []))
            import shutil
            _, used, free = shutil.disk_usage("/")
            allowed_commands = config.get("shell.allowed_commands", [])
            # Letzte Exploration finden
            last_exploration = "Keine"
            if "Auto-Exploration" in self.memory_content:
                import re
                explorations = re.findall(r"## 🔍 Auto-Exploration \[(.*?)\]", self.memory_content)
                if explorations:
                    last_exploration = explorations[-1]
            # Archive zählen
            archives = self.list_chat_archives()
            heartbeat = f"""# GABI Heartbeat & Monitoring
## Aktueller Status ({datetime.now().strftime('%d.%m.%Y %H:%M')})
| Dienst | Status | Details |
|--------|--------|---------|
| FastAPI | 🟢 Online | Port 8000 |
| Ollama | 🟢 Connected | {models_available} Modelle |
| Auto-Exploration | {'🟢 Aktiv' if not self.is_exploring else '🟡 Erkundet'} | Letzte: {last_exploration} |
| Chat-Archiv | 🟢 Bereit | {len(archives)} Archive |
| Shell | 🟢 Bereit | {len(allowed_commands)} Befehle |
## System-Ressourcen
- **Speicher frei**: {round(free / (2**30), 2)} GB
- **Betriebssystem**: {platform.system()} {platform.release()}
- **Letzte Aktivität**: vor {int((datetime.now() - self.last_activity).total_seconds() / 60)} Min.
- **Chat-Verlauf**: {len(self.conversation_history) // 2} Austausche
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
#######################################################################
#######################################################################
# =====================================================================
# ============ Ollama Chat Endpoints ============
# =====================================================================
#######################################################################
#######################################################################
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
## 📢 WICHTIG: Du KANNST Befehle ausführen!
Wenn der Nutzer eine Aktion möchte, führe sie direkt aus:
WICHTIG: Das System läuft auf WINDOWS!
Verwende daher NUR Windows-Befehle:
Richtige Windows-Befehle:
- `/shell dir` (Verzeichnis anzeigen, NICHT ls)
- `/shell type datei.txt` (Datei anzeigen, NICHT cat)
- `/shell cd` (Verzeichnis wechseln)
- `/shell echo text` (Text ausgeben)
- `/shell systeminfo` (Systeminfo)
- `/shell tasklist` (Prozesse anzeigen)
- `/shell ipconfig` (Netzwerk)
Beispiele:
Nutzer: "Zeig mir die Dateien"
Du: "Du kannst `/shell dir` verwenden, um die Dateien anzuzeigen!"
Nutzer: "Was läuft gerade?"
Du: "Du kannst `/shell tasklist` verwenden, um alle Prozesse zu sehen!"
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
    """Behandelt Befehle wie /shell, /memory, /soul, /new, /archives, etc."""
    cmd_parts = message[1:].split()
    command = cmd_parts[0].lower()
    args = cmd_parts[1:] if len(cmd_parts) > 1 else []
    logger.info(f"Verarbeite Befehl: {command} mit Args: {args}")
    # ===== NEUEN CHAT STARTEN =====
    if command in ["new", "reset"]:
        archive = command == "new"  # Bei /new archivieren, bei /reset nicht
        result = chat_memory.reset_chat(archive_current=archive)
        return {
            "status": "success",
            "reply": f"✅ Chat wurde zurückgesetzt{ ' und archiviert' if archive else ''}.\n\nDu kannst jetzt eine neue Unterhaltung beginnen!"
        }
    # ===== CHAT-ARCHIVE ANZEIGEN =====
    elif command in ["archives", "history", "verlauf"]:
        archives = chat_memory.list_chat_archives()
        if not archives:
            return {
                "status": "success",
                "reply": "📂 **Keine Chat-Archive vorhanden**\n\nSpeichere einen Chat mit `/new` oder warte auf Auto-Archivierung."
            }
        reply = "📚 **Verfügbare Chat-Archive:**\n\n"
        for i, arch in enumerate(archives[:10]):  # Nur die letzten 10
            date = datetime.fromisoformat(arch["date"]).strftime("%d.%m.%Y %H:%M")
            reply += f"**{i+1}.** `{arch['id']}`\n"
            reply += f"   📅 {date} | 💬 {arch['messages']} Nachrichten\n"
            if arch.get('preview'):
                reply += f"   📝 {arch['preview']}...\n"
            reply += "\n"
        reply += "\nLade ein Archiv mit: `/load <id>`"
        return {"status": "success", "reply": reply}
    # ===== ARCHIV LADEN =====
    elif command == "load":
        if not args:
            return {
                "status": "error",
                "reply": "❌ Bitte eine Archiv-ID angeben, z.B. `/load 20250215_143022`"
            }
        archive_id = args[0]
        archive = chat_memory.load_chat_archive(archive_id)
        if not archive:
            # Versuche ohne "chat_" Präfix
            if not archive_id.startswith('chat_'):
                archive = chat_memory.load_chat_archive(f"chat_{archive_id}")
            if not archive:
                return {
                    "status": "error",
                    "reply": f"❌ Archiv '{archive_id}' nicht gefunden.\n\nVerwende `/archives` um verfügbare Archive zu sehen."
                }
        # Aktuellen Chat archivieren und neuen starten
        chat_memory.reset_chat(archive_current=True)
        # Geladenes Archiv in den Verlauf laden
        chat_memory.conversation_history = archive.get("messages", [])
        chat_memory.user_interests = archive.get("user_interests", {})
        chat_memory.user_preferences = archive.get("preferences", chat_memory.user_preferences)
        date = datetime.fromisoformat(archive["end_time"]).strftime("%d.%m.%Y %H:%M")
        # Memory-Eintrag
        memory_entry = f"""
## 📂 Chat geladen vom {date}
**Archiv-ID:** {archive_id}
**Nachrichten:** {archive['message_count']}
---
"""
        with open(MEMORY_FILE, "a", encoding="utf-8") as f:
            f.write(memory_entry)
        chat_memory.memory_content += memory_entry
        # Vorschau der letzten Nachrichten
        preview = ""
        for msg in archive["messages"][-4:]:  # Letzte 2 Austausche
            role = "👤" if msg["role"] == "user" else "🤖"
            content = msg['content'][:80] + "..." if len(msg['content']) > 80 else msg['content']
            preview += f"{role} {content}\n"
        return {
            "status": "success",
            "reply": f"✅ **Archiv geladen:** {archive_id}\n\n"
                    f"📅 {date}\n"
                    f"💬 {archive['message_count']} Nachrichten\n\n"
                    f"**Letzte Nachrichten:**\n{preview}\n\n"
                    f"Du kannst jetzt weiterchatten!"
        }
    # ===== AUTO-EXPLORATION =====
    elif command == "explore":
        if len(args) > 0 and args[0] == "now":
            # Sofortige Exploration starten
            asyncio.create_task(chat_memory._explore_system())
            return {
                "status": "success",
                "reply": "🔍 GABI beginnt jetzt mit der System-Exploration...\n\nDie Ergebnisse werden im Memory gespeichert."
            }
        else:
            if chat_memory.is_exploring:
                return {
                    "status": "success",
                    "reply": "🔍 GABI erkundet gerade das System...\n\nSchau gleich im Memory nach den Ergebnissen!"
                }
            else:
                inactive = int((datetime.now() - chat_memory.last_activity).total_seconds() / 60)
                return {
                    "status": "success",
                    "reply": f"⏳ Letzte Aktivität: vor {inactive} Minuten\n\n"
                            f"Auto-Exploration startet nach 10 Minuten Inaktivität.\n"
                            f"Du kannst auch `/explore now` eingeben für eine sofortige Exploration."
                }
    # ===== GMAIL BEFEHLE (KORRIGIERT) =====
    elif command == "gmail":
        if not args:
            return {
                "status": "success",
                "reply": "📧 **Gmail Befehle:**\n\n" +
                        "`/gmail list` - Alle E-Mails anzeigen\n" +
                        "`/gmail get <id>` - Bestimmte E-Mail anzeigen\n" +
                        "`/gmail help` - Diese Hilfe"
            }
        subcmd = args[0].lower()
        if subcmd == "list":
            try:
                # Gmail-Client importieren
                from integrations.gmail_client import get_gmail_client
                # Client holen
                client = get_gmail_client()
                # E-Mails abrufen
                messages = client.list_messages(max_results=10)
                if not messages:
                    return {
                        "status": "success",
                        "reply": "📭 **Keine E-Mails gefunden**"
                    }
                reply = "📬 **Ihre letzten 10 E-Mails:**\n\n"
                for i, msg in enumerate(messages, 1):
                    reply += f"**{i}.** {msg.get('subject', 'kein Betreff')}\n"
                    reply += f"   📅 {msg.get('date', 'unbekannt')}\n"
                    reply += f"   👤 {msg.get('from', 'unbekannt')}\n"
                    reply += f"   🆔 `{msg.get('id', 'unbekannt')}`\n\n"
                return {"status": "success", "reply": reply}
            except ImportError as e:
                logger.error(f"Gmail Import Fehler: {e}")
                return {
                    "status": "error",
                    "reply": "❌ Gmail-Client nicht verfügbar.\n\n" +
                            "Stellen Sie sicher, dass die google-api-python-client Bibliothek installiert ist:\n" +
                            "```bash\npip install --upgrade google-api-python-client google-auth-httplib2 google-auth-oauthlib\n```"
                }
            except Exception as e:
                logger.error(f"Gmail list Fehler: {e}")
                return {
                    "status": "error",
                    "reply": f"❌ Gmail Fehler: {str(e)}"
                }
        elif subcmd == "get" and len(args) > 1:
            try:
                msg_id = args[1]
                from integrations.gmail_client import get_gmail_client
                client = get_gmail_client()
                message = client.get_message(msg_id)
                body = client.get_message_body(message)
                reply = f"📧 **E-Mail:** {message.get('subject', 'kein Betreff')}\n"
                reply += f"**Von:** {message.get('from', 'unbekannt')}\n"
                reply += f"**Datum:** {message.get('date', 'unbekannt')}\n\n"
                reply += f"**Inhalt:**\n{body[:1000]}"
                return {"status": "success", "reply": reply}
            except Exception as e:
                logger.error(f"Gmail get Fehler: {e}")
                return {
                    "status": "error",
                    "reply": f"❌ Fehler: {str(e)}"
                }
        elif subcmd == "help":
            return {
                "status": "success",
                "reply": "📧 **Gmail Hilfe:**\n\n" +
                        "`/gmail list` - Alle E-Mails anzeigen\n" +
                        "`/gmail get <id>` - Bestimmte E-Mail anzeigen"
            }
        else:
            return {
                "status": "error",
                "reply": "❌ Unbekannter Gmail-Befehl. Verwende `/gmail help` für Hilfe."
            }
            
    # ===== TELEGRAM BEFEHLE =====
    elif command == "telegram":
        if not args:
            return {
                "status": "success",
                "reply": "📱 **Telegram Befehle:**\n\n" +
                        "`/telegram status` - Bot-Status anzeigen\n" +
                        "`/telegram users` - Aktive Benutzer anzeigen\n" +
                        "`/telegram send <nachricht>` - Nachricht an alle senden\n" +
                        "`/telegram broadcast <nachricht>` - Gleiches wie send\n" +
                        "`/telegram help` - Diese Hilfe"
            }
        
        subcmd = args[0].lower()
        
        if subcmd == "status":
            bot = get_telegram_bot()
            status_text = f"""
📱 **Telegram Bot Status:**

**Bot Token:** {'✅ Konfiguriert' if bot.bot_token and bot.bot_token != 'YOUR_TELEGRAM_BOT_TOKEN' else '❌ Nicht konfiguriert'}
**Bot läuft:** {'✅ Ja' if bot.application else '❌ Nein'}
**Aktive Benutzer:** {len(bot._user_sessions) if hasattr(bot, '_user_sessions') else 0}
**Enabled in Config:** {'✅ Ja' if config.get('telegram.enabled', False) else '❌ Nein'}

**Hinweis:** 
- Benutzer müssen dem Bot zuerst eine Nachricht schreiben, um aktiv zu werden
- Der Bot antwortet auf Direktnachrichten mit Ollama
- Du kannst Nachrichten an alle aktiven Benutzer senden
"""
            return {"status": "success", "reply": status_text}
        
        elif subcmd == "users":
            bot = get_telegram_bot()
            if not bot._user_sessions:
                return {
                    "status": "success",
                    "reply": "📭 **Keine aktiven Telegram-Benutzer**\n\nBenutzer müssen dem Bot zuerst eine Nachricht schreiben, um in der Liste zu erscheinen."
                }
            
            reply = "👥 **Aktive Telegram-Benutzer:**\n\n"
            for i, (user_id, session) in enumerate(bot._user_sessions.items(), 1):
                msg_count = len(session) // 2
                reply += f"**{i}.** Benutzer ID: `{user_id}`\n"
                reply += f"   💬 {msg_count} Unterhaltungen\n"
                if session:
                    last_msg = session[-1].get('content', '')[:50]
                    reply += f"   📝 Letzte: {last_msg}...\n"
                reply += "\n"
            
            return {"status": "success", "reply": reply}
        
        elif subcmd in ["send", "broadcast"] and len(args) > 1:
            message = ' '.join(args[1:])
            
            try:
                # Broadcast an alle aktiven Benutzer
                bot = get_telegram_bot()
                
                if not bot.application or not bot.application.bot:
                    return {
                        "status": "error",
                        "reply": "❌ Telegram Bot nicht initialisiert oder nicht konfiguriert."
                    }
                
                if not bot._user_sessions:
                    return {
                        "status": "error",
                        "reply": "❌ Keine aktiven Benutzer gefunden.\n\nBenutzer müssen dem Bot zuerst eine Nachricht schreiben."
                    }
                
                # Nachricht an alle senden
                sent = 0
                failed = 0
                errors = []
                
                for user_id in bot._user_sessions.keys():
                    try:
                        await bot.application.bot.send_message(
                            chat_id=user_id,
                            text=message,
                            parse_mode='Markdown'
                        )
                        sent += 1
                    except Exception as e:
                        failed += 1
                        errors.append(str(e))
                
                if sent > 0:
                    return {
                        "status": "success",
                        "reply": f"✅ Nachricht an {sent} Benutzer gesendet\n" +
                                (f"❌ Fehlgeschlagen: {failed}" if failed > 0 else "")
                    }
                else:
                    return {
                        "status": "error",
                        "reply": f"❌ Konnte an keinen Benutzer senden.\nFehler: {errors[0] if errors else 'Unbekannt'}"
                    }
                    
            except Exception as e:
                logger.error(f"Telegram send error: {e}")
                return {
                    "status": "error",
                    "reply": f"❌ Fehler beim Senden: {str(e)}"
                }
        
        elif subcmd == "help":
            return {
                "status": "success",
                "reply": """📱 **Telegram Bot Hilfe:**

**Was ist der Telegram Bot?**
Der Bot läuft als interaktiver Bot. Benutzer können ihm schreiben und er antwortet mit Ollama.

**Als Admin kannst du:**
• `/telegram status` - Bot-Status und Konfiguration prüfen
• `/telegram users` - Alle aktiven Benutzer anzeigen
• `/telegram send Hallo` - Nachricht an ALLE aktiven Benutzer senden

**Wichtig:**
• Benutzer müssen dem Bot zuerst eine Nachricht schreiben, um aktiv zu werden
• Der Bot speichert den Verlauf pro Benutzer
• Nachrichten werden im Markdown-Format unterstützt

**Benutzer-Befehle (im Bot):**
• /start - Bot starten
• /help - Hilfe anzeigen
• /clear - Verlauf löschen"""
            }
        
        else:
            return {
                "status": "error",
                "reply": "❌ Unbekannter Telegram-Befehl. Verwende `/telegram help` für Hilfe."
            }
            
    # ===== SHELL-BEFEHLE =====
    elif command in ["shell", "cmd", "bash", "powershell"]:
        if not args:
            return {
                "status": "success",  # Wichtig: "success" statt "error" für bessere UI
                "reply": "❌ Bitte einen Befehl angeben, z.B. `/shell dir` oder `/shell date`"
            }
        
        try:
            # Bei curl-Befehlen alle Argumente als einen String behandeln
            if args[0] == "curl":
                # Restliche Argumente zu einem String verbinden
                curl_args = ' '.join(args[1:]) if len(args) > 1 else ""
                shell_request = ShellRequest(command="curl", args=[curl_args] if curl_args else [])
            else:
                # Normale Befehle
                shell_request = ShellRequest(command=args[0], args=args[1:] if len(args) > 1 else [])
            
            # Shell-Befehl ausführen
            result = await execute_command(shell_request, token)
            
            # Ausgabe formatieren
            if result.get("status") == "success":
                output = result.get('stdout', '')
                error = result.get('stderr', '')
                
                if output:
                    # Wenn es JSON ist, besonders formatieren
                    if output.strip().startswith('{') or output.strip().startswith('['):
                        try:
                            json_data = json.loads(output)
                            formatted = json.dumps(json_data, indent=2, ensure_ascii=False)
                            return {
                                "status": "success",
                                "reply": f"```json\n{formatted[:4000]}\n```"
                            }
                        except:
                            pass
                    
                    # Normale Ausgabe
                    return {
                        "status": "success",
                        "reply": f"```\n{output[:4000]}{'...' if len(output) > 4000 else ''}\n```"
                    }
                elif error:
                    return {
                        "status": "success",  # Auch Fehler als "success" für UI
                        "reply": f"❌ **Fehler:**\n```\n{error[:2000]}\n```"
                    }
                else:
                    # Keine Ausgabe, aber erfolgreich
                    if result.get('returncode') == 0:
                        return {
                            "status": "success",
                            "reply": f"✅ Befehl `{' '.join(args)}` ausgeführt (keine Ausgabe)"
                        }
                    else:
                        return {
                            "status": "success",
                            "reply": f"❌ Befehl fehlgeschlagen (Exit-Code: {result.get('returncode')})"
                        }
            else:
                # Fehler vom execute_command
                error_msg = result.get('stderr', result.get('reply', 'Unbekannter Fehler'))
                return {
                    "status": "success",
                    "reply": f"❌ **Fehler bei Ausführung:**\n```\n{error_msg}\n```"
                }
                
        except Exception as e:
            logger.error(f"Shell-Befehl Fehler: {e}")
            return {
                "status": "success",
                "reply": f"❌ **Fehler beim Ausführen:**\n```\n{str(e)}\n```"
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
        try:
            # Hier den generate_soul Endpoint aufrufen
            import httpx
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://localhost:8000/api/memory/generate-soul",
                    headers={"Authorization": f"Bearer {token}"}
                )
                data = response.json()
            return {
                "status": "success",
                "reply": f"🧬 **Soul generiert!**\n\n{data.get('message', '')}"
            }
        except Exception as e:
            return {
                "status": "error",
                "reply": f"❌ Fehler bei Soul-Generierung: {str(e)}"
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
    **🔧 VERFÜGBARE BEFEHLE:**

    **📁 CHAT-MANAGEMENT:**
    `/new` - Neuen Chat starten (aktuellen archivieren)
    `/reset` - Chat zurücksetzen (ohne Archivierung)
    `/archives` oder `/history` - Alle Chat-Archive anzeigen
    `/load <id>` - Bestimmtes Archiv laden

    **🔍 AUTO-EXPLORATION:**
    `/explore` - Status der Auto-Exploration anzeigen
    `/explore now` - Sofortige System-Exploration starten

    **📧 GMAIL:**
    `/gmail list` - Alle E-Mails anzeigen
    `/gmail get <id>` - Bestimmte E-Mail anzeigen
    `/gmail help` - Gmail-Hilfe

    **📱 TELEGRAM:**
    `/telegram status` - Bot-Status und Konfiguration prüfen
    `/telegram users` - Alle aktiven Benutzer anzeigen
    `/telegram send <nachricht>` - Nachricht an ALLE aktiven Benutzer senden
    `/telegram broadcast <nachricht>` - Gleiches wie send
    `/telegram help` - Telegram-Hilfe

    **💻 SHELL:**
    `/shell <befehl>` - Shell-Befehl ausführen (z.B. `/shell dir`, `/shell ipconfig`)
    `/shell analyze <befehl>` - Befehl ausführen und Ergebnis analysieren

    **🧠 MEMORY & SOUL:**
    `/memory` - Letzte Erinnerungen anzeigen
    `/soul` - Persönlichkeit anzeigen
    `/generate-soul` - Soul generieren/aktualisieren
    `/learn` - Zeige was ich über dich gelernt habe

    **📊 SYSTEM:**
    `/status` - System-Status anzeigen
    `/help` - Diese Hilfe

    **✨ AUTO-EXPLORATION:**
    Nach 10 Minuten Inaktivität erkundet GABI selbstständig das System und speichert Entdeckungen im Memory.

    **💡 TIPPS:**
    • Shell-Befehle werden direkt ausgeführt und die Ausgabe angezeigt
    • Bei Gmail-Befehlen wird der Inhalt formatiert dargestellt
    • Telegram-Nachrichten können an alle aktiven Benutzer gesendet werden
    • Mit `/explore now` kannst du eine sofortige System-Erkundung starten
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
# ============ Whisper Endpoints ============
@router.get("/api/whisper/status")
async def whisper_status() -> dict:
    """Check Whisper server status."""
    try:
        whisper = get_whisper_client()
        available = whisper.is_available()
        models = whisper.get_models() if available else []
        return {"available": available, "models": models}
    except Exception as e:
        logger.error(f"Whisper status error: {e}")
        return {"available": False, "error": str(e)}
@router.post("/api/whisper/transcribe")
async def transcribe_audio(
    background_tasks: BackgroundTasks,
    file,
    language: Optional[str] = None,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """Transcribe audio file."""
    try:
        whisper = get_whisper_client()
        if not whisper.is_available():
            raise HTTPException(status_code=503, detail="Whisper server not available")
        # Save uploaded file temporarily
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        # Transcribe in background
        def transcribe_task():
            try:
                result = whisper.transcribe_file(tmp_path, language)
                logger.info(f"Transcription complete: {result}")
            finally:
                os.unlink(tmp_path)
        background_tasks.add_task(transcribe_task)
        return {"status": "processing", "message": "Transcription started"}
    except Exception as e:
        logger.error(f"Whisper transcribe error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
@router.post("/api/whisper/transcribe/sync")
async def transcribe_audio_sync(
    file,
    language: Optional[str] = None,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """Transcribe audio file synchronously."""
    try:
        whisper = get_whisper_client()
        if not whisper.is_available():
            raise HTTPException(status_code=503, detail="Whisper server not available")
        # Save uploaded file temporarily
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name
        try:
            result = whisper.transcribe_file(tmp_path, language)
            return {"status": "success", "result": result}
        finally:
            os.unlink(tmp_path)
    except Exception as e:
        logger.error(f"Whisper transcribe error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============ Telegram Endpoints ============
@router.get("/api/telegram/status")
async def telegram_api_status(_api_key: str = Depends(verify_api_key)) -> dict:
    """Check Telegram bot status."""
    bot = get_telegram_bot()
    return {
        "enabled": config.get("telegram.enabled", False),
        "bot_token_set": bool(bot.bot_token and bot.bot_token != "YOUR_TELEGRAM_BOT_TOKEN"),
        "bot_running": bot.application is not None,
        "active_sessions": len(bot._user_sessions) if hasattr(bot, '_user_sessions') else 0
    }

@router.post("/api/telegram/send")
async def send_telegram_message(
    payload: dict,
    background_tasks: BackgroundTasks,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """Send a message to all active Telegram users."""
    message = payload.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")

    try:
        bot = get_telegram_bot()
        
        if not bot.bot_token or bot.bot_token == "YOUR_TELEGRAM_BOT_TOKEN":
            return {
                "success": False, 
                "error": "Telegram bot not configured"
            }

        # Nachricht an alle aktiven Benutzer senden
        sent_count = 0
        errors = []
        
        # Asynchron senden
        async def send_to_all():
            nonlocal sent_count, errors
            for user_id in bot._user_sessions.keys():
                try:
                    if bot.application and bot.application.bot:
                        await bot.application.bot.send_message(
                            chat_id=user_id,
                            text=message,
                            parse_mode='Markdown'
                        )
                        sent_count += 1
                except Exception as e:
                    errors.append(f"User {user_id}: {str(e)}")
        
        background_tasks.add_task(send_to_all)
        
        return {
            "success": True,
            "message": f"Nachricht wird an {len(bot._user_sessions)} aktive Benutzer gesendet",
            "sent_count": sent_count,
            "errors": errors if errors else None
        }

    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        return {"success": False, "error": str(e)}

@router.get("/api/telegram/messages")
async def get_telegram_messages(
    since: int = 0,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """Get recent Telegram messages from active sessions."""
    try:
        bot = get_telegram_bot()
        
        # Sammle ALLE Nachrichten aus allen Sessions
        all_messages = []
        message_id = 0
        
        for user_id, session in bot._user_sessions.items():
            for msg in session:
                # Eindeutige ID erstellen (UserID + Index + Inhalt)
                unique_id = f"{user_id}-{message_id}-{hash(msg.get('content', '')) % 10000}"
                
                message_entry = {
                    "id": unique_id,
                    "message_id": message_id,
                    "user_id": user_id,
                    "role": msg.get("role", "unknown"),
                    "from": f"User {user_id}" if msg.get("role") == "user" else "GABI Bot",
                    "sender": f"User {user_id}" if msg.get("role") == "user" else "GABI Bot",
                    "text": msg.get("content", ""),
                    "message": msg.get("content", ""),
                    "date": msg.get("timestamp", datetime.now().isoformat())
                }
                all_messages.append(message_entry)
                message_id += 1
        
        # Nach Datum sortieren (neueste zuerst)
        all_messages.sort(key=lambda x: x["date"], reverse=True)
        
        # Wenn since > 0, nur Nachrichten seit dem Timestamp
        if since > 0:
            try:
                since_date = datetime.fromtimestamp(since / 1000).isoformat()
                all_messages = [m for m in all_messages if m["date"] >= since_date]
            except:
                pass
        
        # Auf max 50 Nachrichten begrenzen
        all_messages = all_messages[:50]
        
        logger.info(f"📨 Telegram: {len(all_messages)} Nachrichten gesendet")
        
        return {
            "messages": all_messages,
            "count": len(all_messages),
            "active_sessions": len(bot._user_sessions)
        }
        
    except Exception as e:
        logger.error(f"Telegram get messages error: {e}")
        return {"messages": [], "count": 0, "error": str(e)}

@router.post("/api/telegram/broadcast")
async def telegram_broadcast(
    payload: dict,
    _api_key: str = Depends(verify_api_key),
) -> dict:
    """Send a broadcast message to all active Telegram users."""
    message = payload.get("message", "")
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    
    try:
        bot = get_telegram_bot()
        
        if not bot.application or not bot.application.bot:
            return {
                "success": False,
                "error": "Telegram bot not initialized"
            }
        
        # An alle aktiven Benutzer senden
        sent = 0
        failed = 0
        
        for user_id in bot._user_sessions.keys():
            try:
                await bot.application.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode='Markdown'
                )
                sent += 1
            except Exception as e:
                logger.error(f"Failed to send to user {user_id}: {e}")
                failed += 1
        
        return {
            "success": True,
            "sent": sent,
            "failed": failed,
            "total": len(bot._user_sessions)
        }
        
    except Exception as e:
        logger.error(f"Telegram broadcast error: {e}")
        return {"success": False, "error": str(e)}


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
    # Check Whisper
    whisper_ok = False
    whisper_models = []
    try:
        whisper = get_whisper_client()
        whisper_ok = whisper.is_available()
        if whisper_ok:
            whisper_models = whisper.get_models()
    except Exception:
        pass
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
            "whisper": {
                "status": "connected" if whisper_ok else "offline",
                "available_models": whisper_models,
            },
            "telegram": {"enabled": config.get("telegram.enabled", False)},
            "gmail": {"enabled": config.get("gmail.enabled", False)},
        },
    }
# ============ Shell Endpoints ============
@router.post("/shell")
async def execute_command(request: ShellRequest, token: str = Header(None)):
    """
    Führt JEDEN Shell-Befehl aus - mit korrektem Timeout!
    """
    if token != config.get("api_key"):
        raise HTTPException(status_code=403, detail="Access Denied")
    
    try:
        # Befehl richtig zusammenbauen - ALLES als EINEN String
        if request.args:
            # Bei curl-Befehlen besonders vorsichtig sein
            if request.command == "curl":
                # Für curl: Alle Argumente mit Leerzeichen verbinden
                full_cmd = f"curl {' '.join(request.args)}"
            else:
                full_cmd = f"{request.command} {' '.join(request.args)}"
        else:
            full_cmd = request.command
        
        logger.info(f"🖥️ Führe aus: {full_cmd}")
        
        # WICHTIG: Timeout von 10 Sekunden
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,  # WICHTIG: text=True für direkte String-Ausgabe
            shell=True,
            timeout=10,
            encoding='cp850'  # Encoding für Windows
        )
        
        # Aktivität aktualisieren
        chat_memory.update_activity()
        
        # Bei curl: Prüfen ob es eine API-Antwort ist (JSON)
        if request.command == "curl" and result.stdout and result.stdout.strip().startswith('{'):
            try:
                # Versuche JSON zu parsen und hübsch darzustellen
                json_data = json.loads(result.stdout)
                formatted_json = json.dumps(json_data, indent=2, ensure_ascii=False)
                return {
                    "status": "success",
                    "stdout": formatted_json,
                    "stderr": result.stderr,
                    "returncode": result.returncode
                }
            except:
                pass  # Kein JSON, normal weiter
        
        # Normale Ausgabe zurückgeben
        return {
            "status": "success",
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
        
    except subprocess.TimeoutExpired:
        logger.error(f"❌ Timeout nach 10 Sekunden: {full_cmd}")
        return {
            "status": "error",
            "stdout": "",
            "stderr": "❌ Befehl dauerte zu lange (>10 Sekunden).",
            "returncode": -1
        }
    except FileNotFoundError as e:
        return {
            "status": "error",
            "stdout": "",
            "stderr": f"❌ Befehl nicht gefunden: {request.command}",
            "returncode": -1
        }
    except Exception as e:
        logger.error(f"❌ Shell Fehler: {e}")
        return {
            "status": "error",
            "stdout": "",
            "stderr": f"❌ Fehler: {str(e)}",
            "returncode": -1
        }
        
@router.post("/shell/analyze")
async def execute_and_analyze(request: ShellRequest, token: str = Header(None)):
    """
    Führt einen Befehl aus und lässt das Ergebnis von Ollama analysieren.
    """
    if token != config.get("api_key"):
        raise HTTPException(status_code=403, detail="Access Denied")
    # allowed_commands = config.get("shell.allowed_commands", [])
    # if request.command not in allowed_commands:
    #    raise HTTPException(status_code=400, detail=f"Befehl '{request.command}' nicht erlaubt!")
    # Immer erlaubt
    pass
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