"""
LoadingDialog - Non-modal spinner overlay for background operations.

Shows a "Please Wait..." message with an animated spinner while
card detection, installation, or other operations are in progress.
Does NOT block the event loop - signals are processed normally.
"""

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QWidget, QApplication
from PyQt5.QtCore import Qt, QTimer, QRectF
from PyQt5.QtGui import QPainter, QPen, QColor


class SpinnerWidget(QWidget):
    """Animated spinning arc widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate)
        self.setFixedSize(48, 48)

    def _rotate(self):
        self._angle = (self._angle + 10) % 360
        self.update()

    def start(self):
        self._timer.start(50)  # 20 FPS

    def stop(self):
        self._timer.stop()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Draw arc
        pen = QPen(QColor("#3498db"))  # Blue color
        pen.setWidth(4)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)

        rect = QRectF(6, 6, 36, 36)
        # Draw a 270-degree arc, rotating based on _angle
        painter.drawArc(rect, self._angle * 16, 270 * 16)


class LoadingDialog(QDialog):
    """
    Non-modal spinner overlay for background operations.

    Features:
    - Animated spinner
    - "Please Wait..." message
    - Configurable timeout with callback
    - Frameless, centered on parent
    - NON-MODAL: Does not block event processing

    Usage:
        dialog = LoadingDialog(parent=main_window)
        dialog.show_loading(timeout=10)  # Auto-hide after 10s
        # ... operation completes in background ...
        dialog.hide_loading()  # Called when signal received
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        # Frameless overlay - NOT modal so events still process
        # Note: No WindowStaysOnTopHint so other dialogs can appear above
        self.setWindowFlags(
            Qt.Tool
            | Qt.FramelessWindowHint
        )
        # Explicitly non-modal so main event loop keeps processing
        self.setModal(False)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)

        # Styling
        self.setStyleSheet("""
            LoadingDialog {
                background-color: #2d2d2d;
                border: 1px solid #555;
                border-radius: 8px;
            }
            QLabel {
                color: #ffffff;
                font-size: 14px;
            }
        """)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignCenter)

        # Spinner
        self._spinner = SpinnerWidget(self)
        layout.addWidget(self._spinner, alignment=Qt.AlignCenter)

        # Label
        self._label = QLabel("Please Wait...")
        self._label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._label)

        # Timeout timer
        self._timeout_timer = QTimer(self)
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)

        self._timeout_callback = None

        # Fixed size
        self.setFixedSize(160, 120)

    def show_loading(self, timeout: int = 30, on_timeout=None):
        """
        Show the loading dialog.

        Args:
            timeout: Seconds before auto-hiding (0 = no timeout)
            on_timeout: Optional callback when timeout occurs
        """
        self._timeout_callback = on_timeout

        # Center on parent
        if self.parent():
            parent_rect = self.parent().geometry()
            x = parent_rect.x() + (parent_rect.width() - self.width()) // 2
            y = parent_rect.y() + (parent_rect.height() - self.height()) // 2
            self.move(x, y)

        # Start spinner
        self._spinner.start()

        # Start timeout timer
        if timeout > 0:
            self._timeout_timer.start(timeout * 1000)

        self.show()
        self.raise_()

    def hide_loading(self):
        """Hide the loading dialog immediately."""
        self._timeout_timer.stop()
        self._spinner.stop()
        self.hide()
        # Process events to ensure hide takes effect before other dialogs show
        QApplication.processEvents()

    def _on_timeout(self):
        """Handle timeout - hide and call callback."""
        self.hide_loading()
        if self._timeout_callback:
            self._timeout_callback()

    def set_text(self, text: str):
        """Update the label text."""
        self._label.setText(text)

    def is_loading(self) -> bool:
        """Check if the dialog is currently visible."""
        return self.isVisible()
