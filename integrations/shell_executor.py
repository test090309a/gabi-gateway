"""Shell executor - ADMIN MODE: ALL COMMANDS ALLOWED."""
import logging
import subprocess
import os
from typing import Any

from gateway.config import config

logger = logging.getLogger(__name__)


class ShellExecutor:
    """Execute shell commands - ADMIN MODE: all commands allowed."""

    def __init__(self):
        # ADMIN MODE: Empty list = all commands allowed
        self.allowed_commands = []
        self.admin_mode = True
        logger.info("ShellExecutor initialized in ADMIN MODE - ALL COMMANDS ALLOWED")

    def execute(self, command: str, args: list[str] | None = None) -> dict[str, Any]:
        """Execute any command - ADMIN MODE."""
        args = args or []

        # ADMIN MODE: No restrictions
        # Build command
        full_cmd = f"{command} {' '.join(args)}"

        logger.info(f"[ADMIN] Executing: {full_cmd}")

        try:
            # Use shell=True for full command execution
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=60,
                shell=True,
                cwd=os.getcwd(),
                encoding='cp850',
                errors='replace'
            )

            return {
                "command": command,
                "args": args,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0,
            }
        except subprocess.TimeoutExpired:
            logger.error(f"Command timed out: {command}")
            raise TimeoutError(f"Command '{command}' timed out after 60 seconds")
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            raise RuntimeError(f"Command execution failed: {e}")

    def is_allowed(self, command: str) -> bool:
        """Check if command is allowed - ADMIN MODE: always True."""
        return True

    def get_allowed_commands(self) -> list[str]:
        """Get list of allowed commands - ADMIN MODE: all."""
        return ["*"]  # Star means all commands


shell_executor = ShellExecutor()
