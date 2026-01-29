"""
ComboDialog - Generic selection dialog with a dropdown.

Provides a simple dialog for selecting from a list of options.
"""

from typing import Optional, List, Callable, Any

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QLabel,
    QComboBox,
    QDialogButtonBox,
)


class ComboDialog(QDialog):
    """
    Generic dialog with a dropdown selection.

    Features:
    - Configurable title and label
    - Dropdown with provided options
    - OK/Cancel buttons
    - Callbacks for accept/cancel

    Example:
        def on_accept(dialog, choice):
            print(f"Selected: {choice}")

        dialog = ComboDialog(
            options=["Option A", "Option B", "Option C"],
            on_accept=on_accept,
            on_cancel=lambda: print("Cancelled"),
            window_title="Choose",
            combo_label="Select an option:",
        )
        dialog.exec_()
    """

    def __init__(
        self,
        options: List[str],
        on_accept: Callable[["ComboDialog", str], Any],
        on_cancel: Callable[[], Any],
        parent=None,
        window_title: str = "Select Option",
        combo_label: str = "Choose an Option",
    ):
        """
        Initialize the combo dialog.

        Args:
            options: List of option strings for the dropdown
            on_accept: Callback when OK is clicked, receives (dialog, selected_text)
            on_cancel: Callback when Cancel is clicked
            parent: Parent widget
            window_title: Dialog window title
            combo_label: Label above the dropdown
        """
        super().__init__(parent)
        self.setWindowTitle(window_title)

        self.on_accept = on_accept
        self.on_cancel = on_cancel

        # Stores the final choice after accept
        self.choice: Optional[str] = None

        # Create layout
        layout = QVBoxLayout(self)

        # Label
        layout.addWidget(QLabel(combo_label))

        # Dropdown
        self.combo = QComboBox()
        self.combo.addItems(options)
        layout.addWidget(self.combo)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._handle_accept)
        buttons.rejected.connect(self._handle_cancel)
        layout.addWidget(buttons)

        self.setLayout(layout)
        self.setModal(True)

    def _handle_accept(self) -> None:
        """Handle OK button click."""
        self.choice = self.combo.currentText()
        self.on_accept(self, self.choice)
        self.accept()

    def _handle_cancel(self) -> None:
        """Handle Cancel button click."""
        self.on_cancel()
        self.reject()

    @property
    def selected(self) -> str:
        """Get currently selected option text."""
        return self.combo.currentText()

    @property
    def selected_index(self) -> int:
        """Get currently selected option index."""
        return self.combo.currentIndex()

    def set_selected(self, text: str) -> bool:
        """
        Set the selected option by text.

        Args:
            text: Option text to select

        Returns:
            True if option was found and selected
        """
        index = self.combo.findText(text)
        if index >= 0:
            self.combo.setCurrentIndex(index)
            return True
        return False

    def set_selected_index(self, index: int) -> bool:
        """
        Set the selected option by index.

        Args:
            index: Index to select

        Returns:
            True if index was valid
        """
        if 0 <= index < self.combo.count():
            self.combo.setCurrentIndex(index)
            return True
        return False
