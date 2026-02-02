"""
Management Panel

Provides a UI for post-installation applet management, including
action execution and state monitoring.
"""

from typing import Any, Callable, Optional
from dataclasses import dataclass

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QGroupBox,
    QPushButton,
    QScrollArea,
    QFrame,
    QMessageBox,
    QDialog,
    QDialogButtonBox,
)

import re
from .state_monitor import StateMonitor, StateDisplayWidget, StateReaderDefinition
from .dialog_builder import DialogBuilder
from ..schema import FieldDefinition, ManagementAction, WorkflowDefinition
from ..encoding.encoder import TemplateProcessor
from ..logging import logger
from ..workflow.engine import WorkflowBuilder, WorkflowEngine
from ..workflow.context import WorkflowContext


@dataclass
class ActionDefinition:
    """Definition for a management action."""

    id: str
    label: str
    description: Optional[str] = None
    dialog_fields: Optional[list[FieldDefinition]] = None
    workflow_id: Optional[str] = None
    apdu_sequence: Optional[list[str]] = None
    confirm_message: Optional[str] = None


class ActionButton(QPushButton):
    """Button that triggers a management action."""

    action_triggered = pyqtSignal(str)  # action_id

    def __init__(self, action: ActionDefinition, parent: Optional[QWidget] = None):
        super().__init__(action.label, parent)
        self._action = action
        self.clicked.connect(self._on_clicked)

        if action.description:
            self.setToolTip(action.description)

    def _on_clicked(self):
        self.action_triggered.emit(self._action.id)


class ManagementPanel(QWidget):
    """
    Panel for managing an installed applet.

    Provides:
    - Action buttons for management operations
    - State display for monitoring applet state
    - Input dialogs for actions requiring parameters
    """

    action_requested = pyqtSignal(str, dict)  # action_id, parameters
    workflow_requested = pyqtSignal(str, dict)  # workflow_id, initial_values
    refresh_state_requested = pyqtSignal()  # Signal to request state refresh (for parent to handle SELECT)

    def __init__(
        self,
        actions: list[ActionDefinition],
        state_readers: Optional[list[StateReaderDefinition]] = None,
        nfc_service: Any = None,
        parent: Optional[QWidget] = None,
        applet_aid: Optional[str] = None,
    ):
        """
        Initialize the management panel.

        Args:
            actions: List of available management actions
            state_readers: Optional list of state reader definitions
            nfc_service: NFC thread service for card communication
            parent: Parent widget
        """
        super().__init__(parent)
        self._actions = {a.id: a for a in actions}
        self._action_list = actions
        self._state_readers = state_readers or []
        self._nfc_service = nfc_service
        self._applet_aid = applet_aid
        self._state_monitor: Optional[StateMonitor] = None
        self._state_display: Optional[StateDisplayWidget] = None

        self._setup_ui()
        self._setup_state_monitor()

    def _setup_ui(self):
        """Set up the management panel UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Title
        title = QLabel("Applet Management")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        # Actions section
        if self._action_list:
            actions_group = QGroupBox("Actions")
            actions_layout = QVBoxLayout(actions_group)

            for action in self._action_list:
                btn = ActionButton(action)
                btn.action_triggered.connect(self._on_action_triggered)
                actions_layout.addWidget(btn)

            layout.addWidget(actions_group)

        # State section
        if self._state_readers:
            state_readers_defs = [
                StateReaderDefinition(
                    id=r.id if hasattr(r, "id") else r.get("id", ""),
                    label=r.label if hasattr(r, "label") else r.get("label", ""),
                    apdu=r.apdu if hasattr(r, "apdu") else r.get("apdu", ""),
                    parse=r.parse if hasattr(r, "parse") else r.get("parse", {}),
                    select_file=r.select_file if hasattr(r, "select_file") else r.get("select_file"),
                )
                for r in self._state_readers
            ]
            self._state_display = StateDisplayWidget(state_readers_defs)
            self._state_display.refresh_requested.connect(self._on_refresh_state)
            layout.addWidget(self._state_display)

        # Stretch to push content to top
        layout.addStretch()

    def _setup_state_monitor(self):
        """Set up the state monitor."""
        if not self._state_readers:
            return

        readers = [
            StateReaderDefinition(
                id=r.id if hasattr(r, "id") else r.get("id", ""),
                label=r.label if hasattr(r, "label") else r.get("label", ""),
                apdu=r.apdu if hasattr(r, "apdu") else r.get("apdu", ""),
                parse=r.parse if hasattr(r, "parse") else r.get("parse", {}),
                select_file=r.select_file if hasattr(r, "select_file") else r.get("select_file"),
            )
            for r in self._state_readers
        ]
        self._state_monitor = StateMonitor(
            readers, self._nfc_service, self, applet_aid=self._applet_aid
        )
        self._state_monitor.state_updated.connect(self._on_state_updated)
        self._state_monitor.error_occurred.connect(self._on_state_error)

    def set_nfc_service(self, service: Any):
        """Set or update the NFC service."""
        self._nfc_service = service
        if self._state_monitor:
            self._state_monitor.set_nfc_service(service)

    def set_applet_aid(self, aid: str):
        """Set the applet AID for SELECT operations."""
        self._applet_aid = aid
        if self._state_monitor:
            self._state_monitor.set_applet_aid(aid)

    def _select_applet(self) -> bool:
        """
        SELECT the applet before performing operations.

        Returns:
            True if SELECT succeeded, False otherwise
        """
        if not self._applet_aid or not self._nfc_service:
            return True  # No AID or no service, proceed anyway

        try:
            # Build SELECT APDU: 00 A4 04 00 Lc AID
            aid_bytes = bytes.fromhex(self._applet_aid.replace(" ", ""))
            select_apdu = bytes([0x00, 0xA4, 0x04, 0x00, len(aid_bytes)]) + aid_bytes

            if hasattr(self._nfc_service, 'transmit_apdu'):
                response = self._nfc_service.transmit_apdu(select_apdu)
            elif hasattr(self._nfc_service, 'transmit'):
                response = self._nfc_service.transmit(select_apdu)
            else:
                return True  # Can't SELECT, proceed anyway

            # Check status word
            if len(response) >= 2:
                sw = response[-2:].hex().upper()
                return sw == "9000" or sw.startswith("61")  # 61XX means more data available

            return False
        except Exception as e:
            logger.warning(f"SELECT applet failed: {e}")
            return False

    def refresh_state(self):
        """Refresh all state readers (StateMonitor handles SELECT internally)."""
        if self._state_monitor:
            self._state_monitor.read_all()

    def _on_action_triggered(self, action_id: str):
        """Handle action button click."""
        action = self._actions.get(action_id)
        if not action:
            return

        # Check for confirmation
        if action.confirm_message:
            reply = QMessageBox.question(
                self,
                "Confirm Action",
                action.confirm_message,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        # Check for dialog fields
        if action.dialog_fields:
            parameters = self._show_action_dialog(action)
            if parameters is None:
                return  # User cancelled
        else:
            parameters = {}

        # Check for workflow
        if action.workflow_id:
            self.workflow_requested.emit(action.workflow_id, parameters)
        else:
            self.action_requested.emit(action_id, parameters)

    def _show_action_dialog(self, action: ActionDefinition) -> Optional[dict]:
        """
        Show a dialog to collect action parameters.

        Args:
            action: Action definition with dialog_fields

        Returns:
            Dict of collected values, or None if cancelled
        """
        if not action.dialog_fields:
            return {}

        # Build dialog from field definitions
        from .dialog_builder import FormDefinition

        form_def = FormDefinition(fields=action.dialog_fields)
        dialog = DialogBuilder.build_from_form(form_def, action.label)

        if dialog.exec_() == QDialog.Accepted:
            return dialog.getValues()
        return None

    def _on_refresh_state(self):
        """Handle refresh button click."""
        self.refresh_state()

    def _on_state_updated(self, reader_id: str, state):
        """Handle state update from monitor."""
        if self._state_display:
            self._state_display.update_state(reader_id, state)

    def _on_state_error(self, reader_id: str, error: str):
        """Handle state read error."""
        # Optionally show error in status bar or log
        pass


class ManagementDialog(QDialog):
    """
    Dialog wrapper for the management panel.

    Used when opening management UI in a separate window.
    """

    def __init__(
        self,
        title: str,
        actions: list[ActionDefinition],
        state_readers: Optional[list[StateReaderDefinition]] = None,
        nfc_service: Any = None,
        parent: Optional[QWidget] = None,
        applet_aid: Optional[str] = None,
        workflows: Optional[dict[str, WorkflowDefinition]] = None,
    ):
        """
        Initialize the management dialog.

        Args:
            title: Dialog title
            actions: Management action definitions
            state_readers: State reader definitions
            nfc_service: NFC service
            parent: Parent widget
            applet_aid: AID of the applet (for SELECT before operations)
            workflows: Workflow definitions from the plugin schema
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(450, 400)  # Increased for better Windows compatibility

        # Store actions for lookup during execution
        self._actions = {a.id: a for a in actions}
        self._nfc_service = nfc_service
        self._applet_aid = applet_aid
        self._workflows = workflows or {}

        layout = QVBoxLayout(self)

        # Status label for showing progress
        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: gray; font-style: italic;")
        self._status_label.hide()
        layout.addWidget(self._status_label)

        # Management panel (pass applet_aid so it can SELECT before state reads)
        self._panel = ManagementPanel(actions, state_readers, nfc_service, applet_aid=applet_aid)
        self._panel.action_requested.connect(self._on_action_requested)
        self._panel.workflow_requested.connect(self._on_workflow_requested)
        layout.addWidget(self._panel)

        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        # Store pending action for external handling
        self._pending_action: Optional[tuple[str, dict]] = None
        self._pending_workflow: Optional[tuple[str, dict]] = None

    def set_nfc_service(self, service: Any):
        """Set the NFC service."""
        self._nfc_service = service
        self._panel.set_nfc_service(service)

    def showEvent(self, event):
        """Auto-refresh state when dialog is shown."""
        super().showEvent(event)
        # Adjust size to fit content (helps on Windows)
        self.adjustSize()
        # Use a timer to refresh after the dialog is fully displayed
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, self._initial_refresh)

    def _initial_refresh(self):
        """Perform initial state refresh after dialog is shown."""
        self.refresh_state()

    def _select_applet(self) -> bool:
        """
        SELECT the applet before performing operations.

        Returns:
            True if SELECT succeeded, False otherwise
        """
        if not self._applet_aid or not self._nfc_service:
            return True  # No AID or no service, proceed anyway

        try:
            # Build SELECT APDU: 00 A4 04 00 Lc AID
            aid_bytes = bytes.fromhex(self._applet_aid.replace(" ", ""))
            select_apdu = bytes([0x00, 0xA4, 0x04, 0x00, len(aid_bytes)]) + aid_bytes

            if hasattr(self._nfc_service, 'transmit_apdu'):
                response = self._nfc_service.transmit_apdu(select_apdu)
            elif hasattr(self._nfc_service, 'transmit'):
                response = self._nfc_service.transmit(select_apdu)
            else:
                return True  # Can't SELECT, proceed anyway

            # Check status word
            if len(response) >= 2:
                sw = response[-2:].hex().upper()
                return sw == "9000" or sw.startswith("61")  # 61XX means more data available

            return False
        except Exception as e:
            logger.warning(f"SELECT applet failed: {e}")
            return False

    def refresh_state(self):
        """Refresh state display (ManagementPanel handles SELECT internally)."""
        self._panel.refresh_state()

    def _on_action_requested(self, action_id: str, parameters: dict):
        """Handle action request from panel - execute APDU sequence."""
        action = self._actions.get(action_id)
        if not action:
            QMessageBox.warning(self, "Error", f"Unknown action: {action_id}")
            return

        # SELECT applet first
        if not self._select_applet():
            QMessageBox.warning(
                self,
                "Error",
                "Failed to select applet. Card may not be present."
            )
            return

        # Check if action has APDU sequence
        if action.apdu_sequence:
            self._execute_apdu_sequence(action, parameters)
        else:
            # Store for external handling (e.g., by caller)
            self._pending_action = (action_id, parameters)
            QMessageBox.information(
                self,
                "Action",
                f"Action '{action.label}' triggered.\n"
                "This action requires external handling (no APDU sequence defined)."
            )

    def _execute_apdu_sequence(self, action: ActionDefinition, parameters: dict):
        """Execute an APDU sequence for an action."""
        if not self._nfc_service:
            QMessageBox.warning(self, "Error", "No NFC service available")
            return

        self._status_label.show()
        errors = []

        for i, apdu_def in enumerate(action.apdu_sequence):
            # Handle ApduCommand objects, dict format, and string format
            if hasattr(apdu_def, 'apdu'):
                # ApduCommand dataclass
                apdu_template = apdu_def.apdu
                description = apdu_def.description or f"Step {i+1}"
            elif isinstance(apdu_def, dict):
                apdu_template = apdu_def.get("apdu", "")
                description = apdu_def.get("description", f"Step {i+1}")
            else:
                apdu_template = str(apdu_def)
                description = f"Step {i+1}"

            self._status_label.setText(description)
            self._status_label.repaint()

            # Process template variables
            processed_apdu = TemplateProcessor.process(apdu_template, parameters)

            # Clean the APDU (remove spaces, ensure uppercase)
            cleaned_apdu = re.sub(r'[^0-9A-Fa-f]', '', processed_apdu).upper()

            if not cleaned_apdu or len(cleaned_apdu) < 8:
                errors.append(f"Invalid APDU at step {i+1}: {cleaned_apdu}")
                continue

            try:
                # Convert to bytes
                apdu_bytes = bytes.fromhex(cleaned_apdu)

                # Send APDU
                if hasattr(self._nfc_service, 'transmit_apdu'):
                    response = self._nfc_service.transmit_apdu(apdu_bytes)
                elif hasattr(self._nfc_service, 'send_apdu'):
                    response = self._nfc_service.send_apdu(apdu_bytes)
                elif hasattr(self._nfc_service, 'transmit'):
                    response = self._nfc_service.transmit(apdu_bytes)
                else:
                    errors.append("NFC service does not support APDU transmission")
                    break

                # Check status word
                if len(response) >= 2:
                    sw = response[-2:].hex().upper()
                    if sw not in ("9000", "6100", "6200", "6300"):
                        # Not all SWs are errors, but warn for unexpected ones
                        if sw.startswith("6A") or sw.startswith("69"):
                            errors.append(f"Step {i+1} returned error SW: {sw}")

            except ValueError as e:
                errors.append(f"Invalid APDU hex at step {i+1}: {e}")
            except Exception as e:
                errors.append(f"Step {i+1} failed: {e}")

        self._status_label.hide()

        if errors:
            QMessageBox.warning(
                self,
                "Action Errors",
                f"Action '{action.label}' completed with errors:\n\n" +
                "\n".join(errors)
            )
        else:
            QMessageBox.information(
                self,
                "Success",
                f"Action '{action.label}' completed successfully."
            )

        # Refresh state after action
        self.refresh_state()

    def _on_workflow_requested(self, workflow_id: str, initial_values: dict):
        """Handle workflow request from panel - execute the workflow."""
        # Get workflow definition
        workflow_def = self._workflows.get(workflow_id)
        if not workflow_def:
            QMessageBox.warning(
                self,
                "Error",
                f"Workflow '{workflow_id}' not found in plugin definition."
            )
            return

        # SELECT applet first
        if not self._select_applet():
            QMessageBox.warning(
                self,
                "Error",
                "Failed to select applet. Card may not be present."
            )
            return

        # Execute workflow
        self._execute_workflow(workflow_def, initial_values)

    def _execute_workflow(self, workflow_def: WorkflowDefinition, initial_values: dict):
        """Execute a workflow definition."""
        context = None
        try:
            # Build workflow engine
            builder = WorkflowBuilder()

            def progress_callback(message: str, percent: float):
                self._status_label.setText(message)
                self._status_label.repaint()

            engine = builder.build_workflow(workflow_def, progress_callback)

            # Create context with NFC service
            context = WorkflowContext(
                initial_values=initial_values,
                progress_callback=progress_callback,
            )
            context.register_service("nfc_thread", self._nfc_service)

            # If we have an AID, add it to context
            if self._applet_aid:
                context.set("aid", self._applet_aid)

            # Create persistent card connection for the workflow
            # This maintains security state (e.g., after PIN verification)
            reader_name = getattr(self._nfc_service, 'selected_reader_name', None)
            if reader_name and self._applet_aid:
                if not context.create_card_connection(reader_name, self._applet_aid):
                    QMessageBox.warning(
                        self,
                        "Connection Error",
                        "Failed to connect to card. Please ensure card is present."
                    )
                    return

            self._status_label.show()

            # Execute workflow
            results = engine.execute(context=context, initial_values=initial_values)

            self._status_label.hide()

            QMessageBox.information(
                self,
                "Success",
                f"Workflow completed successfully.\n\n"
                f"Steps executed: {len(results)}"
            )

            # Refresh state after workflow
            self.refresh_state()

        except Exception as e:
            self._status_label.hide()
            QMessageBox.warning(
                self,
                "Workflow Error",
                f"Workflow failed:\n\n{str(e)}"
            )
        finally:
            # Always close the card connection when done
            if context:
                context.close_card_connection()

    def get_pending_action(self) -> Optional[tuple[str, dict]]:
        """Get any pending action request."""
        return self._pending_action

    def get_pending_workflow(self) -> Optional[tuple[str, dict]]:
        """Get any pending workflow request."""
        return self._pending_workflow


def create_management_panel_from_schema(
    management_ui: dict,
    nfc_service: Any = None,
) -> ManagementPanel:
    """
    Create a ManagementPanel from a YAML management_ui schema.

    Args:
        management_ui: Management UI definition from YAML
        nfc_service: NFC service for card communication

    Returns:
        Configured ManagementPanel widget
    """
    actions = []
    for action_def in management_ui.get("actions", []):
        # Convert dialog fields if present
        dialog_fields = None
        if "dialog" in action_def and "fields" in action_def["dialog"]:
            from ..parser import YamlPluginParser

            dialog_fields = [
                YamlPluginParser._parse_field(f)
                for f in action_def["dialog"]["fields"]
            ]

        action = ActionDefinition(
            id=action_def.get("id", ""),
            label=action_def.get("label", ""),
            description=action_def.get("description"),
            dialog_fields=dialog_fields,
            workflow_id=action_def.get("workflow"),
            apdu_sequence=action_def.get("apdu_sequence"),
            confirm_message=action_def.get("confirm"),
        )
        actions.append(action)

    state_readers = management_ui.get("state_readers", [])

    return ManagementPanel(actions, state_readers, nfc_service)
