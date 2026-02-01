"""
Field Factory

Creates Qt widgets from YAML field definitions.
Handles field types, validation, conditional display, and value transformations.
"""

import re
from typing import Any, Callable, Optional

from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..schema import (
    FieldDefinition,
    FieldType,
    FieldValidation,
    ShowWhen,
)


class FieldWidget(QWidget):
    """
    Base wrapper for a form field with label, widget, and validation.

    Emits valueChanged when the field value changes.
    """

    valueChanged = pyqtSignal(str, object)  # field_id, new_value

    def __init__(
        self,
        field_def: FieldDefinition,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.field_def = field_def
        self._input_widget: Optional[QWidget] = None
        self._error_label: Optional[QLabel] = None
        self._is_valid = True

        self._setup_ui()

    def _setup_ui(self):
        """Set up the field UI with label, input, and error display."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 8)
        layout.setSpacing(4)

        # Label row (label + required indicator)
        label_layout = QHBoxLayout()
        label_layout.setContentsMargins(0, 0, 0, 0)

        label_text = self.field_def.label
        if self.field_def.required:
            label_text += " *"

        label = QLabel(label_text)
        label_layout.addWidget(label)
        label_layout.addStretch()
        layout.addLayout(label_layout)

        # Description (if provided)
        if self.field_def.description:
            desc_label = QLabel(self.field_def.description)
            desc_label.setStyleSheet("color: gray; font-size: 11px;")
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)

        # Input widget
        self._input_widget = self._create_input_widget()
        layout.addWidget(self._input_widget)

        # Error label (hidden by default)
        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: red; font-size: 11px;")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self.setLayout(layout)

    def _create_input_widget(self) -> QWidget:
        """Create the appropriate input widget based on field type."""
        field_type = self.field_def.type

        if field_type == FieldType.TEXT:
            return self._create_text_input()
        elif field_type == FieldType.PASSWORD:
            return self._create_password_input()
        elif field_type == FieldType.DROPDOWN:
            return self._create_dropdown()
        elif field_type == FieldType.CHECKBOX:
            return self._create_checkbox()
        elif field_type == FieldType.HEX_EDITOR:
            return self._create_hex_editor()
        elif field_type == FieldType.NUMBER:
            return self._create_number_input()
        elif field_type == FieldType.FILE:
            return self._create_file_picker()
        elif field_type == FieldType.HIDDEN:
            return self._create_hidden_input()
        else:
            # Fallback to text input
            return self._create_text_input()

    def _create_text_input(self) -> QLineEdit:
        """Create a text input widget."""
        widget = QLineEdit()
        if self.field_def.placeholder:
            widget.setPlaceholderText(self.field_def.placeholder)
        if self.field_def.default is not None:
            widget.setText(str(self.field_def.default))

        widget.textChanged.connect(self._on_text_changed)
        return widget

    def _create_password_input(self) -> QLineEdit:
        """Create a password input widget."""
        widget = QLineEdit()
        widget.setEchoMode(QLineEdit.Password)
        if self.field_def.placeholder:
            widget.setPlaceholderText(self.field_def.placeholder)

        widget.textChanged.connect(self._on_text_changed)
        return widget

    def _create_dropdown(self) -> QComboBox:
        """Create a dropdown widget."""
        widget = QComboBox()

        for option in self.field_def.options:
            widget.addItem(option.label, option.value)

        # Set default value
        if self.field_def.default is not None:
            index = widget.findData(self.field_def.default)
            if index >= 0:
                widget.setCurrentIndex(index)

        widget.currentIndexChanged.connect(self._on_dropdown_changed)
        return widget

    def _create_checkbox(self) -> QCheckBox:
        """Create a checkbox widget."""
        widget = QCheckBox()
        if self.field_def.default:
            widget.setChecked(bool(self.field_def.default))

        widget.stateChanged.connect(self._on_checkbox_changed)
        return widget

    def _create_hex_editor(self) -> QTextEdit:
        """Create a hex editor widget."""
        widget = QTextEdit()
        widget.setAcceptRichText(False)
        widget.setMinimumHeight(self.field_def.rows * 20)
        widget.setMaximumHeight(self.field_def.rows * 25)

        if self.field_def.placeholder:
            widget.setPlaceholderText(self.field_def.placeholder)
        if self.field_def.default is not None:
            widget.setText(str(self.field_def.default))

        widget.textChanged.connect(self._on_hex_changed)
        return widget

    def _create_number_input(self) -> QSpinBox:
        """Create a number input widget."""
        widget = QSpinBox()

        # Set range from validation if available
        if self.field_def.validation:
            if self.field_def.validation.min_value is not None:
                widget.setMinimum(self.field_def.validation.min_value)
            if self.field_def.validation.max_value is not None:
                widget.setMaximum(self.field_def.validation.max_value)

        if self.field_def.default is not None:
            widget.setValue(int(self.field_def.default))

        widget.valueChanged.connect(self._on_number_changed)
        return widget

    def _create_file_picker(self) -> QWidget:
        """Create a file picker widget."""
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        line_edit = QLineEdit()
        if self.field_def.placeholder:
            line_edit.setPlaceholderText(self.field_def.placeholder)
        if self.field_def.default is not None:
            line_edit.setText(str(self.field_def.default))

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(lambda: self._browse_file(line_edit))

        layout.addWidget(line_edit, 1)
        layout.addWidget(browse_btn)

        line_edit.textChanged.connect(self._on_text_changed)

        # Store reference to line edit for getValue
        container._line_edit = line_edit
        return container

    def _create_hidden_input(self) -> QWidget:
        """Create a hidden input (stores value but not visible)."""
        widget = QLineEdit()
        widget.hide()
        if self.field_def.default is not None:
            widget.setText(str(self.field_def.default))
        return widget

    def _browse_file(self, line_edit: QLineEdit):
        """Open file dialog and set selected path."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {self.field_def.label}",
            "",
            "All Files (*.*)"
        )
        if path:
            line_edit.setText(path)

    def _on_text_changed(self, text: str):
        """Handle text input changes."""
        # Apply transform if specified
        if self.field_def.transform:
            transformed = self._apply_transform(text)
            if transformed != text:
                widget = self._get_text_widget()
                if widget:
                    # Block signals to avoid recursion
                    widget.blockSignals(True)
                    widget.setText(transformed)
                    widget.blockSignals(False)
                    text = transformed

        self._validate_and_emit(text)

    def _on_dropdown_changed(self, index: int):
        """Handle dropdown changes."""
        widget = self._input_widget
        if isinstance(widget, QComboBox):
            value = widget.currentData()
            self._validate_and_emit(value)

    def _on_checkbox_changed(self, state: int):
        """Handle checkbox changes."""
        value = state == Qt.Checked
        self._validate_and_emit(value)

    def _on_hex_changed(self):
        """Handle hex editor changes."""
        widget = self._input_widget
        if isinstance(widget, QTextEdit):
            text = widget.toPlainText()
            # Apply uppercase transform for hex
            if self.field_def.transform == "uppercase":
                transformed = text.upper()
                if transformed != text:
                    cursor = widget.textCursor()
                    pos = cursor.position()
                    widget.blockSignals(True)
                    widget.setText(transformed)
                    cursor.setPosition(min(pos, len(transformed)))
                    widget.setTextCursor(cursor)
                    widget.blockSignals(False)
                    text = transformed

            self._validate_and_emit(text)

    def _on_number_changed(self, value: int):
        """Handle number input changes."""
        self._validate_and_emit(value)

    def _apply_transform(self, text: str) -> str:
        """Apply configured transform to text."""
        if self.field_def.transform == "uppercase":
            return text.upper()
        elif self.field_def.transform == "lowercase":
            return text.lower()
        return text

    def _validate_and_emit(self, value: Any):
        """Validate the value and emit valueChanged signal."""
        is_valid, error_message = self.validate(value)
        self._is_valid = is_valid

        if is_valid:
            self._error_label.hide()
        else:
            self._error_label.setText(error_message)
            self._error_label.show()

        self.valueChanged.emit(self.field_def.id, value)

    def validate(self, value: Any = None) -> tuple[bool, str]:
        """
        Validate the current field value.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if value is None:
            value = self.getValue()

        validation = self.field_def.validation

        # Check required
        if self.field_def.required:
            if value is None or value == "":
                return False, "This field is required"

        # If no validation rules or empty optional field, valid
        if not validation:
            return True, ""

        if value is None or value == "":
            return True, ""  # Empty optional fields are valid

        # String validations
        if isinstance(value, str):
            # Pattern validation
            if validation.pattern:
                if not re.match(validation.pattern, value):
                    return False, validation.message or "Invalid format"

            # Length validation
            if validation.min_length is not None:
                if len(value) < validation.min_length:
                    return False, validation.message or f"Minimum length is {validation.min_length}"

            if validation.max_length is not None:
                if len(value) > validation.max_length:
                    return False, validation.message or f"Maximum length is {validation.max_length}"

        # Number validations
        if isinstance(value, (int, float)):
            if validation.min_value is not None:
                if value < validation.min_value:
                    return False, validation.message or f"Minimum value is {validation.min_value}"

            if validation.max_value is not None:
                if value > validation.max_value:
                    return False, validation.message or f"Maximum value is {validation.max_value}"

        return True, ""

    def _get_text_widget(self) -> Optional[QLineEdit]:
        """Get the text widget if this is a text-based field."""
        if isinstance(self._input_widget, QLineEdit):
            return self._input_widget
        elif hasattr(self._input_widget, '_line_edit'):
            return self._input_widget._line_edit
        return None

    def getValue(self) -> Any:
        """Get the current value of the field."""
        widget = self._input_widget

        if isinstance(widget, QLineEdit):
            return widget.text()
        elif isinstance(widget, QComboBox):
            return widget.currentData()
        elif isinstance(widget, QCheckBox):
            return widget.isChecked()
        elif isinstance(widget, QTextEdit):
            return widget.toPlainText()
        elif isinstance(widget, QSpinBox):
            return widget.value()
        elif hasattr(widget, '_line_edit'):
            return widget._line_edit.text()

        return None

    def setValue(self, value: Any):
        """Set the field value."""
        widget = self._input_widget

        if isinstance(widget, QLineEdit):
            widget.setText(str(value) if value is not None else "")
        elif isinstance(widget, QComboBox):
            index = widget.findData(value)
            if index >= 0:
                widget.setCurrentIndex(index)
        elif isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QTextEdit):
            widget.setText(str(value) if value is not None else "")
        elif isinstance(widget, QSpinBox):
            widget.setValue(int(value) if value is not None else 0)
        elif hasattr(widget, '_line_edit'):
            widget._line_edit.setText(str(value) if value is not None else "")

    def isValid(self) -> bool:
        """Check if the current value is valid."""
        is_valid, _ = self.validate()
        return is_valid

    def getFieldId(self) -> str:
        """Get the field ID."""
        return self.field_def.id


class FieldFactory:
    """
    Factory for creating field widgets from YAML field definitions.
    """

    @staticmethod
    def create(
        field_def: FieldDefinition,
        parent: Optional[QWidget] = None,
    ) -> FieldWidget:
        """
        Create a FieldWidget from a field definition.

        Args:
            field_def: The field definition from YAML
            parent: Parent widget

        Returns:
            Configured FieldWidget instance
        """
        return FieldWidget(field_def, parent)

    @staticmethod
    def create_all(
        field_defs: list[FieldDefinition],
        parent: Optional[QWidget] = None,
    ) -> list[FieldWidget]:
        """
        Create multiple FieldWidgets from a list of definitions.

        Args:
            field_defs: List of field definitions
            parent: Parent widget

        Returns:
            List of FieldWidget instances
        """
        return [FieldFactory.create(fd, parent) for fd in field_defs]


class ConditionalFieldManager(QObject):
    """
    Manages conditional display of fields based on show_when rules.

    Listens to field value changes and shows/hides dependent fields.
    """

    def __init__(self, fields: list[FieldWidget], parent: Optional[QObject] = None):
        super().__init__(parent)
        self._fields = {f.getFieldId(): f for f in fields}
        self._dependencies: dict[str, list[tuple[FieldWidget, ShowWhen]]] = {}

        self._setup_dependencies()
        self._update_all_visibility()

    def _setup_dependencies(self):
        """Set up dependency tracking between fields."""
        for field_widget in self._fields.values():
            show_when = field_widget.field_def.show_when
            if show_when:
                # This field depends on another field
                dep_field_id = show_when.field
                if dep_field_id not in self._dependencies:
                    self._dependencies[dep_field_id] = []
                self._dependencies[dep_field_id].append((field_widget, show_when))

        # Connect to value changes of fields that have dependents
        for dep_field_id in self._dependencies:
            if dep_field_id in self._fields:
                self._fields[dep_field_id].valueChanged.connect(
                    self._on_dependency_changed
                )

    def _on_dependency_changed(self, field_id: str, value: Any):
        """Handle when a field that others depend on changes."""
        if field_id in self._dependencies:
            for field_widget, show_when in self._dependencies[field_id]:
                visible = self._evaluate_show_when(show_when, value)
                field_widget.setVisible(visible)

    def _evaluate_show_when(self, show_when: ShowWhen, value: Any) -> bool:
        """Evaluate a show_when condition."""
        if show_when.equals is not None:
            return str(value) == str(show_when.equals)

        if show_when.not_equals is not None:
            return str(value) != str(show_when.not_equals)

        if show_when.is_set is not None:
            has_value = value is not None and value != ""
            return has_value == show_when.is_set

        return True

    def _update_all_visibility(self):
        """Update visibility of all conditional fields."""
        for dep_field_id, dependents in self._dependencies.items():
            if dep_field_id in self._fields:
                value = self._fields[dep_field_id].getValue()
                for field_widget, show_when in dependents:
                    visible = self._evaluate_show_when(show_when, value)
                    field_widget.setVisible(visible)


class CrossFieldValidator(QObject):
    """
    Validates fields that depend on other fields (e.g., equals_field).
    """

    validationChanged = pyqtSignal(str, bool, str)  # field_id, is_valid, error

    def __init__(self, fields: list[FieldWidget], parent: Optional[QObject] = None):
        super().__init__(parent)
        self._fields = {f.getFieldId(): f for f in fields}
        self._cross_validations: dict[str, str] = {}  # field_id -> equals_field_id

        self._setup_cross_validation()

    def _setup_cross_validation(self):
        """Set up cross-field validation rules."""
        for field_widget in self._fields.values():
            validation = field_widget.field_def.validation
            if validation and validation.equals_field:
                self._cross_validations[field_widget.getFieldId()] = validation.equals_field

                # Listen to changes on both fields
                field_widget.valueChanged.connect(self._on_value_changed)

                other_field_id = validation.equals_field
                if other_field_id in self._fields:
                    self._fields[other_field_id].valueChanged.connect(
                        self._on_value_changed
                    )

    def _on_value_changed(self, field_id: str, value: Any):
        """Handle value changes and revalidate cross-field rules."""
        # Check if this field has an equals_field validation
        if field_id in self._cross_validations:
            self._validate_equals(field_id)

        # Check if other fields depend on this field
        for check_field_id, equals_field_id in self._cross_validations.items():
            if equals_field_id == field_id:
                self._validate_equals(check_field_id)

    def _validate_equals(self, field_id: str):
        """Validate a field against its equals_field."""
        if field_id not in self._fields:
            return

        field_widget = self._fields[field_id]
        equals_field_id = self._cross_validations.get(field_id)

        if not equals_field_id or equals_field_id not in self._fields:
            return

        value = field_widget.getValue()
        other_value = self._fields[equals_field_id].getValue()

        is_valid = value == other_value
        error_msg = ""

        if not is_valid and value and other_value:
            validation = field_widget.field_def.validation
            error_msg = validation.message if validation else "Values must match"

        self.validationChanged.emit(field_id, is_valid, error_msg)
