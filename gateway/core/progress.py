# gateway/core/progress.py
"""Progress-Tracking für asynchrone Chat-Anfragen."""

import threading
import subprocess
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Globale Progress-Daten
_CHAT_PROGRESS: Dict[str, Dict[str, Any]] = {}
_CHAT_PROGRESS_LOCK = threading.Lock()


class ChatCancelled(Exception):
    """Raised when a chat request has been cancelled by the user."""
    pass


def _progress_init(request_id: str) -> None:
    """
    Initialisiert den Progress-Tracker für eine Anfrage.
    
    Args:
        request_id: Eindeutige ID der Anfrage
    """
    with _CHAT_PROGRESS_LOCK:
        _CHAT_PROGRESS[request_id] = {
            "steps": [],
            "updated_at": datetime.now().isoformat(),
            "done": False,
            "cancelled": False,
            "active_model": None,
        }


def _progress_add(request_id: Optional[str], text: str, icon: str = "fa-brain", details: str = "") -> None:
    """
    Fügt einen Progress-Schritt hinzu.
    
    Args:
        request_id: ID der Anfrage
        text: Beschreibung des Schritts
        icon: FontAwesome Icon (optional)
        details: Zusätzliche Details (optional)
    """
    if not request_id:
        return
    
    entry = {
        "text": text,
        "icon": icon,
        "time": datetime.now().isoformat(),
    }
    if details:
        entry["details"] = details
    
    with _CHAT_PROGRESS_LOCK:
        state = _CHAT_PROGRESS.get(request_id)
        if not state:
            return
        state["steps"].append(entry)
        state["updated_at"] = datetime.now().isoformat()


def _progress_set_active_model(request_id: Optional[str], model: Optional[str]) -> None:
    """
    Setzt das aktuell aktive Modell.
    
    Args:
        request_id: ID der Anfrage
        model: Modellname
    """
    if not request_id:
        return
    
    with _CHAT_PROGRESS_LOCK:
        state = _CHAT_PROGRESS.get(request_id)
        if state is not None:
            state["active_model"] = model
            state["updated_at"] = datetime.now().isoformat()


def _progress_mark_done(request_id: Optional[str]) -> None:
    """
    Markiert eine Anfrage als abgeschlossen.
    
    Args:
        request_id: ID der Anfrage
    """
    if not request_id:
        return
    
    with _CHAT_PROGRESS_LOCK:
        state = _CHAT_PROGRESS.get(request_id)
        if state is not None:
            state["done"] = True
            state["updated_at"] = datetime.now().isoformat()


def _progress_cancel(request_id: str) -> None:
    """
    Bricht eine Anfrage ab.
    
    Args:
        request_id: ID der Anfrage
    """
    with _CHAT_PROGRESS_LOCK:
        state = _CHAT_PROGRESS.get(request_id)
        if state is not None:
            state["cancelled"] = True
            state["updated_at"] = datetime.now().isoformat()


def _progress_is_cancelled(request_id: Optional[str]) -> bool:
    """
    Prüft ob eine Anfrage abgebrochen wurde.
    
    Args:
        request_id: ID der Anfrage
        
    Returns:
        True wenn abgebrochen
    """
    if not request_id:
        return False
    
    with _CHAT_PROGRESS_LOCK:
        state = _CHAT_PROGRESS.get(request_id)
        return bool(state and state.get("cancelled"))


def _ensure_not_cancelled(request_id: Optional[str]) -> None:
    """
    Prüft ob eine Anfrage abgebrochen wurde und wirft Exception.
    
    Args:
        request_id: ID der Anfrage
        
    Raises:
        ChatCancelled: Wenn die Anfrage abgebrochen wurde
    """
    if _progress_is_cancelled(request_id):
        raise ChatCancelled("Anfrage wurde abgebrochen")


def _progress_get(request_id: str, since: int = 0) -> Dict[str, Any]:
    """
    Gibt den aktuellen Progress zurück.
    
    Args:
        request_id: ID der Anfrage
        since: Index seit dem neue Schritte zurückgegeben werden sollen
        
    Returns:
        Dict mit Progress-Informationen
    """
    with _CHAT_PROGRESS_LOCK:
        state = _CHAT_PROGRESS.get(request_id)
        if not state:
            return {
                "exists": False,
                "steps": [],
                "next_index": since,
                "done": True,
                "cancelled": True
            }
        
        steps = state.get("steps", [])
        safe_since = max(0, min(int(since or 0), len(steps)))
        new_steps = steps[safe_since:]
        
        return {
            "exists": True,
            "steps": new_steps,
            "next_index": safe_since + len(new_steps),
            "done": bool(state.get("done")),
            "cancelled": bool(state.get("cancelled")),
            "active_model": state.get("active_model"),
            "updated_at": state.get("updated_at"),
        }


def _list_running_ollama_models() -> List[str]:
    """
    Listet laufende Ollama-Modelle auf.
    
    Returns:
        Liste der laufenden Modellnamen
    """
    try:
        proc = subprocess.run(
            ["ollama", "ps"],
            capture_output=True,
            text=True,
            timeout=8,
            shell=False,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            return []
        
        lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
        if len(lines) <= 1:
            return []
        
        models: List[str] = []
        for ln in lines[1:]:
            parts = ln.split()
            if parts:
                models.append(parts[0])
        return models
    except Exception as e:
        logger.debug(f"Fehler beim Auflisten der Ollama-Modelle: {e}")
        return []


def _stop_ollama_model(model: str) -> Dict[str, Any]:
    """
    Stoppt ein laufendes Ollama-Modell.
    
    Args:
        model: Name des Modells
        
    Returns:
        Dict mit Ergebnis
    """
    if not model:
        return {"ok": False, "message": "Kein Modell angegeben"}
    
    try:
        proc = subprocess.run(
            ["ollama", "stop", model],
            capture_output=True,
            text=True,
            timeout=10,
            shell=False,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "ok": proc.returncode == 0,
            "model": model,
            "stdout": (proc.stdout or "").strip(),
            "stderr": (proc.stderr or "").strip(),
            "returncode": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "model": model, "message": "Timeout beim Stoppen"}
    except Exception as e:
        return {"ok": False, "model": model, "message": str(e)}


def _progress_cleanup_old(older_than_seconds: int = 3600) -> int:
    """
    Löscht alte Progress-Einträge.
    
    Args:
        older_than_seconds: Löschen wenn älter als X Sekunden
        
    Returns:
        Anzahl gelöschter Einträge
    """
    cutoff = datetime.now().timestamp() - older_than_seconds
    removed = 0
    
    with _CHAT_PROGRESS_LOCK:
        to_remove = []
        for request_id, state in _CHAT_PROGRESS.items():
            updated_at = state.get("updated_at")
            if updated_at:
                try:
                    ts = datetime.fromisoformat(updated_at).timestamp()
                    if ts < cutoff:
                        to_remove.append(request_id)
                except Exception:
                    pass
        
        for request_id in to_remove:
            del _CHAT_PROGRESS[request_id]
            removed += 1
    
    if removed > 0:
        logger.info(f"🧹 {removed} alte Progress-Einträge gelöscht")
    
    return removed


def _progress_get_all() -> Dict[str, Dict[str, Any]]:
    """
    Gibt alle Progress-Einträge zurück (für Debugging).
    
    Returns:
        Dict aller Progress-Einträge
    """
    with _CHAT_PROGRESS_LOCK:
        return {
            rid: {
                "steps_count": len(state.get("steps", [])),
                "done": state.get("done", False),
                "cancelled": state.get("cancelled", False),
                "active_model": state.get("active_model"),
                "updated_at": state.get("updated_at"),
            }
            for rid, state in _CHAT_PROGRESS.items()
        }


def _progress_get_stats() -> Dict[str, Any]:
    """
    Gibt Statistiken über Progress-Einträge zurück.
    
    Returns:
        Dict mit Statistiken
    """
    with _CHAT_PROGRESS_LOCK:
        active = 0
        completed = 0
        cancelled = 0
        
        for state in _CHAT_PROGRESS.values():
            if state.get("cancelled"):
                cancelled += 1
            elif state.get("done"):
                completed += 1
            else:
                active += 1
        
        return {
            "total": len(_CHAT_PROGRESS),
            "active": active,
            "completed": completed,
            "cancelled": cancelled,
        }


def _progress_get_active_models() -> List[str]:
    """
    Gibt alle aktiven Modelle zurück.
    
    Returns:
        Liste der aktiven Modellnamen
    """
    models = []
    with _CHAT_PROGRESS_LOCK:
        for state in _CHAT_PROGRESS.values():
            model = state.get("active_model")
            if model and not state.get("done") and not state.get("cancelled"):
                models.append(model)
    return list(set(models))


# ===== KOMFORT-FUNKTIONEN =====

def start_progress(request_id: str, initial_message: str = "Starte Verarbeitung") -> None:
    """
    Startet einen neuen Progress-Tracker mit einer initialen Nachricht.
    
    Args:
        request_id: ID der Anfrage
        initial_message: Initiale Nachricht
    """
    _progress_init(request_id)
    _progress_add(request_id, initial_message, "fa-play")


def add_progress_step(request_id: str, message: str, icon: str = "fa-brain") -> None:
    """
    Fügt einen Progress-Schritt hinzu (kompakte Version).
    
    Args:
        request_id: ID der Anfrage
        message: Beschreibung
        icon: FontAwesome Icon
    """
    _progress_add(request_id, message, icon)


def set_active_model(request_id: str, model: str) -> None:
    """
    Setzt das aktive Modell.
    
    Args:
        request_id: ID der Anfrage
        model: Modellname
    """
    _progress_set_active_model(request_id, model)


def complete_progress(request_id: str) -> None:
    """
    Markiert eine Anfrage als abgeschlossen.
    
    Args:
        request_id: ID der Anfrage
    """
    _progress_mark_done(request_id)
    _progress_add(request_id, "Verarbeitung abgeschlossen", "fa-check-circle")


def cancel_progress(request_id: str) -> None:
    """
    Bricht eine Anfrage ab.
    
    Args:
        request_id: ID der Anfrage
    """
    _progress_cancel(request_id)
    _progress_add(request_id, "Anfrage abgebrochen", "fa-stop-circle")


def get_progress(request_id: str) -> Dict[str, Any]:
    """
    Gibt den aktuellen Progress zurück.
    
    Args:
        request_id: ID der Anfrage
        
    Returns:
        Dict mit Progress-Informationen
    """
    return _progress_get(request_id)


def is_cancelled(request_id: str) -> bool:
    """
    Prüft ob eine Anfrage abgebrochen wurde.
    
    Args:
        request_id: ID der Anfrage
        
    Returns:
        True wenn abgebrochen
    """
    return _progress_is_cancelled(request_id)


def ensure_not_cancelled(request_id: str) -> None:
    """
    Prüft ob eine Anfrage abgebrochen wurde und wirft Exception.
    
    Args:
        request_id: ID der Anfrage
        
    Raises:
        ChatCancelled: Wenn die Anfrage abgebrochen wurde
    """
    _ensure_not_cancelled(request_id)


# ===== CLEANUP TASK =====

def _start_cleanup_task(interval_seconds: int = 300) -> threading.Thread:
    """
    Startet einen Hintergrund-Thread für regelmäßige Cleanups.
    
    Args:
        interval_seconds: Intervall in Sekunden
        
    Returns:
        Der gestartete Thread
    """
    def cleanup_loop():
        while True:
            try:
                _progress_cleanup_old(3600)  # Löschen nach 1 Stunde
            except Exception as e:
                logger.error(f"Progress-Cleanup Fehler: {e}")
            threading.Event().wait(interval_seconds)
    
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True, name="Progress-Cleanup")
    cleanup_thread.start()
    logger.info(f"🧹 Progress-Cleanup gestartet (Intervall: {interval_seconds}s)")
    return cleanup_thread


# Automatischen Cleanup starten (wird beim Import ausgeführt)
_cleanup_thread = None


def init_progress_cleanup(interval_seconds: int = 300) -> None:
    """
    Initialisiert den automatischen Progress-Cleanup.
    
    Args:
        interval_seconds: Intervall in Sekunden
    """
    global _cleanup_thread
    if _cleanup_thread is None:
        _cleanup_thread = _start_cleanup_task(interval_seconds)