"""
Settings Dialog

Provides application settings including plugin management.
"""

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
)

from src.plugins.yaml import set_debug_enabled, is_debug_enabled


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
        debug_desc.setStyleSheet("color: #888; font-size: 10px;")
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
        type_label.setStyleSheet("color: #000; font-size: 10px;")
        info_layout.addWidget(type_label)

        # Description if available
        description = plugin_info.get("description", "")
        if description:
            desc_label = QLabel(description)
            desc_label.setStyleSheet("color: #000; font-size: 10px;")
            desc_label.setWordWrap(True)
            info_layout.addWidget(desc_label)

        # Cap files count
        caps = plugin_info.get("caps", [])
        if caps:
            caps_label = QLabel(f"Provides: {len(caps)} applet(s)")
            caps_label.setStyleSheet("color: #000; font-size: 10px;")
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


class PluginsTab(QWidget):
    """Tab for managing plugins."""

    plugins_changed = pyqtSignal()

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
        header.setStyleSheet("color: #ccc; margin-bottom: 10px;")
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

            item = PluginItem(plugin_name, plugin_info, enabled)
            item.toggled.connect(self._on_plugin_toggled)
            self._plugin_items[plugin_name] = item
            scroll_layout.addWidget(item)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll)

        # Buttons
        btn_layout = QHBoxLayout()

        enable_all_btn = QPushButton("Enable All")
        enable_all_btn.clicked.connect(self._enable_all)
        btn_layout.addWidget(enable_all_btn)

        disable_all_btn = QPushButton("Disable All")
        disable_all_btn.clicked.connect(self._disable_all)
        btn_layout.addWidget(disable_all_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _get_plugin_info(self, plugin_name: str, plugin_cls_or_instance) -> Dict[str, Any]:
        """Extract plugin info for display."""
        info = {"type": "Python", "description": "", "caps": []}

        # Check if it's a YAML plugin (instance) or Python plugin (class)
        if isinstance(plugin_cls_or_instance, type):
            info["type"] = "Python"
            try:
                instance = plugin_cls_or_instance()
                if hasattr(instance, "fetch_available_caps"):
                    # Don't actually fetch - just indicate it provides caps
                    info["caps"] = ["..."]
            except Exception:
                pass
        else:
            # YAML plugin instance
            info["type"] = "YAML"
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


class SettingsDialog(QDialog):
    """
    Main settings dialog with tabbed interface.
    """

    def __init__(
        self,
        plugin_map: Dict[str, Any],
        config: Dict[str, Any],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._plugin_map = plugin_map
        self._config = config
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

        # Plugins tab
        disabled = self._config.get("disabled_plugins", [])
        self._plugins_tab = PluginsTab(self._plugin_map, disabled)
        self._plugins_tab.plugins_changed.connect(self._on_changes_made)
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

    def get_config(self) -> Dict[str, Any]:
        """Get the updated config."""
        return self._config

    def needs_restart(self) -> bool:
        """Check if changes require restart."""
        # Plugin changes require restart
        return self._changes_made
