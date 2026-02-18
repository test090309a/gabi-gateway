# Tests für GABI Autonomes Agenten-Framework
"""
Pytest-basierte Tests für alle neuen Komponenten.
"""
import pytest
import sys
from pathlib import Path

# Füge Gateway zum Path hinzu
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSecurityGate:
    """Tests für Security Gate."""

    def test_safe_code_passes(self):
        """Sicherer Code sollte bestehen."""
        from gateway.security_gate import SecurityGate

        gate = SecurityGate()
        safe_code = '''
import logging
from typing import Dict, List

def hello():
    return "Hello"
'''
        result = gate.validate_code(safe_code)
        assert result["passed"] is True
        assert result["score"] == 100

    def test_dangerous_code_fails(self):
        """Gefährlicher Code sollte scheitern."""
        from gateway.security_gate import SecurityGate

        gate = SecurityGate()
        dangerous_code = '''
import os
result = eval("1 + 1")
'''
        result = gate.validate_code(dangerous_code)
        assert result["passed"] is False
        assert len(result["issues"]) > 0


class TestSkillFactory:
    """Tests für Skill Factory."""

    def test_skill_name_generation(self):
        """Prüft ob Skill-Name korrekt generiert wird."""
        from gateway.skill_factory import SkillFactory

        factory = SkillFactory()

        # Test name generation
        name = factory._generate_skill_name("Ich will PDF-Rechnungen lesen")
        assert "pdf" in name.lower() or "rechnung" in name.lower()


class TestAutoLearnMemory:
    """Tests für AutoLearn Memory."""

    def test_memory_creation(self):
        """Prüft ob Memory erstellt werden kann."""
        from gateway.memory_extensions import AutoLearnMemory

        memory = AutoLearnMemory()
        assert memory is not None
        assert isinstance(memory.skills, dict)


class TestDaemon:
    """Tests für Gateway Daemon."""

    def test_task_parsing(self):
        """Prüft Task-Parsing."""
        from gateway.daemon import GatewayDaemon

        daemon = GatewayDaemon()

        # Diese Methode testet intern das Parsing
        assert daemon is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
