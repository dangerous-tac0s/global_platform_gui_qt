"""
Tests for AppletController.
"""

import pytest
from unittest.mock import Mock, MagicMock

from src.controllers.applet_controller import (
    AppletController,
    UNSUPPORTED_APPS,
    MUTUAL_EXCLUSIVITY_RULES,
)
from src.models.applet import InstallStatus
from src.models.card import CardMemory
from src.events.event_bus import (
    EventBus,
    InstalledAppsUpdatedEvent,
    OperationResultEvent,
    ErrorEvent,
)


@pytest.fixture
def event_bus():
    """Create a fresh EventBus for testing."""
    EventBus.reset_instance()
    bus = EventBus.instance()
    bus.enable_logging(True)
    yield bus
    EventBus.reset_instance()


@pytest.fixture
def applet_controller(event_bus):
    """Create an AppletController for testing."""
    return AppletController(event_bus=event_bus)


@pytest.fixture
def mock_plugin_class():
    """Create a mock plugin class."""
    class MockPlugin:
        def __init__(self):
            self.cap_name = None

        def set_cap_name(self, name):
            self.cap_name = name

        def pre_install(self, nfc_thread=None):
            pass

        def post_install(self):
            pass

        def pre_uninstall(self):
            pass

        def create_dialog(self, parent):
            return None

        def get_result(self):
            return {}

        def get_aid_list(self):
            return ["A0000001234567"]

        def get_cap_for_aid(self, aid):
            if aid.upper().replace(" ", "") == "A0000001234567":
                return "TestApp.cap"
            return None

    return MockPlugin


class TestAppletControllerBasics:
    """Test basic AppletController functionality."""

    def test_initial_state(self, applet_controller):
        """Test initial state is empty."""
        assert applet_controller.available_apps == {}
        assert applet_controller.installed_apps == {}
        assert applet_controller.installed_cap_names == []

    def test_register_plugin(self, applet_controller, mock_plugin_class):
        """Test plugin registration."""
        applet_controller.register_plugin(
            name="test_plugin",
            plugin_class=mock_plugin_class,
            caps={"TestApp.cap": "https://example.com/TestApp.cap"},
            descriptions={"TestApp.cap": "# Test App\nA test applet."},
            storage={"TestApp.cap": {"persistent": 5000, "transient": 1000}},
        )

        assert "TestApp.cap" in applet_controller.available_apps
        info = applet_controller.get_applet_info("TestApp.cap")
        assert info is not None
        assert info.plugin_name == "test_plugin"
        assert info.storage_persistent == 5000

    def test_unsupported_apps_filtered(self, applet_controller, mock_plugin_class):
        """Test that unsupported apps are filtered out."""
        applet_controller.register_plugin(
            name="test_plugin",
            plugin_class=mock_plugin_class,
            caps={
                "TestApp.cap": "https://example.com/TestApp.cap",
                "FIDO2.cap": "https://example.com/FIDO2.cap",  # Unsupported
            },
            descriptions={},
            storage={},
        )

        available = applet_controller.get_available_applets()
        assert "TestApp.cap" in available
        assert "FIDO2.cap" not in available


class TestValidation:
    """Test installation validation."""

    def test_validate_unknown_applet(self, applet_controller):
        """Test validation fails for unknown applet."""
        result = applet_controller.validate_install("Unknown.cap")
        assert result.status == InstallStatus.FAILED
        assert "Unknown" in result.message

    def test_validate_mutual_exclusivity(self, applet_controller, mock_plugin_class):
        """Test mutual exclusivity check."""
        # Register U2F app
        applet_controller.register_plugin(
            name="test_plugin",
            plugin_class=mock_plugin_class,
            caps={"vivokey-u2f.cap": "https://example.com/u2f.cap"},
            descriptions={},
            storage={},
        )

        # Simulate FIDO2 being installed
        applet_controller._installed_cap_names = ["FIDO2.cap"]

        result = applet_controller.validate_install("vivokey-u2f.cap")
        assert result.status == InstallStatus.BLOCKED_MUTUAL_EXCLUSION
        assert "FIDO2" in result.message

    def test_validate_storage_persistent(self, applet_controller, mock_plugin_class):
        """Test storage validation for persistent memory."""
        applet_controller.register_plugin(
            name="test_plugin",
            plugin_class=mock_plugin_class,
            caps={"BigApp.cap": "https://example.com/big.cap"},
            descriptions={},
            storage={"BigApp.cap": {"persistent": 50000, "transient": 1000}},
        )

        # Card with insufficient storage
        memory = CardMemory(
            persistent_free=10000,
            persistent_total=50000,
            transient_reset=2000,
            transient_deselect=2000,
        )

        result = applet_controller.validate_install("BigApp.cap", memory)
        assert result.status == InstallStatus.BLOCKED_INSUFFICIENT_STORAGE
        assert "persistent" in result.message.lower()

    def test_validate_storage_transient(self, applet_controller, mock_plugin_class):
        """Test storage validation for transient memory."""
        applet_controller.register_plugin(
            name="test_plugin",
            plugin_class=mock_plugin_class,
            caps={"BigApp.cap": "https://example.com/big.cap"},
            descriptions={},
            storage={"BigApp.cap": {"persistent": 1000, "transient": 5000}},
        )

        # Card with insufficient transient
        memory = CardMemory(
            persistent_free=50000,
            persistent_total=100000,
            transient_reset=1000,
            transient_deselect=1000,
        )

        result = applet_controller.validate_install("BigApp.cap", memory)
        assert result.status == InstallStatus.BLOCKED_INSUFFICIENT_STORAGE
        assert "transient" in result.message.lower()

    def test_validate_success(self, applet_controller, mock_plugin_class):
        """Test successful validation."""
        applet_controller.register_plugin(
            name="test_plugin",
            plugin_class=mock_plugin_class,
            caps={"TestApp.cap": "https://example.com/test.cap"},
            descriptions={},
            storage={"TestApp.cap": {"persistent": 5000, "transient": 1000}},
        )

        memory = CardMemory(
            persistent_free=50000,
            persistent_total=100000,
            transient_reset=5000,
            transient_deselect=5000,
        )

        result = applet_controller.validate_install("TestApp.cap", memory)
        assert result.status == InstallStatus.SUCCESS


class TestInstallWorkflow:
    """Test installation workflow."""

    def test_prepare_install(self, applet_controller, mock_plugin_class, event_bus):
        """Test install preparation."""
        applet_controller.register_plugin(
            name="test_plugin",
            plugin_class=mock_plugin_class,
            caps={"TestApp.cap": "https://example.com/test.cap"},
            descriptions={},
            storage={},
        )

        result = applet_controller.prepare_install("TestApp.cap")
        assert result.status == InstallStatus.SUCCESS
        assert applet_controller._current_plugin is not None

    def test_on_install_complete(self, applet_controller, mock_plugin_class, event_bus):
        """Test install completion handling."""
        applet_controller.register_plugin(
            name="test_plugin",
            plugin_class=mock_plugin_class,
            caps={"TestApp.cap": "https://example.com/test.cap"},
            descriptions={},
            storage={},
        )

        applet_controller.prepare_install("TestApp.cap")
        event_bus.clear_event_log()

        applet_controller.on_install_complete(True, "Installed successfully")

        events = event_bus.get_event_log()
        result_events = [e for e in events if isinstance(e, OperationResultEvent)]
        assert len(result_events) == 1
        assert result_events[0].success is True
        assert result_events[0].operation_type == "install"


class TestUninstallWorkflow:
    """Test uninstallation workflow."""

    def test_prepare_uninstall_unknown(self, applet_controller):
        """Test uninstall preparation for unknown app."""
        result = applet_controller.prepare_uninstall("Unknown: A0000001234567")
        assert result.status == InstallStatus.SUCCESS
        assert "A0000001234567" in result.message

    def test_prepare_uninstall_with_plugin(self, applet_controller, mock_plugin_class):
        """Test uninstall preparation with plugin."""
        applet_controller.register_plugin(
            name="test_plugin",
            plugin_class=mock_plugin_class,
            caps={"TestApp.cap": "https://example.com/test.cap"},
            descriptions={},
            storage={},
        )

        result = applet_controller.prepare_uninstall("TestApp.cap")
        assert result.status == InstallStatus.SUCCESS

    def test_get_fallback_aid(self, applet_controller, mock_plugin_class):
        """Test getting fallback AID for uninstall."""
        applet_controller.register_plugin(
            name="test_plugin",
            plugin_class=mock_plugin_class,
            caps={"TestApp.cap": "https://example.com/test.cap"},
            descriptions={},
            storage={},
        )

        applet_controller.prepare_uninstall("TestApp.cap")
        aid = applet_controller.get_fallback_aid()
        assert aid == "A0000001234567"


class TestInstalledAppsTracking:
    """Test installed apps tracking."""

    def test_update_installed_apps(self, applet_controller, mock_plugin_class, event_bus):
        """Test updating installed apps list."""
        applet_controller.register_plugin(
            name="test_plugin",
            plugin_class=mock_plugin_class,
            caps={"TestApp.cap": "https://example.com/test.cap"},
            descriptions={},
            storage={},
        )

        installed = {
            "A0000001234567": "1.0",
            "A0000009999999": None,
        }

        applet_controller.update_installed_apps(installed)

        assert applet_controller.installed_apps == installed
        assert "TestApp.cap" in applet_controller.installed_cap_names

        events = event_bus.get_event_log()
        updated_events = [e for e in events if isinstance(e, InstalledAppsUpdatedEvent)]
        assert len(updated_events) == 1

    def test_get_installed_display_info(self, applet_controller, mock_plugin_class):
        """Test getting display info for installed apps."""
        applet_controller.register_plugin(
            name="test_plugin",
            plugin_class=mock_plugin_class,
            caps={"TestApp.cap": "https://example.com/test.cap"},
            descriptions={},
            storage={},
        )

        installed = {
            "A0000001234567": "1.0",
            "A0000009999999": None,
        }
        applet_controller.update_installed_apps(installed)

        display_info = applet_controller.get_installed_display_info()
        assert len(display_info) == 2

        # Find the resolved app
        resolved = [d for d in display_info if d['cap_name'] == "TestApp.cap"]
        assert len(resolved) == 1
        assert resolved[0]['display_name'] == "TestApp.cap"

        # Find the unknown app
        unknown = [d for d in display_info if d['cap_name'] is None]
        assert len(unknown) == 1
        assert "Unknown" in unknown[0]['display_name']


class TestAvailability:
    """Test availability filtering."""

    def test_installed_apps_filtered(self, applet_controller, mock_plugin_class):
        """Test that installed apps are filtered from available list."""
        applet_controller.register_plugin(
            name="test_plugin",
            plugin_class=mock_plugin_class,
            caps={
                "App1.cap": "https://example.com/app1.cap",
                "App2.cap": "https://example.com/app2.cap",
            },
            descriptions={},
            storage={},
        )

        # Simulate App1 being installed
        applet_controller._installed_cap_names = ["App1.cap"]

        available = applet_controller.get_available_applets()
        assert "App1.cap" not in available
        assert "App2.cap" in available
