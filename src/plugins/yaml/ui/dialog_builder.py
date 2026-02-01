"""
Dialog Builder

Assembles complete Qt dialogs from YAML UI definitions.
Supports both tabbed dialogs and simple forms.
"""

import os
from typing import Any, Callable, Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..schema import (
    DialogDefinition,
    FieldDefinition,
    FormDefinition,
    InstallUIDefinition,
    TabDefinition,
)
from .field_factory import (
    ConditionalFieldManager,
    CrossFieldValidator,
    FieldFactory,
    FieldWidget,
)


class FormWidget(QWidget):
    """
    A form widget containing multiple fields.

    Provides value collection and validation for all fields.
    """

    valueChanged = pyqtSignal(str, object)  # field_id, value
    validityChanged = pyqtSignal(bool)  # all_valid

    def __init__(
        self,
        fields: list[FieldDefinition],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._field_defs = fields
        self._field_widgets: list[FieldWidget] = []
        self._conditional_manager: Optional[ConditionalFieldManager] = None
        self._cross_validator: Optional[CrossFieldValidator] = None
        self._cross_validation_errors: dict[str, str] = {}

        self._setup_ui()

    def _setup_ui(self):
        """Set up the form UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Create field widgets
        self._field_widgets = FieldFactory.create_all(self._field_defs, self)

        # Add fields to layout
        for field_widget in self._field_widgets:
            layout.addWidget(field_widget)
            field_widget.valueChanged.connect(self._on_field_changed)

        layout.addStretch()
        self.setLayout(layout)

        # Set up conditional display manager
        self._conditional_manager = ConditionalFieldManager(self._field_widgets, self)

        # Set up cross-field validation
        self._cross_validator = CrossFieldValidator(self._field_widgets, self)
        self._cross_validator.validationChanged.connect(self._on_cross_validation_changed)

    def _on_field_changed(self, field_id: str, value: Any):
        """Handle field value changes."""
        self.valueChanged.emit(field_id, value)
        self._check_validity()

    def _on_cross_validation_changed(self, field_id: str, is_valid: bool, error: str):
        """Handle cross-field validation result changes."""
        if is_valid:
            self._cross_validation_errors.pop(field_id, None)
        else:
            self._cross_validation_errors[field_id] = error

        # Update field widget error display
        for widget in self._field_widgets:
            if widget.getFieldId() == field_id:
                if error:
                    widget._error_label.setText(error)
                    widget._error_label.show()
                else:
                    widget._error_label.hide()
                break

        self._check_validity()

    def _check_validity(self):
        """Check validity of all fields and emit signal."""
        all_valid = self.isValid()
        self.validityChanged.emit(all_valid)

    def getValues(self) -> dict[str, Any]:
        """
        Get all field values as a dictionary.

        Returns:
            Dict mapping field_id to value
        """
        values = {}
        for widget in self._field_widgets:
            # Include all fields that should be included based on show_when conditions
            # Uses conditional manager to evaluate conditions directly, avoiding Qt
            # visibility issues with tabbed dialogs (widgets in non-active tabs
            # report isVisible()=False even when their show_when condition is met)
            field_id = widget.getFieldId()
            if self._conditional_manager.should_include_field(field_id):
                values[field_id] = widget.getValue()
        return values

    def setValues(self, values: dict[str, Any]):
        """
        Set multiple field values.

        Args:
            values: Dict mapping field_id to value
        """
        for widget in self._field_widgets:
            field_id = widget.getFieldId()
            if field_id in values:
                widget.setValue(values[field_id])

    def isValid(self) -> bool:
        """
        Check if all relevant fields are valid.

        Returns:
            True if all fields pass validation
        """
        # Check cross-validation errors
        if self._cross_validation_errors:
            return False

        # Check each field that should be validated
        # Uses conditional manager to evaluate show_when conditions directly,
        # avoiding Qt visibility issues with tabbed dialogs
        for widget in self._field_widgets:
            field_id = widget.getFieldId()
            if self._conditional_manager.should_include_field(field_id):
                if not widget.isValid():
                    return False

        return True

    def getFieldWidget(self, field_id: str) -> Optional[FieldWidget]:
        """Get a field widget by ID."""
        for widget in self._field_widgets:
            if widget.getFieldId() == field_id:
                return widget
        return None


class TabbedFormWidget(QWidget):
    """
    A tabbed widget containing multiple form tabs.
    """

    valueChanged = pyqtSignal(str, object)  # field_id, value
    validityChanged = pyqtSignal(bool)  # all_valid

    def __init__(
        self,
        tabs: list[TabDefinition],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._tab_defs = tabs
        self._tab_widget: Optional[QTabWidget] = None
        self._forms: list[FormWidget] = []

        self._setup_ui()

    def _setup_ui(self):
        """Set up the tabbed UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._tab_widget = QTabWidget()

        for tab_def in self._tab_defs:
            # Create scrollable form for each tab
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)

            form = FormWidget(tab_def.fields)
            form.valueChanged.connect(self._on_value_changed)
            form.validityChanged.connect(self._on_validity_changed)

            scroll.setWidget(form)
            self._forms.append(form)

            self._tab_widget.addTab(scroll, tab_def.name)

        layout.addWidget(self._tab_widget)
        self.setLayout(layout)

    def _on_value_changed(self, field_id: str, value: Any):
        """Forward value change signals."""
        self.valueChanged.emit(field_id, value)

    def _on_validity_changed(self, is_valid: bool):
        """Check overall validity when any form changes."""
        self.validityChanged.emit(self.isValid())

    def getValues(self) -> dict[str, Any]:
        """
        Get all field values from all tabs.

        This handles cross-tab show_when conditions by:
        1. First collecting ALL raw values from all forms
        2. Then filtering based on show_when conditions evaluated against
           the full value set (not limited to per-form visibility)
        """
        # First pass: collect all raw values unconditionally
        all_values = {}
        for form in self._forms:
            for widget in form._field_widgets:
                all_values[widget.getFieldId()] = widget.getValue()

        # Second pass: filter based on show_when conditions
        # using the complete value set for cross-tab dependencies
        filtered_values = {}
        for form in self._forms:
            for widget in form._field_widgets:
                field_id = widget.getFieldId()
                show_when = widget.field_def.show_when

                if show_when is None:
                    # No condition, always include
                    filtered_values[field_id] = all_values[field_id]
                else:
                    # Evaluate show_when against all values (cross-tab safe)
                    dep_field_id = show_when.field
                    if dep_field_id in all_values:
                        dep_value = all_values[dep_field_id]
                        if self._evaluate_show_when(show_when, dep_value):
                            filtered_values[field_id] = all_values[field_id]
                    else:
                        # Dependency not found, include by default
                        filtered_values[field_id] = all_values[field_id]

        return filtered_values

    def _evaluate_show_when(self, show_when, dep_value: Any) -> bool:
        """Evaluate a show_when condition against a dependency value."""
        if show_when.equals is not None:
            return dep_value == show_when.equals
        if show_when.not_equals is not None:
            return dep_value != show_when.not_equals
        if show_when.in_list is not None:
            return dep_value in show_when.in_list
        if show_when.not_in_list is not None:
            return dep_value not in show_when.not_in_list
        return True  # No condition specified

    def setValues(self, values: dict[str, Any]):
        """Set field values across all tabs."""
        for form in self._forms:
            form.setValues(values)

    def isValid(self) -> bool:
        """
        Check if all forms in all tabs are valid.

        Handles cross-tab show_when conditions by only validating fields
        whose show_when conditions are satisfied.
        """
        # First collect all values for cross-tab show_when evaluation
        all_values = {}
        for form in self._forms:
            for widget in form._field_widgets:
                all_values[widget.getFieldId()] = widget.getValue()

        # Check each field that should be validated
        for form in self._forms:
            # Check cross-validation errors
            if form._cross_validation_errors:
                return False

            for widget in form._field_widgets:
                show_when = widget.field_def.show_when

                should_validate = False
                if show_when is None:
                    should_validate = True
                else:
                    dep_field_id = show_when.field
                    if dep_field_id in all_values:
                        dep_value = all_values[dep_field_id]
                        should_validate = self._evaluate_show_when(show_when, dep_value)
                    else:
                        should_validate = True  # Dependency not found, validate

                if should_validate and not widget.isValid():
                    return False

        return True

    def getFieldWidget(self, field_id: str) -> Optional[FieldWidget]:
        """Get a field widget by ID from any tab."""
        for form in self._forms:
            widget = form.getFieldWidget(field_id)
            if widget:
                return widget
        return None


class PluginDialog(QDialog):
    """
    A complete dialog for plugin configuration.

    Supports both tabbed and simple form layouts.
    """

    def __init__(
        self,
        ui_def: InstallUIDefinition,
        title: str = "Configuration",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._ui_def = ui_def
        self._form_widget: Optional[QWidget] = None
        self._button_box: Optional[QDialogButtonBox] = None

        self._setup_ui(title)

    def _setup_ui(self, title: str):
        """Set up the dialog UI."""
        # Determine size from definition
        if self._ui_def.dialog:
            size = self._ui_def.dialog.size
            dialog_title = self._ui_def.dialog.title
        else:
            size = (400, 400)
            dialog_title = title

        # Adjust size for Windows
        if os.name == "nt":
            size = (size[0] * 2, size[1] * 2)

        self.setWindowTitle(dialog_title)
        self.resize(*size)

        layout = QVBoxLayout(self)

        # Create form widget (tabbed or simple)
        if self._ui_def.dialog and self._ui_def.dialog.tabs:
            self._form_widget = TabbedFormWidget(self._ui_def.dialog.tabs, self)
        elif self._ui_def.form:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QScrollArea.NoFrame)

            self._form_widget = FormWidget(self._ui_def.form.fields, self)
            scroll.setWidget(self._form_widget)
            layout.addWidget(scroll)
        else:
            # Empty dialog
            self._form_widget = FormWidget([], self)

        if isinstance(self._form_widget, TabbedFormWidget):
            layout.addWidget(self._form_widget)
        elif self._ui_def.form:
            pass  # Already added via scroll area
        else:
            layout.addWidget(self._form_widget)

        # Connect validity changes
        self._form_widget.validityChanged.connect(self._on_validity_changed)

        # Button box
        self._button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self._button_box.accepted.connect(self._on_accept)
        self._button_box.rejected.connect(self.reject)
        layout.addWidget(self._button_box)

        self.setLayout(layout)

        # Initial validity check
        self._on_validity_changed(self._form_widget.isValid())

    def _on_validity_changed(self, is_valid: bool):
        """Enable/disable OK button based on form validity."""
        ok_button = self._button_box.button(QDialogButtonBox.Ok)
        if ok_button:
            ok_button.setEnabled(is_valid)

    def _on_accept(self):
        """Handle OK button click."""
        if self._form_widget.isValid():
            self.accept()

    def getValues(self) -> dict[str, Any]:
        """Get all form values."""
        return self._form_widget.getValues()

    def setValues(self, values: dict[str, Any]):
        """Set form values."""
        self._form_widget.setValues(values)

    def isValid(self) -> bool:
        """Check if form is valid."""
        return self._form_widget.isValid()


class DialogBuilder:
    """
    Builder class for creating dialogs from YAML UI definitions.
    """

    @staticmethod
    def build(
        ui_def: InstallUIDefinition,
        title: str = "Configuration",
        parent: Optional[QWidget] = None,
    ) -> PluginDialog:
        """
        Build a dialog from a UI definition.

        Args:
            ui_def: Installation UI definition from YAML
            title: Dialog title (used if not specified in definition)
            parent: Parent widget

        Returns:
            Configured PluginDialog instance
        """
        return PluginDialog(ui_def, title, parent)

    @staticmethod
    def build_from_form(
        form_def: FormDefinition,
        title: str = "Configuration",
        parent: Optional[QWidget] = None,
    ) -> PluginDialog:
        """
        Build a dialog from a simple form definition.

        Args:
            form_def: Form definition
            title: Dialog title
            parent: Parent widget

        Returns:
            Configured PluginDialog instance
        """
        ui_def = InstallUIDefinition(form=form_def)
        return PluginDialog(ui_def, title, parent)

    @staticmethod
    def build_from_fields(
        fields: list[FieldDefinition],
        title: str = "Configuration",
        parent: Optional[QWidget] = None,
    ) -> PluginDialog:
        """
        Build a dialog from a list of field definitions.

        Args:
            fields: List of field definitions
            title: Dialog title
            parent: Parent widget

        Returns:
            Configured PluginDialog instance
        """
        form_def = FormDefinition(fields=fields)
        return DialogBuilder.build_from_form(form_def, title, parent)

    @staticmethod
    def create_form_widget(
        fields: list[FieldDefinition],
        parent: Optional[QWidget] = None,
    ) -> FormWidget:
        """
        Create a standalone form widget (not in a dialog).

        Args:
            fields: List of field definitions
            parent: Parent widget

        Returns:
            FormWidget instance
        """
        return FormWidget(fields, parent)

    @staticmethod
    def create_tabbed_form(
        tabs: list[TabDefinition],
        parent: Optional[QWidget] = None,
    ) -> TabbedFormWidget:
        """
        Create a standalone tabbed form widget.

        Args:
            tabs: List of tab definitions
            parent: Parent widget

        Returns:
            TabbedFormWidget instance
        """
        return TabbedFormWidget(tabs, parent)
