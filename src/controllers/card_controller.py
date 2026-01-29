"""
CardController - Manages card lifecycle, authentication, and key retrieval.

This controller orchestrates:
- Card detection and connection state management
- CPLC/UID identification flow
- Key retrieval from storage or user prompt
- Authentication state machine

Events Emitted:
- CardPresenceEvent - card inserted/removed
- CardStateChangedEvent - authentication state changes
- KeyPromptEvent - request key from user
- KeyValidatedEvent - key validation result
- ErrorEvent - authentication failures
"""

from typing import Optional, Callable, TYPE_CHECKING
from enum import Enum

from ..models.card import (
    CardIdentifier,
    CardInfo,
    CardState,
    CardConnectionState,
    CardMemory,
)
from ..events.event_bus import (
    EventBus,
    CardPresenceEvent,
    CardStateChangedEvent,
    KeyPromptEvent,
    KeyValidatedEvent,
    ErrorEvent,
    TitleBarUpdateEvent,
    StatusMessageEvent,
)

if TYPE_CHECKING:
    from ..services.interfaces import ISecureStorageService, IConfigService


DEFAULT_KEY = "404142434445464748494A4B4C4D4E4F"


class AuthState(Enum):
    """Internal authentication state machine states."""
    IDLE = "idle"
    DETECTED = "detected"
    IDENTIFYING = "identifying"
    AWAITING_KEY = "awaiting_key"
    AUTHENTICATING = "authenticating"
    AUTHENTICATED = "authenticated"
    ERROR = "error"


class CardController:
    """
    Controller for card lifecycle and authentication management.

    Coordinates between:
    - NFCThread (card detection)
    - StorageService (key persistence)
    - ConfigService (known_tags)
    - UI (via EventBus events)
    """

    def __init__(
        self,
        storage_service: Optional["ISecureStorageService"] = None,
        config_service: Optional["IConfigService"] = None,
        event_bus: Optional[EventBus] = None,
    ):
        """
        Initialize the CardController.

        Args:
            storage_service: Service for encrypted key storage
            config_service: Service for configuration (known_tags)
            event_bus: EventBus instance (uses singleton if not provided)
        """
        self._storage = storage_service
        self._config = config_service
        self._bus = event_bus or EventBus.instance()

        # Current card state
        self._state = CardState()
        self._auth_state = AuthState.IDLE

        # Pending key callback (set when waiting for user input)
        self._key_callback: Optional[Callable[[str], None]] = None

        # Reader info
        self._current_reader: Optional[str] = None

    @property
    def state(self) -> CardState:
        """Get the current card state."""
        return self._state

    @property
    def card_id(self) -> Optional[str]:
        """Get the primary card identifier (CPLC preferred, UID fallback)."""
        return self._state.card_id

    @property
    def identifier(self) -> Optional[CardIdentifier]:
        """Get the full CardIdentifier if available."""
        return self._state.identifier

    @property
    def key(self) -> Optional[str]:
        """Get the current card key."""
        return self._state.key

    @property
    def is_authenticated(self) -> bool:
        """Check if card is authenticated."""
        return self._state.is_authenticated

    def set_reader(self, reader_name: Optional[str]) -> None:
        """Set the current reader name."""
        self._current_reader = reader_name

    # =========================================================================
    # Card Presence Handling
    # =========================================================================

    def on_card_detected(
        self,
        uid: Optional[str] = None,
        is_jcop: bool = False,
        reader_name: Optional[str] = None,
    ) -> None:
        """
        Called when a card is detected by the NFC thread.

        Args:
            uid: Card UID (may be None for contact readers)
            is_jcop: Whether the card is JCOP compatible
            reader_name: Name of the reader that detected the card
        """
        self._current_reader = reader_name or self._current_reader

        # Create initial card info with UID (CPLC will be added later)
        identifier = CardIdentifier(uid=uid) if uid else None
        info = CardInfo(
            identifier=identifier or CardIdentifier(),
            is_jcop=is_jcop,
        ) if is_jcop else None

        self._state = CardState(
            connection_state=CardConnectionState.CONNECTED if is_jcop else CardConnectionState.DISCONNECTED,
            info=info,
        )

        self._auth_state = AuthState.DETECTED if is_jcop else AuthState.IDLE

        # Emit presence event
        self._bus.emit(CardPresenceEvent(
            present=True,
            uid=uid,
            is_jcop_compatible=is_jcop,
            reader_name=reader_name,
        ))

        if is_jcop:
            self._bus.emit(StatusMessageEvent(
                message="Compatible card detected",
                level="info",
            ))

    def on_card_removed(self) -> None:
        """Called when a card is removed."""
        old_state = self._state

        # Reset state
        self._state = CardState()
        self._auth_state = AuthState.IDLE
        self._key_callback = None

        # Emit presence event
        self._bus.emit(CardPresenceEvent(
            present=False,
            uid=old_state.uid,
            reader_name=self._current_reader,
        ))

        # Emit state change
        self._bus.emit(CardStateChangedEvent(state=self._state))

        self._bus.emit(StatusMessageEvent(
            message="Card removed",
            level="info",
        ))

    # =========================================================================
    # Key Management
    # =========================================================================

    def request_key(self, callback: Callable[[str], None]) -> None:
        """
        Request the key for the current card.

        This method determines the key through:
        1. Check secure storage for stored key
        2. Check config for known_tags (default key indicator)
        3. Prompt user for key if not found

        Args:
            callback: Function to call with the key once obtained
        """
        if not self._state.info:
            self._bus.emit(ErrorEvent(
                message="No card detected",
                recoverable=True,
            ))
            return

        self._key_callback = callback
        self._auth_state = AuthState.IDENTIFYING

        identifier = self._state.identifier
        card_id = self.card_id

        # Placeholder for contact cards without UID
        is_contact_placeholder = card_id is None or card_id == "__CONTACT_CARD__"

        key = None

        if not is_contact_placeholder:
            # Try to get key from storage
            key = self._get_key_from_storage(identifier)

            if key is None:
                # Check if known to use default key
                if self._is_known_default_key(card_id):
                    key = DEFAULT_KEY

        if key is not None:
            # Found key, proceed with authentication
            self._on_key_obtained(key)
        else:
            # Need to prompt user
            self._auth_state = AuthState.AWAITING_KEY
            self._prompt_for_key(card_id)

    def _get_key_from_storage(self, identifier: Optional[CardIdentifier]) -> Optional[str]:
        """Try to retrieve key from secure storage."""
        if self._storage is None or identifier is None:
            return None

        # Try CPLC-aware lookup
        if hasattr(self._storage, 'get_key_for_card'):
            return self._storage.get_key_for_card(identifier)

        # Fallback to UID lookup
        if identifier.uid:
            return self._storage.get_key_for_tag(identifier.uid)

        return None

    def _is_known_default_key(self, card_id: Optional[str]) -> bool:
        """Check if card is known to use default key."""
        if self._config is None or card_id is None:
            return False

        config = self._config.load()
        known_tags = config.known_tags if hasattr(config, 'known_tags') else {}
        return known_tags.get(card_id, False) is True

    def _prompt_for_key(self, card_id: Optional[str]) -> None:
        """Emit event to prompt user for key."""
        uid = card_id or "__CONTACT_CARD__"
        self._bus.emit(KeyPromptEvent(
            uid=uid,
            reason="authentication",
        ))

    def set_key(self, key: str) -> None:
        """
        Set the key (called when user provides key via prompt).

        Args:
            key: The key provided by the user
        """
        if self._auth_state != AuthState.AWAITING_KEY:
            return

        self._on_key_obtained(key)

    def _on_key_obtained(self, key: str) -> None:
        """Handle key obtained (from storage or user)."""
        self._state = CardState(
            connection_state=self._state.connection_state,
            info=self._state.info,
            memory=self._state.memory,
            installed_applets=self._state.installed_applets,
            key=key,
            uses_default_key=(key == DEFAULT_KEY),
        )

        self._auth_state = AuthState.AUTHENTICATING

        # Call the callback with the key
        if self._key_callback:
            callback = self._key_callback
            self._key_callback = None
            callback(key)

    def on_key_validated(self, valid: bool, error_message: Optional[str] = None) -> None:
        """
        Called after authentication attempt to report result.

        Args:
            valid: Whether the key was valid
            error_message: Error message if invalid
        """
        if valid:
            self._auth_state = AuthState.AUTHENTICATED
            self._state = CardState(
                connection_state=CardConnectionState.AUTHENTICATED,
                info=self._state.info,
                memory=self._state.memory,
                installed_applets=self._state.installed_applets,
                key=self._state.key,
                uses_default_key=self._state.uses_default_key,
            )

            self._bus.emit(KeyValidatedEvent(
                uid=self.card_id or "",
                valid=True,
                uses_default=self._state.uses_default_key,
            ))

            self._bus.emit(CardStateChangedEvent(state=self._state))
        else:
            self._auth_state = AuthState.ERROR
            self._state = CardState(
                connection_state=CardConnectionState.ERROR,
                info=self._state.info,
                memory=self._state.memory,
                key=None,  # Clear invalid key
                uses_default_key=None,
            )

            self._bus.emit(KeyValidatedEvent(
                uid=self.card_id or "",
                valid=False,
            ))

            self._bus.emit(ErrorEvent(
                message=error_message or "Invalid key",
                recoverable=True,
            ))

            # Clear stored key if it was wrong
            self._clear_stored_key()

            # Re-prompt for key
            self._auth_state = AuthState.AWAITING_KEY
            self._prompt_for_key(self.card_id)

    def _clear_stored_key(self) -> None:
        """Clear the stored key for current card (after failed auth)."""
        if self._storage is None:
            return

        identifier = self._state.identifier
        card_id = self.card_id

        if identifier and hasattr(self._storage, 'set_key_for_card'):
            self._storage.set_key_for_card(identifier, None)
        elif card_id:
            self._storage.set_key_for_tag(card_id, None)

    # =========================================================================
    # CPLC Handling
    # =========================================================================

    def on_cplc_retrieved(self, cplc_hash: str, uid: Optional[str] = None) -> None:
        """
        Called when CPLC data is retrieved for the card.

        This upgrades the card identification from UID-based to CPLC-based.

        Args:
            cplc_hash: The computed CPLC hash (format: "CPLC_...")
            uid: The UID if available (for merging/migration)
        """
        if not self._state.info:
            return

        # Update identifier with CPLC hash
        old_identifier = self._state.identifier
        new_identifier = CardIdentifier(
            cplc_hash=cplc_hash,
            uid=uid or (old_identifier.uid if old_identifier else None),
        )

        # Update card info with new identifier
        new_info = CardInfo(
            identifier=new_identifier,
            is_jcop=self._state.info.is_jcop,
            jcop_version=self._state.info.jcop_version,
            atr=self._state.info.atr,
        )

        self._state = CardState(
            connection_state=self._state.connection_state,
            info=new_info,
            memory=self._state.memory,
            installed_applets=self._state.installed_applets,
            key=self._state.key,
            uses_default_key=self._state.uses_default_key,
        )

        # Migrate storage if needed
        self._migrate_to_cplc(old_identifier, new_identifier)

        # Emit state change
        self._bus.emit(CardStateChangedEvent(state=self._state))

    def _migrate_to_cplc(
        self,
        old_identifier: Optional[CardIdentifier],
        new_identifier: CardIdentifier,
    ) -> None:
        """Migrate storage from UID to CPLC if needed."""
        if self._storage is None:
            return

        # Check if we have a UID entry to migrate
        old_uid = old_identifier.uid if old_identifier else None
        if old_uid and new_identifier.cplc_hash:
            if hasattr(self._storage, 'upgrade_to_cplc'):
                self._storage.upgrade_to_cplc(old_uid, new_identifier.cplc_hash)

    # =========================================================================
    # Memory and Applet State
    # =========================================================================

    def update_memory(self, memory: CardMemory) -> None:
        """Update the card memory information."""
        self._state = CardState(
            connection_state=self._state.connection_state,
            info=self._state.info,
            memory=memory,
            installed_applets=self._state.installed_applets,
            key=self._state.key,
            uses_default_key=self._state.uses_default_key,
        )

    def update_installed_applets(self, applets: dict) -> None:
        """Update the list of installed applets."""
        self._state = CardState(
            connection_state=self._state.connection_state,
            info=self._state.info,
            memory=self._state.memory,
            installed_applets=applets,
            key=self._state.key,
            uses_default_key=self._state.uses_default_key,
        )

    # =========================================================================
    # Key Storage
    # =========================================================================

    def save_key(
        self,
        key: str,
        name: Optional[str] = None,
    ) -> None:
        """
        Save the current key to secure storage.

        Args:
            key: The key to save
            name: Optional friendly name for the card
        """
        if self._storage is None:
            return

        identifier = self._state.identifier
        if identifier:
            if hasattr(self._storage, 'set_key_for_card'):
                self._storage.set_key_for_card(identifier, key, name)
            elif identifier.primary_id:
                self._storage.set_key_for_tag(identifier.primary_id, key, name)

    def get_card_name(self) -> Optional[str]:
        """Get the friendly name for the current card."""
        if self._storage is None:
            return None

        identifier = self._state.identifier
        if identifier and hasattr(self._storage, 'get_name_for_card'):
            return self._storage.get_name_for_card(identifier)
        elif identifier and identifier.primary_id:
            return self._storage.get_tag_name(identifier.primary_id)

        return None

    # =========================================================================
    # Title Bar
    # =========================================================================

    def get_title_string(self) -> str:
        """Generate title bar string for current card state."""
        if not self._state.info:
            return ""

        parts = []

        # Card name or ID
        name = self.get_card_name()
        if name and name != self.card_id:
            parts.append(name)
        elif self.card_id:
            # Shorten CPLC hash for display
            if self.card_id.startswith("CPLC_"):
                parts.append(self.card_id[:12] + "...")
            else:
                parts.append(self.card_id)

        # Key status
        if self._state.uses_default_key:
            parts.append("[Default Key]")
        elif self._state.key:
            parts.append("[Custom Key]")

        return " - ".join(parts) if parts else ""

    def emit_title_update(self) -> None:
        """Emit title bar update event."""
        title = self.get_title_string()
        if title:
            self._bus.emit(TitleBarUpdateEvent(title=title))
