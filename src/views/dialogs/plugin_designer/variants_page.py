"""
Applet Variants Configuration Page

Configures metadata for each CAP file variant when multiple CAP files
are selected for a single plugin. Uses a list+detail layout for full
per-variant metadata editing.
"""

import re
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QSpinBox,
    QListWidget,
    QListWidgetItem,
    QGroupBox,
    QCheckBox,
    QSplitter,
    QWidget,
    QMessageBox,
    QPushButton,
    QFrame,
)


class AppletVariantsPage(QWizardPage):
    """Configure full metadata for each CAP variant using list+detail view."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Configure Applet Variants")
        self.setSubTitle(
            "Select each applet from the list and configure its metadata. "
            "All fields are saved when you select a different applet or click Next."
        )

        self._variant_configs = []  # List of variant configurations
        self._current_index = -1  # Currently selected variant index
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Info label
        info_label = QLabel(
            "Configure each applet individually. Select an applet from the list "
            "to edit its display name, AID, storage requirements, and description."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(
            "background-color: #e3f2fd; padding: 10px; border-radius: 4px;"
        )
        layout.addWidget(info_label)

        layout.addSpacing(10)

        # Main splitter: list on left, detail on right
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)  # Prevent collapse on Windows

        # Left panel: variant list
        left_widget = QWidget()
        left_widget.setMinimumWidth(180)  # Prevent collapse
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        left_layout.addWidget(QLabel("<b>Applets:</b>"))

        self._variant_list = QListWidget()
        self._variant_list.setMinimumWidth(150)
        self._variant_list.currentRowChanged.connect(self._on_variant_selected)
        left_layout.addWidget(self._variant_list)

        # Progress indicator
        self._progress_label = QLabel("0 / 0 configured")
        self._progress_label.setStyleSheet("color: gray;")
        left_layout.addWidget(self._progress_label)

        splitter.addWidget(left_widget)

        # Right panel: detail form
        right_widget = QWidget()
        right_widget.setMinimumWidth(350)  # Prevent collapse
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        # Current applet header
        self._detail_header = QLabel("<b>Select an applet to configure</b>")
        self._detail_header.setStyleSheet(
            "background-color: #f5f5f5; padding: 8px; border-radius: 4px;"
        )
        right_layout.addWidget(self._detail_header)

        # Detail form
        detail_group = QGroupBox("Applet Configuration")
        form_layout = QFormLayout(detail_group)

        # Display name
        self._name_edit = QLineEdit()
        self._name_edit.setMinimumWidth(200)  # Prevent collapse on Windows
        self._name_edit.setPlaceholderText("e.g., Satochip")
        self._name_edit.textChanged.connect(self._on_field_changed)
        form_layout.addRow("Display Name:", self._name_edit)

        # AID
        self._aid_edit = QLineEdit()
        self._aid_edit.setMinimumWidth(200)  # Prevent collapse on Windows
        self._aid_edit.setPlaceholderText("e.g., 5361746F4368697000")
        self._aid_edit.textChanged.connect(self._on_aid_changed)
        form_layout.addRow("AID (hex):", self._aid_edit)

        self._aid_status = QLabel("")
        self._aid_status.setStyleSheet("color: gray;")
        form_layout.addRow("", self._aid_status)

        # Storage requirements
        storage_widget = QWidget()
        storage_layout = QHBoxLayout(storage_widget)
        storage_layout.setContentsMargins(0, 0, 0, 0)

        self._persistent_spin = QSpinBox()
        self._persistent_spin.setRange(0, 1000000)
        self._persistent_spin.setSuffix(" bytes")
        self._persistent_spin.valueChanged.connect(self._on_field_changed)
        storage_layout.addWidget(QLabel("Persistent:"))
        storage_layout.addWidget(self._persistent_spin)

        self._transient_spin = QSpinBox()
        self._transient_spin.setRange(0, 100000)
        self._transient_spin.setSuffix(" bytes")
        self._transient_spin.valueChanged.connect(self._on_field_changed)
        storage_layout.addWidget(QLabel("Transient:"))
        storage_layout.addWidget(self._transient_spin)

        storage_layout.addStretch()
        form_layout.addRow("Storage:", storage_widget)

        # Description
        self._desc_edit = QTextEdit()
        self._desc_edit.setPlaceholderText(
            "Optional markdown description for this applet.\n"
            "Supports **bold**, *italic*, [links](url), etc."
        )
        self._desc_edit.setMaximumHeight(150)
        self._desc_edit.textChanged.connect(self._on_field_changed)
        form_layout.addRow("Description:", self._desc_edit)

        right_layout.addWidget(detail_group)
        right_layout.addStretch()

        splitter.addWidget(right_widget)

        # Set splitter proportions (1:2)
        splitter.setSizes([200, 400])

        layout.addWidget(splitter)

        # Options at the bottom
        options_group = QGroupBox("Sharing Options")
        options_layout = QVBoxLayout(options_group)

        self._shared_workflows_check = QCheckBox(
            "Share all workflows across variants (recommended)"
        )
        self._shared_workflows_check.setChecked(True)
        options_layout.addWidget(self._shared_workflows_check)

        self._shared_actions_check = QCheckBox(
            "Share all management actions across variants"
        )
        self._shared_actions_check.setChecked(True)
        options_layout.addWidget(self._shared_actions_check)

        layout.addWidget(options_group)

        # Initially disable detail form
        self._set_detail_enabled(False)

    def _set_detail_enabled(self, enabled: bool):
        """Enable or disable the detail form."""
        self._name_edit.setEnabled(enabled)
        self._aid_edit.setEnabled(enabled)
        self._persistent_spin.setEnabled(enabled)
        self._transient_spin.setEnabled(enabled)
        self._desc_edit.setEnabled(enabled)

    def initializePage(self):
        """Populate list with selected CAP files."""
        wizard = self.wizard()
        if not wizard:
            return

        selected_caps = wizard.get_plugin_value("_selected_caps", [])
        if not selected_caps:
            return

        # Load any existing variant configs
        existing_variants = wizard.get_plugin_value("_variant_configs", [])
        existing_map = {v.get("filename"): v for v in existing_variants}

        # Initialize variant configs list
        self._variant_configs = []

        # Populate list and configs
        self._variant_list.clear()
        for cap_info in selected_caps:
            filename = cap_info.get("filename", "")
            existing = existing_map.get(filename, {})

            # Get display name from existing config or auto-generate
            display_name = existing.get("display_name", "")
            if not display_name:
                display_name = self._filename_to_display_name(filename)

            # Get AID from existing config or cap metadata
            aid = existing.get("aid", "")
            if not aid:
                cap_metadata = cap_info.get("metadata")
                if cap_metadata:
                    if hasattr(cap_metadata, "applet_aids") and cap_metadata.applet_aids:
                        aid = cap_metadata.applet_aids[0]
                    elif hasattr(cap_metadata, "aid") and cap_metadata.aid:
                        aid = cap_metadata.aid

            # Get storage from existing config
            storage = existing.get("storage", {})
            persistent = storage.get("persistent", 0) if isinstance(storage, dict) else 0
            transient = storage.get("transient", 0) if isinstance(storage, dict) else 0

            # Get description from existing config
            description = existing.get("description", "")

            # Store config
            self._variant_configs.append({
                "filename": filename,
                "display_name": display_name,
                "aid": aid,
                "persistent": persistent,
                "transient": transient,
                "description": description,
            })

            # Add to list with status indicator
            item = QListWidgetItem()
            self._update_list_item(item, filename, display_name, aid)
            self._variant_list.addItem(item)

        # Update progress
        self._update_progress()

        # Select first item
        if self._variant_list.count() > 0:
            self._variant_list.setCurrentRow(0)

    def _update_list_item(self, item: QListWidgetItem, filename: str, display_name: str, aid: str):
        """Update list item display with status."""
        status = "✓" if (display_name and aid) else "○"
        item.setText(f"{status} {display_name or filename}")
        item.setToolTip(f"File: {filename}\nAID: {aid or '(not set)'}")

    def _update_progress(self):
        """Update the progress indicator."""
        configured = sum(1 for v in self._variant_configs if v.get("display_name") and v.get("aid"))
        total = len(self._variant_configs)
        self._progress_label.setText(f"{configured} / {total} configured")

        if configured == total:
            self._progress_label.setStyleSheet("color: green;")
        else:
            self._progress_label.setStyleSheet("color: gray;")

    def _filename_to_display_name(self, filename: str) -> str:
        """Convert a CAP filename to a display name."""
        name = filename
        if name.lower().endswith(".cap"):
            name = name[:-4]
        name = name.replace("-", " ").replace("_", " ")
        return name.title()

    def _on_variant_selected(self, index: int):
        """Handle variant selection change."""
        # Save current variant before switching
        if self._current_index >= 0 and self._current_index < len(self._variant_configs):
            self._save_current_variant()

        self._current_index = index

        if index < 0 or index >= len(self._variant_configs):
            self._set_detail_enabled(False)
            self._detail_header.setText("<b>Select an applet to configure</b>")
            return

        # Load selected variant
        config = self._variant_configs[index]

        self._detail_header.setText(f"<b>Configuring: {config['filename']}</b>")

        # Block signals while loading
        self._name_edit.blockSignals(True)
        self._aid_edit.blockSignals(True)
        self._persistent_spin.blockSignals(True)
        self._transient_spin.blockSignals(True)
        self._desc_edit.blockSignals(True)

        self._name_edit.setText(config.get("display_name", ""))
        self._aid_edit.setText(config.get("aid", ""))
        self._persistent_spin.setValue(config.get("persistent", 0))
        self._transient_spin.setValue(config.get("transient", 0))
        self._desc_edit.setPlainText(config.get("description", ""))

        self._name_edit.blockSignals(False)
        self._aid_edit.blockSignals(False)
        self._persistent_spin.blockSignals(False)
        self._transient_spin.blockSignals(False)
        self._desc_edit.blockSignals(False)

        # Update AID status
        self._validate_aid(config.get("aid", ""))

        self._set_detail_enabled(True)

    def _save_current_variant(self):
        """Save current form values to the variant config."""
        if self._current_index < 0 or self._current_index >= len(self._variant_configs):
            return

        config = self._variant_configs[self._current_index]
        config["display_name"] = self._name_edit.text().strip()
        config["aid"] = self._aid_edit.text().strip().upper().replace(" ", "")
        config["persistent"] = self._persistent_spin.value()
        config["transient"] = self._transient_spin.value()
        config["description"] = self._desc_edit.toPlainText().strip()

        # Update list item
        item = self._variant_list.item(self._current_index)
        if item:
            self._update_list_item(
                item,
                config["filename"],
                config["display_name"],
                config["aid"]
            )

        self._update_progress()

    def _on_field_changed(self):
        """Handle any field change - auto-save."""
        self._save_current_variant()

    def _on_aid_changed(self, text: str):
        """Handle AID change - validate and auto-save."""
        self._validate_aid(text)
        self._save_current_variant()

    def _validate_aid(self, text: str):
        """Validate AID input and update status."""
        aid = text.replace(" ", "").upper()

        if not aid:
            self._aid_status.setText("AID required for applet matching")
            self._aid_status.setStyleSheet("color: orange;")
            return

        if not re.match(r'^[0-9A-F]*$', aid):
            self._aid_status.setText("Invalid: contains non-hex characters")
            self._aid_status.setStyleSheet("color: red;")
            return

        if len(aid) % 2 != 0:
            self._aid_status.setText(f"Invalid: odd number of characters ({len(aid)})")
            self._aid_status.setStyleSheet("color: red;")
            return

        if len(aid) < 10:
            self._aid_status.setText(f"Too short: {len(aid)//2} bytes (minimum 5)")
            self._aid_status.setStyleSheet("color: red;")
            return

        if len(aid) > 32:
            self._aid_status.setText(f"Too long: {len(aid)//2} bytes (maximum 16)")
            self._aid_status.setStyleSheet("color: red;")
            return

        self._aid_status.setText(f"Valid AID: {len(aid)//2} bytes")
        self._aid_status.setStyleSheet("color: green;")

    def validatePage(self) -> bool:
        """Validate all variants and save to wizard."""
        # Save current variant first
        self._save_current_variant()

        wizard = self.wizard()
        if not wizard:
            return True

        # Validate all variants
        for i, config in enumerate(self._variant_configs):
            filename = config.get("filename", "")
            display_name = config.get("display_name", "")
            aid = config.get("aid", "")

            if not display_name:
                QMessageBox.warning(
                    self,
                    "Missing Name",
                    f"Please enter a display name for '{filename}'.\n\n"
                    "Select it from the list to configure.",
                )
                self._variant_list.setCurrentRow(i)
                return False

            # Validate AID format if provided
            if aid:
                if not re.match(r'^[0-9A-F]*$', aid):
                    QMessageBox.warning(
                        self,
                        "Invalid AID",
                        f"AID for '{display_name}' contains invalid characters.",
                    )
                    self._variant_list.setCurrentRow(i)
                    return False
                if len(aid) % 2 != 0 or len(aid) < 10 or len(aid) > 32:
                    QMessageBox.warning(
                        self,
                        "Invalid AID",
                        f"AID for '{display_name}' must be 5-16 bytes (10-32 hex characters).",
                    )
                    self._variant_list.setCurrentRow(i)
                    return False

        # Convert to storage format and save
        variants_for_storage = []
        for config in self._variant_configs:
            variant = {
                "filename": config["filename"],
                "display_name": config["display_name"],
                "aid": config.get("aid", ""),
                "description": config.get("description", ""),
            }
            # Only add storage if non-zero
            persistent = config.get("persistent", 0)
            transient = config.get("transient", 0)
            if persistent > 0 or transient > 0:
                variant["storage"] = {
                    "persistent": persistent,
                    "transient": transient,
                }
            variants_for_storage.append(variant)

        wizard.set_plugin_data("_variant_configs", variants_for_storage)
        wizard.set_plugin_data("_share_workflows", self._shared_workflows_check.isChecked())
        wizard.set_plugin_data("_share_actions", self._shared_actions_check.isChecked())

        return True

    def isComplete(self) -> bool:
        """Check if page is complete (all variants have names)."""
        for config in self._variant_configs:
            if not config.get("display_name"):
                return False
        return len(self._variant_configs) > 0
