"""
Card-related models for representing smartcard state and information.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict


class CardConnectionState(Enum):
    """Represents the connection state of a smartcard."""
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    ERROR = "error"


@dataclass
class CardInfo:
    """Information about a connected smartcard."""
    uid: str
    is_jcop: bool = False
    jcop_version: Optional[tuple] = None  # (major, minor, patch)
    atr: Optional[str] = None

    def __post_init__(self):
        # Normalize UID to uppercase without spaces
        self.uid = self.uid.upper().replace(" ", "")


@dataclass
class CardMemory:
    """Memory information for a smartcard."""
    persistent_free: int = -1
    persistent_total: int = -1
    transient_reset: int = -1
    transient_deselect: int = -1

    @property
    def is_available(self) -> bool:
        """Check if memory information is available."""
        return self.persistent_free != -1

    @property
    def persistent_used(self) -> int:
        """Calculate used persistent storage."""
        if not self.is_available:
            return -1
        return self.persistent_total - self.persistent_free

    @property
    def persistent_percent_free(self) -> float:
        """Calculate percentage of free persistent storage."""
        if not self.is_available or self.persistent_total == 0:
            return 0.0
        return (self.persistent_free / self.persistent_total) * 100

    def can_fit_applet(self, persistent_required: int, transient_required: int = 0) -> bool:
        """Check if an applet with given requirements can fit on the card."""
        if not self.is_available:
            return True  # Can't validate, assume it fits

        if self.persistent_free < persistent_required:
            return False

        if transient_required > 0:
            # Check against available transient memory
            available_transient = max(self.transient_reset, self.transient_deselect)
            if available_transient > 0 and available_transient < transient_required:
                return False

        return True


@dataclass
class CardState:
    """Complete state of a smartcard including connection, info, and installed apps."""
    connection_state: CardConnectionState = CardConnectionState.DISCONNECTED
    info: Optional[CardInfo] = None
    memory: CardMemory = field(default_factory=CardMemory)
    installed_applets: Dict[str, Optional[str]] = field(default_factory=dict)  # AID -> version
    key: Optional[str] = None
    uses_default_key: Optional[bool] = None

    @property
    def is_connected(self) -> bool:
        """Check if card is connected."""
        return self.connection_state in (
            CardConnectionState.CONNECTED,
            CardConnectionState.AUTHENTICATED
        )

    @property
    def is_authenticated(self) -> bool:
        """Check if card is authenticated (key validated)."""
        return self.connection_state == CardConnectionState.AUTHENTICATED

    @property
    def uid(self) -> Optional[str]:
        """Get card UID if available."""
        return self.info.uid if self.info else None

    def has_applet(self, aid: str) -> bool:
        """Check if an applet with given AID is installed."""
        normalized_aid = aid.upper().replace(" ", "")
        return any(
            installed_aid.upper().replace(" ", "") == normalized_aid
            for installed_aid in self.installed_applets.keys()
        )
