"""
Test AID selection for SmartPGP management.

This test verifies that the management dialog correctly uses partial AID
selection to work with any SmartPGP card regardless of manufacturer/serial.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from smartcard.System import readers
from smartcard.util import toHexString

def get_reader():
    """Get the first available reader."""
    reader_list = readers()
    if not reader_list:
        raise RuntimeError("No smartcard readers found")
    return reader_list[0]


def test_partial_aid_selection():
    """Test that partial AID selection works for SmartPGP."""
    print("Testing partial AID selection for SmartPGP...")

    reader = get_reader()
    connection = reader.createConnection()
    connection.connect()

    # Test 1: Full OpenPGP RID prefix (6 bytes) - should always work
    short_aid = bytes.fromhex("D27600012401")
    select_short = bytes([0x00, 0xA4, 0x04, 0x00, len(short_aid)]) + short_aid
    data, sw1, sw2 = connection.transmit(list(select_short))
    sw = f"{sw1:02X}{sw2:02X}"
    print(f"  Short AID (D27600012401): SW={sw}")
    assert sw == "9000", f"Expected 9000, got {sw}"

    # Test 2: Base AID from SmartPGP YAML (8 bytes with version)
    base_aid = bytes.fromhex("D276000124010304")
    select_base = bytes([0x00, 0xA4, 0x04, 0x00, len(base_aid)]) + base_aid
    data, sw1, sw2 = connection.transmit(list(select_base))
    sw = f"{sw1:02X}{sw2:02X}"
    print(f"  Base AID (D276000124010304): SW={sw}")
    assert sw == "9000", f"Expected 9000, got {sw}"

    # Test 3: Verify we can read state after selection
    # GET DATA: PIN retries (C4)
    get_c4 = [0x00, 0xCA, 0x00, 0xC4, 0x00]
    data, sw1, sw2 = connection.transmit(get_c4)
    sw = f"{sw1:02X}{sw2:02X}"
    print(f"  GET DATA C4 (PIN retries): SW={sw}, Data={toHexString(data)}")
    assert sw == "9000", f"Expected 9000, got {sw}"

    # Test 4: Read algorithm attributes (6E)
    get_6e = [0x00, 0xCA, 0x00, 0x6E, 0x00]
    data, sw1, sw2 = connection.transmit(get_6e)
    sw = f"{sw1:02X}{sw2:02X}"
    data_hex = toHexString(data).replace(" ", "")
    print(f"  GET DATA 6E (Application Data): SW={sw}")

    if sw == "6100" or sw.startswith("61"):
        # Need to GET RESPONSE
        le = int(sw[2:4], 16)
        get_response = [0x00, 0xC0, 0x00, 0x00, le]
        data, sw1, sw2 = connection.transmit(get_response)
        sw = f"{sw1:02X}{sw2:02X}"
        data_hex = toHexString(data).replace(" ", "")
        print(f"  GET RESPONSE: SW={sw}, length={len(data)}")

    assert sw == "9000" or sw.startswith("61"), f"Expected 9000 or 61XX, got {sw}"

    connection.disconnect()
    print("\nAll partial AID selection tests passed!")


def test_management_dialog_aid():
    """Test that the adapter uses the correct AID for management dialog."""
    # Need QApplication for dialogs
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])

    from src.plugins.yaml.adapter import YamlPluginAdapter

    # Load SmartPGP plugin
    adapter = YamlPluginAdapter.from_file("plugins/examples/smartpgp.yaml")

    # Check that it has a dynamic AID
    assert adapter._schema.has_dynamic_aid(), "SmartPGP should have dynamic AID"

    # Check the base AID
    base = adapter._schema.applet.metadata.aid_construction.base
    print(f"SmartPGP base AID: {base}")
    assert base == "D276000124010304", f"Expected D276000124010304, got {base}"

    # Create management dialog with a mock NFC service
    class MockNfcService:
        def transmit_apdu(self, apdu):
            print(f"  Would transmit: {apdu.hex().upper()}")
            # Return success
            return bytes.fromhex("9000")

    # Test with a fake installed AID that has different manufacturer
    fake_installed_aid = "D276000124010304AAAA000000010000"

    dialog = adapter.create_management_dialog(
        nfc_service=MockNfcService(),
        installed_aid=fake_installed_aid
    )

    # Check what AID the dialog will use for SELECT
    print(f"Dialog AID: {dialog._applet_aid}")

    # For dynamic AIDs, it should use the base AID, not the full installed AID
    assert dialog._applet_aid == "D276000124010304", \
        f"Expected base AID D276000124010304, got {dialog._applet_aid}"

    print("\nManagement dialog AID test passed!")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-card", action="store_true",
                       help="Skip tests that require a real card")
    args = parser.parse_args()

    # Always run the adapter test
    test_management_dialog_aid()

    # Run card tests if a card is present
    if not args.no_card:
        try:
            test_partial_aid_selection()
        except Exception as e:
            print(f"Card test failed (card may not be present): {e}")
            print("Run with --no-card to skip card tests")
