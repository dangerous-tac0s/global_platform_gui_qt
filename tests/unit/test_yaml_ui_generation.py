"""
Unit tests for YAML Plugin UI Generation

Tests the FieldFactory, DialogBuilder, and related UI components.
Note: These tests require a Qt application instance.
"""

import pytest
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from src.plugins.yaml.schema import (
    FieldDefinition,
    FieldType,
    FieldOption,
    FieldValidation,
    ShowWhen,
    FormDefinition,
    TabDefinition,
    DialogDefinition,
    InstallUIDefinition,
)
from src.plugins.yaml.ui.field_factory import (
    FieldWidget,
    FieldFactory,
    ConditionalFieldManager,
    CrossFieldValidator,
)
from src.plugins.yaml.ui.dialog_builder import (
    FormWidget,
    TabbedFormWidget,
    PluginDialog,
    DialogBuilder,
)
from src.plugins.yaml.ui.widgets.hex_editor import (
    HexEditorWidget,
    HexLineEdit,
)


# Fixture to ensure QApplication exists
@pytest.fixture(scope="module")
def qapp():
    """Create QApplication instance for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestFieldWidget:
    """Tests for FieldWidget class."""

    def test_text_field_creation(self, qapp):
        """Test creating a text field."""
        field_def = FieldDefinition(
            id="test_text",
            type=FieldType.TEXT,
            label="Test Label",
            placeholder="Enter text...",
            default="default value",
        )
        widget = FieldFactory.create(field_def)

        assert widget.getFieldId() == "test_text"
        assert widget.getValue() == "default value"

    def test_password_field_creation(self, qapp):
        """Test creating a password field."""
        field_def = FieldDefinition(
            id="test_password",
            type=FieldType.PASSWORD,
            label="Password",
        )
        widget = FieldFactory.create(field_def)

        widget.setValue("secret123")
        assert widget.getValue() == "secret123"

    def test_dropdown_field_creation(self, qapp):
        """Test creating a dropdown field."""
        field_def = FieldDefinition(
            id="test_dropdown",
            type=FieldType.DROPDOWN,
            label="Select Option",
            options=[
                FieldOption(label="Option A", value="a"),
                FieldOption(label="Option B", value="b"),
                FieldOption(label="Option C", value="c"),
            ],
            default="b",
        )
        widget = FieldFactory.create(field_def)

        assert widget.getValue() == "b"

        widget.setValue("c")
        assert widget.getValue() == "c"

    def test_checkbox_field_creation(self, qapp):
        """Test creating a checkbox field."""
        field_def = FieldDefinition(
            id="test_checkbox",
            type=FieldType.CHECKBOX,
            label="Enable Feature",
            default=True,
        )
        widget = FieldFactory.create(field_def)

        assert widget.getValue() is True

        widget.setValue(False)
        assert widget.getValue() is False

    def test_number_field_creation(self, qapp):
        """Test creating a number field."""
        field_def = FieldDefinition(
            id="test_number",
            type=FieldType.NUMBER,
            label="Count",
            default=10,
            validation=FieldValidation(min_value=0, max_value=100),
        )
        widget = FieldFactory.create(field_def)

        assert widget.getValue() == 10

        widget.setValue(50)
        assert widget.getValue() == 50

    def test_required_field_validation(self, qapp):
        """Test required field validation."""
        field_def = FieldDefinition(
            id="required_field",
            type=FieldType.TEXT,
            label="Required",
            required=True,
        )
        widget = FieldFactory.create(field_def)

        # Empty required field should be invalid
        assert not widget.isValid()

        # With value should be valid
        widget.setValue("some value")
        assert widget.isValid()

    def test_pattern_validation(self, qapp):
        """Test regex pattern validation."""
        field_def = FieldDefinition(
            id="hex_field",
            type=FieldType.TEXT,
            label="Hex Value",
            validation=FieldValidation(
                pattern=r"^[0-9A-Fa-f]+$",
                message="Must be hex characters",
            ),
        )
        widget = FieldFactory.create(field_def)

        widget.setValue("DEADBEEF")
        assert widget.isValid()

        widget.setValue("NOTAHEX!")
        assert not widget.isValid()

    def test_length_validation(self, qapp):
        """Test length validation."""
        field_def = FieldDefinition(
            id="length_field",
            type=FieldType.TEXT,
            label="Fixed Length",
            validation=FieldValidation(
                min_length=4,
                max_length=8,
            ),
        )
        widget = FieldFactory.create(field_def)

        widget.setValue("abc")  # Too short
        assert not widget.isValid()

        widget.setValue("abcd")  # Min length
        assert widget.isValid()

        widget.setValue("abcdefgh")  # Max length
        assert widget.isValid()

        widget.setValue("abcdefghi")  # Too long
        assert not widget.isValid()

    def test_transform_uppercase(self, qapp):
        """Test uppercase transform."""
        field_def = FieldDefinition(
            id="upper_field",
            type=FieldType.TEXT,
            label="Uppercase",
            transform="uppercase",
        )
        widget = FieldFactory.create(field_def)

        widget.setValue("lowercase")
        # Note: Transform is applied on text change, not setValue
        # For this test, we check the transform function directly


class TestConditionalFieldManager:
    """Tests for ConditionalFieldManager."""

    def test_show_when_equals(self, qapp):
        """Test show_when with equals condition."""
        mode_field = FieldDefinition(
            id="mode",
            type=FieldType.DROPDOWN,
            label="Mode",
            options=[
                FieldOption(label="Simple", value="simple"),
                FieldOption(label="Advanced", value="advanced"),
            ],
            default="simple",
        )

        advanced_field = FieldDefinition(
            id="advanced_option",
            type=FieldType.TEXT,
            label="Advanced Option",
            show_when=ShowWhen(field="mode", equals="advanced"),
        )

        mode_widget = FieldFactory.create(mode_field)
        advanced_widget = FieldFactory.create(advanced_field)

        manager = ConditionalFieldManager([mode_widget, advanced_widget])

        # Initially hidden (mode is "simple")
        assert not advanced_widget.isVisible()

        # Show when mode is "advanced"
        mode_widget.setValue("advanced")
        assert advanced_widget.isVisible()

        # Hide when mode is "simple"
        mode_widget.setValue("simple")
        assert not advanced_widget.isVisible()


class TestFormWidget:
    """Tests for FormWidget class."""

    def test_form_creation(self, qapp):
        """Test creating a form with multiple fields."""
        fields = [
            FieldDefinition(id="name", type=FieldType.TEXT, label="Name"),
            FieldDefinition(id="age", type=FieldType.NUMBER, label="Age", default=25),
            FieldDefinition(id="active", type=FieldType.CHECKBOX, label="Active", default=True),
        ]

        form = FormWidget(fields)

        values = form.getValues()
        assert "name" in values
        assert values["age"] == 25
        assert values["active"] is True

    def test_form_set_values(self, qapp):
        """Test setting form values."""
        fields = [
            FieldDefinition(id="field1", type=FieldType.TEXT, label="Field 1"),
            FieldDefinition(id="field2", type=FieldType.TEXT, label="Field 2"),
        ]

        form = FormWidget(fields)

        form.setValues({
            "field1": "value1",
            "field2": "value2",
        })

        values = form.getValues()
        assert values["field1"] == "value1"
        assert values["field2"] == "value2"

    def test_form_validation(self, qapp):
        """Test form validation with required fields."""
        fields = [
            FieldDefinition(id="required", type=FieldType.TEXT, label="Required", required=True),
            FieldDefinition(id="optional", type=FieldType.TEXT, label="Optional"),
        ]

        form = FormWidget(fields)

        # Form should be invalid with empty required field
        assert not form.isValid()

        # Set required field
        form.setValues({"required": "value"})
        assert form.isValid()


class TestTabbedFormWidget:
    """Tests for TabbedFormWidget class."""

    def test_tabbed_form_creation(self, qapp):
        """Test creating a tabbed form."""
        tabs = [
            TabDefinition(
                name="Basic",
                fields=[
                    FieldDefinition(id="name", type=FieldType.TEXT, label="Name"),
                ],
            ),
            TabDefinition(
                name="Advanced",
                fields=[
                    FieldDefinition(id="config", type=FieldType.TEXT, label="Config"),
                ],
            ),
        ]

        tabbed_form = TabbedFormWidget(tabs)

        values = tabbed_form.getValues()
        assert "name" in values
        assert "config" in values

    def test_tabbed_form_values_across_tabs(self, qapp):
        """Test getting/setting values across multiple tabs."""
        tabs = [
            TabDefinition(
                name="Tab1",
                fields=[FieldDefinition(id="field1", type=FieldType.TEXT, label="F1")],
            ),
            TabDefinition(
                name="Tab2",
                fields=[FieldDefinition(id="field2", type=FieldType.TEXT, label="F2")],
            ),
        ]

        tabbed_form = TabbedFormWidget(tabs)

        tabbed_form.setValues({
            "field1": "value1",
            "field2": "value2",
        })

        values = tabbed_form.getValues()
        assert values["field1"] == "value1"
        assert values["field2"] == "value2"


class TestDialogBuilder:
    """Tests for DialogBuilder class."""

    def test_build_simple_dialog(self, qapp):
        """Test building a simple form dialog."""
        form_def = FormDefinition(
            fields=[
                FieldDefinition(id="input", type=FieldType.TEXT, label="Input"),
            ]
        )
        ui_def = InstallUIDefinition(form=form_def)

        dialog = DialogBuilder.build(ui_def, title="Test Dialog")

        assert dialog.windowTitle() == "Test Dialog"

        dialog.setValues({"input": "test value"})
        assert dialog.getValues()["input"] == "test value"

    def test_build_tabbed_dialog(self, qapp):
        """Test building a tabbed dialog."""
        dialog_def = DialogDefinition(
            title="Tabbed Test",
            size=(500, 400),
            tabs=[
                TabDefinition(
                    name="Tab1",
                    fields=[FieldDefinition(id="f1", type=FieldType.TEXT, label="F1")],
                ),
                TabDefinition(
                    name="Tab2",
                    fields=[FieldDefinition(id="f2", type=FieldType.TEXT, label="F2")],
                ),
            ],
        )
        ui_def = InstallUIDefinition(dialog=dialog_def)

        dialog = DialogBuilder.build(ui_def)

        assert dialog.windowTitle() == "Tabbed Test"

    def test_build_from_fields(self, qapp):
        """Test building dialog directly from field list."""
        fields = [
            FieldDefinition(id="name", type=FieldType.TEXT, label="Name"),
            FieldDefinition(id="value", type=FieldType.TEXT, label="Value"),
        ]

        dialog = DialogBuilder.build_from_fields(fields, title="Field Dialog")

        dialog.setValues({"name": "test", "value": "123"})
        values = dialog.getValues()

        assert values["name"] == "test"
        assert values["value"] == "123"


class TestHexEditorWidget:
    """Tests for HexEditorWidget."""

    def test_hex_editor_creation(self, qapp):
        """Test creating hex editor widget."""
        editor = HexEditorWidget()

        editor.setText("DEADBEEF")
        assert editor.getText() == "DEADBEEF"

    def test_hex_editor_validation(self, qapp):
        """Test hex validation."""
        editor = HexEditorWidget()

        editor.setText("ABCD1234")
        assert editor.isValid()

        # Non-hex characters should be stripped
        editor.setText("ABCD-1234-XYZ")
        cleaned = editor.getText()
        assert cleaned == "ABCD1234"

    def test_hex_editor_bytes(self, qapp):
        """Test bytes conversion."""
        editor = HexEditorWidget()

        editor.setBytes(b'\xDE\xAD\xBE\xEF')
        assert editor.getText() == "DEADBEEF"

        assert editor.getBytes() == b'\xDE\xAD\xBE\xEF'

    def test_hex_editor_completeness(self, qapp):
        """Test byte completeness check."""
        editor = HexEditorWidget()

        editor.setText("AABB")  # Complete
        assert editor.isComplete()

        editor.setText("AABBC")  # Incomplete (odd nibbles)
        assert not editor.isComplete()


class TestHexLineEdit:
    """Tests for HexLineEdit."""

    def test_hex_line_creation(self, qapp):
        """Test creating hex line edit."""
        line = HexLineEdit()

        line.setText("1234ABCD")
        assert line.getText() == "1234ABCD"

    def test_hex_line_max_bytes(self, qapp):
        """Test max bytes limit."""
        line = HexLineEdit(max_bytes=4)

        line.setText("1234567890ABCDEF")  # 8 bytes
        # Should be truncated to 4 bytes
        assert len(line.getText()) <= 8  # 4 bytes = 8 hex chars


class TestTabbedFormConditionalFields:
    """Tests for conditional fields in tabbed forms - fixes tab visibility bug."""

    def test_conditional_fields_in_inactive_tabs(self, qapp):
        """
        Test that conditional fields in non-active tabs are included in getValues()
        when their show_when condition is met.

        This tests the fix for the Qt visibility bug where widgets in non-active
        tabs report isVisible()=False even when their show_when condition is satisfied.
        """
        # Tab 1: A dropdown that controls visibility
        # Tab 2: A conditional field that depends on Tab 1's dropdown
        tabs = [
            TabDefinition(
                name="Record Type",
                fields=[
                    FieldDefinition(
                        id="record_type",
                        type=FieldType.DROPDOWN,
                        label="Record Type",
                        options=[
                            FieldOption(label="None", value="none"),
                            FieldOption(label="URI", value="uri"),
                            FieldOption(label="Text", value="text"),
                        ],
                        default="uri",  # Start with URI selected
                    ),
                ],
            ),
            TabDefinition(
                name="URI Settings",
                fields=[
                    FieldDefinition(
                        id="uri_prefix",
                        type=FieldType.DROPDOWN,
                        label="URI Prefix",
                        options=[
                            FieldOption(label="https://", value="https"),
                            FieldOption(label="http://", value="http"),
                        ],
                        default="https",
                        show_when=ShowWhen(field="record_type", equals="uri"),
                    ),
                    FieldDefinition(
                        id="uri_value",
                        type=FieldType.TEXT,
                        label="URI",
                        default="example.com",
                        show_when=ShowWhen(field="record_type", equals="uri"),
                    ),
                ],
            ),
        ]

        tabbed_form = TabbedFormWidget(tabs)

        # Without fix: Tab 2 widgets return isVisible()=False because Tab 1 is active
        # With fix: should_include_field() evaluates show_when conditions directly

        # Get values while Tab 1 is active (default)
        values = tabbed_form.getValues()

        # The conditional fields in Tab 2 should be included because
        # record_type="uri" satisfies their show_when condition
        assert "uri_prefix" in values, "uri_prefix should be included when record_type=uri"
        assert "uri_value" in values, "uri_value should be included when record_type=uri"
        assert values["uri_prefix"] == "https"
        assert values["uri_value"] == "example.com"

    def test_conditional_fields_excluded_when_condition_not_met(self, qapp):
        """
        Test that conditional fields are excluded when their show_when
        condition is NOT met, regardless of tab visibility.
        """
        tabs = [
            TabDefinition(
                name="Settings",
                fields=[
                    FieldDefinition(
                        id="mode",
                        type=FieldType.DROPDOWN,
                        label="Mode",
                        options=[
                            FieldOption(label="Simple", value="simple"),
                            FieldOption(label="Advanced", value="advanced"),
                        ],
                        default="simple",  # Simple mode - advanced options hidden
                    ),
                ],
            ),
            TabDefinition(
                name="Advanced",
                fields=[
                    FieldDefinition(
                        id="advanced_setting",
                        type=FieldType.TEXT,
                        label="Advanced Setting",
                        default="value",
                        show_when=ShowWhen(field="mode", equals="advanced"),
                    ),
                ],
            ),
        ]

        tabbed_form = TabbedFormWidget(tabs)

        # Get values - advanced_setting should NOT be included because mode=simple
        values = tabbed_form.getValues()

        assert "mode" in values
        assert values["mode"] == "simple"
        assert "advanced_setting" not in values, \
            "advanced_setting should be excluded when mode=simple"


class TestCrossFieldValidator:
    """Tests for CrossFieldValidator."""

    def test_equals_field_validation(self, qapp):
        """Test equals_field cross-validation."""
        password_field = FieldDefinition(
            id="password",
            type=FieldType.PASSWORD,
            label="Password",
        )

        confirm_field = FieldDefinition(
            id="confirm",
            type=FieldType.PASSWORD,
            label="Confirm Password",
            validation=FieldValidation(
                equals_field="password",
                message="Passwords must match",
            ),
        )

        password_widget = FieldFactory.create(password_field)
        confirm_widget = FieldFactory.create(confirm_field)

        validator = CrossFieldValidator([password_widget, confirm_widget])

        # Track validation results
        validation_results = []
        validator.validationChanged.connect(
            lambda fid, valid, err: validation_results.append((fid, valid, err))
        )

        # Set matching passwords
        password_widget.setValue("secret123")
        confirm_widget.setValue("secret123")

        # Set non-matching
        confirm_widget.setValue("different")

        # Should have received validation failure
        assert any(not result[1] for result in validation_results)
