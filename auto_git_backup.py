# auto_git_backup.py - Automatisches Git-Backup für GABI Gateway
"""
🤖 GABI Auto Git Backup
Überwacht das Projektverzeichnis auf Änderungen und committed automatisch nach GitHub
"""

import os
import time
import subprocess
import hashlib
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Set, Optional
import threading

# Logging einrichten
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("GIT-BACKUP")

# ===== KONFIGURATION =====
PROJECT_ROOT = Path(__file__).parent  # Verzeichnis des Skripts
STATE_FILE = PROJECT_ROOT / ".git_backup_state.json"  # Speichert den letzten Stand
CHECK_INTERVAL = 60  # Sekunden zwischen Checks (1 Minute)
AUTO_PUSH = True  # Automatisch pushen?
COMMIT_USER = "GABI Auto-Backup"
COMMIT_EMAIL = "gabi@gateway.local"

# Dateien/Ordner IGNORIEREN (Pattern)
IGNORE_PATTERNS = [
    ".git",
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    ".coverage",
    "*.log",
    "*.tmp",
    "*.temp",
    ".env",
    "venv",
    "env",
    "node_modules",
    ".idea",
    ".vscode",
    "screenshots",
    "chat_archives",
    "memory_archive",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.mp4",
    "*.mp3",
    "*.wav",
    "token.json",  # Google Token (sicherheitshalber)
    "credentials.json",
    ".git_backup_state.json",
]


class GitBackup:
    """Automatisches Git-Backup für GABI Gateway"""
    
    def __init__(self, repo_path: Path = PROJECT_ROOT):
        self.repo_path = repo_path
        self.state_file = STATE_FILE
        self.last_state = self._load_state()
        self.running = False
        self.thread = None
        
        # Stelle sicher, dass wir in einem Git-Repo sind
        self._ensure_git_repo()
        
        logger.info(f"🤖 Auto Git Backup initialisiert für: {repo_path}")
        logger.info(f"   Check-Intervall: {CHECK_INTERVAL} Sekunden")
        logger.info(f"   Auto-Push: {AUTO_PUSH}")
    
    def _ensure_git_repo(self):
        """Prüft ob das Verzeichnis ein Git-Repo ist, initialisiert falls nötig"""
        git_dir = self.repo_path / ".git"
        
        if not git_dir.exists():
            logger.info("📦 Kein Git-Repo gefunden. Initialisiere...")
            self._run_git_command(["init"])
            self._run_git_command(["remote", "add", "origin", self._get_remote_url()])
            
            # .gitignore erstellen falls nicht vorhanden
            gitignore = self.repo_path / ".gitignore"
            if not gitignore.exists():
                with open(gitignore, "w") as f:
                    f.write("\n".join(IGNORE_PATTERNS))
                logger.info("📝 .gitignore erstellt")
        
        # Git-User konfigurieren
        self._run_git_command(["config", "user.name", COMMIT_USER])
        self._run_git_command(["config", "user.email", COMMIT_EMAIL])
    
    def _get_remote_url(self) -> str:
        """Holt die Remote-URL aus Konfiguration oder fragt nach"""
        # Versuche aus config zu lesen
        try:
            from gateway.config import config
            url = config.get("git.remote_url", "")
            if url:
                return url
        except:
            pass
        
        # Fallback: Frage nach
        print("\n" + "="*50)
        print("🔗 Bitte gib deine GitHub-Repository-URL ein:")
        print("   (z.B. https://github.com/username/gabi-gateway.git)")
        print("="*50)
        url = input("URL: ").strip()
        return url
    
    def _run_git_command(self, args: List[str]) -> subprocess.CompletedProcess:
        """Führt einen Git-Befehl aus"""
        cmd = ["git"] + args
        try:
            result = subprocess.run(
                cmd,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                timeout=30,
                encoding='utf-8'
            )
            if result.returncode != 0:
                logger.warning(f"⚠️ Git Fehler: {result.stderr}")
            return result
        except Exception as e:
            logger.error(f"❌ Git Fehler: {e}")
            return subprocess.CompletedProcess(cmd, -1, "", str(e))
    
    def _get_file_hash(self, file_path: Path) -> str:
        """Berechnet SHA-256 Hash einer Datei"""
        try:
            with open(file_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        except:
            return ""
    
    def _should_ignore(self, file_path: Path) -> bool:
        """Prüft ob eine Datei ignoriert werden soll"""
        rel_path = str(file_path.relative_to(self.repo_path))
        
        for pattern in IGNORE_PATTERNS:
            if pattern in rel_path:
                return True
            if pattern.startswith("*") and rel_path.endswith(pattern[1:]):
                return True
        return False
    
    def _scan_files(self) -> Dict[str, str]:
        """Scannt alle relevanten Dateien und gibt {pfad: hash} zurück"""
        files = {}
        
        for root, dirs, filenames in os.walk(self.repo_path):
            # Ignorierte Verzeichnisse entfernen
            dirs[:] = [d for d in dirs if not self._should_ignore(Path(root) / d)]
            
            for filename in filenames:
                file_path = Path(root) / filename
                if self._should_ignore(file_path):
                    continue
                
                rel_path = str(file_path.relative_to(self.repo_path))
                files[rel_path] = self._get_file_hash(file_path)
        
        return files
    
    def _load_state(self) -> Dict[str, str]:
        """Lädt den letzten gespeicherten Stand"""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    return json.load(f)
            except:
                logger.warning("⚠️ Konnte State nicht laden, starte neu")
        return {}
    
    def _save_state(self, state: Dict[str, str]):
        """Speichert den aktuellen Stand"""
        try:
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Konnte State nicht speichern: {e}")
    
    def _get_changes(self) -> tuple[Set[str], Set[str], Set[str]]:
        """
        Ermittelt Änderungen seit letztem Check
        
        Returns:
            (added, modified, deleted): Sets mit Dateipfaden
        """
        current_files = self._scan_files()
        current_paths = set(current_files.keys())
        last_paths = set(self.last_state.keys())
        
        # Neu hinzugefügte Dateien
        added = current_paths - last_paths
        
        # Gelöschte Dateien
        deleted = last_paths - current_paths
        
        # Modifizierte Dateien (existieren in beiden, aber Hash unterschiedlich)
        modified = set()
        for path in current_paths & last_paths:
            if current_files[path] != self.last_state.get(path, ""):
                modified.add(path)
        
        return added, modified, deleted
    
    def _generate_commit_message(self, added: Set[str], modified: Set[str], deleted: Set[str]) -> str:
        """Generiert eine aussagekräftige Commit-Nachricht"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        lines = [f"🤖 Auto-Backup: {timestamp}"]
        lines.append("")
        
        if added:
            lines.append(f"✨ NEU: {len(added)} Dateien")
            for f in sorted(added)[:5]:  # Maximal 5 anzeigen
                lines.append(f"  • {f}")
            if len(added) > 5:
                lines.append(f"  • ... und {len(added)-5} weitere")
        
        if modified:
            lines.append(f"")
            lines.append(f"📝 GEÄNDERT: {len(modified)} Dateien")
            for f in sorted(modified)[:5]:
                lines.append(f"  • {f}")
            if len(modified) > 5:
                lines.append(f"  • ... und {len(modified)-5} weitere")
        
        if deleted:
            lines.append(f"")
            lines.append(f"🗑️ GELÖSCHT: {len(deleted)} Dateien")
            for f in sorted(deleted)[:5]:
                lines.append(f"  • {f}")
            if len(deleted) > 5:
                lines.append(f"  • ... und {len(deleted)-5} weitere")
        
        return "\n".join(lines)
    
    def _get_changed_file_details(self, added: Set[str], modified: Set[str]) -> str:
        """Generiert detaillierte Infos zu geänderten Dateien für den Body"""
        details = []
        
        # Python-Dateien besonders behandeln (Änderungen analysieren)
        for file_set, typ in [(added, "neu"), (modified, "geändert")]:
            for file_path in file_set:
                if file_path.endswith('.py'):
                    try:
                        full_path = self.repo_path / file_path
                        with open(full_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                        
                        # Grobe Analyse: Klassen/Funktionen finden
                        import re
                        classes = re.findall(r'class (\w+)', content)
                        functions = re.findall(r'def (\w+)', content)
                        
                        if classes or functions:
                            details.append(f"\n📄 {file_path} ({typ}):")
                            if classes:
                                details.append(f"   Klassen: {', '.join(classes[:3])}")
                            if functions:
                                details.append(f"   Funktionen: {', '.join(functions[:5])}")
                    except:
                        pass
        
        return "\n".join(details)
    
    def check_and_commit(self) -> bool:
        """
        Prüft auf Änderungen und erstellt einen Commit wenn nötig
        
        Returns:
            True wenn Commit erstellt wurde
        """
        try:
            # Änderungen erkennen
            added, modified, deleted = self._get_changes()
            
            if not (added or modified or deleted):
                logger.debug("🔍 Keine Änderungen gefunden")
                return False
            
            # Commit-Nachricht generieren
            commit_msg = self._generate_commit_message(added, modified, deleted)
            details = self._get_changed_file_details(added, modified)
            if details:
                commit_msg += f"\n\n{details}"
            
            logger.info(f"📦 Änderungen gefunden: +{len(added)} ~{len(modified)} -{len(deleted)}")
            
            # Dateien zum Commit hinzufügen
            for file_set in [added, modified]:
                for file_path in file_set:
                    self._run_git_command(["add", file_path])
            
            # Gelöschte Dateien entfernen
            for file_path in deleted:
                self._run_git_command(["rm", file_path])
            
            # Commit erstellen
            result = self._run_git_command(["commit", "-m", commit_msg])
            
            if result.returncode == 0:
                logger.info(f"✅ Commit erstellt: {len(added)+len(modified)} Dateien")
                
                # Aktuellen Stand speichern
                self.last_state = self._scan_files()
                self._save_state(self.last_state)
                
                # Pushen wenn gewünscht
                if AUTO_PUSH:
                    self.push()
                
                return True
            else:
                logger.warning("⚠️ Commit fehlgeschlagen")
                return False
                
        except Exception as e:
            logger.error(f"❌ Fehler beim Commit: {e}")
            return False
    
    def push(self):
        """Pusht die Commits zu GitHub"""
        logger.info("📤 Pushe zu GitHub...")
        
        # Aktuellen Branch herausfinden
        branch_result = self._run_git_command(["branch", "--show-current"])
        current_branch = branch_result.stdout.strip() if branch_result.stdout else "main"
        
        # Push mit aktuellem Branch
        result = self._run_git_command(["push", "-u", "origin", current_branch])
        
        if result.returncode == 0:
            logger.info(f"✅ Erfolgreich zu '{current_branch}' gepusht")
        else:
            logger.warning(f"⚠️ Push fehlgeschlagen: {result.stderr}")
    
    def start_watching(self):
        """Startet den Watchdog-Thread"""
        if self.running:
            logger.warning("⚠️ Backup läuft bereits")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._watch_loop, daemon=True)
        self.thread.start()
        logger.info(f"👀 Watchdog gestartet (Intervall: {CHECK_INTERVAL}s)")
    
    def stop_watching(self):
        """Stoppt den Watchdog-Thread"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("🛑 Watchdog gestoppt")
    
    def _watch_loop(self):
        """Hauptschleife des Watchdogs"""
        while self.running:
            try:
                self.check_and_commit()
                time.sleep(CHECK_INTERVAL)
            except Exception as e:
                logger.error(f"❌ Fehler in Watchdog-Loop: {e}")
                time.sleep(60)  # Bei Fehler länger warten
    
    def manual_backup(self):
        """Führt ein manuelles Backup durch"""
        logger.info("📦 Manuelles Backup gestartet")
        if self.check_and_commit():
            logger.info("✅ Manuelles Backup abgeschlossen")
        else:
            logger.info("ℹ️ Keine Änderungen für manuelles Backup")


# ===== KOMMANDO-ZEILEN-SCHNITTSTELLE =====

def print_status(git: GitBackup):
    """Zeigt Status-Informationen an"""
    print("\n" + "="*60)
    print("🤖 GABI AUTO GIT BACKUP - STATUS")
    print("="*60)
    print(f"📁 Projekt: {git.repo_path}")
    print(f"⏱️  Intervall: {CHECK_INTERVAL} Sekunden")
    print(f"📤 Auto-Push: {AUTO_PUSH}")
    print(f"🔄 Watchdog läuft: {git.running}")
    
    # Git-Status
    result = git._run_git_command(["status", "--porcelain"])
    if result.stdout:
        changes = len(result.stdout.strip().split('\n'))
        print(f"📊 Offene Änderungen: {changes}")
    else:
        print("📊 Offene Änderungen: 0")
    
    # Letzter Commit
    result = git._run_git_command(["log", "-1", "--pretty=format:%h | %s | %cr"])
    if result.stdout:
        print(f"🕒 Letzter Commit: {result.stdout}")
    
    print("="*60 + "\n")


def main():
    """Hauptfunktion für Kommandozeile"""
    import argparse
    
    parser = argparse.ArgumentParser(description="🤖 GABI Auto Git Backup")
    parser.add_argument("--start", action="store_true", help="Watchdog starten")
    parser.add_argument("--stop", action="store_true", help="Watchdog stoppen")
    parser.add_argument("--backup", action="store_true", help="Manuelles Backup")
    parser.add_argument("--status", action="store_true", help="Status anzeigen")
    parser.add_argument("--push", action="store_true", help="Manuell pushen")
    parser.add_argument("--interval", type=int, help="Check-Intervall setzen (Sekunden)")
    parser.add_argument("--no-push", action="store_true", help="Auto-Push deaktivieren")
    
    args = parser.parse_args()
    
    # Globale Konfiguration überschreiben
    global CHECK_INTERVAL, AUTO_PUSH
    if args.interval:
        CHECK_INTERVAL = args.interval
    if args.no_push:
        AUTO_PUSH = False
    
    git = GitBackup()
    
    if args.status:
        print_status(git)
    
    elif args.start:
        git.start_watching()
        print_status(git)
        print("💡 Das Programm läuft jetzt im Hintergrund.")
        print("   Drücke Strg+C zum Beenden.\n")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            git.stop_watching()
            print("\n👋 Watchdog gestoppt")
    
    elif args.stop:
        git.stop_watching()
    
    elif args.backup:
        git.manual_backup()
    
    elif args.push:
        git.push()
    
    else:
        # Standard: Einmal prüfen und beenden
        if git.check_and_commit():
            print("✅ Backup abgeschlossen")
        else:
            print("ℹ️ Keine Änderungen")


if __name__ == "__main__":
    main()