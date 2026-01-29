"""
Tests for CardController.
"""

import pytest
from unittest.mock import Mock, MagicMock

from src.controllers.card_controller import CardController, AuthState, DEFAULT_KEY
from src.models.card import CardIdentifier, CardState, CardConnectionState, CardMemory
from src.events.event_bus import (
    EventBus,
    CardPresenceEvent,
    CardStateChangedEvent,
    KeyPromptEvent,
    KeyValidatedEvent,
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
def card_controller(mock_storage_service, mock_config_service, event_bus):
    """Create a CardController with mock services."""
    return CardController(
        storage_service=mock_storage_service,
        config_service=mock_config_service,
        event_bus=event_bus,
    )


class TestCardControllerBasics:
    """Test basic CardController functionality."""

    def test_initial_state(self, card_controller):
        """Test initial state is disconnected."""
        assert card_controller.state.connection_state == CardConnectionState.DISCONNECTED
        assert card_controller.card_id is None
        assert card_controller.key is None
        assert not card_controller.is_authenticated

    def test_set_reader(self, card_controller):
        """Test setting reader name."""
        card_controller.set_reader("Test Reader 0")
        assert card_controller._current_reader == "Test Reader 0"


class TestCardDetection:
    """Test card detection handling."""

    def test_on_card_detected_jcop(self, card_controller, event_bus):
        """Test detecting a JCOP card."""
        card_controller.on_card_detected(
            uid="04AABBCCDD",
            is_jcop=True,
            reader_name="Test Reader 0",
        )

        # Check state updated
        assert card_controller.state.connection_state == CardConnectionState.CONNECTED
        assert card_controller.card_id == "04AABBCCDD"
        assert card_controller._auth_state == AuthState.DETECTED

        # Check event emitted
        events = event_bus.get_event_log()
        presence_events = [e for e in events if isinstance(e, CardPresenceEvent)]
        assert len(presence_events) == 1
        assert presence_events[0].present is True
        assert presence_events[0].uid == "04AABBCCDD"
        assert presence_events[0].is_jcop_compatible is True

    def test_on_card_detected_non_jcop(self, card_controller, event_bus):
        """Test detecting a non-JCOP card."""
        card_controller.on_card_detected(
            uid="04AABBCCDD",
            is_jcop=False,
            reader_name="Test Reader 0",
        )

        # Card should not be usable
        assert card_controller.state.connection_state == CardConnectionState.DISCONNECTED
        assert card_controller._auth_state == AuthState.IDLE

    def test_on_card_removed(self, card_controller, event_bus):
        """Test card removal handling."""
        # First detect a card
        card_controller.on_card_detected(uid="04AABBCCDD", is_jcop=True)
        event_bus.clear_event_log()

        # Then remove it
        card_controller.on_card_removed()

        # Check state reset
        assert card_controller.state.connection_state == CardConnectionState.DISCONNECTED
        assert card_controller.card_id is None
        assert card_controller._auth_state == AuthState.IDLE

        # Check events emitted
        events = event_bus.get_event_log()
        presence_events = [e for e in events if isinstance(e, CardPresenceEvent)]
        assert len(presence_events) == 1
        assert presence_events[0].present is False


class TestKeyManagement:
    """Test key retrieval and authentication."""

    def test_request_key_from_storage(self, card_controller, mock_storage_service, event_bus):
        """Test getting key from storage."""
        # Store a key
        mock_storage_service.set_key_for_tag("04AABBCCDD", "DEADBEEF" * 4)

        # Detect card
        card_controller.on_card_detected(uid="04AABBCCDD", is_jcop=True)

        # Request key with callback
        key_received = []
        card_controller.request_key(lambda k: key_received.append(k))

        # Key should be retrieved from storage
        assert len(key_received) == 1
        assert key_received[0] == "DEADBEEF" * 4

    def test_request_key_prompts_user(self, card_controller, event_bus):
        """Test that unknown card prompts for key."""
        # Detect card
        card_controller.on_card_detected(uid="04AABBCCDD", is_jcop=True)
        event_bus.clear_event_log()

        # Request key
        callback = Mock()
        card_controller.request_key(callback)

        # Should emit key prompt event
        events = event_bus.get_event_log()
        prompt_events = [e for e in events if isinstance(e, KeyPromptEvent)]
        assert len(prompt_events) == 1
        assert prompt_events[0].uid == "04AABBCCDD"

        # Callback not called yet (waiting for user)
        callback.assert_not_called()

        # State should be awaiting key
        assert card_controller._auth_state == AuthState.AWAITING_KEY

    def test_set_key_after_prompt(self, card_controller, event_bus):
        """Test setting key after user prompt."""
        # Detect card and request key
        card_controller.on_card_detected(uid="04AABBCCDD", is_jcop=True)

        callback = Mock()
        card_controller.request_key(callback)

        # Simulate user providing key
        card_controller.set_key("CAFEBABE" * 4)

        # Callback should be called with key
        callback.assert_called_once_with("CAFEBABE" * 4)

        # State should advance
        assert card_controller._auth_state == AuthState.AUTHENTICATING
        assert card_controller.key == "CAFEBABE" * 4

    def test_key_validated_success(self, card_controller, event_bus):
        """Test successful key validation."""
        # Setup: detect card, get key
        card_controller.on_card_detected(uid="04AABBCCDD", is_jcop=True)
        card_controller.request_key(lambda k: None)
        card_controller.set_key(DEFAULT_KEY)
        event_bus.clear_event_log()

        # Validate key
        card_controller.on_key_validated(valid=True)

        # Check state
        assert card_controller.is_authenticated
        assert card_controller._auth_state == AuthState.AUTHENTICATED
        assert card_controller.state.connection_state == CardConnectionState.AUTHENTICATED

        # Check events
        events = event_bus.get_event_log()
        validated_events = [e for e in events if isinstance(e, KeyValidatedEvent)]
        assert len(validated_events) == 1
        assert validated_events[0].valid is True

    def test_key_validated_failure(self, card_controller, event_bus):
        """Test failed key validation."""
        # Setup: detect card, get key
        card_controller.on_card_detected(uid="04AABBCCDD", is_jcop=True)
        card_controller.request_key(lambda k: None)
        card_controller.set_key("WRONGKEY" * 4)
        event_bus.clear_event_log()

        # Fail validation
        card_controller.on_key_validated(valid=False, error_message="Bad key")

        # Check state
        assert not card_controller.is_authenticated
        assert card_controller._auth_state == AuthState.AWAITING_KEY
        assert card_controller.state.connection_state == CardConnectionState.ERROR

        # Check events
        events = event_bus.get_event_log()
        validated_events = [e for e in events if isinstance(e, KeyValidatedEvent)]
        error_events = [e for e in events if isinstance(e, ErrorEvent)]
        prompt_events = [e for e in events if isinstance(e, KeyPromptEvent)]

        assert len(validated_events) == 1
        assert validated_events[0].valid is False

        assert len(error_events) == 1
        assert "Bad key" in error_events[0].message

        # Should re-prompt for key
        assert len(prompt_events) == 1


class TestCPLCHandling:
    """Test CPLC-based identification."""

    def test_on_cplc_retrieved(self, card_controller, event_bus):
        """Test updating card identifier with CPLC."""
        # Detect card with UID
        card_controller.on_card_detected(uid="04AABBCCDD", is_jcop=True)
        event_bus.clear_event_log()

        # Retrieve CPLC
        card_controller.on_cplc_retrieved(
            cplc_hash="CPLC_1234567890ABCDEF",
            uid="04AABBCCDD",
        )

        # Check identifier updated
        identifier = card_controller.identifier
        assert identifier is not None
        assert identifier.cplc_hash == "CPLC_1234567890ABCDEF"
        assert identifier.uid == "04AABBCCDD"
        assert identifier.is_cplc_based

        # Primary ID should be CPLC hash
        assert card_controller.card_id == "CPLC_1234567890ABCDEF"

    def test_cplc_storage_migration(self, card_controller, mock_storage_service):
        """Test that storage is migrated from UID to CPLC."""
        # Store key under UID
        mock_storage_service.set_key_for_tag("04AABBCCDD", "TESTKEY" * 4)

        # Detect card
        card_controller.on_card_detected(uid="04AABBCCDD", is_jcop=True)

        # Retrieve CPLC
        card_controller.on_cplc_retrieved(
            cplc_hash="CPLC_1234567890ABCDEF",
            uid="04AABBCCDD",
        )

        # Key should now be accessible via CPLC hash
        identifier = CardIdentifier(cplc_hash="CPLC_1234567890ABCDEF")
        key = mock_storage_service.get_key_for_card(identifier)
        assert key == "TESTKEY" * 4


class TestMemoryAndApplets:
    """Test memory and applet state updates."""

    def test_update_memory(self, card_controller):
        """Test updating card memory info."""
        card_controller.on_card_detected(uid="04AABBCCDD", is_jcop=True)

        memory = CardMemory(
            persistent_free=50000,
            persistent_total=100000,
            transient_reset=2000,
            transient_deselect=2000,
        )
        card_controller.update_memory(memory)

        assert card_controller.state.memory.persistent_free == 50000
        assert card_controller.state.memory.is_available

    def test_update_installed_applets(self, card_controller):
        """Test updating installed applets."""
        card_controller.on_card_detected(uid="04AABBCCDD", is_jcop=True)

        applets = {
            "A0000008466D656D6F727901": "1.0",
            "D2760000850101": "1.0",
        }
        card_controller.update_installed_applets(applets)

        assert len(card_controller.state.installed_applets) == 2
        assert card_controller.state.has_applet("A0000008466D656D6F727901")


class TestTitleBar:
    """Test title bar generation."""

    def test_title_with_default_key(self, card_controller, mock_storage_service):
        """Test title shows default key indicator."""
        card_controller.on_card_detected(uid="04AABBCCDD", is_jcop=True)
        card_controller.request_key(lambda k: None)
        card_controller.set_key(DEFAULT_KEY)
        card_controller.on_key_validated(valid=True)

        title = card_controller.get_title_string()
        assert "04AABBCCDD" in title
        assert "Default Key" in title

    def test_title_with_custom_key(self, card_controller, mock_storage_service):
        """Test title shows custom key indicator."""
        card_controller.on_card_detected(uid="04AABBCCDD", is_jcop=True)
        card_controller.request_key(lambda k: None)
        card_controller.set_key("CUSTOMKEY" * 4)
        card_controller.on_key_validated(valid=True)

        title = card_controller.get_title_string()
        assert "Custom Key" in title

    def test_title_with_card_name(self, card_controller, mock_storage_service):
        """Test title uses card name when available."""
        mock_storage_service.set_key_for_tag("04AABBCCDD", DEFAULT_KEY, name="My Card")
        card_controller.on_card_detected(uid="04AABBCCDD", is_jcop=True)

        title = card_controller.get_title_string()
        assert "My Card" in title
