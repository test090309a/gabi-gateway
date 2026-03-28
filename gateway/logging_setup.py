# gateway/logging_setup.py
"""Logging-Konfiguration für GABI Gateway mit Farben."""

import os
import logging
import logging.config
import yaml
from pathlib import Path
from typing import Optional

# Versuche colorlog zu importieren
try:
    import colorlog
    COLORLOG_AVAILABLE = True
except ImportError:
    COLORLOG_AVAILABLE = False
    print("⚠️ colorlog nicht installiert. Installiere mit: pip install colorlog")

def setup_logging(config_path: Optional[str] = None) -> None:
    """
    Konfiguriert das Logging mit Farben.
    
    Args:
        config_path: Pfad zur logging_config.yaml (optional)
    """
    # Erstelle logs Verzeichnis falls nicht vorhanden
    Path("logs").mkdir(exist_ok=True)
    
    if config_path is None:
        config_path = Path(__file__).parent.parent / "logging_config.yaml"
    else:
        config_path = Path(config_path)
    
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                
                # Wenn colorlog nicht verfügbar ist, ersetze colored durch default
                if not COLORLOG_AVAILABLE:
                    for handler in config.get('handlers', {}).values():
                        if handler.get('formatter') == 'colored':
                            handler['formatter'] = 'default'
                    print("⚠️ colorlog nicht verfügbar, verwende Standard-Formatierung")
                
                logging.config.dictConfig(config)
                print("✅ Logging mit Farben konfiguriert")
        except Exception as e:
            print(f"⚠️ Fehler beim Laden der Logging-Konfiguration: {e}")
            _setup_basic_logging()
    else:
        print(f"⚠️ {config_path} nicht gefunden, verwende Standard-Logging")
        _setup_basic_logging()

def _setup_basic_logging() -> None:
    """Fallback: Einfache Logging-Konfiguration."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Setze Logger-Level gemäß config.yaml
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Deaktiviere laute Logger
    for name in ["httpx", "chromadb", "urllib3", "selenium", "webdriver_manager"]:
        logging.getLogger(name).setLevel(logging.WARNING)

def get_logger(name: str) -> logging.Logger:
    """
    Gibt einen konfigurierten Logger zurück.
    
    Args:
        name: Logger-Name
        
    Returns:
        Logger-Instanz
    """
    return logging.getLogger(name)

# Initialisiere Logging beim Import
setup_logging()