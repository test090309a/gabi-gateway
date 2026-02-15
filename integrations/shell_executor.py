"""Shell executor with allowlist security."""
import logging
import subprocess
from typing import Any

from gateway.config import config

logger = logging.getLogger(__name__)


class ShellExecutor:
    """Execute shell commands from an allowlist only."""

    def __init__(self):
        self.allowed_commands = config.get("shell.allowed_commands", [])
        logger.info(f"ShellExecutor initialized with allowed commands: {self.allowed_commands}")

    def execute(self, command: str, args: list[str] | None = None) -> dict[str, Any]:
        """Execute a command from the allowlist with optional arguments."""
        args = args or []

        # Security check: command must be in allowlist
        if command not in self.allowed_commands:
            logger.warning(f"Blocked command not in allowlist: {command}")
            raise PermissionError(
                f"Command '{command}' is not allowed. Allowed commands: {self.allowed_commands}"
            )

        # Build safe command - no shell=True, args as list
        full_cmd = [command] + args

        logger.info(f"Executing allowed command: {' '.join(full_cmd)}")

        try:
            result = subprocess.run(
                full_cmd,
                capture_output=True,
                text=True,
                timeout=30,
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
            raise TimeoutError(f"Command '{command}' timed out after 30 seconds")
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            raise RuntimeError(f"Command execution failed: {e}")

    def is_allowed(self, command: str) -> bool:
        """Check if a command is in the allowlist."""
        return command in self.allowed_commands

    def get_allowed_commands(self) -> list[str]:
        """Get list of allowed commands."""
        return self.allowed_commands.copy()


shell_executor = ShellExecutor()
