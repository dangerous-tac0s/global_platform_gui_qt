"""
StatusBar widget - Displays status messages with auto-rotation.

Subscribes to StatusMessageEvent from EventBus and displays messages
with a timeout calculated based on message length.
"""

from typing import Optional

from PyQt5.QtWidgets import QLabel, QWidget, QHBoxLayout
from PyQt5.QtCore import QTimer

from ...events.event_bus import EventBus, StatusMessageEvent, ErrorEvent


class MessageQueue:
    """
    Message queue that rotates through messages with timeouts.

    Each message is displayed for a duration proportional to its length,
    with a minimum of 3 seconds.
    """

    def __init__(self, label: QLabel):
        """
        Initialize the message queue.

        Args:
            label: QLabel to display messages on
        """
        self.label = label
        self.queue: list = []
        self.timer = QTimer()
        self.timer.timeout.connect(self._process_queue)

    def add_message(self, message: str) -> None:
        """
        Add a message to the queue.

        Args:
            message: Message text to display
        """
        timeout = self._calculate_timeout(message)
        self.queue.append((message, timeout))
        if not self.timer.isActive():
            self._process_queue()

    def _calculate_timeout(self, message: str) -> int:
        """Calculate display timeout based on message length."""
        return max(3000, len(message) * 50)

    def _process_queue(self) -> None:
        """Process the next message in the queue."""
        if self.queue:
            message, timeout = self.queue.pop(0)
            self.label.setText(message)
            self.timer.start(timeout)
        else:
            self.timer.stop()

    def clear(self) -> None:
        """Clear all pending messages."""
        self.queue.clear()
        self.timer.stop()


class StatusBar(QWidget):
    """
    Status bar widget that displays rotating status messages.

    Can be used standalone or with EventBus integration:
    - Direct: statusbar.add_message("Hello")
    - EventBus: Automatically subscribes to StatusMessageEvent, ErrorEvent

    Example:
        # Standalone usage
        status = StatusBar()
        status.add_message("Ready.")

        # With EventBus (auto-subscribed)
        status = StatusBar(subscribe_to_events=True)
        EventBus.instance().emit(StatusMessageEvent(message="Hello"))
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        initial_message: str = "Ready.",
        subscribe_to_events: bool = True,
    ):
        """
        Initialize the status bar.

        Args:
            parent: Parent widget
            initial_message: Initial status message
            subscribe_to_events: If True, subscribe to EventBus events
        """
        super().__init__(parent)

        # Create layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create label
        self._label = QLabel(initial_message)
        layout.addWidget(self._label)

        # Create message queue
        self._queue = MessageQueue(self._label)

        # Subscribe to EventBus if requested
        self._event_bus: Optional[EventBus] = None
        if subscribe_to_events:
            self._subscribe_to_events()

    def _subscribe_to_events(self) -> None:
        """Subscribe to EventBus events."""
        self._event_bus = EventBus.instance()
        self._event_bus.subscribe(StatusMessageEvent, self._on_status_message)
        self._event_bus.subscribe(ErrorEvent, self._on_error)

    def _on_status_message(self, event: StatusMessageEvent) -> None:
        """Handle StatusMessageEvent."""
        self.add_message(event.message)

    def _on_error(self, event: ErrorEvent) -> None:
        """Handle ErrorEvent by displaying error message."""
        self.add_message(f"Error: {event.message}")

    def add_message(self, message: str) -> None:
        """
        Add a message to display.

        Args:
            message: Message text to show
        """
        self._queue.add_message(message)

    def set_text(self, text: str) -> None:
        """
        Set label text directly (bypasses queue).

        Args:
            text: Text to display immediately
        """
        self._label.setText(text)

    def clear(self) -> None:
        """Clear all pending messages and reset to empty."""
        self._queue.clear()
        self._label.setText("")

    def unsubscribe(self) -> None:
        """Unsubscribe from EventBus events."""
        if self._event_bus:
            self._event_bus.unsubscribe(StatusMessageEvent, self._on_status_message)
            self._event_bus.unsubscribe(ErrorEvent, self._on_error)
            self._event_bus = None

    @property
    def label(self) -> QLabel:
        """Get the underlying QLabel."""
        return self._label

    @property
    def message_queue(self) -> MessageQueue:
        """Get the message queue for direct access."""
        return self._queue
