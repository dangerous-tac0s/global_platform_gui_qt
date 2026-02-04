"""
Backup-related dialogs for storage export/import functionality.
"""

import subprocess

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QButtonGroup,
    QGroupBox,
    QScrollArea,
    QWidget,
    QCheckBox,
    QFileDialog,
    QMessageBox,
    QComboBox,
)
from PyQt5.QtCore import Qt

from ...utils.colors import Colors


def _get_gpg_keys() -> list:
    """
    Get list of available GPG keys for encryption.

    Only returns keys that have a valid (non-expired, non-revoked) encryption subkey.

    Returns:
        List of tuples: (key_id, display_string)
    """
    import time

    keys = []
    try:
        # Get public keys with colons format
        result = subprocess.run(
            ["gpg", "--list-keys", "--with-colons"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            current_key_id = None
            current_uids = []
            has_valid_encryption_subkey = False
            current_time = int(time.time())

            for line in result.stdout.split('\n'):
                parts = line.split(':')
                if not parts or len(parts) < 2:
                    continue

                record_type = parts[0]
                validity = parts[1] if len(parts) > 1 else ""

                if record_type == 'pub':
                    # Save previous key if it has valid encryption capability
                    if current_key_id and current_uids and has_valid_encryption_subkey:
                        display = f"{current_uids[0]} ({current_key_id[-8:]})"
                        keys.append((current_key_id, display))

                    # Start new key
                    current_key_id = parts[4] if len(parts) > 4 else None
                    current_uids = []
                    has_valid_encryption_subkey = False

                elif record_type == 'sub' and current_key_id:
                    # Check if this subkey can encrypt
                    # Field 11 contains capabilities, 'e' means encrypt
                    capabilities = parts[11] if len(parts) > 11 else ""

                    if 'e' in capabilities.lower():
                        # Check validity - must not be expired/revoked
                        # validity: '-' or 'u' = valid, 'e' = expired, 'r' = revoked
                        if validity not in ('e', 'r', 'n', 'd'):
                            # Also check expiration timestamp (field 6)
                            exp_timestamp = parts[6] if len(parts) > 6 else ""
                            if not exp_timestamp or int(exp_timestamp) > current_time:
                                has_valid_encryption_subkey = True

                elif record_type == 'uid' and current_key_id:
                    # UID field is in position 9
                    if len(parts) > 9 and parts[9]:
                        current_uids.append(parts[9])

            # Don't forget last key
            if current_key_id and current_uids and has_valid_encryption_subkey:
                display = f"{current_uids[0]} ({current_key_id[-8:]})"
                keys.append((current_key_id, display))

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    return keys


class ExportBackupDialog(QDialog):
    """Dialog for configuring backup export settings."""

    def __init__(self, parent=None, gpg_available: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Export Backup")
        self.setMinimumWidth(400)
        self.gpg_available = gpg_available

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Description
        desc_label = QLabel("Choose encryption method for your backup:")
        layout.addWidget(desc_label)

        # Method selection
        method_group = QGroupBox("Encryption Method")
        method_layout = QVBoxLayout(method_group)

        self.method_button_group = QButtonGroup(self)

        # Password option
        self.password_radio = QRadioButton("Password")
        self.password_radio.setChecked(True)
        self.method_button_group.addButton(self.password_radio, 0)
        method_layout.addWidget(self.password_radio)

        password_desc = QLabel("Encrypt with a password you choose")
        password_desc.setStyleSheet(f"color: {Colors.muted_text()}; margin-left: 20px; font-size: 11px;")
        method_layout.addWidget(password_desc)

        # GPG option
        self.gpg_radio = QRadioButton("GPG Key")
        self.gpg_radio.setEnabled(self.gpg_available)
        self.method_button_group.addButton(self.gpg_radio, 1)
        method_layout.addWidget(self.gpg_radio)

        gpg_desc_text = "Encrypt with a GPG public key"
        if not self.gpg_available:
            gpg_desc_text += " (GPG not available)"
        gpg_desc = QLabel(gpg_desc_text)
        gpg_desc.setStyleSheet(f"color: {Colors.muted_text()}; margin-left: 20px; font-size: 11px;")
        method_layout.addWidget(gpg_desc)

        layout.addWidget(method_group)

        # Password fields
        self.password_group = QGroupBox("Password")
        password_layout = QVBoxLayout(self.password_group)

        pw_row = QHBoxLayout()
        pw_row.addWidget(QLabel("Password:"))
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Enter password")
        pw_row.addWidget(self.password_input)
        password_layout.addLayout(pw_row)

        confirm_row = QHBoxLayout()
        confirm_row.addWidget(QLabel("Confirm:"))
        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.Password)
        self.confirm_input.setPlaceholderText("Confirm password")
        confirm_row.addWidget(self.confirm_input)
        password_layout.addLayout(confirm_row)

        layout.addWidget(self.password_group)

        # GPG key field
        self.gpg_group = QGroupBox("GPG Key")
        gpg_layout = QVBoxLayout(self.gpg_group)

        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("Select Key:"))
        self.gpg_key_combo = QComboBox()
        self.gpg_key_combo.setMinimumWidth(300)

        # Populate with available GPG keys
        self._gpg_keys = _get_gpg_keys()
        if self._gpg_keys:
            for key_id, display in self._gpg_keys:
                self.gpg_key_combo.addItem(display, key_id)
        else:
            self.gpg_key_combo.addItem("No GPG keys found", "")
            self.gpg_key_combo.setEnabled(False)

        key_row.addWidget(self.gpg_key_combo)
        gpg_layout.addLayout(key_row)

        self.gpg_group.setVisible(False)
        layout.addWidget(self.gpg_group)

        # Connect radio buttons to show/hide fields
        self.password_radio.toggled.connect(self._on_method_changed)
        self.gpg_radio.toggled.connect(self._on_method_changed)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        self.export_btn = QPushButton("Export...")
        self.export_btn.setDefault(True)
        self.export_btn.clicked.connect(self._on_export)
        button_layout.addWidget(self.export_btn)

        layout.addLayout(button_layout)

    def _on_method_changed(self):
        """Toggle visibility of input fields based on selected method."""
        is_password = self.password_radio.isChecked()
        self.password_group.setVisible(is_password)
        self.gpg_group.setVisible(not is_password)

    def _on_export(self):
        """Validate inputs and accept dialog."""
        if self.password_radio.isChecked():
            password = self.password_input.text()
            confirm = self.confirm_input.text()

            if not password:
                QMessageBox.warning(self, "Error", "Please enter a password.")
                return

            if len(password) < 8:
                QMessageBox.warning(
                    self, "Error", "Password must be at least 8 characters."
                )
                return

            if password != confirm:
                QMessageBox.warning(self, "Error", "Passwords do not match.")
                return

        else:  # GPG
            key_id = self.gpg_key_combo.currentData()
            if not key_id:
                QMessageBox.warning(self, "Error", "Please select a GPG key.")
                return

        self.accept()

    def get_method(self) -> str:
        """Get selected encryption method."""
        return "password" if self.password_radio.isChecked() else "gpg"

    def get_password(self) -> str:
        """Get entered password (only valid if method is 'password')."""
        return self.password_input.text()

    def get_gpg_key_id(self) -> str:
        """Get selected GPG key ID (only valid if method is 'gpg')."""
        return self.gpg_key_combo.currentData() or ""


class ImportPasswordDialog(QDialog):
    """Dialog for entering password to decrypt a backup."""

    def __init__(self, parent=None, backup_info: dict = None):
        super().__init__(parent)
        self.setWindowTitle("Enter Backup Password")
        self.setMinimumWidth(350)
        self.backup_info = backup_info or {}

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Show backup info if available
        if self.backup_info.get("created"):
            info_label = QLabel(f"Backup created: {self.backup_info['created']}")
            info_label.setStyleSheet("color: gray; font-size: 11px;")
            layout.addWidget(info_label)

        # Password field
        pw_layout = QHBoxLayout()
        pw_layout.addWidget(QLabel("Password:"))
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setPlaceholderText("Enter backup password")
        self.password_input.returnPressed.connect(self.accept)
        pw_layout.addWidget(self.password_input)
        layout.addLayout(pw_layout)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        decrypt_btn = QPushButton("Decrypt")
        decrypt_btn.setDefault(True)
        decrypt_btn.clicked.connect(self.accept)
        button_layout.addWidget(decrypt_btn)

        layout.addLayout(button_layout)

    def get_password(self) -> str:
        """Get entered password."""
        return self.password_input.text()


class ConflictResolutionDialog(QDialog):
    """Dialog for resolving conflicts during backup import."""

    # Resolution options
    KEEP_EXISTING = "keep"
    USE_BACKUP = "backup"
    SKIP = "skip"

    def __init__(self, parent=None, conflicts: list = None):
        """
        Initialize conflict resolution dialog.

        Args:
            parent: Parent widget
            conflicts: List of dicts with 'uid', 'existing_name', 'backup_name' keys
        """
        super().__init__(parent)
        self.setWindowTitle("Import Conflicts")
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)
        self.conflicts = conflicts or []
        self.resolutions = {}

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Description
        desc = QLabel(
            "Some cards in the backup already exist in your storage.\n"
            "Choose how to handle each conflict:"
        )
        layout.addWidget(desc)

        # Scroll area for conflicts
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        self.conflict_widgets = []
        for conflict in self.conflicts:
            widget = self._create_conflict_widget(conflict)
            scroll_layout.addWidget(widget)
            self.conflict_widgets.append(widget)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        # Apply to all checkbox
        self.apply_all_checkbox = QCheckBox("Apply to all remaining conflicts")
        layout.addWidget(self.apply_all_checkbox)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        import_btn = QPushButton("Import")
        import_btn.setDefault(True)
        import_btn.clicked.connect(self.accept)
        button_layout.addWidget(import_btn)

        layout.addLayout(button_layout)

    def _create_conflict_widget(self, conflict: dict) -> QGroupBox:
        """Create a widget for a single conflict."""
        uid = conflict.get("uid", "Unknown")
        existing_name = conflict.get("existing_name", "Unnamed")
        backup_name = conflict.get("backup_name", "Unnamed")

        group = QGroupBox()
        layout = QVBoxLayout(group)

        # Card info
        name_text = existing_name
        if backup_name != existing_name:
            name_text = f"{existing_name} / {backup_name}"
        title = QLabel(f"<b>{name_text}</b> ({uid})")
        layout.addWidget(title)

        # Radio buttons
        btn_layout = QHBoxLayout()
        btn_group = QButtonGroup(group)

        keep_radio = QRadioButton("Keep existing")
        keep_radio.setChecked(True)
        btn_group.addButton(keep_radio, 0)
        btn_layout.addWidget(keep_radio)

        backup_radio = QRadioButton("Use backup")
        btn_group.addButton(backup_radio, 1)
        btn_layout.addWidget(backup_radio)

        skip_radio = QRadioButton("Skip")
        btn_group.addButton(skip_radio, 2)
        btn_layout.addWidget(skip_radio)

        layout.addLayout(btn_layout)

        # Store reference for later
        group.uid = uid
        group.button_group = btn_group

        return group

    def get_resolutions(self) -> dict:
        """
        Get resolution choices for all conflicts.

        Returns:
            Dict mapping uid to resolution ('keep', 'backup', or 'skip')
        """
        resolutions = {}

        for widget in self.conflict_widgets:
            uid = widget.uid
            checked_id = widget.button_group.checkedId()

            if checked_id == 0:
                resolutions[uid] = self.KEEP_EXISTING
            elif checked_id == 1:
                resolutions[uid] = self.USE_BACKUP
            else:
                resolutions[uid] = self.SKIP

        return resolutions


class ChangeEncryptionDialog(QDialog):
    """Dialog for changing the storage encryption method."""

    def __init__(self, parent=None, current_method: str = None, gpg_available: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Change Encryption Method")
        self.setMinimumWidth(450)
        self.current_method = current_method
        self.gpg_available = gpg_available

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Warning
        warning = QLabel(
            "Changing the encryption method will re-encrypt all stored data.\n"
            "Make sure you have a backup before proceeding."
        )
        warning.setStyleSheet(f"color: {Colors.warning_border()}; padding: 10px; background: {Colors.warning_bg()}; border-radius: 4px;")
        layout.addWidget(warning)

        if self.current_method:
            current_label = QLabel(f"Current method: <b>{self.current_method}</b>")
            layout.addWidget(current_label)

        # Method selection
        method_group = QGroupBox("New Encryption Method")
        method_layout = QVBoxLayout(method_group)

        self.method_button_group = QButtonGroup(self)

        # Keyring option
        self.keyring_radio = QRadioButton("System Keyring")
        self.keyring_radio.setChecked(self.current_method != "keyring")
        self.method_button_group.addButton(self.keyring_radio, 0)
        method_layout.addWidget(self.keyring_radio)

        keyring_desc = QLabel("Store encryption key in system keyring (recommended)")
        keyring_desc.setStyleSheet(f"color: {Colors.muted_text()}; margin-left: 20px; font-size: 11px;")
        method_layout.addWidget(keyring_desc)

        # GPG option
        self.gpg_radio = QRadioButton("GPG Key")
        self.gpg_radio.setEnabled(self.gpg_available)
        self.gpg_radio.setChecked(self.current_method == "keyring" and self.gpg_available)
        self.method_button_group.addButton(self.gpg_radio, 1)
        method_layout.addWidget(self.gpg_radio)

        gpg_desc_text = "Encrypt with a GPG key (requires GPG setup)"
        if not self.gpg_available:
            gpg_desc_text += " - GPG not available"
        gpg_desc = QLabel(gpg_desc_text)
        gpg_desc.setStyleSheet(f"color: {Colors.muted_text()}; margin-left: 20px; font-size: 11px;")
        method_layout.addWidget(gpg_desc)

        layout.addWidget(method_group)

        # GPG key field
        self.gpg_group = QGroupBox("GPG Key")
        gpg_layout = QVBoxLayout(self.gpg_group)

        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("Select Key:"))
        self.gpg_key_combo = QComboBox()
        self.gpg_key_combo.setMinimumWidth(300)

        # Populate with available GPG keys
        self._gpg_keys = _get_gpg_keys()
        if self._gpg_keys:
            for key_id, display in self._gpg_keys:
                self.gpg_key_combo.addItem(display, key_id)
        else:
            self.gpg_key_combo.addItem("No GPG keys found", "")
            self.gpg_key_combo.setEnabled(False)

        key_row.addWidget(self.gpg_key_combo)
        gpg_layout.addLayout(key_row)

        self.gpg_group.setVisible(self.gpg_radio.isChecked())
        layout.addWidget(self.gpg_group)

        # Connect radio buttons
        self.gpg_radio.toggled.connect(lambda checked: self.gpg_group.setVisible(checked))

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        change_btn = QPushButton("Change Method")
        change_btn.setDefault(True)
        change_btn.clicked.connect(self._on_change)
        button_layout.addWidget(change_btn)

        layout.addLayout(button_layout)

    def _on_change(self):
        """Validate and accept."""
        if self.gpg_radio.isChecked():
            key_id = self.gpg_key_combo.currentData()
            if not key_id:
                QMessageBox.warning(self, "Error", "Please select a GPG key.")
                return

        # Confirm action
        result = QMessageBox.question(
            self,
            "Confirm Change",
            "Are you sure you want to change the encryption method?\n\n"
            "This will re-encrypt all stored data.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if result == QMessageBox.Yes:
            self.accept()

    def get_method(self) -> str:
        """Get selected method."""
        return "keyring" if self.keyring_radio.isChecked() else "gpg"

    def get_gpg_key_id(self) -> str:
        """Get selected GPG key ID (only valid if method is 'gpg')."""
        return self.gpg_key_combo.currentData() or ""
