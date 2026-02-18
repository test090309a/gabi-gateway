# gateway/security_gate.py - Sicherheits-Validierung für neue Integrationen
"""
SecurityGate: Validierung für neue Integrationen vor Production-Merge.
Mit erweiterter GUI-Sicherheit für Windows-GUI-Steuerung.
"""
import re
import ast
import logging
from pathlib import Path
from typing import Dict, List, Any, Set

logger = logging.getLogger("GATEWAY.security_gate")

# === GUI-SICHERHEITSKONFIGURATION ===
# Erforderliche Scores für verschiedene Aktionstypen
MIN_SCORE_DEFAULT = 70
MIN_SCORE_GUI = 90  # Höherer Score für GUI-Aktionen erforderlich
MIN_SCORE_SHELL = 80  # Shell-Aktionen

# Blockierte GUI-Tastenkombinationen
BLOCKED_GUI_KEYS = [
    "alt+f4",
    "win+l",
    "ctrl+alt+delete",
    "win+ctrl+delete",
    "win+x",
    "alt+tab",
    "win+d",
    "win+m",
    "win+tab",
    "win+ctrl+shift+b",
    "ctrl+shift+escape",
]

# Gefährliche Patterns (Blacklist)
DANGEROUS_PATTERNS = [
    (r'\beval\s*\(', "eval() - Code-Injection Risiko"),
    (r'\bexec\s*\(', "exec() - Code-Injection Risiko"),
    (r'subprocess\.run\s*\([^)]*shell\s*=\s*True', "subprocess mit shell=True - Shell-Injection"),
    (r'subprocess\.Popen\s*\([^)]*shell\s*=\s*True', "Popen mit shell=True - Shell-Injection"),
    (r'__import__\s*\(\s*["\']os["\']', "__import__('os') - Potenzielle Gefahr"),
    (r'__import__\s*\(\s*["\']sys["\']', "__import__('sys') - Potenzielle Gefahr"),
    (r'import\s+os\s*$', "os-Import - Dateisystem-Zugriff"),
    (r'import\s+sys\s*$', "sys-Import - System-Zugriff"),
    (r'os\.system\s*\(', "os.system() - Shell-Befehle"),
    (r'os\.popen\s*\(', "os.popen() - Shell-Befehle"),
    (r'subprocess\.call\s*\([^)]*shell\s*=\s*True', "subprocess.call mit shell=True"),
    (r'\.write\s*\([^)]*\+', "File-Write mit String-Concatenation - Path-Traversal"),
    (r'open\s*\([^)]*\+', "open() mit String-Concatenation - Path-Traversal"),
    (r'input\s*\(', "input() - User-Input ohne Validierung"),
]

# === GUI-SICHERHEIT: Blockierte Tastenkombinationen ===
GUI_BLOCKED_KEYCOMBOS = [
    "alt+f4",    # Fenster schließen
    "alttab",    # Window Switcher
    "alt+f4",    # Schließen
    "win+l",     # Windows sperren
    "win+d",     # Desktop anzeigen (versteckt alles)
    "win+x",     # Quick Link Menu
    "win+m",     # Alle minimieren
    "ctrl+alt+delete",  # Security-Screen
    "win+ctrl+delete",  # Task-Manager
    "win+tab",   # Task View
    "f4+alt",    # Alt+F4 Variante
    "l+win",     # Win+L Variante
]

# GUI-spezifische gefährliche Patterns
GUI_DANGEROUS_PATTERNS = [
    (r'pyautogui\.hotkey\s*\(\s*["\']alt["\']\s*,\s*["\']f4["\']', "Alt+F4 - Fenster schließen (BLOCKIERT)"),
    (r'pyautogui\.hotkey\s*\(\s*["\']win["\']\s*,\s*["\']l["\']', "Win+L - Windows sperren (BLOCKIERT)"),
    (r'pyautogui\.hotkey\s*\(\s*["\']ctrl["\']\s*,\s*["\']alt["\']\s*,\s*["\']delete["\']', "Ctrl+Alt+Delete (BLOCKIERT)"),
    (r'pyautogui\.hotkey\s*\(\s*["\']win["\']\s*,\s*["\']ctrl["\']\s*,\s*["\']delete["\']', "Win+Ctrl+Delete (BLOCKIERT)"),
    (r'pyautogui\.hotkey\s*\(\s*["\']win["\']\s*,\s*["\']x["\']', "Win+X - Quick Menu (BLOCKIERT)"),
    (r'pyautogui\.hotkey\s*\(\s*["\']win["\']\s*,\s*["\']d["\']', "Win+D - Desktop (BLOCKIERT)"),
]

# Erforderlicher Mindest-Score für GUI-Operationen
GUI_MIN_SECURITY_SCORE = 90

# Erlaubte Standard-Libraries (Whitelist)
ALLOWED_STDLIB = {
    'json', 're', 'os', 'sys', 'time', 'datetime', 'math', 'random',
    'collections', 'itertools', 'functools', 'operator', 'string',
    'logging', 'argparse', 'configparser', 'csv', 'io', 'pathlib',
    'hashlib', 'base64', 'binascii', 'struct', 'codecs', 'unicodedata',
    'threading', 'multiprocessing', 'asyncio', 'concurrent', 'queue',
    'socket', 'ssl', 'urllib', 'urllib.parse', 'urllib.request',
    'http.client', 'email', 'html', 'xml.etree', 'xml.dom',
    'sqlite3', 'dbm', 'gzip', 'zipfile', 'tarfile', 'shutil',
    'tempfile', 'glob', 'fnmatch', 'linecache', 'tokenize', 'keyword',
    'ast', 'dis', 'inspect', 'traceback', 'types', 'typing',
    'warnings', 'contextlib', 'abc', 'copy', 'pickle', 'marshal',
    'pickletools', 'pprint', 'textwrap', 'unittest', 'doctest',
    'difflib', 'stat', 'locale', 'gettext', 'platform', 'errno',
    'ctypes', 'signal', 'mmap', 'pty', 'tty', 'termios', 'fcntl',
    'posixpath', 'ntpath', 'genericpath', 'posix', 'nt',
    'graphlib', 'enum', 'graphcycles', 'weakref', 'fibers',
    'sysconfig', 'builtins', '__future__', 'atexit', 'gc',
}

# Erlaubte externe Libraries für GUI und Computer Vision
ALLOWED_GUI_LIBRARIES = {
    'pyautogui',  # GUI-Automatisierung
    'pynput',     # Input-Tracking
    'pygetwindow', # Fenster-Verwaltung
    'cv2',        # OpenCV
    'numpy',      # Für OpenCV
    'PIL',        # Pillow
    'Pillow',     # Pillow (alternativer Import)
    'mss',        # Screenshots
    'mss.tools',  # MSS Tools
}

# GUI-spezifische Sicherheits-Regeln
GUI_BLOCKED_KEY_COMBOS = [
    'alt+f4',   # Fenster schließen
    'win+l',    # Windows sperren
    'ctrl+alt+delete',  # Security-Screen
    'win+ctrl+delete',  # Task-Manager
    'win+x',    # Quick Link Menu
    'win+d',    # Desktop anzeigen (minimize all)
    'win+m',    # Alle minimieren
    'win+tab',   # Task View
    'f4',       # Mit Alt: Fenster schließen
    'l',        # Mit Win: Sperren
]

# Minimale Security-Scores
MIN_SCORE_STANDARD = 70    # Standard für normale Integrationen
MIN_SCORE_GUI = 90         # Erhöht für GUI-Operationen
MIN_SCORE_CRITICAL = 95    # Kritische Operationen


class SecurityGate:
    """
    Sicherheits-Validierung für neue Integrationen.
    Prüft auf gefährliche Patterns und validiert Imports.
    """

    def __init__(self, min_score: int = 70):
        """
        Args:
            min_score: Minimale Punktzahl für Freigabe (0-100)
        """
        self.min_score = min_score
        self.max_score = 100

    def validate_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Validiert eine Python-Datei.

        Args:
            file_path: Pfad zur Python-Datei

        Returns:
            Dict mit:
                - passed: bool - Freigabe erteilt
                - score: int - Sicherheits-Score (0-100)
                - issues: List[str] - Gefundene Probleme
                - warnings: List[str] - Warnungen
        """
        if not file_path.exists():
            return {
                "passed": False,
                "score": 0,
                "issues": [f"Datei nicht gefunden: {file_path}"],
                "warnings": []
            }

        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            return {
                "passed": False,
                "score": 0,
                "issues": [f"Fehler beim Lesen: {e}"],
                "warnings": []
            }

        return self.validate_code(content, str(file_path))

    def validate_code(self, code: str, source_name: str = "unknown") -> Dict[str, Any]:
        """
        Validiert Python-Code.

        Args:
            code: Python-Quellcode
            source_name: Name der Quelle (für Fehlermeldungen)

        Returns:
            Dict mit Validierungsergebnis
        """
        issues: List[str] = []
        warnings: List[str] = []

        # 1. Pattern-basierte Prüfung (Blacklist)
        pattern_issues = self._check_dangerous_patterns(code)
        issues.extend(pattern_issues)

        # 2. AST-basierte Prüfung
        try:
            ast_issues, ast_warnings = self._check_ast(code)
            issues.extend(ast_issues)
            warnings.extend(ast_warnings)
        except SyntaxError as e:
            issues.append(f"Syntax-Fehler: {e}")

        # 3. Import-Validierung
        import_issues = self._check_imports(code)
        issues.extend(import_issues)

        # 4. Score berechnen
        score = self._calculate_score(issues, warnings)

        # 5. Freigabeentscheidung
        passed = score >= self.min_score and len(issues) == 0

        return {
            "passed": passed,
            "score": score,
            "issues": issues,
            "warnings": warnings,
            "source": source_name
        }

    def _check_dangerous_patterns(self, code: str) -> List[str]:
        """Prüft auf gefährliche Patterns."""
        issues = []

        for pattern, description in DANGEROUS_PATTERNS:
            matches = re.finditer(pattern, code, re.IGNORECASE | re.MULTILINE)
            for match in matches:
                # Zeilennummer ermitteln
                line_num = code[:match.start()].count('\n') + 1
                issues.append(f"Zeile {line_num}: {description}")

        return issues

    def _check_ast(self, code: str) -> tuple[List[str], List[str]]:
        """AST-basierte Sicherheitsprüfung."""
        issues = []
        warnings = []

        try:
            tree = ast.parse(code)

            for node in ast.walk(tree):
                # Prüfe auf exec/eval-Aufrufe
                if isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ('exec', 'eval'):
                            line_num = node.lineno or 0
                            issues.append(f"Zeile {line_num}: Dynamische Code-Ausführung ({node.func.id})")

                # Prüfe auf unsichere Funktionsaufrufe
                if isinstance(node, ast.Attribute):
                    # os.system, os.popen, etc.
                    if isinstance(node.value, ast.Name):
                        if node.value.id == 'os' and node.attr in ('system', 'popen'):
                            line_num = node.lineno or 0
                            issues.append(f"Zeile {line_num}: Potenziell unsicherer Aufruf os.{node.attr}")

        except SyntaxError:
            pass  # Wird woanders behandelt

        return issues, warnings

    def _check_imports(self, code: str) -> List[str]:
        """Prüft Imports auf potenzielle Gefahren."""
        issues = []

        # Regex für Import-Zeilen
        import_pattern = r'^(?:from\s+(\S+)\s+import|import\s+(\S+))'

        for i, line in enumerate(code.splitlines(), 1):
            line = line.strip()
            if line.startswith('#'):
                continue

            match = re.match(import_pattern, line)
            if match:
                module = match.group(1) or match.group(2)

                # Erlaubte Module prüfen
                base_module = module.split('.')[0]

                # Einige stdlib-Module mit Vorsicht erlauben
                if base_module in ('os', 'sys', 'subprocess', 'socket'):
                    # Nur mit spezifischen Checks erlauben
                    pass
                elif base_module not in ALLOWED_STDLIB:
                    # Nicht-stdlib und nicht-bekannte Module
                    if base_module not in self._get_known_safe_modules():
                        warnings.append(f"Zeile {i}: Unbekannter Import: {module}")

        return issues

    def _get_known_safe_modules(self) -> Set[str]:
        """Gibt Menge bekannter sicherer externer Module zurück."""
        return {
            'requests', 'httpx', 'aiohttp', 'websockets',
            'fastapi', 'uvicorn', 'starlette',
            'telegram', 'telegram.ext',
            'google', 'google.api', 'google.cloud',
            'oauth2client', 'google_auth',
            'pandas', 'numpy', 'matplotlib',
            'Pillow', 'PIL',
            'sqlalchemy', 'psycopg2', 'pymysql',
            'redis', 'pymongo',
            'pydantic', 'typer', 'click',
            'colorlog', 'python-dotenv',
            'jwt', 'cryptography', 'pyjwt',
            'bcrypt', 'passlib',
            'pytest', 'pytest_asyncio',
            'apscheduler',
            # GUI-Bibliotheken
            'pyautogui', 'PyAutoGUI',
            'cv2', 'opencv',
            'numpy',
        }

    def _calculate_score(self, issues: List[str], warnings: List[str]) -> int:
        """Berechnet Sicherheits-Score basierend auf Issues und Warnings."""
        score = self.max_score

        # Je schwerer das Issue, desto mehr Abzug
        critical_keywords = ['eval', 'exec', 'shell=True', 'os.system', 'os.popen']
        high_keywords = ['__import__', 'subprocess']
        medium_keywords = ['input', 'write', 'open']

        for issue in issues:
            issue_lower = issue.lower()
            if any(kw in issue_lower for kw in critical_keywords):
                score -= 30
            elif any(kw in issue_lower for kw in high_keywords):
                score -= 20
            elif any(kw in issue_lower for kw in medium_keywords):
                score -= 10
            else:
                score -= 5

        # Warnings reduzieren Score weniger
        score -= len(warnings) * 2

        # Minimaler Score ist 0
        return max(0, score)

    def validate_integration(self, integration_code: str) -> Dict[str, Any]:
        """
        Alias für validate_code für Integrationen.
        """
        return self.validate_code(integration_code, "integration")

    def validate_gui_action(self, action: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Validiert eine GUI-Aktion bevor sie ausgeführt wird.

        Args:
            action: Die GUI-Aktion (z.B. 'click', 'hotkey', 'type')
            params: Parameter für die Aktion

        Returns:
            Dict mit 'allowed', 'score', 'reason'
        """
        # Prüfe ob GUI-Aktion erlaubt basierend auf aktuellem Score
        current_score = self._get_current_security_score()

        if current_score < MIN_SCORE_GUI:
            return {
                "allowed": False,
                "score": current_score,
                "reason": f"Security-Score ({current_score}) ist zu niedrig für GUI-Aktionen (min: {MIN_SCORE_GUI})"
            }

        # Prüfe auf blockierte Tastenkombinationen
        if action == "hotkey" and params:
            keys = params.get("keys", [])
            combo = "+".join(keys).lower()

            if combo in BLOCKED_GUI_KEYS:
                # Erlaube nur mit explizitem Override
                if not params.get("override_allowed", False):
                    return {
                        "allowed": False,
                        "score": current_score,
                        "reason": f"Tastenkombination '{combo}' ist aus Sicherheitsgründen blockiert"
                    }

        # Prüfe auf gefährliche Koordinaten (außerhalb des Bildschirms)
        if action == "click" and params:
            x, y = params.get("x", 0), params.get("y", 0)
            # Hier könnten wir Bildschirmgröße prüfen

        return {
            "allowed": True,
            "score": current_score,
            "reason": "GUI-Aktion erlaubt"
        }

    def _get_current_security_score(self) -> int:
        """
        Gibt den aktuellen Security-Score zurück.
        In einer erweiterten Version könnte dies dynamisch aus verschiedenen Quellen berechnet werden.
        """
        # Für jetzt: Score basierend auf Konfiguration
        # Könnte erweitert werden mit: Benutzer-Verifizierung, Zeit seit letter Aktion, etc.
        return 80  # Default Score

    def validate_gui_action(self, action: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Validiert eine GUI-Aktion vor der Ausführung.

        Args:
            action: Die GUI-Aktion (z.B. "click", "hotkey", "type")
            params: Parameter der Aktion

        Returns:
            Dict mit 'allowed', 'score', 'reason'
        """
        # Standard-Score für GUI-Aktionen
        required_score = MIN_SCORE_GUI

        # Hole aktuellen Score (könnte aus einer Integration kommen)
        current_score = 100  # Default: voll vertrauenswürdig

        # Blockierte Aktionen prüfen
        if params:
            # Prüfe auf blockierte Tastenkombinationen
            if action == "hotkey":
                keys = params.get("keys", [])
                combo = "+".join(keys).lower()
                if combo in BLOCKED_GUI_KEYS:
                    # Nur mit expliziter Erlaubnis
                    if not params.get("explicit_allow", False):
                        return {
                            "allowed": False,
                            "score": current_score,
                            "reason": f"Blockierte Tastenkombination: {combo}"
                        }

            # Koordinaten-Validierung für Clicks
            if action in ["click", "safe_click"]:
                x = params.get("x", 0)
                y = params.get("y", 0)
                # Prüfe ob Koordinaten im Bildschirmbereich
                # (Wird zur Laufzeit geprüft)

        # Score-Anforderung prüfen
        if current_score < required_score:
            return {
                "allowed": False,
                "score": current_score,
                "reason": f"Score {current_score} < erforderlich {required_score}"
            }

        return {
            "allowed": True,
            "score": current_score,
            "reason": "GUI-Aktion erlaubt"
        }

    def check_key_combo_allowed(self, key_combo: str, explicit_override: bool = False) -> Dict[str, Any]:
        """
        Prüft ob eine Tastenkombination erlaubt ist.

        Args:
            key_combo: Die Tastenkombination (z.B. "ctrl+c", "alt+f4")
            explicit_override: Erlaubt das Überschreiben der Blockierung

        Returns:
            Dict mit 'allowed' und 'reason'
        """
        combo = key_combo.lower().replace(" ", "")

        if combo in BLOCKED_GUI_KEYS:
            if explicit_override:
                logger.warning(f"Tastenkombination {combo} mit Override erlaubt")
                return {"allowed": True, "reason": "Explicit override"}
            return {
                "allowed": False,
                "reason": f"Tastenkombination '{combo}' ist aus Sicherheitsgründen blockiert"
            }

        return {"allowed": True, "reason": "Erlaubt"}


# Singleton-Instanz
_gate_instance = None


def get_security_gate() -> SecurityGate:
    """Gibt die Singleton-Instanz des Security Gates zurück."""
    global _gate_instance
    if _gate_instance is None:
        _gate_instance = SecurityGate()
    return _gate_instance


def validate_code(code: str) -> Dict[str, Any]:
    """Shortcut für Code-Validierung."""
    return get_security_gate().validate_code(code)


def validate_file(file_path: Path) -> Dict[str, Any]:
    """Shortcut für Datei-Validierung."""
    return get_security_gate().validate_file(file_path)
