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
)


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
        from PyQt5.QtWidgets import QInputDialog
        text, ok = QInputDialog.getText(
            self,
            "Add Exclusion",
            "Enter CAP filename:",
            QLineEdit.Normal,
            "*.cap",
        )
        if ok and text:
            self._exclusion_list.addItem(text.strip())

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
                f"Multiple CAP files selected: {', '.join(cap_names)}\n"
                "Configure metadata for the primary applet below. "
                "Each CAP will be available as a separate install option."
            )
            self._caps_info_label.show()
        else:
            self._caps_info_label.hide()

        # Load existing metadata (for editing)
        applet_name = wizard.get_plugin_value("applet.metadata.name", "")
        if applet_name and not self._name_edit.text():
            self._name_edit.setText(applet_name)
        elif not self._name_edit.text():
            # Fall back to plugin name
            plugin_name = wizard.get_plugin_value("plugin.name", "")
            if plugin_name:
                self._name_edit.setText(plugin_name.replace("-", " ").title())

        # Load AID
        aid = wizard.get_plugin_value("applet.metadata.aid", "")
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

        # AID
        aid = self._aid_edit.text().replace(" ", "").upper()
        if len(aid) >= 10 and len(aid) <= 32 and len(aid) % 2 == 0:
            wizard.set_plugin_data("applet.metadata.aid", aid)
        else:
            return False  # Invalid AID

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
