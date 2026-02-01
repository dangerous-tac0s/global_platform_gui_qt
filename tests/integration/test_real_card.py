#!/usr/bin/env python3
"""
Test SmartPGP management with a real card - NO MOCKS.

Run with: source venv/bin/activate && python -m tests.integration.test_real_card
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from PyQt5.QtWidgets import QApplication, QMessageBox, QPushButton, QLineEdit, QComboBox, QDialog
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtTest import QTest

from src.plugins.yaml.adapter import YamlPluginAdapter


class RealCardNFCService:
    """NFC service that talks to a real smartcard."""

    def __init__(self, reader):
        self.reader = reader
        self.connection = None

    def connect(self):
        try:
            self.connection = self.reader.createConnection()
            self.connection.connect()
            print(f"Connected to card on {self.reader}")
            return True
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False

    def transmit_apdu(self, apdu_bytes):
        if not self.connection:
            raise Exception("Not connected to card")

        apdu_list = list(apdu_bytes)
        print(f"  >> {apdu_bytes.hex().upper()}")

        response, sw1, sw2 = self.connection.transmit(apdu_list)
        result = bytes(response) + bytes([sw1, sw2])
        print(f"  << {result.hex().upper()} (SW={sw1:02X}{sw2:02X})")

        return result


class RealCardTest:
    def __init__(self):
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.nfc_service = None
        self.dialog = None

    def find_reader(self):
        from smartcard.System import readers
        available = readers()
        if not available:
            print("ERROR: No smartcard readers found!")
            return None
        print(f"Found reader: {available[0]}")
        return available[0]

    def find_smartpgp_aid(self):
        """Try to find the actual SmartPGP AID on the card."""
        # Try partial AID selection first - OpenPGP RID
        # This matches ANY OpenPGP applet regardless of version/serial
        partial_aids = [
            "D27600012401",  # OpenPGP RID (matches any OpenPGP app)
        ]

        for aid in partial_aids:
            try:
                select = bytes.fromhex(f"00A40400{len(bytes.fromhex(aid)):02X}{aid}")
                response = self.nfc_service.transmit_apdu(select)
                sw = response[-2:].hex().upper()
                if sw == "9000" or sw.startswith("61"):
                    print(f"Found OpenPGP applet via partial AID: {aid}")
                    # Return the partial AID - management will work with it
                    return aid
            except Exception as e:
                print(f"  Error trying {aid}: {e}")

        # Fallback: try common full AIDs
        full_aids = [
            "D2760001240103040001000000010000",  # Default
            "D27600012401030400010000000A0001",  # With manufacturer ID 000A
            "D2760001240103040001000000000000",  # Zeros
        ]

        for aid in full_aids:
            try:
                select = bytes.fromhex(f"00A40400{len(bytes.fromhex(aid)):02X}{aid}")
                response = self.nfc_service.transmit_apdu(select)
                sw = response[-2:].hex().upper()
                if sw == "9000" or sw.startswith("61"):
                    print(f"Found SmartPGP at AID: {aid}")
                    return aid
            except:
                pass

        print("SmartPGP/OpenPGP not found on card")
        return None

    def click_button(self, parent, button_text):
        """Find and click a button by its text."""
        buttons = parent.findChildren(QPushButton)
        for btn in buttons:
            if button_text in btn.text():
                print(f"  Clicking button: '{btn.text()}'")
                QTest.mouseClick(btn, Qt.LeftButton)
                self.app.processEvents()
                return True
        print(f"  Button '{button_text}' not found!")
        return False

    def fill_dialog_and_accept(self, admin_pin="12345678"):
        """Find popup dialog, fill fields, and accept."""
        QTest.qWait(200)
        self.app.processEvents()

        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QDialog) and widget.isVisible() and widget != self.dialog:
                print(f"  Found dialog: {widget.windowTitle()}")

                # Fill password fields
                line_edits = widget.findChildren(QLineEdit)
                for le in line_edits:
                    if le.echoMode() == QLineEdit.Password:
                        print(f"    Entering admin PIN")
                        le.setText(admin_pin)

                # Check combo boxes
                combos = widget.findChildren(QComboBox)
                for combo in combos:
                    print(f"    ComboBox: {combo.currentText()}")

                # Click OK
                if self.click_button(widget, "OK"):
                    return True

                # Try accept directly
                widget.accept()
                return True

        return False

    def dismiss_message_box(self):
        """Dismiss any message boxes."""
        QTest.qWait(200)
        self.app.processEvents()

        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QMessageBox) and widget.isVisible():
                print(f"  Message box: {widget.text()}")
                widget.accept()
                return True
        return False

    def setup_auto_dialog_handler(self, admin_pin="12345678"):
        """Set up a timer to automatically handle workflow dialogs."""
        def handle_dialogs():
            self.app.processEvents()
            for widget in QApplication.topLevelWidgets():
                if isinstance(widget, QDialog) and widget.isVisible() and widget != self.dialog:
                    print(f"  [AUTO] Found dialog: {widget.windowTitle()}")

                    # Fill password fields
                    line_edits = widget.findChildren(QLineEdit)
                    for le in line_edits:
                        if le.echoMode() == QLineEdit.Password:
                            print(f"    [AUTO] Setting admin PIN")
                            le.setText(admin_pin)

                    # Click OK button
                    buttons = widget.findChildren(QPushButton)
                    for btn in buttons:
                        if btn.text() in ["OK", "&OK", "Accept"]:
                            print(f"    [AUTO] Clicking '{btn.text()}'")
                            QTest.mouseClick(btn, Qt.LeftButton)
                            return

                    # Fallback: accept directly
                    widget.accept()
                    return

                if isinstance(widget, QMessageBox) and widget.isVisible():
                    print(f"  [AUTO] Message box: {widget.text()}")
                    widget.accept()
                    return

            # Keep checking if we didn't find anything
            QTimer.singleShot(100, handle_dialogs)

        # Start checking for dialogs
        QTimer.singleShot(100, handle_dialogs)

    def run_test(self):
        print("=" * 60)
        print("REAL CARD TEST - NO MOCKS")
        print("=" * 60)

        # Find reader
        reader = self.find_reader()
        if not reader:
            return False

        # Connect
        self.nfc_service = RealCardNFCService(reader)
        if not self.nfc_service.connect():
            return False

        # Find SmartPGP
        aid = self.find_smartpgp_aid()
        if not aid:
            print("\nSmartPGP not installed. Install it first via main app.")
            return False

        # Load plugin
        print("\nLoading SmartPGP plugin...")
        yaml_path = PROJECT_ROOT / "plugins" / "examples" / "smartpgp.yaml"
        adapter = YamlPluginAdapter.from_file(yaml_path)

        # Create dialog with REAL NFC service
        print("\nCreating management dialog with REAL card...")
        self.dialog = adapter.create_management_dialog(
            nfc_service=self.nfc_service,
            parent=None,
            installed_aid=aid,
        )

        if not self.dialog:
            print("Failed to create dialog!")
            return False

        self.dialog.show()
        self.app.processEvents()
        QTest.qWait(500)  # Wait for auto-refresh

        # Check state display
        print("\n--- State after opening dialog ---")
        self.app.processEvents()

        # Test Generate Signature Key workflow
        print("\n--- Testing Generate Signature Key ---")

        # Set up auto-handler for popup dialogs BEFORE clicking the button
        self.setup_auto_dialog_handler()

        # Find and click the button
        buttons = self.dialog.findChildren(QPushButton)
        for btn in buttons:
            if "Generate Signature Key" in btn.text():
                print(f"  Clicking: '{btn.text()}'")
                btn.click()  # This will trigger the workflow
                break

        # Process events for a while to let the workflow complete
        for i in range(30):  # 3 seconds max
            QTest.qWait(100)
            self.app.processEvents()

        print("\n--- Test complete ---")
        print("Close the dialog window to exit.")

        # Run event loop to let user see results
        return self.app.exec_() == 0


def main():
    test = RealCardTest()
    success = test.run_test()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
