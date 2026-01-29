"""
EventBus - Central event dispatcher for decoupled communication.

This replaces direct signal connections with a typed event system,
addressing Issue #11 (Signal Slop).
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Any, Callable
from enum import Enum

from PyQt5.QtCore import QObject, pyqtSignal

from ..models.card import CardState, CardInfo, CardMemory


# ============================================================================
# Event Data Classes
# ============================================================================


@dataclass
class CardEvent:
    """Base class for card-related events."""
    pass


@dataclass
class ReadersChangedEvent(CardEvent):
    """Emitted when the list of available readers changes."""
    readers: List[str]


@dataclass
class CardPresenceEvent(CardEvent):
    """Emitted when a card is inserted or removed."""
    present: bool
    uid: Optional[str] = None
    is_jcop_compatible: bool = False
    reader_name: Optional[str] = None


@dataclass
class CardStateChangedEvent(CardEvent):
    """Emitted when card state changes (memory, installed apps, etc.)."""
    state: CardState


@dataclass
class CardMemoryUpdatedEvent(CardEvent):
    """Emitted when card memory information is updated."""
    memory: CardMemory


@dataclass
class InstalledAppsUpdatedEvent(CardEvent):
    """Emitted when the list of installed apps changes."""
    apps: Dict[str, Optional[str]]  # AID -> version


@dataclass
class OperationResultEvent(CardEvent):
    """Emitted when an install/uninstall operation completes."""
    success: bool
    message: str
    operation_type: str  # 'install', 'uninstall', 'key_change'
    details: Optional[Dict[str, Any]] = None


@dataclass
class StatusMessageEvent(CardEvent):
    """Emitted for status bar updates."""
    message: str
    level: str = "info"  # 'info', 'warning', 'error'


@dataclass
class ErrorEvent(CardEvent):
    """Emitted when an error occurs."""
    message: str
    exception: Optional[Exception] = None
    recoverable: bool = True


@dataclass
class KeyPromptEvent(CardEvent):
    """Emitted when a key prompt is needed."""
    uid: str
    reason: str = "authentication"


@dataclass
class KeyValidatedEvent(CardEvent):
    """Emitted when a key is validated (correct or incorrect)."""
    uid: str
    valid: bool
    uses_default: Optional[bool] = None


@dataclass
class TitleBarUpdateEvent(CardEvent):
    """Emitted to update the window title."""
    title: str


@dataclass
class ProgressEvent(CardEvent):
    """Emitted for progress updates during operations."""
    operation: str
    progress: int  # 0-100, -1 for indeterminate
    message: Optional[str] = None


# ============================================================================
# Event Bus Implementation
# ============================================================================


class EventBus(QObject):
    """
    Central event dispatcher using Qt signals.

    Provides typed event emission and subscription for decoupled
    communication between components.

    Usage:
        bus = EventBus.instance()

        # Subscribe
        bus.card_presence.connect(my_handler)

        # Emit
        bus.emit(CardPresenceEvent(present=True, uid="04AABB..."))
    """

    # Typed signals for each event category
    readers_changed = pyqtSignal(object)  # ReadersChangedEvent
    card_presence = pyqtSignal(object)    # CardPresenceEvent
    card_state = pyqtSignal(object)       # CardStateChangedEvent
    card_memory = pyqtSignal(object)      # CardMemoryUpdatedEvent
    installed_apps = pyqtSignal(object)   # InstalledAppsUpdatedEvent
    operation_result = pyqtSignal(object) # OperationResultEvent
    status_message = pyqtSignal(object)   # StatusMessageEvent
    error = pyqtSignal(object)            # ErrorEvent
    key_prompt = pyqtSignal(object)       # KeyPromptEvent
    key_validated = pyqtSignal(object)    # KeyValidatedEvent
    title_bar = pyqtSignal(object)        # TitleBarUpdateEvent
    progress = pyqtSignal(object)         # ProgressEvent

    # Singleton instance
    _instance: Optional["EventBus"] = None

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._event_log: List[CardEvent] = []
        self._log_events = False

    @classmethod
    def instance(cls) -> "EventBus":
        """Get the singleton EventBus instance."""
        if cls._instance is None:
            cls._instance = EventBus()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None

    def enable_logging(self, enable: bool = True) -> None:
        """Enable/disable event logging for debugging."""
        self._log_events = enable

    def get_event_log(self) -> List[CardEvent]:
        """Get logged events (for debugging/testing)."""
        return list(self._event_log)

    def clear_event_log(self) -> None:
        """Clear the event log."""
        self._event_log.clear()

    def emit(self, event: CardEvent) -> None:
        """
        Emit an event to the appropriate signal.

        Args:
            event: Event instance to emit
        """
        if self._log_events:
            self._event_log.append(event)

        # Route to appropriate signal based on event type
        if isinstance(event, ReadersChangedEvent):
            self.readers_changed.emit(event)
        elif isinstance(event, CardPresenceEvent):
            self.card_presence.emit(event)
        elif isinstance(event, CardStateChangedEvent):
            self.card_state.emit(event)
        elif isinstance(event, CardMemoryUpdatedEvent):
            self.card_memory.emit(event)
        elif isinstance(event, InstalledAppsUpdatedEvent):
            self.installed_apps.emit(event)
        elif isinstance(event, OperationResultEvent):
            self.operation_result.emit(event)
        elif isinstance(event, StatusMessageEvent):
            self.status_message.emit(event)
        elif isinstance(event, ErrorEvent):
            self.error.emit(event)
        elif isinstance(event, KeyPromptEvent):
            self.key_prompt.emit(event)
        elif isinstance(event, KeyValidatedEvent):
            self.key_validated.emit(event)
        elif isinstance(event, TitleBarUpdateEvent):
            self.title_bar.emit(event)
        elif isinstance(event, ProgressEvent):
            self.progress.emit(event)

    # Convenience methods for common events

    def emit_status(self, message: str, level: str = "info") -> None:
        """Emit a status message event."""
        self.emit(StatusMessageEvent(message=message, level=level))

    def emit_error(
        self,
        message: str,
        exception: Optional[Exception] = None,
        recoverable: bool = True,
    ) -> None:
        """Emit an error event."""
        self.emit(ErrorEvent(
            message=message,
            exception=exception,
            recoverable=recoverable,
        ))

    def emit_progress(
        self,
        operation: str,
        progress: int,
        message: Optional[str] = None,
    ) -> None:
        """Emit a progress event."""
        self.emit(ProgressEvent(
            operation=operation,
            progress=progress,
            message=message,
        ))
