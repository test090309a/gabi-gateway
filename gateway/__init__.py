# gateway/__init__.py
"""GABI Gateway - AI Assistant with Brain Integration."""

__version__ = "1.0.0"
__author__ = "GABI Team"
__license__ = "MIT"

from gateway.config import config
from gateway.auth import verify_api_key
from gateway.ollama_client import ollama_client

# Core components
from gateway.core.memory import chat_memory
from gateway.core.brain import get_brain
from gateway.core.router import classify_intent, auto_select_model

# Convenience exports
__all__ = [
    "__version__",
    "config",
    "verify_api_key",
    "ollama_client",
    "chat_memory",
    "get_brain",
    "classify_intent",
    "auto_select_model",
]