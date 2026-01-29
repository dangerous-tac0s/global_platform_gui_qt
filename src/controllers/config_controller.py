"""
ConfigController - Manages application configuration and settings.

This controller provides a UI-friendly interface to ConfigService:
- Window state persistence
- Card configuration (names, known_tags)
- Plugin release caching

Does not emit events directly - mainly provides methods for other controllers
and UI components to read/write configuration.
"""

from typing import Optional, Dict, Any, TYPE_CHECKING
import time

from ..models.config import ConfigData, WindowConfig, PluginCache
from ..services.config_service import ConfigService

if TYPE_CHECKING:
    from ..models.card import CardIdentifier


DEFAULT_KEY = "404142434445464748494A4B4C4D4E4F"


class ConfigController:
    """
    Controller for application configuration management.

    Wraps ConfigService to provide:
    - Simplified API for common operations
    - Integration with CardIdentifier for CPLC-aware lookups
    - Window state management
    - Plugin cache management
    """

    def __init__(
        self,
        config_service: Optional[ConfigService] = None,
        config_path: Optional[str] = None,
    ):
        """
        Initialize the ConfigController.

        Args:
            config_service: ConfigService instance (creates one if not provided)
            config_path: Path to config file (only used if creating new service)
        """
        self._service = config_service or ConfigService(config_path)
        self._config: Optional[ConfigData] = None

    @property
    def config(self) -> ConfigData:
        """Get the current configuration, loading if necessary."""
        if self._config is None:
            self._config = self._service.load()
        return self._config

    def save(self) -> None:
        """Save the current configuration to disk."""
        if self._config is not None:
            self._service.save(self._config)

    def reload(self) -> ConfigData:
        """Reload configuration from disk."""
        self._config = self._service.load()
        return self._config

    # =========================================================================
    # Window State
    # =========================================================================

    def get_window_size(self) -> tuple:
        """Get saved window size as (width, height) tuple."""
        return (self.config.window.width, self.config.window.height)

    def set_window_size(self, width: int, height: int) -> None:
        """Save window size."""
        self.config.window.width = width
        self.config.window.height = height
        self.save()

    # =========================================================================
    # Known Tags / Cards
    # =========================================================================

    def is_known_tag(self, card_id: str) -> bool:
        """Check if a card identifier is known."""
        return self.config.is_known_tag(card_id)

    def uses_default_key(self, card_id: str) -> Optional[bool]:
        """
        Check if a card uses the default key.

        Returns:
            True if uses default key, False if custom key, None if unknown
        """
        return self.config.uses_default_key(card_id)

    def set_uses_default_key(self, card_id: str, uses_default: bool) -> None:
        """
        Set whether a card uses the default key.

        Args:
            card_id: Card identifier (CPLC hash or UID)
            uses_default: True if using default key
        """
        self.config.set_tag_key_type(card_id, uses_default)
        self.save()

    def update_known_tag(self, card_id: str, key: str) -> None:
        """
        Update known tag entry based on key value.

        Args:
            card_id: Card identifier
            key: The key being used
        """
        uses_default = (key == DEFAULT_KEY)
        self.set_uses_default_key(card_id, uses_default)

    def get_known_tags(self) -> Dict[str, bool]:
        """Get all known tags (card_id -> uses_default_key)."""
        # Return data from known_cards, not legacy known_tags
        result = {}
        for card_id, entry in self.config.known_cards.items():
            result[card_id] = entry.uses_default_key
        return result

    # =========================================================================
    # CPLC-Aware Card Config
    # =========================================================================

    def get_card_config(self, identifier: "CardIdentifier") -> Optional[Dict[str, Any]]:
        """
        Get configuration for a card using CardIdentifier.

        Tries CPLC hash first, then falls back to UID.

        Args:
            identifier: CardIdentifier with cplc_hash and/or uid

        Returns:
            Card config dict or None if not found
        """
        # Try CPLC hash first
        if identifier.cplc_hash:
            entry = self.config.get_card_config(identifier.cplc_hash)
            if entry:
                return entry.to_dict()

        # Fall back to UID
        if identifier.uid:
            entry = self.config.find_card_by_uid(identifier.uid)
            if entry:
                return entry.to_dict()

        return None

    def upgrade_card_to_cplc(self, uid: str, cplc_hash: str) -> bool:
        """
        Migrate a card config from UID-based to CPLC-based.

        Args:
            uid: Original UID
            cplc_hash: New CPLC hash

        Returns:
            True if migration was performed
        """
        result = self.config.upgrade_card_to_cplc(uid, cplc_hash)
        if result:
            self.save()
        return result

    # =========================================================================
    # Plugin Cache
    # =========================================================================

    def get_plugin_cache(self, plugin_name: str) -> Optional[PluginCache]:
        """Get cached data for a plugin."""
        return self.config.get_plugin_cache(plugin_name)

    def is_plugin_cache_stale(
        self,
        plugin_name: str,
        max_age_hours: float = 24.0,
    ) -> bool:
        """
        Check if a plugin's cache is stale.

        Args:
            plugin_name: Name of the plugin
            max_age_hours: Maximum age in hours before considered stale

        Returns:
            True if cache is stale or doesn't exist
        """
        cache = self.get_plugin_cache(plugin_name)
        if cache is None:
            return True
        return cache.is_stale(max_age_hours)

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
        self.config.set_plugin_cache(
            plugin_name,
            PluginCache(
                apps=apps,
                last_checked=time.time(),
                release=release,
            ),
        )
        self.save()

    def get_cached_apps(self, plugin_name: str) -> Dict[str, str]:
        """
        Get cached apps for a plugin.

        Args:
            plugin_name: Name of the plugin

        Returns:
            Dict mapping cap_name to download_url, empty if no cache
        """
        cache = self.get_plugin_cache(plugin_name)
        return cache.apps if cache else {}

    def get_cached_release(self, plugin_name: str) -> Optional[str]:
        """Get cached release version for a plugin."""
        cache = self.get_plugin_cache(plugin_name)
        return cache.release if cache else None

    # =========================================================================
    # Raw Config Access (for compatibility)
    # =========================================================================

    def get_raw_config(self) -> Dict[str, Any]:
        """
        Get raw config dictionary for legacy compatibility.

        Returns:
            Config as dictionary
        """
        return self.config.to_dict()

    def set_raw_value(self, key: str, value: Any) -> None:
        """
        Set a raw config value (for legacy compatibility).

        Args:
            key: Config key
            value: Value to set
        """
        # Handle nested keys like "window.width"
        if "." in key:
            parts = key.split(".")
            obj = self.config
            for part in parts[:-1]:
                obj = getattr(obj, part, None)
                if obj is None:
                    return
            setattr(obj, parts[-1], value)
        else:
            if hasattr(self.config, key):
                setattr(self.config, key, value)
        self.save()

    def get_raw_value(self, key: str, default: Any = None) -> Any:
        """
        Get a raw config value (for legacy compatibility).

        Args:
            key: Config key
            default: Default value if not found

        Returns:
            Config value or default
        """
        raw = self.get_raw_config()
        if "." in key:
            parts = key.split(".")
            obj = raw
            for part in parts:
                if isinstance(obj, dict) and part in obj:
                    obj = obj[part]
                else:
                    return default
            return obj
        return raw.get(key, default)
