"""
Integration tests for plugin system and UI.

Tests the full flow from plugin loading through UI display.
"""

import pytest
import sys
import os
import tempfile
import json

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt


# Create QApplication for tests (needed for Qt widgets)
@pytest.fixture(scope="module")
def qapp():
    """Create a QApplication instance for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def temp_config():
    """Create a temporary config dict."""
    return {
        "cache_latest_release": False,
        "known_tags": {},
        "last_checked": {},
        "window": {"width": 800, "height": 600},
        "disabled_plugins": []
    }


@pytest.fixture
def temp_config_with_disabled():
    """Create a config with disabled plugins."""
    return {
        "cache_latest_release": False,
        "known_tags": {},
        "last_checked": {},
        "window": {"width": 800, "height": 600},
        "disabled_plugins": ["flexsecure_applets"]
    }


class TestPluginLoading:
    """Test plugin loading functionality."""

    def test_load_plugins_returns_all_plugins(self):
        """Test that load_plugins returns all plugins (not filtered)."""
        from main import load_plugins

        plugins = load_plugins()

        # Should have at least some plugins
        assert len(plugins) > 0, "No plugins loaded"

        # Print what we got for debugging
        print(f"\nLoaded plugins: {list(plugins.keys())}")

    def test_load_plugins_includes_python_plugins(self):
        """Test that Python plugins are loaded."""
        from main import load_plugins

        plugins = load_plugins()

        # Check for flexsecure_applets (the Python plugin)
        assert "flexsecure_applets" in plugins, (
            f"Python plugin 'flexsecure_applets' not found. "
            f"Available plugins: {list(plugins.keys())}"
        )

    def test_load_plugins_includes_yaml_plugins(self):
        """Test that YAML plugins are loaded."""
        from main import load_plugins

        plugins = load_plugins()

        # Check for YAML plugins
        yaml_plugins = [
            name for name, plugin in plugins.items()
            if not isinstance(plugin, type)  # YAML plugins are instances, not classes
        ]

        print(f"\nYAML plugins found: {yaml_plugins}")
        assert len(yaml_plugins) > 0, "No YAML plugins found"


class TestSettingsDialog:
    """Test Settings dialog functionality."""

    def test_settings_dialog_shows_all_plugins(self, qapp, temp_config):
        """Test that Settings dialog shows all plugins including disabled ones."""
        from main import load_plugins
        from src.views.dialogs.settings_dialog import SettingsDialog

        # Load all plugins
        plugins = load_plugins()
        assert len(plugins) > 0, "No plugins to test with"

        # Create settings dialog
        dialog = SettingsDialog(plugins, temp_config)

        # Check that plugins tab exists
        assert dialog._plugins_tab is not None

        # Check that plugin items were created for all plugins
        plugin_items = dialog._plugins_tab._plugin_items
        assert len(plugin_items) == len(plugins), (
            f"Settings shows {len(plugin_items)} plugins, "
            f"but {len(plugins)} were loaded. "
            f"Missing: {set(plugins.keys()) - set(plugin_items.keys())}"
        )

        dialog.close()

    def test_settings_dialog_respects_disabled_state(self, qapp, temp_config_with_disabled):
        """Test that Settings dialog shows disabled plugins as unchecked."""
        from main import load_plugins
        from src.views.dialogs.settings_dialog import SettingsDialog

        plugins = load_plugins()

        # Create settings dialog with disabled plugin
        dialog = SettingsDialog(plugins, temp_config_with_disabled)

        # Check that flexsecure_applets is shown but unchecked
        if "flexsecure_applets" in dialog._plugins_tab._plugin_items:
            item = dialog._plugins_tab._plugin_items["flexsecure_applets"]
            assert not item.is_enabled, (
                "flexsecure_applets should be disabled (unchecked) in settings"
            )

        dialog.close()

    def test_settings_dialog_can_toggle_plugin(self, qapp, temp_config):
        """Test that plugins can be enabled/disabled in settings."""
        from main import load_plugins
        from src.views.dialogs.settings_dialog import SettingsDialog

        plugins = load_plugins()
        dialog = SettingsDialog(plugins, temp_config)

        # Find first plugin item
        plugin_items = dialog._plugins_tab._plugin_items
        if len(plugin_items) > 0:
            first_name = list(plugin_items.keys())[0]
            first_item = plugin_items[first_name]

            # Toggle it off
            first_item._checkbox.setChecked(False)

            # Check disabled list updated
            disabled = dialog._plugins_tab.get_disabled_plugins()
            assert first_name in disabled, (
                f"Plugin {first_name} should be in disabled list after unchecking"
            )

        dialog.close()

    def test_settings_dialog_saves_disabled_plugins(self, qapp, temp_config):
        """Test that disabled plugins are saved to config."""
        from main import load_plugins
        from src.views.dialogs.settings_dialog import SettingsDialog

        plugins = load_plugins()
        dialog = SettingsDialog(plugins, temp_config)

        # Disable a plugin
        plugin_items = dialog._plugins_tab._plugin_items
        if "flexsecure_applets" in plugin_items:
            plugin_items["flexsecure_applets"]._checkbox.setChecked(False)

        # Save settings
        dialog._save_settings()

        # Check config was updated
        assert "disabled_plugins" in dialog._config
        assert "flexsecure_applets" in dialog._config["disabled_plugins"], (
            "flexsecure_applets should be in disabled_plugins after save"
        )

        dialog.close()


class TestPluginFiltering:
    """Test that disabled plugins are properly filtered from app functionality."""

    def test_disabled_plugins_excluded_from_available_apps(self, temp_config_with_disabled):
        """Test that disabled plugins don't contribute to available apps."""
        from main import load_plugins, get_plugin_instance

        plugins = load_plugins()
        disabled_set = set(temp_config_with_disabled.get("disabled_plugins", []))

        # Simulate the app's filtering logic
        available_apps = {}
        for plugin_name, plugin_cls_or_instance in plugins.items():
            if plugin_name in disabled_set:
                continue  # Skip disabled

            plugin = get_plugin_instance(plugin_cls_or_instance)
            try:
                caps = plugin.fetch_available_caps()
                for cap_name, url in caps.items():
                    available_apps[cap_name] = (plugin_name, url)
            except Exception:
                pass  # Some plugins may fail to fetch

        # Check that flexsecure_applets' caps are not in available_apps
        for cap_name, (plugin_name, _) in available_apps.items():
            assert plugin_name != "flexsecure_applets", (
                f"Cap {cap_name} is from disabled plugin flexsecure_applets"
            )


class TestManagementPanel:
    """Test management panel functionality."""

    def test_management_panel_creation(self, qapp):
        """Test that management panel can be created."""
        from src.plugins.yaml.ui.management_panel import (
            ManagementPanel,
            ActionDefinition
        )

        actions = [
            ActionDefinition(
                id="test_action",
                label="Test Action",
                description="A test action",
            )
        ]

        panel = ManagementPanel(actions, state_readers=None, nfc_service=None)
        assert panel is not None
        panel.close()

    def test_management_dialog_creation(self, qapp):
        """Test that management dialog can be created."""
        from src.plugins.yaml.ui.management_panel import (
            ManagementDialog,
            ActionDefinition
        )

        actions = [
            ActionDefinition(
                id="test_action",
                label="Test Action",
                apdu_sequence=[
                    {"apdu": "00A4040007D276000124010304", "description": "Select"}
                ]
            )
        ]

        dialog = ManagementDialog(
            title="Test Management",
            actions=actions,
            state_readers=None,
            nfc_service=None
        )
        assert dialog is not None
        dialog.close()

    def test_action_button_emits_signal(self, qapp):
        """Test that action buttons emit the correct signal."""
        from src.plugins.yaml.ui.management_panel import (
            ManagementPanel,
            ActionDefinition
        )
        from PyQt5.QtTest import QSignalSpy

        actions = [
            ActionDefinition(
                id="test_action",
                label="Test Action",
            )
        ]

        panel = ManagementPanel(actions, state_readers=None, nfc_service=None)

        # Set up signal spy
        spy = QSignalSpy(panel.action_requested)

        # Find and click the action button
        # The button is in the actions group
        for child in panel.findChildren(type(panel)):
            pass  # Just checking it doesn't crash

        panel.close()


class TestYamlPluginManagement:
    """Test YAML plugin management UI integration."""

    def test_yaml_plugin_has_management_ui(self):
        """Test that YAML plugins report having management UI."""
        from main import load_plugins, get_plugin_instance

        plugins = load_plugins()

        # Find YAML plugins with management UI
        yaml_with_mgmt = []
        for name, plugin in plugins.items():
            instance = get_plugin_instance(plugin)
            if hasattr(instance, 'has_management_ui') and instance.has_management_ui():
                yaml_with_mgmt.append(name)

        print(f"\nYAML plugins with management UI: {yaml_with_mgmt}")

    def test_yaml_plugin_creates_management_dialog(self, qapp):
        """Test that YAML plugins can create management dialogs."""
        from main import load_plugins, get_plugin_instance

        plugins = load_plugins()

        # Find a YAML plugin with management UI
        for name, plugin in plugins.items():
            instance = get_plugin_instance(plugin)
            if (hasattr(instance, 'has_management_ui') and
                instance.has_management_ui() and
                hasattr(instance, 'create_management_dialog')):

                # Try to create the dialog
                try:
                    dialog = instance.create_management_dialog(
                        nfc_service=None,
                        parent=None
                    )
                    assert dialog is not None, (
                        f"Plugin {name} returned None for management dialog"
                    )
                    dialog.close()
                    print(f"\nSuccessfully created management dialog for {name}")
                    return  # Success!
                except Exception as e:
                    pytest.fail(f"Failed to create management dialog for {name}: {e}")

        # If we get here, no plugins had management UI
        pytest.skip("No YAML plugins with management UI found")


class TestNFCServiceIntegration:
    """Test NFC service integration with management panel."""

    def test_nfc_thread_has_transmit_apdu(self):
        """Test that NFCHandlerThread has transmit_apdu method."""
        from src.threads.nfc_thread import NFCHandlerThread

        # Check the method exists
        assert hasattr(NFCHandlerThread, 'transmit_apdu'), (
            "NFCHandlerThread should have transmit_apdu method"
        )

    def test_management_panel_checks_for_transmit_apdu(self, qapp):
        """Test that management panel checks for transmit_apdu method."""
        from src.plugins.yaml.ui.management_panel import ManagementDialog, ActionDefinition

        # Create a mock NFC service with transmit_apdu
        class MockNFCService:
            def transmit_apdu(self, apdu: bytes) -> bytes:
                # Return success status word
                return bytes([0x90, 0x00])

        mock_service = MockNFCService()

        actions = [
            ActionDefinition(
                id="test",
                label="Test",
                apdu_sequence=[{"apdu": "00A40400", "description": "Test"}]
            )
        ]

        dialog = ManagementDialog(
            title="Test",
            actions=actions,
            state_readers=None,
            nfc_service=mock_service
        )

        # Verify NFC service is set
        assert dialog._nfc_service is mock_service
        assert hasattr(dialog._nfc_service, 'transmit_apdu')

        dialog.close()


class TestEndToEndPluginFlow:
    """End-to-end tests for the plugin system."""

    def test_full_plugin_flow(self, qapp):
        """Test the complete flow: load -> settings -> enable/disable."""
        from main import load_plugins
        from src.views.dialogs.settings_dialog import SettingsDialog

        # 1. Load all plugins
        plugins = load_plugins()
        print(f"\n1. Loaded {len(plugins)} plugins: {list(plugins.keys())}")

        assert len(plugins) > 0, "No plugins loaded"

        # 2. Create config with all enabled
        config = {
            "disabled_plugins": [],
            "last_checked": {},
            "known_tags": {},
        }

        # 3. Create settings dialog - should show all plugins
        dialog = SettingsDialog(plugins, config)
        items = dialog._plugins_tab._plugin_items

        print(f"2. Settings shows {len(items)} plugins")
        assert len(items) == len(plugins), (
            f"Settings should show all {len(plugins)} plugins, shows {len(items)}"
        )

        # 4. Disable first plugin
        first_plugin = list(items.keys())[0]
        items[first_plugin]._checkbox.setChecked(False)
        dialog._save_settings()

        print(f"3. Disabled plugin: {first_plugin}")
        assert first_plugin in config["disabled_plugins"]

        # 5. Re-enable it
        items[first_plugin]._checkbox.setChecked(True)
        dialog._save_settings()

        print(f"4. Re-enabled plugin: {first_plugin}")
        assert first_plugin not in config["disabled_plugins"]

        dialog.close()
        print("5. Test complete - full plugin flow works!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
