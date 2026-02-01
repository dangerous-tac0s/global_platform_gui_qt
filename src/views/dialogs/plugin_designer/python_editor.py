"""
Python Script Editor with Syntax Highlighting

Provides a QTextEdit with Python syntax highlighting and pop-out capability.
"""

import re
from typing import Optional, Callable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import (
    QSyntaxHighlighter,
    QTextCharFormat,
    QColor,
    QFont,
    QTextDocument,
)
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTextEdit,
    QPushButton,
    QDialog,
    QLabel,
    QMessageBox,
    QDialogButtonBox,
)

from .utils import show_open_file_dialog, show_save_file_dialog


class PythonHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for Python code."""

    def __init__(self, document: QTextDocument):
        super().__init__(document)
        self._highlighting_rules = []
        self._setup_rules()

    def _setup_rules(self):
        """Set up syntax highlighting rules."""
        # Keywords
        keyword_format = QTextCharFormat()
        keyword_format.setForeground(QColor("#CF8E6D"))  # Orange
        keyword_format.setFontWeight(QFont.Bold)
        keywords = [
            "and", "as", "assert", "async", "await", "break", "class",
            "continue", "def", "del", "elif", "else", "except", "finally",
            "for", "from", "global", "if", "import", "in", "is", "lambda",
            "nonlocal", "not", "or", "pass", "raise", "return", "try",
            "while", "with", "yield", "True", "False", "None",
        ]
        for word in keywords:
            pattern = rf"\b{word}\b"
            self._highlighting_rules.append((re.compile(pattern), keyword_format))

        # Built-in functions
        builtin_format = QTextCharFormat()
        builtin_format.setForeground(QColor("#56A8F5"))  # Blue
        builtins = [
            "abs", "all", "any", "bin", "bool", "bytes", "callable", "chr",
            "dict", "dir", "enumerate", "eval", "exec", "filter", "float",
            "format", "getattr", "hasattr", "hash", "hex", "id", "input",
            "int", "isinstance", "issubclass", "iter", "len", "list", "map",
            "max", "min", "next", "object", "oct", "open", "ord", "pow",
            "print", "range", "repr", "reversed", "round", "set", "setattr",
            "slice", "sorted", "str", "sum", "super", "tuple", "type", "zip",
        ]
        for word in builtins:
            pattern = rf"\b{word}\b"
            self._highlighting_rules.append((re.compile(pattern), builtin_format))

        # Self
        self_format = QTextCharFormat()
        self_format.setForeground(QColor("#94558D"))  # Purple
        self_format.setFontItalic(True)
        self._highlighting_rules.append((re.compile(r"\bself\b"), self_format))
        self._highlighting_rules.append((re.compile(r"\bcontext\b"), self_format))

        # Decorators
        decorator_format = QTextCharFormat()
        decorator_format.setForeground(QColor("#BBB529"))  # Yellow
        self._highlighting_rules.append((re.compile(r"@\w+"), decorator_format))

        # Numbers
        number_format = QTextCharFormat()
        number_format.setForeground(QColor("#6897BB"))  # Light blue
        self._highlighting_rules.append((
            re.compile(r"\b[0-9]+\.?[0-9]*([eE][+-]?[0-9]+)?\b"),
            number_format
        ))
        self._highlighting_rules.append((
            re.compile(r"\b0[xX][0-9A-Fa-f]+\b"),
            number_format
        ))

        # Strings (double quotes)
        string_format = QTextCharFormat()
        string_format.setForeground(QColor("#6A8759"))  # Green
        self._highlighting_rules.append((
            re.compile(r'"[^"\\]*(\\.[^"\\]*)*"'),
            string_format
        ))
        # Strings (single quotes)
        self._highlighting_rules.append((
            re.compile(r"'[^'\\]*(\\.[^'\\]*)*'"),
            string_format
        ))
        # Triple-quoted strings
        self._highlighting_rules.append((
            re.compile(r'""".*?"""', re.DOTALL),
            string_format
        ))
        self._highlighting_rules.append((
            re.compile(r"'''.*?'''", re.DOTALL),
            string_format
        ))

        # Comments
        comment_format = QTextCharFormat()
        comment_format.setForeground(QColor("#808080"))  # Gray
        comment_format.setFontItalic(True)
        self._highlighting_rules.append((re.compile(r"#[^\n]*"), comment_format))

        # Function/method definitions
        func_format = QTextCharFormat()
        func_format.setForeground(QColor("#FFC66D"))  # Yellow-orange
        self._highlighting_rules.append((
            re.compile(r"\bdef\s+(\w+)"),
            func_format,
            1  # Group index
        ))

        # Class definitions
        class_format = QTextCharFormat()
        class_format.setForeground(QColor("#FFC66D"))
        class_format.setFontWeight(QFont.Bold)
        self._highlighting_rules.append((
            re.compile(r"\bclass\s+(\w+)"),
            class_format,
            1
        ))

    def highlightBlock(self, text: str):
        """Apply syntax highlighting to a block of text."""
        for rule in self._highlighting_rules:
            if len(rule) == 2:
                pattern, fmt = rule
                group = 0
            else:
                pattern, fmt, group = rule

            for match in pattern.finditer(text):
                start = match.start(group)
                length = match.end(group) - start
                self.setFormat(start, length, fmt)


class PythonEditorPopout(QDialog):
    """Pop-out window for Python script editing."""

    text_changed = pyqtSignal(str)

    def __init__(self, initial_text: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Python Script Editor")
        self.setMinimumSize(700, 500)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowMinMaxButtonsHint |
            Qt.WindowCloseButtonHint
        )

        self._setup_ui()
        self._editor.setPlainText(initial_text)

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Toolbar
        toolbar = QHBoxLayout()

        load_btn = QPushButton("Load from File...")
        load_btn.clicked.connect(self._load_from_file)
        toolbar.addWidget(load_btn)

        save_btn = QPushButton("Save to File...")
        save_btn.clicked.connect(self._save_to_file)
        toolbar.addWidget(save_btn)

        toolbar.addStretch()

        hint = QLabel("Changes sync automatically to the main window")
        hint.setStyleSheet("color: gray; font-size: 10px;")
        toolbar.addWidget(hint)

        layout.addLayout(toolbar)

        # Editor
        self._editor = QTextEdit()
        self._editor.setFont(QFont("Consolas, Monaco, monospace", 10))
        self._editor.setTabStopDistance(40)  # 4 spaces worth
        self._editor.setLineWrapMode(QTextEdit.NoWrap)
        self._editor.setStyleSheet("""
            QTextEdit {
                background-color: #2B2B2B;
                color: #A9B7C6;
                border: 1px solid #3C3F41;
                selection-background-color: #214283;
            }
        """)
        self._highlighter = PythonHighlighter(self._editor.document())
        self._editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._editor)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def _on_text_changed(self):
        """Emit signal when text changes."""
        self.text_changed.emit(self._editor.toPlainText())

    def _load_from_file(self):
        """Load script from file."""
        def on_file_selected(file_path: str):
            if file_path:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    self._editor.setPlainText(content)
                except Exception as e:
                    QMessageBox.warning(
                        self,
                        "Error Loading File",
                        f"Could not load file:\n{e}"
                    )

        show_open_file_dialog(
            self,
            "Load Python Script",
            [("Python Files", "*.py"), ("All Files", "*.*")],
            on_file_selected
        )

    def _save_to_file(self):
        """Save script to file."""
        content = self._editor.toPlainText()

        def on_file_selected(file_path: str):
            if file_path:
                try:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                except Exception as e:
                    QMessageBox.warning(
                        self,
                        "Error Saving File",
                        f"Could not save file:\n{e}"
                    )

        show_save_file_dialog(
            self,
            "Save Python Script",
            [("Python Files", "*.py"), ("All Files", "*.*")],
            "script.py",
            on_file_selected
        )

    def get_text(self) -> str:
        """Get the current script text."""
        return self._editor.toPlainText()

    def set_text(self, text: str):
        """Set the script text."""
        self._editor.setPlainText(text)


class PythonScriptEditor(QWidget):
    """
    Python script editor widget with syntax highlighting and pop-out support.

    Features:
    - Python syntax highlighting
    - Load from file
    - Pop-out to separate window
    - Syncs changes between main and pop-out editors
    """

    text_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popout_dialog: Optional[PythonEditorPopout] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Python script (sandboxed):"))
        toolbar.addStretch()

        load_btn = QPushButton("Load...")
        load_btn.setMaximumWidth(70)
        load_btn.clicked.connect(self._load_from_file)
        toolbar.addWidget(load_btn)

        self._popout_btn = QPushButton("Pop Out")
        self._popout_btn.setMaximumWidth(70)
        self._popout_btn.clicked.connect(self._toggle_popout)
        toolbar.addWidget(self._popout_btn)

        layout.addLayout(toolbar)

        # Editor
        self._editor = QTextEdit()
        self._editor.setFont(QFont("Consolas, Monaco, monospace", 10))
        self._editor.setTabStopDistance(40)
        self._editor.setPlaceholderText(
            "# Access context variables with context.get('key')\n"
            "# Store results with context.set('key', value)\n"
            "# Example:\n"
            "from cryptography.hazmat.primitives.asymmetric import ec\n"
            "key = ec.generate_private_key(ec.SECP256R1())\n"
            "context.set('private_key', key)"
        )
        self._editor.setStyleSheet("""
            QTextEdit {
                background-color: #2B2B2B;
                color: #A9B7C6;
                border: 1px solid #3C3F41;
                selection-background-color: #214283;
            }
        """)
        self._highlighter = PythonHighlighter(self._editor.document())
        self._editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._editor)

    def _on_text_changed(self):
        """Handle text changes in main editor."""
        if not self._is_popped_out():
            self.text_changed.emit(self._editor.toPlainText())

    def _load_from_file(self):
        """Load script from file."""
        def on_file_selected(file_path: str):
            if file_path:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    self._editor.setPlainText(content)
                except Exception as e:
                    QMessageBox.warning(
                        self,
                        "Error Loading File",
                        f"Could not load file:\n{e}"
                    )

        show_open_file_dialog(
            self,
            "Load Python Script",
            [("Python Files", "*.py"), ("All Files", "*.*")],
            on_file_selected
        )

    def _toggle_popout(self):
        """Toggle the pop-out editor window."""
        if self._is_popped_out():
            # Close popout
            self._popout_dialog.close()
        else:
            # Open popout
            self._popout_dialog = PythonEditorPopout(
                self._editor.toPlainText(),
                self.window()
            )
            self._popout_dialog.text_changed.connect(self._on_popout_text_changed)
            self._popout_dialog.finished.connect(self._on_popout_closed)

            # Disable main editor while popped out
            self._editor.setReadOnly(True)
            self._editor.setStyleSheet("""
                QTextEdit {
                    background-color: #1E1E1E;
                    color: #6A6A6A;
                    border: 1px solid #3C3F41;
                }
            """)
            self._popout_btn.setText("Pop In")

            self._popout_dialog.show()

    def _is_popped_out(self) -> bool:
        """Check if editor is currently popped out."""
        return self._popout_dialog is not None and self._popout_dialog.isVisible()

    def _on_popout_text_changed(self, text: str):
        """Sync text from popout to main editor."""
        self._editor.blockSignals(True)
        self._editor.setPlainText(text)
        self._editor.blockSignals(False)
        self.text_changed.emit(text)

    def _on_popout_closed(self):
        """Handle popout window closing."""
        # Sync final text
        if self._popout_dialog:
            final_text = self._popout_dialog.get_text()
            self._editor.blockSignals(True)
            self._editor.setPlainText(final_text)
            self._editor.blockSignals(False)

        # Re-enable main editor
        self._editor.setReadOnly(False)
        self._editor.setStyleSheet("""
            QTextEdit {
                background-color: #2B2B2B;
                color: #A9B7C6;
                border: 1px solid #3C3F41;
                selection-background-color: #214283;
            }
        """)
        self._popout_btn.setText("Pop Out")
        self._popout_dialog = None

    def get_text(self) -> str:
        """Get the current script text."""
        # If popout is open, get text from there (it has the latest edits)
        if self._is_popped_out():
            return self._popout_dialog.get_text()
        return self._editor.toPlainText()

    def set_text(self, text: str):
        """Set the script text."""
        self._editor.setPlainText(text)
        if self._popout_dialog:
            self._popout_dialog.set_text(text)

    def setMaximumHeight(self, height: int):
        """Set maximum height of the editor."""
        self._editor.setMaximumHeight(height)

    def setPlaceholderText(self, text: str):
        """Set placeholder text."""
        self._editor.setPlaceholderText(text)

    def toPlainText(self) -> str:
        """Get plain text (compatibility method)."""
        return self.get_text()

    def setPlainText(self, text: str):
        """Set plain text (compatibility method)."""
        self.set_text(text)
