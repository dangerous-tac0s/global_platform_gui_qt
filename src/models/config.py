"""
Configuration models for application settings.

These models handle the config.json structure with migration support.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import time


# Current config version - increment when schema changes
CONFIG_VERSION = 1


@dataclass
class WindowConfig:
    """Window size and position configuration."""
    width: int = 800
    height: int = 600

    def to_dict(self) -> Dict[str, int]:
        return {"width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WindowConfig":
        return cls(
            width=data.get("width", 800),
            height=data.get("height", 600),
        )


@dataclass
class PluginCache:
    """Cached information about a plugin's available apps."""
    apps: Dict[str, str] = field(default_factory=dict)  # cap_name -> download_url
    last_checked: float = 0.0  # Unix timestamp
    release: str = ""

    def is_stale(self, max_age_hours: float = 24.0) -> bool:
        """Check if the cache is older than max_age_hours."""
        if self.last_checked == 0:
            return True
        age_seconds = time.time() - self.last_checked
        return age_seconds > (max_age_hours * 3600)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "apps": self.apps,
            "last": self.last_checked,
            "release": self.release,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PluginCache":
        return cls(
            apps=data.get("apps", {}),
            last_checked=data.get("last", 0.0),
            release=data.get("release", ""),
        )


@dataclass
class ConfigData:
    """
    Main configuration data structure.

    This represents the config.json file structure.
    Migration support: add new fields with defaults, never remove fields.
    """
    # Version for migration tracking
    _version: int = CONFIG_VERSION

    # Whether to cache the latest release info
    cache_latest_release: bool = False

    # Per-plugin cache of available apps
    last_checked: Dict[str, PluginCache] = field(default_factory=dict)

    # Known card UIDs mapped to whether they use default key
    # True = uses default key, False = uses custom key
    known_tags: Dict[str, bool] = field(default_factory=dict)

    # Window configuration
    window: WindowConfig = field(default_factory=WindowConfig)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "_version": self._version,
            "cache_latest_release": self.cache_latest_release,
            "last_checked": {
                name: cache.to_dict()
                for name, cache in self.last_checked.items()
            },
            "known_tags": self.known_tags,
            "window": self.window.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConfigData":
        """Create from dictionary, handling missing fields gracefully."""
        last_checked = {}
        for name, cache_data in data.get("last_checked", {}).items():
            last_checked[name] = PluginCache.from_dict(cache_data)

        return cls(
            _version=data.get("_version", 0),
            cache_latest_release=data.get("cache_latest_release", False),
            last_checked=last_checked,
            known_tags=data.get("known_tags", {}),
            window=WindowConfig.from_dict(data.get("window", {})),
        )

    def get_plugin_cache(self, plugin_name: str) -> Optional[PluginCache]:
        """Get cached data for a plugin."""
        return self.last_checked.get(plugin_name)

    def set_plugin_cache(self, plugin_name: str, cache: PluginCache) -> None:
        """Set cached data for a plugin."""
        self.last_checked[plugin_name] = cache

    def is_known_tag(self, uid: str) -> bool:
        """Check if a card UID is known."""
        normalized = uid.upper().replace(" ", "")
        return normalized in self.known_tags

    def uses_default_key(self, uid: str) -> Optional[bool]:
        """Get whether a known tag uses the default key."""
        normalized = uid.upper().replace(" ", "")
        return self.known_tags.get(normalized)

    def set_tag_key_type(self, uid: str, uses_default: bool) -> None:
        """Set whether a tag uses the default key."""
        normalized = uid.upper().replace(" ", "")
        self.known_tags[normalized] = uses_default


# Default configuration for new installations
DEFAULT_CONFIG = ConfigData()
