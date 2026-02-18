# gateway/memory_extensions.py - Erweiterungen für MEMORY-System
"""
AutoLearnMemory: Erweiterungen für persistentes Gedächtnis.
"""
import os
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger("GATEWAY.memory")

# Pfade
BASE_DIR = Path(__file__).parent.parent
AUTOLEARN_PATH = BASE_DIR / "gateway" / "AUTOLEARN.md"
MEMORY_PATH = BASE_DIR / "MEMORY.md"
SKILLS_PATH = BASE_DIR / "SKILLS.md"


class AutoLearnMemory:
    """
    Persistentes Gedächtnis für Selbsterweiterungen.
    Lädt AUTOLEARN.md beim Start und bietet Query-Methoden.
    """

    def __init__(self):
        self.skills: Dict[str, Dict[str, Any]] = {}
        self.last_updated: Optional[datetime] = None
        self.load()

    def load(self) -> None:
        """Lädt AUTOLEARN.md beim Start."""
        if not AUTOLEARN_PATH.exists():
            logger.info("AUTOLEARN.md nicht gefunden, erstelle leere Memory")
            self.skills = {}
            return

        try:
            content = AUTOLEARN_PATH.read_text(encoding="utf-8")
            self._parse_autolearn(content)
            self.last_updated = datetime.now()
            logger.info(f"AutoLearn Memory geladen: {len(self.skills)} Skills")
        except Exception as e:
            logger.error(f"Fehler beim Laden von AUTOLEARN.md: {e}")
            self.skills = {}

    def _parse_autolearn(self, content: str) -> None:
        """Parst AUTOLEARN.md und extrahiert Skills."""
        self.skills = {}

        # Pattern für Skill-Einträge
        # ## Skill: skill_name
        # - **Anforderung**: ...
        # - **Libraries**: ...
        # - **Erstellt**: ...
        # - **Security Score**: ...
        # - **Status**: ...

        current_skill = None

        for line in content.splitlines():
            line = line.strip()

            # Neue Skill-Sektion
            if line.startswith("## Skill:"):
                skill_name = line.replace("## Skill:", "").strip()
                current_skill = skill_name
                self.skills[skill_name] = {
                    "name": skill_name,
                    "requirement": "",
                    "libraries": [],
                    "created": "",
                    "security_score": 0,
                    "status": "unknown"
                }

            # Felder innerhalb eines Skills
            elif current_skill and line.startswith("- **"):
                if "**Anforderung**" in line:
                    self.skills[current_skill]["requirement"] = line.split("**Anforderung****:")[1].strip()
                elif "**Libraries**" in line:
                    libs = line.split("**Libraries**:")[1].strip()
                    self.skills[current_skill]["libraries"] = [l.strip() for l in libs.split(",") if l.strip()]
                elif "**Erstellt**" in line:
                    self.skills[current_skill]["created"] = line.split("**Erstellt**")[1].strip()
                elif "**Security Score**" in line:
                    score_str = line.split("**Security Score****:")[1].strip().split("/")[0]
                    try:
                        self.skills[current_skill]["security_score"] = int(score_str)
                    except:
                        pass
                elif "**Status**" in line:
                    self.skills[current_skill]["status"] = line.split("**Status****:")[1].strip()

    def has_skill(self, skill_identifier: str) -> bool:
        """
        Prüft ob GABI bereits ein Modul für etwas hat.

        Args:
            skill_identifier: Name, Anforderung oder Stichwort

        Returns:
            True wenn Skill vorhanden
        """
        skill_lower = skill_identifier.lower()

        for skill_name, skill_data in self.skills.items():
            # Prüfe Skill-Name
            if skill_lower in skill_name.lower():
                return True

            # Prüfe Anforderung
            if "requirement" in skill_data:
                if skill_lower in skill_data["requirement"].lower():
                    return True

            # Prüfe Libraries
            if "libraries" in skill_data:
                for lib in skill_data["libraries"]:
                    if skill_lower in lib.lower():
                        return True

        return False

    def find_skill(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Findet einen Skill basierend auf einer Query.

        Args:
            query: Suchbegriff

        Returns:
            Skill-Dict oder None
        """
        query_lower = query.lower()

        best_match = None
        best_score = 0

        for skill_name, skill_data in self.skills.items():
            score = 0

            # Name exact match
            if query_lower == skill_name.lower():
                score = 100
            # Name partial match
            elif query_lower in skill_name.lower():
                score = 80
            # Requirement match
            elif skill_data.get("requirement", "").lower().find(query_lower) >= 0:
                score = 60
            # Library match
            else:
                for lib in skill_data.get("libraries", []):
                    if query_lower in lib.lower():
                        score = 40
                        break

            if score > best_score:
                best_score = score
                best_match = skill_data

        return best_match if best_score > 0 else None

    def get_all_skills(self) -> List[Dict[str, Any]]:
        """Gibt alle Skills als Liste zurück."""
        return list(self.skills.values())

    def get_active_skills(self) -> List[Dict[str, Any]]:
        """Gibt nur aktive Skills zurück."""
        return [
            s for s in self.skills.values()
            if s.get("status", "").find("Aktiv") >= 0 or s.get("status", "").find("✅") >= 0
        ]

    def get_context_for_prompt(self, topic: Optional[str] = None) -> str:
        """
        Erstellt Kontext-String für LLM-Prompts.

        Args:
            topic: Optional - nur Skills zu diesem Thema

        Returns:
            Formatierter String mit Skill-Informationen
        """
        skills = self.get_all_skills()

        if topic:
            skills = [s for s in skills if topic.lower() in s.get("requirement", "").lower()]

        if not skills:
            return "Keine Skills im AutoLearn Memory."

        lines = ["## AutoLearn Skills"]

        for skill in skills:
            lines.append(f"- **{skill['name']}**: {skill.get('requirement', 'N/A')}")
            if skill.get("libraries"):
                lines.append(f"  - Libraries: {', '.join(skill['libraries'])}")

        return "\n".join(lines)

    def add_skill(self, skill_name: str, requirement: str,
                  libraries: List[str], security_score: int = 100) -> None:
        """
        Fügt einen neuen Skill manuell hinzu.

        Args:
            skill_name: Name des Skills
            requirement: Anforderung/Beschreibung
            libraries: Liste der verwendeten Libraries
            security_score: Security Score (0-100)
        """
        self.skills[skill_name] = {
            "name": skill_name,
            "requirement": requirement,
            "libraries": libraries,
            "created": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "security_score": security_score,
            "status": "✅ Aktiv"
        }

        self._save()
        logger.info(f"Skill '{skill_name}' zum Memory hinzugefügt")

    def _save(self) -> None:
        """Speichert das Memory in AUTOLEARN.md."""
        lines = ["# AUTOLEARN.md\n", "Dokumentation aller Selbsterweiterungen von GABI.\n"]

        for skill_name, skill_data in self.skills.items():
            lines.append(f"\n## Skill: {skill_name}")
            lines.append(f"- **Anforderung**: {skill_data.get('requirement', 'N/A')}")
            lines.append(f"- **Libraries**: {', '.join(skill_data.get('libraries', []))}")
            lines.append(f"- **Erstellt**: {skill_data.get('created', 'N/A')}")
            lines.append(f"- **Security Score**: {skill_data.get('security_score', 0)}/100")
            lines.append(f"- **Status**: {skill_data.get('status', 'unknown')}")

        AUTOLEARN_PATH.write_text("\n".join(lines), encoding="utf-8")

    def reload(self) -> None:
        """Lädt das Memory neu von der Festplatte."""
        self.load()


# Singleton-Instanz
_memory_instance: Optional[AutoLearnMemory] = None


def get_memory() -> AutoLearnMemory:
    """Gibt die Singleton-Instanz des AutoLearn Memory zurück."""
    global _memory_instance
    if _memory_instance is None:
        _memory_instance = AutoLearnMemory()
    return _memory_instance


def has_skill(skill_identifier: str) -> bool:
    """Shortcut für has_skill()."""
    return get_memory().has_skill(skill_identifier)


def find_skill(query: str) -> Optional[Dict[str, Any]]:
    """Shortcut für find_skill()."""
    return get_memory().find_skill(query)


def get_context_for_prompt(topic: Optional[str] = None) -> str:
    """Shortcut für get_context_for_prompt()."""
    return get_memory().get_context_for_prompt(topic)
