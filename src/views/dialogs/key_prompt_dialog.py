"""
KeyPromptDialog - Dialog for entering smart card keys.

Used when a new card is detected or when updating an existing card's key.
"""

from typing import Optional, Dict, Any

from PyQt5.QtWidgets import (
    QDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
)

# Default GlobalPlatform key
DEFAULT_KEY = "404142434445464748494A4B4C4D4E4F"


class KeyPromptDialog(QDialog):
    """
    Dialog for prompting user to enter a smart card key.

    Shows a form with:
    - Label explaining the purpose
    - Text field for key entry (pre-filled with default if new card)
    - Reset to Default button
    - OK button to submit

    Example:
        dialog = KeyPromptDialog("04AABBCCDD", is_new=True)
        if dialog.exec_() == QDialog.Accepted:
            result = dialog.get_results()
            # result = {"card_id": "04AABBCCDD", "key": "..."}
    """

    def __init__(
        self,
        card_id: str,
        existing_key: Optional[str] = None,
        is_new: bool = True,
        parent=None,
    ):
        """
        Initialize the key prompt dialog.

        Args:
            card_id: Card identifier (CPLC hash or UID)
            existing_key: Current key if updating, None for new card
            is_new: True if this is a new card, False if updating
            parent: Parent widget
        """
        super().__init__(parent)

        # Set title based on context
        if is_new:
            title = "New Smart Card Found!"
        else:
            title = "Update Smart Card Key"

        self.setWindowTitle(title)
        self.card_id = card_id

        # Create layout
        layout = QFormLayout()

        # Label
        self.label = QLabel("Enter key:")
        layout.addRow(self.label)

        # Input field
        self.input_field = QLineEdit()
        if existing_key is None or existing_key == "None":
            self.input_field.setText(DEFAULT_KEY)
        else:
            self.input_field.setText(existing_key)
        layout.addRow(self.input_field)

        # Buttons
        self.reset_button = QPushButton("Reset to Default")
        self.reset_button.clicked.connect(self._reset_to_default)

        self.submit_button = QPushButton("OK")
        self.submit_button.clicked.connect(self.accept)

        layout.addRow(self.reset_button, self.submit_button)

        self.setLayout(layout)
        self.setFixedWidth(800)

    def _reset_to_default(self) -> None:
        """Reset the input field to the default key."""
        self.input_field.setText(DEFAULT_KEY)

    def get_input(self) -> str:
        """Get the entered key."""
        return self.input_field.text()

    def get_results(self) -> Dict[str, Any]:
        """
        Get the dialog results.

        Returns:
            Dict with 'card_id' and 'key'
        """
        return {
            "card_id": self.card_id,
            "key": self.input_field.text(),
        }

    @property
    def key(self) -> str:
        """Get the entered key."""
        return self.input_field.text()

    def is_default_key(self) -> bool:
        """Check if the entered key is the default key."""
        return self.input_field.text() == DEFAULT_KEY
