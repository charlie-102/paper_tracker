"""Configuration loader for Paper Tracker."""

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# Load .env file if exists
try:
    from dotenv import load_dotenv
    # Look for .env in project root (1 level up from package)
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass  # python-dotenv not installed, skip


class Config:
    """Configuration manager."""

    _instance: Optional["Config"] = None
    _config: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"

        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r") as f:
            self._config = yaml.safe_load(f)

        # Override with environment variables
        self._apply_env_overrides()

        return self._config

    def _apply_env_overrides(self):
        """Apply environment variable overrides."""
        # GitHub token
        if os.environ.get("GITHUB_TOKEN"):
            self._config.setdefault("github", {})["token"] = os.environ["GITHUB_TOKEN"]

        # Min stars override
        if os.environ.get("TRACKER_MIN_STARS"):
            self._config["search"]["min_stars"] = int(os.environ["TRACKER_MIN_STARS"])

        # Year filter override
        if os.environ.get("TRACKER_YEAR"):
            self._config["search"]["year_filter"] = os.environ["TRACKER_YEAR"]

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value by dot-separated key."""
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
    def search(self) -> Dict[str, Any]:
        return self._config.get("search", {})

    @property
    def queries(self) -> list:
        return self._config.get("queries", [])

    @property
    def relevance(self) -> Dict[str, Any]:
        return self._config.get("relevance", {})

    @property
    def weight_detection(self) -> Dict[str, Any]:
        return self._config.get("weight_detection", {})

    @property
    def conferences(self) -> Dict[str, Any]:
        return self._config.get("conferences", {})

    @property
    def output(self) -> Dict[str, Any]:
        return self._config.get("output", {})


# Global config instance
config = Config()
