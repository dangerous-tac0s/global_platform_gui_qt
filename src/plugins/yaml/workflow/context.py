"""
Workflow Context

Provides a context for workflow execution with variable storage,
service access, and progress reporting.
"""

import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

from ..logging import logger


class CardConnection:
    """
    Persistent card connection for workflow execution.

    Maintains a single pyscard connection throughout the workflow,
    preserving security state (e.g., after PIN verification).
    """

    def __init__(self, reader_name: str, applet_aid: Optional[str] = None):
        """
        Initialize the card connection.

        Args:
            reader_name: Name of the card reader
            applet_aid: AID of applet to SELECT (optional)
        """
        self._reader_name = reader_name
        self._applet_aid = applet_aid
        self._connection = None
        self._selected = False

    def connect(self) -> bool:
        """
        Establish connection and optionally SELECT the applet.

        Returns:
            True if connection (and SELECT if AID provided) succeeded
        """
        try:
            from smartcard.System import readers as get_readers

            # Find the reader
            filtered_readers = [
                r for r in get_readers() if "SAM" not in str(r).upper()
            ]
            card_reader = None
            for r in filtered_readers:
                if self._reader_name in str(r):
                    card_reader = r
                    break

            if not card_reader:
                logger.warning(f"Card reader not found: {self._reader_name}")
                return False

            # Create and connect
            self._connection = card_reader.createConnection()
            self._connection.connect()

            # SELECT applet if AID provided
            if self._applet_aid:
                aid_bytes = bytes.fromhex(self._applet_aid.replace(" ", ""))
                select_apdu = [0x00, 0xA4, 0x04, 0x00, len(aid_bytes)] + list(aid_bytes)
                data, sw1, sw2 = self._connection.transmit(select_apdu)
                sw = f"{sw1:02X}{sw2:02X}"
                if sw != "9000" and not sw.startswith("61"):
                    logger.warning(f"SELECT failed with SW: {sw}")
                    return False
                self._selected = True

            return True

        except Exception as e:
            logger.error(f"Card connection error: {e}", exc_info=True)
            return False

    def transmit(self, apdu_bytes: bytes) -> Optional[bytes]:
        """
        Transmit an APDU on the persistent connection.

        Args:
            apdu_bytes: APDU to send

        Returns:
            Response bytes or None on error
        """
        if not self._connection:
            return None

        try:
            apdu_list = list(apdu_bytes)
            data, sw1, sw2 = self._connection.transmit(apdu_list)
            return bytes(data) + bytes([sw1, sw2])
        except Exception as e:
            logger.error(f"Transmit error: {e}", exc_info=True)
            return None

    def disconnect(self):
        """Disconnect from the card."""
        if self._connection:
            try:
                self._connection.disconnect()
            except Exception:
                pass
            self._connection = None
            self._selected = False

    @property
    def is_connected(self) -> bool:
        """Check if connection is active."""
        return self._connection is not None

    @property
    def is_selected(self) -> bool:
        """Check if applet has been selected."""
        return self._selected


class WorkflowContext:
    """
    Execution context for workflow steps.

    Provides:
    - Variable storage (get/set)
    - Temporary file directory
    - Progress reporting
    - Service access (card, GP operations)
    """

    def __init__(
        self,
        initial_values: Optional[dict[str, Any]] = None,
        temp_dir: Optional[str] = None,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ):
        """
        Initialize the workflow context.

        Args:
            initial_values: Initial variable values (e.g., from form fields)
            temp_dir: Temporary directory for file operations
            progress_callback: Callback for progress updates (message, percent)
        """
        self._variables: dict[str, Any] = initial_values.copy() if initial_values else {}
        self._step_results: dict[str, Any] = {}
        self._temp_dir = Path(temp_dir) if temp_dir else Path(tempfile.mkdtemp(prefix="workflow_"))
        self._progress_callback = progress_callback
        self._services: dict[str, Any] = {}
        self._cancelled = False
        self._card_connection: Optional[CardConnection] = None

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a variable value.

        Args:
            key: Variable name
            default: Default value if not found

        Returns:
            Variable value or default
        """
        # Check step results first
        if key in self._step_results:
            return self._step_results[key]
        return self._variables.get(key, default)

    def set(self, key: str, value: Any):
        """
        Set a variable value.

        Args:
            key: Variable name
            value: Value to store
        """
        self._variables[key] = value

    def set_step_result(self, step_id: str, result: Any):
        """
        Store the result of a workflow step.

        Args:
            step_id: Step identifier
            result: Step result data
        """
        self._step_results[step_id] = result
        # Also store as {step_id}_result for template access
        self._variables[f"{step_id}_result"] = result

    def get_step_result(self, step_id: str) -> Any:
        """
        Get the result of a previous step.

        Args:
            step_id: Step identifier

        Returns:
            Step result or None
        """
        return self._step_results.get(step_id)

    def get_all_variables(self) -> dict[str, Any]:
        """Get all variables including step results."""
        result = self._variables.copy()
        result.update(self._step_results)
        return result

    @property
    def temp_dir(self) -> Path:
        """Get the temporary directory path."""
        return self._temp_dir

    def create_temp_file(self, name: str, content: bytes = b"") -> Path:
        """
        Create a temporary file.

        Args:
            name: File name
            content: Initial content

        Returns:
            Path to the created file
        """
        file_path = self._temp_dir / name
        file_path.write_bytes(content)
        return file_path

    def report_progress(self, message: str, percent: float = -1):
        """
        Report progress to the callback.

        Args:
            message: Progress message
            percent: Progress percentage (0-100) or -1 for indeterminate
        """
        if self._progress_callback:
            self._progress_callback(message, percent)

    def register_service(self, name: str, service: Any):
        """
        Register a service for use by workflow steps.

        Args:
            name: Service name (e.g., "nfc_thread", "gp_service")
            service: Service instance
        """
        self._services[name] = service

    def get_service(self, name: str) -> Any:
        """
        Get a registered service.

        Args:
            name: Service name

        Returns:
            Service instance or None
        """
        return self._services.get(name)

    def cancel(self):
        """Cancel the workflow execution."""
        self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        """Check if workflow has been cancelled."""
        return self._cancelled

    def cleanup(self):
        """Clean up temporary files and close card connection."""
        # Close card connection first
        self.close_card_connection()

        import shutil
        if self._temp_dir.exists():
            try:
                shutil.rmtree(self._temp_dir)
            except Exception:
                pass  # Best effort cleanup

    def create_card_connection(self, reader_name: str, applet_aid: Optional[str] = None) -> bool:
        """
        Create a persistent card connection for the workflow.

        Args:
            reader_name: Name of the card reader
            applet_aid: AID of applet to SELECT

        Returns:
            True if connection succeeded
        """
        # Close any existing connection
        self.close_card_connection()

        self._card_connection = CardConnection(reader_name, applet_aid)
        if not self._card_connection.connect():
            self._card_connection = None
            return False
        return True

    def get_card_connection(self) -> Optional[CardConnection]:
        """Get the persistent card connection."""
        return self._card_connection

    def close_card_connection(self):
        """Close the persistent card connection."""
        if self._card_connection:
            self._card_connection.disconnect()
            self._card_connection = None


class SandboxedContext:
    """
    A sandboxed view of the workflow context for script execution.

    Provides limited access to context variables and functions
    to prevent unauthorized operations.
    """

    def __init__(self, context: WorkflowContext):
        """
        Initialize the sandboxed context.

        Args:
            context: Parent workflow context
        """
        self._context = context

    def get(self, key: str, default: Any = None) -> Any:
        """Get a variable value."""
        return self._context.get(key, default)

    def set(self, key: str, value: Any):
        """Set a variable value."""
        self._context.set(key, value)

    def get_temp_dir(self) -> str:
        """Get the temporary directory path as string."""
        return str(self._context.temp_dir)

    def create_temp_file(self, name: str, content: bytes = b"") -> str:
        """Create a temporary file and return its path as string."""
        return str(self._context.create_temp_file(name, content))

    def report_progress(self, message: str):
        """Report progress (percent not available in sandbox)."""
        self._context.report_progress(message, -1)

    def get_step_result(self, step_id: str) -> Any:
        """
        Get the result of a previous workflow step.

        Args:
            step_id: Step identifier

        Returns:
            Step result or None
        """
        return self._context.get_step_result(step_id)
