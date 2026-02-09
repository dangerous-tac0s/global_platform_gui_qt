"""
Card-related models for representing smartcard state and information.
"""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Union


class CardConnectionState(Enum):
    """Represents the connection state of a smartcard."""
    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    AUTHENTICATED = "authenticated"
    ERROR = "error"


class CardType(Enum):
    """Identifies the card platform for service routing."""
    STANDARD_GP = "standard_gp"    # Normal GlobalPlatform card (uses gp.jar)
    FIDESMO = "fidesmo"            # Fidesmo device (uses fdsm.jar)
    UNKNOWN = "unknown"            # Not yet determined


# Fidesmo detection constants
FIDESMO_PERSISTENT_TOTAL = 84336  # VivoKey Apex persistent_total from JavaCard memory applet
FIDESMO_KEY_SENTINEL = "FIDESMO"
FIDESMO_DETECTION_AIDS = [
    "A000000617020002000001",    # Fidesmo App AID
    "A000000617020002000002",    # Fidesmo Batch AID
    "A00000061702000900010101",  # Fidesmo Platform AID
]


@dataclass
class CardIdentifier:
    """
    Unique card identifier supporting both CPLC-based and UID-based identification.

    CPLC (Card Production Life Cycle) data provides a universal identifier that works
    across both contact and contactless interfaces. UID is used as a fallback for
    contactless-only scenarios or when CPLC is unavailable.

    Primary: CPLC hash (format: "CPLC_" + 16 hex chars)
    Fallback: UID (typically 8-14 hex chars)
    """
    cplc_hash: Optional[str] = None
    uid: Optional[str] = None

    def __post_init__(self):
        if self.cplc_hash:
            self.cplc_hash = self.cplc_hash.upper()
        if self.uid:
            self.uid = self.uid.upper().replace(" ", "")

    @property
    def primary_id(self) -> str:
        """Get the primary identifier (CPLC hash if available, else UID)."""
        return self.cplc_hash or self.uid or ""

    @property
    def is_cplc_based(self) -> bool:
        """Check if using CPLC-based identification."""
        return self.cplc_hash is not None

    def matches(self, other: "CardIdentifier") -> bool:
        """
        Check if two identifiers refer to the same card.

        CPLC comparison takes precedence when both have CPLC hashes.
        Falls back to UID comparison when CPLC is not available.
        """
        if self.cplc_hash and other.cplc_hash:
            return self.cplc_hash == other.cplc_hash
        if self.uid and other.uid:
            return self.uid == other.uid
        return False

    @staticmethod
    def compute_cplc_hash(raw_cplc_hex: str) -> str:
        """
        Compute the CPLC-based identifier from raw CPLC hex data.

        Returns format: "CPLC_" + first 16 hex chars of SHA-256 hash.
        """
        h = hashlib.sha256(raw_cplc_hex.upper().encode()).hexdigest()
        return f"CPLC_{h[:16].upper()}"


@dataclass
class CardInfo:
    """Information about a connected smartcard."""
    identifier: Union[CardIdentifier, str]
    is_jcop: bool = False
    jcop_version: Optional[tuple] = None  # (major, minor, patch)
    atr: Optional[str] = None
    card_type: CardType = CardType.UNKNOWN

    def __post_init__(self):
        # Handle legacy construction with just a UID string
        if isinstance(self.identifier, str):
            self.identifier = CardIdentifier(uid=self.identifier)

    @property
    def uid(self) -> str:
        """Legacy property for backwards compatibility. Returns UID if available."""
        return self.identifier.uid or self.identifier.primary_id

    @property
    def card_id(self) -> str:
        """Get the primary card identifier (CPLC preferred, UID fallback)."""
        return self.identifier.primary_id


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
    card_type: CardType = CardType.UNKNOWN

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
        """Get card UID if available (legacy property)."""
        return self.info.uid if self.info else None

    @property
    def card_id(self) -> Optional[str]:
        """Get the primary card identifier (CPLC preferred, UID fallback)."""
        return self.info.card_id if self.info else None

    @property
    def identifier(self) -> Optional[CardIdentifier]:
        """Get the full CardIdentifier if available."""
        return self.info.identifier if self.info else None

    def has_applet(self, aid: str) -> bool:
        """Check if an applet with given AID is installed."""
        normalized_aid = aid.upper().replace(" ", "")
        return any(
            installed_aid.upper().replace(" ", "") == normalized_aid
            for installed_aid in self.installed_applets.keys()
        )
