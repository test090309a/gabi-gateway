"""Config loader from YAML file."""
import os
from pathlib import Path
from typing import Any

import yaml


class Config:
    _instance = None
    _config: dict = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, path: str = "config.yaml") -> dict:
        """Load config from YAML file."""
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(config_path, "r") as f:
            self._config = yaml.safe_load(f)

        return self._config

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value by dot-notation key (e.g., 'ollama.base_url')."""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    @property
    def data(self) -> dict:
        return self._config


config = Config()
