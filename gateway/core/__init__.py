# gateway/core/__init__.py
"""Core components for GABI Gateway."""

from gateway.core.memory import chat_memory, ChatMemory
from gateway.core.brain import get_brain, CorpusCallosum, reset_brain
from gateway.core.router import (
    classify_intent,
    auto_select_model,
    is_complex_request,
    extract_entities,
    _classify_intent_enhanced,
    _auto_select_model,
)
from gateway.core.commands import handle_command
from gateway.core.progress import (
    ChatCancelled,
    _progress_init,
    _progress_add,
    _progress_mark_done,
    _progress_set_active_model,
    _ensure_not_cancelled,
    _progress_get,
)
from gateway.core.integration_watcher import (
    init_integration_watcher,
    get_integration_status,
    reload_single_integration,
)

__all__ = [
    # Memory
    "chat_memory",
    "ChatMemory",
    
    # Brain
    "get_brain",
    "CorpusCallosum",
    "reset_brain",
    
    # Router
    "classify_intent",
    "auto_select_model",
    "is_complex_request",
    "extract_entities",
    "_classify_intent_enhanced",
    "_auto_select_model",
    
    # Commands
    "handle_command",
    
    # Progress
    "ChatCancelled",
    "_progress_init",
    "_progress_add",
    "_progress_mark_done",
    "_progress_set_active_model",
    "_ensure_not_cancelled",
    "_progress_get",
    
    # Integration Watcher
    "init_integration_watcher",
    "get_integration_status",
    "reload_single_integration",
]