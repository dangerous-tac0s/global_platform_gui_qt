"""
ConfigService - Configuration file management with migration support.

Handles loading, saving, and migrating config.json files while
ensuring backwards compatibility with existing configurations.
"""

import json
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any

from ..models.config import ConfigData, WindowConfig, PluginCache, CONFIG_VERSION


class ConfigService:
    """
    Service for managing application configuration.

    Provides:
    - Loading/saving config.json
    - Automatic migration of old config formats
    - Safe handling of corrupted files
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the config service.

        Args:
            config_path: Path to config.json. Defaults to 'config.json' in current dir.
        """
        self._config_path = config_path or "config.json"
        self._config: Optional[ConfigData] = None

    def get_config_path(self) -> str:
        """Get the path to the configuration file."""
        return self._config_path

    def load(self) -> ConfigData:
        """
        Load configuration from disk.

        If the file doesn't exist, returns default config.
        If the file is corrupted, backs it up and returns default config.
        If the file is old format, migrates it automatically.

        Returns:
            ConfigData instance
        """
        if not os.path.exists(self._config_path):
            self._config = ConfigData()
            return self._config

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                raw_data = json.load(f)

            # Check version and migrate if needed
            version = raw_data.get("_version", 0)
            if version < CONFIG_VERSION:
                raw_data = self._migrate(raw_data, version)
                # Save migrated config
                self._save_raw(raw_data)

            self._config = ConfigData.from_dict(raw_data)
            return self._config

        except json.JSONDecodeError:
            # Corrupted file - back it up and start fresh
            self._backup_corrupted()
            self._config = ConfigData()
            return self._config
        except Exception as e:
            # Other error - try to preserve data by backing up
            self._backup_corrupted()
            self._config = ConfigData()
            return self._config

    def save(self, config: Optional[ConfigData] = None) -> None:
        """
        Save configuration to disk.

        Args:
            config: ConfigData to save. Uses cached config if None.
        """
        if config is not None:
            self._config = config

        if self._config is None:
            self._config = ConfigData()

        self._save_raw(self._config.to_dict())

    def _save_raw(self, data: Dict[str, Any]) -> None:
        """Save raw dictionary to config file."""
        with open(self._config_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    def _backup_corrupted(self) -> None:
        """Backup a corrupted config file."""
        if not os.path.exists(self._config_path):
            return

        timestamp = int(time.time())
        backup_path = f"config-{timestamp}-.broken.json"
        try:
            os.rename(self._config_path, backup_path)
        except Exception:
            pass  # Best effort backup

    def _migrate(self, data: Dict[str, Any], from_version: int) -> Dict[str, Any]:
        """
        Apply migrations sequentially from old version to current.

        Args:
            data: Raw config dictionary
            from_version: Version to migrate from

        Returns:
            Migrated config dictionary
        """
        migrations = {
            0: self._migrate_v0_to_v1,
            # Add future migrations here:
            # 1: self._migrate_v1_to_v2,
        }

        current = dict(data)
        for v in range(from_version, CONFIG_VERSION):
            if v in migrations:
                current = migrations[v](current)

        current["_version"] = CONFIG_VERSION
        return current

    def _migrate_v0_to_v1(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Migrate from unversioned config to v1.

        This handles configs created before versioning was added.
        NEVER removes keys - only adds or transforms.
        """
        result = dict(data)

        # Ensure all expected keys exist with defaults
        if "cache_latest_release" not in result:
            result["cache_latest_release"] = False

        if "known_tags" not in result:
            result["known_tags"] = {}

        if "last_checked" not in result:
            result["last_checked"] = {}

        if "window" not in result:
            result["window"] = {"width": 800, "height": 600}
        else:
            # Ensure window has required fields
            if "width" not in result["window"]:
                result["window"]["width"] = 800
            if "height" not in result["window"]:
                result["window"]["height"] = 600

        return result

    # === Convenience methods ===

    def get(self) -> ConfigData:
        """Get the current config, loading if necessary."""
        if self._config is None:
            return self.load()
        return self._config

    def update_window_size(self, width: int, height: int) -> None:
        """Update window size in config."""
        config = self.get()
        config.window.width = width
        config.window.height = height
        self.save(config)

    def set_known_tag(self, uid: str, uses_default_key: bool) -> None:
        """Set whether a tag uses the default key."""
        config = self.get()
        config.set_tag_key_type(uid, uses_default_key)
        self.save(config)

    def is_known_tag(self, uid: str) -> bool:
        """Check if a tag UID is known."""
        return self.get().is_known_tag(uid)

    def update_plugin_cache(
        self,
        plugin_name: str,
        apps: Dict[str, str],
        release: str,
    ) -> None:
        """
        Update the cache for a plugin.

        Args:
            plugin_name: Name of the plugin
            apps: Dict mapping cap_name to download_url
            release: Release version string
        """
        config = self.get()
        config.set_plugin_cache(
            plugin_name,
            PluginCache(
                apps=apps,
                last_checked=time.time(),
                release=release,
            ),
        )
        self.save(config)

    def get_plugin_cache(self, plugin_name: str) -> Optional[PluginCache]:
        """Get the cached data for a plugin."""
        return self.get().get_plugin_cache(plugin_name)

    def is_plugin_cache_stale(
        self, plugin_name: str, max_age_hours: float = 24.0
    ) -> bool:
        """Check if a plugin's cache is stale."""
        cache = self.get_plugin_cache(plugin_name)
        if cache is None:
            return True
        return cache.is_stale(max_age_hours)


class MockConfigService(ConfigService):
    """
    Mock ConfigService for testing.

    Stores config in memory instead of disk.
    """

    def __init__(self):
        super().__init__("/dev/null")  # Won't actually be used
        self._config = ConfigData()
        self._saved_configs: list = []

    def load(self) -> ConfigData:
        return self._config

    def save(self, config: Optional[ConfigData] = None) -> None:
        if config is not None:
            self._config = config
        self._saved_configs.append(self._config.to_dict())

    def get_saved_configs(self) -> list:
        """Get list of all configs that were saved (for testing)."""
        return self._saved_configs

    def reset(self) -> None:
        """Reset to default config."""
        self._config = ConfigData()
        self._saved_configs.clear()
