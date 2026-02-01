"""
APDU Step

Sends APDU commands to a connected card.
"""

import re
from typing import Any, Optional

from ..context import WorkflowContext
from .base import BaseStep, StepResult, StepError
from ...encoding.encoder import TemplateProcessor


class ApduStep(BaseStep):
    """
    Sends an APDU command to the connected card.

    The APDU can use template variables from the context.
    Response data is stored in the context for later steps.
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

            # Send APDU (this interface depends on the NFC implementation)
            if hasattr(nfc_thread, 'send_apdu'):
                response = nfc_thread.send_apdu(apdu_bytes)
            elif hasattr(nfc_thread, 'transmit'):
                response = nfc_thread.transmit(apdu_bytes)
            else:
                return StepResult.fail("NFC service does not support APDU transmission")

            # Parse response
            if len(response) < 2:
                return StepResult.fail("Invalid response (too short)")

            sw = response[-2:].hex().upper()
            data = response[:-2].hex().upper() if len(response) > 2 else ""

            # Check status word
            if self.expect_sw and sw != self.expect_sw.upper():
                return StepResult.fail(
                    f"Unexpected status word: {sw} (expected {self.expect_sw})"
                )

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

        # Basic format check (can't fully validate with templates)
        cleaned = self._clean_apdu(self.apdu.replace("{", "").replace("}", ""))
        if cleaned and not self._validate_apdu(cleaned):
            return "APDU appears to be malformed"

        return None
