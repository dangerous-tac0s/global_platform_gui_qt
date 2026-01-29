"""
Unit tests for model classes.
"""

import pytest
from src.models.card import CardState, CardInfo, CardMemory, CardConnectionState, CardIdentifier
from src.models.applet import AppletInfo, InstalledApplet, InstallResult, InstallStatus
from src.models.config import ConfigData, WindowConfig, PluginCache
import time


class TestCardModels:
    """Tests for card-related models."""

    def test_card_info_normalizes_uid(self):
        """UID should be normalized to uppercase without spaces."""
        # CardInfo now takes identifier parameter, supports legacy string construction
        info = CardInfo(identifier="04 aa bb cc dd")
        assert info.uid == "04AABBCCDD"

        # Also test with CardIdentifier directly
        identifier = CardIdentifier(uid="04 aa bb cc dd")
        info2 = CardInfo(identifier=identifier)
        assert info2.uid == "04AABBCCDD"

    def test_card_memory_is_available(self):
        """Memory should report as available when values are set."""
        memory = CardMemory(persistent_free=1000, persistent_total=2000)
        assert memory.is_available is True

        memory_unavailable = CardMemory()
        assert memory_unavailable.is_available is False

    def test_card_memory_can_fit_applet(self):
        """Should correctly check if applet fits."""
        memory = CardMemory(
            persistent_free=10000,
            persistent_total=20000,
            transient_reset=2000,
            transient_deselect=1000,
        )

        # Should fit
        assert memory.can_fit_applet(5000, 1000) is True

        # Too much persistent
        assert memory.can_fit_applet(15000, 0) is False

        # Too much transient
        assert memory.can_fit_applet(1000, 3000) is False

    def test_card_memory_percent_free(self):
        """Should calculate percentage correctly."""
        memory = CardMemory(persistent_free=500, persistent_total=1000)
        assert memory.persistent_percent_free == 50.0

    def test_card_state_is_connected(self):
        """Should correctly report connection state."""
        state = CardState(connection_state=CardConnectionState.CONNECTED)
        assert state.is_connected is True
        assert state.is_authenticated is False

        state_auth = CardState(connection_state=CardConnectionState.AUTHENTICATED)
        assert state_auth.is_connected is True
        assert state_auth.is_authenticated is True

        state_disc = CardState(connection_state=CardConnectionState.DISCONNECTED)
        assert state_disc.is_connected is False

    def test_card_state_has_applet(self):
        """Should check for installed applets by AID."""
        state = CardState(
            installed_applets={"A0000008466D656D6F727901": "1.0"}
        )
        assert state.has_applet("A0000008466D656D6F727901") is True
        assert state.has_applet("a0000008466d656d6f727901") is True  # Case insensitive
        assert state.has_applet("DEADBEEF") is False


class TestAppletModels:
    """Tests for applet-related models."""

    def test_applet_info_normalizes_aid(self):
        """AID should be normalized."""
        info = AppletInfo(
            cap_name="test.cap",
            aid="a0 00 00 08",
            plugin_name="test",
            download_url="http://example.com/test.cap",
        )
        assert info.aid == "A0000008"

    def test_applet_info_mutual_exclusion_set(self):
        """Mutual exclusion should be converted to set."""
        info = AppletInfo(
            cap_name="FIDO2.cap",
            aid="A0000006472F000101",
            plugin_name="flexsecure",
            download_url="http://example.com",
            mutual_exclusion=["U2FApplet.cap"],
        )
        assert isinstance(info.mutual_exclusion, set)
        assert "U2FApplet.cap" in info.mutual_exclusion

    def test_install_result_success(self):
        """Should correctly report success status."""
        result = InstallResult(
            status=InstallStatus.SUCCESS,
            message="Installation complete",
        )
        assert result.success is True
        assert result.was_blocked is False

    def test_install_result_blocked(self):
        """Should correctly identify blocked operations."""
        result = InstallResult(
            status=InstallStatus.BLOCKED_MUTUAL_EXCLUSION,
            message="Conflicts with U2FApplet",
        )
        assert result.success is False
        assert result.was_blocked is True


class TestConfigModels:
    """Tests for configuration models."""

    def test_window_config_to_dict(self):
        """WindowConfig should serialize correctly."""
        config = WindowConfig(width=1024, height=768)
        d = config.to_dict()
        assert d == {"width": 1024, "height": 768}

    def test_window_config_from_dict(self):
        """WindowConfig should deserialize correctly."""
        config = WindowConfig.from_dict({"width": 1920, "height": 1080})
        assert config.width == 1920
        assert config.height == 1080

    def test_plugin_cache_is_stale(self):
        """Should correctly detect stale cache."""
        # Fresh cache
        cache = PluginCache(last_checked=time.time())
        assert cache.is_stale(max_age_hours=24) is False

        # Stale cache
        old_cache = PluginCache(last_checked=time.time() - 100000)
        assert old_cache.is_stale(max_age_hours=24) is True

        # Empty cache
        empty_cache = PluginCache()
        assert empty_cache.is_stale() is True

    def test_config_data_known_tags(self):
        """Should manage known tags correctly."""
        config = ConfigData()

        # Initially unknown
        assert config.is_known_tag("04AABBCCDD") is False

        # Set as known with default key
        config.set_tag_key_type("04aabbccdd", True)
        assert config.is_known_tag("04AABBCCDD") is True
        assert config.uses_default_key("04AABBCCDD") is True

        # Set as custom key
        config.set_tag_key_type("04AABBCCDD", False)
        assert config.uses_default_key("04AABBCCDD") is False

    def test_config_data_round_trip(self):
        """Config should survive serialization round trip."""
        original = ConfigData(
            cache_latest_release=True,
            known_tags={"04AABBCCDD": True},
        )
        original.window.width = 1024
        original.window.height = 768

        d = original.to_dict()
        restored = ConfigData.from_dict(d)

        assert restored.cache_latest_release is True
        assert restored.known_tags == {"04AABBCCDD": True}
        assert restored.window.width == 1024
        assert restored.window.height == 768
