"""
Settings Dialog

Provides application settings including plugin management.
"""

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QGroupBox,
    QCheckBox,
    QLabel,
    QPushButton,
    QDialogButtonBox,
    QScrollArea,
    QFrame,
    QMessageBox,
    QMenu,
    QToolButton,
    QRadioButton,
    QLineEdit,
    QApplication,
    QComboBox,
)

from src.plugins.yaml import set_debug_enabled, is_debug_enabled
from src.utils.colors import Colors
from src.views.dialogs.plugin_designer.utils import show_open_file_dialog, show_save_file_dialog


class GeneralTab(QWidget):
    """Tab for general application settings."""

    settings_changed = pyqtSignal()

    def __init__(
        self,
        config: Dict[str, Any],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._config = config
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Debug settings group
        debug_group = QGroupBox("Debugging")
        debug_layout = QVBoxLayout(debug_group)

        # Show debug checkbox
        self._debug_checkbox = QCheckBox("Enable debug logging")
        self._debug_checkbox.setChecked(self._config.get("show_debug", False))
        self._debug_checkbox.setToolTip(
            "When enabled, detailed debug information will be logged to the console.\n"
            "This includes YAML plugin parsing, workflow execution, and card communication."
        )
        self._debug_checkbox.toggled.connect(self._on_debug_toggled)
        debug_layout.addWidget(self._debug_checkbox)

        # Description
        debug_desc = QLabel(
            "Enable this option to see detailed logs for troubleshooting plugin issues."
        )
        debug_desc.setStyleSheet(f"color: {Colors.muted_text()};")
        debug_desc.setWordWrap(True)
        debug_layout.addWidget(debug_desc)

        layout.addWidget(debug_group)
        layout.addStretch()

    def _on_debug_toggled(self, checked: bool):
        self._config["show_debug"] = checked
        # Apply immediately
        set_debug_enabled(checked)
        self.settings_changed.emit()

    def get_debug_enabled(self) -> bool:
        """Get the current debug setting."""
        return self._debug_checkbox.isChecked()


# Cache timeout display labels (must match keys in secure_storage.CACHE_TIMEOUT_OPTIONS)
CACHE_TIMEOUT_LABELS = {
    "never": "Never (always unlock)",
    "30_seconds": "30 seconds",
    "1_minute": "1 minute",
    "5_minutes": "5 minutes",
    "15_minutes": "15 minutes",
    "30_minutes": "30 minutes",
    "1_hour": "1 hour",
    "session": "Session (until app closes)",
}

CACHE_TIMEOUT_KEYS = list(CACHE_TIMEOUT_LABELS.keys())


class StorageTab(QWidget):
    """Tab for managing secure storage settings."""

    reset_storage_requested = pyqtSignal()
    change_method_requested = pyqtSignal()
    export_backup_requested = pyqtSignal()
    import_backup_requested = pyqtSignal()
    browse_storage_requested = pyqtSignal()
    cache_timeout_changed = pyqtSignal(str)  # Emits the timeout key

    def __init__(
        self,
        storage_info: Dict[str, Any],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._storage_info = storage_info
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Storage Status group
        status_group = QGroupBox("Storage Status")
        status_layout = QVBoxLayout(status_group)

        # Storage file path
        file_layout = QHBoxLayout()
        file_layout.addWidget(QLabel("Storage file:"))
        self._file_label = QLabel(self._storage_info.get("file_path", "Not configured"))
        self._file_label.setStyleSheet(f"color: {Colors.secondary_text()};")
        file_layout.addWidget(self._file_label)
        file_layout.addStretch()
        status_layout.addLayout(file_layout)

        # Storage method
        method_layout = QHBoxLayout()
        method_layout.addWidget(QLabel("Encryption method:"))
        method = self._storage_info.get("method", "Unknown")
        method_display = "GPG" if method == "gpg" else "System Keyring" if method == "keyring" else method
        self._method_label = QLabel(method_display)
        self._method_label.setStyleSheet(f"color: {Colors.secondary_text()};")
        method_layout.addWidget(self._method_label)
        method_layout.addStretch()
        status_layout.addLayout(method_layout)

        # Status indicator
        status_layout.addSpacing(10)
        is_loaded = self._storage_info.get("is_loaded", False)
        if is_loaded:
            tag_count = self._storage_info.get("tag_count", 0)
            status_text = f"✓ Storage loaded ({tag_count} saved tag{'s' if tag_count != 1 else ''})"
            status_color = "color: #4CAF50;"
        else:
            status_text = "✗ Storage not loaded"
            status_color = "color: #f44336;"

        self._status_label = QLabel(status_text)
        self._status_label.setStyleSheet(status_color)
        status_layout.addWidget(self._status_label)

        # Change encryption method button
        status_layout.addSpacing(10)
        change_method_layout = QHBoxLayout()
        change_method_btn = QPushButton("Change Encryption Method...")
        change_method_btn.setToolTip(
            "Switch between System Keyring and GPG encryption methods.\n"
            "This will re-encrypt all stored data."
        )
        change_method_btn.clicked.connect(self._on_change_method_clicked)
        change_method_layout.addWidget(change_method_btn)
        change_method_layout.addStretch()
        status_layout.addLayout(change_method_layout)

        layout.addWidget(status_group)

        # Cache settings group
        cache_group = QGroupBox("Cache Settings")
        cache_layout = QVBoxLayout(cache_group)

        cache_desc = QLabel(
            "Control how long decrypted storage remains cached in memory.\n"
            "Longer timeouts reduce GPG unlock prompts but keep data in memory longer."
        )
        cache_desc.setStyleSheet(f"color: {Colors.muted_text()};")
        cache_desc.setWordWrap(True)
        cache_layout.addWidget(cache_desc)

        timeout_layout = QHBoxLayout()
        timeout_layout.addWidget(QLabel("Cache secure storage for:"))
        self._cache_timeout_combo = QComboBox()
        for key in CACHE_TIMEOUT_KEYS:
            self._cache_timeout_combo.addItem(CACHE_TIMEOUT_LABELS[key], key)

        # Set current value from storage_info
        current_timeout = self._storage_info.get("cache_timeout", "session")
        idx = CACHE_TIMEOUT_KEYS.index(current_timeout) if current_timeout in CACHE_TIMEOUT_KEYS else 0
        self._cache_timeout_combo.setCurrentIndex(idx)
        self._cache_timeout_combo.currentIndexChanged.connect(self._on_cache_timeout_changed)
        timeout_layout.addWidget(self._cache_timeout_combo)
        timeout_layout.addStretch()
        cache_layout.addLayout(timeout_layout)

        layout.addWidget(cache_group)

        # Backup & Restore group
        backup_group = QGroupBox("Backup & Restore")
        backup_layout = QVBoxLayout(backup_group)

        backup_desc = QLabel(
            "Create encrypted backups or restore from previous backups."
        )
        backup_desc.setStyleSheet(f"color: {Colors.muted_text()};")
        backup_desc.setWordWrap(True)
        backup_layout.addWidget(backup_desc)

        backup_btn_layout = QHBoxLayout()
        export_btn = QPushButton("Export Backup...")
        export_btn.setToolTip(
            "Export your saved keys to an encrypted backup file.\n"
            "Choose between password or GPG encryption."
        )
        export_btn.clicked.connect(self._on_export_clicked)
        backup_btn_layout.addWidget(export_btn)

        import_btn = QPushButton("Import Backup...")
        import_btn.setToolTip(
            "Import keys from a previously exported backup file.\n"
            "Conflicts will be resolved interactively."
        )
        import_btn.clicked.connect(self._on_import_clicked)
        backup_btn_layout.addWidget(import_btn)

        backup_btn_layout.addStretch()
        backup_layout.addLayout(backup_btn_layout)

        layout.addWidget(backup_group)

        # Actions group
        actions_group = QGroupBox("Storage Actions")
        actions_layout = QVBoxLayout(actions_group)

        # Browse stored cards button
        browse_layout = QHBoxLayout()
        browse_btn = QPushButton("Browse Stored Cards...")
        browse_btn.setToolTip(
            "View, edit, or delete stored card entries.\n"
            "See all cards with their names, UIDs, and keys."
        )
        browse_btn.clicked.connect(self._on_browse_clicked)
        browse_layout.addWidget(browse_btn)
        browse_layout.addStretch()
        actions_layout.addLayout(browse_layout)

        actions_layout.addSpacing(10)

        # Reset storage button
        reset_layout = QHBoxLayout()
        reset_btn = QPushButton("Reset Secure Storage...")
        reset_btn.setToolTip(
            "Create a new secure storage file.\n"
            "Your existing data will be backed up first."
        )
        reset_btn.clicked.connect(self._on_reset_clicked)
        reset_layout.addWidget(reset_btn)
        reset_layout.addStretch()
        actions_layout.addLayout(reset_layout)

        # Description
        reset_desc = QLabel(
            "Resetting creates a new empty storage file. Your existing data "
            "will be backed up to a timestamped file in the same directory."
        )
        reset_desc.setStyleSheet(f"color: {Colors.muted_text()};")
        reset_desc.setWordWrap(True)
        actions_layout.addWidget(reset_desc)

        layout.addWidget(actions_group)

        # Info section
        info_group = QGroupBox("About Secure Storage")
        info_layout = QVBoxLayout(info_group)

        info_text = QLabel(
            "Secure storage protects your saved card keys using encryption. "
            "Keys are encrypted using either your system's keyring or a GPG key.\n\n"
            "• <b>System Keyring</b>: Uses your OS credential manager (recommended)\n"
            "• <b>GPG</b>: Uses a GPG key for encryption"
        )
        info_text.setStyleSheet(f"color: {Colors.subtle_text()};")
        info_text.setWordWrap(True)
        info_text.setTextFormat(Qt.RichText)
        info_layout.addWidget(info_text)

        layout.addWidget(info_group)

        layout.addStretch()

    def _on_reset_clicked(self):
        """Handle reset storage request."""
        reply = QMessageBox.question(
            self,
            "Reset Secure Storage",
            "This will create a new secure storage file.\n\n"
            "Your existing data will be backed up first.\n\n"
            "Are you sure you want to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.reset_storage_requested.emit()

    def _on_change_method_clicked(self):
        """Handle change encryption method request."""
        self.change_method_requested.emit()

    def _on_export_clicked(self):
        """Handle export backup request."""
        self.export_backup_requested.emit()

    def _on_import_clicked(self):
        """Handle import backup request."""
        self.import_backup_requested.emit()

    def _on_browse_clicked(self):
        """Handle browse storage request."""
        self.browse_storage_requested.emit()

    def _on_cache_timeout_changed(self, index: int):
        """Handle cache timeout selection change."""
        timeout_key = self._cache_timeout_combo.currentData()
        self.cache_timeout_changed.emit(timeout_key)

    def get_cache_timeout(self) -> str:
        """Get the selected cache timeout key."""
        return self._cache_timeout_combo.currentData()

    def update_status(self, storage_info: Dict[str, Any]):
        """Update the displayed storage status."""
        self._storage_info = storage_info

        # Update file path
        self._file_label.setText(storage_info.get("file_path", "Not configured"))

        # Update method
        method = storage_info.get("method", "Unknown")
        method_display = "GPG" if method == "gpg" else "System Keyring" if method == "keyring" else method
        self._method_label.setText(method_display)

        # Update status
        is_loaded = storage_info.get("is_loaded", False)
        if is_loaded:
            tag_count = storage_info.get("tag_count", 0)
            status_text = f"✓ Storage loaded ({tag_count} saved tag{'s' if tag_count != 1 else ''})"
            status_color = "color: #4CAF50;"
        else:
            status_text = "✗ Storage not loaded"
            status_color = "color: #f44336;"

        self._status_label.setText(status_text)
        self._status_label.setStyleSheet(status_color)


class PluginItem(QFrame):
    """A single plugin item with checkbox and info."""

    toggled = pyqtSignal(str, bool)  # plugin_name, enabled
    edit_requested = pyqtSignal(str)  # plugin_name
    duplicate_requested = pyqtSignal(str)  # plugin_name
    export_requested = pyqtSignal(str)  # plugin_name
    delete_requested = pyqtSignal(str)  # plugin_name

    def __init__(
        self,
        plugin_name: str,
        plugin_info: Dict[str, Any],
        enabled: bool = True,
        is_yaml: bool = False,
        yaml_path: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._plugin_name = plugin_name
        self._is_yaml = is_yaml
        self._yaml_path = yaml_path
        self._setup_ui(plugin_info, enabled)

    def _setup_ui(self, plugin_info: Dict[str, Any], enabled: bool):
        self._menu_btn = None  # Initialize for non-YAML plugins
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            PluginItem {
                background-color: #adadad;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 8px;
                margin: 2px;
            }
            PluginItem:hover {
                border-color: #5d5d5d;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Checkbox
        self._checkbox = QCheckBox()
        self._checkbox.setChecked(enabled)
        self._checkbox.toggled.connect(self._on_toggled)
        layout.addWidget(self._checkbox)

        # Plugin info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        # Name
        name_label = QLabel(f"<b>{self._plugin_name}</b>")
        info_layout.addWidget(name_label)

        # Type and details
        plugin_type = plugin_info.get("type", "unknown")
        type_label = QLabel(f"Type: {plugin_type}")
        type_label.setStyleSheet(f"color: {Colors.primary_text()};")
        info_layout.addWidget(type_label)

        # Description if available
        description = plugin_info.get("description", "")
        if description:
            desc_label = QLabel(description)
            desc_label.setStyleSheet(f"color: {Colors.primary_text()};")
            desc_label.setWordWrap(True)
            info_layout.addWidget(desc_label)

        # Cap files count
        caps = plugin_info.get("caps", [])
        if caps:
            caps_label = QLabel(f"Provides: {len(caps)} applet(s)")
            caps_label.setStyleSheet(f"color: {Colors.primary_text()};")
            info_layout.addWidget(caps_label)

        layout.addLayout(info_layout, 1)

        # Menu button for YAML plugins
        if self._is_yaml:
            self._menu_btn = QToolButton()
            self._menu_btn.setText("⋮")
            self._menu_btn.setStyleSheet("""
                QToolButton {
                    border: none;
                    padding: 4px 8px;
                    font-weight: bold;
                }
                QToolButton:hover {
                    background-color: #5d5d5d;
                    border-radius: 4px;
                }
            """)
            # Use larger font for menu icon to be visible on Windows
            menu_font = self._menu_btn.font()
            menu_font.setPointSize(14)
            self._menu_btn.setFont(menu_font)
            self._menu_btn.setPopupMode(QToolButton.InstantPopup)

            menu = QMenu(self)
            menu.addAction("Edit", self._on_edit)
            menu.addAction("Duplicate", self._on_duplicate)
            menu.addAction("Export", self._on_export)
            menu.addSeparator()
            menu.addAction("Delete", self._on_delete)

            self._menu_btn.setMenu(menu)
            layout.addWidget(self._menu_btn)

    def _on_toggled(self, checked: bool):
        self.toggled.emit(self._plugin_name, checked)

    @property
    def plugin_name(self) -> str:
        return self._plugin_name

    @property
    def is_enabled(self) -> bool:
        return self._checkbox.isChecked()

    @property
    def yaml_path(self) -> Optional[str]:
        return self._yaml_path

    def _on_edit(self):
        self.edit_requested.emit(self._plugin_name)

    def _on_duplicate(self):
        self.duplicate_requested.emit(self._plugin_name)

    def _on_export(self):
        self.export_requested.emit(self._plugin_name)

    def _on_delete(self):
        self.delete_requested.emit(self._plugin_name)


class ImportPluginDialog(QDialog):
    """Dialog for importing plugins from various sources."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Import Plugin")
        self.setMinimumWidth(500)

        self._result_path = None
        self._imported_names = []  # Names of successfully imported plugins
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Source selection
        source_group = QGroupBox("Import From")
        source_layout = QVBoxLayout(source_group)

        # Local file option
        self._local_radio = QRadioButton("Local File")
        self._local_radio.setChecked(True)
        self._local_radio.toggled.connect(self._on_source_changed)
        source_layout.addWidget(self._local_radio)

        local_layout = QHBoxLayout()
        self._local_path_edit = QLineEdit()
        self._local_path_edit.setPlaceholderText("Select a .yaml or .gp-plugin.yaml file...")
        self._local_path_edit.setReadOnly(True)
        local_layout.addWidget(self._local_path_edit)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_local)
        local_layout.addWidget(browse_btn)
        source_layout.addLayout(local_layout)

        # URL option
        self._url_radio = QRadioButton("URL")
        self._url_radio.toggled.connect(self._on_source_changed)
        source_layout.addWidget(self._url_radio)

        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("https://example.com/plugin.gp-plugin.yaml")
        self._url_edit.setEnabled(False)
        source_layout.addWidget(self._url_edit)

        # GitHub repo option
        self._github_radio = QRadioButton("GitHub Repository")
        self._github_radio.toggled.connect(self._on_source_changed)
        source_layout.addWidget(self._github_radio)

        self._github_edit = QLineEdit()
        self._github_edit.setPlaceholderText("https://github.com/owner/repo or owner/repo")
        self._github_edit.setEnabled(False)
        source_layout.addWidget(self._github_edit)

        github_desc = QLabel(
            "Will search for gp-plugin.yaml or *.gp-plugin.yaml in the repository root."
        )
        github_desc.setStyleSheet(f"color: {Colors.muted_text()}; margin-left: 20px;")
        github_desc.setWordWrap(True)
        source_layout.addWidget(github_desc)

        layout.addWidget(source_group)

        # Status label
        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"color: {Colors.secondary_text()};")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        # Buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        self._ok_btn = button_box.button(QDialogButtonBox.Ok)
        self._ok_btn.setText("Import")
        layout.addWidget(button_box)

    def _on_source_changed(self):
        """Update UI based on selected source."""
        self._local_path_edit.setEnabled(self._local_radio.isChecked())
        self._url_edit.setEnabled(self._url_radio.isChecked())
        self._github_edit.setEnabled(self._github_radio.isChecked())

    def _browse_local(self):
        """Browse for a local plugin file."""
        def on_file_selected(path: str):
            if path:
                self._local_path_edit.setText(path)

        show_open_file_dialog(
            self,
            "Select Plugin File",
            [("Plugin Files", "*.yaml *.yml"), ("All Files", "*.*")],
            on_file_selected,
        )

    def _on_accept(self):
        """Handle import request."""
        # Use user_plugins in current working directory (writable, persists across restarts)
        plugins_dir = Path.cwd() / "user_plugins"

        if self._local_radio.isChecked():
            self._import_local(plugins_dir)
        elif self._url_radio.isChecked():
            self._import_url(plugins_dir)
        elif self._github_radio.isChecked():
            self._import_github(plugins_dir)

    def _import_local(self, plugins_dir: Path):
        """Import from local file."""
        src_path = self._local_path_edit.text().strip()
        if not src_path:
            QMessageBox.warning(self, "No File Selected", "Please select a plugin file.")
            return

        src = Path(src_path)
        if not src.exists():
            QMessageBox.warning(self, "File Not Found", f"File not found: {src_path}")
            return

        # Copy to plugins directory
        dest = plugins_dir / src.name
        if dest.exists():
            reply = QMessageBox.question(
                self,
                "File Exists",
                f"Plugin '{src.name}' already exists. Overwrite?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        try:
            plugins_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dest)
            self._result_path = str(dest)
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to import plugin:\n{e}")

    def _import_url(self, plugins_dir: Path):
        """Import from URL."""
        import urllib.request
        import urllib.error

        url = self._url_edit.text().strip()
        if not url:
            QMessageBox.warning(self, "No URL", "Please enter a URL.")
            return

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Extract filename from URL
        filename = url.split("/")[-1]
        if not filename.endswith((".yaml", ".yml")):
            filename = "imported-plugin.gp-plugin.yaml"

        self._status_label.setText("Downloading...")
        QApplication.processEvents()

        try:
            dest = plugins_dir / filename
            if dest.exists():
                reply = QMessageBox.question(
                    self,
                    "File Exists",
                    f"Plugin '{filename}' already exists. Overwrite?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    self._status_label.setText("")
                    return

            plugins_dir.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(url, dest)
            self._result_path = str(dest)
            self._status_label.setText("Downloaded successfully!")
            self.accept()
        except urllib.error.URLError as e:
            self._status_label.setText("")
            QMessageBox.critical(self, "Download Failed", f"Failed to download:\n{e.reason}")
        except Exception as e:
            self._status_label.setText("")
            QMessageBox.critical(self, "Error", f"Failed to import plugin:\n{e}")

    def _import_github(self, plugins_dir: Path):
        """Import from GitHub repository."""
        import urllib.request
        import urllib.error
        import json
        import yaml

        repo = self._github_edit.text().strip()
        if not repo:
            QMessageBox.warning(self, "No Repository", "Please enter a GitHub repository.")
            return

        # Parse repo format
        if repo.startswith("https://github.com/"):
            repo = repo.replace("https://github.com/", "")
        elif repo.startswith("github.com/"):
            repo = repo.replace("github.com/", "")

        # Remove trailing slashes and .git
        repo = repo.rstrip("/").removesuffix(".git")

        # Extract owner/repo
        parts = repo.split("/")
        if len(parts) < 2:
            QMessageBox.warning(
                self,
                "Invalid Repository",
                "Please enter a valid repository in the format 'owner/repo'.",
            )
            return

        owner, repo_name = parts[0], parts[1]

        self._status_label.setText("Searching for plugin files...")
        QApplication.processEvents()

        # Use the shared utility functions to find ALL plugins
        from src.views.dialogs.plugin_designer.utils import (
            fetch_github_plugin_definition,
            fetch_github_release_plugin_definition,
        )

        try:
            # Collect from repo root and release assets
            repo_plugins = fetch_github_plugin_definition(owner, repo_name)
            release_plugins = fetch_github_release_plugin_definition(owner, repo_name, "")

            # Combine and deduplicate by filename
            seen_filenames = set()
            all_plugins = []
            for filename, plugin_data in repo_plugins + release_plugins:
                if filename not in seen_filenames:
                    seen_filenames.add(filename)
                    all_plugins.append((filename, plugin_data))

            if not all_plugins:
                self._status_label.setText("")
                QMessageBox.warning(
                    self,
                    "No Plugin Found",
                    f"Could not find any plugin files in repository '{owner}/{repo_name}'.\n\n"
                    "Expected: gp-plugin.yaml in repo root or *.gp-plugin.yaml in releases.",
                )
                return

            # If multiple plugins found, show selection dialog
            if len(all_plugins) > 1:
                selected = self._show_plugin_selection_dialog(all_plugins)
                if not selected:
                    self._status_label.setText("")
                    return
            else:
                selected = all_plugins

            # Import selected plugins
            imported = []
            for filename, plugin_data in selected:
                plugin_name = plugin_data.get("plugin", {}).get("name", filename.replace(".gp-plugin.yaml", ""))
                safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in plugin_name)
                dest = plugins_dir / f"{safe_name}.yaml"

                if dest.exists():
                    reply = QMessageBox.question(
                        self,
                        "File Exists",
                        f"Plugin '{safe_name}.yaml' already exists. Overwrite?",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No,
                    )
                    if reply != QMessageBox.Yes:
                        continue

                self._status_label.setText(f"Saving {safe_name}.yaml...")
                QApplication.processEvents()

                plugins_dir.mkdir(parents=True, exist_ok=True)
                with open(dest, "w", encoding="utf-8") as f:
                    yaml.dump(plugin_data, f, default_flow_style=False, allow_unicode=True)
                imported.append(safe_name)

            if imported:
                self._status_label.setText("Import complete!")
                self._result_path = str(plugins_dir / f"{imported[0]}.yaml")
                self._imported_names = imported  # Store for caller to access

                # Debug logging
                import os
                debug_path = os.path.expanduser("~/gp_gui_debug.log")
                with open(debug_path, "a") as f:
                    f.write(f"\n=== _import_github completed ===\n")
                    f.write(f"plugins_dir: {plugins_dir}\n")
                    f.write(f"imported names: {imported}\n")
                    f.write(f"result_path: {self._result_path}\n")

                self.accept()
            else:
                self._status_label.setText("")

        except urllib.error.URLError as e:
            self._status_label.setText("")
            QMessageBox.critical(self, "Network Error", f"Failed to access GitHub:\n{e.reason}")
        except Exception as e:
            self._status_label.setText("")
            QMessageBox.critical(self, "Error", f"Failed to import plugin:\n{e}")

    def _show_plugin_selection_dialog(self, plugins: list) -> list:
        """Show dialog to select which plugins to import."""
        from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QListWidget, QListWidgetItem

        dialog = QDialog(self)
        dialog.setWindowTitle("Select Plugins to Import")
        dialog.setMinimumWidth(400)

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"Found {len(plugins)} plugin definitions. Select which to import:"))

        list_widget = QListWidget()
        for filename, plugin_data in plugins:
            plugin_name = plugin_data.get("plugin", {}).get("name", filename)
            item = QListWidgetItem(f"{plugin_name} ({filename})")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)
            item.setData(Qt.UserRole, (filename, plugin_data))
            list_widget.addItem(item)
        layout.addWidget(list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec_() == QDialog.Accepted:
            selected = []
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                if item.checkState() == Qt.Checked:
                    selected.append(item.data(Qt.UserRole))
            return selected
        return []

    def get_imported_path(self) -> str:
        """Get the path to the imported plugin file."""
        return self._result_path

    def get_imported_names(self) -> List[str]:
        """Get the names of successfully imported plugins."""
        return self._imported_names


class PluginsTab(QWidget):
    """Tab for managing plugins."""

    plugins_changed = pyqtSignal()
    edit_plugin = pyqtSignal(str, str)  # plugin_name, yaml_path
    refresh_requested = pyqtSignal()  # request parent to refresh plugins
    save_required = pyqtSignal()  # request immediate save (for hiding plugins)

    def __init__(
        self,
        plugin_map: Dict[str, Any],
        disabled_plugins: List[str],
        hidden_plugins: List[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._plugin_map = plugin_map
        self._disabled_plugins = set(disabled_plugins)
        self._hidden_plugins = set(hidden_plugins or [])
        self._plugin_items: Dict[str, PluginItem] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header = QLabel(
            "Enable or disable plugins. Disabled plugins will not load on next startup."
        )
        header.setStyleSheet(f"color: {Colors.subtle_text()};margin-bottom: 10px;")
        header.setWordWrap(True)
        layout.addWidget(header)

        # Scroll area for plugins
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(4)

        # Add plugin items (skip hidden plugins)
        for plugin_name, plugin_cls_or_instance in self._plugin_map.items():
            if plugin_name in self._hidden_plugins:
                continue  # Skip hidden plugins

            # Get plugin info
            plugin_info = self._get_plugin_info(plugin_name, plugin_cls_or_instance)
            enabled = plugin_name not in self._disabled_plugins

            item = PluginItem(
                plugin_name,
                plugin_info,
                enabled,
                is_yaml=plugin_info.get("is_yaml", False),
                yaml_path=plugin_info.get("yaml_path"),
            )
            item.toggled.connect(self._on_plugin_toggled)
            item.edit_requested.connect(self._on_edit_plugin)
            item.duplicate_requested.connect(self._on_duplicate_plugin)
            item.export_requested.connect(self._on_export_plugin)
            item.delete_requested.connect(self._on_delete_plugin)
            self._plugin_items[plugin_name] = item
            scroll_layout.addWidget(item)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # Buttons
        btn_layout = QHBoxLayout()

        import_btn = QPushButton("Import Plugin...")
        import_btn.clicked.connect(self._on_import_plugin)
        btn_layout.addWidget(import_btn)

        btn_layout.addStretch()

        enable_all_btn = QPushButton("Enable All")
        enable_all_btn.clicked.connect(self._enable_all)
        btn_layout.addWidget(enable_all_btn)

        disable_all_btn = QPushButton("Disable All")
        disable_all_btn.clicked.connect(self._disable_all)
        btn_layout.addWidget(disable_all_btn)

        # Restore hidden button (only visible when there are hidden plugins)
        self._restore_hidden_btn = QPushButton("Restore Hidden...")
        self._restore_hidden_btn.clicked.connect(self._on_restore_hidden)
        self._restore_hidden_btn.setVisible(len(self._hidden_plugins) > 0)
        btn_layout.addWidget(self._restore_hidden_btn)

        layout.addLayout(btn_layout)

    def _get_plugin_info(self, plugin_name: str, plugin_cls_or_instance) -> Dict[str, Any]:
        """Extract plugin info for display."""
        info = {"type": "Python", "description": "", "caps": [], "is_yaml": False, "yaml_path": None}

        # Check if it's a YAML plugin (instance) or Python plugin (class)
        if isinstance(plugin_cls_or_instance, type):
            info["type"] = "Python"
            info["is_yaml"] = False
            try:
                instance = plugin_cls_or_instance()
                if hasattr(instance, "fetch_available_caps"):
                    info["caps"] = ["..."]
            except Exception:
                pass
        else:
            # YAML plugin instance
            info["type"] = "YAML"
            info["is_yaml"] = True
            if hasattr(plugin_cls_or_instance, "_yaml_path"):
                info["yaml_path"] = plugin_cls_or_instance._yaml_path
            if hasattr(plugin_cls_or_instance, "_schema"):
                schema = plugin_cls_or_instance._schema
                if hasattr(schema, "plugin") and hasattr(schema.plugin, "description"):
                    info["description"] = schema.plugin.description or ""
            if hasattr(plugin_cls_or_instance, "_fetched_cap_names"):
                info["caps"] = plugin_cls_or_instance._fetched_cap_names

        return info

    def _on_plugin_toggled(self, plugin_name: str, enabled: bool):
        if enabled:
            self._disabled_plugins.discard(plugin_name)
        else:
            self._disabled_plugins.add(plugin_name)
        self.plugins_changed.emit()

    def _enable_all(self):
        self._disabled_plugins.clear()
        for item in self._plugin_items.values():
            item._checkbox.setChecked(True)
        self.plugins_changed.emit()

    def _disable_all(self):
        self._disabled_plugins = set(self._plugin_map.keys())
        for item in self._plugin_items.values():
            item._checkbox.setChecked(False)
        self.plugins_changed.emit()

    def get_disabled_plugins(self) -> List[str]:
        """Get list of disabled plugin names."""
        return list(self._disabled_plugins)

    def get_hidden_plugins(self) -> List[str]:
        """Get list of hidden plugin names (bundled plugins user chose to hide)."""
        return list(self._hidden_plugins)

    def update_plugin_map(self, new_plugin_map: Dict[str, Any]):
        """Update the plugin list with a new plugin map (after import/delete)."""
        self._plugin_map = new_plugin_map

        # Clear existing plugin items from UI
        for widget in self._plugin_items.values():
            widget.setParent(None)
            widget.deleteLater()
        self._plugin_items.clear()

        # Find the scroll content layout
        scroll = self.findChild(QScrollArea)
        if scroll and scroll.widget():
            scroll_layout = scroll.widget().layout()
            if scroll_layout:
                # Remove the stretch at the end
                while scroll_layout.count() > 0:
                    item = scroll_layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()

                # Rebuild plugin items
                for plugin_name, plugin_cls_or_instance in self._plugin_map.items():
                    if plugin_name in self._hidden_plugins:
                        continue

                    plugin_info = self._get_plugin_info(plugin_name, plugin_cls_or_instance)
                    enabled = plugin_name not in self._disabled_plugins

                    item = PluginItem(
                        plugin_name,
                        plugin_info,
                        enabled,
                        is_yaml=plugin_info.get("is_yaml", False),
                        yaml_path=plugin_info.get("yaml_path"),
                    )
                    item.toggled.connect(self._on_plugin_toggled)
                    item.edit_requested.connect(self._on_edit_plugin)
                    item.duplicate_requested.connect(self._on_duplicate_plugin)
                    item.export_requested.connect(self._on_export_plugin)
                    item.delete_requested.connect(self._on_delete_plugin)
                    self._plugin_items[plugin_name] = item
                    scroll_layout.addWidget(item)

                scroll_layout.addStretch()

    def _on_restore_hidden(self):
        """Show dialog to restore hidden plugins."""
        if not self._hidden_plugins:
            return

        from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QListWidget, QListWidgetItem

        dialog = QDialog(self)
        dialog.setWindowTitle("Restore Hidden Plugins")
        dialog.setMinimumWidth(300)

        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("Select plugins to restore:"))

        list_widget = QListWidget()
        for name in sorted(self._hidden_plugins):
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            list_widget.addItem(item)
        layout.addWidget(list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec_() == QDialog.Accepted:
            restored = []
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                if item.checkState() == Qt.Checked:
                    restored.append(item.text())

            if restored:
                for name in restored:
                    self._hidden_plugins.discard(name)
                self._restore_hidden_btn.setVisible(len(self._hidden_plugins) > 0)
                self.plugins_changed.emit()
                self.save_required.emit()  # Save immediately so restore persists
                self.refresh_requested.emit()
                QMessageBox.information(
                    self,
                    "Plugins Restored",
                    f"Restored {len(restored)} plugin(s).\n\n"
                    "The application will reload plugins to apply changes.",
                )

    def _on_import_plugin(self):
        """Handle import plugin request."""
        dialog = ImportPluginDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            imported_path = dialog.get_imported_path()
            imported_names = dialog.get_imported_names()

            # Debug: Log to file for troubleshooting
            import os
            debug_path = os.path.expanduser("~/gp_gui_debug.log")
            with open(debug_path, "a") as f:
                f.write(f"\n=== _on_import_plugin ===\n")
                f.write(f"imported_path: {imported_path}\n")
                f.write(f"imported_names: {imported_names}\n")
                f.write(f"hidden_plugins: {self._hidden_plugins}\n")

            if imported_path:
                # Unhide any imported plugins that were previously hidden
                unhidden = []
                for name in imported_names:
                    if name in self._hidden_plugins:
                        self._hidden_plugins.discard(name)
                        unhidden.append(name)
                if unhidden:
                    self._restore_hidden_btn.setVisible(len(self._hidden_plugins) > 0)

                with open(debug_path, "a") as f:
                    f.write(f"unhidden: {unhidden}\n")
                    f.write(f"hidden_plugins after: {self._hidden_plugins}\n")

                count = len(imported_names)
                if count == 1:
                    msg = f"Plugin imported successfully!\n\nFile: {Path(imported_path).name}"
                else:
                    msg = f"{count} plugins imported successfully!"
                if unhidden:
                    msg += f"\n\n(Note: {len(unhidden)} previously hidden plugin(s) have been restored)"

                QMessageBox.information(self, "Plugin Imported", msg)
                self.plugins_changed.emit()
                self.save_required.emit()  # Save to persist unhiding
                self.refresh_requested.emit()

    def _on_edit_plugin(self, plugin_name: str):
        """Handle edit request."""
        item = self._plugin_items.get(plugin_name)
        if item and item.yaml_path:
            self.edit_plugin.emit(plugin_name, item.yaml_path)

    def _on_duplicate_plugin(self, plugin_name: str):
        """Handle duplicate request."""
        item = self._plugin_items.get(plugin_name)
        if not item or not item.yaml_path:
            return

        src_path = Path(item.yaml_path)
        if not src_path.exists():
            QMessageBox.warning(self, "Error", f"Plugin file not found: {src_path}")
            return

        # Generate unique name, preserving original extension
        base_name = src_path.stem
        ext = src_path.suffix  # Preserve .yaml or .yml
        dest_dir = src_path.parent
        counter = 1
        dest_path = dest_dir / f"{base_name}_copy{ext}"
        while dest_path.exists():
            counter += 1
            dest_path = dest_dir / f"{base_name}_copy{counter}{ext}"

        try:
            shutil.copy(src_path, dest_path)
            # Disable original to prevent AID conflict
            self._disabled_plugins.add(plugin_name)
            if plugin_name in self._plugin_items:
                self._plugin_items[plugin_name]._checkbox.setChecked(False)

            QMessageBox.information(
                self,
                "Duplicated",
                f"Plugin duplicated to:\n{dest_path.name}\n\nOriginal disabled to avoid AID conflict.",
            )
            self.plugins_changed.emit()
            self.refresh_requested.emit()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to duplicate: {e}")

    def _on_export_plugin(self, plugin_name: str):
        """Handle export request."""
        item = self._plugin_items.get(plugin_name)
        if not item or not item.yaml_path:
            return

        src_path = Path(item.yaml_path)
        if not src_path.exists():
            QMessageBox.warning(self, "Error", f"Plugin file not found: {src_path}")
            return

        def on_path_selected(dest_path: str):
            if dest_path:
                try:
                    shutil.copy(src_path, dest_path)
                    QMessageBox.information(self, "Exported", f"Plugin exported to:\n{dest_path}")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Failed to export: {e}")

        show_save_file_dialog(
            self,
            "Export Plugin",
            [("YAML Files", "*.yaml *.yml"), ("All Files", "*.*")],
            src_path.name,
            on_path_selected,
        )

    def _on_delete_plugin(self, plugin_name: str):
        """Handle delete request."""
        item = self._plugin_items.get(plugin_name)
        if not item or not item.yaml_path:
            return

        src_path = Path(item.yaml_path)

        reply = QMessageBox.question(
            self,
            "Delete Plugin",
            f"Delete plugin '{plugin_name}'?\n\nFile: {src_path.name}\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            try:
                src_path.unlink(missing_ok=True)
                # Remove from disabled list if present
                self._disabled_plugins.discard(plugin_name)
                # Remove widget from UI immediately
                if plugin_name in self._plugin_items:
                    widget = self._plugin_items.pop(plugin_name)
                    widget.setParent(None)
                    widget.deleteLater()
                self.plugins_changed.emit()
                self.refresh_requested.emit()
            except OSError as e:
                import errno
                # Check for read-only filesystem (errno 30) or permission denied (errno 1/13)
                if e.errno in (errno.EROFS, errno.EPERM, errno.EACCES):
                    # File is read-only (e.g., bundled in AppImage) - offer to hide instead
                    reply = QMessageBox.question(
                        self,
                        "Cannot Delete",
                        f"Plugin '{plugin_name}' is in a read-only location (bundled with the app).\n\n"
                        "Would you like to hide it instead? Hidden plugins won't appear in the list.",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.Yes,
                    )
                    if reply == QMessageBox.Yes:
                        self._hidden_plugins.add(plugin_name)
                        self._disabled_plugins.discard(plugin_name)
                        # Remove widget from UI immediately
                        if plugin_name in self._plugin_items:
                            widget = self._plugin_items.pop(plugin_name)
                            widget.setParent(None)
                            widget.deleteLater()
                        # Show restore button now that there are hidden plugins
                        self._restore_hidden_btn.setVisible(True)
                        self.plugins_changed.emit()
                        self.save_required.emit()  # Save immediately so hiding persists
                else:
                    QMessageBox.critical(self, "Error", f"Failed to delete: {e}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete: {e}")


class FidesmoTab(QWidget):
    """Tab for managing Fidesmo API credentials."""

    settings_changed = pyqtSignal()

    def __init__(
        self,
        secure_storage: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._secure_storage = secure_storage
        self._config = config or {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Status section
        status_group = QGroupBox("Status")
        status_layout = QVBoxLayout(status_group)

        self._status_label = QLabel()
        self._update_status_label()
        status_layout.addWidget(self._status_label)

        layout.addWidget(status_group)

        # Authentication section
        auth_group = QGroupBox("Authentication")
        auth_layout = QVBoxLayout(auth_group)

        auth_desc = QLabel(
            "Enter your Fidesmo API token to enable applet installation and management."
        )
        auth_desc.setStyleSheet(f"color: {Colors.muted_text()};")
        auth_desc.setWordWrap(True)
        auth_layout.addWidget(auth_desc)

        # Token input row
        token_input_layout = QHBoxLayout()
        self._token_edit = QLineEdit()
        self._token_edit.setPlaceholderText("Enter API token...")
        self._token_edit.setEchoMode(QLineEdit.Password)
        self._token_edit.textChanged.connect(self._on_token_text_changed)
        token_input_layout.addWidget(self._token_edit)

        self._token_toggle_btn = QPushButton("Show")
        self._token_toggle_btn.setFixedWidth(60)
        self._token_toggle_btn.clicked.connect(self._toggle_token_visibility)
        token_input_layout.addWidget(self._token_toggle_btn)

        auth_layout.addLayout(token_input_layout)

        # Token buttons
        token_btn_layout = QHBoxLayout()
        self._token_save_btn = QPushButton("Save")
        self._token_save_btn.setEnabled(False)
        self._token_save_btn.clicked.connect(self._on_save_token)
        token_btn_layout.addWidget(self._token_save_btn)

        self._token_clear_btn = QPushButton("Clear")
        self._token_clear_btn.setEnabled(self._has_stored_token())
        self._token_clear_btn.clicked.connect(self._on_clear_token)
        token_btn_layout.addWidget(self._token_clear_btn)

        token_btn_layout.addStretch()
        auth_layout.addLayout(token_btn_layout)

        layout.addWidget(auth_group)

        # Application section
        app_group = QGroupBox("Application")
        app_layout = QVBoxLayout(app_group)

        app_desc = QLabel(
            "Fidesmo Application ID (optional, for developer use)."
        )
        app_desc.setStyleSheet(f"color: {Colors.muted_text()};")
        app_desc.setWordWrap(True)
        app_layout.addWidget(app_desc)

        # App ID input
        self._app_id_edit = QLineEdit()
        self._app_id_edit.setPlaceholderText("Enter application ID...")
        self._app_id_edit.textChanged.connect(self._on_app_id_text_changed)

        # Load existing app ID
        existing_app_id = self._config.get("fidesmo_app_id", "")
        if existing_app_id:
            self._app_id_edit.setText(existing_app_id)

        app_layout.addWidget(self._app_id_edit)

        # App ID buttons
        app_btn_layout = QHBoxLayout()
        self._app_id_save_btn = QPushButton("Save")
        self._app_id_save_btn.setEnabled(False)
        self._app_id_save_btn.clicked.connect(self._on_save_app_id)
        app_btn_layout.addWidget(self._app_id_save_btn)

        self._app_id_clear_btn = QPushButton("Clear")
        self._app_id_clear_btn.setEnabled(bool(existing_app_id))
        self._app_id_clear_btn.clicked.connect(self._on_clear_app_id)
        app_btn_layout.addWidget(self._app_id_clear_btn)

        app_btn_layout.addStretch()
        app_layout.addLayout(app_btn_layout)

        layout.addWidget(app_group)

        layout.addStretch()

    def _has_stored_token(self) -> bool:
        """Check if a token is currently stored in secure storage."""
        try:
            if self._secure_storage and self._secure_storage.get("fidesmo"):
                return bool(self._secure_storage["fidesmo"].get("auth_token"))
        except Exception:
            pass
        return False

    def _update_status_label(self):
        """Update the status label based on current stored values."""
        if self._has_stored_token():
            self._status_label.setText("API Token: Configured")
            self._status_label.setStyleSheet("color: #4CAF50;")
        else:
            self._status_label.setText("API Token: Not configured")
            self._status_label.setStyleSheet("")

    def _on_token_text_changed(self, text: str):
        """Enable/disable save button based on input."""
        self._token_save_btn.setEnabled(bool(text.strip()))

    def _toggle_token_visibility(self):
        """Toggle between showing and hiding the token."""
        if self._token_edit.echoMode() == QLineEdit.Password:
            self._token_edit.setEchoMode(QLineEdit.Normal)
            self._token_toggle_btn.setText("Hide")
        else:
            self._token_edit.setEchoMode(QLineEdit.Password)
            self._token_toggle_btn.setText("Show")

    def _on_save_token(self):
        """Save the API token to secure storage."""
        token = self._token_edit.text().strip()
        if not token:
            return

        try:
            if self._secure_storage is not None:
                if not self._secure_storage.get("fidesmo"):
                    self._secure_storage["fidesmo"] = {}
                self._secure_storage["fidesmo"]["auth_token"] = token
                self._token_save_btn.setEnabled(False)
                self._token_clear_btn.setEnabled(True)
                self._update_status_label()
                self.settings_changed.emit()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save token:\n{e}")

    def _on_clear_token(self):
        """Clear the stored API token."""
        try:
            if self._secure_storage is not None and self._secure_storage.get("fidesmo"):
                del self._secure_storage["fidesmo"]["auth_token"]
                if not self._secure_storage["fidesmo"]:
                    del self._secure_storage["fidesmo"]
                self._token_edit.clear()
                self._token_save_btn.setEnabled(False)
                self._token_clear_btn.setEnabled(False)
                self._update_status_label()
                self.settings_changed.emit()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to clear token:\n{e}")

    def _on_app_id_text_changed(self, text: str):
        """Enable/disable save button based on input."""
        self._app_id_save_btn.setEnabled(bool(text.strip()))

    def _on_save_app_id(self):
        """Save the app ID to config."""
        app_id = self._app_id_edit.text().strip()
        if not app_id:
            return

        self._config["fidesmo_app_id"] = app_id
        self._app_id_save_btn.setEnabled(False)
        self._app_id_clear_btn.setEnabled(True)
        self.settings_changed.emit()

    def _on_clear_app_id(self):
        """Clear the stored app ID."""
        self._config["fidesmo_app_id"] = ""
        self._app_id_edit.clear()
        self._app_id_save_btn.setEnabled(False)
        self._app_id_clear_btn.setEnabled(False)
        self.settings_changed.emit()


class SettingsDialog(QDialog):
    """
    Main settings dialog with tabbed interface.
    """

    edit_plugin_requested = pyqtSignal(str)  # yaml_path
    refresh_plugins_requested = pyqtSignal()
    reset_storage_requested = pyqtSignal()
    change_method_requested = pyqtSignal()
    export_backup_requested = pyqtSignal()
    import_backup_requested = pyqtSignal()
    browse_storage_requested = pyqtSignal()
    cache_timeout_changed = pyqtSignal(str)  # Emits timeout key

    def __init__(
        self,
        plugin_map: Dict[str, Any],
        config: Dict[str, Any],
        storage_info: Optional[Dict[str, Any]] = None,
        secure_storage: Optional[Any] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._plugin_map = plugin_map
        self._config = config
        self._storage_info = storage_info or {}
        self._secure_storage = secure_storage
        self._changes_made = False

        self.setWindowTitle("Settings")
        self.setMinimumSize(500, 400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Tab widget
        tabs = QTabWidget()

        # General tab
        self._general_tab = GeneralTab(self._config)
        self._general_tab.settings_changed.connect(self._on_changes_made)
        tabs.addTab(self._general_tab, "General")

        # Storage tab
        self._storage_tab = StorageTab(self._storage_info)
        self._storage_tab.reset_storage_requested.connect(self._on_reset_storage)
        self._storage_tab.change_method_requested.connect(self._on_change_method)
        self._storage_tab.export_backup_requested.connect(self._on_export_backup)
        self._storage_tab.import_backup_requested.connect(self._on_import_backup)
        self._storage_tab.browse_storage_requested.connect(self._on_browse_storage)
        self._storage_tab.cache_timeout_changed.connect(self._on_cache_timeout_changed)
        tabs.addTab(self._storage_tab, "Storage")

        # Plugins tab
        disabled = self._config.get("disabled_plugins", [])
        hidden = self._config.get("hidden_plugins", [])
        self._plugins_tab = PluginsTab(self._plugin_map, disabled, hidden)
        self._plugins_tab.plugins_changed.connect(self._on_changes_made)
        self._plugins_tab.edit_plugin.connect(self._on_edit_plugin)
        self._plugins_tab.refresh_requested.connect(self._on_refresh_requested)
        self._plugins_tab.save_required.connect(self._save_settings)
        tabs.addTab(self._plugins_tab, "Plugins")

        # Fidesmo tab
        self._fidesmo_tab = FidesmoTab(self._secure_storage, self._config, self)
        self._fidesmo_tab.settings_changed.connect(self._on_changes_made)
        tabs.addTab(self._fidesmo_tab, "Fidesmo")

        layout.addWidget(tabs)

        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply
        )
        button_box.accepted.connect(self._on_accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.Apply).clicked.connect(self._on_apply)
        self._apply_btn = button_box.button(QDialogButtonBox.Apply)
        self._apply_btn.setEnabled(False)
        layout.addWidget(button_box)

    def _on_changes_made(self):
        self._changes_made = True
        self._apply_btn.setEnabled(True)

    def _on_apply(self):
        self._save_settings()
        self._changes_made = False
        self._apply_btn.setEnabled(False)

    def _on_accept(self):
        if self._changes_made:
            self._save_settings()
        self.accept()

    def _save_settings(self):
        """Save settings to config."""
        self._config["disabled_plugins"] = self._plugins_tab.get_disabled_plugins()
        self._config["hidden_plugins"] = self._plugins_tab.get_hidden_plugins()
        self._config["cache_timeout"] = self._storage_tab.get_cache_timeout()

    def _on_edit_plugin(self, plugin_name: str, yaml_path: str):
        """Handle edit plugin request - open wizard with loaded data."""
        from src.views.dialogs.plugin_designer.wizard import PluginDesignerWizard

        wizard = PluginDesignerWizard(self)
        try:
            wizard.load_from_file(yaml_path)
            wizard.setWindowTitle(f"Edit Plugin: {plugin_name}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load plugin:\n{e}")
            return

        if wizard.exec_() == QDialog.Accepted:
            self.refresh_plugins_requested.emit()

    def _on_refresh_requested(self):
        """Handle request to refresh plugin list."""
        # Debug: Log to file
        import os
        debug_path = os.path.expanduser("~/gp_gui_debug.log")
        with open(debug_path, "a") as f:
            f.write(f"\n=== _on_refresh_requested ===\n")

        # Reload plugins and update the tab UI
        from main import load_plugins
        new_plugin_map = load_plugins()

        with open(debug_path, "a") as f:
            f.write(f"load_plugins returned: {len(new_plugin_map) if new_plugin_map else 0} plugins\n")
            if new_plugin_map:
                f.write(f"Plugin names: {list(new_plugin_map.keys())}\n")
            f.write(f"Hidden in tab: {self._plugins_tab._hidden_plugins}\n")

        if new_plugin_map:
            self._plugin_map = new_plugin_map
            self._plugins_tab.update_plugin_map(new_plugin_map)
        # Also notify main window
        self.refresh_plugins_requested.emit()

    def _on_reset_storage(self):
        """Handle reset storage request - emit to main window."""
        self.reset_storage_requested.emit()

    def _on_change_method(self):
        """Handle change encryption method request - emit to main window."""
        self.change_method_requested.emit()

    def _on_export_backup(self):
        """Handle export backup request - emit to main window."""
        self.export_backup_requested.emit()

    def _on_import_backup(self):
        """Handle import backup request - emit to main window."""
        self.import_backup_requested.emit()

    def _on_browse_storage(self):
        """Handle browse storage request - emit to main window."""
        self.browse_storage_requested.emit()

    def _on_cache_timeout_changed(self, timeout_key: str):
        """Handle cache timeout change - emit to main window."""
        self.cache_timeout_changed.emit(timeout_key)
        self._on_changes_made()

    def update_storage_info(self, storage_info: Dict[str, Any]):
        """Update the storage tab with new info."""
        self._storage_info = storage_info
        self._storage_tab.update_status(storage_info)

    def get_config(self) -> Dict[str, Any]:
        """Get the updated config."""
        return self._config

    def needs_restart(self) -> bool:
        """Check if changes require restart."""
        # Plugin changes require restart
        return self._changes_made
