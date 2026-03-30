# gateway/core/memory.py
"""ChatMemory Klasse für Konversationsspeicherung, Erinnerungen und Auto-Exploration."""

import os
import json
import re
import platform
import asyncio
import subprocess
import shutil
import random
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Konstanten
MEMORY_FILE = "MEMORY.md"
SKILLS_FILE = "SKILLS.md"
HEARTBEAT_FILE = "HEARTBEAT.md"
NOTES_FILE = "MEMORY_NOTES.json"
CHAT_ARCHIVE_DIR = "chat_archives"


class ChatMemory:
    """Verwaltet Konversationsspeicher, Erinnerungen und Auto-Exploration."""

    def __init__(self):
        """Initialisiert das ChatMemory mit allen Komponenten."""
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
        self.user_notes = self._load_notes()
        
        # Konfigurierbare Grenzen
        self.max_memory_entries = 200      # von 100 erhöht
        self.max_memory_size = 50000       # von 10000 erhöht
        
        # Verzeichnisse erstellen
        os.makedirs(CHAT_ARCHIVE_DIR, exist_ok=True)
        
        # Auto-Exploration starten
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(self._start_auto_exploration())
            else:
                loop.run_until_complete(self._start_auto_exploration())
        except Exception:
            asyncio.create_task(self._start_auto_exploration())
    
    # ===== READ/WRITE METHODEN =====
    
    def _read_file(self, filename: str) -> str:
        """Liest eine Datei oder erstellt sie mit Standard-Inhalt."""
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            default_content = self._get_default_content(filename)
            self._write_file(filename, default_content)
            return default_content
    
    def _write_file(self, filename: str, content: str) -> None:
        """Schreibt Inhalt in eine Datei."""
        with open(filename, "w", encoding="utf-8") as f:
            f.write(content)
    
    def _get_default_content(self, filename: str) -> str:
        """Gibt Standard-Inhalt für eine Datei zurück."""
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
    
    # ===== NOTES MANAGEMENT =====
    
    def _load_notes(self) -> List[Dict[str, Any]]:
        """Lädt die gespeicherten Notizen."""
        try:
            with open(NOTES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return [n for n in data if isinstance(n, dict) and n.get("text")]
        except Exception:
            pass
        return []
    
    def _save_notes(self) -> None:
        """Speichert die Notizen."""
        with open(NOTES_FILE, "w", encoding="utf-8") as f:
            json.dump(self.user_notes[-500:], f, ensure_ascii=False, indent=2)
    
    def remember_note(self, text: str, source: str = "manual") -> tuple:
        """
        Speichert eine explizite Notiz dauerhaft.
        
        Args:
            text: Der Notiztext
            source: Quelle der Notiz (manual, chat, command)
            
        Returns:
            Tuple (entry, created) mit dem Eintrag und ob neu erstellt
        """
        clean_text = (text or "").strip()
        if not clean_text:
            return None, False
        
        now = datetime.now()
        now_iso = now.isoformat()
        
        # Prüfe auf Duplikate
        existing = next(
            (n for n in self.user_notes if n.get("text", "").strip().lower() == clean_text.lower()),
            None,
        )
        
        if existing:
            existing["confirmed_at"] = now_iso
            existing["source"] = source or existing.get("source", "manual")
            self._save_notes()
            self.update_activity()
            return existing, False
        
        # Neuen Eintrag erstellen
        entry = {
            "id": now.strftime("%Y%m%d_%H%M%S_%f"),
            "text": clean_text,
            "timestamp": now_iso,
            "source": source or "manual",
        }
        self.user_notes.append(entry)
        self._save_notes()
        
        # Auch in MEMORY.md speichern
        memory_entry = f"""
## 🧠 Gemerkt [{now.strftime('%Y-%m-%d %H:%M:%S')}]
- {clean_text}
---
"""
        try:
            with open(MEMORY_FILE, "a", encoding="utf-8") as f:
                f.write(memory_entry)
            self.memory_content += memory_entry
        except Exception as e:
            logger.error(f"Merk-Notiz konnte nicht ins Memory geschrieben werden: {e}")
        
        self.update_activity()
        self.update_heartbeat()
        return entry, True
    
    def get_remembered_notes(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Gibt gemerkte Notizen zurück (neueste zuerst).
        
        Args:
            limit: Maximale Anzahl der Notizen
            
        Returns:
            Liste der Notizen
        """
        safe_limit = max(1, min(limit, 200))
        return list(reversed(self.user_notes[-safe_limit:]))
    
    # ===== SLEEP PHASE =====
    
    def run_sleep_phase(self, reason: str = "idle") -> Dict[str, Any]:
        """
        Schlafphase: sortiert/kompaktiert Memory und aktualisiert Nutzer-Zuordnungen.
        
        Args:
            reason: Grund für die Schlafphase
            
        Returns:
            Dict mit Ergebnissen der Schlafphase
        """
        before_notes = len(self.user_notes)
        
        # 1) Dedupliziere explizite Notizen
        deduped = []
        seen = set()
        for note in self.user_notes:
            key = (note.get("text", "") or "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(note)
        self.user_notes = deduped[-500:]
        self._save_notes()
        
        # 2) Ableitung von Interessen aus den letzten User-Nachrichten
        recent_users = [m.get("content", "") for m in self.conversation_history if m.get("role") == "user"][-40:]
        for msg in recent_users:
            topic = self._detect_topic(msg)
            self.user_interests[topic] = self.user_interests.get(topic, 0) + 1
        
        # 3) Memory kompaktieren falls zu groß
        compacted = False
        if len(self.memory_content) > int(self.max_memory_size * 1.2):
            self._archive_old_memory()
            compacted = True
        
        # 4) Profil-Snapshot speichern
        profile = {
            "updated_at": datetime.now().isoformat(),
            "reason": reason,
            "user_interests": dict(sorted(self.user_interests.items(), key=lambda x: x[1], reverse=True)[:12]),
            "user_preferences": self.user_preferences,
            "notes_count": len(self.user_notes),
        }
        try:
            with open("MEMORY_PROFILE.json", "w", encoding="utf-8") as f:
                json.dump(profile, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Sleep-Phase: MEMORY_PROFILE.json konnte nicht geschrieben werden: {e}")
        
        # 5) Schlafphasen-Log
        sleep_log = (
            f"\n## 🌙 Schlafphase [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]\n"
            f"- Grund: {reason}\n"
            f"- Notizen bereinigt: {before_notes} -> {len(self.user_notes)}\n"
            f"- Memory kompaktiert: {'ja' if compacted else 'nein'}\n"
            f"- Interessen aktualisiert: {', '.join(list(profile['user_interests'].keys())[:5]) if profile['user_interests'] else 'keine'}\n"
            "---\n"
        )
        try:
            with open(MEMORY_FILE, "a", encoding="utf-8") as f:
                f.write(sleep_log)
            self.memory_content += sleep_log
        except Exception as e:
            logger.warning(f"Sleep-Phase Log konnte nicht geschrieben werden: {e}")
        
        self.update_heartbeat()
        
        return {
            "reason": reason,
            "notes_before": before_notes,
            "notes_after": len(self.user_notes),
            "memory_compacted": compacted,
            "top_topics": list(profile["user_interests"].keys())[:5],
        }
    
    # ===== AUTO-EXPLORATION =====
    
    async def _start_auto_exploration(self) -> None:
        """Startet den Auto-Exploration Task."""
        while True:
            try:
                inactive_time = (datetime.now() - self.last_activity).total_seconds()
                if inactive_time > 1800 and not self.is_exploring:  # von 600 ( 10 Minuten Inaktivität) auf 1800
                    self.run_sleep_phase(reason=f"idle-{int(inactive_time)}s")
                    await self._explore_system()
                await asyncio.sleep(900)  # von 300 (Alle 5 Minuten prüfen) auf 900 
            except Exception as e:
                logger.error(f"Auto-Exploration Fehler: {e}")
                await asyncio.sleep(60)
    
    async def _explore_system(self) -> None:
        """Erkundet das System bei Inaktivität."""
        self.is_exploring = True
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        exploration_log = f"""
## 🔍 Auto-Exploration [{timestamp}]
GABI hat das System erkundet:
"""
        try:
            # System-Informationen
            system_os = platform.system()
            
            # 1. SYSTEM-INFORMATIONEN
            if system_os == "Windows":
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
            else:
                try:
                    system_info = subprocess.run(
                        ["uname", "-a"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    exploration_log += f"### 💻 System:\n{system_info.stdout}\n"
                except Exception as e:
                    exploration_log += f"### 💻 System:\n- Keine Systeminfo verfügbar ({str(e)})\n"
            
            # 2. UMGEBUNGSVARIABLEN
            exploration_log += "\n### 🌍 Wichtige Pfade:\n"
            path_vars = ['PATH', 'USERPROFILE', 'HOME', 'TEMP', 'TMP']
            for var_name in path_vars:
                path_value = os.environ.get(var_name, '')
                if path_value:
                    exploration_log += f"  **{var_name}**: `{path_value}`\n"
            
            # 3. LAUFWERKE (nur Windows)
            if system_os == "Windows":
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
                    for drive in drives[:10]:
                        exploration_log += f"  • {drive}\n"
                except Exception as e:
                    exploration_log += f"  • Keine Laufwerksinfo verfügbar ({str(e)})\n"
            
            # 4. PROZESSE
            exploration_log += "\n### ⚙️ Prozesse:\n"
            try:
                if system_os == "Windows":
                    tasks = subprocess.run(
                        ["tasklist", "/FI", "STATUS eq running"],
                        capture_output=True,
                        text=True,
                        shell=True,
                        timeout=10,
                        encoding="cp850"
                    )
                    process_count = len([l for l in tasks.stdout.split('\n') if '.exe' in l])
                    exploration_log += f"- Laufende Prozesse: {process_count}\n"
                else:
                    tasks = subprocess.run(
                        ["ps", "aux"],
                        capture_output=True,
                        text=True,
                        timeout=10
                    )
                    process_count = len(tasks.stdout.split('\n')) - 1
                    exploration_log += f"- Laufende Prozesse: {process_count}\n"
            except Exception as e:
                exploration_log += f"- Keine Prozessinfo verfügbar ({str(e)})\n"
            
            # 5. NETZWERK
            exploration_log += "\n### 🌐 Netzwerk:\n"
            try:
                if system_os == "Windows":
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
                    exploration_log += f"- Aktive Verbindungen: {connections}\n- Listening Ports: {listening}\n"
            except Exception as e:
                exploration_log += f"- Keine Netzwerkinfo verfügbar ({str(e)})\n"
            
            # 6. CHAT-ARCHIVE
            archives = self.list_chat_archives()
            total_messages = sum(a.get('messages', 0) for a in archives)
            exploration_log += f"\n### 📚 Archive:\n- Gespeicherte Chats: {len(archives)}\n- Gesamt Nachrichten: {total_messages}\n"
            
            # 7. ZUFÄLLIGE ENTDECKUNG
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
            
            # Exploration speichern
            with open(MEMORY_FILE, "a", encoding="utf-8") as f:
                f.write(exploration_log)
            self.memory_content += exploration_log
            self.update_heartbeat()
            logger.info(f"✅ Auto-Exploration abgeschlossen: {timestamp}")
            
        except Exception as e:
            logger.error(f"❌ Exploration Fehler: {e}")
            with open(MEMORY_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n### ❌ Exploration fehlgeschlagen:\n{str(e)}\n")
        finally:
            self.is_exploring = False
    
    # ===== CHAT-ARCHIV FUNKTIONEN =====
    
    def save_chat_session(self) -> Optional[str]:
        """
        Speichert die aktuelle Chat-Session als Archiv.
        
        Returns:
            Pfad der gespeicherten Datei oder None
        """
        if len(self.conversation_history) < 2:
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{CHAT_ARCHIVE_DIR}/chat_{timestamp}.json"
        
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
        md_filename = f"{CHAT_ARCHIVE_DIR}/chat_{timestamp}.md"
        with open(md_filename, "w", encoding="utf-8") as f:
            f.write(f"# Chat-Session vom {datetime.now().strftime('%d.%m.%Y %H:%M')}\n\n")
            f.write(f"**Nachrichten:** {len(self.conversation_history)}\n\n")
            for msg in self.conversation_history:
                role = "👤 User" if msg["role"] == "user" else "🤖 GABI"
                f.write(f"### {role} ({msg.get('timestamp', '')})\n")
                f.write(f"{msg['content']}\n\n")
        
        return filename
    
    def list_chat_archives(self) -> List[Dict[str, Any]]:
        """
        Listet alle gespeicherten Chat-Archive auf.
        
        Returns:
            Liste der Archive mit Metadaten
        """
        archives = []
        for f in os.listdir(CHAT_ARCHIVE_DIR):
            if f.endswith('.json'):
                filepath = os.path.join(CHAT_ARCHIVE_DIR, f)
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
                except Exception:
                    pass
        
        archives.sort(key=lambda x: x["date"], reverse=True)
        return archives
    
    def load_chat_archive(self, archive_id: str) -> Optional[Dict[str, Any]]:
        """
        Lädt ein Chat-Archiv.
        
        Args:
            archive_id: ID des Archivs
            
        Returns:
            Archiv-Inhalt oder None
        """
        possible_files = [
            f"{CHAT_ARCHIVE_DIR}/chat_{archive_id}.json",
            f"{CHAT_ARCHIVE_DIR}/{archive_id}",
            f"{CHAT_ARCHIVE_DIR}/{archive_id}.json"
        ]
        
        for filename in possible_files:
            if os.path.exists(filename):
                try:
                    with open(filename, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception:
                    pass
        return None
    
    # ===== CHAT RESET =====
    
    def reset_chat(self, archive_current: bool = True) -> Dict[str, Any]:
        """
        Setzt den Chat zurück, optional mit Archivierung.
        
        Args:
            archive_current: Ob aktueller Chat archiviert werden soll
            
        Returns:
            Status-Dict
        """
        if archive_current and len(self.conversation_history) > 0:
            self.save_chat_session()
        
        self.conversation_history = []
        self.last_activity = datetime.now()
        
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
    
    def update_activity(self) -> None:
        """Aktualisiert den letzten Aktivitäts-Timestamp."""
        self.last_activity = datetime.now()
    
    # ===== SYSTEM PROMPT =====
    
    def get_system_prompt(self) -> str:
        """
        Optimierter System-Prompt - kurz und präzise.
        
        Returns:
            System-Prompt für das LLM
        """
        system_os = platform.system()
        if system_os == "Windows":
            dir_cmd = "dir"
            file_cmd = "type"
        else:
            dir_cmd = "ls -la"
            file_cmd = "cat"
        
        inactive_time = (datetime.now() - self.last_activity).total_seconds()
        current_time = datetime.now().strftime('%d.%m.%Y %H:%M')
        
        return f"""Du bist GABI, ein KI-Assistent auf {system_os}.

## 🛠️ WIE DU SHELL-BEFEHLE AUSFÜHRST
- Wenn der Nutzer EXPLIZIT einen Shell-Befehl möchte, antworte mit `/shell <befehl>`
- Beispiel: Nutzer: "zeig mir alle python dateien" → Du antwortest: `/shell {dir_cmd} *.py`
- Beispiel: Nutzer: "erstelle datei test.txt" → Du antwortest: `/shell echo "" > test.txt`

## ⚠️ WICHTIGE REGELN
- Führe NIEMALS Shell-Befehle aus, wenn der Nutzer nur eine Wissensfrage stellt
- Bei Wissensfragen (wie "was sind schwarze löcher") antworte NORMAL mit Text, NICHT mit /shell
- Der Nutzer erwartet von dir eine verständliche Antwort, keine Shell-Befehle

## 🆔 SYSTEM-INFO
- OS: {system_os}
- Zeit: {current_time}
- Aktiv: vor {int(inactive_time / 60)} Minuten

Antworte JETZT auf die Nutzer-Anfrage!"""
    
    # ===== HILFSMETHODEN =====
    
    def _get_recent_context(self, limit: int = 3) -> str:
        """
        Gibt die letzten limit Konversationen zurück.
        
        Args:
            limit: Anzahl der Konversationen
            
        Returns:
            Kontext-String
        """
        if not self.conversation_history:
            return "Keine vorherigen Nachrichten."
        
        context = ""
        start = max(0, len(self.conversation_history) - limit * 2)
        for i, msg in enumerate(self.conversation_history[start:]):
            role = "👤 User" if msg["role"] == "user" else "🤖 GABI"
            content = msg['content'][:100] + "..." if len(msg['content']) > 100 else msg['content']
            context += f"{role}: {content}\n"
        return context
    
    def _detect_topic(self, message: str) -> str:
        """
        Erkennt das Thema der Nachricht.
        
        Args:
            message: Die Nachricht
            
        Returns:
            Erkanntes Thema
        """
        topics = {
            "shell": ["bash", "cmd", "terminal", "command", "ausführen", "shell"],
            "git": ["git", "commit", "push", "pull", "branch"],
            "python": ["python", "code", "skript", "programm"],
            "gmail": ["mail", "email", "gmail", "nachricht"],
            "system": ["status", "health", "server", "läuft", "exploration"],
            "memory": ["erinner", "memory", "vorher", "gestern", "archiv"],
            "hilfe": ["hilfe", "help", "frage", "problem", "fehler"],
            "chat": ["new", "reset", "load", "archive", "verlauf"],
        }
        
        msg_lower = message.lower()
        for topic, keywords in topics.items():
            if any(keyword in msg_lower for keyword in keywords):
                return topic
        return "allgemein"
    
    def _learn_from_interaction(self, user_message: str, bot_response: str, timestamp: str) -> None:
        """
        Extrahiert Lernpunkte aus der Interaktion.
        
        Args:
            user_message: Die User-Nachricht
            bot_response: Die Bot-Antwort
            timestamp: Zeitstempel
        """
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
        
        for pattern, info_type in important_patterns:
            match = re.search(pattern, user_message, re.IGNORECASE)
            if match:
                self.important_info[info_type] = match.group(1)
    
    def add_to_memory(self, user_message: str, bot_response: str) -> None:
        """
        Fügt eine Konversation zum Memory hinzu.
        
        Args:
            user_message: Die User-Nachricht
            bot_response: Die Bot-Antwort
        """
        self.update_activity()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        self.conversation_history.append({"role": "user", "content": user_message, "timestamp": timestamp})
        self.conversation_history.append({"role": "assistant", "content": bot_response, "timestamp": timestamp})
        
        if len(self.conversation_history) > self.max_memory_entries:
            self.conversation_history = self.conversation_history[-self.max_memory_entries:]
        
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
            self._learn_from_interaction(user_message, bot_response, timestamp)
            
            if len(self.memory_content) > self.max_memory_size:
                self._archive_old_memory()
        except Exception as e:
            logger.error(f"Memory Update fehlgeschlagen: {e}")
        
        self.update_heartbeat()
    
    def _archive_old_memory(self) -> None:
        """Archiviert alten Memory-Inhalt."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_dir = Path(__file__).parent.parent.parent / "memory_archive"
            archive_dir.mkdir(exist_ok=True)
            archive_name = archive_dir / f"MEMORY_ARCHIVE_{timestamp}.md"
            
            lines = self.memory_content.split('\n')
            archive_content = '\n'.join(lines[:len(lines)//2])
            
            with open(archive_name, "w", encoding="utf-8") as f:
                f.write(f"""# GABI Memory Archiv vom {datetime.now().strftime('%Y-%m-%d %H:%M')}
{archive_content}
""")
            
            self.memory_content = '\n'.join(lines[len(lines)//2:])
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                f.write(self.memory_content)
            
            logger.info(f"Memory archiviert: {archive_name}")
        except Exception as e:
            logger.error(f"Archivierung fehlgeschlagen: {e}")
    
    def update_heartbeat(self) -> None:
        """Aktualisiert den Heartbeat mit aktuellen Status."""
        try:
            from gateway.ollama_client import ollama_client
            
            models_info = ollama_client.list_models()
            models_available = len(models_info.get("models", []))
            
            _, used, free = shutil.disk_usage("/")
            
            last_exploration = "Keine"
            if "Auto-Exploration" in self.memory_content:
                explorations = re.findall(r"## 🔍 Auto-Exploration \[(.*?)\]", self.memory_content)
                if explorations:
                    last_exploration = explorations[-1]
            
            archives = self.list_chat_archives()
            
            heartbeat = f"""# GABI Heartbeat & Monitoring
## Aktueller Status ({datetime.now().strftime('%d.%m.%Y %H:%M')})
| Dienst | Status | Details |
|--------|--------|---------|
| FastAPI | 🟢 Online | Port 8000 |
| Ollama | 🟢 Connected | {models_available} Modelle |
| Auto-Exploration | {'🟢 Aktiv' if not self.is_exploring else '🟡 Erkundet'} | Letzte: {last_exploration} |
| Chat-Archiv | 🟢 Bereit | {len(archives)} Archive |
## System-Ressourcen
- **Speicher frei**: {round(free / (2**30), 2)} GB
- **Betriebssystem**: {platform.system()} {platform.release()}
- **Letzte Aktivität**: vor {int((datetime.now() - self.last_activity).total_seconds() / 60)} Min.
- **Chat-Verlauf**: {len(self.conversation_history) // 2} Austausche
## Letzte Aktivitäten
"""
            for i, msg in enumerate(self.conversation_history[-5:]):
                role = "👤 User" if msg["role"] == "user" else "🤖 GABI"
                content = msg["content"][:50] + "..." if len(msg["content"]) > 50 else msg["content"]
                heartbeat += f"- {role}: {content}\n"
            
            self._write_file(HEARTBEAT_FILE, heartbeat)
            self.heartbeat_content = heartbeat
            
        except Exception as e:
            logger.error(f"Heartbeat Update fehlgeschlagen: {e}")
    
    def get_communication_style(self) -> str:
        """
        Analysiert den Kommunikationsstil des Nutzers.
        
        Returns:
            Style-Empfehlungen als String
        """
        if len(self.conversation_history) < 4:
            return ""
        
        user_msgs = [msg["content"] for msg in self.conversation_history if msg["role"] == "user"][-10:]
        if not user_msgs:
            return ""
        
        avg_len = sum(len(msg) for msg in user_msgs) / len(user_msgs)
        
        style_recommendations = []
        
        if avg_len < 50:
            style_recommendations.append("- Nutzer mag **kurze, prägnante** Antworten")
        elif avg_len > 200:
            style_recommendations.append("- Nutzer schätzt **ausführliche Erklärungen**")
        else:
            style_recommendations.append("- Nutzer bevorzugt **ausgewogene** Antworten")
        
        tech_terms = ['python', 'git', 'shell', 'api', 'json', 'config', 'code', 'terminal', 'cmd', 'bash']
        tech_count = sum(1 for msg in user_msgs for term in tech_terms if term in msg.lower())
        if tech_count > 3:
            style_recommendations.append("- Nutzer ist **technisch versiert** - Fachbegriffe können verwendet werden")
        else:
            style_recommendations.append("- Nutzer ist **weniger technisch** - Begriffe erklären")
        
        informal_words = ['hallo', 'hi', 'hey', 'tschau', 'bye', 'cool', 'super', '😊', '👍']
        formal_words = ['bitte', 'danke', 'könnten sie', 'würden sie', 'grüß gott']
        all_text = ' '.join(user_msgs).lower()
        informal_score = sum(1 for w in informal_words if w in all_text)
        formal_score = sum(1 for w in formal_words if w in all_text)
        
        if informal_score > formal_score:
            style_recommendations.append("- Nutzer kommuniziert **informell** - duzend und locker")
        else:
            style_recommendations.append("- Nutzer kommuniziert **eher formell** - respektvoll bleiben")
        
        emoji_count = sum(1 for msg in user_msgs for c in msg if c in ['😊', '👍', '🎉', '❤️', '😂', '🙏'])
        if emoji_count > 2:
            style_recommendations.append("- Nutzer verwendet **Emojis** - kann auch in Antworten verwendet werden")
        
        question_count = sum(1 for msg in user_msgs if '?' in msg)
        if question_count / len(user_msgs) > 0.5:
            style_recommendations.append("- Nutzer stellt **viele Fragen** - antworte klar und direkt")
        
        if style_recommendations:
            return "\n".join(style_recommendations)
        return ""


# Globale Memory-Instanz
chat_memory = ChatMemory()