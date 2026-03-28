# integrations/__init__.py
"""External integrations for GABI Gateway."""

# Lazy imports to avoid circular dependencies
def get_gmail_client():
    from gateway.integrations.gmail_client import get_gmail_client
    return get_gmail_client()

def get_calendar_client():
    from gateway.integrations.google_calendar_client import get_calendar_client
    return get_calendar_client()

def get_telegram_bot():
    from gateway.integrations.telegram_bot import get_telegram_bot
    return get_telegram_bot()

def get_gui_controller():
    from gateway.integrations.gui_controller import get_gui_controller
    return get_gui_controller()

def get_whisper_client():
    from gateway.integrations.whisper_client import get_whisper_client
    return get_whisper_client()

def get_web_automation(headless=True):
    from gateway.integrations.web_automation import get_web_automation
    return get_web_automation(headless=headless)

def get_web_learning():
    from gateway.integrations.web_learning import get_web_learning
    return get_web_learning()

def get_semantic_memory():
    from gateway.integrations.semantic_memory import SemanticMemory
    return SemanticMemory()

def get_som_agent(headless=True):
    from gateway.integrations.som_agent import get_som_agent
    return get_som_agent(headless=headless)

def get_gabi_vision():
    from gateway.integrations.gabi_vision import get_gabi_vision
    return get_gabi_vision()

def get_web_vision_agent():
    from gateway.integrations.web_vision_agent import get_web_vision_agent
    return get_web_vision_agent()

__all__ = [
    "get_gmail_client",
    "get_calendar_client",
    "get_telegram_bot",
    "get_gui_controller",
    "get_whisper_client",
    "get_web_automation",
    "get_web_learning",
    "get_semantic_memory",
    "get_som_agent",
    "get_gabi_vision",
    "get_web_vision_agent",
]