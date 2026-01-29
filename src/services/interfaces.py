"""
Service interfaces (Protocols) for dependency injection and testing.

These protocols define the contracts that services must implement,
enabling easy mocking in tests and loose coupling between components.
"""

from typing import Protocol, Optional, Dict, List, Tuple, Any
from ..models.config import ConfigData


class IGPService(Protocol):
    """Interface for GlobalPlatformPro operations."""

    def list_applets(self, reader: str, key: str) -> Dict[str, Optional[str]]:
        """
        List installed applets on a card.

        Args:
            reader: Reader name
            key: Card master key (hex string)

        Returns:
            Dict mapping AID to version (or None if version unknown)
        """
        ...

    def install_applet(
        self,
        reader: str,
        key: str,
        cap_path: str,
        params: Optional[str] = None,
        create_aid: Optional[str] = None,
    ) -> "GPResult":
        """
        Install an applet on the card.

        Args:
            reader: Reader name
            key: Card master key
            cap_path: Path to CAP file
            params: Optional install parameters (hex string)
            create_aid: Optional AID to create

        Returns:
            GPResult with success status and output
        """
        ...

    def uninstall_applet(
        self,
        reader: str,
        key: str,
        target: str,
        force: bool = False,
    ) -> "GPResult":
        """
        Uninstall an applet from the card.

        Args:
            reader: Reader name
            key: Card master key
            target: AID or CAP path to uninstall
            force: Force uninstall even if dependencies exist

        Returns:
            GPResult with success status and output
        """
        ...

    def change_key(
        self,
        reader: str,
        old_key: str,
        new_key: str,
    ) -> "GPResult":
        """
        Change the card master key.

        Args:
            reader: Reader name
            old_key: Current master key
            new_key: New master key

        Returns:
            GPResult with success status
        """
        ...


class ICardService(Protocol):
    """Interface for direct smartcard communication."""

    def get_available_readers(self) -> List[str]:
        """Get list of available reader names."""
        ...

    def connect(self, reader_name: str) -> bool:
        """
        Connect to a card in the specified reader.

        Returns:
            True if connection successful
        """
        ...

    def disconnect(self) -> None:
        """Disconnect from the current card."""
        ...

    def get_card_uid(self) -> Optional[str]:
        """
        Get the UID of the connected card.

        Returns:
            UID as hex string, or None if not available
        """
        ...

    def is_card_present(self) -> bool:
        """Check if a card is present in the current reader."""
        ...

    def is_jcop_compatible(self) -> bool:
        """Check if the connected card is JCOP compatible."""
        ...

    def transmit_apdu(self, apdu: List[int]) -> Tuple[List[int], int, int]:
        """
        Transmit an APDU command to the card.

        Args:
            apdu: APDU bytes as list of integers

        Returns:
            Tuple of (response_data, sw1, sw2)
        """
        ...


class IConfigService(Protocol):
    """Interface for configuration persistence."""

    def load(self) -> ConfigData:
        """Load configuration from disk."""
        ...

    def save(self, config: ConfigData) -> None:
        """Save configuration to disk."""
        ...

    def get_config_path(self) -> str:
        """Get the path to the configuration file."""
        ...


class ISecureStorageService(Protocol):
    """Interface for secure (encrypted) key storage."""

    def is_initialized(self) -> bool:
        """Check if secure storage has been initialized."""
        ...

    def initialize(self, method: str, key_id: str) -> bool:
        """
        Initialize secure storage with specified encryption method.

        Args:
            method: 'keyring' or 'gpg'
            key_id: Key identifier (service name for keyring, GPG key ID for gpg)

        Returns:
            True if initialization successful
        """
        ...

    def load(self) -> Dict[str, Any]:
        """Load and decrypt stored data."""
        ...

    def save(self, data: Dict[str, Any]) -> None:
        """Encrypt and save data."""
        ...

    def get_key_for_tag(self, uid: str) -> Optional[str]:
        """
        Get the stored key for a card UID.

        Returns:
            Key as hex string, or None if not stored
        """
        ...

    def set_key_for_tag(self, uid: str, key: str, name: Optional[str] = None) -> None:
        """
        Store a key for a card UID.

        Args:
            uid: Card UID
            key: Key as hex string
            name: Optional friendly name for the card
        """
        ...

    def get_tag_name(self, uid: str) -> Optional[str]:
        """Get the friendly name for a card UID."""
        ...

    def set_tag_name(self, uid: str, name: str) -> None:
        """Set the friendly name for a card UID."""
        ...
