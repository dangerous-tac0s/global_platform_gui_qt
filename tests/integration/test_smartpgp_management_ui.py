#!/usr/bin/env python3
"""
Integration test for SmartPGP management UI.

This script actually launches the UI components and verifies they work.
Run with: python -m tests.integration.test_smartpgp_management_ui
"""

import sys
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock
from dataclasses import dataclass

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Must set up Qt application before importing Qt widgets
from PyQt5.QtWidgets import QApplication, QPushButton, QLabel, QDialog
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtTest import QTest


@dataclass
class TestResult:
    name: str
    passed: bool
    message: str


class SmartPGPManagementUITest:
    """Test harness for SmartPGP management UI."""

    def __init__(self):
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.results: list[TestResult] = []
        self.dialog = None
        self.mock_nfc = None

    def log(self, message: str):
        print(f"  {message}")

    def test_pass(self, name: str, message: str = ""):
        self.results.append(TestResult(name, True, message))
        print(f"  ✓ {name}" + (f" - {message}" if message else ""))

    def test_fail(self, name: str, message: str):
        self.results.append(TestResult(name, False, message))
        print(f"  ✗ {name} - {message}")

    def create_mock_nfc_service(self, simulate_no_keys: bool = False):
        """Create a mock NFC service that logs calls.

        Args:
            simulate_no_keys: If True, return 6A88 for key state readers (simulates card before key generation)
        """
        mock = Mock()

        # Track all APDU calls
        mock.apdu_log = []

        def transmit_apdu(apdu_bytes):
            hex_str = apdu_bytes.hex().upper()
            mock.apdu_log.append(hex_str)
            print(f"    [MOCK NFC] Received APDU: {hex_str}")

            # Return success for SELECT
            if hex_str.startswith("00A40400"):
                return bytes.fromhex("9000")

            # Return success for VERIFY PIN
            if hex_str.startswith("00200083"):
                return bytes.fromhex("9000")

            # Return success for PUT DATA (set algorithm)
            if hex_str.startswith("00DA00C"):
                return bytes.fromhex("9000")

            # Return success for GENERATE KEY
            if hex_str.startswith("00478000"):
                return bytes.fromhex("9000")

            # Return mock data for GET DATA (state readers)
            if hex_str.startswith("00CA"):
                if simulate_no_keys and hex_str.startswith("00CA006E"):
                    # Return 6A88 for key state readers (referenced data not found)
                    return bytes.fromhex("6A88")
                elif hex_str.startswith("00CA00C4"):
                    # PIN retry counter - return some retry data
                    return bytes.fromhex("0303039000")  # 3/3/3 retries
                else:
                    # Return some mock TLV data
                    return bytes.fromhex("C101129000")  # Key type = ECC P-256

            # Default: return success
            return bytes.fromhex("9000")

        mock.transmit_apdu = transmit_apdu
        return mock

    def load_plugin(self):
        """Load the SmartPGP YAML plugin."""
        print("\n[1] Loading SmartPGP plugin...")

        try:
            from src.plugins.yaml.adapter import YamlPluginAdapter
            yaml_path = PROJECT_ROOT / "plugins" / "examples" / "smartpgp.yaml"

            if not yaml_path.exists():
                self.test_fail("Load plugin", f"File not found: {yaml_path}")
                return None

            adapter = YamlPluginAdapter.from_file(yaml_path)
            self.test_pass("Load plugin", f"Loaded from {yaml_path}")
            return adapter

        except Exception as e:
            self.test_fail("Load plugin", str(e))
            return None

    def check_management_ui_definition(self, adapter):
        """Verify management UI is properly defined in the schema."""
        print("\n[2] Checking management UI definition...")

        schema = adapter._schema

        # Check management_ui exists
        if not schema.has_management_ui():
            self.test_fail("Management UI exists", "No management_ui in schema")
            return False
        self.test_pass("Management UI exists")

        # Check state readers
        readers = schema.management_ui.state_readers
        self.log(f"Found {len(readers)} state readers")
        for r in readers:
            self.log(f"  - {r.id}: {r.label} (APDU: {r.apdu})")

        if len(readers) >= 5:
            self.test_pass("State readers", f"{len(readers)} readers defined")
        else:
            self.test_fail("State readers", f"Expected 5, got {len(readers)}")

        # Check actions
        actions = schema.management_ui.actions
        self.log(f"Found {len(actions)} actions")
        for a in actions:
            self.log(f"  - {a.id}: {a.label}" + (f" [workflow: {a.workflow}]" if a.workflow else ""))

        if len(actions) >= 4:
            self.test_pass("Actions", f"{len(actions)} actions defined")
        else:
            self.test_fail("Actions", f"Expected 4, got {len(actions)}")

        # Check workflows
        workflows = schema.workflows
        self.log(f"Found {len(workflows)} workflows")
        for wf_id, wf in workflows.items():
            self.log(f"  - {wf_id}: {len(wf.steps)} steps")

        expected_workflows = ["generate_sig_key", "generate_enc_key", "generate_auth_key"]
        for wf_id in expected_workflows:
            if wf_id in workflows:
                self.test_pass(f"Workflow '{wf_id}'", "Defined")
            else:
                self.test_fail(f"Workflow '{wf_id}'", "Missing from schema")

        return True

    def create_management_dialog(self, adapter):
        """Create the management dialog."""
        print("\n[3] Creating management dialog...")

        try:
            self.mock_nfc = self.create_mock_nfc_service()

            # Use a test AID
            test_aid = "D2760001240103040001000000010000"

            dialog = adapter.create_management_dialog(
                nfc_service=self.mock_nfc,
                parent=None,
                installed_aid=test_aid,
            )

            if dialog is None:
                self.test_fail("Create dialog", "create_management_dialog returned None")
                return None

            self.test_pass("Create dialog", f"Dialog created: {type(dialog).__name__}")
            self.dialog = dialog
            return dialog

        except Exception as e:
            import traceback
            self.test_fail("Create dialog", f"{e}\n{traceback.format_exc()}")
            return None

    def inspect_dialog_ui(self, dialog):
        """Inspect the dialog UI elements."""
        print("\n[4] Inspecting dialog UI...")

        # Find all buttons
        buttons = dialog.findChildren(QPushButton)
        self.log(f"Found {len(buttons)} buttons:")

        button_labels = []
        for btn in buttons:
            text = btn.text()
            button_labels.append(text)
            enabled = "enabled" if btn.isEnabled() else "disabled"
            self.log(f"  - '{text}' ({enabled})")

        # Check for expected buttons
        expected_buttons = [
            "Generate Signature Key",
            "Generate Encryption Key",
            "Generate Authentication Key",
            "Change User PIN",
            "Refresh",
        ]

        for expected in expected_buttons:
            found = any(expected in label for label in button_labels)
            if found:
                self.test_pass(f"Button '{expected}'", "Found in UI")
            else:
                self.test_fail(f"Button '{expected}'", f"NOT FOUND. Available: {button_labels}")

        # Find state labels
        labels = dialog.findChildren(QLabel)
        state_labels = [l for l in labels if l.text() not in ["", "--"] and ":" in l.text()]
        self.log(f"Found {len(state_labels)} state labels")

        return True

    def test_workflow_button_click(self, dialog, button_text: str):
        """Test clicking a workflow button."""
        print(f"\n[5] Testing '{button_text}' button click...")

        # Find the button
        buttons = dialog.findChildren(QPushButton)
        target_btn = None
        for btn in buttons:
            if button_text in btn.text():
                target_btn = btn
                break

        if not target_btn:
            self.test_fail(f"Find button '{button_text}'", "Button not found")
            return False

        self.test_pass(f"Find button '{button_text}'", "Found")

        # Check if button is enabled
        if not target_btn.isEnabled():
            self.test_fail(f"Button enabled", "Button is disabled")
            return False
        self.test_pass("Button enabled")

        # Clear APDU log
        self.mock_nfc.apdu_log.clear()

        # Click the button - this should trigger the workflow
        self.log("Clicking button...")

        # We need to handle the dialog that pops up
        # Use a timer to close it automatically
        dialog_closed = [False]

        def close_popup_dialogs():
            # Find and interact with any popup dialogs
            for widget in QApplication.topLevelWidgets():
                if isinstance(widget, QDialog) and widget != dialog and widget.isVisible():
                    self.log(f"  Found popup dialog: {widget.windowTitle()}")

                    # Look for input fields
                    from PyQt5.QtWidgets import QLineEdit, QComboBox

                    line_edits = widget.findChildren(QLineEdit)
                    for le in line_edits:
                        if le.echoMode() == QLineEdit.Password:
                            self.log(f"    Setting password field to '12345678'")
                            le.setText("12345678")
                        else:
                            self.log(f"    Setting text field to 'test'")
                            le.setText("test")

                    combos = widget.findChildren(QComboBox)
                    for combo in combos:
                        self.log(f"    ComboBox has {combo.count()} items, current: {combo.currentText()}")

                    # Find OK/Accept button
                    popup_buttons = widget.findChildren(QPushButton)
                    for btn in popup_buttons:
                        if btn.text() in ["OK", "Accept", "&OK"]:
                            self.log(f"    Clicking '{btn.text()}' button")
                            QTest.mouseClick(btn, Qt.LeftButton)
                            dialog_closed[0] = True
                            return

                    # Try to accept the dialog directly
                    if hasattr(widget, 'accept'):
                        self.log("    Accepting dialog directly")
                        widget.accept()
                        dialog_closed[0] = True

        # Set up timer to handle popup
        QTimer.singleShot(100, close_popup_dialogs)
        QTimer.singleShot(500, close_popup_dialogs)  # Try again after 500ms
        QTimer.singleShot(1000, close_popup_dialogs)  # And again

        # Click the button
        QTest.mouseClick(target_btn, Qt.LeftButton)

        # Process events
        for _ in range(50):  # Process events for up to 5 seconds
            self.app.processEvents()
            QTest.qWait(100)
            if dialog_closed[0]:
                break

        # Check what APDUs were sent
        if self.mock_nfc.apdu_log:
            self.log(f"APDUs sent during workflow:")
            for apdu in self.mock_nfc.apdu_log:
                self.log(f"    {apdu}")
            self.test_pass("Workflow execution", f"Sent {len(self.mock_nfc.apdu_log)} APDUs")
        else:
            self.test_fail("Workflow execution", "No APDUs were sent")

        return True

    def run_all_tests(self):
        """Run all tests."""
        print("=" * 60)
        print("SmartPGP Management UI Integration Test")
        print("=" * 60)

        # Load plugin
        adapter = self.load_plugin()
        if not adapter:
            return False

        # Check schema
        if not self.check_management_ui_definition(adapter):
            return False

        # Create dialog
        dialog = self.create_management_dialog(adapter)
        if not dialog:
            return False

        # Show dialog (needed for event processing)
        dialog.show()
        self.app.processEvents()

        # Inspect UI
        self.inspect_dialog_ui(dialog)

        # Test all three key generation workflows
        self.test_workflow_button_click(dialog, "Generate Signature Key")
        self.test_workflow_button_click(dialog, "Generate Encryption Key")
        self.test_workflow_button_click(dialog, "Generate Authentication Key")

        # Close dialog
        dialog.close()

        # Test 6A88 handling (simulates card before keys are generated)
        self.test_6a88_handling(adapter)

        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)

        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)

        print(f"\nPassed: {passed}")
        print(f"Failed: {failed}")

        if failed > 0:
            print("\nFailed tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  ✗ {r.name}: {r.message}")

        return failed == 0

    def test_6a88_handling(self, adapter):
        """Test that 6A88 (data not found) shows 'Not generated' instead of error."""
        print("\n[6] Testing 6A88 handling (keys not yet generated)...")

        # Create mock that returns 6A88 for key state readers
        mock_nfc_6a88 = self.create_mock_nfc_service(simulate_no_keys=True)

        test_aid = "D2760001240103040001000000010000"
        dialog = adapter.create_management_dialog(
            nfc_service=mock_nfc_6a88,
            parent=None,
            installed_aid=test_aid,
        )

        if not dialog:
            self.test_fail("Create dialog for 6A88 test", "Dialog creation failed")
            return

        dialog.show()
        self.app.processEvents()

        # Trigger a refresh to read state
        dialog.refresh_state()
        self.app.processEvents()

        # Check what was displayed
        from PyQt5.QtWidgets import QLabel

        labels = dialog.findChildren(QLabel)
        key_labels = []
        for label in labels:
            text = label.text()
            # Look for labels showing key status
            if "Key" in text or "Not" in text or "Error" in text or "generated" in text.lower():
                key_labels.append(text)
                style = label.styleSheet()
                is_red = "red" in style.lower() if style else False
                self.log(f"  Label: '{text}' (red={is_red})")

        # Check that we got "Not generated" instead of "Error: 6A88"
        found_not_generated = any("Not generated" in t or "Not found" in t for t in key_labels)
        found_error_6a88 = any("Error: 6A88" in t for t in key_labels)

        if found_error_6a88:
            self.test_fail("6A88 handling", "Still shows 'Error: 6A88' instead of friendly message")
        elif found_not_generated:
            self.test_pass("6A88 handling", "Shows 'Not generated' for missing keys")
        else:
            self.log(f"  All labels found: {key_labels}")
            self.test_fail("6A88 handling", "Neither 'Not generated' nor 'Error: 6A88' found")

        dialog.close()


def main():
    test = SmartPGPManagementUITest()
    success = test.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
