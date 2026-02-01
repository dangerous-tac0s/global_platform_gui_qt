"""
Dialog Step

Shows a dialog to collect user input during workflow execution.
"""

from typing import Any, Callable, Optional

from ..context import WorkflowContext
from .base import BaseStep, StepResult, StepError
from ...schema import FieldDefinition
from ...ui.dialog_builder import DialogBuilder, FormDefinition


class DialogStep(BaseStep):
    """
    Shows a dialog to collect user input.

    The collected values are stored in the context for later steps.
    """

    def __init__(
        self,
        step_id: str,
        fields: list[FieldDefinition],
        name: Optional[str] = None,
        description: Optional[str] = None,
        depends_on: Optional[list[str]] = None,
        title: Optional[str] = None,
        dialog_factory: Optional[Callable] = None,
    ):
        """
        Initialize the dialog step.

        Args:
            step_id: Step identifier
            fields: Field definitions for the dialog
            name: Human-readable name
            description: Description shown during execution
            depends_on: Step dependencies
            title: Dialog title
            dialog_factory: Optional factory function for creating the dialog
        """
        super().__init__(step_id, name, description, depends_on)
        self.fields = fields
        self.title = title or name or "Input Required"
        self._dialog_factory = dialog_factory

    def execute(self, context: WorkflowContext) -> StepResult:
        """Show the dialog and collect input."""
        from ...encoding.encoder import TemplateProcessor

        context.report_progress(
            self.description or f"Waiting for input: {self.name}..."
        )

        # Check if we're in a headless environment
        if context.get("_headless"):
            return self._execute_headless(context)

        try:
            # Process template variables in field defaults before creating dialog
            variables = context.get_all_variables()
            processed_fields = []
            for field in self.fields:
                # Create a copy of the field with processed default
                if field.default and isinstance(field.default, str) and "{" in field.default:
                    processed_default = TemplateProcessor.process(field.default, variables)
                    # Create new field with processed default
                    processed_field = FieldDefinition(
                        id=field.id,
                        type=field.type,
                        label=field.label,
                        description=field.description,
                        placeholder=field.placeholder,
                        default=processed_default,
                        required=field.required,
                        options=field.options,
                        validation=field.validation,
                        show_when=field.show_when,
                        transform=field.transform,
                        readonly=field.readonly,
                    )
                    processed_fields.append(processed_field)
                else:
                    processed_fields.append(field)

            # Create the dialog with processed fields
            if self._dialog_factory:
                dialog = self._dialog_factory(processed_fields, self.title)
            else:
                form_def = FormDefinition(fields=processed_fields)
                dialog = DialogBuilder.build_from_form(form_def, self.title)

            # Pre-populate with existing context values
            prefill = {}
            for field in processed_fields:
                value = context.get(field.id)
                if value is not None:
                    prefill[field.id] = value
            if prefill:
                dialog.setValues(prefill)

            # Show the dialog
            result = dialog.exec_()

            if result:  # Accepted
                values = dialog.getValues()

                # Store values in context
                for key, value in values.items():
                    context.set(key, value)

                # Auto-compute hex encodings only for text/password fields
                # Skip for dropdowns and other fields that may contain hex values
                text_field_ids = set()
                for field in self.fields:
                    if field.type in ("text", "password"):
                        text_field_ids.add(field.id)

                for key, value in values.items():
                    if isinstance(value, str) and key in text_field_ids:
                        # Store as hex-encoded string (ASCII encoding)
                        context.set(f"{key}_hex", value.encode('utf-8').hex().upper())
                        # Store length (in characters, which becomes bytes when ASCII encoded)
                        context.set(f"{key}_length", len(value))

                return StepResult.ok(values)
            else:  # Cancelled
                return StepResult.fail("User cancelled the dialog")

        except Exception as e:
            return StepResult.fail(f"Dialog error: {e}")

    def _execute_headless(self, context: WorkflowContext) -> StepResult:
        """Execute in headless mode using context values."""
        values = {}
        missing = []

        for field in self.fields:
            value = context.get(field.id)
            if value is not None:
                values[field.id] = value
            elif field.default is not None:
                values[field.id] = field.default
            elif field.required:
                missing.append(field.id)

        if missing:
            return StepResult.fail(
                f"Required fields missing in headless mode: {', '.join(missing)}"
            )

        # Store values in context
        for key, value in values.items():
            context.set(key, value)

        # Auto-compute hex encodings for text/password fields (same as regular execute)
        text_field_ids = set()
        for field in self.fields:
            if field.type in ("text", "password"):
                text_field_ids.add(field.id)

        for key, value in values.items():
            if isinstance(value, str) and key in text_field_ids:
                # Store as hex-encoded string (ASCII encoding)
                context.set(f"{key}_hex", value.encode('utf-8').hex().upper())
                # Store length (in characters, which becomes bytes when ASCII encoded)
                context.set(f"{key}_length", len(value))

        return StepResult.ok(values)

    def validate(self, context: WorkflowContext) -> Optional[str]:
        """Validate the dialog step."""
        if not self.fields:
            return "No fields specified for dialog"
        return None


class ConfirmationStep(BaseStep):
    """
    Shows a simple confirmation dialog.

    Returns success if confirmed, failure if cancelled.
    """

    def __init__(
        self,
        step_id: str,
        message: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        depends_on: Optional[list[str]] = None,
        title: str = "Confirm",
    ):
        """
        Initialize the confirmation step.

        Args:
            step_id: Step identifier
            message: Message to display
            name: Human-readable name
            description: Description shown during execution
            depends_on: Step dependencies
            title: Dialog title
        """
        super().__init__(step_id, name, description, depends_on)
        self.message = message
        self.title = title

    def execute(self, context: WorkflowContext) -> StepResult:
        """Show confirmation dialog."""
        from PyQt5.QtWidgets import QMessageBox

        context.report_progress(
            self.description or f"Confirmation required: {self.name}..."
        )

        # Check headless mode
        if context.get("_headless"):
            # Auto-confirm in headless mode
            return StepResult.ok(True)

        try:
            # Process template variables in message
            from ...encoding.encoder import TemplateProcessor
            variables = context.get_all_variables()
            processed_message = TemplateProcessor.process(self.message, variables)

            reply = QMessageBox.question(
                None,
                self.title,
                processed_message,
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                return StepResult.ok(True)
            else:
                return StepResult.fail("User declined")

        except Exception as e:
            return StepResult.fail(f"Confirmation dialog error: {e}")
