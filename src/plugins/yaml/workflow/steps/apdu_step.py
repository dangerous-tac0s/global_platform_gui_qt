"""
APDU Step

Sends APDU commands to a connected card.
"""

import re
from typing import Any, Optional

from ..context import WorkflowContext
from .base import BaseStep, StepResult, StepError
from ...encoding.encoder import TemplateProcessor
from ...logging import logger


class ApduStep(BaseStep):
    """
    Sends an APDU command to the connected card.

    The APDU can use template variables from the context.
    Response data is stored in the context for later steps.

    Uses pyscard directly to maintain connection between SELECT and
    the actual APDU, since transmit_apdu creates a new connection each time.
    """

    def __init__(
        self,
        step_id: str,
        apdu: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        depends_on: Optional[list[str]] = None,
        expect_sw: Optional[str] = None,
    ):
        """
        Initialize the APDU step.

        Args:
            step_id: Step identifier
            apdu: APDU hex string (with optional template variables)
            name: Human-readable name
            description: Description shown during execution
            depends_on: Step dependencies
            expect_sw: Expected status word (e.g., "9000"), None to accept any
        """
        super().__init__(step_id, name, description, depends_on)
        self.apdu = apdu
        self.expect_sw = expect_sw

    def execute(self, context: WorkflowContext) -> StepResult:
        """Execute the APDU command."""
        context.report_progress(
            self.description or f"Sending APDU for {self.name}..."
        )

        # Get the NFC service
        nfc_thread = context.get_service("nfc_thread")
        if not nfc_thread:
            return StepResult.fail("NFC service not available")

        # Process template variables in APDU
        variables = context.get_all_variables()
        processed_apdu = TemplateProcessor.process(self.apdu, variables)

        # Clean the APDU (remove spaces, ensure uppercase)
        cleaned_apdu = self._clean_apdu(processed_apdu)

        # Validate APDU format
        if not self._validate_apdu(cleaned_apdu):
            return StepResult.fail(f"Invalid APDU format: {cleaned_apdu}")

        try:
            # Convert to bytes
            apdu_bytes = bytes.fromhex(cleaned_apdu)

            response = None

            # Priority 1: Use persistent card connection (maintains security state)
            card_conn = context.get_card_connection()
            if card_conn and card_conn.is_connected:
                response = card_conn.transmit(apdu_bytes)

            # Priority 2: Use pyscard directly for SELECT + APDU on same connection
            if response is None:
                applet_aid = context.get("aid")
                reader_name = getattr(nfc_thread, 'selected_reader_name', None)

                if reader_name and applet_aid:
                    # Use pyscard directly to maintain connection
                    response = self._transmit_with_pyscard(
                        apdu_bytes, applet_aid, reader_name
                    )

            # Priority 3: Fall back to NFC service (for mocks/testing)
            if response is None:
                if hasattr(nfc_thread, 'transmit_apdu'):
                    response = nfc_thread.transmit_apdu(apdu_bytes)
                elif hasattr(nfc_thread, 'send_apdu'):
                    response = nfc_thread.send_apdu(apdu_bytes)
                elif hasattr(nfc_thread, 'transmit'):
                    response = nfc_thread.transmit(apdu_bytes)
                else:
                    return StepResult.fail("NFC service does not support APDU transmission")

            if response is None:
                return StepResult.fail("No response from card")

            # Parse response
            if len(response) < 2:
                return StepResult.fail("Invalid response (too short)")

            sw = response[-2:].hex().upper()
            data = response[:-2].hex().upper() if len(response) > 2 else ""

            # Check status word - fail on error SWs unless accepting any
            if self.expect_sw:
                if sw != self.expect_sw.upper():
                    return StepResult.fail(
                        f"Unexpected status word: {sw} (expected {self.expect_sw})"
                    )
            else:
                # Default: fail on obvious error status words
                if sw.startswith("6E") or sw.startswith("6D"):
                    # 6Exx = Class not supported, 6Dxx = Instruction not supported
                    return StepResult.fail(
                        f"Card error: {sw} (applet may not be selected)"
                    )
                if sw == "6A82":
                    return StepResult.fail(f"Application/file not found: {sw}")
                if sw == "6985":
                    return StepResult.fail(f"Conditions not satisfied: {sw}")
                if sw == "6982":
                    return StepResult.fail(f"Security status not satisfied: {sw}")

            # Store results
            result_data = {
                "sw": sw,
                "data": data,
                "raw": response.hex().upper(),
            }

            # Also store individual parts for template access
            context.set(f"{self.step_id}_sw", sw)
            context.set(f"{self.step_id}_data", data)
            context.set(f"{self.step_id}_response", result_data)

            return StepResult.ok(result_data)

        except ValueError as e:
            return StepResult.fail(f"Invalid APDU hex: {e}")
        except Exception as e:
            return StepResult.fail(f"APDU transmission failed: {e}")

    def _transmit_with_pyscard(
        self, apdu_bytes: bytes, applet_aid: str, reader_name: str
    ) -> Optional[bytes]:
        """
        Send APDU using pyscard directly with SELECT on same connection.

        This ensures the applet is selected before the APDU is sent,
        on the same connection.

        Args:
            apdu_bytes: APDU to send
            applet_aid: AID of applet to SELECT first
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
                # Send SELECT first
                aid_bytes = bytes.fromhex(applet_aid.replace(" ", ""))
                select_apdu = [0x00, 0xA4, 0x04, 0x00, len(aid_bytes)] + list(aid_bytes)
                data, sw1, sw2 = connection.transmit(select_apdu)
                sw = f"{sw1:02X}{sw2:02X}"
                if sw != "9000" and not sw.startswith("61"):
                    # SELECT failed
                    return bytes([sw1, sw2])

                # Send the actual APDU
                apdu_list = list(apdu_bytes)
                data, sw1, sw2 = connection.transmit(apdu_list)

                # Build response
                return bytes(data) + bytes([sw1, sw2])

            finally:
                try:
                    connection.disconnect()
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"pyscard transmit error: {e}", exc_info=True)
            return None

    def _clean_apdu(self, apdu: str) -> str:
        """Clean APDU string (remove spaces, uppercase)."""
        return re.sub(r'[^0-9A-Fa-f]', '', apdu).upper()

    def _validate_apdu(self, apdu: str) -> bool:
        """Validate APDU format."""
        # Must be even length (complete bytes)
        if len(apdu) % 2 != 0:
            return False

        # Minimum 4 bytes (CLA INS P1 P2)
        if len(apdu) < 8:
            return False

        return True

    def get_required_services(self) -> list[str]:
        """APDU steps require the NFC service."""
        return ["nfc_thread"]

    def validate(self, context: WorkflowContext) -> Optional[str]:
        """Validate the APDU step."""
        if not self.apdu:
            return "No APDU specified"

        # Skip validation for APDUs with template variables
        # The final APDU will be validated after template processing in execute()
        if "{" in self.apdu:
            return None

        # Validate static APDUs
        cleaned = self._clean_apdu(self.apdu)
        if cleaned and not self._validate_apdu(cleaned):
            return "APDU appears to be malformed"

        return None
