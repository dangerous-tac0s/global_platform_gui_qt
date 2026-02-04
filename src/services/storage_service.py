"""
StorageService - Secure encrypted storage for card keys and metadata.

This wraps the existing SecureStorage class to provide a clean interface
for dependency injection and testing.

Supports dual-lookup by CardIdentifier (CPLC hash preferred, UID fallback).
"""

import logging
from typing import Optional, Dict, Any, TYPE_CHECKING
import sys
import os

logger = logging.getLogger(__name__)

# Add parent directory to path to import existing secure_storage
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from secure_storage import SecureStorage as LegacySecureStorage
except ImportError:
    LegacySecureStorage = None

if TYPE_CHECKING:
    from ..models.card import CardIdentifier


class StorageError(Exception):
    """Base exception for storage operations."""
    pass


class StorageLoadError(StorageError):
    """Failed to load storage."""
    pass


class StorageDecryptError(StorageError):
    """Failed to decrypt storage."""
    pass


class StorageSaveError(StorageError):
    """Failed to save storage."""
    pass


class StorageService:
    """
    Service for secure storage of card keys and metadata.

    Wraps the existing SecureStorage implementation while providing
    a cleaner interface for the MVC architecture.
    """

    def __init__(self, storage_path: Optional[str] = None):
        """
        Initialize the storage service.

        Args:
            storage_path: Path to encrypted storage file.
                         Defaults to 'data.enc.json'.
        """
        self._storage_path = storage_path or "data.enc.json"
        self._storage: Optional[LegacySecureStorage] = None
        self._data: Optional[Dict[str, Any]] = None

    def is_initialized(self) -> bool:
        """Check if secure storage has been initialized."""
        return os.path.exists(self._storage_path)

    def initialize(self, method: str, key_id: str) -> bool:
        """
        Initialize secure storage with specified encryption method.

        Args:
            method: 'keyring' or 'gpg'
            key_id: Key identifier

        Returns:
            True if initialization successful

        Raises:
            StorageError: If initialization fails
        """
        if LegacySecureStorage is None:
            raise StorageError("SecureStorage module not available")

        try:
            self._storage = LegacySecureStorage(self._storage_path)
            self._storage.initialize(method, key_id)
            self._storage.load()
            self._data = self._storage.get_data()
            return True
        except Exception as e:
            logger.error(f"Failed to initialize storage: {e}")
            raise StorageError(f"Failed to initialize storage: {e}") from e

    def load(self) -> Dict[str, Any]:
        """
        Load and decrypt stored data.

        Returns:
            Decrypted data dictionary

        Raises:
            StorageLoadError: If loading fails
            StorageDecryptError: If decryption fails
        """
        if self._data is not None:
            return self._data

        if LegacySecureStorage is None:
            raise StorageLoadError("SecureStorage module not available")

        try:
            self._storage = LegacySecureStorage(self._storage_path)
            self._storage.load()
            self._data = self._storage.get_data()
            if self._data is None:
                self._data = {"tags": {}}
            return self._data
        except FileNotFoundError as e:
            logger.warning(f"Storage file not found: {e}")
            raise StorageLoadError(f"Storage file not found: {e}") from e
        except RuntimeError as e:
            # RuntimeError from SecureStorage typically indicates decryption issues
            logger.error(f"Failed to decrypt storage: {e}")
            raise StorageDecryptError(f"Failed to decrypt storage: {e}") from e
        except Exception as e:
            logger.error(f"Failed to load storage: {e}")
            raise StorageLoadError(f"Failed to load storage: {e}") from e

    def save(self, data: Optional[Dict[str, Any]] = None) -> None:
        """
        Encrypt and save data.

        Args:
            data: Data to save. Uses cached data if None.

        Raises:
            StorageSaveError: If saving fails
        """
        if data is not None:
            self._data = data

        if self._data is None:
            self._data = {"tags": {}}

        if self._storage is not None:
            try:
                self._storage.set_data(self._data)
                self._storage.save()
            except Exception as e:
                logger.error(f"Failed to save storage: {e}")
                raise StorageSaveError(f"Failed to save storage: {e}") from e
        else:
            raise StorageSaveError("Storage not initialized")

    def get_key_for_tag(self, uid: str) -> Optional[str]:
        """
        Get the stored key for a card UID.

        Args:
            uid: Card UID (normalized to uppercase, no spaces)

        Returns:
            Key as hex string, or None if not stored
        """
        data = self.load()
        uid_normalized = uid.upper().replace(" ", "")

        tags = data.get("tags", {})
        tag_data = tags.get(uid_normalized)

        if tag_data and "key" in tag_data:
            return tag_data["key"]
        return None

    def set_key_for_tag(
        self, uid: str, key: Optional[str], name: Optional[str] = None
    ) -> None:
        """
        Store a key for a card UID.

        Args:
            uid: Card UID
            key: Key as hex string (or None to clear)
            name: Optional friendly name for the card
        """
        data = self.load()
        uid_normalized = uid.upper().replace(" ", "")

        if "tags" not in data:
            data["tags"] = {}

        if uid_normalized not in data["tags"]:
            data["tags"][uid_normalized] = {}

        data["tags"][uid_normalized]["key"] = key

        if name is not None:
            data["tags"][uid_normalized]["name"] = name

        self._data = data
        self.save()

    def get_tag_name(self, uid: str) -> Optional[str]:
        """Get the friendly name for a card UID."""
        data = self.load()
        uid_normalized = uid.upper().replace(" ", "")

        tags = data.get("tags", {})
        tag_data = tags.get(uid_normalized)

        if tag_data and "name" in tag_data:
            return tag_data["name"]
        return None

    def set_tag_name(self, uid: str, name: str) -> None:
        """Set the friendly name for a card UID."""
        data = self.load()
        uid_normalized = uid.upper().replace(" ", "")

        if "tags" not in data:
            data["tags"] = {}

        if uid_normalized not in data["tags"]:
            data["tags"][uid_normalized] = {}

        data["tags"][uid_normalized]["name"] = name
        self._data = data
        self.save()

    def get_all_tags(self) -> Dict[str, Dict[str, Any]]:
        """Get all stored tag data."""
        data = self.load()
        return data.get("tags", {})

    def remove_tag(self, uid: str) -> bool:
        """
        Remove a tag from storage.

        Args:
            uid: Card UID to remove

        Returns:
            True if tag was removed, False if not found
        """
        data = self.load()
        uid_normalized = uid.upper().replace(" ", "")

        if "tags" in data and uid_normalized in data["tags"]:
            del data["tags"][uid_normalized]
            self._data = data
            self.save()
            return True
        return False

    # === CPLC-aware dual-lookup methods ===

    def get_key_for_card(self, identifier: "CardIdentifier") -> Optional[str]:
        """
        Get the stored key for a card using CardIdentifier.

        Tries CPLC hash first, then falls back to UID lookup.

        Args:
            identifier: CardIdentifier with cplc_hash and/or uid

        Returns:
            Key as hex string, or None if not stored
        """
        data = self.load()
        tags = data.get("tags", {})

        # Try CPLC hash first
        if identifier.cplc_hash:
            cplc_normalized = identifier.cplc_hash.upper()
            if cplc_normalized in tags:
                tag_data = tags[cplc_normalized]
                if tag_data and "key" in tag_data:
                    return tag_data["key"]

        # Fall back to UID
        if identifier.uid:
            uid_normalized = identifier.uid.upper().replace(" ", "")
            if uid_normalized in tags:
                tag_data = tags[uid_normalized]
                if tag_data and "key" in tag_data:
                    return tag_data["key"]

        return None

    def get_name_for_card(self, identifier: "CardIdentifier") -> Optional[str]:
        """
        Get the friendly name for a card using CardIdentifier.

        Tries CPLC hash first, then falls back to UID lookup.

        Args:
            identifier: CardIdentifier with cplc_hash and/or uid

        Returns:
            Friendly name string, or None if not stored
        """
        data = self.load()
        tags = data.get("tags", {})

        # Try CPLC hash first
        if identifier.cplc_hash:
            cplc_normalized = identifier.cplc_hash.upper()
            if cplc_normalized in tags:
                tag_data = tags[cplc_normalized]
                if tag_data and "name" in tag_data:
                    return tag_data["name"]

        # Fall back to UID
        if identifier.uid:
            uid_normalized = identifier.uid.upper().replace(" ", "")
            if uid_normalized in tags:
                tag_data = tags[uid_normalized]
                if tag_data and "name" in tag_data:
                    return tag_data["name"]

        return None

    def set_key_for_card(
        self,
        identifier: "CardIdentifier",
        key: Optional[str],
        name: Optional[str] = None,
    ) -> None:
        """
        Store a key for a card using CardIdentifier.

        Uses CPLC hash as primary key if available, otherwise uses UID.

        Args:
            identifier: CardIdentifier with cplc_hash and/or uid
            key: Key as hex string (or None to clear)
            name: Optional friendly name for the card
        """
        data = self.load()

        if "tags" not in data:
            data["tags"] = {}

        # Determine primary key (CPLC preferred)
        if identifier.cplc_hash:
            primary_key = identifier.cplc_hash.upper()
        elif identifier.uid:
            primary_key = identifier.uid.upper().replace(" ", "")
        else:
            return  # No identifier available

        if primary_key not in data["tags"]:
            data["tags"][primary_key] = {}

        data["tags"][primary_key]["key"] = key

        # Store UID as reference if we're using CPLC
        if identifier.cplc_hash and identifier.uid:
            data["tags"][primary_key]["uid"] = identifier.uid.upper().replace(" ", "")

        if name is not None:
            data["tags"][primary_key]["name"] = name

        self._data = data
        self.save()

    def upgrade_to_cplc(self, old_uid: str, cplc_hash: str) -> bool:
        """
        Migrate a UID-based entry to use CPLC as primary key.

        This is called when we first obtain CPLC data for a known card.
        Creates a new entry with CPLC key, preserves all data, and removes
        the old UID-keyed entry.

        Args:
            old_uid: Original UID used as key
            cplc_hash: New CPLC-based identifier (format: "CPLC_...")

        Returns:
            True if upgrade was performed, False if UID entry not found
        """
        data = self.load()
        tags = data.get("tags", {})

        uid_normalized = old_uid.upper().replace(" ", "")
        cplc_normalized = cplc_hash.upper()

        if uid_normalized not in tags:
            return False

        # Get existing entry data
        old_entry = tags[uid_normalized]

        # Create new entry with CPLC key
        new_entry = dict(old_entry)
        new_entry["uid"] = uid_normalized  # Preserve UID as reference
        new_entry["migrated_from_uid"] = True

        # Add new CPLC-keyed entry
        tags[cplc_normalized] = new_entry

        # Remove old UID-keyed entry
        del tags[uid_normalized]

        self._data = data
        self.save()
        return True

    def find_by_uid(self, uid: str) -> Optional[str]:
        """
        Find the primary key (storage key) for a card by its UID.

        Useful when a card is detected by UID but may be stored under CPLC.

        Args:
            uid: Card UID to search for

        Returns:
            The storage key (CPLC hash or UID) if found, None otherwise
        """
        data = self.load()
        tags = data.get("tags", {})
        uid_normalized = uid.upper().replace(" ", "")

        # Direct UID key lookup
        if uid_normalized in tags:
            return uid_normalized

        # Search for UID in entry data (for CPLC-keyed entries)
        for key, entry in tags.items():
            if entry.get("uid") == uid_normalized:
                return key

        return None


class MockStorageService(StorageService):
    """
    Mock StorageService for testing.

    Stores data in memory without encryption.
    """

    def __init__(self):
        super().__init__("/dev/null")
        self._data = {"tags": {}}
        self._initialized = True

    def is_initialized(self) -> bool:
        return self._initialized

    def initialize(self, method: str, key_id: str) -> bool:
        self._initialized = True
        return True

    def load(self) -> Dict[str, Any]:
        return self._data

    def save(self, data: Optional[Dict[str, Any]] = None) -> None:
        if data is not None:
            self._data = data

    def reset(self) -> None:
        """Reset to empty state."""
        self._data = {"tags": {}}
