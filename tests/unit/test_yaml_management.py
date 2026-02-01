"""
Unit tests for YAML Plugin Management UI

Tests the StateParser, StateMonitor, ManagementPanel, and related components.
"""

import pytest
from unittest.mock import Mock, MagicMock

# Ensure QApplication exists for widget tests
from PyQt5.QtWidgets import QApplication
import sys

# Create QApplication if it doesn't exist
if not QApplication.instance():
    _app = QApplication(sys.argv)

from src.plugins.yaml.ui.state_monitor import (
    StateParser,
    StateMonitor,
    StateDisplayWidget,
    StateReaderDefinition,
    ParsedState,
)
from src.plugins.yaml.ui.management_panel import (
    ActionDefinition,
    ActionButton,
    ManagementPanel,
    ManagementDialog,
)


class TestStateParser:
    """Tests for StateParser class."""

    def test_parse_byte_simple(self):
        """Test parsing a single byte."""
        parse_def = {"type": "byte", "offset": 0}
        result = StateParser.parse("FF", parse_def)

        assert result.success
        assert result.raw_value == "FF"
        assert result.display_value == "255"

    def test_parse_byte_with_offset(self):
        """Test parsing a byte at offset."""
        parse_def = {"type": "byte", "offset": 2}
        result = StateParser.parse("AABBCCDD", parse_def)

        assert result.success
        assert result.raw_value == "CC"
        assert result.display_value == "204"

    def test_parse_byte_with_display_map(self):
        """Test parsing with display mapping."""
        parse_def = {
            "type": "byte",
            "offset": 0,
            "display_map": {
                "00": "Disabled",
                "01": "Enabled",
            },
        }

        result = StateParser.parse("01", parse_def)
        assert result.success
        assert result.display_value == "Enabled"

        result = StateParser.parse("00", parse_def)
        assert result.display_value == "Disabled"

    def test_parse_byte_with_display_template(self):
        """Test parsing with display template."""
        parse_def = {
            "type": "byte",
            "offset": 0,
            "display": "{value}/3 attempts",
        }

        result = StateParser.parse("02", parse_def)
        assert result.success
        assert result.display_value == "2/3 attempts"

    def test_parse_hex_simple(self):
        """Test parsing hex string."""
        parse_def = {"type": "hex", "offset": 0, "length": 4}
        result = StateParser.parse("DEADBEEF0102", parse_def)

        assert result.success
        assert result.raw_value == "DEADBEEF"

    def test_parse_hex_with_offset(self):
        """Test parsing hex with offset."""
        parse_def = {"type": "hex", "offset": 2, "length": 2}
        result = StateParser.parse("AABBCCDD", parse_def)

        assert result.success
        assert result.raw_value == "CCDD"

    def test_parse_hex_no_length(self):
        """Test parsing hex without length (rest of string)."""
        parse_def = {"type": "hex", "offset": 1}
        result = StateParser.parse("AABBCCDD", parse_def)

        assert result.success
        assert result.raw_value == "BBCCDD"

    def test_parse_tlv_found(self):
        """Test parsing TLV when tag is found."""
        # TLV: tag=81, length=02, value=AABB
        parse_def = {"type": "tlv", "tag": "81"}
        result = StateParser.parse("8102AABB", parse_def)

        assert result.success
        assert result.raw_value == "AABB"

    def test_parse_tlv_not_found(self):
        """Test parsing TLV when tag is not found."""
        parse_def = {"type": "tlv", "tag": "82"}
        result = StateParser.parse("8102AABB", parse_def)

        assert not result.success
        assert "not found" in result.display_value.lower()

    def test_parse_tlv_multiple_tags(self):
        """Test parsing TLV with multiple tags."""
        # TLV: 81 02 AABB 82 04 DEADBEEF
        parse_def = {"type": "tlv", "tag": "82"}
        result = StateParser.parse("8102AABB8204DEADBEEF", parse_def)

        assert result.success
        assert result.raw_value == "DEADBEEF"

    def test_parse_ascii(self):
        """Test parsing as ASCII string."""
        parse_def = {"type": "ascii", "offset": 0, "length": 5}
        # "Hello" in hex
        result = StateParser.parse("48656C6C6F", parse_def)

        assert result.success
        assert "Hello" in result.display_value

    def test_parse_response_too_short(self):
        """Test parsing when response is too short."""
        parse_def = {"type": "byte", "offset": 10}
        result = StateParser.parse("AABB", parse_def)

        assert not result.success
        assert "too short" in result.error.lower() or "N/A" in result.display_value


class TestStateMonitor:
    """Tests for StateMonitor class."""

    def test_create_monitor(self):
        """Test creating a state monitor."""
        readers = [
            StateReaderDefinition(
                id="test_reader",
                label="Test",
                apdu="00CA0001",
                parse={"type": "byte", "offset": 0},
            )
        ]
        monitor = StateMonitor(readers)
        assert monitor is not None

    def test_read_state_no_service(self):
        """Test reading state without NFC service."""
        readers = [
            StateReaderDefinition(
                id="test",
                label="Test",
                apdu="00CA0001",
                parse={"type": "byte", "offset": 0},
            )
        ]
        monitor = StateMonitor(readers)

        result = monitor.read_state("test")
        assert result is None

    def test_read_state_with_mock_service(self):
        """Test reading state with mocked NFC service."""
        readers = [
            StateReaderDefinition(
                id="test",
                label="Test",
                apdu="00CA0001",
                parse={"type": "byte", "offset": 0},
            )
        ]

        mock_nfc = Mock()
        mock_nfc.transmit_apdu.return_value = bytes.fromhex("039000")

        monitor = StateMonitor(readers, mock_nfc)
        result = monitor.read_state("test")

        assert result is not None
        assert result.success
        assert result.raw_value == "03"
        assert result.display_value == "3"

    def test_read_state_apdu_failure(self):
        """Test reading state when APDU returns 6A82 (file not found).

        Note: Common status codes like 6A82/6A88 are now shown as friendly
        messages rather than errors, since "not found" is expected for
        uninitialized state (e.g., keys not yet generated).
        """
        readers = [
            StateReaderDefinition(
                id="test",
                label="Test",
                apdu="00CA0001",
                parse={"type": "byte", "offset": 0},
            )
        ]

        mock_nfc = Mock()
        mock_nfc.transmit_apdu.return_value = bytes.fromhex("6A82")

        monitor = StateMonitor(readers, mock_nfc)
        result = monitor.read_state("test")

        assert result is not None
        # 6A82 is now treated as "not found" (success with friendly message)
        assert result.success
        assert "not found" in result.display_value.lower()

    def test_read_all_states(self):
        """Test reading all state readers."""
        readers = [
            StateReaderDefinition(
                id="reader1",
                label="Reader 1",
                apdu="00CA0001",
                parse={"type": "byte", "offset": 0},
            ),
            StateReaderDefinition(
                id="reader2",
                label="Reader 2",
                apdu="00CA0002",
                parse={"type": "byte", "offset": 0},
            ),
        ]

        mock_nfc = Mock()
        mock_nfc.transmit_apdu.return_value = bytes.fromhex("019000")

        monitor = StateMonitor(readers, mock_nfc)
        monitor.read_all()

        # Both readers should have been called
        assert mock_nfc.transmit_apdu.call_count == 2

    def test_signal_emission(self):
        """Test that signals are emitted on state updates."""
        readers = [
            StateReaderDefinition(
                id="test",
                label="Test",
                apdu="00CA0001",
                parse={"type": "byte", "offset": 0},
            )
        ]

        mock_nfc = Mock()
        mock_nfc.transmit_apdu.return_value = bytes.fromhex("019000")

        monitor = StateMonitor(readers, mock_nfc)

        # Connect to signal
        signal_received = []
        monitor.state_updated.connect(lambda rid, state: signal_received.append((rid, state)))

        monitor.read_state("test")

        assert len(signal_received) == 1
        assert signal_received[0][0] == "test"


class TestActionDefinition:
    """Tests for ActionDefinition dataclass."""

    def test_create_simple_action(self):
        """Test creating a simple action."""
        action = ActionDefinition(
            id="test_action",
            label="Test Action",
        )
        assert action.id == "test_action"
        assert action.label == "Test Action"
        assert action.dialog_fields is None

    def test_create_action_with_all_fields(self):
        """Test creating an action with all fields."""
        from src.plugins.yaml.schema import FieldDefinition, FieldType

        action = ActionDefinition(
            id="full_action",
            label="Full Action",
            description="A complete action definition",
            dialog_fields=[
                FieldDefinition(id="field1", type=FieldType.TEXT, label="Field 1")
            ],
            workflow_id="test_workflow",
            apdu_sequence=["00A40400"],
            confirm_message="Are you sure?",
        )

        assert action.workflow_id == "test_workflow"
        assert len(action.dialog_fields) == 1
        assert action.confirm_message == "Are you sure?"


class TestManagementPanel:
    """Tests for ManagementPanel widget."""

    @pytest.fixture
    def simple_actions(self):
        """Create simple test actions."""
        return [
            ActionDefinition(id="action1", label="Action 1"),
            ActionDefinition(id="action2", label="Action 2"),
        ]

    def test_create_panel(self, simple_actions):
        """Test creating a management panel."""
        panel = ManagementPanel(simple_actions)
        assert panel is not None

    def test_panel_with_state_readers(self, simple_actions):
        """Test panel with state readers."""
        readers = [
            StateReaderDefinition(
                id="state1",
                label="State 1",
                apdu="00CA0001",
                parse={"type": "byte", "offset": 0},
            )
        ]

        panel = ManagementPanel(simple_actions, state_readers=readers)
        assert panel is not None
        assert panel._state_monitor is not None

    def test_set_nfc_service(self, simple_actions):
        """Test setting NFC service."""
        readers = [
            StateReaderDefinition(
                id="state1",
                label="State 1",
                apdu="00CA0001",
                parse={"type": "byte", "offset": 0},
            )
        ]

        panel = ManagementPanel(simple_actions, state_readers=readers)

        mock_nfc = Mock()
        panel.set_nfc_service(mock_nfc)

        assert panel._nfc_service is mock_nfc

    def test_action_signal_emission(self, simple_actions):
        """Test that action signals are emitted."""
        panel = ManagementPanel(simple_actions)

        received_actions = []
        panel.action_requested.connect(lambda aid, params: received_actions.append((aid, params)))

        # Trigger action directly (simulating button click)
        panel._on_action_triggered("action1")

        assert len(received_actions) == 1
        assert received_actions[0][0] == "action1"


class TestManagementDialog:
    """Tests for ManagementDialog."""

    def test_create_dialog(self):
        """Test creating a management dialog."""
        actions = [
            ActionDefinition(id="action1", label="Action 1"),
        ]

        dialog = ManagementDialog(
            title="Test Management",
            actions=actions,
        )

        assert dialog is not None
        assert dialog.windowTitle() == "Test Management"

    def test_dialog_with_state_readers(self):
        """Test dialog with state readers."""
        actions = [ActionDefinition(id="action1", label="Action 1")]
        readers = [
            StateReaderDefinition(
                id="state1",
                label="State 1",
                apdu="00CA0001",
                parse={"type": "byte", "offset": 0},
            )
        ]

        dialog = ManagementDialog(
            title="Test",
            actions=actions,
            state_readers=readers,
        )

        assert dialog._panel._state_monitor is not None


class TestAdapterManagement:
    """Tests for management features in YamlPluginAdapter."""

    @pytest.fixture
    def yaml_with_management(self):
        """Create YAML with management UI."""
        return """
schema_version: "1.0"
plugin:
  name: "test-plugin"
  version: "1.0.0"
applet:
  source:
    type: "local"
    path: "/path/to/test.cap"
  metadata:
    name: "Test Applet"
    aid: "D276000124010304"
management_ui:
  actions:
    - id: "set_pin"
      label: "Set PIN"
      description: "Change the PIN"
      dialog:
        fields:
          - id: "new_pin"
            type: "password"
            label: "New PIN"
      apdu_sequence:
        - "00200081{pin_hex}"
  state_readers:
    - id: "pin_retries"
      label: "PIN Retries"
      apdu: "00CA00C4"
      parse:
        type: "byte"
        offset: 0
        display: "{value}/3"
"""

    def test_adapter_has_management_ui(self, yaml_with_management):
        """Test that adapter correctly identifies management UI."""
        from src.plugins.yaml.adapter import YamlPluginAdapter

        adapter = YamlPluginAdapter.from_string(yaml_with_management)

        assert adapter.has_management_ui()

    def test_adapter_get_management_actions(self, yaml_with_management):
        """Test getting management actions from adapter."""
        from src.plugins.yaml.adapter import YamlPluginAdapter

        adapter = YamlPluginAdapter.from_string(yaml_with_management)
        actions = adapter.get_management_actions()

        assert len(actions) == 1
        assert actions[0]["id"] == "set_pin"
        assert actions[0]["label"] == "Set PIN"
        assert actions[0]["has_dialog"] is True

    def test_adapter_get_state_readers(self, yaml_with_management):
        """Test getting state readers from adapter."""
        from src.plugins.yaml.adapter import YamlPluginAdapter

        adapter = YamlPluginAdapter.from_string(yaml_with_management)
        readers = adapter.get_state_readers()

        assert len(readers) == 1
        assert readers[0]["id"] == "pin_retries"
        assert readers[0]["apdu"] == "00CA00C4"

    def test_adapter_create_management_dialog(self, yaml_with_management):
        """Test creating management dialog from adapter."""
        from src.plugins.yaml.adapter import YamlPluginAdapter

        adapter = YamlPluginAdapter.from_string(yaml_with_management)
        dialog = adapter.create_management_dialog()

        assert dialog is not None
        assert "Test Applet" in dialog.windowTitle()
