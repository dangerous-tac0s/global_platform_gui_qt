"""
Configuration models for application settings.

These models handle the config.json structure with migration support.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Union
import time


# Current config version - increment when schema changes
CONFIG_VERSION = 2


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
class CardConfigEntry:
    """
    Configuration entry for a known card.

    Supports both CPLC-based and UID-based identification, with the primary_id
    being the key used in the known_cards dictionary.
    """
    uses_default_key: bool
    uid: Optional[str] = None        # Original UID (for reference/fallback)
    cplc_hash: Optional[str] = None  # CPLC-based ID if known (format: "CPLC_...")
    migrated_from_uid: bool = False  # True if this entry was migrated from v1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uses_default_key": self.uses_default_key,
            "uid": self.uid,
            "cplc_hash": self.cplc_hash,
            "migrated_from_uid": self.migrated_from_uid,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CardConfigEntry":
        return cls(
            uses_default_key=data.get("uses_default_key", True),
            uid=data.get("uid"),
            cplc_hash=data.get("cplc_hash"),
            migrated_from_uid=data.get("migrated_from_uid", False),
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

    # v2: Known cards mapped by primary identifier (CPLC hash or UID)
    # Key is the primary_id, value contains full card config
    known_cards: Dict[str, CardConfigEntry] = field(default_factory=dict)

    # v1 (deprecated): Known card UIDs mapped to whether they use default key
    # Kept for backwards compatibility during migration
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
            "known_cards": {
                card_id: entry.to_dict()
                for card_id, entry in self.known_cards.items()
            },
            "known_tags": self.known_tags,  # Keep for rollback safety
            "window": self.window.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConfigData":
        """Create from dictionary, handling missing fields gracefully."""
        last_checked = {}
        for name, cache_data in data.get("last_checked", {}).items():
            last_checked[name] = PluginCache.from_dict(cache_data)

        known_cards = {}
        for card_id, entry_data in data.get("known_cards", {}).items():
            known_cards[card_id] = CardConfigEntry.from_dict(entry_data)

        return cls(
            _version=data.get("_version", 0),
            cache_latest_release=data.get("cache_latest_release", False),
            last_checked=last_checked,
            known_cards=known_cards,
            known_tags=data.get("known_tags", {}),
            window=WindowConfig.from_dict(data.get("window", {})),
        )

    def get_plugin_cache(self, plugin_name: str) -> Optional[PluginCache]:
        """Get cached data for a plugin."""
        return self.last_checked.get(plugin_name)

    def set_plugin_cache(self, plugin_name: str, cache: PluginCache) -> None:
        """Set cached data for a plugin."""
        self.last_checked[plugin_name] = cache

    def is_known_card(self, card_id: str) -> bool:
        """Check if a card identifier (CPLC hash or UID) is known."""
        normalized = card_id.upper().replace(" ", "")
        return normalized in self.known_cards

    def is_known_tag(self, uid: str) -> bool:
        """Check if a card UID is known (checks both known_cards and legacy known_tags)."""
        normalized = uid.upper().replace(" ", "")
        # Check new known_cards first
        if normalized in self.known_cards:
            return True
        # Also check by UID field in known_cards entries
        for entry in self.known_cards.values():
            if entry.uid and entry.uid.upper().replace(" ", "") == normalized:
                return True
        # Fall back to legacy known_tags
        return normalized in self.known_tags

    def get_card_config(self, card_id: str) -> Optional[CardConfigEntry]:
        """Get card configuration by primary identifier (CPLC hash or UID)."""
        normalized = card_id.upper().replace(" ", "")
        return self.known_cards.get(normalized)

    def find_card_by_uid(self, uid: str) -> Optional[CardConfigEntry]:
        """Find card configuration by UID (searches known_cards entries)."""
        normalized = uid.upper().replace(" ", "")
        # Direct lookup first
        if normalized in self.known_cards:
            return self.known_cards[normalized]
        # Search by uid field
        for entry in self.known_cards.values():
            if entry.uid and entry.uid.upper().replace(" ", "") == normalized:
                return entry
        return None

    def uses_default_key(self, card_id: str) -> Optional[bool]:
        """Get whether a known card uses the default key."""
        normalized = card_id.upper().replace(" ", "")
        # Check known_cards first
        if normalized in self.known_cards:
            return self.known_cards[normalized].uses_default_key
        # Search by UID field
        for entry in self.known_cards.values():
            if entry.uid and entry.uid.upper().replace(" ", "") == normalized:
                return entry.uses_default_key
        # Fall back to legacy known_tags
        return self.known_tags.get(normalized)

    def set_card_config(
        self,
        card_id: str,
        uses_default: bool,
        uid: Optional[str] = None,
        cplc_hash: Optional[str] = None,
    ) -> None:
        """Set card configuration by primary identifier."""
        normalized = card_id.upper().replace(" ", "")
        self.known_cards[normalized] = CardConfigEntry(
            uses_default_key=uses_default,
            uid=uid.upper().replace(" ", "") if uid else None,
            cplc_hash=cplc_hash.upper() if cplc_hash else None,
            migrated_from_uid=False,
        )

    def set_tag_key_type(self, uid: str, uses_default: bool) -> None:
        """Set whether a tag uses the default key (legacy method, uses known_cards)."""
        normalized = uid.upper().replace(" ", "")
        # Check if already exists in known_cards
        existing = self.find_card_by_uid(normalized)
        if existing:
            # Update existing entry
            for key, entry in self.known_cards.items():
                if entry.uid and entry.uid.upper().replace(" ", "") == normalized:
                    entry.uses_default_key = uses_default
                    return
                if key == normalized:
                    entry.uses_default_key = uses_default
                    return
        # Create new entry with UID as primary key
        self.known_cards[normalized] = CardConfigEntry(
            uses_default_key=uses_default,
            uid=normalized,
            cplc_hash=None,
            migrated_from_uid=False,
        )

    def upgrade_card_to_cplc(self, old_uid: str, cplc_hash: str) -> bool:
        """
        Upgrade a UID-based card entry to use CPLC as primary identifier.

        Returns True if upgrade was performed, False if card not found.
        """
        normalized_uid = old_uid.upper().replace(" ", "")
        normalized_cplc = cplc_hash.upper()

        # Find existing entry by UID
        existing_entry: Optional[CardConfigEntry] = None
        existing_key: Optional[str] = None

        if normalized_uid in self.known_cards:
            existing_entry = self.known_cards[normalized_uid]
            existing_key = normalized_uid
        else:
            for key, entry in self.known_cards.items():
                if entry.uid and entry.uid.upper().replace(" ", "") == normalized_uid:
                    existing_entry = entry
                    existing_key = key
                    break

        if not existing_entry:
            return False

        # Create new entry with CPLC as primary key
        new_entry = CardConfigEntry(
            uses_default_key=existing_entry.uses_default_key,
            uid=normalized_uid,
            cplc_hash=normalized_cplc,
            migrated_from_uid=existing_entry.migrated_from_uid,
        )

        # Add with CPLC as key, remove old UID key if different
        self.known_cards[normalized_cplc] = new_entry
        if existing_key and existing_key != normalized_cplc:
            del self.known_cards[existing_key]

        return True


# Default configuration for new installations
DEFAULT_CONFIG = ConfigData()
