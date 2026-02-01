"""
Applet Variants Configuration Page

Configures display names and descriptions for each CAP file variant
when multiple CAP files are selected for a single plugin.
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
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QGroupBox,
    QCheckBox,
    QAbstractItemView,
    QMessageBox,
)


class AppletVariantsPage(QWizardPage):
    """Configure individual names and descriptions for each CAP variant."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Applet Variants")
        self.setSubTitle(
            "Configure display names for each applet variant. "
            "Each CAP file can have its own name and description."
        )

        self._variant_configs = []  # List of variant configurations
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Info label
        info_label = QLabel(
            "You've selected multiple CAP files. Configure how each variant "
            "will appear in the installation UI."
        )
        info_label.setWordWrap(True)
        info_label.setStyleSheet(
            "background-color: #e3f2fd; padding: 10px; border-radius: 4px;"
        )
        layout.addWidget(info_label)

        layout.addSpacing(10)

        # Variants table
        self._variants_table = QTableWidget()
        self._variants_table.setColumnCount(3)
        self._variants_table.setHorizontalHeaderLabels(
            ["CAP File", "Display Name", "Description (Optional)"]
        )

        # Configure table
        header = self._variants_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Stretch)

        self._variants_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._variants_table.setAlternatingRowColors(True)

        layout.addWidget(self._variants_table)

        # Options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        self._shared_workflows_check = QCheckBox(
            "Share all workflows across variants (recommended)"
        )
        self._shared_workflows_check.setChecked(True)
        self._shared_workflows_check.setToolTip(
            "When checked, all workflows defined later will apply to all variants.\n"
            "When unchecked, you can assign workflows to specific variants."
        )
        options_layout.addWidget(self._shared_workflows_check)

        self._shared_actions_check = QCheckBox(
            "Share all management actions across variants"
        )
        self._shared_actions_check.setChecked(True)
        self._shared_actions_check.setToolTip(
            "When checked, all management actions will apply to all variants.\n"
            "When unchecked, you can assign actions to specific variants."
        )
        options_layout.addWidget(self._shared_actions_check)

        layout.addWidget(options_group)

        # Quick fill section
        quick_fill_group = QGroupBox("Quick Fill")
        quick_fill_layout = QHBoxLayout(quick_fill_group)

        quick_fill_layout.addWidget(QLabel("Prefix:"))
        self._prefix_edit = QLineEdit()
        self._prefix_edit.setPlaceholderText("e.g., SmartPGP")
        self._prefix_edit.setMaximumWidth(150)
        quick_fill_layout.addWidget(self._prefix_edit)

        from PyQt5.QtWidgets import QPushButton

        apply_prefix_btn = QPushButton("Apply Prefix")
        apply_prefix_btn.clicked.connect(self._apply_prefix)
        apply_prefix_btn.setToolTip(
            "Apply the prefix to generate display names from filenames.\n"
            "e.g., 'SmartPGP' + 'rsa-only.cap' → 'SmartPGP RSA Only'"
        )
        quick_fill_layout.addWidget(apply_prefix_btn)

        auto_name_btn = QPushButton("Auto-Name from Files")
        auto_name_btn.clicked.connect(self._auto_name_from_files)
        auto_name_btn.setToolTip(
            "Generate display names from CAP filenames automatically.\n"
            "e.g., 'smartpgp-rsa-only.cap' → 'Smartpgp Rsa Only'"
        )
        quick_fill_layout.addWidget(auto_name_btn)

        quick_fill_layout.addStretch()
        layout.addWidget(quick_fill_group)

        layout.addStretch()

    def initializePage(self):
        """Populate table with selected CAP files."""
        wizard = self.wizard()
        if not wizard:
            return

        selected_caps = wizard.get_plugin_value("_selected_caps", [])
        if not selected_caps:
            return

        # Load any existing variant configs
        existing_variants = wizard.get_plugin_value("_variant_configs", [])
        existing_map = {v.get("filename"): v for v in existing_variants}

        # Populate table
        self._variants_table.setRowCount(len(selected_caps))

        for row, cap_info in enumerate(selected_caps):
            filename = cap_info.get("filename", "")

            # CAP file column (read-only)
            file_item = QTableWidgetItem(filename)
            file_item.setFlags(file_item.flags() & ~Qt.ItemIsEditable)
            file_item.setToolTip(cap_info.get("url", ""))
            self._variants_table.setItem(row, 0, file_item)

            # Display name column
            existing = existing_map.get(filename, {})
            display_name = existing.get("display_name", "")

            if not display_name:
                # Auto-generate from filename
                display_name = self._filename_to_display_name(filename)

            name_item = QTableWidgetItem(display_name)
            self._variants_table.setItem(row, 1, name_item)

            # Description column
            description = existing.get("description", "")
            desc_item = QTableWidgetItem(description)
            desc_item.setToolTip("Optional description for this variant")
            self._variants_table.setItem(row, 2, desc_item)

        # Try to guess a good prefix from the plugin name or common filename parts
        plugin_name = wizard.get_plugin_value("plugin.name", "")
        if plugin_name and not self._prefix_edit.text():
            # Clean up plugin name for prefix
            prefix = plugin_name.replace("-", " ").replace("_", " ").title()
            self._prefix_edit.setText(prefix)

    def _filename_to_display_name(self, filename: str) -> str:
        """Convert a CAP filename to a display name."""
        # Remove .cap extension
        name = filename
        if name.lower().endswith(".cap"):
            name = name[:-4]

        # Replace separators with spaces
        name = name.replace("-", " ").replace("_", " ")

        # Title case
        name = name.title()

        return name

    def _apply_prefix(self):
        """Apply prefix to generate display names."""
        prefix = self._prefix_edit.text().strip()
        if not prefix:
            QMessageBox.warning(
                self,
                "No Prefix",
                "Please enter a prefix first.",
            )
            return

        for row in range(self._variants_table.rowCount()):
            file_item = self._variants_table.item(row, 0)
            if not file_item:
                continue

            filename = file_item.text()

            # Extract variant part from filename
            # e.g., "SmartPGPApplet-default.cap" → "default"
            variant_part = filename
            if variant_part.lower().endswith(".cap"):
                variant_part = variant_part[:-4]

            # Remove common prefix patterns from filename
            # Try to find what makes this variant different
            clean_variant = variant_part.replace("-", " ").replace("_", " ")

            # Remove prefix-like words from the beginning
            prefix_lower = prefix.lower()
            words = clean_variant.split()
            filtered_words = []
            for word in words:
                if word.lower() not in prefix_lower:
                    filtered_words.append(word)

            if filtered_words:
                variant_suffix = " ".join(filtered_words).title()
                display_name = f"{prefix} {variant_suffix}"
            else:
                display_name = prefix

            name_item = self._variants_table.item(row, 1)
            if name_item:
                name_item.setText(display_name.strip())

    def _auto_name_from_files(self):
        """Generate display names from filenames automatically."""
        for row in range(self._variants_table.rowCount()):
            file_item = self._variants_table.item(row, 0)
            if not file_item:
                continue

            filename = file_item.text()
            display_name = self._filename_to_display_name(filename)

            name_item = self._variants_table.item(row, 1)
            if name_item:
                name_item.setText(display_name)

    def validatePage(self) -> bool:
        """Validate and save variant configurations."""
        wizard = self.wizard()
        if not wizard:
            return True

        # Collect variant configs
        variants = []
        for row in range(self._variants_table.rowCount()):
            file_item = self._variants_table.item(row, 0)
            name_item = self._variants_table.item(row, 1)
            desc_item = self._variants_table.item(row, 2)

            if not file_item or not name_item:
                continue

            filename = file_item.text()
            display_name = name_item.text().strip()
            description = desc_item.text().strip() if desc_item else ""

            if not display_name:
                QMessageBox.warning(
                    self,
                    "Missing Name",
                    f"Please enter a display name for '{filename}'.",
                )
                return False

            variants.append(
                {
                    "filename": filename,
                    "display_name": display_name,
                    "description": description,
                }
            )

        # Store variant configs
        wizard.set_plugin_data("_variant_configs", variants)
        wizard.set_plugin_data("_share_workflows", self._shared_workflows_check.isChecked())
        wizard.set_plugin_data("_share_actions", self._shared_actions_check.isChecked())

        return True

    def isComplete(self) -> bool:
        """Check if page is complete (all variants have names)."""
        for row in range(self._variants_table.rowCount()):
            name_item = self._variants_table.item(row, 1)
            if not name_item or not name_item.text().strip():
                return False
        return True
