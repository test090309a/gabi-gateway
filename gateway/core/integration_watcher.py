# gateway/core/integration_watcher.py
"""Hot-Reload System für dynamische Integrationen."""

import os
import sys
import time
import threading
import importlib
import inspect
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Globale Registry für dynamisch geladene Integrationen
_dynamic_integrations: Dict[str, Any] = {}
_last_scan_times: Dict[str, float] = {}
FILE_WATCH_INTERVAL = 5  # Sekunden zwischen Datei-Scans

# Logger für Hot-Reload (wird nach dem Import initialisiert)
_hotreload_logger = None


def _get_hotreload_logger():
    """Lazy Logger für Hot-Reload."""
    global _hotreload_logger
    if _hotreload_logger is None:
        _hotreload_logger = logging.getLogger("GATEWAY.hotreload")
    return _hotreload_logger


def _get_integrations_dir() -> Path:
    """
    Gibt den Pfad zum integrations/ Verzeichnis zurück.
    
    Returns:
        Path zum integrations Verzeichnis
    """
    # Gehe von gateway/core/integration_watcher.py zu gateway/../integrations
    current_dir = Path(__file__).parent  # gateway/core
    gateway_dir = current_dir.parent  # gateway
    integrations_dir = gateway_dir / "integrations"
    return integrations_dir


def _scan_integrations_dir() -> List[Dict[str, Any]]:
    """
    Scannt das integrations/ Verzeichnis nach neuen .py Dateien.
    
    Returns:
        Liste der gefundenen Integrationen mit Metadaten
    """
    integrations_dir = _get_integrations_dir()
    
    if not integrations_dir.exists():
        _get_hotreload_logger().debug(f"Integrations-Verzeichnis nicht gefunden: {integrations_dir}")
        return []
    
    integrations = []
    for py_file in integrations_dir.glob("*.py"):
        # Überspringe interne Dateien
        if py_file.name.startswith("_") or py_file.name == "__init__.py":
            continue
        
        # Überspringe Dateien, die nicht geladen werden sollen
        skip_files = ["semantic_memory.py", "som_agent.py", "gabi_vision.py", "telegram_bot.py"]
        if py_file.name in skip_files:
            continue
        
        try:
            stat = py_file.stat()
            mtime = stat.st_mtime
            size = stat.st_size
            
            integrations.append({
                "name": py_file.stem,
                "path": str(py_file),
                "mtime": mtime,
                "size": size,
                "exists": True
            })
        except Exception as e:
            _get_hotreload_logger().warning(f"Fehler beim Scannen von {py_file}: {e}")
    
    return integrations


def _load_integration_module(module_name: str) -> Optional[Any]:
    """
    Lädt ein Integration-Modul dynamisch mit importlib.
    
    Args:
        module_name: Name des Moduls (ohne 'integrations.' prefix)
        
    Returns:
        Das geladene Modul oder None bei Fehler
    """
    try:
        # Ändere von "integrations.{module_name}" zu "gateway.integrations.{module_name}"
        full_module_name = f"gateway.integrations.{module_name}"
        
        # Bestehendes Modul aus Cache entfernen
        if full_module_name in sys.modules:
            old_module = sys.modules[full_module_name]
            _get_hotreload_logger().debug(f"Entferne altes Modul: {full_module_name}")
            del sys.modules[full_module_name]
        
        # Modul importieren
        module = importlib.import_module(full_module_name)
        
        # Modul reloaden (falls schon importiert)
        importlib.reload(module)
        
        _get_hotreload_logger().info(f"Hot-Reload: Modul '{module_name}' geladen")
        return module
        
    except ImportError as e:
        _get_hotreload_logger().error(f"Hot-Reload Import Fehler für '{module_name}': {e}")
        return None
    except Exception as e:
        _get_hotreload_logger().error(f"Hot-Reload Fehler für '{module_name}': {e}")
        return None


def _register_integration_routes(module_name: str, module: Any, app=None) -> bool:
    """
    Registriert automatisch neue FastAPI-Routen aus einem Modul.
    
    Args:
        module_name: Name des Moduls
        module: Das geladene Modul
        app: FastAPI App (optional, wird bei Bedarf importiert)
        
    Returns:
        True wenn Routen registriert wurden
    """
    try:
        # Suche nach FastAPI-Routern im Modul
        router = getattr(module, "router", None)
        if router:
            # Versuche app aus dem aktuellen Kontext zu holen
            if app is None:
                try:
                    # Dynamischer Import um Zirkelimporte zu vermeiden
                    from gateway.main import app as main_app
                    app = main_app
                except ImportError:
                    _get_hotreload_logger().warning("main_app konnte nicht importiert werden")
                    return False
            
            # Prüfe ob Router bereits registriert ist
            if router not in [r for r in app.routes if hasattr(r, 'path')]:
                app.include_router(router, prefix=f"/api/{module_name}", tags=[module_name])
                _get_hotreload_logger().info(f"Neue Route registriert: /api/{module_name}")
                return True
        
        # Suche nach eigenständigen Endpoint-Funktionen
        endpoints_found = False
        for name, obj in inspect.getmembers(module, inspect.isfunction):
            if name.startswith("router_") or name.endswith("_endpoint"):
                _get_hotreload_logger().info(f"Funktion gefunden: {name} in {module_name}")
                endpoints_found = True
        
        return endpoints_found
        
    except Exception as e:
        _get_hotreload_logger().error(f"Fehler beim Registrieren von Routen für '{module_name}': {e}")
        return False


def check_and_reload_integrations(app=None) -> Dict[str, Any]:
    """
    Prüft auf neue/geänderte Integrationen und lädt sie dynamisch.
    
    Args:
        app: FastAPI App (optional)
        
    Returns:
        Dict mit Informationen über geladene Integrationen
    """
    current_integrations = _scan_integrations_dir()
    reloads = []
    errors = []
    
    for integration in current_integrations:
        name = integration["name"]
        path = integration["path"]
        mtime = integration["mtime"]
        
        # Neue oder geänderte Datei?
        last_time = _last_scan_times.get(name, 0)
        if mtime > last_time:
            _get_hotreload_logger().info(f"Hot-Reload: Neue/geänderte Integration erkannt: {name}")
            
            try:
                # Modul laden
                module = _load_integration_module(name)
                if module:
                    # Routen registrieren
                    _register_integration_routes(name, module, app)
                    
                    # In Registry speichern
                    _dynamic_integrations[name] = {
                        "module": module,
                        "path": path,
                        "loaded_at": time.time(),
                        "mtime": mtime
                    }
                    
                    reloads.append(name)
                else:
                    errors.append(f"Modul {name} konnte nicht geladen werden")
                    
            except Exception as e:
                error_msg = f"Fehler beim Laden von {name}: {e}"
                _get_hotreload_logger().error(error_msg)
                errors.append(error_msg)
            
            _last_scan_times[name] = mtime
    
    return {
        "reloaded": reloads,
        "errors": errors,
        "total": len(_dynamic_integrations),
        "scanned": len(current_integrations)
    }


def _integration_watcher_loop(app=None, interval: float = FILE_WATCH_INTERVAL):
    """
    Hintergrund-Loop für die Integration-Überwachung.
    
    Args:
        app: FastAPI App
        interval: Scan-Intervall in Sekunden
    """
    _get_hotreload_logger().info(f"Integration-Watcher gestartet (Intervall: {interval}s)")
    
    while True:
        try:
            check_and_reload_integrations(app)
        except Exception as e:
            _get_hotreload_logger().error(f"Integration-Watcher Fehler: {e}")
        
        time.sleep(interval)


def start_integration_watcher(app=None, interval: float = FILE_WATCH_INTERVAL) -> threading.Thread:
    """
    Startet den Hintergrund-Thread für Integration-Überwachung.
    
    Args:
        app: FastAPI App
        interval: Scan-Intervall in Sekunden
        
    Returns:
        Der gestartete Thread
    """
    watcher_thread = threading.Thread(
        target=_integration_watcher_loop,
        args=(app, interval),
        daemon=True,
        name="Integration-Watcher"
    )
    watcher_thread.start()
    _get_hotreload_logger().info(f"Integration-Watcher Thread gestartet (ID: {watcher_thread.ident})")
    return watcher_thread


def stop_integration_watcher() -> None:
    """
    Stoppt den Integration-Watcher (setzt Flag, der Thread ist daemon).
    Daemon-Threads werden automatisch beendet wenn das Hauptprogramm endet.
    """
    _get_hotreload_logger().info("Integration-Watcher wird gestoppt (daemon thread)")
    # Daemon-Threads können nicht direkt gestoppt werden
    # Sie enden automatisch wenn das Hauptprogramm endet
    # Hier nur Logging


def get_loaded_integrations() -> Dict[str, Any]:
    """
    Gibt alle geladenen Integrationen zurück.
    
    Returns:
        Dict mit Informationen über geladene Integrationen
    """
    result = {}
    for name, info in _dynamic_integrations.items():
        result[name] = {
            "loaded_at": info.get("loaded_at"),
            "path": info.get("path"),
            "mtime": info.get("mtime")
        }
    return result


def reload_single_integration(module_name: str, app=None) -> Dict[str, Any]:
    """
    Lädt eine einzelne Integration neu.
    
    Args:
        module_name: Name des Moduls
        app: FastAPI App
        
    Returns:
        Dict mit Ergebnis
    """
    _get_hotreload_logger().info(f"Manuelles Reload: {module_name}")
    
    try:
        # Prüfe ob Datei existiert
        integrations_dir = _get_integrations_dir()
        module_path = integrations_dir / f"{module_name}.py"
        
        if not module_path.exists():
            return {
                "success": False,
                "error": f"Modul {module_name}.py nicht gefunden in {integrations_dir}"
            }
        
        # Modul laden
        module = _load_integration_module(module_name)
        if not module:
            return {
                "success": False,
                "error": f"Modul {module_name} konnte nicht geladen werden"
            }
        
        # Routen registrieren
        _register_integration_routes(module_name, module, app)
        
        # Update mtime
        stat = module_path.stat()
        _last_scan_times[module_name] = stat.st_mtime
        
        # In Registry speichern
        _dynamic_integrations[module_name] = {
            "module": module,
            "path": str(module_path),
            "loaded_at": time.time(),
            "mtime": stat.st_mtime
        }
        
        return {
            "success": True,
            "message": f"Integration {module_name} erfolgreich geladen",
            "module": module_name
        }
        
    except Exception as e:
        _get_hotreload_logger().error(f"Manuelles Reload Fehler für {module_name}: {e}")
        return {
            "success": False,
            "error": str(e),
            "module": module_name
        }


def unload_integration(module_name: str) -> Dict[str, Any]:
    """
    Entlädt eine Integration (entfernt sie aus der Registry).
    
    Args:
        module_name: Name des Moduls
        
    Returns:
        Dict mit Ergebnis
    """
    if module_name not in _dynamic_integrations:
        return {
            "success": False,
            "error": f"Integration {module_name} nicht geladen"
        }
    
    try:
        # Aus Registry entfernen
        del _dynamic_integrations[module_name]
        
        # Aus last_scan_times entfernen
        if module_name in _last_scan_times:
            del _last_scan_times[module_name]
        
        _get_hotreload_logger().info(f"Integration {module_name} entladen")
        
        return {
            "success": True,
            "message": f"Integration {module_name} entladen"
        }
        
    except Exception as e:
        _get_hotreload_logger().error(f"Fehler beim Entladen von {module_name}: {e}")
        return {
            "success": False,
            "error": str(e),
            "module": module_name
        }


def get_integration_status() -> Dict[str, Any]:
    """
    Gibt den Status aller Integrationen zurück.
    
    Returns:
        Dict mit Statusinformationen
    """
    integrations_dir = _get_integrations_dir()
    scanned = _scan_integrations_dir()
    
    return {
        "watcher_running": True,  # Daemon-Thread läuft
        "interval_seconds": FILE_WATCH_INTERVAL,
        "integrations_dir": str(integrations_dir),
        "integrations_dir_exists": integrations_dir.exists(),
        "loaded_count": len(_dynamic_integrations),
        "loaded_integrations": list(_dynamic_integrations.keys()),
        "scanned_files": [i["name"] for i in scanned],
        "last_scan_times": _last_scan_times
    }


def force_rescan(app=None) -> Dict[str, Any]:
    """
    Erzwingt einen sofortigen Rescan des Integrations-Verzeichnisses.
    
    Args:
        app: FastAPI App
        
    Returns:
        Dict mit Ergebnissen
    """
    _get_hotreload_logger().info("Force Rescan ausgeführt")
    
    # Setze alle mtimes zurück, damit alle Dateien als neu erkannt werden
    for name in list(_last_scan_times.keys()):
        _last_scan_times[name] = 0
    
    # Führe Scan aus
    result = check_and_reload_integrations(app)
    
    return result


# ===== INITIALISIERUNG =====
# Diese Funktion sollte beim Start der App aufgerufen werden
_watcher_thread = None


def init_integration_watcher(app=None, auto_start: bool = True) -> None:
    """
    Initialisiert den Integration-Watcher.
    
    Args:
        app: FastAPI App
        auto_start: Ob der Watcher automatisch gestartet werden soll
    """
    global _watcher_thread
    
    # Prüfe ob Integrations-Verzeichnis existiert
    integrations_dir = _get_integrations_dir()
    if not integrations_dir.exists():
        _get_hotreload_logger().warning(f"Integrations-Verzeichnis existiert nicht: {integrations_dir}")
        _get_hotreload_logger().warning("Erstelle Verzeichnis...")
        try:
            integrations_dir.mkdir(parents=True, exist_ok=True)
            _get_hotreload_logger().info(f"Integrations-Verzeichnis erstellt: {integrations_dir}")
        except Exception as e:
            _get_hotreload_logger().error(f"Konnte Integrations-Verzeichnis nicht erstellen: {e}")
    
    # Starte Watcher wenn gewünscht
    if auto_start and _watcher_thread is None:
        _watcher_thread = start_integration_watcher(app)
    elif _watcher_thread is not None:
        _get_hotreload_logger().info(f"Integration-Watcher bereits gestartet (Thread: {_watcher_thread.ident})")
    else:
        _get_hotreload_logger().info("Integration-Watcher nicht gestartet (auto_start=False)")


def shutdown_integration_watcher() -> None:
    """
    Fährt den Integration-Watcher herunter.
    """
    global _watcher_thread
    _get_hotreload_logger().info("Integration-Watcher wird heruntergefahren")
    _watcher_thread = None
    # Daemon-Threads werden automatisch beendet