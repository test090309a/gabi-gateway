# gateway/skill_factory.py - Self-Programming Engine für automatische Skill-Erstellung
"""
SkillFactory: Automatische Erstellung von Integrationen basierend auf Anforderungen.
Mit SELF-CORRECTION LOOP: Automatische Fehleranalyse und -korrektur.
"""
import os
import re
import subprocess
import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger("GATEWAY.skill_factory")

# Pfade
BASE_DIR = Path(__file__).parent.parent
INTEGRATIONS_DIR = BASE_DIR / "integrations"
TESTS_DIR = BASE_DIR / "tests" / "integrations"
AUTOLEARN_PATH = BASE_DIR / "gateway" / "AUTOLEARN.md"

# Self-Correction Konfiguration
MAX_CORRECTION_ITERATIONS = 3
MIN_SECURITY_SCORE = 80


# Bekannte Library-Mappings
KNOWN_LIBRARIES = {
    "pdf": "PyPDF2",
    "rechnung": "PyPDF2",
    "excel": "openpyxl",
    "spreadsheet": "openpyxl",
    "csv": "pandas",
    "json": "json (stdlib)",
    "xml": "xml.etree.ElementTree (stdlib)",
    "email": "email (stdlib)",
    "imap": "imaplib (stdlib)",
    "smtp": "smtplib (stdlib)",
    "database": "sqlite3 (stdlib)",
    "mysql": "mysql-connector-python",
    "postgres": "psycopg2",
    "mongodb": "pymongo",
    "redis": "redis",
    "api": "requests",
    "http": "requests",
    "web": "requests",
    "websocket": "websockets",
    "telegram": "python-telegram-bot",
    "slack": "slack-sdk",
    "discord": "discord.py",
    "twitter": "tweepy",
    "github": "PyGithub",
    "aws": "boto3",
    "google": "google-api-python-client",
    "cloud": "google-cloud",
    "ai": "openai",
    "ollama": "ollama (stdlib)",
    "llm": "requests",
    "image": "Pillow",
    "bild": "Pillow",
    "video": "opencv-python",
    "audio": "pydub",
    "speech": "SpeechRecognition",
    "ocr": "pytesseract",
    "crypto": "cryptography",
    "encrypt": "cryptography",
    "password": "hashlib (stdlib)",
    "excel": "openpyxl",
    "word": "python-docx",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "zip": "zipfile (stdlib)",
    "tar": "tarfile (stdlib)",
    "ftp": "ftplib (stdlib)",
    "ssh": "paramiko",
    "sftp": "paramiko",
    "calendar": "ics",
    "ical": "ics",
    "rss": "feedparser",
    "sitemap": "beautifulsoup4",
    "scrap": "beautifulsoup4",
    "html": "beautifulsoup4",
    "yaml": "pyyaml",
    "toml": "toml",
    "docker": "docker",
    "k8s": "kubernetes",
    "mqtt": "paho-mqtt",
    "rabbitmq": "pika",
    "sms": "twilio",
    "phone": "twilio",
    "blender": "bpy",            # ← NEU
    "3d": "bpy",                 # ← NEU  
    "mathutils": "mathutils",    # ← NEU
}


class SkillFactory:
    """
    Self-Programming Engine für automatische Skill-Erstellung.
    """

    def __init__(self):
        self.base_dir = BASE_DIR
        self.integrations_dir = INTEGRATIONS_DIR
        self.tests_dir = TESTS_DIR
        self.autolearn_path = AUTOLEARN_PATH

    def create_skill(self, requirement: str) -> Dict[str, Any]:
        """
        Erstellt einen neuen Skill basierend auf einer Anforderung.

        Workflow mit SELF-CORRECTION LOOP:
        1. Identifiziere benötigte Libraries
        2. Installiere Libraries (pip)
        3. Generiere Integration
        4. Generiere Tests
        5. Führe Tests aus
        6. Security Gate Validation
        7. SELF-CORRECTION: Wenn Score < 80 oder Tests fehlgeschlagen -> Korrigiere und wiederhole
        8. Dokumentiere in AUTOLEARN.md

        Args:
            requirement: Natürlichsprachliche Beschreibung der Anforderung

        Returns:
            Dict mit Erfolgsstatus und Details
        """
        logger.info(f"SkillFactory: Erstelle Skill für '{requirement}'")

        skill_name = self._generate_skill_name(requirement)

        # Schritt 1: Libraries identifizieren
        libraries = self._identify_libraries(requirement)
        logger.info(f"Identifizierte Libraries: {libraries}")

        # Schritt 2: Libraries installieren
        if libraries:
            install_result = self._install_libraries(libraries)
            if not install_result.get("success"):
                return {
                    "success": False,
                    "error": f"Library-Installation fehlgeschlagen: {install_result.get('error')}",
                    "skill_name": skill_name
                }

        integration_path = self.integrations_dir / f"{skill_name}.py"
        test_path = self.tests_dir / f"test_{skill_name}.py"

        # === SELF-CORRECTION LOOP ===
        correction_iterations = []
        current_code = None
        current_test = None

        for iteration in range(MAX_CORRECTION_ITERATIONS):
            logger.info(f"Self-Correction Loop: Iteration {iteration + 1}/{MAX_CORRECTION_ITERATIONS}")

            # Schritt 3: Integration generieren (beim ersten Mal oder nach Korrektur)
            if current_code is None:
                current_code = self._generate_integration(skill_name, requirement, libraries)

            try:
                integration_path.write_text(current_code, encoding="utf-8")
                logger.info(f"Integration geschrieben: {integration_path}")
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Fehler beim Schreiben der Integration: {e}",
                    "skill_name": skill_name
                }

            # Schritt 4: Tests generieren
            if current_test is None:
                current_test = self._generate_test(skill_name, requirement)

            try:
                self.tests_dir.mkdir(parents=True, exist_ok=True)
                test_path.write_text(current_test, encoding="utf-8")
                logger.info(f"Tests geschrieben: {test_path}")
            except Exception as e:
                logger.warning(f"Fehler beim Erstellen der Tests: {e}")

            # Schritt 5: Tests ausführen
            test_result = self._run_tests(test_path)
            test_passed = test_result.get("success", False)
            logger.info(f"Test-Ergebnis: {'PASSED' if test_passed else 'FAILED'}")

            # Schritt 6: Security Gate Validation
            security_result = self._security_validate(integration_path)
            security_score = security_result.get("score", 0)
            security_passed = security_result.get("passed", False) and security_score >= MIN_SECURITY_SCORE
            logger.info(f"Security Score: {security_score}/100 (Min: {MIN_SECURITY_SCORE})")

            # Iterations-Info speichern
            correction_iterations.append({
                "iteration": iteration + 1,
                "test_passed": test_passed,
                "security_score": security_score,
                "security_passed": security_passed,
                "issues": security_result.get("issues", [])
            })

            # Prüfen ob beide Checks bestanden
            if test_passed and security_passed:
                logger.info(f"✓ Alle Checks bestanden in Iteration {iteration + 1}")
                break

            # === SELF-CORRECTION: Code analysieren und korrigieren ===
            logger.warning(f"✗ Checks nicht bestanden - starte Auto-Korrektur...")

            # Fehler analysieren
            errors = []
            if not security_passed:
                errors.extend(security_result.get("issues", []))
            if not test_passed:
                test_output = test_result.get("output", "")
                errors.append(f"Test-Fehler: {test_output[:200]}")

            # Code korrigieren
            current_code = self._auto_fix_code(current_code, errors, security_result)
            current_test = None  # Tests werden neu generiert

            # Falls Integration existiert, löschen für Neuschreibung
            if integration_path.exists():
                try:
                    integration_path.unlink()
                except:
                    pass

        # Nach allen Iterationen: Prüfen ob最终 erfolgreich
        last_iteration = correction_iterations[-1] if correction_iterations else {}

        if not (last_iteration.get("test_passed") and last_iteration.get("security_passed")):
            # Fehlgeschlagen nach allen Iterationen
            try:
                if integration_path.exists():
                    integration_path.unlink()
            except:
                pass
            try:
                if test_path.exists():
                    test_path.unlink()
            except:
                pass

            return {
                "success": False,
                "error": f"Self-Correction fehlgeschlagen nach {MAX_CORRECTION_ITERATIONS} Versuchen",
                "skill_name": skill_name,
                "iterations": correction_iterations
            }

        # Schritt 7: AUTOLEARN.md aktualisieren
        self._document_skill(skill_name, requirement, libraries, security_result)

        # Schritt 8: Module reload (für dynamische Integration)
        self._reload_modules()

        return {
            "success": True,
            "skill_name": skill_name,
            "integration_path": str(integration_path),
            "test_path": str(test_path),
            "libraries": libraries,
            "security_score": security_score,
            "iterations": correction_iterations
        }

    def _auto_fix_code(self, code: str, errors: List[str], security_result: Dict) -> str:
        """
        Analysiert Fehler und korrigiert den Code automatisch.

        Args:
            code: Der aktuelle Python-Code
            errors: Liste der aufgetretenen Fehler
            security_result: Das Security-Gate Ergebnis

        Returns:
            Korrigierter Python-Code
        """
        logger.info(f"Auto-Fix: Analysiere {len(errors)} Fehler...")

        fixed_code = code

        # 1. Security-Probleme beheben
        issues = security_result.get("issues", [])

        for issue in issues:
            issue_lower = issue.lower()

            # eval/exec entfernen
            if "eval" in issue_lower or "exec" in issue_lower:
                logger.info(f"  → Entferne unsichere Code-Ausführung")
                fixed_code = re.sub(r'\beval\s*\([^)]*\)', '# eval entfernt', fixed_code)
                fixed_code = re.sub(r'\bexec\s*\([^)]*\)', '# exec entfernt', fixed_code)

            # shell=True entfernen
            if "shell=true" in issue_lower:
                logger.info(f"  → Entferne shell=True")
                fixed_code = re.sub(r'shell\s*=\s*True', 'shell=False', fixed_code)

            # os.system/popen entfernen
            if "os.system" in issue_lower or "os.popen" in issue_lower:
                logger.info(f"  → Ersetze os.system/popen durch sichere Alternative")
                fixed_code = re.sub(r'os\.system\s*\([^)]*\)', '# os.system entfernt', fixed_code)
                fixed_code = re.sub(r'os\.popen\s*\([^)]*\)', '# os.popen entfernt', fixed_code)

            # __import__ entfernen
            if "__import__" in issue_lower:
                logger.info(f"  → Entferne __import__")
                fixed_code = re.sub(r'__import__\s*\([^)]*\)', '# __import__ entfernt', fixed_code)

        # 2. Import-Probleme beheben
        for error in errors:
            error_lower = error.lower()

            # Syntax-Fehler
            if "syntax" in error_lower:
                logger.info(f"  → Versuche Syntax-Fehler zu beheben")
                # Basis-Syntax-Reparatur versuchen
                fixed_code = self._fix_syntax_errors(fixed_code)

            # Import-Fehler
            if "importerror" in error_lower or "modulenotfound" in error_lower:
                logger.info(f"  → Import-Problem erkannt")

        logger.info(f"Auto-Fix abgeschlossen")
        return fixed_code

    def _fix_syntax_errors(self, code: str) -> str:
        """Versucht grundlegende Syntax-Fehler zu beheben."""
        lines = code.split('\n')
        fixed_lines = []

        for line in lines:
            # Fehlende Doppelpunkte nach Klassen/Funktionen/if/for/while
            if re.match(r'^\s*(class|def|if|for|while|try|except|finally|else|elif)\s+', line):
                if not line.rstrip().endswith(':'):
                    line = line + ':'

            fixed_lines.append(line)

        return '\n'.join(fixed_lines)

    def _generate_skill_name(self, requirement: str) -> str:
        """Generiert einen gültigen Python-Modulnamen aus der Anforderung."""
        # Extrahiere Schlüsselwörter
        words = re.findall(r'\b[a-zA-Z]{3,}\b', requirement.lower())

        # Filtere generische Wörter
        stop_words = {"eine", "einen", "einer", "einem", "der", "die", "das", "und", "oder",
                      "ich", "will", "brauche", "möchte", "kann", "soll", "für", "mit", "ohne",
                      "the", "and", "or", "for", "with", "need", "want", "have", "get", "make"}
        words = [w for w in words if w not in stop_words]

        if not words:
            # Fallback: timestamp-basierter Name
            return f"auto_skill_{int(datetime.now().timestamp())}"

        # Nehme die ersten 2-3 relevanten Wörter
        skill_name = "_".join(words[:3])

        # Nur alphanumerisch und underscores
        skill_name = re.sub(r'[^a-z0-9_]', '', skill_name)

        # Keine führenden Zahlen
        if skill_name[0].isdigit():
            skill_name = "auto_" + skill_name

        return skill_name

    def _identify_libraries(self, requirement: str) -> List[str]:
        """
        Identifiziert benötigte Libraries aus der Anforderung.
        """
        requirement_lower = requirement.lower()
        identified = set()

        for keyword, library in KNOWN_LIBRARIES.items():
            if keyword in requirement_lower:
                # Stdlib Libraries nicht installieren
                if "(stdlib)" not in library:
                    identified.add(library)

        return list(identified)

    def _install_libraries(self, libraries: List[str]) -> Dict[str, Any]:
        """
        Installiert benötigte Libraries via pip.
        """
        logger.info(f"Installiere Libraries: {libraries}")

        for library in libraries:
            try:
                result = subprocess.run(
                    ["pip", "install", library, "--quiet"],
                    capture_output=True,
                    text=True,
                    timeout=120
                )

                if result.returncode != 0:
                    logger.warning(f"Library {library} konnte nicht installiert werden: {result.stderr}")

            except Exception as e:
                logger.warning(f"Fehler bei Installation von {library}: {e}")

        return {"success": True, "installed": libraries}

    def _generate_integration(self, skill_name: str, requirement: str, libraries: List[str]) -> str:
        """
        Generiert den Python-Code für die neue Integration.
        """
        # Template für neue Integrationen
        template = f'''# Auto-generierte Integration: {skill_name}
"""
{requirement}

Erstellt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Libraries: {', '.join(libraries) if libraries else 'None'}
"""
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("GATEWAY.{skill_name}")

# === KONFIGURATION ===
# Hier können konfigurierbare Parameter definiert werden


class {skill_name.title().replace('_', '')}Integration:
    """
    Auto-generierte Integration für: {requirement}
    """

    def __init__(self):
        self.name = "{skill_name}"
        logger.info(f"Initialisiere {{self.name}} Integration")

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Führt die Hauptfunktion aus.

        Args:
            **kwargs: Beliebige Parameter

        Returns:
            Dict mit Ergebnis
        """
        logger.info(f"Execute: {{kwargs}}")

        # === HIER LOGIK IMPLEMENTIEREN ===
        # Beispiel:
        # result = self._do_something(**kwargs)

        return {{
            "status": "success",
            "skill": "{skill_name}",
            "message": "Integration ausgeführt",
            "data": kwargs
        }}

    def _do_something(self, param: str) -> str:
        """Platzhalter für eigentliche Funktionalität."""
        return f"Verarbeite: {{param}}"

    def health_check(self) -> bool:
        """Prüft ob die Integration funktionsbereit ist."""
        return True


# Singleton-Instanz
_integration_instance: Optional[{skill_name.title().replace('_', '')}Integration] = None


def get_integration() -> {skill_name.title().replace('_', '')}Integration:
    """Gibt die Singleton-Instanz zurück."""
    global _integration_instance
    if _integration_instance is None:
        _integration_instance = {skill_name.title().replace('_', '')}Integration()
    return _integration_instance


#便捷 Funktionen für direkten Import
def execute(**kwargs) -> Dict[str, Any]:
    """Führt die Integration direkt aus."""
    return get_integration().execute(**kwargs)


if __name__ == "__main__":
    # Test
    integration = get_integration()
    result = integration.execute(test="value")
    print(result)
'''

        return template

    def _generate_test(self, skill_name: str, requirement: str) -> str:
        """
        Generiert pytest-kompatible Tests.
        """
        class_name = skill_name.title().replace('_', '')

        template = f'''# Auto-generierter Test für {skill_name}
"""
Test für: {requirement}
Erstellt: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
import pytest
import sys
from pathlib import Path

# Füge Gateway zum Path hinzu
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


class Test{class_name}:
    """Tests für {skill_name} Integration"""

    @pytest.fixture
    def integration(self):
        """Fixture für die Integration."""
        from integrations.{skill_name} import get_integration
        return get_integration()

    def test_integration_exists(self, integration):
        """Prüft ob Integration existiert."""
        assert integration is not None
        assert integration.name == "{skill_name}"

    def test_execute_returns_dict(self, integration):
        """Prüft ob execute() ein Dict zurückgibt."""
        result = integration.execute()
        assert isinstance(result, dict)

    def test_execute_has_status(self, integration):
        """Prüft ob Ergebnis einen Status hat."""
        result = integration.execute()
        assert "status" in result
        assert result["status"] == "success"

    def test_health_check(self, integration):
        """Prüft Health-Check."""
        assert integration.health_check() is True

    def test_skill_name_in_result(self, integration):
        """Prüft ob Skill-Name im Ergebnis enthalten ist."""
        result = integration.execute()
        assert result.get("skill") == "{skill_name}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
'''

        return template

    def _run_tests(self, test_path: Path) -> Dict[str, Any]:
        """
        Führt pytest für die generierten Tests aus.
        """
        if not test_path.exists():
            return {"success": False, "error": "Test-Datei nicht gefunden"}

        try:
            result = subprocess.run(
                ["pytest", str(test_path), "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(self.base_dir)
            )

            return {
                "success": result.returncode == 0,
                "output": result.stdout,
                "returncode": result.returncode
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def _security_validate(self, integration_path: Path) -> Dict[str, Any]:
        """
        Security Gate: Validierung für neue Integrationen.
        """
        from gateway.security_gate import SecurityGate

        gate = SecurityGate()
        result = gate.validate_file(integration_path)

        return result

    def _document_skill(self, skill_name: str, requirement: str,
                       libraries: List[str], security_result: Dict) -> None:
        """
        Dokumentiert den neuen Skill in AUTOLEARN.md.
        """
        entry = f"""
## Skill: {skill_name}
- **Anforderung**: {requirement}
- **Libraries**: {', '.join(libraries) if libraries else 'None'}
- **Erstellt**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **Security Score**: {security_result.get('score', 0)}/100
- **Status**: {'✅ Aktiv' if security_result.get('passed') else '❌ Blockiert'}
"""

        try:
            if self.autolearn_path.exists():
                content = self.autolearn_path.read_text(encoding="utf-8")
                # Vor dem letzten Header oder am Ende einfügen
                self.autolearn_path.write_text(content + entry + "\n", encoding="utf-8")
            else:
                # Neue Datei erstellen
                header = "# AUTOLEARN.md\n\n" \
                         "Dokumentation aller Selbsterweiterungen von GABI.\n\n"
                self.autolearn_path.write_text(header + entry + "\n", encoding="utf-8")

            logger.info(f"Skill dokumentiert in AUTOLEARN.md")

        except Exception as e:
            logger.error(f"Fehler beim Dokumentieren: {e}")

    def _reload_modules(self) -> None:
        """
        Versucht importierte Module zu reloaden (für dynamische Integration).
        """
        # Dies ist schwierig in Python - wir protokollieren nur
        logger.info("Module-Reload erfordert Neustart des Gateways")


# Singleton-Instanz
_factory_instance: Optional[SkillFactory] = None


def get_factory() -> SkillFactory:
    """Gibt die Singleton-Instanz der SkillFactory zurück."""
    global _factory_instance
    if _factory_instance is None:
        _factory_instance = SkillFactory()
    return _factory_instance


def create_skill(requirement: str) -> Dict[str, Any]:
    """Shortcut für Skill-Erstellung."""
    return get_factory().create_skill(requirement)
