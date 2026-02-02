"""
Plugin Designer Wizard

Main wizard dialog for creating YAML plugin definitions.
"""

from typing import Any, Optional
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWizard,
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QSplitter,
)

import yaml


def _literal_str_representer(dumper, data):
    """Represent multiline strings with literal block style (|)."""
    if '\n' in data:
        # Use literal block style for multiline
        return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
    return dumper.represent_scalar('tag:yaml.org,2002:str', data)


# Register the custom representer
yaml.add_representer(str, _literal_str_representer)


class PluginDesignerWizard(QWizard):
    """
    Multi-page wizard for creating YAML plugins.

    Pages:
    1. Source Config - CAP file source (local, HTTP, GitHub) - FIRST to enable auto-population
    2. Basic Info - Plugin name, description, author (can be pre-filled from GitHub)
    3. Metadata - AID, storage requirements, mutual exclusions
    4. Variants (conditional) - Per-CAP naming when multiple CAPs selected
    5. UI Builder - Form fields for installation parameters
    6. Action Builder - Management actions for installed applets
    7. Workflow Builder - Multi-step workflows for complex operations
    8. Preview - Final YAML preview with export option
    """

    plugin_created = pyqtSignal(str, str)  # yaml_content, save_path

    # Page IDs - Source first to enable auto-population
    PAGE_SOURCE = 0
    PAGE_INTRO = 1
    PAGE_METADATA = 2
    PAGE_VARIANTS = 3  # Only shown when multiple CAPs selected
    PAGE_UI_BUILDER = 4
    PAGE_ACTION_BUILDER = 5
    PAGE_WORKFLOW_BUILDER = 6
    PAGE_PREVIEW = 7

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Plugin")
        self.setMinimumSize(800, 600)
        self.setWizardStyle(QWizard.ModernStyle)

        # Store plugin data
        self._plugin_data = {
            "schema_version": "1.0",
            "plugin": {
                "name": "",
                "description": "",
                "version": "1.0.0",
                "author": "",
            },
            "applet": {
                "source": {},
                "metadata": {},
            },
            "install_ui": None,
            "parameters": None,
            "management_ui": None,
            "workflows": None,
        }
        self._original_path: Optional[str] = None
        self._has_changes = False
        self._saved = False

        self._setup_pages()

    def _setup_pages(self):
        """Set up wizard pages."""
        # Page 1: Source Config (first to enable auto-population)
        from .source_page import SourceConfigPage
        self.setPage(self.PAGE_SOURCE, SourceConfigPage(self))

        # Page 2: Basic Info (can be pre-filled from source)
        self.setPage(self.PAGE_INTRO, IntroPage(self))

        # Page 3: Metadata
        from .metadata_page import MetadataPage
        self.setPage(self.PAGE_METADATA, MetadataPage(self))

        # Page 4: Variants (conditionally shown)
        from .variants_page import AppletVariantsPage
        self.setPage(self.PAGE_VARIANTS, AppletVariantsPage(self))

        # Page 5: UI Builder
        from .ui_builder_page import UIBuilderPage
        self.setPage(self.PAGE_UI_BUILDER, UIBuilderPage(self))

        # Page 6: Action Builder
        from .action_builder_page import ActionBuilderPage
        self.setPage(self.PAGE_ACTION_BUILDER, ActionBuilderPage(self))

        # Page 7: Workflow Builder
        from .workflow_builder_page import WorkflowBuilderPage
        self.setPage(self.PAGE_WORKFLOW_BUILDER, WorkflowBuilderPage(self))

        # Page 8: Preview
        self.setPage(self.PAGE_PREVIEW, PreviewPage(self))

    def _should_show_variants_page(self) -> bool:
        """Check if variants page should be shown (multiple CAPs selected)."""
        selected_caps = self.get_plugin_value("_selected_caps", [])
        return len(selected_caps) > 1

    def get_plugin_data(self) -> dict:
        """Get the current plugin data."""
        return self._plugin_data

    def set_plugin_data(self, key: str, value: Any):
        """Set a value in plugin data using dot notation."""
        # Skip internal keys (starting with _) for change tracking
        if not key.startswith("_"):
            self._has_changes = True
        keys = key.split(".")
        data = self._plugin_data
        for k in keys[:-1]:
            if k not in data or data[k] is None or not isinstance(data[k], dict):
                data[k] = {}
            data = data[k]
        data[keys[-1]] = value

    def get_plugin_value(self, key: str, default: Any = None) -> Any:
        """Get a value from plugin data using dot notation."""
        keys = key.split(".")
        data = self._plugin_data
        for k in keys:
            if isinstance(data, dict) and k in data:
                data = data[k]
            else:
                return default
        return data

    def generate_yaml(self) -> str:
        """Generate YAML from the current plugin data."""
        # Make a deep copy to avoid modifying original
        import copy
        data = copy.deepcopy(self._plugin_data)

        # Convert internal variant configs to proper YAML structure
        variant_configs = data.pop("_variant_configs", None)
        selected_caps = data.pop("_selected_caps", None)

        if variant_configs and len(variant_configs) > 1:
            # Multiple variants - add to applet section
            variants = []
            for vc in variant_configs:
                variant_entry = {
                    "filename": vc.get("filename", ""),
                    "display_name": vc.get("display_name", ""),
                }
                if vc.get("aid"):
                    variant_entry["aid"] = vc["aid"]
                if vc.get("description"):
                    variant_entry["description"] = vc["description"]
                if vc.get("storage"):
                    variant_entry["storage"] = vc["storage"]
                variants.append(variant_entry)

            if "applet" not in data:
                data["applet"] = {}
            data["applet"]["variants"] = variants

        # Remove other internal keys (starting with _)
        keys_to_remove = [k for k in data.keys() if k.startswith("_")]
        for k in keys_to_remove:
            del data[k]

        # Clean up the data (remove empty values)
        data = self._clean_plugin_data(data)
        return yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)

    def _clean_plugin_data(self, data: dict) -> dict:
        """Remove empty/None values and internal keys from plugin data."""
        if not isinstance(data, dict):
            return data

        cleaned = {}
        for key, value in data.items():
            # Skip internal keys (starting with _)
            if key.startswith("_"):
                continue
            if value is None:
                continue
            if isinstance(value, dict):
                cleaned_value = self._clean_plugin_data(value)
                if cleaned_value:  # Only add non-empty dicts
                    cleaned[key] = cleaned_value
            elif isinstance(value, list):
                if value:  # Only add non-empty lists
                    cleaned[key] = value
            elif value != "":  # Only add non-empty strings
                cleaned[key] = value

        return cleaned

    def import_plugin_definition(self, plugin_data: dict, source_filename: str):
        """
        Import a discovered plugin definition directly.

        This saves the plugin YAML and closes the wizard.
        Used when a gp-plugin.yaml is discovered in a repository.
        """
        # Validate the plugin data has required fields
        if not plugin_data.get("plugin") and not plugin_data.get("applet"):
            QMessageBox.warning(
                self,
                "Invalid Plugin",
                "The plugin definition is missing required fields.",
            )
            return

        # Merge with defaults
        if "schema_version" in plugin_data:
            self._plugin_data["schema_version"] = plugin_data["schema_version"]

        if "plugin" in plugin_data:
            self._plugin_data["plugin"].update(plugin_data["plugin"])

        if "applet" in plugin_data:
            if "source" in plugin_data["applet"]:
                self._plugin_data["applet"]["source"] = plugin_data["applet"]["source"]
            if "metadata" in plugin_data["applet"]:
                self._plugin_data["applet"]["metadata"] = plugin_data["applet"]["metadata"]

        if "install_ui" in plugin_data:
            self._plugin_data["install_ui"] = plugin_data["install_ui"]

        if "parameters" in plugin_data:
            self._plugin_data["parameters"] = plugin_data["parameters"]

        if "management_ui" in plugin_data:
            self._plugin_data["management_ui"] = plugin_data["management_ui"]

        if "workflows" in plugin_data:
            self._plugin_data["workflows"] = plugin_data["workflows"]

        # Generate YAML
        yaml_content = self.generate_yaml()

        # Determine save path
        plugins_dir = Path(__file__).parent.parent.parent.parent.parent / "plugins"
        plugins_dir.mkdir(exist_ok=True)

        plugin_name = self._plugin_data.get("plugin", {}).get("name", "imported-plugin")
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in plugin_name)
        save_path = plugins_dir / f"{safe_name}.yaml"

        # Check for overwrite
        if save_path.exists():
            reply = QMessageBox.question(
                self,
                "Overwrite?",
                f"Plugin '{safe_name}.yaml' already exists.\nOverwrite?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(yaml_content)

            self.plugin_created.emit(yaml_content, str(save_path))
            QMessageBox.information(
                self,
                "Plugin Imported",
                f"Plugin imported from {source_filename}\n\nSaved to:\n{save_path}",
            )
            super().accept()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save plugin:\n{e}",
            )

    def load_from_file(self, yaml_path: str):
        """
        Load existing plugin data from a YAML file for editing.

        Args:
            yaml_path: Path to the YAML plugin file

        Raises:
            FileNotFoundError: If the file does not exist
            ValueError: If the file is empty or invalid YAML
        """
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Plugin file not found: {yaml_path}")

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError("Empty or invalid YAML file")

        # Store the original path for save operations
        self._original_path = yaml_path

        # Merge loaded data with defaults
        if "schema_version" in data:
            self._plugin_data["schema_version"] = data["schema_version"]

        if "plugin" in data:
            self._plugin_data["plugin"].update(data["plugin"])

        if "applet" in data:
            if "source" in data["applet"]:
                self._plugin_data["applet"]["source"] = data["applet"]["source"]
            if "metadata" in data["applet"]:
                self._plugin_data["applet"]["metadata"] = data["applet"]["metadata"]
            if "variants" in data["applet"]:
                # Store variants for the source page to use
                self._plugin_data["applet"]["variants"] = data["applet"]["variants"]
                # Also populate _variant_configs and _selected_caps for the variants page
                variant_configs = []
                selected_caps = []
                for v in data["applet"]["variants"]:
                    variant_configs.append({
                        "filename": v.get("filename", ""),
                        "display_name": v.get("display_name", ""),
                        "description": v.get("description", ""),
                        "aid": v.get("aid", ""),
                        "storage": v.get("storage", {}),
                    })
                    selected_caps.append({
                        "filename": v.get("filename", ""),
                        "url": "",  # URL not stored in YAML, will be fetched
                        "metadata": None,
                    })
                self._plugin_data["_variant_configs"] = variant_configs
                self._plugin_data["_selected_caps"] = selected_caps

        if "install_ui" in data:
            self._plugin_data["install_ui"] = data["install_ui"]

        if "parameters" in data:
            self._plugin_data["parameters"] = data["parameters"]

        if "management_ui" in data:
            self._plugin_data["management_ui"] = data["management_ui"]

        if "workflows" in data:
            self._plugin_data["workflows"] = data["workflows"]

    def _get_user_plugins_dir(self) -> Path:
        """
        Get the user-writable plugins directory.

        This is always in the current working directory (next to config.json),
        NOT in the PyInstaller bundle temp directory. This ensures plugin
        edits persist across app restarts.
        """
        import os
        # Use current working directory (where config.json lives)
        user_plugins = Path(os.getcwd()) / "user_plugins"
        user_plugins.mkdir(exist_ok=True)
        return user_plugins

    def accept(self):
        """Handle wizard acceptance - auto-save to user plugins directory."""
        yaml_content = self.generate_yaml()

        # Always save to user_plugins directory for persistence
        # This works for both new plugins and edits to bundled plugins
        plugins_dir = self._get_user_plugins_dir()

        plugin_name = self._plugin_data.get("plugin", {}).get("name", "untitled")
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in plugin_name)
        save_path = plugins_dir / f"{safe_name}.yaml"

        # Check if we're editing an existing user plugin (same name, same dir)
        old_path = Path(self._original_path) if self._original_path else None
        old_is_in_user_dir = old_path and old_path.parent == plugins_dir if old_path else False

        # Check for overwrite (only if not the same file being edited)
        if save_path.exists() and not (old_is_in_user_dir and save_path == old_path):
            reply = QMessageBox.question(
                self,
                "Overwrite?",
                f"Plugin '{safe_name}.yaml' already exists in user_plugins.\nOverwrite?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(yaml_content)

            # Delete old file only if it was in user_plugins and name changed
            if old_is_in_user_dir and old_path and old_path.exists() and old_path != save_path:
                old_path.unlink()

            self.plugin_created.emit(yaml_content, str(save_path))
            QMessageBox.information(
                self,
                "Success",
                f"Plugin saved to:\n{save_path}",
            )
            self._saved = True
            super().accept()
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save plugin:\n{e}",
            )

    def done(self, result):
        """Clean up when wizard closes."""
        # Check for unsaved changes if closing without saving
        if result != QWizard.Accepted and self._has_changes and not self._saved:
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes.\n\n"
                "Are you sure you want to close without saving?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return  # Don't close

        self._cleanup_preview_windows()
        super().done(result)

    def _cleanup_preview_windows(self):
        """Close any open preview windows from wizard pages."""
        # Clean up UIBuilderPage preview window
        ui_page = self.page(self.PAGE_UI_BUILDER)
        if ui_page and hasattr(ui_page, '_preview_window') and ui_page._preview_window:
            ui_page._preview_window.close()
            ui_page._preview_window = None


class IntroPage(QWizardPage):
    """Plugin information page - can be pre-filled from source."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Plugin Information")
        self.setSubTitle("Enter basic information about your plugin.")

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Plugin name
        layout.addWidget(QLabel("Plugin Name:"))
        self._name_edit = QLineEdit()
        self._name_edit.setMinimumWidth(250)  # Prevent collapse on Windows
        self._name_edit.setPlaceholderText("e.g., my-applet")
        self.registerField("plugin_name*", self._name_edit)
        layout.addWidget(self._name_edit)

        # Description
        layout.addWidget(QLabel("Description:"))
        self._desc_edit = QTextEdit()
        self._desc_edit.setMaximumHeight(80)
        self._desc_edit.setMinimumWidth(300)  # Prevent collapse on Windows
        self._desc_edit.setPlaceholderText("Brief description of what this plugin does")
        layout.addWidget(self._desc_edit)

        # Version
        layout.addWidget(QLabel("Version:"))
        self._version_edit = QLineEdit("1.0.0")
        self._version_edit.setMinimumWidth(100)  # Prevent collapse on Windows
        self.registerField("plugin_version", self._version_edit)
        layout.addWidget(self._version_edit)

        # Author
        layout.addWidget(QLabel("Author:"))
        self._author_edit = QLineEdit()
        self._author_edit.setMinimumWidth(250)  # Prevent collapse on Windows
        self._author_edit.setPlaceholderText("Your name or organization")
        self.registerField("plugin_author", self._author_edit)
        layout.addWidget(self._author_edit)

        layout.addStretch()

    def initializePage(self):
        """Pre-fill from source data or loaded plugin data."""
        wizard = self.wizard()
        if not wizard:
            return

        # Load from plugin data (for editing)
        plugin_name = wizard.get_plugin_value("plugin.name", "")
        if plugin_name and not self._name_edit.text():
            self._name_edit.setText(plugin_name)

        plugin_desc = wizard.get_plugin_value("plugin.description", "")
        if plugin_desc and not self._desc_edit.toPlainText():
            self._desc_edit.setPlainText(plugin_desc)

        plugin_version = wizard.get_plugin_value("plugin.version", "")
        if plugin_version and plugin_version != "1.0.0":
            self._version_edit.setText(plugin_version)

        plugin_author = wizard.get_plugin_value("plugin.author", "")
        if plugin_author and not self._author_edit.text():
            self._author_edit.setText(plugin_author)

        # Try to get GitHub repo info (for new plugins from GitHub)
        repo_info = wizard.get_plugin_value("_github_repo_info")
        if repo_info:
            if not self._name_edit.text() and repo_info.get("name"):
                self._name_edit.setText(repo_info["name"])
            if not self._desc_edit.toPlainText() and repo_info.get("description"):
                self._desc_edit.setPlainText(repo_info["description"])
            if not self._author_edit.text() and repo_info.get("owner"):
                self._author_edit.setText(repo_info["owner"])


    def validatePage(self) -> bool:
        """Validate and save data."""
        wizard = self.wizard()
        if wizard:
            wizard.set_plugin_data("plugin.name", self._name_edit.text().strip())
            wizard.set_plugin_data("plugin.description", self._desc_edit.toPlainText().strip())
            wizard.set_plugin_data("plugin.version", self._version_edit.text().strip())
            wizard.set_plugin_data("plugin.author", self._author_edit.text().strip())
        return True


class YamlPreviewDialog:
    """Separate window for YAML preview."""

    def __init__(self, yaml_content: str, parent=None):
        from PyQt5.QtWidgets import QDialog

        # Create the preview widget
        from .yaml_preview import YamlPreviewPane

        self._dialog = QDialog(parent)
        self._dialog.setWindowTitle("Plugin YAML Preview")
        self._dialog.setMinimumSize(700, 500)

        layout = QVBoxLayout(self._dialog)

        self._preview = YamlPreviewPane()
        self._preview.set_yaml(yaml_content)
        layout.addWidget(self._preview)

        # Buttons
        btn_layout = QHBoxLayout()
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self._copy_to_clipboard)
        btn_layout.addWidget(copy_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self._dialog.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        self._yaml_content = yaml_content

    def _copy_to_clipboard(self):
        """Copy YAML to clipboard."""
        from PyQt5.QtWidgets import QApplication
        QApplication.clipboard().setText(self._yaml_content)
        QMessageBox.information(
            self._dialog,
            "Copied",
            "YAML copied to clipboard.",
        )

    def exec_(self):
        return self._dialog.exec_()


class PreviewPage(QWizardPage):
    """Final page: Shows summary and opens preview window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Review & Export")
        self.setSubTitle("Your plugin is ready. Review the generated YAML and save.")
        self.setCommitPage(True)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Summary info
        self._summary_label = QLabel()
        self._summary_label.setWordWrap(True)
        self._summary_label.setStyleSheet("background-color: #f5f5f5; padding: 12px; border-radius: 4px;")
        layout.addWidget(self._summary_label)

        layout.addSpacing(20)

        # Preview button
        preview_btn = QPushButton("Show YAML Preview...")
        preview_btn.clicked.connect(self._show_preview_window)
        layout.addWidget(preview_btn)

        # Copy button
        copy_btn = QPushButton("Copy YAML to Clipboard")
        copy_btn.clicked.connect(self._copy_to_clipboard)
        layout.addWidget(copy_btn)

        layout.addStretch()

        # Instructions
        instructions = QLabel(
            "Click 'Finish' to save the plugin YAML file.\n"
            "You can also copy the YAML to clipboard and paste it elsewhere."
        )
        instructions.setStyleSheet("color: gray;")
        layout.addWidget(instructions)

    def initializePage(self):
        """Update summary when page is shown."""
        wizard = self.wizard()
        if not wizard:
            return

        # Build summary
        plugin_name = wizard.get_plugin_value("plugin.name", "Unknown")
        plugin_version = wizard.get_plugin_value("plugin.version", "1.0.0")
        source_type = wizard.get_plugin_value("applet.source.type", "unknown")
        selected_caps = wizard.get_plugin_value("_selected_caps", [])
        variant_configs = wizard.get_plugin_value("_variant_configs", [])

        summary_lines = [
            f"<b>Plugin:</b> {plugin_name} v{plugin_version}",
            f"<b>Source:</b> {source_type}",
        ]

        # Show variant info if multiple CAPs
        if variant_configs and len(variant_configs) > 1:
            summary_lines.append(f"<b>Variants:</b> {len(variant_configs)}")
            for vc in variant_configs:
                display_name = vc.get('display_name', vc.get('filename', 'Unknown'))
                aid = vc.get('aid', '')
                if aid:
                    summary_lines.append(f"  • {display_name} (AID: {aid})")
                else:
                    summary_lines.append(f"  • {display_name}")
        elif selected_caps:
            cap_names = [cap["filename"] for cap in selected_caps]
            summary_lines.append(f"<b>CAP Files:</b> {', '.join(cap_names)}")
            # Show single AID for non-variant plugins
            aid = wizard.get_plugin_value("applet.metadata.aid")
            if aid:
                summary_lines.append(f"<b>AID:</b> {aid}")

        self._summary_label.setText("<br>".join(summary_lines))

    def _show_preview_window(self):
        """Open YAML preview in separate window."""
        wizard = self.wizard()
        if wizard:
            yaml_content = wizard.generate_yaml()
            dialog = YamlPreviewDialog(yaml_content, self)
            dialog.exec_()

    def _copy_to_clipboard(self):
        """Copy YAML to clipboard."""
        from PyQt5.QtWidgets import QApplication
        wizard = self.wizard()
        if wizard:
            yaml_content = wizard.generate_yaml()
            QApplication.clipboard().setText(yaml_content)
            QMessageBox.information(
                self,
                "Copied",
                "YAML copied to clipboard.",
            )
