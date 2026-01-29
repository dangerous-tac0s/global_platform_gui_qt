"""
CardService - Direct smartcard communication via PC/SC.

This service handles low-level smartcard operations like
detecting readers, connecting to cards, and transmitting APDUs.
"""

from typing import Optional, List, Tuple
from dataclasses import dataclass


@dataclass
class APDUResponse:
    """Response from an APDU command."""
    data: List[int]
    sw1: int
    sw2: int

    @property
    def status_word(self) -> int:
        """Get the full status word as a 16-bit integer."""
        return (self.sw1 << 8) | self.sw2

    @property
    def is_success(self) -> bool:
        """Check if the response indicates success (SW=9000)."""
        return self.sw1 == 0x90 and self.sw2 == 0x00

    @property
    def data_hex(self) -> str:
        """Get response data as hex string."""
        return "".join(f"{b:02X}" for b in self.data)


class CardService:
    """
    Service for direct smartcard communication.

    This handles PC/SC reader operations and APDU transmission.
    """

    # Standard APDUs
    GET_UID_APDU = [0xFF, 0xCA, 0x00, 0x00, 0x00]
    GP_SELECT_APDU = [0x00, 0xA4, 0x04, 0x00, 0x00]

    def __init__(self):
        """Initialize the card service."""
        self._current_reader_name: Optional[str] = None
        self._connection = None

    def get_available_readers(self) -> List[str]:
        """
        Get list of available reader names.

        Returns:
            List of reader name strings
        """
        try:
            from smartcard.System import readers
            return [str(r) for r in readers()]
        except Exception:
            return []

    def connect(self, reader_name: str) -> bool:
        """
        Connect to a card in the specified reader.

        Args:
            reader_name: Name of the reader to connect to

        Returns:
            True if connection successful, False otherwise
        """
        try:
            from smartcard.System import readers
            from smartcard.Exceptions import NoCardException, CardConnectionException

            available = readers()
            for r in available:
                if str(r) == reader_name:
                    try:
                        self._connection = r.createConnection()
                        self._connection.connect()
                        self._current_reader_name = reader_name
                        return True
                    except (NoCardException, CardConnectionException):
                        self._connection = None
                        return False
            return False
        except Exception:
            self._connection = None
            return False

    def disconnect(self) -> None:
        """Disconnect from the current card."""
        if self._connection:
            try:
                self._connection.disconnect()
            except Exception:
                pass
        self._connection = None
        self._current_reader_name = None

    def is_connected(self) -> bool:
        """Check if currently connected to a card."""
        return self._connection is not None

    def get_current_reader(self) -> Optional[str]:
        """Get the name of the currently connected reader."""
        return self._current_reader_name

    def get_card_uid(self, reader_name: Optional[str] = None) -> Optional[str]:
        """
        Get the UID of the card.

        If reader_name is provided, temporarily connects to that reader.
        Otherwise uses the current connection.

        Args:
            reader_name: Optional reader name to connect to

        Returns:
            UID as hex string (uppercase, no spaces), or None if unavailable
        """
        if reader_name:
            # Temporary connection
            try:
                from smartcard.System import readers
                from smartcard.Exceptions import NoCardException, CardConnectionException
                from smartcard.util import toHexString

                available = readers()
                for r in available:
                    if str(r) == reader_name:
                        try:
                            connection = r.createConnection()
                            connection.connect()
                            response, sw1, sw2 = connection.transmit(self.GET_UID_APDU)
                            if sw1 == 0x90 and sw2 == 0x00:
                                return toHexString(response).replace(" ", "")
                        except (NoCardException, CardConnectionException):
                            pass
                        finally:
                            try:
                                connection.disconnect()
                            except:
                                pass
                return None
            except Exception:
                return None
        else:
            # Use current connection
            if not self._connection:
                return None
            try:
                from smartcard.util import toHexString
                response, sw1, sw2 = self._connection.transmit(self.GET_UID_APDU)
                if sw1 == 0x90 and sw2 == 0x00:
                    return toHexString(response).replace(" ", "")
                return None
            except Exception:
                return None

    def is_card_present(self, reader_name: Optional[str] = None) -> bool:
        """
        Check if a card is present.

        Args:
            reader_name: Reader to check. Uses current connection if None.

        Returns:
            True if a card is present
        """
        uid = self.get_card_uid(reader_name)
        return uid is not None

    def is_jcop_compatible(self, reader_name: Optional[str] = None) -> bool:
        """
        Check if the card responds to GP SELECT (indicates JCOP/JavaCard).

        Args:
            reader_name: Reader to check. Uses current connection if None.

        Returns:
            True if card appears to be JCOP compatible
        """
        if reader_name:
            # Temporary connection
            try:
                from smartcard.System import readers
                from smartcard.Exceptions import NoCardException, CardConnectionException

                available = readers()
                for r in available:
                    if str(r) == reader_name:
                        try:
                            connection = r.createConnection()
                            connection.connect()
                            _, sw1, sw2 = connection.transmit(self.GP_SELECT_APDU)
                            return sw1 == 0x90 and sw2 == 0x00
                        except (NoCardException, CardConnectionException):
                            return False
                        finally:
                            try:
                                connection.disconnect()
                            except:
                                pass
                return False
            except Exception:
                return False
        else:
            if not self._connection:
                return False
            try:
                _, sw1, sw2 = self._connection.transmit(self.GP_SELECT_APDU)
                return sw1 == 0x90 and sw2 == 0x00
            except Exception:
                return False

    def transmit_apdu(self, apdu: List[int]) -> APDUResponse:
        """
        Transmit an APDU command to the card.

        Args:
            apdu: APDU bytes as list of integers

        Returns:
            APDUResponse with data, SW1, and SW2

        Raises:
            RuntimeError: If not connected to a card
        """
        if not self._connection:
            raise RuntimeError("Not connected to a card")

        try:
            data, sw1, sw2 = self._connection.transmit(apdu)
            return APDUResponse(data=data, sw1=sw1, sw2=sw2)
        except Exception as e:
            raise RuntimeError(f"APDU transmission failed: {e}")

    def select_application(self, aid: str) -> APDUResponse:
        """
        Select an application by AID.

        Args:
            aid: Application ID as hex string

        Returns:
            APDUResponse from the SELECT command
        """
        # Convert AID hex string to bytes
        aid_bytes = bytes.fromhex(aid.replace(" ", ""))

        # Build SELECT APDU: CLA INS P1 P2 Lc AID
        apdu = [0x00, 0xA4, 0x04, 0x00, len(aid_bytes)] + list(aid_bytes)

        return self.transmit_apdu(apdu)


class MockCardService(CardService):
    """
    Mock CardService for testing.

    Simulates card responses without requiring actual hardware.
    """

    def __init__(self):
        super().__init__()
        self._mock_readers: List[str] = []
        self._mock_uid: Optional[str] = None
        self._mock_is_jcop: bool = True
        self._mock_apdu_responses: dict = {}

    def set_mock_readers(self, readers: List[str]) -> None:
        """Set the list of mock readers."""
        self._mock_readers = readers

    def set_mock_uid(self, uid: Optional[str]) -> None:
        """Set the mock card UID."""
        self._mock_uid = uid

    def set_mock_jcop(self, is_jcop: bool) -> None:
        """Set whether mock card is JCOP compatible."""
        self._mock_is_jcop = is_jcop

    def set_mock_apdu_response(
        self, apdu: Tuple[int, ...], response: APDUResponse
    ) -> None:
        """Set a mock response for a specific APDU."""
        self._mock_apdu_responses[apdu] = response

    def get_available_readers(self) -> List[str]:
        return list(self._mock_readers)

    def connect(self, reader_name: str) -> bool:
        if reader_name in self._mock_readers:
            self._current_reader_name = reader_name
            self._connection = True  # Mock connection
            return True
        return False

    def disconnect(self) -> None:
        self._connection = None
        self._current_reader_name = None

    def get_card_uid(self, reader_name: Optional[str] = None) -> Optional[str]:
        return self._mock_uid

    def is_card_present(self, reader_name: Optional[str] = None) -> bool:
        return self._mock_uid is not None

    def is_jcop_compatible(self, reader_name: Optional[str] = None) -> bool:
        return self._mock_is_jcop and self._mock_uid is not None

    def transmit_apdu(self, apdu: List[int]) -> APDUResponse:
        if not self._connection:
            raise RuntimeError("Not connected to a card")

        apdu_tuple = tuple(apdu)
        if apdu_tuple in self._mock_apdu_responses:
            return self._mock_apdu_responses[apdu_tuple]

        # Default success response
        return APDUResponse(data=[], sw1=0x90, sw2=0x00)
