"""Configuration loader with atomic save and validation."""
import json
import logging
from pathlib import Path
from typing import Optional
import asyncio
from datetime import datetime

from .models import BotConfig

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Handles loading, validating, and saving configuration."""

    def __init__(self, config_path: str = "config.json"):
        self.config_path = Path(config_path)
        self._config: Optional[BotConfig] = None
        self._last_modified: Optional[float] = None
        self._watch_task: Optional[asyncio.Task] = None

    def load(self) -> BotConfig:
        """Load configuration from file."""
        if not self.config_path.exists():
            logger.warning(f"Config file {self.config_path} not found, using defaults")
            self._config = BotConfig()
            self.save(self._config)
            return self._config

        try:
            with open(self.config_path, "r") as f:
                data = json.load(f)
            self._config = BotConfig(**data)
            self._last_modified = self.config_path.stat().st_mtime
            logger.info(f"Loaded configuration from {self.config_path}")
            return self._config
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise ValueError(f"Invalid configuration: {e}")

    def save(self, config: BotConfig) -> None:
        """Save configuration to file atomically."""
        try:
            # Write to temporary file first
            temp_path = self.config_path.with_suffix(".tmp")
            with open(temp_path, "w") as f:
                json.dump(config.model_dump(), f, indent=2)

            # Atomic rename
            temp_path.replace(self.config_path)
            self._config = config
            self._last_modified = self.config_path.stat().st_mtime
            logger.info(f"Saved configuration to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            raise

    def get_config(self) -> BotConfig:
        """Get current configuration."""
        if self._config is None:
            return self.load()
        return self._config

    def update_config(self, **kwargs) -> BotConfig:
        """Update specific config fields and save."""
        current = self.get_config()
        updated_data = current.model_dump()
        updated_data.update(kwargs)
        new_config = BotConfig(**updated_data)
        self.save(new_config)
        return new_config

    def check_for_updates(self) -> bool:
        """Check if config file has been modified externally."""
        if not self.config_path.exists():
            return False

        current_mtime = self.config_path.stat().st_mtime
        if self._last_modified and current_mtime > self._last_modified:
            logger.info("Config file modified externally, reloading")
            self.load()
            return True
        return False

    async def watch_for_changes(self, callback=None):
        """Watch for config file changes (optional live reload)."""
        while True:
            try:
                await asyncio.sleep(5)
                if self.check_for_updates():
                    if callback:
                        await callback(self._config)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error watching config: {e}")

    def start_watching(self, callback=None):
        """Start watching config file for changes."""
        if self._watch_task is None or self._watch_task.done():
            self._watch_task = asyncio.create_task(self.watch_for_changes(callback))

    def stop_watching(self):
        """Stop watching config file."""
        if self._watch_task and not self._watch_task.done():
            self._watch_task.cancel()


# Global instance
_config_loader: Optional[ConfigLoader] = None


def get_config_loader(config_path: str = "config.json") -> ConfigLoader:
    """Get or create global config loader instance."""
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader(config_path)
    return _config_loader
