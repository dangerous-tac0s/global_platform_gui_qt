"""
Unit tests for YAML Plugin Adapter and Loader

Tests the YamlPluginAdapter and YamlPluginLoader classes.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.plugins.yaml.adapter import YamlPluginAdapter, ValidationError
from src.plugins.yaml.loader import YamlPluginLoader, discover_yaml_plugins, load_yaml_plugin
from src.plugins.yaml.schema import SourceType


# Path to example plugins
EXAMPLES_DIR = Path(__file__).parent.parent.parent / "plugins" / "examples"


class TestYamlPluginAdapter:
    """Tests for YamlPluginAdapter class."""

    def test_load_simple_plugin(self):
        """Test loading a simple plugin."""
        path = EXAMPLES_DIR / "simple_applet.yaml"
        adapter = YamlPluginAdapter.from_file(path)

        assert adapter.name == "simple-memory-reporter"
        assert adapter.schema.plugin.version == "1.0.0"

    def test_load_complex_plugin(self):
        """Test loading a complex plugin with all features."""
        path = EXAMPLES_DIR / "smartpgp.yaml"
        adapter = YamlPluginAdapter.from_file(path)

        assert adapter.name == "smartpgp"
        assert adapter.has_management_ui()
        assert len(adapter.get_management_actions()) > 0

    def test_fetch_available_caps_http(self):
        """Test fetching CAP info for HTTP source."""
        path = EXAMPLES_DIR / "simple_applet.yaml"
        adapter = YamlPluginAdapter.from_file(path)

        caps = adapter.fetch_available_caps()
        assert len(caps) == 1
        assert "memory-reporter.cap" in caps
        assert caps["memory-reporter.cap"].startswith("https://")

    def test_fetch_available_caps_github(self):
        """Test fetching CAP info for GitHub source."""
        path = EXAMPLES_DIR / "smartpgp.yaml"
        adapter = YamlPluginAdapter.from_file(path)

        caps = adapter.fetch_available_caps()
        # Multiple CAP files may match the asset pattern (default and large variants)
        assert len(caps) >= 1
        # All URLs should reference the ANSSI-FR repo (original SmartPGP source)
        for name, url in caps.items():
            assert "SmartPGP" in name
            assert "github://" in url or "ANSSI-FR" in url or "github-af" in url

    def test_get_descriptions(self):
        """Test getting applet descriptions."""
        path = EXAMPLES_DIR / "simple_applet.yaml"
        adapter = YamlPluginAdapter.from_file(path)

        descriptions = adapter.get_descriptions()
        assert len(descriptions) == 1

    def test_get_mutual_exclusions(self):
        """Test getting mutual exclusion list."""
        path = EXAMPLES_DIR / "simple_applet.yaml"
        adapter = YamlPluginAdapter.from_file(path)

        exclusions = adapter.get_mutual_exclusions()
        # Simple applet has no exclusions
        assert exclusions == []

    def test_set_cap_name(self):
        """Test setting selected CAP name."""
        path = EXAMPLES_DIR / "simple_applet.yaml"
        adapter = YamlPluginAdapter.from_file(path)

        adapter.set_cap_name("test.cap")
        assert adapter._selected_cap == "test.cap"

    def test_set_release(self):
        """Test setting release version."""
        path = EXAMPLES_DIR / "simple_applet.yaml"
        adapter = YamlPluginAdapter.from_file(path)

        adapter.set_release("v1.2.3")
        assert adapter.release == "1.2.3"  # v prefix stripped

        adapter.set_release("2.0.0")
        assert adapter.release == "2.0.0"

    def test_storage_from_schema(self):
        """Test that storage is loaded from schema."""
        path = EXAMPLES_DIR / "simple_applet.yaml"
        adapter = YamlPluginAdapter.from_file(path)

        # Storage should be populated from schema
        assert len(adapter.storage) > 0

    def test_get_result_no_dialog(self):
        """Test get_result when no dialog was shown."""
        path = EXAMPLES_DIR / "simple_applet.yaml"
        adapter = YamlPluginAdapter.from_file(path)

        result = adapter.get_result()
        assert "param_string" in result

    def test_get_aid_static(self):
        """Test getting static AID."""
        path = EXAMPLES_DIR / "simple_applet.yaml"
        adapter = YamlPluginAdapter.from_file(path)

        aid = adapter.get_aid()
        assert aid == "A0000008466D656D6F727901"

    def test_get_aid_dynamic(self):
        """Test getting dynamic AID."""
        path = EXAMPLES_DIR / "smartpgp.yaml"
        adapter = YamlPluginAdapter.from_file(path)

        # Set dialog values for dynamic AID construction
        adapter._dialog_values = {
            "manufacturer_id": "000A",
            "serial_number": "00000001",
        }

        aid = adapter.get_aid()
        assert aid.startswith("D276000124010304")
        assert "000A" in aid
        assert "00000001" in aid


class TestYamlPluginAdapterWithDialog:
    """Tests for YamlPluginAdapter dialog functionality."""

    @pytest.fixture
    def qapp(self):
        """Create QApplication for dialog tests."""
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        yield app

    def test_create_dialog_with_ui(self, qapp):
        """Test creating dialog for plugin with install_ui."""
        import os
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

        path = EXAMPLES_DIR / "smartpgp.yaml"
        adapter = YamlPluginAdapter.from_file(path)

        dialog = adapter.create_dialog()
        assert dialog is not None

    def test_create_dialog_without_ui(self, qapp):
        """Test creating dialog for plugin without install_ui."""
        path = EXAMPLES_DIR / "simple_applet.yaml"
        adapter = YamlPluginAdapter.from_file(path)

        dialog = adapter.create_dialog()
        assert dialog is None


class TestYamlPluginLoader:
    """Tests for YamlPluginLoader class."""

    def test_discover_plugins(self):
        """Test discovering plugins from directories."""
        base_dir = Path(__file__).parent.parent.parent
        loader = YamlPluginLoader(str(base_dir))

        plugins = loader.discover(["plugins/examples"])

        assert len(plugins) >= 2
        assert "simple-memory-reporter" in plugins
        assert "smartpgp" in plugins

    def test_discover_recursive(self):
        """Test recursive directory scanning."""
        base_dir = Path(__file__).parent.parent.parent
        loader = YamlPluginLoader(str(base_dir))

        # Discover with recursion
        plugins = loader.discover(["plugins"], recursive=True)

        # Should find plugins in subdirectories
        assert len(plugins) >= 2

    def test_discover_non_recursive(self):
        """Test non-recursive directory scanning."""
        base_dir = Path(__file__).parent.parent.parent
        loader = YamlPluginLoader(str(base_dir))

        # Discover without recursion - plugins dir itself has no YAML files
        plugins = loader.discover(["plugins"], recursive=False)

        # May or may not find plugins depending on structure
        # Just verify it doesn't crash

    def test_load_single_file(self):
        """Test loading a single plugin file."""
        base_dir = Path(__file__).parent.parent.parent
        loader = YamlPluginLoader(str(base_dir))

        adapter = loader.load_file("plugins/examples/simple_applet.yaml")
        assert adapter.name == "simple-memory-reporter"

    def test_get_errors(self):
        """Test getting error list after discovery."""
        base_dir = Path(__file__).parent.parent.parent
        loader = YamlPluginLoader(str(base_dir))

        loader.discover(["plugins/examples"])

        errors = loader.get_errors()
        # Should be empty for valid plugins
        assert isinstance(errors, list)

    def test_discover_handles_invalid_files(self, tmp_path):
        """Test that invalid YAML files are handled gracefully."""
        # Create an invalid YAML file
        invalid_file = tmp_path / "invalid.yaml"
        invalid_file.write_text("this is not: valid: yaml: {{{{")

        loader = YamlPluginLoader(str(tmp_path))
        plugins = loader.discover(["."])

        # Should have no plugins and one error
        assert len(plugins) == 0
        errors = loader.get_errors()
        assert len(errors) == 1

    def test_discover_handles_missing_dir(self):
        """Test that missing directories are handled gracefully."""
        loader = YamlPluginLoader("/tmp")
        plugins = loader.discover(["nonexistent_directory"])

        # Should return empty dict without crashing
        assert plugins == {}


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_discover_yaml_plugins(self):
        """Test discover_yaml_plugins function."""
        base_dir = Path(__file__).parent.parent.parent

        plugins = discover_yaml_plugins(
            str(base_dir),
            ["plugins/examples"],
        )

        assert len(plugins) >= 2

    def test_load_yaml_plugin(self):
        """Test load_yaml_plugin function."""
        path = EXAMPLES_DIR / "simple_applet.yaml"

        adapter = load_yaml_plugin(path)
        assert adapter.name == "simple-memory-reporter"


class TestValidationError:
    """Tests for ValidationError in hooks."""

    def test_validation_error_in_hook(self):
        """Test that ValidationError can be raised in hooks."""
        from src.plugins.yaml.parser import YamlPluginParser

        yaml_str = """
schema_version: "1.0"
plugin:
  name: "test-validation"
applet:
  source:
    type: "http"
    url: "https://example.com/test.cap"
  metadata:
    name: "Test"
    aid: "A0000000010203"
hooks:
  pre_install:
    type: "script"
    script: |
      raise ValidationError("Test validation failed")
"""
        schema = YamlPluginParser.loads(yaml_str)
        adapter = YamlPluginAdapter(schema)

        with pytest.raises(ValidationError) as exc_info:
            adapter.pre_install()

        assert "Test validation failed" in str(exc_info.value)
