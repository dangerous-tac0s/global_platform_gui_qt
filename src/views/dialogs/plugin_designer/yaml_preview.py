"""
YAML Preview Pane

Displays YAML content with syntax highlighting.
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QColor, QTextCharFormat, QSyntaxHighlighter
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QTextEdit,
    QLabel,
)


class YamlHighlighter(QSyntaxHighlighter):
    """Simple YAML syntax highlighter."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Define formats
        self._key_format = QTextCharFormat()
        self._key_format.setForeground(QColor("#0000CC"))  # Blue
        self._key_format.setFontWeight(QFont.Bold)

        self._string_format = QTextCharFormat()
        self._string_format.setForeground(QColor("#008800"))  # Green

        self._number_format = QTextCharFormat()
        self._number_format.setForeground(QColor("#CC6600"))  # Orange

        self._comment_format = QTextCharFormat()
        self._comment_format.setForeground(QColor("#888888"))  # Gray
        self._comment_format.setFontItalic(True)

        self._bool_format = QTextCharFormat()
        self._bool_format.setForeground(QColor("#CC00CC"))  # Purple

        self._list_marker_format = QTextCharFormat()
        self._list_marker_format.setForeground(QColor("#666666"))  # Dark gray

    def highlightBlock(self, text: str):
        """Apply highlighting to a block of text."""
        # Skip empty lines
        if not text.strip():
            return

        # Check for comment
        if text.strip().startswith("#"):
            self.setFormat(0, len(text), self._comment_format)
            return

        # Check for list marker
        stripped = text.lstrip()
        if stripped.startswith("- "):
            indent = len(text) - len(stripped)
            self.setFormat(indent, 2, self._list_marker_format)
            text = text[indent + 2:]
            start_offset = indent + 2
        else:
            start_offset = 0

        # Check for key: value
        if ":" in text:
            colon_pos = text.index(":")
            # Highlight key
            key_start = 0
            while key_start < len(text) and text[key_start] == " ":
                key_start += 1

            self.setFormat(start_offset + key_start, colon_pos - key_start, self._key_format)

            # Highlight value
            value_start = colon_pos + 1
            while value_start < len(text) and text[value_start] == " ":
                value_start += 1

            value = text[value_start:].strip()

            if value:
                # Check value type
                if value.startswith('"') or value.startswith("'"):
                    self.setFormat(start_offset + value_start, len(value), self._string_format)
                elif value.lower() in ("true", "false", "yes", "no", "null", "~"):
                    self.setFormat(start_offset + value_start, len(value), self._bool_format)
                elif self._is_number(value):
                    self.setFormat(start_offset + value_start, len(value), self._number_format)
                else:
                    # Plain string value
                    self.setFormat(start_offset + value_start, len(value), self._string_format)

    def _is_number(self, text: str) -> bool:
        """Check if text is a number."""
        try:
            float(text)
            return True
        except ValueError:
            return False


class YamlPreviewPane(QWidget):
    """
    Widget that displays YAML content with syntax highlighting.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # YAML display
        self._text_edit = QTextEdit()
        self._text_edit.setReadOnly(True)
        self._text_edit.setFont(QFont("Courier New", 10))
        self._text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #f8f8f8;
                border: 1px solid #ccc;
            }
        """)

        # Apply syntax highlighter
        self._highlighter = YamlHighlighter(self._text_edit.document())

        layout.addWidget(self._text_edit)

    def set_yaml(self, yaml_content: str):
        """Set the YAML content to display."""
        self._text_edit.setPlainText(yaml_content)

    def get_yaml(self) -> str:
        """Get the current YAML content."""
        return self._text_edit.toPlainText()

    def clear(self):
        """Clear the display."""
        self._text_edit.clear()
