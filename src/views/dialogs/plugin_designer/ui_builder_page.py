"""
UI Builder Page

Allows creating installation form fields through a visual interface.
Supports both flat field lists and tabbed dialogs.
"""

from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import (
    QWizardPage,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QCheckBox,
    QGroupBox,
    QFormLayout,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QDialog,
    QDialogButtonBox,
    QSpinBox,
    QTextEdit,
    QFrame,
    QWidget,
    QScrollArea,
    QTabWidget,
    QInputDialog,
    QSplitter,
    QMessageBox,
)


class FieldDefinitionDialog(QDialog):
    """Dialog for editing a field definition."""

    def __init__(self, field_data: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Field Definition")
        self.setMinimumWidth(400)

        self._field_data = field_data or {}
        self._setup_ui()
        self._load_data()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # Field ID
        self._id_edit = QLineEdit()
        self._id_edit.setPlaceholderText("e.g., user_name")
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
        self._label_edit.setPlaceholderText("Display label")
        form.addRow("Label:", self._label_edit)

        # Default value
        self._default_edit = QLineEdit()
        self._default_edit.setPlaceholderText("Optional default value")
        form.addRow("Default:", self._default_edit)

        # Required
        self._required_check = QCheckBox()
        form.addRow("Required:", self._required_check)

        # Placeholder
        self._placeholder_edit = QLineEdit()
        self._placeholder_edit.setPlaceholderText("Optional placeholder text")
        form.addRow("Placeholder:", self._placeholder_edit)

        # Description
        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText("Optional description/tooltip")
        form.addRow("Description:", self._desc_edit)

        # Options (for dropdown)
        self._options_label = QLabel("Options (comma-separated):")
        self._options_edit = QLineEdit()
        self._options_edit.setPlaceholderText("option1, option2, option3")
        form.addRow(self._options_label, self._options_edit)

        # Validation pattern
        self._pattern_edit = QLineEdit()
        self._pattern_edit.setPlaceholderText("Optional regex pattern")
        form.addRow("Validation Pattern:", self._pattern_edit)

        # Width (for multi-column layouts)
        width_layout = QHBoxLayout()
        self._width_combo = QComboBox()
        self._width_combo.addItems([
            "Full width (100%)",
            "Half width (50%)",
            "Third width (33%)",
            "Quarter width (25%)",
        ])
        width_layout.addWidget(self._width_combo)
        width_hint = QLabel("(allows multiple fields per row)")
        width_hint.setStyleSheet("color: #666; font-size: 10px;")
        width_layout.addWidget(width_hint)
        width_layout.addStretch()
        form.addRow("Width:", width_layout)

        layout.addLayout(form)

        # Show/hide options based on type
        self._type_combo.currentTextChanged.connect(self._on_type_changed)
        self._on_type_changed(self._type_combo.currentText())

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_type_changed(self, field_type: str):
        """Update UI based on field type."""
        is_dropdown = field_type == "dropdown"
        self._options_label.setVisible(is_dropdown)
        self._options_edit.setVisible(is_dropdown)

    def _load_data(self):
        """Load existing field data."""
        if not self._field_data:
            return

        self._id_edit.setText(self._field_data.get("id", ""))
        self._label_edit.setText(self._field_data.get("label", ""))
        self._default_edit.setText(str(self._field_data.get("default", "")))
        self._required_check.setChecked(self._field_data.get("required", False))
        self._placeholder_edit.setText(self._field_data.get("placeholder", ""))
        self._desc_edit.setText(self._field_data.get("description", ""))
        self._pattern_edit.setText(self._field_data.get("validation", {}).get("pattern", ""))

        # Set type
        field_type = self._field_data.get("type", "text")
        index = self._type_combo.findText(field_type)
        if index >= 0:
            self._type_combo.setCurrentIndex(index)

        # Set options
        options = self._field_data.get("options", [])
        if options:
            if isinstance(options[0], dict):
                self._options_edit.setText(", ".join(o.get("label", "") for o in options))
            else:
                self._options_edit.setText(", ".join(options))

        # Set width
        width = self._field_data.get("width", 1.0)
        if width <= 0.25:
            self._width_combo.setCurrentIndex(3)
        elif width <= 0.33:
            self._width_combo.setCurrentIndex(2)
        elif width <= 0.5:
            self._width_combo.setCurrentIndex(1)
        else:
            self._width_combo.setCurrentIndex(0)

    def get_field_data(self) -> dict:
        """Get the field definition data."""
        data = {
            "id": self._id_edit.text().strip(),
            "type": self._type_combo.currentText(),
            "label": self._label_edit.text().strip(),
        }

        # Optional fields
        default = self._default_edit.text().strip()
        if default:
            data["default"] = default

        if self._required_check.isChecked():
            data["required"] = True

        placeholder = self._placeholder_edit.text().strip()
        if placeholder:
            data["placeholder"] = placeholder

        desc = self._desc_edit.text().strip()
        if desc:
            data["description"] = desc

        pattern = self._pattern_edit.text().strip()
        if pattern:
            data["validation"] = {"pattern": pattern}

        # Options for dropdown
        if data["type"] == "dropdown":
            options_text = self._options_edit.text().strip()
            if options_text:
                options = [o.strip() for o in options_text.split(",") if o.strip()]
                data["options"] = [{"value": o, "label": o} for o in options]

        # Width
        width_index = self._width_combo.currentIndex()
        width_map = {0: 1.0, 1: 0.5, 2: 0.33, 3: 0.25}
        width = width_map.get(width_index, 1.0)
        if width < 1.0:
            data["width"] = width

        return data


class DraggableFieldRow(QFrame):
    """A draggable row in the preview representing a single field."""

    clicked = pyqtSignal(int)  # Emits field index (for selection)
    double_clicked = pyqtSignal(int)  # Emits field index (for editing)
    dropped = pyqtSignal(int, int)  # Emits (from_index, to_index)

    def __init__(self, index: int, label_text: str, widget: QWidget, width_ratio: float = 1.0, parent=None):
        super().__init__(parent)
        self._index = index
        self._drag_start_pos = None
        self._selected = False

        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        self._update_style()
        self.setCursor(QCursor(Qt.OpenHandCursor))
        self.setAcceptDrops(True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        # Drag handle
        handle = QLabel("\u2630")  # Hamburger menu icon
        handle.setStyleSheet("color: #888; font-size: 14px;")
        layout.addWidget(handle)

        # Label
        label = QLabel(label_text)
        label.setMinimumWidth(80)
        layout.addWidget(label)

        # Widget
        layout.addWidget(widget, 1)

        # Width indicator if not full width
        if width_ratio < 1.0:
            width_label = QLabel(f"[{int(width_ratio * 100)}%]")
            width_label.setStyleSheet("color: #888; font-size: 10px;")
            layout.addWidget(width_label)

    def _update_style(self):
        """Update the visual style based on selection state."""
        if self._selected:
            self.setStyleSheet("""
                DraggableFieldRow {
                    background-color: #e0f0ff;
                    border: 2px solid #0078d4;
                    border-radius: 4px;
                    padding: 4px;
                    margin: 2px;
                }
            """)
        else:
            self.setStyleSheet("""
                DraggableFieldRow {
                    background-color: white;
                    border: 1px solid #ccc;
                    border-radius: 4px;
                    padding: 4px;
                    margin: 2px;
                }
                DraggableFieldRow:hover {
                    border-color: #0078d4;
                    background-color: #f0f8ff;
                }
            """)

    def set_selected(self, selected: bool):
        """Set selection state."""
        self._selected = selected
        self._update_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
            self.clicked.emit(self._index)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit(self._index)
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_pos and (event.pos() - self._drag_start_pos).manhattanLength() > 10:
            from PyQt5.QtCore import QMimeData
            from PyQt5.QtGui import QDrag

            drag = QDrag(self)
            mime = QMimeData()
            mime.setText(str(self._index))
            drag.setMimeData(mime)
            self.setCursor(QCursor(Qt.ClosedHandCursor))
            drag.exec_(Qt.MoveAction)
            self.setCursor(QCursor(Qt.OpenHandCursor))
            self._drag_start_pos = None

    def dragEnterEvent(self, event):
        if event.mimeData().hasText():
            event.acceptProposedAction()
            self.setStyleSheet("""
                DraggableFieldRow {
                    background-color: #e0f0ff;
                    border: 2px dashed #0078d4;
                    border-radius: 4px;
                    padding: 4px;
                    margin: 2px;
                }
            """)

    def dragLeaveEvent(self, event):
        self.setStyleSheet("""
            DraggableFieldRow {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 4px;
                margin: 2px;
            }
            DraggableFieldRow:hover {
                border-color: #0078d4;
                background-color: #f0f8ff;
            }
        """)

    def dropEvent(self, event):
        from_index = int(event.mimeData().text())
        self.dropped.emit(from_index, self._index)
        self.setStyleSheet("""
            DraggableFieldRow {
                background-color: white;
                border: 1px solid #ccc;
                border-radius: 4px;
                padding: 4px;
                margin: 2px;
            }
            DraggableFieldRow:hover {
                border-color: #0078d4;
                background-color: #f0f8ff;
            }
        """)


class TabbedFormPreviewWindow(QDialog):
    """Floating window showing live preview of tabbed form."""

    field_selected = pyqtSignal(int, int)  # (tab_index, field_index)
    field_edit_requested = pyqtSignal(int, int)  # (tab_index, field_index)
    tab_changed = pyqtSignal(int)  # tab_index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Form Preview")
        self.setMinimumSize(500, 400)
        self.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        hint = QLabel("Preview of the installation dialog")
        hint.setStyleSheet("color: #666; font-size: 10px; padding: 4px;")
        layout.addWidget(hint)

        self._tab_widget = QTabWidget()
        self._tab_widget.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self._tab_widget)

        self._placeholder = QLabel("(No fields defined)")
        self._placeholder.setStyleSheet("color: gray; padding: 20px;")
        self._placeholder.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._placeholder)
        self._placeholder.hide()

    def _on_tab_changed(self, index: int):
        self.tab_changed.emit(index)

    def update_preview_tabs(self, tabs: list[dict]):
        """Update preview with tabbed data."""
        # Clear existing tabs
        while self._tab_widget.count() > 0:
            widget = self._tab_widget.widget(0)
            self._tab_widget.removeTab(0)
            if widget:
                widget.deleteLater()

        if not tabs:
            self._tab_widget.hide()
            self._placeholder.show()
            return

        self._placeholder.hide()
        self._tab_widget.show()

        for tab_idx, tab in enumerate(tabs):
            tab_name = tab.get("name", f"Tab {tab_idx + 1}")
            fields = tab.get("fields", [])

            # Create scroll area for this tab
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameStyle(QFrame.NoFrame)

            container = QWidget()
            container_layout = QVBoxLayout(container)
            container_layout.setSpacing(8)

            if not fields:
                empty_label = QLabel("(No fields in this tab)")
                empty_label.setStyleSheet("color: gray;")
                empty_label.setAlignment(Qt.AlignCenter)
                container_layout.addWidget(empty_label)
            else:
                for field_idx, field in enumerate(fields):
                    row = self._create_field_preview(tab_idx, field_idx, field)
                    container_layout.addWidget(row)

            container_layout.addStretch()
            scroll.setWidget(container)
            self._tab_widget.addTab(scroll, tab_name)

    def update_preview_flat(self, fields: list[dict]):
        """Update preview with flat field list (single tab)."""
        self.update_preview_tabs([{"name": "Settings", "fields": fields}])

    def _create_field_preview(self, tab_idx: int, field_idx: int, field: dict) -> QFrame:
        """Create a preview row for a field."""
        frame = QFrame()
        frame.setFrameStyle(QFrame.StyledPanel)
        frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 4px;
                padding: 4px;
            }
        """)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 4)

        # Label
        label_text = field.get("label", field.get("id", "Field"))
        if field.get("required"):
            label_text += " *"
        label = QLabel(label_text)
        label.setMinimumWidth(100)
        layout.addWidget(label)

        # Widget preview
        widget = self._create_widget_preview(field)
        layout.addWidget(widget, 1)

        return frame

    def _create_widget_preview(self, field: dict) -> QWidget:
        """Create a preview widget for a field type."""
        field_type = field.get("type", "text")

        if field_type in ("text", "password"):
            widget = QLineEdit()
            widget.setPlaceholderText(field.get("placeholder", ""))
            if field_type == "password":
                widget.setEchoMode(QLineEdit.Password)
            if field.get("default"):
                widget.setText(str(field.get("default")))
        elif field_type == "number":
            widget = QSpinBox()
        elif field_type == "checkbox":
            widget = QCheckBox()
        elif field_type == "dropdown":
            widget = QComboBox()
            for opt in field.get("options", []):
                if isinstance(opt, dict):
                    widget.addItem(opt.get("label", ""))
                else:
                    widget.addItem(str(opt))
        elif field_type == "hex_editor":
            widget = QLineEdit()
            widget.setPlaceholderText(field.get("placeholder", "Hex data..."))
        elif field_type == "file":
            widget = QWidget()
            file_layout = QHBoxLayout(widget)
            file_layout.setContentsMargins(0, 0, 0, 0)
            file_edit = QLineEdit()
            file_edit.setPlaceholderText("Select file...")
            browse_btn = QPushButton("Browse...")
            browse_btn.setMaximumWidth(70)
            file_layout.addWidget(file_edit, 1)
            file_layout.addWidget(browse_btn)
        else:
            widget = QLineEdit()

        return widget

    def set_current_tab(self, index: int):
        """Set the currently visible tab."""
        if 0 <= index < self._tab_widget.count():
            self._tab_widget.setCurrentIndex(index)


class UIBuilderPage(QWizardPage):
    """Build the installation UI fields with optional tab support."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Installation UI")
        self.setSubTitle("Define the form fields for installation parameters.")

        # Data storage
        self._use_tabs = False
        self._tabs: list[dict] = []  # List of {"name": str, "fields": list}
        self._fields: list[dict] = []  # Flat field list (when not using tabs)
        self._current_tab_index = 0

        self._preview_window: Optional[TabbedFormPreviewWindow] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Tab mode toggle
        self._use_tabs_check = QCheckBox("Use tabbed dialog")
        self._use_tabs_check.stateChanged.connect(self._on_tabs_mode_changed)
        layout.addWidget(self._use_tabs_check)

        # Main content area - will switch between flat and tabbed mode
        self._content_stack = QWidget()
        content_layout = QVBoxLayout(self._content_stack)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # === Tabbed mode UI ===
        self._tabbed_widget = QWidget()
        tabbed_layout = QHBoxLayout(self._tabbed_widget)
        tabbed_layout.setContentsMargins(0, 0, 0, 0)

        # Left side: Tab list
        tabs_panel = QWidget()
        tabs_panel_layout = QVBoxLayout(tabs_panel)
        tabs_panel_layout.setContentsMargins(0, 0, 0, 0)

        tabs_panel_layout.addWidget(QLabel("Tabs:"))
        self._tabs_list = QListWidget()
        self._tabs_list.setMaximumWidth(150)
        self._tabs_list.currentRowChanged.connect(self._on_tab_selected)
        tabs_panel_layout.addWidget(self._tabs_list)

        tab_btn_layout = QHBoxLayout()
        add_tab_btn = QPushButton("+")
        add_tab_btn.setMaximumWidth(30)
        add_tab_btn.setToolTip("Add Tab")
        add_tab_btn.clicked.connect(self._add_tab)
        tab_btn_layout.addWidget(add_tab_btn)

        rename_tab_btn = QPushButton("Rename")
        rename_tab_btn.clicked.connect(self._rename_tab)
        tab_btn_layout.addWidget(rename_tab_btn)

        remove_tab_btn = QPushButton("-")
        remove_tab_btn.setMaximumWidth(30)
        remove_tab_btn.setToolTip("Remove Tab")
        remove_tab_btn.clicked.connect(self._remove_tab)
        tab_btn_layout.addWidget(remove_tab_btn)

        tabs_panel_layout.addLayout(tab_btn_layout)
        tabbed_layout.addWidget(tabs_panel)

        # Right side: Fields for selected tab
        self._tab_fields_panel = QWidget()
        tab_fields_layout = QVBoxLayout(self._tab_fields_panel)
        tab_fields_layout.setContentsMargins(0, 0, 0, 0)

        self._tab_fields_label = QLabel("Fields in selected tab:")
        tab_fields_layout.addWidget(self._tab_fields_label)

        self._tab_fields_list = QListWidget()
        self._tab_fields_list.itemDoubleClicked.connect(self._edit_tab_field)
        tab_fields_layout.addWidget(self._tab_fields_list)

        tab_field_btn_layout = QHBoxLayout()
        add_field_btn = QPushButton("Add Field")
        add_field_btn.clicked.connect(self._add_tab_field)
        tab_field_btn_layout.addWidget(add_field_btn)

        edit_field_btn = QPushButton("Edit")
        edit_field_btn.clicked.connect(self._edit_selected_tab_field)
        tab_field_btn_layout.addWidget(edit_field_btn)

        remove_field_btn = QPushButton("Remove")
        remove_field_btn.clicked.connect(self._remove_tab_field)
        tab_field_btn_layout.addWidget(remove_field_btn)

        tab_field_btn_layout.addStretch()

        move_up_btn = QPushButton("Up")
        move_up_btn.clicked.connect(self._move_tab_field_up)
        tab_field_btn_layout.addWidget(move_up_btn)

        move_down_btn = QPushButton("Down")
        move_down_btn.clicked.connect(self._move_tab_field_down)
        tab_field_btn_layout.addWidget(move_down_btn)

        tab_fields_layout.addLayout(tab_field_btn_layout)
        tabbed_layout.addWidget(self._tab_fields_panel, 1)

        content_layout.addWidget(self._tabbed_widget)

        # === Flat mode UI ===
        self._flat_widget = QWidget()
        flat_layout = QVBoxLayout(self._flat_widget)
        flat_layout.setContentsMargins(0, 0, 0, 0)

        flat_layout.addWidget(QLabel("Form Fields:"))

        self._fields_list = QListWidget()
        self._fields_list.itemDoubleClicked.connect(self._edit_field)
        flat_layout.addWidget(self._fields_list)

        btn_layout = QHBoxLayout()

        add_btn = QPushButton("Add Field")
        add_btn.clicked.connect(self._add_field)
        btn_layout.addWidget(add_btn)

        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(self._edit_selected_field)
        btn_layout.addWidget(edit_btn)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._remove_field)
        btn_layout.addWidget(remove_btn)

        btn_layout.addStretch()

        move_up_btn = QPushButton("Move Up")
        move_up_btn.clicked.connect(self._move_field_up)
        btn_layout.addWidget(move_up_btn)

        move_down_btn = QPushButton("Move Down")
        move_down_btn.clicked.connect(self._move_field_down)
        btn_layout.addWidget(move_down_btn)

        flat_layout.addLayout(btn_layout)

        content_layout.addWidget(self._flat_widget)

        layout.addWidget(self._content_stack)
        layout.addStretch()

        # Skip checkbox
        self._skip_check = QCheckBox("Skip installation UI (no user input required)")
        self._skip_check.stateChanged.connect(self._on_skip_changed)
        layout.addWidget(self._skip_check)

        # Initially show flat mode
        self._update_mode_visibility()

    def _on_tabs_mode_changed(self, state):
        """Handle switching between flat and tabbed mode."""
        new_use_tabs = state == Qt.Checked

        if new_use_tabs and not self._use_tabs:
            # Switching to tabbed mode - migrate flat fields to first tab
            if self._fields:
                reply = QMessageBox.question(
                    self,
                    "Switch to Tabbed Mode",
                    f"Your {len(self._fields)} field(s) will be moved to a 'General' tab.\n\n"
                    "Continue?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if reply != QMessageBox.Yes:
                    # Revert checkbox without triggering signal
                    self._use_tabs_check.blockSignals(True)
                    self._use_tabs_check.setChecked(False)
                    self._use_tabs_check.blockSignals(False)
                    return
                self._tabs = [{"name": "General", "fields": self._fields.copy()}]
                self._fields = []
            elif not self._tabs:
                self._tabs = [{"name": "General", "fields": []}]

        elif not new_use_tabs and self._use_tabs:
            # Switching to flat mode - flatten all tab fields
            total_fields = sum(len(tab.get("fields", [])) for tab in self._tabs)
            tab_names = [tab.get("name", "Tab") for tab in self._tabs if tab.get("fields")]

            if len(self._tabs) > 1 and total_fields > 0:
                reply = QMessageBox.warning(
                    self,
                    "Switch to Flat Mode",
                    f"You have {len(self._tabs)} tabs with {total_fields} total field(s).\n\n"
                    f"All fields from tabs ({', '.join(tab_names)}) will be merged into a single list. "
                    "Tab organization will be lost.\n\n"
                    "Continue?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    # Revert checkbox without triggering signal
                    self._use_tabs_check.blockSignals(True)
                    self._use_tabs_check.setChecked(True)
                    self._use_tabs_check.blockSignals(False)
                    return

            all_fields = []
            for tab in self._tabs:
                all_fields.extend(tab.get("fields", []))
            self._fields = all_fields
            self._tabs = []

        self._use_tabs = new_use_tabs
        self._update_mode_visibility()
        self._update_all_lists()
        self._update_preview()

    def _update_mode_visibility(self):
        """Show/hide UI based on current mode."""
        self._tabbed_widget.setVisible(self._use_tabs)
        self._flat_widget.setVisible(not self._use_tabs)

    def _update_all_lists(self):
        """Update all list widgets."""
        if self._use_tabs:
            self._update_tabs_list()
        else:
            self._update_fields_list()

    # === Tab management ===

    def _update_tabs_list(self):
        """Update the tabs list widget."""
        self._tabs_list.clear()
        for tab in self._tabs:
            name = tab.get("name", "Untitled")
            field_count = len(tab.get("fields", []))
            self._tabs_list.addItem(f"{name} ({field_count})")

        # Select first tab if any
        if self._tabs and self._tabs_list.count() > 0:
            self._tabs_list.setCurrentRow(min(self._current_tab_index, len(self._tabs) - 1))
        else:
            self._update_tab_fields_list()

    def _on_tab_selected(self, index: int):
        """Handle tab selection."""
        self._current_tab_index = index
        self._update_tab_fields_list()
        if self._preview_window:
            self._preview_window.set_current_tab(index)

    def _update_tab_fields_list(self):
        """Update the fields list for the current tab."""
        self._tab_fields_list.clear()

        if not self._tabs or self._current_tab_index >= len(self._tabs):
            self._tab_fields_label.setText("Fields: (no tab selected)")
            return

        tab = self._tabs[self._current_tab_index]
        tab_name = tab.get("name", "Tab")
        self._tab_fields_label.setText(f"Fields in '{tab_name}':")

        for field in tab.get("fields", []):
            field_id = field.get("id", "?")
            field_type = field.get("type", "text")
            label = field.get("label", field_id)
            required = "*" if field.get("required") else ""
            self._tab_fields_list.addItem(f"{label}{required} [{field_type}]")

    def _add_tab(self):
        """Add a new tab."""
        name, ok = QInputDialog.getText(self, "Add Tab", "Tab name:")
        if ok and name.strip():
            self._tabs.append({"name": name.strip(), "fields": []})
            self._update_tabs_list()
            self._tabs_list.setCurrentRow(len(self._tabs) - 1)
            self._update_preview()

    def _rename_tab(self):
        """Rename the selected tab."""
        if not self._tabs or self._current_tab_index >= len(self._tabs):
            return

        current_name = self._tabs[self._current_tab_index].get("name", "")
        name, ok = QInputDialog.getText(self, "Rename Tab", "New name:", text=current_name)
        if ok and name.strip():
            self._tabs[self._current_tab_index]["name"] = name.strip()
            self._update_tabs_list()
            self._update_preview()

    def _remove_tab(self):
        """Remove the selected tab."""
        if not self._tabs or self._current_tab_index >= len(self._tabs):
            return

        self._tabs.pop(self._current_tab_index)
        if self._current_tab_index >= len(self._tabs):
            self._current_tab_index = max(0, len(self._tabs) - 1)
        self._update_tabs_list()
        self._update_preview()

    # === Tab field management ===

    def _get_current_tab_fields(self) -> list:
        """Get the fields list for the current tab."""
        if self._tabs and 0 <= self._current_tab_index < len(self._tabs):
            return self._tabs[self._current_tab_index].get("fields", [])
        return []

    def _add_tab_field(self):
        """Add a field to the current tab."""
        if not self._tabs:
            return

        dialog = FieldDefinitionDialog(parent=self)
        if dialog.exec_() == QDialog.Accepted:
            field_data = dialog.get_field_data()
            if field_data.get("id"):
                if "fields" not in self._tabs[self._current_tab_index]:
                    self._tabs[self._current_tab_index]["fields"] = []
                self._tabs[self._current_tab_index]["fields"].append(field_data)
                self._update_tabs_list()
                self._update_tab_fields_list()
                self._update_preview()

    def _edit_tab_field(self, item: QListWidgetItem):
        """Edit a tab field by double-clicking."""
        index = self._tab_fields_list.row(item)
        fields = self._get_current_tab_fields()
        if 0 <= index < len(fields):
            self._edit_tab_field_at(index)

    def _edit_selected_tab_field(self):
        """Edit the selected tab field."""
        current = self._tab_fields_list.currentRow()
        if current >= 0:
            self._edit_tab_field_at(current)

    def _edit_tab_field_at(self, index: int):
        """Edit a specific tab field."""
        fields = self._get_current_tab_fields()
        if 0 <= index < len(fields):
            dialog = FieldDefinitionDialog(fields[index], parent=self)
            if dialog.exec_() == QDialog.Accepted:
                self._tabs[self._current_tab_index]["fields"][index] = dialog.get_field_data()
                self._update_tab_fields_list()
                self._update_preview()

    def _remove_tab_field(self):
        """Remove the selected tab field."""
        current = self._tab_fields_list.currentRow()
        fields = self._get_current_tab_fields()
        if 0 <= current < len(fields):
            self._tabs[self._current_tab_index]["fields"].pop(current)
            self._update_tabs_list()
            self._update_tab_fields_list()
            self._update_preview()

    def _move_tab_field_up(self):
        """Move selected tab field up."""
        current = self._tab_fields_list.currentRow()
        fields = self._get_current_tab_fields()
        if current > 0 and current < len(fields):
            fields[current], fields[current - 1] = fields[current - 1], fields[current]
            self._update_tab_fields_list()
            self._tab_fields_list.setCurrentRow(current - 1)
            self._update_preview()

    def _move_tab_field_down(self):
        """Move selected tab field down."""
        current = self._tab_fields_list.currentRow()
        fields = self._get_current_tab_fields()
        if 0 <= current < len(fields) - 1:
            fields[current], fields[current + 1] = fields[current + 1], fields[current]
            self._update_tab_fields_list()
            self._tab_fields_list.setCurrentRow(current + 1)
            self._update_preview()

    # === Flat field management ===

    def _update_fields_list(self):
        """Update the flat fields list display."""
        self._fields_list.clear()

        for field in self._fields:
            field_id = field.get("id", "?")
            field_type = field.get("type", "text")
            label = field.get("label", field_id)
            required = "*" if field.get("required") else ""
            width = field.get("width", 1.0)
            width_str = "" if width >= 1.0 else f" ({int(width * 100)}%)"

            item_text = f"{label}{required} [{field_type}]{width_str}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, field)
            self._fields_list.addItem(item)

    def _add_field(self):
        """Add a new field (flat mode)."""
        dialog = FieldDefinitionDialog(parent=self)
        if dialog.exec_() == QDialog.Accepted:
            field_data = dialog.get_field_data()
            if field_data.get("id"):
                self._fields.append(field_data)
                self._update_fields_list()
                self._update_preview()

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
            dialog = FieldDefinitionDialog(self._fields[index], parent=self)
            if dialog.exec_() == QDialog.Accepted:
                self._fields[index] = dialog.get_field_data()
                self._update_fields_list()
                self._update_preview()

    def _remove_field(self):
        """Remove selected field."""
        current = self._fields_list.currentRow()
        if 0 <= current < len(self._fields):
            self._fields.pop(current)
            self._update_fields_list()
            self._update_preview()

    def _move_field_up(self):
        """Move selected field up."""
        current = self._fields_list.currentRow()
        if current > 0:
            self._fields[current], self._fields[current - 1] = \
                self._fields[current - 1], self._fields[current]
            self._update_fields_list()
            self._fields_list.setCurrentRow(current - 1)
            self._update_preview()

    def _move_field_down(self):
        """Move selected field down."""
        current = self._fields_list.currentRow()
        if 0 <= current < len(self._fields) - 1:
            self._fields[current], self._fields[current + 1] = \
                self._fields[current + 1], self._fields[current]
            self._update_fields_list()
            self._fields_list.setCurrentRow(current + 1)
            self._update_preview()

    # === Preview ===

    def _update_preview(self):
        """Update the preview window."""
        if not self._preview_window:
            return

        if self._use_tabs:
            self._preview_window.update_preview_tabs(self._tabs)
        else:
            self._preview_window.update_preview_flat(self._fields)

    def _ensure_preview_window(self):
        """Create and show the preview window."""
        if not self._preview_window:
            self._preview_window = TabbedFormPreviewWindow(self.wizard())
            self._preview_window.tab_changed.connect(self._on_preview_tab_changed)

        wizard = self.wizard()
        if wizard:
            wizard_geo = wizard.geometry()
            self._preview_window.move(wizard_geo.right() + 10, wizard_geo.top())

        self._preview_window.show()
        self._preview_window.raise_()

    def _on_preview_tab_changed(self, index: int):
        """Sync tab selection from preview."""
        if self._use_tabs and 0 <= index < len(self._tabs):
            self._tabs_list.setCurrentRow(index)

    def _on_skip_changed(self, state):
        """Handle skip checkbox change."""
        enabled = state != Qt.Checked
        self._content_stack.setEnabled(enabled)
        self._use_tabs_check.setEnabled(enabled)

    # === Page lifecycle ===

    def initializePage(self):
        """Load existing fields when editing."""
        wizard = self.wizard()
        if wizard and not self._fields and not self._tabs:
            import copy

            # Try tabbed dialog structure first
            tabs = wizard.get_plugin_value("install_ui.dialog.tabs", [])
            if tabs:
                self._tabs = copy.deepcopy(tabs)
                self._use_tabs = True
                self._use_tabs_check.setChecked(True)
            else:
                # Try flat form structure
                form_fields = wizard.get_plugin_value("install_ui.form.fields", [])
                if form_fields:
                    self._fields = copy.deepcopy(form_fields)
                    self._use_tabs = False
                    self._use_tabs_check.setChecked(False)

            self._update_mode_visibility()
            self._update_all_lists()

        # Show preview if we have content
        if self._fields or self._tabs:
            self._ensure_preview_window()
            self._update_preview()

    def cleanupPage(self):
        """Close preview window when leaving page."""
        if self._preview_window:
            self._preview_window.close()
            self._preview_window = None

    def validatePage(self) -> bool:
        """Validate and save data."""
        if self._preview_window:
            self._preview_window.close()
            self._preview_window = None

        wizard = self.wizard()
        if not wizard:
            return True

        if self._skip_check.isChecked():
            wizard.set_plugin_data("install_ui", None)
        elif self._use_tabs:
            # Save as tabbed dialog
            if self._tabs:
                wizard.set_plugin_data("install_ui.dialog.tabs", self._tabs)
            else:
                wizard.set_plugin_data("install_ui", None)
        else:
            # Save as flat form
            if self._fields:
                wizard.set_plugin_data("install_ui.form.fields", self._fields)
            else:
                wizard.set_plugin_data("install_ui", None)

        return True
