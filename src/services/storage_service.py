"""
StorageService - Secure encrypted storage for card keys and metadata.

This wraps the existing SecureStorage class to provide a clean interface
for dependency injection and testing.
"""

from typing import Optional, Dict, Any
import sys
import os

# Add parent directory to path to import existing secure_storage
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

try:
    from secure_storage import SecureStorage as LegacySecureStorage
except ImportError:
    LegacySecureStorage = None


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
        """
        if LegacySecureStorage is None:
            return False

        try:
            self._storage = LegacySecureStorage(self._storage_path)
            self._storage.initialize(method, key_id)
            self._data = self._storage.load()
            return True
        except Exception:
            return False

    def load(self) -> Dict[str, Any]:
        """
        Load and decrypt stored data.

        Returns:
            Decrypted data dictionary
        """
        if self._data is not None:
            return self._data

        if LegacySecureStorage is None:
            return {"tags": {}}

        try:
            self._storage = LegacySecureStorage(self._storage_path)
            self._data = self._storage.load()
            return self._data
        except Exception:
            return {"tags": {}}

    def save(self, data: Optional[Dict[str, Any]] = None) -> None:
        """
        Encrypt and save data.

        Args:
            data: Data to save. Uses cached data if None.
        """
        if data is not None:
            self._data = data

        if self._data is None:
            self._data = {"tags": {}}

        if self._storage is not None:
            try:
                self._storage.save(self._data)
            except Exception:
                pass

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
