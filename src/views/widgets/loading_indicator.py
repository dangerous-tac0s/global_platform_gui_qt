"""
LoadingIndicator widget - Shows an animated spinner during async operations.

Provides visual feedback that the application is working on something.
"""

from typing import Optional

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtCore import QTimer, Qt


class LoadingIndicator(QWidget):
    """
    Animated loading indicator using Unicode braille spinner.

    Usage:
        indicator = LoadingIndicator()
        indicator.start("Loading plugins...")
        # ... async operation ...
        indicator.stop()
    """

    # Braille spinner animation frames
    SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        interval: int = 80,
    ):
        """
        Initialize the loading indicator.

        Args:
            parent: Parent widget
            interval: Animation frame interval in milliseconds
        """
        super().__init__(parent)

        self._frame_index = 0
        self._message = ""

        # Create layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Spinner label
        self._spinner_label = QLabel("")
        self._spinner_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(self._spinner_label)

        # Message label
        self._message_label = QLabel("")
        self._message_label.setStyleSheet("color: #888;")
        layout.addWidget(self._message_label)

        layout.addStretch()

        # Animation timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_frame)
        self._interval = interval

        # Start hidden
        self.hide()

    def start(self, message: str = "Loading...") -> None:
        """
        Start the loading animation with a message.

        Args:
            message: Status message to display
        """
        self._message = message
        self._message_label.setText(message)
        self._frame_index = 0
        self._update_frame()
        self._timer.start(self._interval)
        self.show()

    def stop(self) -> None:
        """Stop the loading animation and hide the indicator."""
        self._timer.stop()
        self._spinner_label.setText("")
        self._message_label.setText("")
        self.hide()

    def set_message(self, message: str) -> None:
        """
        Update the loading message without restarting.

        Args:
            message: New status message
        """
        self._message = message
        self._message_label.setText(message)

    def _update_frame(self) -> None:
        """Update to the next animation frame."""
        self._spinner_label.setText(self.SPINNER_FRAMES[self._frame_index])
        self._frame_index = (self._frame_index + 1) % len(self.SPINNER_FRAMES)

    @property
    def is_running(self) -> bool:
        """Check if the indicator is currently running."""
        return self._timer.isActive()
