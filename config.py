# gateway/config.py
"""Configuration management for GABI Gateway."""

import os
import yaml
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class Config:
    """
    Configuration manager for GABI Gateway.
    
    Loads configuration from config.yaml with fallback defaults.
    Supports hot-reload and environment variable overrides.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration manager.
        
        Args:
            config_path: Path to config file (default: config.yaml in current directory)
        """
        self._config_path = config_path or "config.yaml"
        self._data: Dict[str, Any] = {}
        self._load_config()
        
    def _load_config(self) -> None:
        """Load configuration from YAML file."""
        config_file = Path(self._config_path)
        
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    self._data = yaml.safe_load(f) or {}
                logger.info(f"✅ Config loaded from {self._config_path}")
            except Exception as e:
                logger.error(f"❌ Failed to load config: {e}")
                self._data = {}
        else:
            logger.warning(f"⚠️ Config file not found: {self._config_path}")
            self._data = {}
        
        # Apply environment variable overrides
        self._apply_env_overrides()
        
        # Ensure required sections exist
        self._ensure_defaults()
    
    def _apply_env_overrides(self) -> None:
        """Override config values from environment variables."""
        # API Key
        if os.environ.get("GABI_API_KEY"):
            self._data["api_key"] = os.environ["GABI_API_KEY"]
        
        # Ollama settings
        if os.environ.get("OLLAMA_HOST"):
            self._data.setdefault("ollama", {})["host"] = os.environ["OLLAMA_HOST"]
        if os.environ.get("OLLAMA_PORT"):
            self._data.setdefault("ollama", {})["port"] = int(os.environ["OLLAMA_PORT"])
        if os.environ.get("OLLAMA_DEFAULT_MODEL"):
            self._data.setdefault("ollama", {})["default_model"] = os.environ["OLLAMA_DEFAULT_MODEL"]
        
        # Telegram settings
        if os.environ.get("TELEGRAM_BOT_TOKEN"):
            self._data.setdefault("telegram", {})["bot_token"] = os.environ["TELEGRAM_BOT_TOKEN"]
        if os.environ.get("TELEGRAM_CHAT_ID"):
            self._data.setdefault("telegram", {})["chat_id"] = os.environ["TELEGRAM_CHAT_ID"]
        if os.environ.get("TELEGRAM_ENABLED"):
            self._data.setdefault("telegram", {})["enabled"] = os.environ["TELEGRAM_ENABLED"].lower() == "true"
        
        # Gmail settings
        if os.environ.get("GMAIL_ENABLED"):
            self._data.setdefault("gmail", {})["enabled"] = os.environ["GMAIL_ENABLED"].lower() == "true"
        if os.environ.get("GMAIL_CREDENTIALS_FILE"):
            self._data.setdefault("gmail", {})["credentials_file"] = os.environ["GMAIL_CREDENTIALS_FILE"]
        if os.environ.get("GMAIL_TOKEN_FILE"):
            self._data.setdefault("gmail", {})["token_file"] = os.environ["GMAIL_TOKEN_FILE"]
        
        # Calendar settings
        if os.environ.get("CALENDAR_ENABLED"):
            self._data.setdefault("calendar", {})["enabled"] = os.environ["CALENDAR_ENABLED"].lower() == "true"
        if os.environ.get("CALENDAR_CREDENTIALS_FILE"):
            self._data.setdefault("calendar", {})["credentials_file"] = os.environ["CALENDAR_CREDENTIALS_FILE"]
        if os.environ.get("CALENDAR_TOKEN_FILE"):
            self._data.setdefault("calendar", {})["token_file"] = os.environ["CALENDAR_TOKEN_FILE"]
        
        # ComfyUI settings
        if os.environ.get("COMFYUI_HOST"):
            self._data.setdefault("comfyui", {})["host"] = os.environ["COMFYUI_HOST"]
        if os.environ.get("COMFYUI_PORT"):
            self._data.setdefault("comfyui", {})["port"] = int(os.environ["COMFYUI_PORT"])
        
        # Shell settings
        if os.environ.get("SHELL_ALLOWED_COMMANDS"):
            self._data.setdefault("shell", {})["allowed_commands"] = os.environ["SHELL_ALLOWED_COMMANDS"].split(",")
        
        # Logging
        if os.environ.get("LOG_LEVEL"):
            self._data["log_level"] = os.environ["LOG_LEVEL"]
    
    def _ensure_defaults(self) -> None:
        """Ensure all required config sections have defaults."""
        # API settings
        if "api_key" not in self._data:
            self._data["api_key"] = "sysop"  # Default development key
        
        # Ollama settings
        if "ollama" not in self._data:
            self._data["ollama"] = {}
        if "host" not in self._data["ollama"]:
            self._data["ollama"]["host"] = "http://localhost"
        if "port" not in self._data["ollama"]:
            self._data["ollama"]["port"] = 11434
        if "default_model" not in self._data["ollama"]:
            self._data["ollama"]["default_model"] = "llama2:latest"
        if "auto_max_model_size_b" not in self._data["ollama"]:
            self._data["ollama"]["auto_max_model_size_b"] = 12.0
        if "preferred_code_models" not in self._data["ollama"]:
            self._data["ollama"]["preferred_code_models"] = ["codellama:latest", "deepseek-coder:latest"]
        if "preferred_general_models" not in self._data["ollama"]:
            self._data["ollama"]["preferred_general_models"] = ["llama2:latest", "mistral:latest"]
        if "preferred_vision_models" not in self._data["ollama"]:
            self._data["ollama"]["preferred_vision_models"] = ["llava:latest", "bakllava:latest"]
        
        # Telegram settings
        if "telegram" not in self._data:
            self._data["telegram"] = {}
        if "enabled" not in self._data["telegram"]:
            self._data["telegram"]["enabled"] = False
        
        # Gmail settings
        if "gmail" not in self._data:
            self._data["gmail"] = {}
        if "enabled" not in self._data["gmail"]:
            self._data["gmail"]["enabled"] = False
        
        # Calendar settings
        if "calendar" not in self._data:
            self._data["calendar"] = {}
        if "enabled" not in self._data["calendar"]:
            self._data["calendar"]["enabled"] = False
        
        # Shell settings
        if "shell" not in self._data:
            self._data["shell"] = {}
        if "allowed_commands" not in self._data["shell"]:
            self._data["shell"]["allowed_commands"] = [
                "ls", "dir", "pwd", "cd", "echo", "cat", "type",
                "git", "python", "pip", "head", "tail", "wc",
                "systeminfo", "whoami", "netstat", "ipconfig", "ifconfig"
            ]
        
        # ComfyUI settings
        if "comfyui" not in self._data:
            self._data["comfyui"] = {}
        if "host" not in self._data["comfyui"]:
            self._data["comfyui"]["host"] = "127.0.0.1"
        if "port" not in self._data["comfyui"]:
            self._data["comfyui"]["port"] = 8188
        
        # Whisper settings
        if "whisper" not in self._data:
            self._data["whisper"] = {}
        if "host" not in self._data["whisper"]:
            self._data["whisper"]["host"] = "127.0.0.1"
        if "port" not in self._data["whisper"]:
            self._data["whisper"]["port"] = 9090
        
        # Logging
        if "log_level" not in self._data:
            self._data["log_level"] = "INFO"
        
        # Memory settings
        if "memory" not in self._data:
            self._data["memory"] = {}
        if "max_entries" not in self._data["memory"]:
            self._data["memory"]["max_entries"] = 100
        if "max_size" not in self._data["memory"]:
            self._data["memory"]["max_size"] = 10000
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get configuration value by dot-notation key.
        
        Args:
            key: Dot-notation key (e.g., "ollama.default_model")
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        parts = key.split(".")
        value = self._data
        
        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
                if value is None:
                    return default
            else:
                return default
        
        return value if value is not None else default
    
    def set(self, key: str, value: Any) -> None:
        """
        Set configuration value by dot-notation key.
        
        Args:
            key: Dot-notation key (e.g., "ollama.default_model")
            value: Value to set
        """
        parts = key.split(".")
        target = self._data
        
        # Navigate to parent
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            target = target[part]
        
        # Set value
        target[parts[-1]] = value
        
        # Optionally save to file
        self._save_config()
    
    def _save_config(self) -> None:
        """Save current configuration to file."""
        try:
            with open(self._config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self._data, f, default_flow_style=False, allow_unicode=True)
            logger.debug(f"Config saved to {self._config_path}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
    
    def reload(self) -> None:
        """Reload configuration from file."""
        self._load_config()
        logger.info("Config reloaded")
    
    @property
    def data(self) -> Dict[str, Any]:
        """Get raw config data."""
        return self._data.copy()
    
    def get_ollama_url(self) -> str:
        """
        Get full Ollama API URL.
        
        Returns:
            Ollama API URL (e.g., "http://localhost:11434")
        """
        host = self.get("ollama.host", "http://localhost")
        port = self.get("ollama.port", 11434)
        return f"{host}:{port}"
    
    def get_ollama_base_url(self) -> str:
        """
        Get Ollama base URL for API calls.
        
        Returns:
            Ollama base URL (e.g., "http://localhost:11434")
        """
        return self.get_ollama_url()
    
    def get_comfyui_url(self) -> str:
        """
        Get ComfyUI API URL.
        
        Returns:
            ComfyUI API URL (e.g., "http://127.0.0.1:8188")
        """
        host = self.get("comfyui.host", "127.0.0.1")
        port = self.get("comfyui.port", 8188)
        return f"http://{host}:{port}"
    
    def get_whisper_url(self) -> str:
        """
        Get Whisper API URL.
        
        Returns:
            Whisper API URL (e.g., "http://127.0.0.1:9090")
        """
        host = self.get("whisper.host", "127.0.0.1")
        port = self.get("whisper.port", 9090)
        return f"http://{host}:{port}"
    
    def is_telegram_enabled(self) -> bool:
        """
        Check if Telegram is enabled.
        
        Returns:
            True if Telegram is enabled and configured
        """
        if not self.get("telegram.enabled", False):
            return False
        
        bot_token = self.get("telegram.bot_token", "")
        return bool(bot_token and bot_token != "YOUR_TELEGRAM_BOT_TOKEN")
    
    def is_gmail_enabled(self) -> bool:
        """
        Check if Gmail is enabled.
        
        Returns:
            True if Gmail is enabled and configured
        """
        return self.get("gmail.enabled", False)
    
    def is_calendar_enabled(self) -> bool:
        """
        Check if Calendar is enabled.
        
        Returns:
            True if Calendar is enabled and configured
        """
        return self.get("calendar.enabled", False)
    
    def is_shell_allowed(self, command: str) -> bool:
        """
        Check if a shell command is allowed.
        
        Args:
            command: Command to check
            
        Returns:
            True if command is allowed
        """
        allowed = self.get("shell.allowed_commands", [])
        cmd_base = command.split()[0].lower() if command else ""
        return cmd_base in allowed
    
    def get_telegram_targets(self) -> list:
        """
        Get all configured Telegram targets.
        
        Returns:
            List of chat IDs or channel usernames
        """
        targets = []
        
        # Single chat_id
        chat_id = self.get("telegram.chat_id")
        if chat_id:
            targets.append(chat_id)
        
        # Channel ID
        channel_id = self.get("telegram.channel_id")
        if channel_id:
            targets.append(channel_id)
        
        # Multiple chat_ids
        chat_ids = self.get("telegram.chat_ids", [])
        if isinstance(chat_ids, list):
            targets.extend(chat_ids)
        elif isinstance(chat_ids, str) and chat_ids.strip():
            targets.extend([c.strip() for c in chat_ids.split(",") if c.strip()])
        
        return targets


# Global config instance
config = Config()


def get_config() -> Config:
    """
    Get the global config instance.
    
    Returns:
        Global Config instance
    """
    return config


def reload_config() -> None:
    """
    Reload configuration from file.
    """
    config.reload()


# Example config.yaml content:
"""
# GABI Gateway Configuration

# API Key for authentication
api_key: sysop

# Ollama settings
ollama:
  host: http://localhost
  port: 11434
  default_model: llama2:latest
  auto_max_model_size_b: 12.0
  preferred_code_models:
    - codellama:latest
    - deepseek-coder:latest
  preferred_general_models:
    - llama2:latest
    - mistral:latest
  preferred_vision_models:
    - llava:latest
    - bakllava:latest

# Telegram Bot
telegram:
  enabled: false
  bot_token: YOUR_TELEGRAM_BOT_TOKEN
  chat_id: null
  channel_id: null
  chat_ids: []

# Gmail
gmail:
  enabled: false
  credentials_file: credentials.json
  token_file: token.json

# Google Calendar
calendar:
  enabled: false
  credentials_file: calendar_credentials.json
  token_file: calendar_token.json

# Shell Execution
shell:
  allowed_commands:
    - ls
    - dir
    - pwd
    - cd
    - echo
    - cat
    - type
    - git
    - python
    - pip
    - head
    - tail
    - wc
    - systeminfo
    - whoami
    - netstat
    - ipconfig
    - ifconfig

# ComfyUI
comfyui:
  host: 127.0.0.1
  port: 8188

# Whisper
whisper:
  host: 127.0.0.1
  port: 9090

# Memory
memory:
  max_entries: 100
  max_size: 10000

# Logging
log_level: INFO
"""