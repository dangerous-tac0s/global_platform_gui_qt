"""
Applet-related models for representing JavaCard applets.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Set
from enum import Enum


class InstallStatus(Enum):
    """Status of an installation operation."""
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED_MUTUAL_EXCLUSION = "blocked_mutual_exclusion"
    BLOCKED_INSUFFICIENT_STORAGE = "blocked_insufficient_storage"
    BLOCKED_NO_KEY = "blocked_no_key"


@dataclass
class AppletInfo:
    """Information about an available applet."""
    cap_name: str
    aid: str
    plugin_name: str
    download_url: str
    name: Optional[str] = None  # Human-readable name
    description_md: Optional[str] = None
    storage_persistent: Optional[int] = None  # Bytes
    storage_transient: Optional[int] = None   # Bytes
    mutual_exclusion: Set[str] = field(default_factory=set)  # CAP names that conflict
    unsupported: bool = False
    unsupported_reason: Optional[str] = None

    def __post_init__(self):
        # Normalize AID
        self.aid = self.aid.upper().replace(" ", "")
        # Ensure mutual_exclusion is a set
        if isinstance(self.mutual_exclusion, list):
            self.mutual_exclusion = set(self.mutual_exclusion)


@dataclass
class InstalledApplet:
    """Represents an applet installed on a card."""
    aid: str
    version: Optional[str] = None
    cap_name: Optional[str] = None  # Resolved via plugin AID mapping
    plugin_name: Optional[str] = None

    def __post_init__(self):
        # Normalize AID
        self.aid = self.aid.upper().replace(" ", "")


@dataclass
class InstallResult:
    """Result of an install/uninstall operation."""
    status: InstallStatus
    message: str
    applet: Optional[InstalledApplet] = None
    rollback_performed: bool = False
    stdout: Optional[str] = None
    stderr: Optional[str] = None

    @property
    def success(self) -> bool:
        """Check if operation was successful."""
        return self.status == InstallStatus.SUCCESS

    @property
    def was_blocked(self) -> bool:
        """Check if operation was blocked by a safety check."""
        return self.status in (
            InstallStatus.BLOCKED_MUTUAL_EXCLUSION,
            InstallStatus.BLOCKED_INSUFFICIENT_STORAGE,
            InstallStatus.BLOCKED_NO_KEY,
        )


@dataclass
class StorageRequirement:
    """Storage requirements for an applet."""
    persistent: int  # Bytes
    transient: int   # Bytes

    def fits_in(self, available_persistent: int, available_transient: int) -> bool:
        """Check if these requirements fit in available space."""
        if available_persistent >= 0 and self.persistent > available_persistent:
            return False
        if available_transient >= 0 and self.transient > available_transient:
            return False
        return True
