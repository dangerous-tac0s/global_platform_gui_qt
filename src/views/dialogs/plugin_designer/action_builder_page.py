"""
Action Builder Page

Allows creating management actions through a visual interface.
Management actions are commands that can be run on installed applets.
"""

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QTextEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QComboBox,
    QCheckBox,
    QSplitter,
    QWidget,
    QTabWidget,
    QMessageBox,
)


class ApduSequenceDialog(QDialog):
    """Dialog for editing an APDU sequence entry."""

    def __init__(
        self,
        apdu_data: Optional[dict] = None,
        available_fields: Optional[list[dict]] = None,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("APDU Command")
        self.setMinimumSize(550, 350)

        self._apdu_data = apdu_data or {}
        self._available_fields = available_fields or []
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Main content in horizontal layout
        content_layout = QHBoxLayout()

        # Left side: Form
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        form = QFormLayout()

        # Command name
        self._command_edit = QLineEdit()
        self._command_edit.setPlaceholderText("e.g., SELECT_APPLET")
        form.addRow("Command Name:", self._command_edit)

        # APDU template
        self._apdu_edit = QLineEdit()
        self._apdu_edit.setPlaceholderText("e.g., 00A4040007{aid}")
        form.addRow("APDU Template:", self._apdu_edit)

        # Description
        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText("Selecting applet...")
        form.addRow("Description:", self._desc_edit)

        # Expected SW (optional)
        self._sw_edit = QLineEdit()
        self._sw_edit.setPlaceholderText("9000 (default)")
        form.addRow("Expected SW:", self._sw_edit)

        left_layout.addLayout(form)

        # Help text
        help_text = QLabel(
            "Use {field_id} placeholders for field values.\n"
            "Suffixes: _hex (hex encode), _length (byte length)"
        )
        help_text.setStyleSheet("color: gray; font-size: 10px;")
        left_layout.addWidget(help_text)
        left_layout.addStretch()

        content_layout.addWidget(left_widget, 2)

        # Right side: Available fields
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        right_layout.addWidget(QLabel("Available Fields (double-click):"))
        self._fields_list = QListWidget()
        self._fields_list.itemDoubleClicked.connect(self._insert_field)
        right_layout.addWidget(self._fields_list)

        # Populate fields list
        self._populate_fields_list()

        content_layout.addWidget(right_widget, 1)

        layout.addLayout(content_layout)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate_fields_list(self):
        """Populate the available fields list."""
        self._fields_list.clear()

        # Separate action dialog fields from install UI fields
        action_fields = [f for f in self._available_fields if f.get("_source") != "install_ui"]
        install_fields = [f for f in self._available_fields if f.get("_source") == "install_ui"]

        # Add action dialog fields
        if action_fields:
            header = QListWidgetItem("-- Action Dialog --")
            header.setFlags(header.flags() & ~Qt.ItemIsEnabled)
            header.setForeground(Qt.gray)
            self._fields_list.addItem(header)
            for field in action_fields:
                field_id = field.get("id", "?")
                field_type = field.get("type", "text")
                item = QListWidgetItem(f"  {field_id} [{field_type}]")
                item.setData(Qt.UserRole, field_id)
                self._fields_list.addItem(item)

        # Add install UI fields
        if install_fields:
            header = QListWidgetItem("-- Install UI --")
            header.setFlags(header.flags() & ~Qt.ItemIsEnabled)
            header.setForeground(Qt.gray)
            self._fields_list.addItem(header)
            for field in install_fields:
                field_id = field.get("id", "?")
                field_type = field.get("type", "text")
                item = QListWidgetItem(f"  {field_id} [{field_type}]")
                item.setData(Qt.UserRole, field_id)
                self._fields_list.addItem(item)

        # Add built-in fields
        header = QListWidgetItem("-- Built-in --")
        header.setFlags(header.flags() & ~Qt.ItemIsEnabled)
        header.setForeground(Qt.gray)
        self._fields_list.addItem(header)
        for field_id in ["aid", "package_aid", "applet_aid"]:
            item = QListWidgetItem(f"  {field_id}")
            item.setData(Qt.UserRole, field_id)
            self._fields_list.addItem(item)

    def _insert_field(self, item: QListWidgetItem):
        """Insert field into APDU template."""
        field_id = item.data(Qt.UserRole)
        if not field_id:
            return

        current = self._apdu_edit.text()
        cursor_pos = self._apdu_edit.cursorPosition()
        new_text = current[:cursor_pos] + "{" + field_id + "}" + current[cursor_pos:]
        self._apdu_edit.setText(new_text)
        self._apdu_edit.setCursorPosition(cursor_pos + len(field_id) + 2)
        self._apdu_edit.setFocus()

    def _load_data(self):
        """Load existing APDU data."""
        if not self._apdu_data:
            return

        self._command_edit.setText(self._apdu_data.get("command", ""))
        self._apdu_edit.setText(self._apdu_data.get("apdu", ""))
        self._desc_edit.setText(self._apdu_data.get("description", ""))
        self._sw_edit.setText(self._apdu_data.get("expect_sw", ""))

    def get_apdu_data(self) -> dict:
        """Get the APDU command data."""
        data = {
            "command": self._command_edit.text().strip(),
            "apdu": self._apdu_edit.text().strip(),
        }

        desc = self._desc_edit.text().strip()
        if desc:
            data["description"] = desc

        sw = self._sw_edit.text().strip()
        if sw:
            data["expect_sw"] = sw

        return data


class ActionFieldDialog(QDialog):
    """Dialog for editing an action dialog field."""

    def __init__(self, field_data: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dialog Field")
        self.setMinimumWidth(400)

        self._field_data = field_data or {}
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # Field ID
        self._id_edit = QLineEdit()
        self._id_edit.setPlaceholderText("e.g., new_pin")
        form.addRow("Field ID:", self._id_edit)

        # Field Type
        self._type_combo = QComboBox()
        self._type_combo.addItems([
            "text",
            "password",
            "number",
            "dropdown",
            "checkbox",
            "hex_editor",
            "file",
        ])
        form.addRow("Type:", self._type_combo)

        # Label
        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("New PIN")
        form.addRow("Label:", self._label_edit)

        # Required
        self._required_check = QCheckBox()
        form.addRow("Required:", self._required_check)

        # Placeholder
        self._placeholder_edit = QLineEdit()
        form.addRow("Placeholder:", self._placeholder_edit)

        layout.addLayout(form)

        # Validation group
        validation_group = QGroupBox("Validation (optional)")
        val_layout = QFormLayout(validation_group)

        self._min_length_edit = QLineEdit()
        self._min_length_edit.setPlaceholderText("e.g., 6")
        val_layout.addRow("Min Length:", self._min_length_edit)

        self._max_length_edit = QLineEdit()
        self._max_length_edit.setPlaceholderText("e.g., 127")
        val_layout.addRow("Max Length:", self._max_length_edit)

        self._equals_field_edit = QLineEdit()
        self._equals_field_edit.setPlaceholderText("e.g., new_pin (for confirmation)")
        val_layout.addRow("Equals Field:", self._equals_field_edit)

        layout.addWidget(validation_group)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self):
        """Validate field data before accepting."""
        import re

        field_id = self._id_edit.text().strip()

        if not field_id:
            QMessageBox.warning(
                self,
                "Field ID Required",
                "Please enter a field ID.",
            )
            self._id_edit.setFocus()
            return

        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', field_id):
            QMessageBox.warning(
                self,
                "Invalid Field ID",
                f"'{field_id}' is not a valid identifier.\n\n"
                "Field IDs must start with a letter or underscore "
                "and contain only letters, numbers, and underscores.",
            )
            self._id_edit.setFocus()
            return

        label = self._label_edit.text().strip()
        if not label:
            QMessageBox.warning(
                self,
                "Label Required",
                "Please enter a display label.",
            )
            self._label_edit.setFocus()
            return

        self.accept()

    def _load_data(self):
        """Load existing field data."""
        if not self._field_data:
            return

        self._id_edit.setText(self._field_data.get("id", ""))
        self._label_edit.setText(self._field_data.get("label", ""))
        self._required_check.setChecked(self._field_data.get("required", False))
        self._placeholder_edit.setText(self._field_data.get("placeholder", ""))

        # Set type
        field_type = self._field_data.get("type", "text")
        index = self._type_combo.findText(field_type)
        if index >= 0:
            self._type_combo.setCurrentIndex(index)

        # Validation
        validation = self._field_data.get("validation", {})
        if "min_length" in validation:
            self._min_length_edit.setText(str(validation["min_length"]))
        if "max_length" in validation:
            self._max_length_edit.setText(str(validation["max_length"]))
        if "equals_field" in validation:
            self._equals_field_edit.setText(validation["equals_field"])

    def get_field_data(self) -> dict:
        """Get the field definition data."""
        data = {
            "id": self._id_edit.text().strip(),
            "type": self._type_combo.currentText(),
            "label": self._label_edit.text().strip(),
        }

        if self._required_check.isChecked():
            data["required"] = True

        placeholder = self._placeholder_edit.text().strip()
        if placeholder:
            data["placeholder"] = placeholder

        # Validation
        validation = {}
        min_len = self._min_length_edit.text().strip()
        if min_len:
            try:
                validation["min_length"] = int(min_len)
            except ValueError:
                pass

        max_len = self._max_length_edit.text().strip()
        if max_len:
            try:
                validation["max_length"] = int(max_len)
            except ValueError:
                pass

        equals = self._equals_field_edit.text().strip()
        if equals:
            validation["equals_field"] = equals

        if validation:
            data["validation"] = validation

        return data


class ActionDefinitionDialog(QDialog):
    """Dialog for editing a management action."""

    def __init__(
        self,
        action_data: Optional[dict] = None,
        install_ui_fields: Optional[list[dict]] = None,
        available_workflows: Optional[list[str]] = None,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Management Action")
        self.setMinimumSize(600, 500)

        self._action_data = action_data or {}
        self._install_ui_fields = install_ui_fields or []
        self._available_workflows = available_workflows or []
        self._fields: list[dict] = []
        self._apdu_sequence: list[dict] = []
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Basic info
        form = QFormLayout()

        self._id_edit = QLineEdit()
        self._id_edit.setPlaceholderText("e.g., change_pin")
        form.addRow("Action ID:", self._id_edit)

        self._label_edit = QLineEdit()
        self._label_edit.setPlaceholderText("Change PIN")
        form.addRow("Label:", self._label_edit)

        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText("Change the user PIN")
        form.addRow("Description:", self._desc_edit)

        # Confirm message (optional)
        self._confirm_edit = QLineEdit()
        self._confirm_edit.setPlaceholderText("(Optional) Confirmation prompt")
        form.addRow("Confirm Message:", self._confirm_edit)

        # Workflow reference (optional)
        workflow_layout = QVBoxLayout()
        self._workflow_edit = QLineEdit()
        self._workflow_edit.setPlaceholderText("(Optional) workflow_id")
        workflow_layout.addWidget(self._workflow_edit)
        workflow_hint = QLabel("Define workflows in the next wizard step, then reference them here by ID")
        workflow_hint.setStyleSheet("color: gray; font-size: 10px;")
        workflow_layout.addWidget(workflow_hint)
        form.addRow("Workflow:", workflow_layout)

        layout.addLayout(form)

        # Tabs for dialog fields and APDU sequence
        tabs = QTabWidget()

        # Dialog fields tab
        fields_widget = QWidget()
        fields_layout = QVBoxLayout(fields_widget)
        fields_layout.setContentsMargins(0, 10, 0, 0)

        fields_layout.addWidget(QLabel("User input fields:"))

        self._fields_list = QListWidget()
        self._fields_list.itemDoubleClicked.connect(self._edit_field)
        fields_layout.addWidget(self._fields_list)

        field_btn_layout = QHBoxLayout()
        add_field_btn = QPushButton("Add Field")
        add_field_btn.clicked.connect(self._add_field)
        field_btn_layout.addWidget(add_field_btn)

        edit_field_btn = QPushButton("Edit")
        edit_field_btn.clicked.connect(self._edit_selected_field)
        field_btn_layout.addWidget(edit_field_btn)

        remove_field_btn = QPushButton("Remove")
        remove_field_btn.clicked.connect(self._remove_field)
        field_btn_layout.addWidget(remove_field_btn)

        field_btn_layout.addStretch()
        fields_layout.addLayout(field_btn_layout)

        tabs.addTab(fields_widget, "Dialog Fields")

        # APDU sequence tab
        apdu_widget = QWidget()
        apdu_layout = QVBoxLayout(apdu_widget)
        apdu_layout.setContentsMargins(0, 10, 0, 0)

        apdu_layout.addWidget(QLabel("APDU commands to execute:"))

        self._apdu_list = QListWidget()
        self._apdu_list.itemDoubleClicked.connect(self._edit_apdu)
        apdu_layout.addWidget(self._apdu_list)

        apdu_btn_layout = QHBoxLayout()
        add_apdu_btn = QPushButton("Add APDU")
        add_apdu_btn.clicked.connect(self._add_apdu)
        apdu_btn_layout.addWidget(add_apdu_btn)

        edit_apdu_btn = QPushButton("Edit")
        edit_apdu_btn.clicked.connect(self._edit_selected_apdu)
        apdu_btn_layout.addWidget(edit_apdu_btn)

        remove_apdu_btn = QPushButton("Remove")
        remove_apdu_btn.clicked.connect(self._remove_apdu)
        apdu_btn_layout.addWidget(remove_apdu_btn)

        apdu_btn_layout.addStretch()

        move_up_btn = QPushButton("Move Up")
        move_up_btn.clicked.connect(self._move_apdu_up)
        apdu_btn_layout.addWidget(move_up_btn)

        move_down_btn = QPushButton("Move Down")
        move_down_btn.clicked.connect(self._move_apdu_down)
        apdu_btn_layout.addWidget(move_down_btn)

        apdu_layout.addLayout(apdu_btn_layout)

        tabs.addTab(apdu_widget, "APDU Sequence")

        layout.addWidget(tabs)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _validate_and_accept(self):
        """Validate action data before accepting."""
        import re

        action_id = self._id_edit.text().strip()

        if not action_id:
            QMessageBox.warning(
                self,
                "Action ID Required",
                "Please enter an action ID.\n\n"
                "The action ID is used to identify this action in the plugin.",
            )
            self._id_edit.setFocus()
            return

        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', action_id):
            QMessageBox.warning(
                self,
                "Invalid Action ID",
                f"'{action_id}' is not a valid identifier.\n\n"
                "Action IDs must start with a letter or underscore "
                "and contain only letters, numbers, and underscores.",
            )
            self._id_edit.setFocus()
            return

        label = self._label_edit.text().strip()
        if not label:
            QMessageBox.warning(
                self,
                "Label Required",
                "Please enter a display label for the action.",
            )
            self._label_edit.setFocus()
            return

        self.accept()

    def _load_data(self):
        """Load existing action data."""
        if not self._action_data:
            return

        self._id_edit.setText(self._action_data.get("id", ""))
        self._label_edit.setText(self._action_data.get("label", ""))
        self._desc_edit.setText(self._action_data.get("description", ""))
        self._confirm_edit.setText(self._action_data.get("confirm", ""))
        self._workflow_edit.setText(self._action_data.get("workflow", ""))

        # Load dialog fields
        dialog = self._action_data.get("dialog", {})
        self._fields = dialog.get("fields", []).copy()
        self._update_fields_list()

        # Load APDU sequence
        self._apdu_sequence = self._action_data.get("apdu_sequence", []).copy()
        self._update_apdu_list()

    def _update_fields_list(self):
        """Update the fields list display."""
        self._fields_list.clear()
        for field in self._fields:
            field_id = field.get("id", "?")
            field_type = field.get("type", "text")
            label = field.get("label", field_id)
            required = "*" if field.get("required") else ""
            item_text = f"{label}{required} [{field_type}]"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, field)
            self._fields_list.addItem(item)

    def _update_apdu_list(self):
        """Update the APDU list display."""
        self._apdu_list.clear()
        for i, apdu in enumerate(self._apdu_sequence):
            command = apdu.get("command", f"Step {i+1}")
            apdu_str = apdu.get("apdu", "")
            item_text = f"{command}: {apdu_str[:30]}..."
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, apdu)
            self._apdu_list.addItem(item)

    def _add_field(self):
        """Add a new dialog field."""
        dialog = ActionFieldDialog(parent=self)
        if dialog.exec_() == QDialog.Accepted:
            field_data = dialog.get_field_data()
            if field_data.get("id"):
                self._fields.append(field_data)
                self._update_fields_list()

    def _edit_field(self, item: QListWidgetItem):
        """Edit a field by double-clicking."""
        index = self._fields_list.row(item)
        if 0 <= index < len(self._fields):
            self._edit_field_at(index)

    def _edit_selected_field(self):
        """Edit the selected field."""
        current = self._fields_list.currentRow()
        if current >= 0:
            self._edit_field_at(current)

    def _edit_field_at(self, index: int):
        """Edit field at index."""
        if 0 <= index < len(self._fields):
            dialog = ActionFieldDialog(self._fields[index], parent=self)
            if dialog.exec_() == QDialog.Accepted:
                self._fields[index] = dialog.get_field_data()
                self._update_fields_list()

    def _remove_field(self):
        """Remove selected field."""
        current = self._fields_list.currentRow()
        if 0 <= current < len(self._fields):
            self._fields.pop(current)
            self._update_fields_list()

    def _get_all_available_fields(self) -> list[dict]:
        """Get all available fields (action dialog + install UI)."""
        all_fields = []
        # Action dialog fields first (most relevant)
        all_fields.extend(self._fields)
        # Then install UI fields
        for field in self._install_ui_fields:
            # Mark as from install UI to distinguish
            field_copy = field.copy()
            field_copy["_source"] = "install_ui"
            all_fields.append(field_copy)
        return all_fields

    def _add_apdu(self):
        """Add a new APDU command."""
        dialog = ApduSequenceDialog(
            available_fields=self._get_all_available_fields(),
            parent=self
        )
        if dialog.exec_() == QDialog.Accepted:
            apdu_data = dialog.get_apdu_data()
            if apdu_data.get("apdu"):
                self._apdu_sequence.append(apdu_data)
                self._update_apdu_list()

    def _edit_apdu(self, item: QListWidgetItem):
        """Edit an APDU by double-clicking."""
        index = self._apdu_list.row(item)
        if 0 <= index < len(self._apdu_sequence):
            self._edit_apdu_at(index)

    def _edit_selected_apdu(self):
        """Edit the selected APDU."""
        current = self._apdu_list.currentRow()
        if current >= 0:
            self._edit_apdu_at(current)

    def _edit_apdu_at(self, index: int):
        """Edit APDU at index."""
        if 0 <= index < len(self._apdu_sequence):
            dialog = ApduSequenceDialog(
                apdu_data=self._apdu_sequence[index],
                available_fields=self._get_all_available_fields(),
                parent=self
            )
            if dialog.exec_() == QDialog.Accepted:
                self._apdu_sequence[index] = dialog.get_apdu_data()
                self._update_apdu_list()

    def _remove_apdu(self):
        """Remove selected APDU."""
        current = self._apdu_list.currentRow()
        if 0 <= current < len(self._apdu_sequence):
            self._apdu_sequence.pop(current)
            self._update_apdu_list()

    def _move_apdu_up(self):
        """Move selected APDU up."""
        current = self._apdu_list.currentRow()
        if current > 0:
            self._apdu_sequence[current], self._apdu_sequence[current - 1] = \
                self._apdu_sequence[current - 1], self._apdu_sequence[current]
            self._update_apdu_list()
            self._apdu_list.setCurrentRow(current - 1)

    def _move_apdu_down(self):
        """Move selected APDU down."""
        current = self._apdu_list.currentRow()
        if 0 <= current < len(self._apdu_sequence) - 1:
            self._apdu_sequence[current], self._apdu_sequence[current + 1] = \
                self._apdu_sequence[current + 1], self._apdu_sequence[current]
            self._update_apdu_list()
            self._apdu_list.setCurrentRow(current + 1)

    def get_action_data(self) -> dict:
        """Get the action definition data."""
        data = {
            "id": self._id_edit.text().strip(),
            "label": self._label_edit.text().strip(),
        }

        desc = self._desc_edit.text().strip()
        if desc:
            data["description"] = desc

        confirm = self._confirm_edit.text().strip()
        if confirm:
            data["confirm"] = confirm

        workflow = self._workflow_edit.text().strip()
        if workflow:
            data["workflow"] = workflow

        # Dialog fields
        if self._fields:
            data["dialog"] = {"fields": self._fields}

        # APDU sequence
        if self._apdu_sequence:
            data["apdu_sequence"] = self._apdu_sequence

        return data


class ActionBuilderPage(QWizardPage):
    """Build management actions for the plugin."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Management Actions")
        self.setSubTitle(
            "Define actions that can be performed on installed applets "
            "(e.g., change PIN, generate keys)."
        )

        self._actions: list[dict] = []
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Actions list
        layout.addWidget(QLabel("Management Actions:"))

        self._actions_list = QListWidget()
        self._actions_list.itemDoubleClicked.connect(self._edit_action)
        layout.addWidget(self._actions_list)

        # Buttons
        btn_layout = QHBoxLayout()

        add_btn = QPushButton("Add Action")
        add_btn.clicked.connect(self._add_action)
        btn_layout.addWidget(add_btn)

        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit_selected_action)
        btn_layout.addWidget(edit_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_action)
        btn_layout.addWidget(remove_btn)

        btn_layout.addStretch()

        move_up_btn = QPushButton("Move Up")
        move_up_btn.clicked.connect(self._move_action_up)
        btn_layout.addWidget(move_up_btn)

        move_down_btn = QPushButton("Move Down")
        move_down_btn.clicked.connect(self._move_action_down)
        btn_layout.addWidget(move_down_btn)

        layout.addLayout(btn_layout)

        # Skip checkbox
        self._skip_check = QCheckBox("Skip management UI (no post-install configuration)")
        self._skip_check.stateChanged.connect(self._on_skip_changed)
        layout.addWidget(self._skip_check)

    def initializePage(self):
        """Load existing actions when editing."""
        wizard = self.wizard()
        if not wizard:
            return

        # Get management_ui.actions from loaded plugin data
        actions = wizard.get_plugin_value("management_ui.actions", [])
        if actions and not self._actions:  # Only load if not already populated
            # Deep copy to avoid modifying original data
            import copy
            self._actions = copy.deepcopy(actions)

        # Always update list to ensure UI reflects current state
        if self._actions:
            self._update_list()

    def _on_skip_changed(self, state):
        """Handle skip checkbox change."""
        self._actions_list.setEnabled(state != Qt.Checked)

    def _get_install_ui_fields(self) -> list[dict]:
        """Get install UI fields from the wizard for variable references."""
        wizard = self.wizard()
        if not wizard:
            return []
        # Get fields from install_ui.form.fields
        fields = wizard.get_plugin_value("install_ui.form.fields", [])
        return fields if fields else []

    def _get_existing_action_ids(self, exclude_index: int = -1) -> set:
        """Get set of existing action IDs, optionally excluding one index."""
        ids = set()
        for i, action in enumerate(self._actions):
            if i != exclude_index:
                ids.add(action.get("id", ""))
        return ids

    def _add_action(self):
        """Add a new action."""
        dialog = ActionDefinitionDialog(
            install_ui_fields=self._get_install_ui_fields(),
            parent=self
        )
        if dialog.exec_() == QDialog.Accepted:
            action_data = dialog.get_action_data()
            action_id = action_data.get("id")
            if action_id:
                # Check for duplicate ID
                if action_id in self._get_existing_action_ids():
                    QMessageBox.warning(
                        self,
                        "Duplicate Action ID",
                        f"An action with ID '{action_id}' already exists.\n\n"
                        "Please use a unique action ID.",
                    )
                    return
                self._actions.append(action_data)
                self._update_list()

    def _edit_action(self, item: QListWidgetItem):
        """Edit an action by double-clicking."""
        index = self._actions_list.row(item)
        if 0 <= index < len(self._actions):
            self._edit_action_at(index)

    def _edit_selected_action(self):
        """Edit the selected action."""
        current = self._actions_list.currentRow()
        if current >= 0:
            self._edit_action_at(current)

    def _edit_action_at(self, index: int):
        """Edit action at index."""
        if 0 <= index < len(self._actions):
            dialog = ActionDefinitionDialog(
                action_data=self._actions[index],
                install_ui_fields=self._get_install_ui_fields(),
                parent=self
            )
            if dialog.exec_() == QDialog.Accepted:
                action_data = dialog.get_action_data()
                action_id = action_data.get("id")
                # Check for duplicate ID (excluding current action)
                if action_id and action_id in self._get_existing_action_ids(exclude_index=index):
                    QMessageBox.warning(
                        self,
                        "Duplicate Action ID",
                        f"An action with ID '{action_id}' already exists.\n\n"
                        "Please use a unique action ID.",
                    )
                    return
                self._actions[index] = action_data
                self._update_list()

    def _remove_action(self):
        """Remove selected action."""
        current = self._actions_list.currentRow()
        if 0 <= current < len(self._actions):
            self._actions.pop(current)
            self._update_list()

    def _move_action_up(self):
        """Move selected action up."""
        current = self._actions_list.currentRow()
        if current > 0:
            self._actions[current], self._actions[current - 1] = \
                self._actions[current - 1], self._actions[current]
            self._update_list()
            self._actions_list.setCurrentRow(current - 1)

    def _move_action_down(self):
        """Move selected action down."""
        current = self._actions_list.currentRow()
        if 0 <= current < len(self._actions) - 1:
            self._actions[current], self._actions[current + 1] = \
                self._actions[current + 1], self._actions[current]
            self._update_list()
            self._actions_list.setCurrentRow(current + 1)

    def _update_list(self):
        """Update the actions list display."""
        self._actions_list.clear()

        for action in self._actions:
            action_id = action.get("id", "?")
            label = action.get("label", action_id)
            has_workflow = "workflow" in action
            has_apdu = "apdu_sequence" in action

            suffix = ""
            if has_workflow:
                suffix = f" -> {action['workflow']}"
            elif has_apdu:
                suffix = f" ({len(action['apdu_sequence'])} APDUs)"

            item_text = f"{label}{suffix}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, action)
            self._actions_list.addItem(item)

    def validatePage(self) -> bool:
        """Validate and save data."""
        wizard = self.wizard()
        if not wizard:
            return True

        if self._skip_check.isChecked() or not self._actions:
            wizard.set_plugin_data("management_ui", None)
        else:
            wizard.set_plugin_data("management_ui.actions", self._actions)

        return True
