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
)

from src.plugins.yaml import set_debug_enabled, is_debug_enabled
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
        debug_desc.setStyleSheet("color: #666;")
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


class StorageTab(QWidget):
    """Tab for managing secure storage settings."""

    reset_storage_requested = pyqtSignal()
    change_method_requested = pyqtSignal()

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
        self._file_label.setStyleSheet("color: #888;")
        file_layout.addWidget(self._file_label)
        file_layout.addStretch()
        status_layout.addLayout(file_layout)

        # Storage method
        method_layout = QHBoxLayout()
        method_layout.addWidget(QLabel("Encryption method:"))
        method = self._storage_info.get("method", "Unknown")
        method_display = "GPG" if method == "gpg" else "System Keyring" if method == "keyring" else method
        self._method_label = QLabel(method_display)
        self._method_label.setStyleSheet("color: #888;")
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

        layout.addWidget(status_group)

        # Actions group
        actions_group = QGroupBox("Storage Actions")
        actions_layout = QVBoxLayout(actions_group)

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
        reset_desc.setStyleSheet("color: #666;")
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
        info_text.setStyleSheet("color: #555;")
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
        type_label.setStyleSheet("color: #333;")
        info_layout.addWidget(type_label)

        # Description if available
        description = plugin_info.get("description", "")
        if description:
            desc_label = QLabel(description)
            desc_label.setStyleSheet("color: #333;")
            desc_label.setWordWrap(True)
            info_layout.addWidget(desc_label)

        # Cap files count
        caps = plugin_info.get("caps", [])
        if caps:
            caps_label = QLabel(f"Provides: {len(caps)} applet(s)")
            caps_label.setStyleSheet("color: #333;")
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
                    font-size: 16px;
                    font-weight: bold;
                }
                QToolButton:hover {
                    background-color: #5d5d5d;
                    border-radius: 4px;
                }
            """)
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
        github_desc.setStyleSheet("color: #666; margin-left: 20px;")
        github_desc.setWordWrap(True)
        source_layout.addWidget(github_desc)

        layout.addWidget(source_group)

        # Status label
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #888;")
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
        plugins_dir = Path(__file__).parent.parent.parent / "plugins" / "examples"

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

        # Search patterns
        plugin_patterns = [
            "gp-plugin.yaml",
            "gp-plugin.yml",
        ]

        try:
            # First, try direct files
            found_url = None
            found_name = None

            for pattern in plugin_patterns:
                raw_url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/main/{pattern}"
                try:
                    req = urllib.request.Request(raw_url, method="HEAD")
                    urllib.request.urlopen(req, timeout=10)
                    found_url = raw_url
                    found_name = f"{repo_name}.gp-plugin.yaml"
                    break
                except urllib.error.HTTPError:
                    # Try master branch
                    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo_name}/master/{pattern}"
                    try:
                        req = urllib.request.Request(raw_url, method="HEAD")
                        urllib.request.urlopen(req, timeout=10)
                        found_url = raw_url
                        found_name = f"{repo_name}.gp-plugin.yaml"
                        break
                    except urllib.error.HTTPError:
                        continue

            # If not found, search via GitHub API
            if not found_url:
                api_url = f"https://api.github.com/repos/{owner}/{repo_name}/contents"
                req = urllib.request.Request(api_url)
                req.add_header("Accept", "application/vnd.github.v3+json")

                with urllib.request.urlopen(req, timeout=10) as response:
                    contents = json.loads(response.read().decode())

                for item in contents:
                    if item["type"] == "file" and item["name"].endswith(".gp-plugin.yaml"):
                        found_url = item["download_url"]
                        found_name = item["name"]
                        break

            if not found_url:
                self._status_label.setText("")
                QMessageBox.warning(
                    self,
                    "No Plugin Found",
                    f"Could not find a plugin file in repository '{owner}/{repo_name}'.\n\n"
                    "Expected: gp-plugin.yaml or *.gp-plugin.yaml in the repository root.",
                )
                return

            # Download the plugin
            self._status_label.setText(f"Downloading {found_name}...")
            QApplication.processEvents()

            dest = plugins_dir / found_name
            if dest.exists():
                reply = QMessageBox.question(
                    self,
                    "File Exists",
                    f"Plugin '{found_name}' already exists. Overwrite?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    self._status_label.setText("")
                    return

            plugins_dir.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(found_url, dest)
            self._result_path = str(dest)
            self._status_label.setText("Downloaded successfully!")
            self.accept()

        except urllib.error.URLError as e:
            self._status_label.setText("")
            QMessageBox.critical(self, "Network Error", f"Failed to access GitHub:\n{e.reason}")
        except Exception as e:
            self._status_label.setText("")
            QMessageBox.critical(self, "Error", f"Failed to import plugin:\n{e}")

    def get_imported_path(self) -> str:
        """Get the path to the imported plugin file."""
        return self._result_path


class PluginsTab(QWidget):
    """Tab for managing plugins."""

    plugins_changed = pyqtSignal()
    edit_plugin = pyqtSignal(str, str)  # plugin_name, yaml_path
    refresh_requested = pyqtSignal()  # request parent to refresh plugins

    def __init__(
        self,
        plugin_map: Dict[str, Any],
        disabled_plugins: List[str],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._plugin_map = plugin_map
        self._disabled_plugins = set(disabled_plugins)
        self._plugin_items: Dict[str, PluginItem] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header = QLabel(
            "Enable or disable plugins. Disabled plugins will not load on next startup."
        )
        header.setStyleSheet("color: #555;margin-bottom: 10px;")
        header.setWordWrap(True)
        layout.addWidget(header)

        # Scroll area for plugins
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(4)

        # Add plugin items
        for plugin_name, plugin_cls_or_instance in self._plugin_map.items():
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

    def _on_import_plugin(self):
        """Handle import plugin request."""
        dialog = ImportPluginDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            imported_path = dialog.get_imported_path()
            if imported_path:
                QMessageBox.information(
                    self,
                    "Plugin Imported",
                    f"Plugin imported successfully!\n\nFile: {Path(imported_path).name}\n\n"
                    "The application will reload plugins to apply changes.",
                )
                self.plugins_changed.emit()
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
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to delete: {e}")


class SettingsDialog(QDialog):
    """
    Main settings dialog with tabbed interface.
    """

    edit_plugin_requested = pyqtSignal(str)  # yaml_path
    refresh_plugins_requested = pyqtSignal()
    reset_storage_requested = pyqtSignal()

    def __init__(
        self,
        plugin_map: Dict[str, Any],
        config: Dict[str, Any],
        storage_info: Optional[Dict[str, Any]] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._plugin_map = plugin_map
        self._config = config
        self._storage_info = storage_info or {}
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
        tabs.addTab(self._storage_tab, "Storage")

        # Plugins tab
        disabled = self._config.get("disabled_plugins", [])
        self._plugins_tab = PluginsTab(self._plugin_map, disabled)
        self._plugins_tab.plugins_changed.connect(self._on_changes_made)
        self._plugins_tab.edit_plugin.connect(self._on_edit_plugin)
        self._plugins_tab.refresh_requested.connect(self._on_refresh_requested)
        tabs.addTab(self._plugins_tab, "Plugins")

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
        self.refresh_plugins_requested.emit()

    def _on_reset_storage(self):
        """Handle reset storage request - emit to main window."""
        self.reset_storage_requested.emit()

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
