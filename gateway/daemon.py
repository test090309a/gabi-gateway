# gateway/daemon.py - Das proaktive Herz von GABI
"""
GatewayDaemon: Hintergrunddienst der alle 5 Minuten HEARTBEAT.md auf Tasks prüft.
Mit PROAKTIVEM ENVIRONMENT-SENSING: Scannt das System nach verfügbaren Tools.
"""
import time
import threading
import logging
import os
import re
import subprocess
import shutil
import platform
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Set

logger = logging.getLogger("GATEWAY.daemon")

# Pfade
BASE_DIR = Path(__file__).parent.parent
HEARTBEAT_PATH = BASE_DIR / "HEARTBEAT.md"
AUTOLEARN_PATH = BASE_DIR / "gateway" / "AUTOLEARN.md"

# Environment-Sensing Konfiguration
ENV_SCAN_INTERVAL = 3600  # 1x pro Stunde (3600 Sekunden)
TASK_SCAN_INTERVAL = 300  # 5 Minuten für HEARTBEAT-Tasks
KNOWN_TOOLS = {
    "ffmpeg": "Video/Audio-Verarbeitung",
    "ffprobe": "Media-Analyse",
    "tesseract": "OCR - Texterkennung in Bildern",
    "docker": "Container-Management",
    "git": "Versionskontrolle",
    "python": "Python-Interpreter",
    "python3": "Python-Interpreter",
    "node": "Node.js Runtime",
    "npm": "Node Package Manager",
    "pip": "Python Package Manager",
    "pip3": "Python Package Manager",
    "curl": "HTTP-Client",
    "wget": "File-Download",
    "rsync": "File-Sync",
    "pandoc": "Dokument-Konvertierung",
    "pdftk": "PDF-Manipulation",
    "imagemagick": "Bildverarbeitung",
    "magick": "Bildverarbeitung (ImageMagick 7)",
    "ghostscript": "PDF/PostScript",
    "latex": "LaTeX Dokumentenerstellung",
    "make": "Build-Tool",
    "cmake": "Build-Tool",
    "gcc": "C/C++ Compiler",
    "g++": "C++ Compiler",
    "rustc": "Rust Compiler",
    "go": "Go Compiler",
    "java": "Java Runtime",
    "javac": "Java Compiler",
    "gradle": "Java Build-Tool",
    "maven": "Java Build-Tool",
    "kubectl": "Kubernetes CLI",
    "terraform": "Infrastructure as Code",
    "ansible": "Automatisierung",
    "psql": "PostgreSQL Client",
    "mysql": "MySQL Client",
    "mongosh": "MongoDB Shell",
    "redis-cli": "Redis Client",
    "sqlite3": "SQLite CLI",
    "pwsh": "PowerShell Core",
    "code": "VS Code",
    "notepad": "Notepad",
    "notepad++": "Notepad++",
    "sublime": "Sublime Text",
    "7z": "7-Zip Archiver",
    "tar": "Tar Archiver",
    "zip": "Zip Archiver",
    "unzip": "Unzip",
}

# Bereits gescannte Tools (vermeidet doppelte Tasks)
_discovered_tools: Set[str] = set()
_last_env_scan: float = 0  # Zeitstempel des letzten Environment-Scans
_last_env_scan: float = 0  # Zeitstempel des letzten Environment-Scans


class Task:
    """Repräsentiert eine Aufgabe aus HEARTBEAT.md"""
    def __init__(self, task_id: str, description: str, category: str, completed: bool = False):
        self.task_id = task_id
        self.description = description
        self.category = category  # "user" oder "system"
        self.completed = completed
        self.created_at = datetime.now()

    def __repr__(self):
        status = "✓" if self.completed else " "
        return f"[{status}] {self.task_id}: {self.description}"


class GatewayDaemon:
    """
    Thread-basierter Hintergrunddienst für automatische Aufgabenverarbeitung.
    Prüft alle 5 Minuten HEARTBEAT.md auf neue Tasks.
    """

    def __init__(self, interval_seconds: int = 300):
        self.interval = interval_seconds
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.skill_factory = None

    def start(self):
        """Startet den Daemon in einem separaten Thread."""
        if self.running:
            logger.warning("Daemon läuft bereits")
            return

        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="GABI-Daemon")
        self.thread.start()
        logger.info(f"Daemon gestartet (Intervall: {self.interval}s)")

    def stop(self):
        """Stoppt den Daemon."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        logger.info("Daemon gestoppt")

    def _run_loop(self):
        """Main loop des Daemons."""
        logger.info("Daemon-Loop gestartet")

        # Initial scan
        self._process_tasks()

        while self.running:
            try:
                time.sleep(self.interval)
                if self.running:
                    self._process_tasks()
            except Exception as e:
                logger.error(f"Fehler im Daemon-Loop: {e}")
                time.sleep(60)  # Bei Fehler eine Minute warten

    def _process_tasks(self):
        """Liest HEARTBEAT.md und verarbeitet neue Tasks."""
        try:
            # === PROAKTIVES ENVIRONMENT SENSING ===
            # Scanne das System nach neuen Tools (1x pro Stunde)
            self._scan_environment()

            # HEARTBEAT Tasks verarbeiten
            tasks = self._parse_heartbeat()
            if not tasks:
                return

            pending_tasks = [t for t in tasks if not t.completed]

            if pending_tasks:
                logger.info(f"{len(pending_tasks)} offene Tasks gefunden")

                for task in pending_tasks:
                    self._execute_task(task)

        except Exception as e:
            logger.error(f"Fehler bei Task-Verarbeitung: {e}")

    def _scan_environment(self) -> None:
        """
        Proaktives Environment-Sensing: Scannt das System nach verfügbaren Tools
        und erstellt automatisch HEARTBEAT-Tasks für neue Integrationen.
        Läuft nur 1x pro Stunde (ENV_SCAN_INTERVAL).
        """
        global _discovered_tools, _last_env_scan

        current_time = time.time()

        # Prüfen ob genug Zeit vergangen ist seit dem letzten Scan
        if current_time - _last_env_scan < ENV_SCAN_INTERVAL:
            # Noch nicht wieder scannen
            return

        _last_env_scan = current_time
        logger.info("🔍 Starte Environment-Scan...")

        # System-Plattform
        system = platform.system().lower()

        # PATH Variable auslesen
        path_env = os.environ.get("PATH", "")
        path_dirs = path_env.split(os.pathsep) if path_env else []

        found_tools = []

        for tool, description in KNOWN_TOOLS.items():
            # Prüfe ob Tool verfügbar ist
            if shutil.which(tool):
                found_tools.append(tool)
                logger.info(f"  ✓ Tool gefunden: {tool} ({description})")

                # Wenn neu entdeckt -> Task erstellen
                if tool not in _discovered_tools:
                    logger.info(f"  ✨ NEUES TOOL ENTDECKT: {tool} - erstelle Task")
                    self._create_environment_task(tool, description)
                    _discovered_tools.add(tool)

        logger.info(f"Environment-Scan abgeschlossen: {len(found_tools)}/{len(KNOWN_TOOLS)} Tools gefunden")

    def _create_environment_task(self, tool: str, description: str) -> None:
        """
        Erstellt automatisch eine HEARTBEAT-Task für ein entdecktes Tool.

        Args:
            tool: Name des Tools
            description: Beschreibung des Tools
        """
        try:
            if not HEARTBEAT_PATH.exists():
                # Erstelle HEARTBEAT.md falls nicht vorhanden
                HEARTBEAT_PATH.write_text("# HEARTBEAT.md\n\n## System Tasks\n", encoding="utf-8")

            content = HEARTBEAT_PATH.read_text(encoding="utf-8")

            # Generiere Task-ID
            task_num = len(re.findall(r"TASK-\d+", content)) + 1
            task_id = f"TASK-AUTO-{task_num:03d}"

            # Prüfe ob Task bereits existiert (vermeide Duplikate)
            if tool.lower() in content.lower():
                logger.debug(f"Task für {tool} existiert bereits")
                return

            # Erstelle Task-Eintrag
            task_entry = f"- [ ] {task_id}: Erstelle {tool}-Integration für {description}\n"

            # Füge vor "## User Tasks" oder am Ende ein
            if "## User Tasks" in content:
                content = content.replace("## User Tasks", f"## System Tasks\n{task_entry}\n## User Tasks")
            else:
                content += f"\n## System Tasks\n{task_entry}"

            HEARTBEAT_PATH.write_text(content, encoding="utf-8")
            logger.info(f"  📝 Task erstellt: {task_id} für {tool}")

        except Exception as e:
            logger.error(f"Fehler beim Erstellen der Environment-Task für {tool}: {e}")

    def _parse_heartbeat(self) -> List[Task]:
        """Parst HEARTBEAT.md und extrahiert Tasks."""
        tasks = []

        if not HEARTBEAT_PATH.exists():
            logger.debug("HEARTBEAT.md nicht gefunden")
            return tasks

        try:
            content = HEARTBEAT_PATH.read_text(encoding="utf-8")

            # Regex für Tasks: - [ ] TASK-XXX: description oder - [x] TASK-XXX: description
            pattern = r"- \[([ x])\] (TASK-\d+): (.+)$"

            for line in content.splitlines():
                match = re.match(pattern, line.strip())
                if match:
                    status = match.group(1).lower() == "x"
                    task_id = match.group(2)
                    description = match.group(3).strip()

                    # Kategorie bestimmen (vorherigen Header suchen)
                    category = "system"  # Default
                    tasks.append(Task(task_id, description, category, status))

            logger.debug(f"{len(tasks)} Tasks geparst")
            return tasks

        except Exception as e:
            logger.error(f"Fehler beim Parsen von HEARTBEAT.md: {e}")
            return tasks

    def _execute_task(self, task: Task):
        """Führt eine einzelne Task aus."""
        logger.info(f"Führe Task aus: {task.task_id} - {task.description}")

        # Skill Factory importieren wenn benötigt
        if not self.skill_factory:
            try:
                from gateway.skill_factory import SkillFactory
                self.skill_factory = SkillFactory()
            except ImportError as e:
                logger.error(f"Kann SkillFactory nicht importieren: {e}")
                return

        # Aufgabe basierend auf Beschreibung ausführen
        task_lower = task.description.lower()

        # Check ob es eine AutoLearn-Anfrage ist
        if any(keyword in task_lower for keyword in ["lerne", "integration", "fähigkeit", "skill", "install"]):
            self._handle_skill_request(task)
        else:
            logger.info(f"Task '{task.task_id}' ist kein AutoLearn-Task, übersprungen")

    def _handle_skill_request(self, task: Task):
        """Verarbeitet eine Skill-Anfrage mit der Skill Factory."""
        try:
            result = self.skill_factory.create_skill(task.description)

            if result.get("success"):
                # Task als erledigt markieren
                self._mark_task_completed(task.task_id)
                logger.info(f"Skill erfolgreich erstellt: {result.get('skill_name')}")
            else:
                logger.error(f"Skill-Erstellung fehlgeschlagen: {result.get('error')}")

        except Exception as e:
            logger.error(f"Fehler bei Skill-Erstellung: {e}")

    def _mark_task_completed(self, task_id: str):
        """Markiert eine Task in HEARTBEAT.md als erledigt."""
        try:
            if not HEARTBEAT_PATH.exists():
                return

            content = HEARTBEAT_PATH.read_text(encoding="utf-8")
            # - [ ] TASK-XXX: -> - [x] TASK-XXX:
            updated = re.sub(
                rf"- \[ \] ({re.escape(task_id)}):",
                r"- [x] \1:",
                content
            )

            HEARTBEAT_PATH.write_text(updated, encoding="utf-8")
            logger.info(f"Task {task_id} als erledigt markiert")

        except Exception as e:
            logger.error(f"Fehler beim Markieren der Task: {e}")

    def run_task_manually(self, task_description: str) -> Dict:
        """Führt eine Task manuell aus (für API-Aufrufe)."""
        task = Task(
            task_id=f"TASK-MANUAL-{int(time.time())}",
            description=task_description,
            category="user",
            completed=False
        )
        self._execute_task(task)
        return {"status": "executed", "task": task.task_id}


# Singleton-Instanz
_daemon_instance: Optional[GatewayDaemon] = None


def get_daemon() -> GatewayDaemon:
    """Gibt die Singleton-Instanz des Daemons zurück."""
    global _daemon_instance
    if _daemon_instance is None:
        _daemon_instance = GatewayDaemon()
    return _daemon_instance


def start_daemon():
    """Startet den Daemon (Shortcut)."""
    daemon = get_daemon()
    daemon.start()


def stop_daemon():
    """Stoppt den Daemon (Shortcut)."""
    daemon = get_daemon()
    daemon.stop()
