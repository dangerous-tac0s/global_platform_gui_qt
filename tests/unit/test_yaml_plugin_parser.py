"""
Unit tests for YAML Plugin Parser

Tests the schema definitions and YAML parsing functionality.
"""

import pytest
from pathlib import Path

from src.plugins.yaml.schema import (
    PluginSchema,
    PluginInfo,
    SourceType,
    FieldType,
    EncodingType,
    StepType,
    CURRENT_SCHEMA_VERSION,
)
from src.plugins.yaml.parser import YamlPluginParser, YamlParseError


# Path to example plugins
EXAMPLES_DIR = Path(__file__).parent.parent.parent / "plugins" / "examples"


class TestYamlPluginParser:
    """Tests for YamlPluginParser class."""

    def test_load_simple_applet(self):
        """Test loading a simple applet YAML file."""
        path = EXAMPLES_DIR / "simple_applet.yaml"
        schema = YamlPluginParser.load(path)

        assert schema.schema_version == CURRENT_SCHEMA_VERSION
        assert schema.plugin.name == "simple-memory-reporter"
        assert schema.plugin.version == "1.0.0"
        assert schema.applet.source.type == SourceType.HTTP
        assert schema.applet.source.url == "https://example.com/memory-reporter.cap"
        assert schema.applet.metadata.name == "Memory Reporter"
        assert schema.applet.metadata.aid == "A0000008466D656D6F727901"
        assert schema.applet.metadata.storage.persistent == 1024
        assert schema.applet.metadata.storage.transient == 256

    def test_load_smartpgp(self):
        """Test loading the SmartPGP plugin with complex features."""
        path = EXAMPLES_DIR / "smartpgp.yaml"
        schema = YamlPluginParser.load(path)

        # Plugin info
        assert schema.plugin.name == "smartpgp"
        assert schema.plugin.version == "1.0.0"

        # Source (ANSSI-FR is the original SmartPGP source with on-card key generation)
        assert schema.applet.source.type == SourceType.GITHUB_RELEASE
        assert schema.applet.source.owner == "ANSSI-FR"
        assert schema.applet.source.repo == "SmartPGP"

        # Dynamic AID construction
        assert schema.has_dynamic_aid()
        aid_const = schema.applet.metadata.aid_construction
        assert aid_const.base == "D276000124010304"
        assert len(aid_const.segments) == 3
        assert aid_const.segments[0].name == "manufacturer"
        assert aid_const.segments[0].length == 2
        assert aid_const.segments[0].source == "field:manufacturer_id"

        # Install UI
        assert schema.has_install_ui()
        assert schema.install_ui.form is not None
        assert len(schema.install_ui.form.fields) == 2
        assert schema.install_ui.form.fields[0].id == "manufacturer_id"
        assert schema.install_ui.form.fields[0].type == FieldType.TEXT
        assert schema.install_ui.form.fields[0].validation.pattern == "^[0-9A-Fa-f]{4}$"

        # Management UI
        assert schema.has_management_ui()
        assert len(schema.management_ui.state_readers) == 8  # PIN retries, admin PIN retries, 3 keys, name, url, login
        assert len(schema.management_ui.actions) == 7  # change PIN, 3 key generation, set name, url, login

        # Workflows
        assert "generate_sig_key" in schema.workflows
        workflow = schema.get_workflow("generate_sig_key")
        assert len(workflow.steps) == 7  # dialog + verify + set_algo + generate + compute_fp + upload_fp + upload_timestamp
        assert workflow.steps[0].type == StepType.DIALOG
        assert workflow.steps[1].type == StepType.APDU

        # Hooks
        assert schema.hooks is not None
        assert schema.hooks.pre_install is not None
        assert schema.hooks.pre_install.type == "script"

    def test_parse_from_string(self):
        """Test parsing YAML from a string."""
        yaml_str = """
schema_version: "1.0"
plugin:
  name: "test-plugin"
  description: "Test"
  version: "1.0.0"
applet:
  source:
    type: "local"
    path: "/path/to/applet.cap"
  metadata:
    name: "Test Applet"
    aid: "A000000001"
"""
        schema = YamlPluginParser.loads(yaml_str)
        assert schema.plugin.name == "test-plugin"
        assert schema.applet.source.type == SourceType.LOCAL
        assert schema.applet.source.path == "/path/to/applet.cap"

    def test_missing_required_field(self):
        """Test that missing required fields raise errors."""
        yaml_str = """
schema_version: "1.0"
plugin:
  name: "test-plugin"
# Missing applet section
"""
        with pytest.raises(YamlParseError) as exc_info:
            YamlPluginParser.loads(yaml_str)
        assert "Missing required field 'applet'" in str(exc_info.value)

    def test_invalid_source_type(self):
        """Test that invalid source types raise errors."""
        yaml_str = """
schema_version: "1.0"
plugin:
  name: "test"
applet:
  source:
    type: "invalid_type"
  metadata:
    name: "Test"
"""
        with pytest.raises(YamlParseError) as exc_info:
            YamlPluginParser.loads(yaml_str)
        assert "Invalid source type" in str(exc_info.value)

    def test_invalid_field_type(self):
        """Test that invalid field types raise errors."""
        yaml_str = """
schema_version: "1.0"
plugin:
  name: "test"
applet:
  source:
    type: "http"
    url: "https://example.com/test.cap"
  metadata:
    name: "Test"
install_ui:
  form:
    fields:
      - id: "test_field"
        type: "invalid_field_type"
        label: "Test"
"""
        with pytest.raises(YamlParseError) as exc_info:
            YamlPluginParser.loads(yaml_str)
        assert "Invalid field type" in str(exc_info.value)

    def test_unsupported_schema_version(self):
        """Test that unsupported schema versions raise errors."""
        yaml_str = """
schema_version: "99.0"
plugin:
  name: "test"
applet:
  source:
    type: "http"
    url: "https://example.com/test.cap"
  metadata:
    name: "Test"
"""
        with pytest.raises(YamlParseError) as exc_info:
            YamlPluginParser.loads(yaml_str)
        assert "Unsupported schema version" in str(exc_info.value)

    def test_file_not_found(self):
        """Test that non-existent files raise errors."""
        with pytest.raises(YamlParseError) as exc_info:
            YamlPluginParser.load("/nonexistent/path/plugin.yaml")
        assert "File not found" in str(exc_info.value)

    def test_empty_yaml(self):
        """Test that empty YAML raises errors."""
        with pytest.raises(YamlParseError) as exc_info:
            YamlPluginParser.loads("")
        assert "Empty YAML" in str(exc_info.value)


class TestPluginSchema:
    """Tests for PluginSchema dataclass methods."""

    def test_get_aid_static(self):
        """Test getting static AID."""
        yaml_str = """
schema_version: "1.0"
plugin:
  name: "test"
applet:
  source:
    type: "http"
    url: "https://example.com/test.cap"
  metadata:
    name: "Test"
    aid: "A0000000041010"
"""
        schema = YamlPluginParser.loads(yaml_str)
        assert schema.get_aid() == "A0000000041010"
        assert not schema.has_dynamic_aid()

    def test_has_dynamic_aid(self):
        """Test dynamic AID detection."""
        yaml_str = """
schema_version: "1.0"
plugin:
  name: "test"
applet:
  source:
    type: "http"
    url: "https://example.com/test.cap"
  metadata:
    name: "Test"
    aid_construction:
      base: "D276000124"
      segments:
        - name: "version"
          length: 2
          default: "0304"
"""
        schema = YamlPluginParser.loads(yaml_str)
        assert schema.has_dynamic_aid()
        assert schema.get_aid() is None

    def test_has_install_ui_dialog(self):
        """Test install UI with dialog."""
        yaml_str = """
schema_version: "1.0"
plugin:
  name: "test"
applet:
  source:
    type: "http"
    url: "https://example.com/test.cap"
  metadata:
    name: "Test"
install_ui:
  dialog:
    title: "Configure"
    tabs:
      - name: "Basic"
        fields:
          - id: "test"
            type: "text"
            label: "Test"
"""
        schema = YamlPluginParser.loads(yaml_str)
        assert schema.has_install_ui()
        assert schema.install_ui.dialog is not None
        assert schema.install_ui.dialog.title == "Configure"
        assert len(schema.install_ui.dialog.tabs) == 1

    def test_has_management_ui(self):
        """Test management UI detection."""
        yaml_str = """
schema_version: "1.0"
plugin:
  name: "test"
applet:
  source:
    type: "http"
    url: "https://example.com/test.cap"
  metadata:
    name: "Test"
management_ui:
  actions:
    - id: "test_action"
      label: "Test Action"
      apdu_sequence:
        - "00A4040007D276000124010304"
"""
        schema = YamlPluginParser.loads(yaml_str)
        assert schema.has_management_ui()
        assert len(schema.management_ui.actions) == 1
        assert schema.management_ui.actions[0].id == "test_action"


class TestFieldDefinitions:
    """Tests for field definition parsing."""

    def test_dropdown_with_options(self):
        """Test parsing dropdown with options."""
        yaml_str = """
schema_version: "1.0"
plugin:
  name: "test"
applet:
  source:
    type: "http"
    url: "https://example.com/test.cap"
  metadata:
    name: "Test"
install_ui:
  form:
    fields:
      - id: "key_type"
        type: "dropdown"
        label: "Key Type"
        options:
          - label: "RSA 2048"
            value: "01"
          - label: "ECC P-256"
            value: "12"
        default: "12"
"""
        schema = YamlPluginParser.loads(yaml_str)
        field = schema.install_ui.form.fields[0]
        assert field.type == FieldType.DROPDOWN
        assert len(field.options) == 2
        assert field.options[0].label == "RSA 2048"
        assert field.options[0].value == "01"
        assert field.default == "12"

    def test_field_with_validation(self):
        """Test parsing field with validation."""
        yaml_str = """
schema_version: "1.0"
plugin:
  name: "test"
applet:
  source:
    type: "http"
    url: "https://example.com/test.cap"
  metadata:
    name: "Test"
install_ui:
  form:
    fields:
      - id: "hex_input"
        type: "text"
        label: "Hex Value"
        validation:
          pattern: "^[0-9A-Fa-f]+$"
          message: "Must be hex characters"
          min_length: 2
          max_length: 32
"""
        schema = YamlPluginParser.loads(yaml_str)
        field = schema.install_ui.form.fields[0]
        assert field.validation is not None
        assert field.validation.pattern == "^[0-9A-Fa-f]+$"
        assert field.validation.min_length == 2
        assert field.validation.max_length == 32

    def test_field_with_show_when(self):
        """Test parsing field with conditional display."""
        yaml_str = """
schema_version: "1.0"
plugin:
  name: "test"
applet:
  source:
    type: "http"
    url: "https://example.com/test.cap"
  metadata:
    name: "Test"
install_ui:
  form:
    fields:
      - id: "mode"
        type: "dropdown"
        label: "Mode"
        options:
          - label: "Simple"
            value: "simple"
          - label: "Advanced"
            value: "advanced"
      - id: "advanced_option"
        type: "text"
        label: "Advanced Option"
        show_when:
          field: "mode"
          equals: "advanced"
"""
        schema = YamlPluginParser.loads(yaml_str)
        field = schema.install_ui.form.fields[1]
        assert field.show_when is not None
        assert field.show_when.field == "mode"
        assert field.show_when.equals == "advanced"


class TestWorkflowParsing:
    """Tests for workflow parsing."""

    def test_workflow_with_dependencies(self):
        """Test parsing workflow with step dependencies."""
        yaml_str = """
schema_version: "1.0"
plugin:
  name: "test"
applet:
  source:
    type: "http"
    url: "https://example.com/test.cap"
  metadata:
    name: "Test"
workflows:
  test_flow:
    steps:
      - id: "step1"
        type: "dialog"
        name: "Get Input"
        fields:
          - id: "value"
            type: "text"
            label: "Value"
      - id: "step2"
        type: "apdu"
        name: "Send Command"
        depends_on: ["step1"]
        apdu: "00A4040007{aid}"
      - id: "step3"
        type: "script"
        name: "Process"
        depends_on: ["step2"]
        script: |
          result = context.get("step2_response")
"""
        schema = YamlPluginParser.loads(yaml_str)
        workflow = schema.get_workflow("test_flow")
        assert workflow is not None
        assert len(workflow.steps) == 3

        assert workflow.steps[0].type == StepType.DIALOG
        assert len(workflow.steps[0].fields) == 1

        assert workflow.steps[1].type == StepType.APDU
        assert workflow.steps[1].depends_on == ["step1"]
        assert workflow.steps[1].apdu == "00A4040007{aid}"

        assert workflow.steps[2].type == StepType.SCRIPT
        assert workflow.steps[2].depends_on == ["step2"]
        assert "context.get" in workflow.steps[2].script
