"""
Workflow Builder Page

Allows creating multi-step workflows through a visual interface.
Workflows are sequences of operations that can include APDU commands,
user dialogs, scripts, and confirmations.
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
    QTreeWidget,
    QTreeWidgetItem,
    QToolTip,
    QFileDialog,
    QMessageBox,
)
from PyQt5.QtGui import QCursor


class WorkflowStepDialog(QDialog):
    """Dialog for editing a workflow step."""

    STEP_TYPES = [
        ("apdu", "APDU Command"),
        ("dialog", "User Dialog"),
        ("script", "Python Script"),
        ("confirmation", "Confirmation"),
    ]

    def __init__(
        self,
        step_data: Optional[dict] = None,
        existing_steps: list[str] = None,
        available_variables: Optional[dict[str, list[dict]]] = None,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Workflow Step")
        self.setMinimumSize(700, 550)

        self._step_data = step_data or {}
        self._existing_steps = existing_steps or []
        self._available_variables = available_variables or {}
        self._fields: list[dict] = []
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Main content in horizontal splitter
        splitter = QSplitter(Qt.Horizontal)

        # Left side: Step configuration
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # Basic info
        form = QFormLayout()

        self._id_edit = QLineEdit()
        self._id_edit.setPlaceholderText("e.g., verify_pin")
        form.addRow("Step ID:", self._id_edit)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("Verify PIN")
        form.addRow("Display Name:", self._name_edit)

        self._type_combo = QComboBox()
        for type_id, type_label in self.STEP_TYPES:
            self._type_combo.addItem(type_label, type_id)
        self._type_combo.currentIndexChanged.connect(self._on_type_changed)
        form.addRow("Step Type:", self._type_combo)

        left_layout.addLayout(form)

        # Dependencies
        deps_group = QGroupBox("Dependencies (check steps that must complete first)")
        deps_layout = QVBoxLayout(deps_group)

        self._deps_list = QListWidget()
        self._deps_list.setMaximumHeight(80)
        # Use checkboxes instead of multi-selection for clearer UX
        deps_layout.addWidget(self._deps_list)

        self._deps_hint = QLabel(
            "No other steps exist yet.\n"
            "After adding more steps to this workflow, you can edit this step\n"
            "to set which steps must complete before this one runs."
        )
        self._deps_hint.setStyleSheet("color: gray; font-size: 10px; font-style: italic;")
        deps_layout.addWidget(self._deps_hint)

        left_layout.addWidget(deps_group)

        # Type-specific configuration
        self._config_stack = QWidget()
        self._config_layout = QVBoxLayout(self._config_stack)
        self._config_layout.setContentsMargins(0, 0, 0, 0)

        # APDU config
        self._apdu_group = QGroupBox("APDU Configuration")
        apdu_layout = QFormLayout(self._apdu_group)

        self._apdu_edit = QLineEdit()
        self._apdu_edit.setPlaceholderText("e.g., 00200081{pin_length}{pin_hex}")
        apdu_layout.addRow("APDU Template:", self._apdu_edit)

        self._apdu_desc_edit = QLineEdit()
        self._apdu_desc_edit.setPlaceholderText("Verifying PIN...")
        apdu_layout.addRow("Description:", self._apdu_desc_edit)

        self._config_layout.addWidget(self._apdu_group)

        # Dialog config
        self._dialog_group = QGroupBox("Dialog Configuration")
        dialog_layout = QVBoxLayout(self._dialog_group)

        dialog_layout.addWidget(QLabel("Fields to collect from user:"))
        self._dialog_fields_list = QListWidget()
        self._dialog_fields_list.setMaximumHeight(100)
        dialog_layout.addWidget(self._dialog_fields_list)

        dialog_btn_layout = QHBoxLayout()
        add_field_btn = QPushButton("Add Field")
        add_field_btn.clicked.connect(self._add_dialog_field)
        dialog_btn_layout.addWidget(add_field_btn)

        remove_field_btn = QPushButton("Remove")
        remove_field_btn.clicked.connect(self._remove_dialog_field)
        dialog_btn_layout.addWidget(remove_field_btn)
        dialog_btn_layout.addStretch()
        dialog_layout.addLayout(dialog_btn_layout)

        self._config_layout.addWidget(self._dialog_group)

        # Script config
        self._script_group = QGroupBox("Script Configuration")
        script_layout = QVBoxLayout(self._script_group)

        from .python_editor import PythonScriptEditor
        self._script_edit = PythonScriptEditor()
        self._script_edit.setMaximumHeight(180)
        script_layout.addWidget(self._script_edit)

        self._config_layout.addWidget(self._script_group)

        # Confirmation config
        self._confirm_group = QGroupBox("Confirmation Configuration")
        confirm_layout = QFormLayout(self._confirm_group)

        self._confirm_message_edit = QLineEdit()
        self._confirm_message_edit.setPlaceholderText("Are you sure you want to proceed?")
        confirm_layout.addRow("Message:", self._confirm_message_edit)

        self._config_layout.addWidget(self._confirm_group)

        left_layout.addWidget(self._config_stack)

        # Show appropriate config for default type
        self._on_type_changed(0)

        splitter.addWidget(left_widget)

        # Right side: Available variables panel
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)

        vars_group = QGroupBox("Available Variables (double-click to insert)")
        vars_layout = QVBoxLayout(vars_group)

        self._vars_tree = QTreeWidget()
        self._vars_tree.setHeaderLabels(["Variable", "Type"])
        self._vars_tree.setColumnWidth(0, 150)
        self._vars_tree.itemDoubleClicked.connect(self._insert_variable)
        vars_layout.addWidget(self._vars_tree)

        hint = QLabel("Use {variable_id} in APDU templates\nor context.get('variable_id') in scripts")
        hint.setStyleSheet("color: gray; font-size: 10px;")
        hint.setWordWrap(True)
        vars_layout.addWidget(hint)

        right_layout.addWidget(vars_group)
        splitter.addWidget(right_widget)

        # Set splitter sizes (60% left, 40% right)
        splitter.setSizes([400, 250])

        layout.addWidget(splitter)

        # Populate variables tree
        self._populate_variables_tree()

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_type_changed(self, index: int):
        """Show appropriate configuration for selected type."""
        step_type = self._type_combo.currentData()

        self._apdu_group.setVisible(step_type == "apdu")
        self._dialog_group.setVisible(step_type == "dialog")
        self._script_group.setVisible(step_type == "script")
        self._confirm_group.setVisible(step_type == "confirmation")

    def _populate_variables_tree(self):
        """Populate the available variables tree."""
        self._vars_tree.clear()

        # Install UI fields
        install_fields = self._available_variables.get("install_ui", [])
        if install_fields:
            install_item = QTreeWidgetItem(self._vars_tree, ["Install UI Fields", ""])
            install_item.setExpanded(True)
            for field in install_fields:
                field_id = field.get("id", "?")
                field_type = field.get("type", "text")
                child = QTreeWidgetItem(install_item, [field_id, field_type])
                child.setData(0, Qt.UserRole, field_id)

        # Management action fields
        action_fields = self._available_variables.get("action_fields", [])
        if action_fields:
            action_item = QTreeWidgetItem(self._vars_tree, ["Action Dialog Fields", ""])
            action_item.setExpanded(True)
            for field in action_fields:
                field_id = field.get("id", "?")
                field_type = field.get("type", "text")
                child = QTreeWidgetItem(action_item, [field_id, field_type])
                child.setData(0, Qt.UserRole, field_id)

        # Previous workflow steps
        if self._existing_steps:
            steps_item = QTreeWidgetItem(self._vars_tree, ["Previous Steps", ""])
            steps_item.setExpanded(True)
            for step_id in self._existing_steps:
                child = QTreeWidgetItem(steps_item, [f"{step_id}_result", "result"])
                child.setData(0, Qt.UserRole, f"{step_id}_result")

        # Built-in variables
        builtins = QTreeWidgetItem(self._vars_tree, ["Built-in", ""])
        builtins.setExpanded(True)
        for var_id, var_type in [("aid", "hex"), ("package_aid", "hex"), ("applet_aid", "hex")]:
            child = QTreeWidgetItem(builtins, [var_id, var_type])
            child.setData(0, Qt.UserRole, var_id)

        if self._vars_tree.topLevelItemCount() == 0:
            empty = QTreeWidgetItem(self._vars_tree, ["(no variables defined)", ""])
            empty.setDisabled(True)

    def _insert_variable(self, item: QTreeWidgetItem, column: int):
        """Insert selected variable into current input."""
        var_id = item.data(0, Qt.UserRole)
        if not var_id:
            return  # Clicked on a group header

        step_type = self._type_combo.currentData()

        if step_type == "apdu":
            # Insert as template variable
            current = self._apdu_edit.text()
            cursor_pos = self._apdu_edit.cursorPosition()
            new_text = current[:cursor_pos] + "{" + var_id + "}" + current[cursor_pos:]
            self._apdu_edit.setText(new_text)
            self._apdu_edit.setCursorPosition(cursor_pos + len(var_id) + 2)
            self._apdu_edit.setFocus()

        elif step_type == "script":
            # Insert as context.get() call
            cursor = self._script_edit.textCursor()
            cursor.insertText(f"context.get('{var_id}')")
            self._script_edit.setFocus()

        elif step_type == "confirmation":
            # Insert as template variable in message
            current = self._confirm_message_edit.text()
            cursor_pos = self._confirm_message_edit.cursorPosition()
            new_text = current[:cursor_pos] + "{" + var_id + "}" + current[cursor_pos:]
            self._confirm_message_edit.setText(new_text)
            self._confirm_message_edit.setCursorPosition(cursor_pos + len(var_id) + 2)
            self._confirm_message_edit.setFocus()

    def _load_data(self):
        """Load existing step data."""
        # Populate dependency options with checkboxes
        self._deps_list.clear()
        depends_on = self._step_data.get("depends_on", []) if self._step_data else []

        for step_id in self._existing_steps:
            if step_id != self._step_data.get("id") if self._step_data else True:
                item = QListWidgetItem(step_id)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                # Check if this step is a dependency
                item.setCheckState(Qt.Checked if step_id in depends_on else Qt.Unchecked)
                self._deps_list.addItem(item)

        # Show/hide hint based on available dependencies
        has_deps = self._deps_list.count() > 0
        self._deps_list.setVisible(has_deps)
        self._deps_hint.setVisible(not has_deps)

        if not self._step_data:
            return

        self._id_edit.setText(self._step_data.get("id", ""))
        self._name_edit.setText(self._step_data.get("name", ""))

        # Set type
        step_type = self._step_data.get("type", "apdu")
        for i in range(self._type_combo.count()):
            if self._type_combo.itemData(i) == step_type:
                self._type_combo.setCurrentIndex(i)
                break

        # Load type-specific config
        if step_type == "apdu":
            self._apdu_edit.setText(self._step_data.get("apdu", ""))
            self._apdu_desc_edit.setText(self._step_data.get("description", ""))

        elif step_type == "dialog":
            self._fields = self._step_data.get("fields", []).copy()
            self._update_dialog_fields_list()

        elif step_type == "script":
            self._script_edit.setPlainText(self._step_data.get("script", ""))

        elif step_type == "confirmation":
            self._confirm_message_edit.setText(self._step_data.get("message", ""))

    def _update_dialog_fields_list(self):
        """Update the dialog fields list."""
        self._dialog_fields_list.clear()
        for field in self._fields:
            field_id = field.get("id", "?")
            field_type = field.get("type", "text")
            label = field.get("label", field_id)
            self._dialog_fields_list.addItem(f"{label} [{field_type}]")

    def _add_dialog_field(self):
        """Add a dialog field."""
        from .action_builder_page import ActionFieldDialog
        dialog = ActionFieldDialog(parent=self)
        if dialog.exec_() == QDialog.Accepted:
            field_data = dialog.get_field_data()
            if field_data.get("id"):
                self._fields.append(field_data)
                self._update_dialog_fields_list()

    def _remove_dialog_field(self):
        """Remove selected dialog field."""
        current = self._dialog_fields_list.currentRow()
        if 0 <= current < len(self._fields):
            self._fields.pop(current)
            self._update_dialog_fields_list()

    def get_step_data(self) -> dict:
        """Get the step definition data."""
        step_type = self._type_combo.currentData()

        data = {
            "id": self._id_edit.text().strip(),
            "name": self._name_edit.text().strip(),
            "type": step_type,
        }

        # Dependencies (using checkboxes)
        selected_deps = []
        for i in range(self._deps_list.count()):
            item = self._deps_list.item(i)
            if item.checkState() == Qt.Checked:
                selected_deps.append(item.text())
        if selected_deps:
            data["depends_on"] = selected_deps

        # Type-specific data
        if step_type == "apdu":
            data["apdu"] = self._apdu_edit.text().strip()
            desc = self._apdu_desc_edit.text().strip()
            if desc:
                data["description"] = desc

        elif step_type == "dialog":
            if self._fields:
                data["fields"] = self._fields

        elif step_type == "script":
            data["script"] = self._script_edit.toPlainText()

        elif step_type == "confirmation":
            data["message"] = self._confirm_message_edit.text().strip()

        return data


class WorkflowDefinitionDialog(QDialog):
    """Dialog for editing a complete workflow."""

    def __init__(
        self,
        workflow_id: str = "",
        workflow_data: Optional[dict] = None,
        available_variables: Optional[dict[str, list[dict]]] = None,
        parent=None
    ):
        super().__init__(parent)
        self.setWindowTitle("Workflow Definition")
        self.setMinimumSize(700, 550)

        self._workflow_id = workflow_id
        self._workflow_data = workflow_data or {"steps": []}
        self._available_variables = available_variables or {}
        self._steps: list[dict] = []
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Workflow ID
        form = QFormLayout()
        self._id_edit = QLineEdit()
        self._id_edit.setText(self._workflow_id)
        self._id_edit.setPlaceholderText("e.g., key_generation")
        form.addRow("Workflow ID:", self._id_edit)
        layout.addLayout(form)

        # Steps
        layout.addWidget(QLabel("Workflow Steps:"))

        splitter = QSplitter(Qt.Horizontal)

        # Steps list
        steps_widget = QWidget()
        steps_layout = QVBoxLayout(steps_widget)
        steps_layout.setContentsMargins(0, 0, 0, 0)

        self._steps_list = QListWidget()
        self._steps_list.itemDoubleClicked.connect(self._edit_step)
        self._steps_list.currentRowChanged.connect(self._on_step_selected)
        steps_layout.addWidget(self._steps_list)

        btn_layout = QHBoxLayout()

        add_btn = QPushButton("Add Step")
        add_btn.clicked.connect(self._add_step)
        btn_layout.addWidget(add_btn)

        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit_selected_step)
        btn_layout.addWidget(edit_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_step)
        btn_layout.addWidget(remove_btn)

        btn_layout.addStretch()
        steps_layout.addLayout(btn_layout)

        move_layout = QHBoxLayout()
        move_up_btn = QPushButton("Move Up")
        move_up_btn.clicked.connect(self._move_step_up)
        move_layout.addWidget(move_up_btn)

        move_down_btn = QPushButton("Move Down")
        move_down_btn.clicked.connect(self._move_step_down)
        move_layout.addWidget(move_down_btn)
        move_layout.addStretch()
        steps_layout.addLayout(move_layout)

        splitter.addWidget(steps_widget)

        # Step preview
        preview_widget = QWidget()
        preview_layout = QVBoxLayout(preview_widget)
        preview_layout.setContentsMargins(0, 0, 0, 0)

        preview_layout.addWidget(QLabel("Step Details:"))
        self._preview_text = QTextEdit()
        self._preview_text.setReadOnly(True)
        self._preview_text.setStyleSheet("background-color: #f8f8f8;")
        preview_layout.addWidget(self._preview_text)

        splitter.addWidget(preview_widget)

        layout.addWidget(splitter)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_data(self):
        """Load existing workflow data."""
        self._steps = self._workflow_data.get("steps", []).copy()
        self._update_steps_list()

    def _update_steps_list(self):
        """Update the steps list display."""
        self._steps_list.clear()
        for step in self._steps:
            step_id = step.get("id", "?")
            step_name = step.get("name", step_id)
            step_type = step.get("type", "?")
            deps = step.get("depends_on", [])

            if deps:
                dep_str = f" (after: {', '.join(deps)})"
            else:
                dep_str = ""

            item_text = f"{step_name} [{step_type}]{dep_str}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, step)
            self._steps_list.addItem(item)

    def _on_step_selected(self, row: int):
        """Show step details in preview."""
        if 0 <= row < len(self._steps):
            step = self._steps[row]
            preview = self._format_step_preview(step)
            self._preview_text.setPlainText(preview)
        else:
            self._preview_text.clear()

    def _format_step_preview(self, step: dict) -> str:
        """Format step for preview display."""
        lines = [
            f"ID: {step.get('id', 'N/A')}",
            f"Name: {step.get('name', 'N/A')}",
            f"Type: {step.get('type', 'N/A')}",
        ]

        deps = step.get("depends_on", [])
        if deps:
            lines.append(f"Depends on: {', '.join(deps)}")

        step_type = step.get("type")
        if step_type == "apdu":
            lines.append(f"\nAPDU: {step.get('apdu', 'N/A')}")
            if step.get("description"):
                lines.append(f"Description: {step['description']}")

        elif step_type == "dialog":
            fields = step.get("fields", [])
            if fields:
                lines.append(f"\nFields ({len(fields)}):")
                for f in fields:
                    lines.append(f"  - {f.get('label', f.get('id', '?'))} [{f.get('type', 'text')}]")

        elif step_type == "script":
            script = step.get("script", "")
            lines.append(f"\nScript ({len(script.splitlines())} lines):")
            lines.append(script[:200] + ("..." if len(script) > 200 else ""))

        elif step_type == "confirmation":
            lines.append(f"\nMessage: {step.get('message', 'N/A')}")

        return "\n".join(lines)

    def _get_existing_step_ids(self) -> list[str]:
        """Get list of existing step IDs."""
        return [s.get("id", "") for s in self._steps if s.get("id")]

    def _add_step(self):
        """Add a new step."""
        dialog = WorkflowStepDialog(
            existing_steps=self._get_existing_step_ids(),
            available_variables=self._available_variables,
            parent=self
        )
        if dialog.exec_() == QDialog.Accepted:
            step_data = dialog.get_step_data()
            if step_data.get("id"):
                self._steps.append(step_data)
                self._update_steps_list()

    def _edit_step(self, item: QListWidgetItem):
        """Edit a step by double-clicking."""
        index = self._steps_list.row(item)
        if 0 <= index < len(self._steps):
            self._edit_step_at(index)

    def _edit_selected_step(self):
        """Edit the selected step."""
        current = self._steps_list.currentRow()
        if current >= 0:
            self._edit_step_at(current)

    def _edit_step_at(self, index: int):
        """Edit step at index."""
        if 0 <= index < len(self._steps):
            # Exclude current step ID from existing steps for dependency selection
            other_step_ids = [s.get("id", "") for i, s in enumerate(self._steps) if i != index]
            dialog = WorkflowStepDialog(
                step_data=self._steps[index],
                existing_steps=other_step_ids,
                available_variables=self._available_variables,
                parent=self
            )
            if dialog.exec_() == QDialog.Accepted:
                self._steps[index] = dialog.get_step_data()
                self._update_steps_list()
                self._steps_list.setCurrentRow(index)
                self._on_step_selected(index)

    def _remove_step(self):
        """Remove selected step."""
        current = self._steps_list.currentRow()
        if 0 <= current < len(self._steps):
            removed_id = self._steps[current].get("id")
            self._steps.pop(current)

            # Remove references to this step from dependencies
            for step in self._steps:
                deps = step.get("depends_on", [])
                if removed_id in deps:
                    deps.remove(removed_id)

            self._update_steps_list()
            self._preview_text.clear()

    def _move_step_up(self):
        """Move selected step up."""
        current = self._steps_list.currentRow()
        if current > 0:
            self._steps[current], self._steps[current - 1] = \
                self._steps[current - 1], self._steps[current]
            self._update_steps_list()
            self._steps_list.setCurrentRow(current - 1)

    def _move_step_down(self):
        """Move selected step down."""
        current = self._steps_list.currentRow()
        if 0 <= current < len(self._steps) - 1:
            self._steps[current], self._steps[current + 1] = \
                self._steps[current + 1], self._steps[current]
            self._update_steps_list()
            self._steps_list.setCurrentRow(current + 1)

    def get_workflow_id(self) -> str:
        """Get the workflow ID."""
        return self._id_edit.text().strip()

    def get_workflow_data(self) -> dict:
        """Get the workflow definition data."""
        return {"steps": self._steps}


class WorkflowBuilderPage(QWizardPage):
    """Build workflows for the plugin."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Workflows")
        self.setSubTitle(
            "Define multi-step workflows for complex operations "
            "(e.g., key generation, certificate loading)."
        )

        self._workflows: dict[str, dict] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Help text
        help_label = QLabel(
            "Workflows are referenced by management actions and can include "
            "APDU commands, user dialogs, Python scripts, and confirmations."
        )
        help_label.setWordWrap(True)
        help_label.setStyleSheet("color: gray;")
        layout.addWidget(help_label)

        # Workflows list
        layout.addWidget(QLabel("Defined Workflows:"))

        self._workflows_list = QListWidget()
        self._workflows_list.itemDoubleClicked.connect(self._edit_workflow)
        layout.addWidget(self._workflows_list)

        # Buttons
        btn_layout = QHBoxLayout()

        add_btn = QPushButton("Add Workflow")
        add_btn.clicked.connect(self._add_workflow)
        btn_layout.addWidget(add_btn)

        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit_selected_workflow)
        btn_layout.addWidget(edit_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_workflow)
        btn_layout.addWidget(remove_btn)

        btn_layout.addStretch()

        layout.addLayout(btn_layout)

        # Skip checkbox
        self._skip_check = QCheckBox("Skip workflows (simple actions only)")
        self._skip_check.stateChanged.connect(self._on_skip_changed)
        layout.addWidget(self._skip_check)

    def initializePage(self):
        """Load existing workflows when editing."""
        wizard = self.wizard()
        if not wizard:
            return

        # Get workflows from loaded plugin data
        workflows = wizard.get_plugin_value("workflows", {})
        if workflows and not self._workflows:  # Only load if not already populated
            # Deep copy to avoid modifying original data
            import copy
            self._workflows = copy.deepcopy(workflows)
            self._update_list()

    def _on_skip_changed(self, state):
        """Handle skip checkbox change."""
        self._workflows_list.setEnabled(state != Qt.Checked)

    def _get_available_variables(self) -> dict[str, list[dict]]:
        """Get available variables from wizard data."""
        variables = {}
        wizard = self.wizard()
        if wizard:
            # Install UI fields
            install_fields = wizard.get_plugin_value("install_ui.form.fields", [])
            if install_fields:
                variables["install_ui"] = install_fields

            # Management action dialog fields (aggregate from all actions)
            actions = wizard.get_plugin_value("management_ui.actions", [])
            action_fields = []
            for action in actions or []:
                dialog_data = action.get("dialog", {})
                fields = dialog_data.get("fields", [])
                action_fields.extend(fields)
            if action_fields:
                variables["action_fields"] = action_fields

        return variables

    def _add_workflow(self):
        """Add a new workflow."""
        dialog = WorkflowDefinitionDialog(
            available_variables=self._get_available_variables(),
            parent=self
        )
        if dialog.exec_() == QDialog.Accepted:
            workflow_id = dialog.get_workflow_id()
            if workflow_id:
                self._workflows[workflow_id] = dialog.get_workflow_data()
                self._update_list()

    def _edit_workflow(self, item: QListWidgetItem):
        """Edit a workflow by double-clicking."""
        workflow_id = item.data(Qt.UserRole)
        if workflow_id in self._workflows:
            self._edit_workflow_by_id(workflow_id)

    def _edit_selected_workflow(self):
        """Edit the selected workflow."""
        current = self._workflows_list.currentItem()
        if current:
            workflow_id = current.data(Qt.UserRole)
            if workflow_id in self._workflows:
                self._edit_workflow_by_id(workflow_id)

    def _edit_workflow_by_id(self, workflow_id: str):
        """Edit workflow by ID."""
        dialog = WorkflowDefinitionDialog(
            workflow_id=workflow_id,
            workflow_data=self._workflows[workflow_id],
            available_variables=self._get_available_variables(),
            parent=self
        )
        if dialog.exec_() == QDialog.Accepted:
            new_id = dialog.get_workflow_id()
            new_data = dialog.get_workflow_data()

            # Handle ID change
            if new_id != workflow_id:
                del self._workflows[workflow_id]

            self._workflows[new_id] = new_data
            self._update_list()

    def _remove_workflow(self):
        """Remove selected workflow."""
        current = self._workflows_list.currentItem()
        if current:
            workflow_id = current.data(Qt.UserRole)
            if workflow_id in self._workflows:
                del self._workflows[workflow_id]
                self._update_list()

    def _update_list(self):
        """Update the workflows list display."""
        self._workflows_list.clear()

        for workflow_id, workflow_data in self._workflows.items():
            steps = workflow_data.get("steps", [])
            step_count = len(steps)

            item_text = f"{workflow_id} ({step_count} steps)"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, workflow_id)
            self._workflows_list.addItem(item)

    def validatePage(self) -> bool:
        """Validate and save data."""
        wizard = self.wizard()
        if not wizard:
            return True

        if self._skip_check.isChecked() or not self._workflows:
            wizard.set_plugin_data("workflows", None)
        else:
            wizard.set_plugin_data("workflows", self._workflows)

        return True
