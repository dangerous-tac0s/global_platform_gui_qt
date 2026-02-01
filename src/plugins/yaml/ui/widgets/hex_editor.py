"""
Hex Editor Widget

A specialized text editor for hexadecimal input with:
- Auto-formatting (uppercase, spacing)
- Validation (only hex characters)
- Byte count display
"""

import re
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QTextCursor
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)


class HexEditorWidget(QWidget):
    """
    A widget for editing hexadecimal data with validation and formatting.

    Features:
    - Automatic uppercase conversion
    - Optional space formatting (every 2 chars)
    - Hex-only input validation
    - Byte count display
    """

    textChanged = pyqtSignal(str)  # Emits cleaned hex (no spaces)
    validChanged = pyqtSignal(bool)  # Emits validity status

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        auto_format: bool = True,
        show_byte_count: bool = True,
        min_rows: int = 3,
        max_rows: int = 10,
    ):
        super().__init__(parent)
        self._auto_format = auto_format
        self._show_byte_count = show_byte_count
        self._min_rows = min_rows
        self._max_rows = max_rows
        self._is_valid = True
        self._updating = False

        self._setup_ui()

    def _setup_ui(self):
        """Set up the widget UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Text editor
        self._editor = QPlainTextEdit()
        self._editor.setFont(QFont("Monospace", 10))
        self._editor.setLineWrapMode(QPlainTextEdit.WidgetWidth)

        # Set height based on rows
        line_height = self._editor.fontMetrics().lineSpacing()
        self._editor.setMinimumHeight(line_height * self._min_rows + 10)
        self._editor.setMaximumHeight(line_height * self._max_rows + 10)

        self._editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._editor)

        # Status bar with byte count and validation
        if self._show_byte_count:
            status_layout = QHBoxLayout()
            status_layout.setContentsMargins(0, 0, 0, 0)

            self._byte_count_label = QLabel("0 bytes")
            self._byte_count_label.setStyleSheet("color: gray; font-size: 11px;")
            status_layout.addWidget(self._byte_count_label)

            status_layout.addStretch()

            self._status_label = QLabel("")
            self._status_label.setStyleSheet("color: gray; font-size: 11px;")
            status_layout.addWidget(self._status_label)

            layout.addLayout(status_layout)

        self.setLayout(layout)

    def _on_text_changed(self):
        """Handle text changes with auto-formatting."""
        if self._updating:
            return

        text = self._editor.toPlainText()
        cursor = self._editor.textCursor()
        position = cursor.position()

        # Clean and validate
        cleaned = self._clean_hex(text)
        is_valid = self._validate_hex(cleaned)

        # Auto-format if enabled
        if self._auto_format and is_valid:
            formatted = self._format_hex(cleaned)

            if formatted != text:
                self._updating = True

                # Calculate new cursor position
                # Count hex chars before cursor in original text
                hex_before_cursor = len(self._clean_hex(text[:position]))

                self._editor.setPlainText(formatted)

                # Position cursor after same number of hex chars
                new_pos = self._position_after_hex_chars(formatted, hex_before_cursor)
                cursor = self._editor.textCursor()
                cursor.setPosition(new_pos)
                self._editor.setTextCursor(cursor)

                self._updating = False

        # Update status
        self._update_status(cleaned, is_valid)

        # Emit signals
        if is_valid != self._is_valid:
            self._is_valid = is_valid
            self.validChanged.emit(is_valid)

        self.textChanged.emit(cleaned)

    def _clean_hex(self, text: str) -> str:
        """Remove all non-hex characters and convert to uppercase."""
        return re.sub(r'[^0-9A-Fa-f]', '', text).upper()

    def _validate_hex(self, hex_str: str) -> bool:
        """Validate that string contains only hex characters."""
        if not hex_str:
            return True
        return bool(re.match(r'^[0-9A-Fa-f]*$', hex_str))

    def _format_hex(self, hex_str: str) -> str:
        """Format hex string with spaces every 2 characters."""
        # Add space every 2 chars
        formatted = ' '.join(hex_str[i:i+2] for i in range(0, len(hex_str), 2))
        return formatted.upper()

    def _position_after_hex_chars(self, formatted: str, hex_count: int) -> int:
        """Find position in formatted string after N hex characters."""
        count = 0
        for i, char in enumerate(formatted):
            if char in '0123456789ABCDEFabcdef':
                count += 1
                if count >= hex_count:
                    return i + 1
        return len(formatted)

    def _update_status(self, hex_str: str, is_valid: bool):
        """Update status labels."""
        if not self._show_byte_count:
            return

        byte_count = len(hex_str) // 2
        remainder = len(hex_str) % 2

        if remainder:
            self._byte_count_label.setText(f"{byte_count} bytes + {remainder} nibble")
            self._byte_count_label.setStyleSheet("color: orange; font-size: 11px;")
        else:
            self._byte_count_label.setText(f"{byte_count} bytes")
            self._byte_count_label.setStyleSheet("color: gray; font-size: 11px;")

        if is_valid:
            self._status_label.setText("")
        else:
            self._status_label.setText("Invalid hex")
            self._status_label.setStyleSheet("color: red; font-size: 11px;")

    def getText(self) -> str:
        """Get the cleaned hex string (no spaces)."""
        return self._clean_hex(self._editor.toPlainText())

    def setText(self, hex_str: str):
        """Set the hex content."""
        cleaned = self._clean_hex(hex_str)
        if self._auto_format:
            formatted = self._format_hex(cleaned)
        else:
            formatted = cleaned
        self._editor.setPlainText(formatted)

    def getBytes(self) -> bytes:
        """Get the hex content as bytes."""
        hex_str = self.getText()
        if len(hex_str) % 2:
            hex_str = hex_str[:-1]  # Truncate incomplete byte
        return bytes.fromhex(hex_str) if hex_str else b''

    def setBytes(self, data: bytes):
        """Set the hex content from bytes."""
        self.setText(data.hex())

    def isValid(self) -> bool:
        """Check if the current content is valid hex."""
        return self._is_valid

    def isComplete(self) -> bool:
        """Check if hex has complete bytes (even number of chars)."""
        return len(self.getText()) % 2 == 0

    def clear(self):
        """Clear the editor."""
        self._editor.clear()

    def setPlaceholderText(self, text: str):
        """Set placeholder text."""
        self._editor.setPlaceholderText(text)

    def setReadOnly(self, readonly: bool):
        """Set read-only mode."""
        self._editor.setReadOnly(readonly)


class HexLineEdit(QWidget):
    """
    A single-line hex editor widget.

    Similar to HexEditorWidget but for single-line input.
    """

    textChanged = pyqtSignal(str)
    validChanged = pyqtSignal(bool)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        auto_format: bool = True,
        max_bytes: Optional[int] = None,
    ):
        super().__init__(parent)
        self._auto_format = auto_format
        self._max_bytes = max_bytes
        self._is_valid = True
        self._updating = False

        self._setup_ui()

    def _setup_ui(self):
        """Set up the widget UI."""
        from PyQt5.QtWidgets import QLineEdit

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._editor = QLineEdit()
        self._editor.setFont(QFont("Monospace", 10))
        self._editor.textChanged.connect(self._on_text_changed)

        layout.addWidget(self._editor, 1)

        self._byte_label = QLabel("0B")
        self._byte_label.setStyleSheet("color: gray; font-size: 11px;")
        self._byte_label.setFixedWidth(40)
        layout.addWidget(self._byte_label)

        self.setLayout(layout)

    def _on_text_changed(self, text: str):
        """Handle text changes."""
        if self._updating:
            return

        cursor_pos = self._editor.cursorPosition()

        # Clean and validate
        cleaned = self._clean_hex(text)

        # Apply max bytes limit
        if self._max_bytes and len(cleaned) > self._max_bytes * 2:
            cleaned = cleaned[:self._max_bytes * 2]

        is_valid = self._validate_hex(cleaned)

        # Auto-format
        if self._auto_format and is_valid:
            formatted = self._format_hex(cleaned)

            if formatted != text:
                self._updating = True

                hex_before_cursor = len(self._clean_hex(text[:cursor_pos]))
                self._editor.setText(formatted)

                new_pos = self._position_after_hex_chars(formatted, hex_before_cursor)
                self._editor.setCursorPosition(new_pos)

                self._updating = False

        # Update byte count
        byte_count = len(cleaned) // 2
        self._byte_label.setText(f"{byte_count}B")

        # Emit signals
        if is_valid != self._is_valid:
            self._is_valid = is_valid
            self.validChanged.emit(is_valid)

        self.textChanged.emit(cleaned)

    def _clean_hex(self, text: str) -> str:
        """Remove non-hex characters."""
        return re.sub(r'[^0-9A-Fa-f]', '', text).upper()

    def _validate_hex(self, hex_str: str) -> bool:
        """Validate hex string."""
        if not hex_str:
            return True
        return bool(re.match(r'^[0-9A-Fa-f]*$', hex_str))

    def _format_hex(self, hex_str: str) -> str:
        """Format with spaces."""
        return ' '.join(hex_str[i:i+2] for i in range(0, len(hex_str), 2)).upper()

    def _position_after_hex_chars(self, formatted: str, hex_count: int) -> int:
        """Find position after N hex chars."""
        count = 0
        for i, char in enumerate(formatted):
            if char in '0123456789ABCDEFabcdef':
                count += 1
                if count >= hex_count:
                    return i + 1
        return len(formatted)

    def getText(self) -> str:
        """Get cleaned hex."""
        return self._clean_hex(self._editor.text())

    def setText(self, hex_str: str):
        """Set hex content."""
        cleaned = self._clean_hex(hex_str)
        if self._auto_format:
            self._editor.setText(self._format_hex(cleaned))
        else:
            self._editor.setText(cleaned)

    def isValid(self) -> bool:
        """Check validity."""
        return self._is_valid

    def clear(self):
        """Clear editor."""
        self._editor.clear()

    def setPlaceholderText(self, text: str):
        """Set placeholder."""
        self._editor.setPlaceholderText(text)
