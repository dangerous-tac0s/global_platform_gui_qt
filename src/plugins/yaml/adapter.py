"""
YAML Plugin Adapter

Adapts YAML plugin definitions to the BaseAppletPlugin interface,
allowing YAML plugins to be used alongside Python plugins.
"""

import os
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from PyQt5.QtWidgets import QDialog

from base_plugin import BaseAppletPlugin
from .schema import (
    AIDConstruction,
    PluginSchema,
    SourceType,
)
from .parser import YamlPluginParser
from .ui.dialog_builder import DialogBuilder, PluginDialog
from .encoding.encoder import AIDBuilder, ParameterEncoder


class YamlPluginAdapter(BaseAppletPlugin):
    """
    Adapts a YAML plugin definition to the BaseAppletPlugin interface.

    This allows YAML-defined plugins to be loaded and used by the existing
    plugin system without modification.
    """

    def __init__(self, schema: PluginSchema, yaml_path: Optional[str] = None):
        """
        Initialize the adapter with a parsed plugin schema.

        Args:
            schema: Parsed PluginSchema from YAML
            yaml_path: Optional path to the source YAML file
        """
        self._schema = schema
        self._yaml_path = yaml_path
        self._selected_cap: Optional[str] = None
        self._dialog: Optional[PluginDialog] = None
        self._dialog_values: dict[str, Any] = {}
        self._param_encoder = ParameterEncoder(schema.parameters)

        # For compatibility with BaseAppletPlugin
        self.release = None
        self.storage = {}

        # Load storage from schema if defined
        if schema.applet.metadata.storage:
            cap_name = self._get_cap_name()
            if cap_name:
                self.storage = {
                    cap_name: {
                        "persistent": schema.applet.metadata.storage.persistent,
                        "transient": schema.applet.metadata.storage.transient,
                    }
                }

    @classmethod
    def from_file(cls, path: str | Path) -> "YamlPluginAdapter":
        """
        Create an adapter from a YAML file path.

        Args:
            path: Path to the YAML plugin file

        Returns:
            Configured YamlPluginAdapter instance
        """
        schema = YamlPluginParser.load(path)
        return cls(schema, str(path))

    @classmethod
    def from_string(cls, yaml_str: str) -> "YamlPluginAdapter":
        """
        Create an adapter from a YAML string.

        Args:
            yaml_str: YAML content as string

        Returns:
            Configured YamlPluginAdapter instance
        """
        schema = YamlPluginParser.loads(yaml_str)
        return cls(schema)

    @property
    def name(self) -> str:
        """Return the plugin name."""
        return self._schema.plugin.name

    @property
    def schema(self) -> PluginSchema:
        """Return the underlying plugin schema."""
        return self._schema

    def _get_cap_name(self) -> Optional[str]:
        """Get the CAP filename from the source definition."""
        source = self._schema.applet.source

        if source.url:
            # Extract filename from URL
            parsed = urlparse(source.url)
            path = parsed.path
            if path:
                return os.path.basename(path)

        if source.path:
            return os.path.basename(source.path)

        if source.asset_pattern:
            # Use the pattern as a basis (without glob chars)
            pattern = source.asset_pattern.replace("*", "").replace("?", "")
            if pattern.endswith(".cap"):
                return pattern
            return f"{self._schema.plugin.name}.cap"

        return f"{self._schema.plugin.name}.cap"

    def create_dialog(self, parent=None) -> Optional[QDialog]:
        """
        Create and return a configuration dialog if defined.

        Args:
            parent: Parent widget

        Returns:
            QDialog instance or None if no UI defined
        """
        if not self._schema.has_install_ui():
            return None

        self._dialog = DialogBuilder.build(
            self._schema.install_ui,
            title=f"Configure {self._schema.applet.metadata.name}",
            parent=parent,
        )

        return self._dialog

    def fetch_available_caps(self) -> dict[str, str]:
        """
        Return available CAP files with their download URLs.

        Returns:
            Dict mapping cap_filename to download_url
        """
        source = self._schema.applet.source
        cap_name = self._get_cap_name()

        if source.type == SourceType.HTTP:
            if source.url:
                return {cap_name: source.url}

        elif source.type == SourceType.LOCAL:
            if source.path:
                return {cap_name: f"file://{source.path}"}
            if source.url:
                return {cap_name: source.url}

        elif source.type == SourceType.GITHUB_RELEASE:
            # For GitHub releases, we need to fetch from the API
            # Return a placeholder that will be resolved by the main app
            # or implement GitHub API call here
            if source.owner and source.repo:
                # Return a special URL format that can be resolved later
                return {
                    cap_name: f"github://{source.owner}/{source.repo}/{source.asset_pattern or '*.cap'}"
                }

        return {}

    def pre_install(self, **kwargs):
        """
        Execute pre-install hooks if defined.

        Raises:
            Exception if pre-install validation fails
        """
        if not self._schema.hooks or not self._schema.hooks.pre_install:
            return

        hook = self._schema.hooks.pre_install

        if hook.type == "script" and hook.script:
            self._execute_hook_script(hook.script, kwargs)
        elif hook.type == "command" and hook.command:
            self._execute_hook_command(hook.command, kwargs)

    def post_install(self, **kwargs):
        """Execute post-install hooks if defined."""
        if not self._schema.hooks or not self._schema.hooks.post_install:
            return

        hook = self._schema.hooks.post_install

        if hook.type == "script" and hook.script:
            self._execute_hook_script(hook.script, kwargs)
        elif hook.type == "command" and hook.command:
            self._execute_hook_command(hook.command, kwargs)

    def pre_uninstall(self, **kwargs):
        """Execute pre-uninstall hooks if defined."""
        if not self._schema.hooks or not self._schema.hooks.pre_uninstall:
            return

        hook = self._schema.hooks.pre_uninstall

        if hook.type == "script" and hook.script:
            self._execute_hook_script(hook.script, kwargs)
        elif hook.type == "command" and hook.command:
            self._execute_hook_command(hook.command, kwargs)

    def post_uninstall(self, **kwargs):
        """Execute post-uninstall hooks if defined."""
        if not self._schema.hooks or not self._schema.hooks.post_uninstall:
            return

        hook = self._schema.hooks.post_uninstall

        if hook.type == "script" and hook.script:
            self._execute_hook_script(hook.script, kwargs)
        elif hook.type == "command" and hook.command:
            self._execute_hook_command(hook.command, kwargs)

    def _execute_hook_script(self, script: str, context: dict):
        """Execute a Python hook script."""
        # Build execution context
        local_vars = {
            "field_values": self._dialog_values,
            "context": context,
            "ValidationError": ValidationError,
        }

        safe_builtins = {
            "len": len,
            "str": str,
            "int": int,
            "hex": hex,
            "bytes": bytes,
            "True": True,
            "False": False,
            "None": None,
            "print": print,
        }

        global_vars = {"__builtins__": safe_builtins}

        try:
            exec(script, global_vars, local_vars)
        except ValidationError:
            raise
        except Exception as e:
            raise RuntimeError(f"Hook script failed: {e}")

    def _execute_hook_command(self, command: list[str], context: dict):
        """Execute a shell command hook."""
        import subprocess

        # Substitute variables in command
        processed_cmd = []
        for arg in command:
            processed = arg
            for key, value in self._dialog_values.items():
                processed = processed.replace(f"{{{key}}}", str(value))
            processed_cmd.append(processed)

        try:
            result = subprocess.run(
                processed_cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Command failed: {result.stderr}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Command timed out")

    def set_cap_name(self, cap_name: str, override_map=None):
        """Called when user selects a CAP file."""
        self._selected_cap = cap_name
        # YAML plugins don't use the override_map pattern
        self._override_instance = None

    def set_release(self, release: str):
        """Set the release version."""
        self.release = release.lstrip("v")
        # Storage is already set from schema, no need to load from JSON

    def get_descriptions(self) -> dict[str, str]:
        """Return applet descriptions."""
        cap_name = self._get_cap_name()
        description = self._schema.applet.metadata.description or ""

        if description:
            return {cap_name: description}
        return {}

    def get_result(self) -> dict[str, Any]:
        """
        Get the result after dialog is accepted.

        Returns:
            Dict with param_string and optionally create_aid
        """
        # Get values from dialog if it was shown
        if self._dialog:
            self._dialog_values = self._dialog.getValues()

        # Encode parameters
        result = self._param_encoder.encode(self._dialog_values)

        # Handle dynamic AID
        if self._schema.has_dynamic_aid():
            aid_construction = self._schema.applet.metadata.aid_construction
            aid = self._build_dynamic_aid(aid_construction)
            if result.get("create_aid"):
                result["create_aid"] = aid
            else:
                result["param_string"] += f" --create {aid}"

        # Handle static AID
        elif self._schema.get_aid() and not result.get("create_aid"):
            result["create_aid"] = self._schema.get_aid()

        return result

    def _build_dynamic_aid(self, aid_construction: AIDConstruction) -> str:
        """Build a dynamic AID from the construction rules."""
        segments = [
            {
                "name": seg.name,
                "length": seg.length,
                "source": seg.source,
                "default": seg.default,
            }
            for seg in aid_construction.segments
        ]

        return AIDBuilder.build(
            aid_construction.base,
            segments,
            self._dialog_values,
        )

    def get_aid(self) -> Optional[str]:
        """Get the AID (static or dynamic)."""
        if self._schema.has_dynamic_aid():
            return self._build_dynamic_aid(
                self._schema.applet.metadata.aid_construction
            )
        return self._schema.get_aid()

    def get_mutual_exclusions(self) -> list[str]:
        """Get list of CAP files this applet conflicts with."""
        return self._schema.applet.metadata.mutual_exclusion

    def has_management_ui(self) -> bool:
        """Check if this plugin has management UI."""
        return self._schema.has_management_ui()

    def get_management_actions(self) -> list[dict]:
        """Get list of management actions if defined."""
        if not self._schema.has_management_ui():
            return []

        return [
            {
                "id": action.id,
                "label": action.label,
                "description": action.description,
                "has_dialog": action.dialog is not None,
                "has_workflow": action.workflow is not None,
            }
            for action in self._schema.management_ui.actions
        ]


class ValidationError(Exception):
    """Exception raised when hook validation fails."""
    pass
