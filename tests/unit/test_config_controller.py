"""
Tests for ConfigController.
"""

import pytest
import time
from unittest.mock import Mock

from src.controllers.config_controller import ConfigController, DEFAULT_KEY
from src.services.config_service import MockConfigService
from src.models.config import ConfigData, PluginCache, CardConfigEntry
from src.models.card import CardIdentifier


@pytest.fixture
def mock_config_service():
    """Create a mock config service."""
    return MockConfigService()


@pytest.fixture
def config_controller(mock_config_service):
    """Create a ConfigController with mock service."""
    return ConfigController(config_service=mock_config_service)


class TestConfigControllerBasics:
    """Test basic ConfigController functionality."""

    def test_initial_config_loaded(self, config_controller):
        """Test that config is loaded on first access."""
        config = config_controller.config
        assert config is not None
        assert isinstance(config, ConfigData)

    def test_save_and_reload(self, config_controller):
        """Test saving and reloading config."""
        config_controller.config.window.width = 1200
        config_controller.save()

        # Reload
        config_controller.reload()
        assert config_controller.config.window.width == 1200


class TestWindowState:
    """Test window state management."""

    def test_get_window_size(self, config_controller):
        """Test getting window size."""
        width, height = config_controller.get_window_size()
        assert width == 800  # Default
        assert height == 600  # Default

    def test_set_window_size(self, config_controller):
        """Test setting window size."""
        config_controller.set_window_size(1024, 768)

        width, height = config_controller.get_window_size()
        assert width == 1024
        assert height == 768


class TestKnownTags:
    """Test known tags management."""

    def test_is_known_tag_false(self, config_controller):
        """Test unknown tag returns False."""
        assert config_controller.is_known_tag("UNKNOWN123") is False

    def test_set_uses_default_key(self, config_controller):
        """Test setting default key flag."""
        config_controller.set_uses_default_key("04AABBCCDD", True)

        assert config_controller.is_known_tag("04AABBCCDD") is True
        assert config_controller.uses_default_key("04AABBCCDD") is True

    def test_update_known_tag_with_default_key(self, config_controller):
        """Test updating tag with default key."""
        config_controller.update_known_tag("04AABBCCDD", DEFAULT_KEY)

        assert config_controller.uses_default_key("04AABBCCDD") is True

    def test_update_known_tag_with_custom_key(self, config_controller):
        """Test updating tag with custom key."""
        config_controller.update_known_tag("04AABBCCDD", "CUSTOMKEY" * 4)

        assert config_controller.uses_default_key("04AABBCCDD") is False

    def test_get_known_tags(self, config_controller):
        """Test getting all known tags."""
        config_controller.set_uses_default_key("TAG1", True)
        config_controller.set_uses_default_key("TAG2", False)

        tags = config_controller.get_known_tags()
        assert "TAG1" in tags
        assert "TAG2" in tags
        assert tags["TAG1"] is True
        assert tags["TAG2"] is False


class TestCPLCAwareConfig:
    """Test CPLC-aware configuration."""

    def test_get_card_config_by_cplc(self, config_controller):
        """Test getting card config by CPLC hash."""
        # Set up config with CPLC entry using CardConfigEntry
        config_controller.config.known_cards["CPLC_1234567890ABCDEF"] = CardConfigEntry(
            uses_default_key=True,
            cplc_hash="CPLC_1234567890ABCDEF",
        )

        identifier = CardIdentifier(cplc_hash="CPLC_1234567890ABCDEF")
        config = config_controller.get_card_config(identifier)

        assert config is not None
        assert config["uses_default_key"] is True

    def test_get_card_config_fallback_to_uid(self, config_controller):
        """Test getting card config falls back to UID."""
        # Set up config with UID entry
        config_controller.set_uses_default_key("04AABBCCDD", False)

        identifier = CardIdentifier(uid="04AABBCCDD")
        config = config_controller.get_card_config(identifier)

        # Should find the config
        assert config is not None
        assert config["uses_default_key"] is False

    def test_upgrade_card_to_cplc(self, config_controller):
        """Test upgrading card from UID to CPLC."""
        # Set up UID-based entry
        config_controller.set_uses_default_key("04AABBCCDD", True)

        # Upgrade to CPLC
        result = config_controller.upgrade_card_to_cplc(
            uid="04AABBCCDD",
            cplc_hash="CPLC_1234567890ABCDEF",
        )

        assert result is True

        # Check that CPLC entry exists
        identifier = CardIdentifier(cplc_hash="CPLC_1234567890ABCDEF")
        config = config_controller.get_card_config(identifier)
        assert config is not None
        assert config["uses_default_key"] is True


class TestPluginCache:
    """Test plugin cache management."""

    def test_no_cache_returns_none(self, config_controller):
        """Test that missing cache returns None."""
        cache = config_controller.get_plugin_cache("nonexistent")
        assert cache is None

    def test_no_cache_is_stale(self, config_controller):
        """Test that missing cache is considered stale."""
        assert config_controller.is_plugin_cache_stale("nonexistent") is True

    def test_update_plugin_cache(self, config_controller):
        """Test updating plugin cache."""
        config_controller.update_plugin_cache(
            plugin_name="test_plugin",
            apps={"App1.cap": "https://example.com/app1.cap"},
            release="v1.0.0",
        )

        cache = config_controller.get_plugin_cache("test_plugin")
        assert cache is not None
        assert cache.release == "v1.0.0"
        assert "App1.cap" in cache.apps

    def test_get_cached_apps(self, config_controller):
        """Test getting cached apps."""
        config_controller.update_plugin_cache(
            plugin_name="test_plugin",
            apps={
                "App1.cap": "https://example.com/app1.cap",
                "App2.cap": "https://example.com/app2.cap",
            },
            release="v1.0.0",
        )

        apps = config_controller.get_cached_apps("test_plugin")
        assert "App1.cap" in apps
        assert "App2.cap" in apps

    def test_get_cached_release(self, config_controller):
        """Test getting cached release."""
        config_controller.update_plugin_cache(
            plugin_name="test_plugin",
            apps={},
            release="v2.0.0",
        )

        release = config_controller.get_cached_release("test_plugin")
        assert release == "v2.0.0"

    def test_fresh_cache_not_stale(self, config_controller):
        """Test that fresh cache is not stale."""
        config_controller.update_plugin_cache(
            plugin_name="test_plugin",
            apps={},
            release="v1.0.0",
        )

        assert config_controller.is_plugin_cache_stale("test_plugin") is False


class TestRawConfigAccess:
    """Test raw config access for legacy compatibility."""

    def test_get_raw_config(self, config_controller):
        """Test getting raw config dict."""
        raw = config_controller.get_raw_config()
        assert isinstance(raw, dict)
        assert "window" in raw
        assert "_version" in raw

    def test_get_raw_value(self, config_controller):
        """Test getting raw value."""
        value = config_controller.get_raw_value("window.width")
        assert value == 800  # Default

    def test_get_raw_value_default(self, config_controller):
        """Test getting raw value with default."""
        value = config_controller.get_raw_value("nonexistent.key", default="fallback")
        assert value == "fallback"

    def test_set_raw_value(self, config_controller):
        """Test setting raw value."""
        config_controller.set_raw_value("window.width", 1920)

        value = config_controller.get_raw_value("window.width")
        assert value == 1920
