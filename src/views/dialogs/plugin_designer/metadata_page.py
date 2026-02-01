"""
Metadata Configuration Page

Configures applet metadata including AID, storage, and mutual exclusions.
"""

import re
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QGroupBox,
    QFormLayout,
    QCheckBox,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QMessageBox,
    QDialog,
    QDialogButtonBox,
    QRadioButton,
    QComboBox,
)


# Well-known applets with their AIDs for mutual exclusion selection
KNOWN_APPLETS = [
    ("OpenJavaCard NDEF (Full)", "D2760000850101", "openjavacard-ndef-full.cap"),
    ("OpenJavaCard NDEF (Tiny)", "D2760000850101", "openjavacard-ndef-tiny.cap"),
    ("SmartPGP", "D276000124010304000A000000000000", "SmartPGPApplet-default.cap"),
    ("SatoChip", "5361746F4368697000", "SatoChip.cap"),
    ("SeedKeeper", "536565644B656570657200", "SeedKeeper.cap"),
    ("U2F Applet", "A0000006472F0002", "U2FApplet.cap"),
    ("FIDO2", "A0000006472F000101", "FIDO2.cap"),
    ("YubiKey HMAC", "A000000527200101", "YkHMACApplet.cap"),
    ("VivoKey OTP", "A0000005272101014150455801", "vivokey-otp.cap"),
    ("JavaCard Memory", "A0000008466D656D6F727901", "javacard-memory.cap"),
    ("Keycard", "A0000008040001", "keycard.cap"),
]


class MutualExclusionDialog(QDialog):
    """Dialog for adding a mutual exclusion entry."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Mutual Exclusion")
        self.setMinimumWidth(450)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Selection mode
        layout.addWidget(QLabel("Exclude applet by:"))

        self._known_radio = QRadioButton("Known Applet")
        self._known_radio.setChecked(True)
        self._known_radio.toggled.connect(self._on_mode_changed)
        layout.addWidget(self._known_radio)

        # Known applet dropdown
        self._known_combo = QComboBox()
        for name, aid, cap in KNOWN_APPLETS:
            self._known_combo.addItem(f"{name} ({cap})", (name, aid, cap))
        layout.addWidget(self._known_combo)

        self._cap_radio = QRadioButton("CAP Filename Pattern")
        self._cap_radio.toggled.connect(self._on_mode_changed)
        layout.addWidget(self._cap_radio)

        # CAP pattern input
        self._cap_edit = QLineEdit()
        self._cap_edit.setPlaceholderText("e.g., *.cap or specific-app.cap")
        self._cap_edit.setEnabled(False)
        layout.addWidget(self._cap_edit)

        self._aid_radio = QRadioButton("Custom AID")
        self._aid_radio.toggled.connect(self._on_mode_changed)
        layout.addWidget(self._aid_radio)

        # AID input
        self._aid_edit = QLineEdit()
        self._aid_edit.setPlaceholderText("e.g., D276000124010304")
        self._aid_edit.setEnabled(False)
        layout.addWidget(self._aid_edit)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_mode_changed(self):
        """Update UI based on selected mode."""
        self._known_combo.setEnabled(self._known_radio.isChecked())
        self._cap_edit.setEnabled(self._cap_radio.isChecked())
        self._aid_edit.setEnabled(self._aid_radio.isChecked())

    def get_result(self) -> str:
        """Get the exclusion entry string."""
        if self._known_radio.isChecked():
            data = self._known_combo.currentData()
            if data:
                name, aid, cap = data
                return cap  # Return CAP filename for exclusion
        elif self._cap_radio.isChecked():
            cap = self._cap_edit.text().strip()
            return cap if cap else ""
        elif self._aid_radio.isChecked():
            aid = self._aid_edit.text().strip().upper().replace(" ", "")
            return aid if aid else ""
        return ""


class MetadataPage(QWizardPage):
    """Configure applet metadata."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Applet Metadata")
        self.setSubTitle("Configure the applet identifier, storage, and other metadata.")

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Info label for multiple CAPs (hidden by default)
        self._caps_info_label = QLabel("")
        self._caps_info_label.setStyleSheet("background-color: #e3f2fd; padding: 8px; border-radius: 4px;")
        self._caps_info_label.setWordWrap(True)
        self._caps_info_label.hide()
        layout.addWidget(self._caps_info_label)

        # Applet Name
        layout.addWidget(QLabel("Applet Display Name:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g., My Applet")
        layout.addWidget(self._name_edit)

        # AID Section
        aid_group = QGroupBox("Application Identifier (AID)")
        aid_layout = QVBoxLayout(aid_group)

        aid_layout.addWidget(QLabel("AID (5-16 bytes in hex):"))
        self._aid_edit = QLineEdit()
        self._aid_edit.setPlaceholderText("e.g., D276000124010304")
        self._aid_edit.textChanged.connect(self._validate_aid)
        aid_layout.addWidget(self._aid_edit)

        self._aid_status = QLabel("")
        self._aid_status.setStyleSheet("color: gray;")
        aid_layout.addWidget(self._aid_status)

        layout.addWidget(aid_group)

        # Storage Requirements
        storage_group = QGroupBox("Storage Requirements (optional)")
        storage_layout = QFormLayout(storage_group)

        self._persistent_spin = QSpinBox()
        self._persistent_spin.setRange(0, 1000000)
        self._persistent_spin.setSuffix(" bytes")
        self._persistent_spin.setValue(0)
        storage_layout.addRow("Persistent:", self._persistent_spin)

        self._transient_spin = QSpinBox()
        self._transient_spin.setRange(0, 100000)
        self._transient_spin.setSuffix(" bytes")
        self._transient_spin.setValue(0)
        storage_layout.addRow("Transient:", self._transient_spin)

        layout.addWidget(storage_group)

        # Mutual Exclusions
        exclusion_group = QGroupBox("Mutual Exclusions (optional)")
        exclusion_layout = QVBoxLayout(exclusion_group)

        exclusion_layout.addWidget(QLabel("CAP files that conflict with this applet:"))

        self._exclusion_list = QListWidget()
        self._exclusion_list.setMaximumHeight(100)
        exclusion_layout.addWidget(self._exclusion_list)

        btn_layout = QHBoxLayout()
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_exclusion)
        btn_layout.addWidget(add_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_exclusion)
        btn_layout.addWidget(remove_btn)

        btn_layout.addStretch()
        exclusion_layout.addLayout(btn_layout)

        layout.addWidget(exclusion_group)

        layout.addStretch()

    def _validate_aid(self, text: str):
        """Validate AID input."""
        aid = text.replace(" ", "").upper()

        # Check if valid hex
        if not re.match(r'^[0-9A-F]*$', aid):
            self._aid_status.setText("Invalid: contains non-hex characters")
            self._aid_status.setStyleSheet("color: red;")
            return

        # Check length (5-16 bytes = 10-32 hex chars)
        if len(aid) == 0:
            self._aid_status.setText("AID required")
            self._aid_status.setStyleSheet("color: gray;")
        elif len(aid) % 2 != 0:
            self._aid_status.setText(f"Invalid: odd number of characters ({len(aid)})")
            self._aid_status.setStyleSheet("color: red;")
        elif len(aid) < 10:
            self._aid_status.setText(f"Too short: {len(aid)//2} bytes (minimum 5)")
            self._aid_status.setStyleSheet("color: red;")
        elif len(aid) > 32:
            self._aid_status.setText(f"Too long: {len(aid)//2} bytes (maximum 16)")
            self._aid_status.setStyleSheet("color: red;")
        else:
            self._aid_status.setText(f"Valid AID: {len(aid)//2} bytes")
            self._aid_status.setStyleSheet("color: green;")

    def _add_exclusion(self):
        """Add a mutual exclusion."""
        dialog = MutualExclusionDialog(self)
        if dialog.exec_() == 1:  # QDialog.Accepted
            result = dialog.get_result()
            if result:
                self._exclusion_list.addItem(result)

    def _remove_exclusion(self):
        """Remove selected exclusion."""
        current = self._exclusion_list.currentItem()
        if current:
            self._exclusion_list.takeItem(self._exclusion_list.row(current))

    def initializePage(self):
        """Initialize with data from wizard."""
        wizard = self.wizard()
        if not wizard:
            return

        # Check for multiple selected CAPs
        selected_caps = wizard.get_plugin_value("_selected_caps", [])
        if len(selected_caps) > 1:
            cap_names = [cap["filename"] for cap in selected_caps]
            self._caps_info_label.setText(
                f"Multiple CAP files selected: {', '.join(cap_names)}\n\n"
                "Configure shared metadata here. On the next page, you can "
                "set individual display names for each variant."
            )
            self._caps_info_label.show()
        else:
            self._caps_info_label.hide()

        # Load existing metadata (for editing)
        applet_name = wizard.get_plugin_value("applet.metadata.name", "")
        if applet_name and not self._name_edit.text():
            self._name_edit.setText(applet_name)
        elif not self._name_edit.text():
            # Try to get name from CAP metadata or filename
            name_found = False

            # Check extracted metadata for package name
            extracted = wizard.get_plugin_value("_extracted_metadata")
            if extracted and extracted.package_name:
                # Convert package name to display name (e.g., "org.example.MyApplet" -> "My Applet")
                pkg_parts = extracted.package_name.split(".")
                if pkg_parts:
                    # Use last part, add spaces before capitals
                    last_part = pkg_parts[-1]
                    import re
                    display_name = re.sub(r'(?<!^)(?=[A-Z])', ' ', last_part)
                    self._name_edit.setText(display_name)
                    name_found = True

            # Fall back to first selected CAP filename
            if not name_found and selected_caps:
                first_cap = selected_caps[0]
                filename = first_cap.get("filename", "")
                if filename:
                    # Remove .cap extension and convert to display name
                    name = filename.replace(".cap", "").replace("-", " ").replace("_", " ")
                    # Title case but preserve existing caps
                    self._name_edit.setText(name.title())
                    name_found = True

            # Last resort: fall back to plugin name
            if not name_found:
                plugin_name = wizard.get_plugin_value("plugin.name", "")
                if plugin_name:
                    self._name_edit.setText(plugin_name.replace("-", " ").title())

        # Load AID - check for static aid first, then aid_construction.base
        aid = wizard.get_plugin_value("applet.metadata.aid", "")
        if not aid:
            # Fall back to aid_construction.base for dynamic AID plugins
            aid = wizard.get_plugin_value("applet.metadata.aid_construction.base", "")
        if aid and not self._aid_edit.text():
            self._aid_edit.setText(aid)
            self._validate_aid(aid)

        # Load storage
        persistent = wizard.get_plugin_value("applet.metadata.storage.persistent", 0)
        transient = wizard.get_plugin_value("applet.metadata.storage.transient", 0)
        if persistent:
            self._persistent_spin.setValue(persistent)
        if transient:
            self._transient_spin.setValue(transient)

        # Load mutual exclusions
        exclusions = wizard.get_plugin_value("applet.metadata.mutual_exclusion", [])
        if exclusions and self._exclusion_list.count() == 0:
            for excl in exclusions:
                self._exclusion_list.addItem(excl)

        # Try to use extracted CAP metadata (for new plugins)
        extracted = wizard.get_plugin_value("_extracted_metadata")
        if extracted and not self._aid_edit.text():
            if extracted.aid:
                if extracted.applet_aids:
                    self._aid_edit.setText(extracted.applet_aids[0])
                else:
                    self._aid_edit.setText(extracted.aid)
                self._validate_aid(self._aid_edit.text())

    def validatePage(self) -> bool:
        """Validate and save data."""
        wizard = self.wizard()
        if not wizard:
            return True

        # Applet name
        name = self._name_edit.text().strip()
        if name:
            wizard.set_plugin_data("applet.metadata.name", name)

        # AID validation with user feedback
        aid = self._aid_edit.text().replace(" ", "").upper()
        if not aid:
            QMessageBox.warning(
                self,
                "AID Required",
                "Please enter an Application Identifier (AID).\n\n"
                "The AID must be 5-16 bytes (10-32 hex characters).",
            )
            self._aid_edit.setFocus()
            return False

        if not re.match(r'^[0-9A-F]*$', aid):
            QMessageBox.warning(
                self,
                "Invalid AID",
                "The AID contains invalid characters.\n\n"
                "Only hexadecimal characters (0-9, A-F) are allowed.",
            )
            self._aid_edit.setFocus()
            return False

        if len(aid) % 2 != 0:
            QMessageBox.warning(
                self,
                "Invalid AID",
                f"The AID has an odd number of characters ({len(aid)}).\n\n"
                "Each byte requires two hex characters.",
            )
            self._aid_edit.setFocus()
            return False

        if len(aid) < 10:
            QMessageBox.warning(
                self,
                "AID Too Short",
                f"The AID is only {len(aid)//2} bytes.\n\n"
                "The minimum AID length is 5 bytes (10 hex characters).",
            )
            self._aid_edit.setFocus()
            return False

        if len(aid) > 32:
            QMessageBox.warning(
                self,
                "AID Too Long",
                f"The AID is {len(aid)//2} bytes.\n\n"
                "The maximum AID length is 16 bytes (32 hex characters).",
            )
            self._aid_edit.setFocus()
            return False

        wizard.set_plugin_data("applet.metadata.aid", aid)

        # Storage
        persistent = self._persistent_spin.value()
        transient = self._transient_spin.value()
        if persistent > 0 or transient > 0:
            wizard.set_plugin_data("applet.metadata.storage.persistent", persistent)
            wizard.set_plugin_data("applet.metadata.storage.transient", transient)

        # Mutual exclusions
        exclusions = []
        for i in range(self._exclusion_list.count()):
            item = self._exclusion_list.item(i)
            if item:
                exclusions.append(item.text())
        if exclusions:
            wizard.set_plugin_data("applet.metadata.mutual_exclusion", exclusions)

        return True

    def nextId(self) -> int:
        """Determine next page - skip variants page if only one CAP."""
        wizard = self.wizard()
        if not wizard:
            return -1

        # Check if we should show variants page (multiple CAPs selected)
        if wizard._should_show_variants_page():
            return wizard.PAGE_VARIANTS
        else:
            return wizard.PAGE_UI_BUILDER
