# gateway/api/__init__.py
"""API endpoints for GABI Gateway."""

# Import all API modules
from gateway.api import (
    chat,
    shell,
    gmail,
    calendar,
    telegram,
    gui,
    vision,
    whisper,
    comfy,
    memory,
    web,
    som,
    system,
    brain_api,
    integrations_api,
    models_api
)

# Create convenience imports
__all__ = [
    "chat",
    "shell",
    "gmail",
    "calendar",
    "telegram",
    "gui",
    "vision",
    "whisper",
    "comfy",
    "memory",
    "web",
    "som",
    "system",
    "brain_api",
    "integrations_api",
    "models_api",
]

# Version info
__version__ = "1.0.0"