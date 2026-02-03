"""
Manage Tags Dialog

Allows users to view, edit, and delete stored card/tag information.
"""

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QMessageBox,
    QAbstractItemView,
    QMenu,
)


class ManageTagsDialog(QDialog):
    """Dialog for managing stored tags/cards."""

    def __init__(self, secure_storage: dict, config: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manage Known Tags")
        self.setMinimumSize(600, 400)

        self._secure_storage = secure_storage
        self._config = config
        self._modified = False

        self._setup_ui()
        self._load_tags()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Info label
        info = QLabel(
            "View and manage your stored cards. "
            "Changes are saved when you click OK."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; margin-bottom: 8px;")
        layout.addWidget(info)

        # Table of tags
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Card ID", "UID", "Name", "Has Key", "Key Type"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        layout.addWidget(self._table)

        # Buttons row
        btn_layout = QHBoxLayout()

        rename_btn = QPushButton("Rename")
        rename_btn.clicked.connect(self._rename_selected)
        btn_layout.addWidget(rename_btn)

        delete_btn = QPushButton("Delete")
        delete_btn.clicked.connect(self._delete_selected)
        btn_layout.addWidget(delete_btn)

        clear_key_btn = QPushButton("Clear Key")
        clear_key_btn.setToolTip("Remove stored key for selected tag")
        clear_key_btn.clicked.connect(self._clear_key_selected)
        btn_layout.addWidget(clear_key_btn)

        btn_layout.addStretch()

        # OK/Cancel buttons
        ok_btn = QPushButton("OK")
        ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(ok_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

    def _load_tags(self):
        """Load tags from secure storage into table."""
        self._table.setRowCount(0)

        if not self._secure_storage:
            return

        tags = self._secure_storage.get("tags", {})
        self._table.setRowCount(len(tags))

        for row, (card_id, tag_data) in enumerate(tags.items()):
            # Card ID (read-only)
            id_item = QTableWidgetItem(card_id)
            id_item.setFlags(id_item.flags() & ~Qt.ItemIsEditable)
            id_item.setData(Qt.UserRole, card_id)  # Store original ID
            self._table.setItem(row, 0, id_item)

            # UID (read-only) - shows original UID if card_id is CPLC-based
            uid = tag_data.get("uid", "")
            uid_item = QTableWidgetItem(uid if uid else "-")
            uid_item.setFlags(uid_item.flags() & ~Qt.ItemIsEditable)
            if uid:
                uid_item.setToolTip(f"Original card UID: {uid}")
            else:
                uid_item.setForeground(Qt.gray)
            self._table.setItem(row, 1, uid_item)

            # Name (editable)
            name = tag_data.get("name", card_id)
            name_item = QTableWidgetItem(name)
            self._table.setItem(row, 2, name_item)

            # Has Key
            key = tag_data.get("key")
            has_key = "Yes" if key else "No"
            key_item = QTableWidgetItem(has_key)
            key_item.setFlags(key_item.flags() & ~Qt.ItemIsEditable)
            if key:
                key_item.setForeground(Qt.darkGreen)
            else:
                key_item.setForeground(Qt.gray)
            self._table.setItem(row, 3, key_item)

            # Key Type
            key_config = tag_data.get("key_config")
            if key_config:
                key_type = key_config.get("key_type", "Unknown")
                mode = key_config.get("mode", "single")
                if mode == "separate":
                    key_type += " (SCP03)"
            elif key:
                # Infer from key length
                key_len = len(key) // 2  # hex chars to bytes
                if key_len == 16:
                    key_type = "3DES/AES-128"
                elif key_len == 24:
                    key_type = "3DES-192/AES-192"
                elif key_len == 32:
                    key_type = "AES-256"
                else:
                    key_type = f"{key_len} bytes"
            else:
                key_type = "-"

            type_item = QTableWidgetItem(key_type)
            type_item.setFlags(type_item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(row, 4, type_item)

        # Connect item changed for tracking modifications
        self._table.itemChanged.connect(self._on_item_changed)

    def _on_item_changed(self, item):
        """Track modifications to table data."""
        if item.column() == 2:  # Name column
            self._modified = True

    def _on_cell_double_clicked(self, row, col):
        """Handle double-click on table cells."""
        if col == 2:  # Name column - allow editing
            self._table.editItem(self._table.item(row, col))

    def _show_context_menu(self, pos):
        """Show context menu for table."""
        item = self._table.itemAt(pos)
        if not item:
            return

        row = item.row()
        self._table.selectRow(row)

        menu = QMenu(self)
        rename_action = menu.addAction("Rename")
        rename_action.triggered.connect(self._rename_selected)

        clear_key_action = menu.addAction("Clear Key")
        clear_key_action.triggered.connect(self._clear_key_selected)

        menu.addSeparator()

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(self._delete_selected)

        menu.exec_(self._table.mapToGlobal(pos))

    def _get_selected_card_id(self) -> Optional[str]:
        """Get the card ID of the selected row."""
        selected = self._table.selectedItems()
        if not selected:
            return None
        row = selected[0].row()
        id_item = self._table.item(row, 0)
        return id_item.data(Qt.UserRole) if id_item else None

    def _rename_selected(self):
        """Rename the selected tag."""
        selected = self._table.selectedItems()
        if not selected:
            QMessageBox.information(self, "No Selection", "Please select a tag to rename.")
            return

        row = selected[0].row()
        name_item = self._table.item(row, 2)
        if name_item:
            self._table.editItem(name_item)

    def _delete_selected(self):
        """Delete the selected tag."""
        card_id = self._get_selected_card_id()
        if not card_id:
            QMessageBox.information(self, "No Selection", "Please select a tag to delete.")
            return

        # Get display name
        tags = self._secure_storage.get("tags", {})
        tag_data = tags.get(card_id, {})
        name = tag_data.get("name", card_id)

        reply = QMessageBox.warning(
            self,
            "Confirm Delete",
            f"Delete tag '{name}'?\n\n"
            "This will remove the stored name and key for this card.\n"
            "This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            # Get the UID before deleting (needed for cleaning up config)
            uid = tag_data.get("uid", "")

            # Remove from internal data
            if card_id in tags:
                del tags[card_id]
                self._modified = True

            # Also remove from config known_tags - by BOTH card_id AND uid
            # This is critical: on initial detection, the system looks up by UID
            # before CPLC is retrieved, so we must clean up both entries
            known_tags = self._config.get("known_tags", {})
            if card_id in known_tags:
                del known_tags[card_id]
            if uid and uid in known_tags:
                del known_tags[uid]

            # Reload table
            self._table.itemChanged.disconnect(self._on_item_changed)
            self._load_tags()

    def _clear_key_selected(self):
        """Clear the key for the selected tag."""
        card_id = self._get_selected_card_id()
        if not card_id:
            QMessageBox.information(self, "No Selection", "Please select a tag.")
            return

        tags = self._secure_storage.get("tags", {})
        tag_data = tags.get(card_id, {})

        if not tag_data.get("key"):
            QMessageBox.information(self, "No Key", "This tag has no stored key.")
            return

        name = tag_data.get("name", card_id)
        reply = QMessageBox.warning(
            self,
            "Clear Key",
            f"Clear the stored key for '{name}'?\n\n"
            "You will need to re-enter the key the next time you use this card.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            # Get UID before modifying
            uid = tag_data.get("uid", "")

            tag_data["key"] = None
            if "key_config" in tag_data:
                del tag_data["key_config"]
            self._modified = True

            # Update config to mark as unknown key - BOTH card_id AND uid
            # This is critical: on initial detection, the system looks up by UID
            known_tags = self._config.get("known_tags", {})
            if card_id in known_tags:
                known_tags[card_id] = None
            if uid and uid in known_tags:
                known_tags[uid] = None

            # Reload table
            self._table.itemChanged.disconnect(self._on_item_changed)
            self._load_tags()

    def get_modified_data(self) -> tuple[dict, dict, bool]:
        """
        Get the modified storage data.

        Returns:
            Tuple of (secure_storage, config, was_modified)
        """
        if not self._modified:
            return self._secure_storage, self._config, False

        # Apply any pending name changes from table
        tags = self._secure_storage.get("tags", {})
        for row in range(self._table.rowCount()):
            id_item = self._table.item(row, 0)
            name_item = self._table.item(row, 2)
            if id_item and name_item:
                card_id = id_item.data(Qt.UserRole)
                new_name = name_item.text().strip()
                if card_id in tags and new_name:
                    tags[card_id]["name"] = new_name

        return self._secure_storage, self._config, True

    def was_modified(self) -> bool:
        """Check if any data was modified."""
        return self._modified
