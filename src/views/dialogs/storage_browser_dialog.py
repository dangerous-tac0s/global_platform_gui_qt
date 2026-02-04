"""
Storage browser dialogs for viewing, editing, and deleting stored card entries.
"""

import re
from typing import Optional, Dict, List, Any

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QWidget,
    QAbstractItemView,
    QCheckBox,
    QGroupBox,
    QToolButton,
)


# Valid key lengths in bytes
VALID_KEY_LENGTHS = [8, 16, 24, 32]


class HexLineEdit(QLineEdit):
    """QLineEdit with automatic hex formatting and validation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.textChanged.connect(self._format_input)
        self.setPlaceholderText("Enter hex bytes (e.g., 404142434445464748494A4B4C4D4E4F)")

    def _format_input(self):
        """Auto-format input as uppercase hex."""
        text = self.text()
        # Remove all non-hex characters
        hex_only = re.sub(r"[^0-9a-fA-F]", "", text)
        self.blockSignals(True)
        self.setText(hex_only.upper())
        self.blockSignals(False)

    def get_clean_hex(self) -> str:
        """Get hex value without spaces."""
        return self.text().replace(" ", "")

    def get_byte_count(self) -> int:
        """Get number of bytes entered."""
        clean = self.get_clean_hex()
        return len(clean) // 2 if len(clean) % 2 == 0 else 0

    def is_valid_key_length(self) -> bool:
        """Check if current input is a valid key length."""
        return self.get_byte_count() in VALID_KEY_LENGTHS


class CardEntryDialog(QDialog):
    """
    Dialog for adding or editing a card entry.

    Supports both single key (SCP02/legacy) and separate keys (SCP03).

    Modes:
    - 'new': Adding a new card (UID pre-filled, read-only)
    - 'edit': Editing an existing card (UID read-only)
    """

    def __init__(
        self,
        parent=None,
        mode: str = "new",
        uid: str = "",
        name: str = "",
        key_data: Dict[str, Any] = None,
        title: str = None,
        description: str = None,
    ):
        """
        Initialize the card entry dialog.

        Args:
            parent: Parent widget
            mode: 'new' or 'edit'
            uid: Card UID
            name: Card name
            key_data: Key data dict with either:
                - {"key": "..."} for single key mode
                - {"enc_key": "...", "mac_key": "...", "dek_key": "..."} for separate keys
            title: Dialog title override
            description: Description text to show
        """
        super().__init__(parent)

        self.mode = mode
        self._uid = uid
        self._original_name = name
        self._key_data = key_data or {}

        # Determine if we have separate keys
        self._has_separate_keys = "enc_key" in self._key_data

        # Set title based on mode
        if title:
            self.setWindowTitle(title)
        elif mode == "new":
            self.setWindowTitle("New Card Detected")
        else:
            self.setWindowTitle("Edit Card")

        self.setMinimumWidth(500)
        self._setup_ui(description)

    def _setup_ui(self, description: str = None):
        layout = QVBoxLayout(self)

        # Description (if provided)
        if description:
            desc_label = QLabel(description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: #666; margin-bottom: 10px;")
            layout.addWidget(desc_label)

        # Form layout for basic fields
        form = QFormLayout()

        # UID field (read-only)
        self._uid_input = QLineEdit()
        self._uid_input.setText(self._uid)
        self._uid_input.setReadOnly(True)
        self._uid_input.setStyleSheet("background-color: #f0f0f0;")
        form.addRow("UID:", self._uid_input)

        # Name field
        self._name_input = QLineEdit()
        self._name_input.setText(self._original_name)
        self._name_input.setPlaceholderText("Enter a name for this card")
        form.addRow("Name:", self._name_input)

        layout.addLayout(form)

        # Key mode selection
        self._use_separate_keys = QCheckBox("Use separate ENC/MAC/DEK keys (SCP03)")
        self._use_separate_keys.setChecked(self._has_separate_keys)
        self._use_separate_keys.toggled.connect(self._on_key_mode_changed)
        layout.addWidget(self._use_separate_keys)

        # Single key section
        self._single_key_group = QGroupBox("Key")
        single_layout = QFormLayout(self._single_key_group)

        self._key_input = HexLineEdit()
        if not self._has_separate_keys:
            self._key_input.setText(self._key_data.get("key", ""))
        self._key_input.textChanged.connect(self._validate_keys)
        single_layout.addRow("Key:", self._key_input)

        self._single_validation = QLabel()
        self._single_validation.setStyleSheet("color: #666; font-size: 11px;")
        single_layout.addRow("", self._single_validation)

        layout.addWidget(self._single_key_group)

        # Separate keys section
        self._separate_keys_group = QGroupBox("Separate Keys")
        sep_layout = QFormLayout(self._separate_keys_group)

        self._enc_input = HexLineEdit()
        self._enc_input.setText(self._key_data.get("enc_key", ""))
        self._enc_input.textChanged.connect(self._validate_keys)
        self._enc_input.textChanged.connect(self._sync_keys_if_needed)
        sep_layout.addRow("ENC Key:", self._enc_input)

        self._mac_input = HexLineEdit()
        self._mac_input.setText(self._key_data.get("mac_key", ""))
        self._mac_input.textChanged.connect(self._validate_keys)
        sep_layout.addRow("MAC Key:", self._mac_input)

        self._dek_input = HexLineEdit()
        self._dek_input.setText(self._key_data.get("dek_key", ""))
        self._dek_input.textChanged.connect(self._validate_keys)
        sep_layout.addRow("DEK Key:", self._dek_input)

        # Use same key checkbox
        self._use_same_key = QCheckBox("Use same key for all three")
        self._use_same_key.toggled.connect(self._on_use_same_key_toggled)
        sep_layout.addRow("", self._use_same_key)

        self._separate_validation = QLabel()
        self._separate_validation.setStyleSheet("color: #666; font-size: 11px;")
        sep_layout.addRow("", self._separate_validation)

        layout.addWidget(self._separate_keys_group)

        # Validation summary
        self._validation_label = QLabel()
        self._validation_label.setStyleSheet("font-size: 11px;")
        layout.addWidget(self._validation_label)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        self._save_btn = QPushButton("Save")
        self._save_btn.setDefault(True)
        self._save_btn.clicked.connect(self._on_save)
        button_layout.addWidget(self._save_btn)

        layout.addLayout(button_layout)

        # Initial state
        self._on_key_mode_changed(self._has_separate_keys)
        self._validate_keys()

    def _on_key_mode_changed(self, use_separate: bool):
        """Handle switch between single and separate key modes."""
        self._single_key_group.setVisible(not use_separate)
        self._separate_keys_group.setVisible(use_separate)
        self._validate_keys()
        self.adjustSize()

    def _on_use_same_key_toggled(self, checked: bool):
        """Handle 'use same key' checkbox."""
        self._mac_input.setEnabled(not checked)
        self._dek_input.setEnabled(not checked)

        if checked:
            enc_key = self._enc_input.text()
            self._mac_input.setText(enc_key)
            self._dek_input.setText(enc_key)

    def _sync_keys_if_needed(self):
        """Sync MAC/DEK to ENC if 'use same key' is checked."""
        if self._use_same_key.isChecked():
            enc_key = self._enc_input.text()
            self._mac_input.blockSignals(True)
            self._dek_input.blockSignals(True)
            self._mac_input.setText(enc_key)
            self._dek_input.setText(enc_key)
            self._mac_input.blockSignals(False)
            self._dek_input.blockSignals(False)

    def _validate_key_input(self, input_widget: HexLineEdit) -> tuple:
        """Validate a single key input. Returns (is_valid, message)."""
        byte_count = input_widget.get_byte_count()
        hex_text = input_widget.get_clean_hex()

        if not hex_text:
            return False, "Enter a hex key"

        if len(hex_text) % 2 != 0:
            return False, "Incomplete byte"

        if byte_count not in VALID_KEY_LENGTHS:
            return False, f"Invalid length ({byte_count} bytes)"

        return True, f"Valid ({byte_count} bytes)"

    def _validate_keys(self):
        """Validate all key inputs and update UI."""
        if self._use_separate_keys.isChecked():
            # Validate separate keys
            enc_valid, enc_msg = self._validate_key_input(self._enc_input)
            mac_valid, mac_msg = self._validate_key_input(self._mac_input)
            dek_valid, dek_msg = self._validate_key_input(self._dek_input)

            all_valid = enc_valid and mac_valid and dek_valid

            # Check that all keys have same length
            if all_valid:
                enc_len = self._enc_input.get_byte_count()
                mac_len = self._mac_input.get_byte_count()
                dek_len = self._dek_input.get_byte_count()

                if not (enc_len == mac_len == dek_len):
                    all_valid = False
                    self._separate_validation.setText("All keys must have the same length")
                    self._separate_validation.setStyleSheet("color: #f44336; font-size: 11px;")
                else:
                    self._separate_validation.setText(f"All keys valid ({enc_len} bytes each)")
                    self._separate_validation.setStyleSheet("color: #4caf50; font-size: 11px;")
            else:
                messages = []
                if not enc_valid:
                    messages.append(f"ENC: {enc_msg}")
                if not mac_valid:
                    messages.append(f"MAC: {mac_msg}")
                if not dek_valid:
                    messages.append(f"DEK: {dek_msg}")
                self._separate_validation.setText("; ".join(messages))
                self._separate_validation.setStyleSheet("color: #f44336; font-size: 11px;")

            self._save_btn.setEnabled(all_valid)
            self._validation_label.setText("")
        else:
            # Validate single key
            valid, msg = self._validate_key_input(self._key_input)

            if valid:
                self._single_validation.setText(msg)
                self._single_validation.setStyleSheet("color: #4caf50; font-size: 11px;")
            else:
                self._single_validation.setText(msg)
                self._single_validation.setStyleSheet("color: #f44336; font-size: 11px;")

            self._save_btn.setEnabled(valid)
            self._validation_label.setText("")

    def _on_save(self):
        """Validate and accept."""
        self._validate_keys()
        if self._save_btn.isEnabled():
            self.accept()

    def get_results(self) -> Dict[str, Any]:
        """Get the entered values."""
        result = {
            "uid": self._uid,
            "name": self._name_input.text().strip(),
        }

        if self._use_separate_keys.isChecked():
            result["enc_key"] = self._enc_input.get_clean_hex()
            result["mac_key"] = self._mac_input.get_clean_hex()
            result["dek_key"] = self._dek_input.get_clean_hex()
        else:
            result["key"] = self._key_input.get_clean_hex()

        return result


class StorageBrowserDialog(QDialog):
    """
    Dialog for browsing and managing stored card entries.

    Features:
    - View all stored cards with name, UID, and key
    - Toggle key visibility per row
    - Edit card entries (supports both single and separate keys)
    - Delete card entries
    """

    # Signals for actions that need to persist
    card_edited = pyqtSignal(str, dict)  # uid, key_data (includes name)
    card_deleted = pyqtSignal(str)  # uid

    def __init__(
        self,
        parent=None,
        cards: List[Dict[str, Any]] = None,
        title: str = "Stored Cards",
    ):
        """
        Initialize the storage browser dialog.

        Args:
            parent: Parent widget
            cards: List of card dicts with 'uid', 'name', and key data
            title: Dialog title
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(650)
        self.setMinimumHeight(400)

        self._cards = cards or []
        self._key_visible = {}  # uid -> bool

        self._setup_ui()
        self._populate_table()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(4)
        self._table.setHorizontalHeaderLabels(["Name", "UID", "Key(s)", ""])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.selectionModel().selectionChanged.connect(self._on_selection_changed)

        # Column sizing
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)  # Name
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # UID
        header.setSectionResizeMode(2, QHeaderView.Stretch)  # Key
        header.setSectionResizeMode(3, QHeaderView.Fixed)  # Toggle button
        self._table.setColumnWidth(3, 50)

        layout.addWidget(self._table)

        # Empty state label
        self._empty_label = QLabel("No cards stored yet.")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.setStyleSheet("color: #666; font-style: italic;")
        self._empty_label.hide()
        layout.addWidget(self._empty_label)

        # Button row
        button_layout = QHBoxLayout()

        self._edit_btn = QPushButton("Edit...")
        self._edit_btn.setEnabled(False)
        self._edit_btn.clicked.connect(self._on_edit)
        button_layout.addWidget(self._edit_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setEnabled(False)
        self._delete_btn.clicked.connect(self._on_delete)
        button_layout.addWidget(self._delete_btn)

        button_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)

        layout.addLayout(button_layout)

    def _populate_table(self):
        """Populate the table with card data."""
        self._table.setRowCount(0)

        if not self._cards:
            self._table.hide()
            self._empty_label.show()
            return

        self._table.show()
        self._empty_label.hide()

        for card in self._cards:
            self._add_card_row(card)

    def _add_card_row(self, card: Dict[str, Any]):
        """Add a row for a card."""
        row = self._table.rowCount()
        self._table.insertRow(row)

        uid = card.get("uid", "")
        name = card.get("name", "")

        # Initialize visibility state
        self._key_visible[uid] = False

        # Name
        name_item = QTableWidgetItem(name or "(unnamed)")
        name_item.setData(Qt.UserRole, uid)  # Store UID for reference
        self._table.setItem(row, 0, name_item)

        # UID
        uid_item = QTableWidgetItem(uid)
        self._table.setItem(row, 1, uid_item)

        # Key display (masked)
        key_display = self._get_key_display(card, masked=True)
        key_item = QTableWidgetItem(key_display)
        key_item.setData(Qt.UserRole, card)  # Store full card data
        self._table.setItem(row, 2, key_item)

        # Toggle button
        toggle_btn = QPushButton("Show")
        toggle_btn.setFixedWidth(50)
        toggle_btn.clicked.connect(lambda checked, r=row, u=uid: self._toggle_key_visibility(r, u))
        self._table.setCellWidget(row, 3, toggle_btn)

    def _get_key_display(self, card: Dict[str, Any], masked: bool = True) -> str:
        """Get display string for card keys."""
        has_separate = "enc_key" in card

        if has_separate:
            enc = card.get("enc_key", "")
            mac = card.get("mac_key", "")
            dek = card.get("dek_key", "")

            if masked:
                return "ENC/MAC/DEK: •••••••••"
            else:
                # Show abbreviated keys
                enc_disp = self._abbreviate_key(enc)
                mac_disp = self._abbreviate_key(mac)
                dek_disp = self._abbreviate_key(dek)
                return f"ENC:{enc_disp} MAC:{mac_disp} DEK:{dek_disp}"
        else:
            key = card.get("key", "")
            if masked:
                return "•" * min(16, max(8, len(key))) if key else "(no key)"
            else:
                return self._abbreviate_key(key) if key else "(no key)"

    def _abbreviate_key(self, key: str) -> str:
        """Abbreviate a key for display."""
        if not key:
            return "(none)"
        if len(key) > 20:
            return f"{key[:8]}...{key[-8:]}"
        return key

    def _toggle_key_visibility(self, row: int, uid: str):
        """Toggle key visibility for a row."""
        self._key_visible[uid] = not self._key_visible[uid]

        key_item = self._table.item(row, 2)
        card = key_item.data(Qt.UserRole)
        toggle_btn = self._table.cellWidget(row, 3)

        if self._key_visible[uid]:
            key_item.setText(self._get_key_display(card, masked=False))
            toggle_btn.setText("Hide")
        else:
            key_item.setText(self._get_key_display(card, masked=True))
            toggle_btn.setText("Show")

    def _on_selection_changed(self):
        """Handle selection changes."""
        has_selection = len(self._table.selectedItems()) > 0
        self._edit_btn.setEnabled(has_selection)
        self._delete_btn.setEnabled(has_selection)

    def _get_selected_card(self) -> Optional[Dict[str, Any]]:
        """Get the currently selected card data."""
        selected = self._table.selectedItems()
        if not selected:
            return None

        row = selected[0].row()
        uid = self._table.item(row, 0).data(Qt.UserRole)
        name = self._table.item(row, 0).text()
        if name == "(unnamed)":
            name = ""

        # Get full card data from key column
        card = self._table.item(row, 2).data(Qt.UserRole)
        card["row"] = row
        card["name"] = name  # May have been updated

        return card

    def _on_edit(self):
        """Handle edit button click."""
        card = self._get_selected_card()
        if not card:
            return

        # Prepare key_data for dialog
        key_data = {}
        if "enc_key" in card:
            key_data["enc_key"] = card.get("enc_key", "")
            key_data["mac_key"] = card.get("mac_key", "")
            key_data["dek_key"] = card.get("dek_key", "")
        else:
            key_data["key"] = card.get("key", "")

        dialog = CardEntryDialog(
            parent=self,
            mode="edit",
            uid=card["uid"],
            name=card["name"],
            key_data=key_data,
        )

        if dialog.exec_() == QDialog.Accepted:
            result = dialog.get_results()
            row = card["row"]

            # Update table
            name = result.get("name", "") or "(unnamed)"
            self._table.item(row, 0).setText(name)

            # Build updated card data
            updated_card = {"uid": result["uid"], "name": result.get("name", "")}
            if "enc_key" in result:
                updated_card["enc_key"] = result["enc_key"]
                updated_card["mac_key"] = result["mac_key"]
                updated_card["dek_key"] = result["dek_key"]
            else:
                updated_card["key"] = result.get("key", "")

            # Update key display
            self._table.item(row, 2).setData(Qt.UserRole, updated_card)
            if self._key_visible.get(card["uid"], False):
                self._table.item(row, 2).setText(self._get_key_display(updated_card, masked=False))
            else:
                self._table.item(row, 2).setText(self._get_key_display(updated_card, masked=True))

            # Update internal data
            for i, c in enumerate(self._cards):
                if c.get("uid") == card["uid"]:
                    self._cards[i] = updated_card
                    break

            # Emit signal for persistence
            self.card_edited.emit(result["uid"], result)

    def _on_delete(self):
        """Handle delete button click."""
        card = self._get_selected_card()
        if not card:
            return

        # Confirmation
        name_display = card.get("name") or card["uid"]
        result = QMessageBox.question(
            self,
            "Delete Card",
            f"Are you sure you want to delete '{name_display}'?\n\n"
            "This will remove the stored key(s) for this card.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if result != QMessageBox.Yes:
            return

        # Remove from table
        self._table.removeRow(card["row"])

        # Remove from internal data
        self._cards = [c for c in self._cards if c.get("uid") != card["uid"]]

        # Remove visibility state
        self._key_visible.pop(card["uid"], None)

        # Show empty state if no cards left
        if not self._cards:
            self._table.hide()
            self._empty_label.show()

        # Emit signal for persistence
        self.card_deleted.emit(card["uid"])

    def get_cards(self) -> List[Dict[str, Any]]:
        """Get the current list of cards (after any edits/deletes)."""
        return self._cards
