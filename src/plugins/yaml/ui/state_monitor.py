"""
State Monitor

Monitors and displays current applet state by executing state reader APDUs.
"""

from typing import Any, Callable, Optional
from dataclasses import dataclass

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGroupBox,
    QGridLayout,
    QPushButton,
)


@dataclass
class StateReaderDefinition:
    """Definition for a state reader."""

    id: str
    label: str
    apdu: str
    parse: dict
    refresh_interval: int = 0  # 0 = manual only
    select_file: Optional[str] = None  # File ID to SELECT before reading (e.g., "E104" for NDEF)


@dataclass
class ParsedState:
    """Result of parsing an APDU response."""

    raw_value: str
    display_value: str
    success: bool
    error: Optional[str] = None


class StateParser:
    """
    Parses APDU responses according to state reader definitions.

    Supports:
    - byte: Extract a single byte
    - hex: Extract hex string
    - tlv: Extract TLV-encoded value
    - ascii: Convert hex to ASCII string
    - map: Map value to display string
    """

    @classmethod
    def parse(cls, response_hex: str, parse_def: dict) -> ParsedState:
        """
        Parse an APDU response.

        Args:
            response_hex: Response data as hex string (without SW)
            parse_def: Parse definition from state reader

        Returns:
            ParsedState with parsed value
        """
        try:
            parse_type = parse_def.get("type", "hex")

            if parse_type == "byte":
                return cls._parse_byte(response_hex, parse_def)
            elif parse_type == "hex":
                return cls._parse_hex(response_hex, parse_def)
            elif parse_type == "tlv":
                return cls._parse_tlv(response_hex, parse_def)
            elif parse_type == "ascii":
                return cls._parse_ascii(response_hex, parse_def)
            elif parse_type == "openpgp_key":
                return cls._parse_openpgp_key(response_hex, parse_def)
            else:
                return ParsedState(
                    raw_value=response_hex,
                    display_value=response_hex,
                    success=True,
                )

        except Exception as e:
            return ParsedState(
                raw_value=response_hex,
                display_value="Error",
                success=False,
                error=str(e),
            )

    @classmethod
    def _parse_byte(cls, response_hex: str, parse_def: dict) -> ParsedState:
        """Parse a single byte value."""
        offset = parse_def.get("offset", 0) or 0  # Handle None
        byte_offset = offset * 2  # Convert byte offset to hex char offset

        if byte_offset + 2 > len(response_hex):
            return ParsedState(
                raw_value="",
                display_value="N/A",
                success=False,
                error="Response too short",
            )

        raw_value = response_hex[byte_offset : byte_offset + 2]
        int_value = int(raw_value, 16)

        # Check for display mapping (handle None values)
        display_map = parse_def.get("display_map") or {}
        if raw_value.upper() in display_map:
            display_value = display_map[raw_value.upper()]
        elif str(int_value) in display_map:
            display_value = display_map[str(int_value)]
        else:
            # Use display template if provided
            display_template = parse_def.get("display") or "{value}"
            display_value = display_template.format(value=int_value, hex=raw_value)

        return ParsedState(
            raw_value=raw_value,
            display_value=display_value,
            success=True,
        )

    @classmethod
    def _parse_hex(cls, response_hex: str, parse_def: dict) -> ParsedState:
        """Parse a hex string."""
        offset = parse_def.get("offset", 0) or 0  # Handle None
        length = parse_def.get("length", 0) or 0  # Handle None

        byte_offset = offset * 2
        byte_length = length * 2 if length > 0 else len(response_hex) - byte_offset

        if byte_offset > len(response_hex):
            return ParsedState(
                raw_value="",
                display_value="N/A",
                success=False,
                error="Response too short",
            )

        raw_value = response_hex[byte_offset : byte_offset + byte_length]

        # Determine display value based on format
        format_type = parse_def.get("format")
        if format_type == "int" or format_type == "decimal":
            # Convert hex to integer (big-endian)
            try:
                int_value = int(raw_value, 16) if raw_value else 0
                display_val = int_value
            except ValueError:
                display_val = raw_value
        else:
            display_val = raw_value

        # Check for display mapping (handle None values)
        display_map = parse_def.get("display_map") or {}
        if raw_value.upper() in display_map:
            display_value = display_map[raw_value.upper()]
        elif str(display_val) in display_map:
            display_value = display_map[str(display_val)]
        else:
            display_template = parse_def.get("display") or "{value}"
            display_value = display_template.format(value=display_val)

        return ParsedState(
            raw_value=raw_value,
            display_value=display_value,
            success=True,
        )

    @classmethod
    def _parse_tlv(cls, response_hex: str, parse_def: dict) -> ParsedState:
        """Parse a TLV-encoded value, supporting nested structures."""
        target_tag = parse_def.get("tag", "").upper()

        # Search for tag in response (handles nested TLV)
        value = cls._find_tlv_tag(response_hex, target_tag)

        if value is not None:
            # Apply encoding if specified (e.g., "ascii" to decode hex to text)
            encoding = parse_def.get("encoding")
            decoded_value = value
            if encoding == "ascii" and value:
                try:
                    decoded_value = bytes.fromhex(value).decode("ascii", errors="replace")
                except Exception:
                    decoded_value = value  # Fall back to hex if decode fails

            display_map = parse_def.get("display_map") or {}
            # First check decoded value in display_map
            if decoded_value in display_map:
                display_value = display_map[decoded_value]
            # Then check value as-is (hex)
            elif value.upper() in display_map:
                display_value = display_map[value.upper()]
            # Then check first byte (for algorithm type)
            elif len(value) >= 2 and value[:2].upper() in display_map:
                display_value = display_map[value[:2].upper()]
            # Then check for empty string key (for "not generated")
            elif value == "" and "" in display_map:
                display_value = display_map[""]
            else:
                # Use decoded value for display if encoding was specified
                display_template = parse_def.get("display") or "{value}"
                display_value = display_template.format(value=decoded_value)

            return ParsedState(
                raw_value=value,
                display_value=display_value,
                success=True,
            )

        # Check if display_map has empty string entry for "not found"
        display_map = parse_def.get("display_map") or {}
        if "" in display_map:
            return ParsedState(
                raw_value="",
                display_value=display_map[""],
                success=True,
            )

        return ParsedState(
            raw_value="",
            display_value="Not found",
            success=False,
            error=f"Tag {target_tag} not found",
        )

    @classmethod
    def _find_tlv_tag(cls, data: str, target_tag: str) -> Optional[str]:
        """
        Find a TLV tag in data, including nested structures.

        Args:
            data: Hex string containing TLV data
            target_tag: Tag to search for (1 or 2 byte hex)

        Returns:
            Value as hex string, or None if not found
        """
        pos = 0
        while pos < len(data) - 3:
            # Parse tag (handle 2-byte tags starting with 5F, 7F, etc.)
            tag = data[pos:pos + 2].upper()
            pos += 2

            # Check for 2-byte tag
            first_byte = int(tag, 16)
            if (first_byte & 0x1F) == 0x1F:  # More tag bytes follow
                if pos + 2 > len(data):
                    break
                tag += data[pos:pos + 2].upper()
                pos += 2

            if pos + 2 > len(data):
                break

            # Parse length (handle extended length)
            length_byte = int(data[pos:pos + 2], 16)
            pos += 2

            if length_byte <= 0x7F:
                length = length_byte
            elif length_byte == 0x81:
                if pos + 2 > len(data):
                    break
                length = int(data[pos:pos + 2], 16)
                pos += 2
            elif length_byte == 0x82:
                if pos + 4 > len(data):
                    break
                length = int(data[pos:pos + 4], 16)
                pos += 4
            else:
                break  # Invalid length encoding

            value_len = length * 2
            if pos + value_len > len(data):
                break

            value = data[pos:pos + value_len]

            # Check if this is the target tag
            if tag == target_tag:
                return value

            # Recursively search in constructed tags (even bytes = constructed)
            if first_byte & 0x20:  # Constructed tag
                nested_result = cls._find_tlv_tag(value, target_tag)
                if nested_result is not None:
                    return nested_result

            pos += value_len

        return None

    @classmethod
    def _parse_openpgp_key(cls, response_hex: str, parse_def: dict) -> ParsedState:
        """
        Parse OpenPGP public key response to determine key type.

        Detects RSA vs ECC and key size from the 7F49 public key template.
        """
        # Find 7F49 (public key template)
        pub_key_data = cls._find_tlv_tag(response_hex, "7F49")

        if not pub_key_data:
            # No key found
            display_map = parse_def.get("display_map") or {}
            if "" in display_map:
                return ParsedState(
                    raw_value="",
                    display_value=display_map[""],
                    success=True,
                )
            return ParsedState(
                raw_value="",
                display_value="Not generated",
                success=True,
            )

        # Look for RSA modulus (tag 81) or EC point (tag 86)
        modulus = cls._find_tlv_tag(pub_key_data, "81")
        ec_point = cls._find_tlv_tag(pub_key_data, "86")

        if modulus:
            # RSA key - determine size from modulus length
            modulus_bytes = len(modulus) // 2
            if modulus_bytes <= 256:
                key_type = "RSA 2048"
            elif modulus_bytes <= 384:
                key_type = "RSA 3072"
            else:
                key_type = "RSA 4096"
        elif ec_point:
            # ECC key - determine curve from point size
            point_bytes = len(ec_point) // 2
            if point_bytes <= 65:  # P-256: 1 + 32 + 32 = 65
                key_type = "ECC P-256"
            elif point_bytes <= 97:  # P-384: 1 + 48 + 48 = 97
                key_type = "ECC P-384"
            elif point_bytes <= 133:  # P-521: 1 + 66 + 66 = 133
                key_type = "ECC P-521"
            else:
                key_type = "ECC"
        else:
            # Unknown format but key exists
            key_type = "Unknown"

        return ParsedState(
            raw_value=pub_key_data[:40] + "..." if len(pub_key_data) > 40 else pub_key_data,
            display_value=key_type,
            success=True,
        )

    @classmethod
    def _parse_ascii(cls, response_hex: str, parse_def: dict) -> ParsedState:
        """Parse hex as ASCII string."""
        offset = parse_def.get("offset", 0) or 0
        length = parse_def.get("length", 0) or 0

        byte_offset = offset * 2
        byte_length = length * 2 if length > 0 else len(response_hex) - byte_offset

        raw_value = response_hex[byte_offset : byte_offset + byte_length]

        # Check for empty value
        display_map = parse_def.get("display_map") or {}
        if not raw_value or raw_value == "":
            if "" in display_map:
                return ParsedState(
                    raw_value="",
                    display_value=display_map[""],
                    success=True,
                )
            return ParsedState(
                raw_value="",
                display_value="(empty)",
                success=True,
            )

        try:
            ascii_value = bytes.fromhex(raw_value).decode("ascii", errors="replace")

            # Check if decoded value is in display_map
            if ascii_value in display_map:
                display_value = display_map[ascii_value]
            else:
                display_template = parse_def.get("display") or "{value}"
                display_value = display_template.format(value=ascii_value)

            return ParsedState(
                raw_value=raw_value,
                display_value=display_value,
                success=True,
            )
        except Exception as e:
            return ParsedState(
                raw_value=raw_value,
                display_value="Error",
                success=False,
                error=str(e),
            )


class StateMonitor(QObject):
    """
    Monitors applet state by executing APDUs and parsing responses.

    Emits signals when state values are updated.
    """

    state_updated = pyqtSignal(str, ParsedState)  # reader_id, parsed_state
    error_occurred = pyqtSignal(str, str)  # reader_id, error_message

    def __init__(
        self,
        readers: list[StateReaderDefinition],
        nfc_service: Any = None,
        parent: Optional[QObject] = None,
        applet_aid: Optional[str] = None,
    ):
        """
        Initialize the state monitor.

        Args:
            readers: List of state reader definitions
            nfc_service: NFC thread service for APDU communication
            parent: Parent QObject
            applet_aid: AID for SELECT before reading state
        """
        super().__init__(parent)
        self._readers = {r.id: r for r in readers}
        self._nfc_service = nfc_service
        self._applet_aid = applet_aid
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timer)
        self._auto_refresh_readers: list[str] = []
        self._current_states: dict[str, ParsedState] = {}

    def set_nfc_service(self, service: Any):
        """Set or update the NFC service."""
        self._nfc_service = service

    def set_applet_aid(self, aid: str):
        """Set the applet AID for SELECT operations."""
        self._applet_aid = aid

    def read_state(self, reader_id: str) -> Optional[ParsedState]:
        """
        Read state for a specific reader.

        Uses pyscard directly to send SELECT + state reader APDU on the same
        connection, since transmit_apdu creates a new connection for each call.

        Args:
            reader_id: Reader identifier

        Returns:
            ParsedState or None if reader not found
        """
        reader = self._readers.get(reader_id)
        if not reader:
            self.error_occurred.emit(reader_id, f"Unknown reader: {reader_id}")
            return None

        if not self._nfc_service:
            self.error_occurred.emit(reader_id, "NFC service not available")
            return None

        try:
            # Try to use pyscard directly to keep connection open between SELECT and data read
            reader_name = getattr(self._nfc_service, 'selected_reader_name', None)

            if reader_name and self._applet_aid:
                # Use pyscard for real cards (SELECT + APDU on same connection)
                response = self._read_with_pyscard(reader, reader_name)
            else:
                # Fall back to NFC service (for mocks/testing)
                response = self._read_with_service(reader)

            if response is None:
                return None

            # Check response length
            if len(response) < 2:
                self.error_occurred.emit(reader_id, "Response too short")
                return None

            # Extract status word and data
            sw = response[-2:].hex().upper()
            data = response[:-2].hex().upper() if len(response) > 2 else ""

            # Check for success
            if sw != "9000":
                # Map common status words to user-friendly messages
                sw_messages = {
                    "6A88": "Not found",      # Referenced data not found (key not generated)
                    "6A82": "Not found",      # File/app not found
                    "6982": "Security status not satisfied",
                    "6983": "Auth blocked",   # PIN blocked
                    "6985": "Conditions not satisfied",
                    "6D00": "Not supported",
                    "6E00": "Class not supported",
                }
                display = sw_messages.get(sw, f"Error: {sw}")

                # Check if display_map has an entry for empty/error state
                # For 6A88 (data not found), use the empty string mapping if available
                if reader.parse and isinstance(reader.parse, dict):
                    display_map = reader.parse.get("display_map", {})
                    if display_map and "" in display_map and sw == "6A88":
                        display = display_map[""]  # Use "Not generated" from display_map

                parsed = ParsedState(
                    raw_value=sw,
                    display_value=display,
                    success=True,  # Mark as success so it doesn't show red
                    error=None,
                )
            else:
                # Parse the response
                parsed = StateParser.parse(data, reader.parse)

            self._current_states[reader_id] = parsed
            self.state_updated.emit(reader_id, parsed)
            return parsed

        except Exception as e:
            self.error_occurred.emit(reader_id, str(e))
            return None

    def _read_with_pyscard(
        self, reader: StateReaderDefinition, reader_name: str
    ) -> Optional[bytes]:
        """
        Read state using pyscard directly for SELECT + APDU on same connection.

        Args:
            reader: State reader definition
            reader_name: Name of the card reader

        Returns:
            Response bytes or None on error
        """
        try:
            from smartcard.System import readers as get_readers

            # Find the reader
            filtered_readers = [
                r for r in get_readers() if "SAM" not in str(r).upper()
            ]
            card_reader = None
            for r in filtered_readers:
                if reader_name in str(r):
                    card_reader = r
                    break

            if not card_reader:
                return None

            # Create connection
            connection = card_reader.createConnection()
            connection.connect()

            try:
                # Send SELECT if we have an AID
                if self._applet_aid:
                    aid_bytes = bytes.fromhex(self._applet_aid.replace(" ", ""))
                    select_apdu = [0x00, 0xA4, 0x04, 0x00, len(aid_bytes)] + list(aid_bytes)
                    data, sw1, sw2 = connection.transmit(select_apdu)
                    sw = f"{sw1:02X}{sw2:02X}"
                    if sw != "9000" and not sw.startswith("61"):
                        return None

                # Select file if specified (e.g., NDEF file E104)
                if reader.select_file:
                    file_id = bytes.fromhex(reader.select_file.replace(" ", ""))
                    # SELECT by file ID: 00 A4 00 0C 02 [file_id]
                    select_file_apdu = [0x00, 0xA4, 0x00, 0x0C, len(file_id)] + list(file_id)
                    data, sw1, sw2 = connection.transmit(select_file_apdu)
                    sw = f"{sw1:02X}{sw2:02X}"
                    if sw != "9000" and not sw.startswith("61"):
                        # File selection failed
                        return bytes([sw1, sw2])  # Return SW to show error

                # Send the state reader APDU
                apdu_bytes = bytes.fromhex(reader.apdu.replace(" ", ""))
                apdu_list = list(apdu_bytes)
                data, sw1, sw2 = connection.transmit(apdu_list)

                # Build response
                return bytes(data) + bytes([sw1, sw2])

            finally:
                try:
                    connection.disconnect()
                except Exception:
                    pass

        except Exception:
            return None

    def _read_with_service(self, reader: StateReaderDefinition) -> Optional[bytes]:
        """
        Read state using NFC service (for mocks/testing).

        Args:
            reader: State reader definition

        Returns:
            Response bytes or None on error
        """
        try:
            apdu_bytes = bytes.fromhex(reader.apdu.replace(" ", ""))

            if hasattr(self._nfc_service, "transmit_apdu"):
                return self._nfc_service.transmit_apdu(apdu_bytes)
            elif hasattr(self._nfc_service, "send_apdu"):
                return self._nfc_service.send_apdu(apdu_bytes)
            elif hasattr(self._nfc_service, "transmit"):
                return self._nfc_service.transmit(apdu_bytes)
            else:
                return None
        except Exception:
            return None

    def read_all(self):
        """Read all state readers."""
        for reader_id in self._readers:
            self.read_state(reader_id)

    def start_auto_refresh(self, interval_ms: int = 5000):
        """
        Start automatic refresh of readers with refresh_interval > 0.

        Args:
            interval_ms: Refresh interval in milliseconds
        """
        self._auto_refresh_readers = [
            r.id for r in self._readers.values() if r.refresh_interval > 0
        ]
        if self._auto_refresh_readers:
            self._timer.start(interval_ms)

    def stop_auto_refresh(self):
        """Stop automatic refresh."""
        self._timer.stop()

    def _on_timer(self):
        """Timer callback for auto-refresh."""
        for reader_id in self._auto_refresh_readers:
            self.read_state(reader_id)

    def get_current_state(self, reader_id: str) -> Optional[ParsedState]:
        """Get the last read state for a reader."""
        return self._current_states.get(reader_id)


class StateDisplayWidget(QWidget):
    """
    Widget that displays state reader values.
    """

    refresh_requested = pyqtSignal()

    def __init__(
        self,
        readers: list[StateReaderDefinition],
        parent: Optional[QWidget] = None,
    ):
        """
        Initialize the state display widget.

        Args:
            readers: State reader definitions
            parent: Parent widget
        """
        super().__init__(parent)
        self._readers = readers
        self._value_labels: dict[str, QLabel] = {}
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout(self)

        # Create group box for state values
        group = QGroupBox("Applet State")
        group_layout = QGridLayout(group)

        for i, reader in enumerate(self._readers):
            # Label
            label = QLabel(f"{reader.label}:")
            label.setStyleSheet("font-weight: bold;")
            group_layout.addWidget(label, i, 0)

            # Value
            value_label = QLabel("--")
            value_label.setStyleSheet("color: gray;")
            group_layout.addWidget(value_label, i, 1)
            self._value_labels[reader.id] = value_label

        layout.addWidget(group)

        # Refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self.refresh_requested.emit)
        layout.addWidget(refresh_btn)

    def update_state(self, reader_id: str, state: ParsedState):
        """
        Update the display for a state reader.

        Args:
            reader_id: Reader identifier
            state: Parsed state value
        """
        label = self._value_labels.get(reader_id)
        if label:
            label.setText(state.display_value)
            if state.success:
                label.setStyleSheet("color: black;")
            else:
                label.setStyleSheet("color: red;")
                label.setToolTip(state.error or "")

    def clear_states(self):
        """Clear all state displays."""
        for label in self._value_labels.values():
            label.setText("--")
            label.setStyleSheet("color: gray;")
