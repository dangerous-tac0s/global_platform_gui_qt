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
from .logging import logger
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
        self._fetched_cap_names: list[str] = []  # Cache of available cap names

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
        result = {}

        if source.type == SourceType.HTTP:
            cap_name = self._get_cap_name()
            if source.url:
                result = {cap_name: source.url}

        elif source.type == SourceType.LOCAL:
            cap_name = self._get_cap_name()
            if source.path:
                result = {cap_name: f"file://{source.path}"}
            elif source.url:
                result = {cap_name: source.url}

        elif source.type == SourceType.GITHUB_RELEASE:
            # Fetch from GitHub API to get actual download URLs
            if source.owner and source.repo:
                result = self._fetch_github_release_caps(
                    source.owner,
                    source.repo,
                    source.asset_pattern,
                )

        # Filter by variants if defined - only provide CAPs that are in the variants list
        if self._schema.applet.variants:
            variant_filenames = {v.filename for v in self._schema.applet.variants}
            result = {k: v for k, v in result.items() if k in variant_filenames}

        # Cache the cap names for later AID matching
        self._fetched_cap_names = list(result.keys())
        return result

    def get_variant_display_name(self, filename: str) -> str:
        """
        Get the display name for a CAP variant.

        Args:
            filename: The CAP filename

        Returns:
            Display name from variants config, or filename without extension
        """
        # Check if we have variant info
        for variant in self._schema.applet.variants:
            if variant.filename == filename:
                return variant.display_name

        # Fall back to filename without extension
        if filename.lower().endswith(".cap"):
            return filename[:-4]
        return filename

    def get_variants(self) -> list[dict]:
        """
        Get all variant definitions.

        Returns:
            List of variant dicts with filename, display_name, description
        """
        return [
            {
                "filename": v.filename,
                "display_name": v.display_name,
                "description": v.description,
            }
            for v in self._schema.applet.variants
        ]

    def has_variants(self) -> bool:
        """Check if this plugin has multiple variants defined."""
        return len(self._schema.applet.variants) > 1

    def set_cached_cap_names(self, cap_names: list[str]):
        """
        Set cached cap names from external data (e.g., config cache).

        This ensures get_cap_for_aid() returns correct cap names even
        when fetch_available_caps() was not called (using cached data).

        Args:
            cap_names: List of cap filenames to cache
        """
        if not self._fetched_cap_names:  # Don't overwrite if already fetched
            self._fetched_cap_names = list(cap_names)

    def get_extract_pattern(self) -> Optional[str]:
        """
        Get the extract pattern for ZIP archives.

        Returns:
            Glob pattern for extracting files from ZIP, or None if not a ZIP source
        """
        return self._schema.applet.source.extract_pattern

    def _fetch_github_release_caps(
        self,
        owner: str,
        repo: str,
        asset_pattern: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> dict[str, str]:
        """
        Fetch CAP files from a GitHub release.

        Args:
            owner: GitHub repo owner
            repo: GitHub repo name
            asset_pattern: Glob pattern to match assets (e.g., "SmartPGP*.cap")
            tag: Specific release tag (None for latest)

        Returns:
            Dict mapping cap_filename to download_url
        """
        import fnmatch
        import requests

        try:
            # Get release info from GitHub API
            if tag:
                api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
            else:
                api_url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"

            response = requests.get(api_url, timeout=15)
            response.raise_for_status()
            release_data = response.json()

            # Store release version
            self.release = release_data.get("tag_name", "").lstrip("v")

            # Find matching assets
            caps = {}
            pattern = asset_pattern or "*.cap"

            for asset in release_data.get("assets", []):
                asset_name = asset.get("name", "")
                if fnmatch.fnmatch(asset_name, pattern):
                    download_url = asset.get("browser_download_url", "")
                    if download_url:
                        caps[asset_name] = download_url

            return caps

        except requests.RequestException as e:
            logger.warning(f"Error fetching GitHub release for {owner}/{repo}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error fetching GitHub release: {e}", exc_info=True)
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

    def get_aid_list(self) -> list[str]:
        """Get list of AIDs this plugin can handle."""
        aid = self._schema.get_aid()
        if aid:
            return [aid]
        # For dynamic AIDs, return the base prefix
        if self._schema.has_dynamic_aid():
            base = self._schema.applet.metadata.aid_construction.base
            if base:
                return [base]
        return []

    def get_cap_for_aid(self, raw_aid: str) -> Optional[str]:
        """
        Given an AID, return the CAP filename if this plugin handles it.

        Args:
            raw_aid: The AID to match (from an installed applet)

        Returns:
            CAP filename if matched, None otherwise
        """
        norm_aid = raw_aid.upper().replace(" ", "")

        # Helper to get the best cap name
        def get_best_cap_name() -> str:
            # Priority: selected cap > fetched caps > default name
            if self._selected_cap:
                return self._selected_cap
            if self._fetched_cap_names:
                return self._fetched_cap_names[0]
            return self._get_cap_name()

        # Check for exact static AID match
        static_aid = self._schema.get_aid()
        if static_aid:
            if static_aid.upper().replace(" ", "") == norm_aid:
                return get_best_cap_name()

        # Check for dynamic AID (prefix match)
        if self._schema.has_dynamic_aid():
            base = self._schema.applet.metadata.aid_construction.base
            if base:
                base_norm = base.upper().replace(" ", "")
                if norm_aid.startswith(base_norm):
                    return get_best_cap_name()

        return None

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

        actions = []
        for action in self._schema.management_ui.actions:
            action_def = {
                "id": action.id,
                "label": action.label,
                "description": action.description,
                "has_dialog": action.dialog is not None,
                "has_workflow": action.workflow is not None,
            }

            # Include dialog fields if present
            if action.dialog and action.dialog.fields:
                action_def["dialog_fields"] = action.dialog.fields

            # Include workflow ID if present
            if action.workflow:
                action_def["workflow"] = action.workflow

            # Include APDU sequence if present
            if action.apdu_sequence:
                action_def["apdu_sequence"] = action.apdu_sequence

            actions.append(action_def)

        return actions

    def get_state_readers(self) -> list[dict]:
        """Get list of state reader definitions if defined."""
        if not self._schema.has_management_ui():
            return []

        if not self._schema.management_ui.state_readers:
            return []

        return [
            {
                "id": reader.id,
                "label": reader.label,
                "apdu": reader.apdu,
                "select_file": reader.select_file,  # File to SELECT before reading
                "parse": {
                    "type": reader.parse.type.value if hasattr(reader.parse.type, "value") else reader.parse.type,
                    "offset": reader.parse.offset,
                    "length": reader.parse.length,
                    "tag": reader.parse.tag,  # TLV tag to search for
                    "encoding": reader.parse.encoding,  # Value encoding (e.g., "ascii")
                    "format": reader.parse.format,  # Value format (e.g., "int" to convert hex to decimal)
                    "display": reader.parse.display,
                    "display_map": reader.parse.display_map,
                },
            }
            for reader in self._schema.management_ui.state_readers
        ]

    def create_management_dialog(self, nfc_service=None, parent=None, installed_aid=None):
        """
        Create a management dialog for this plugin.

        Args:
            nfc_service: NFC thread service for card communication
            parent: Parent widget
            installed_aid: The actual AID of the installed applet (from card)

        Returns:
            ManagementDialog or None if no management UI defined
        """
        if not self._schema.has_management_ui():
            return None

        from .ui.management_panel import (
            ActionDefinition,
            ManagementDialog,
            StateReaderDefinition,
        )

        # Convert actions
        actions = []
        for action in self._schema.management_ui.actions:
            action_def = ActionDefinition(
                id=action.id,
                label=action.label,
                description=action.description,
                dialog_fields=action.dialog.fields if action.dialog else None,
                workflow_id=action.workflow,
                apdu_sequence=action.apdu_sequence,
            )
            actions.append(action_def)

        # Convert state readers
        state_readers = None
        if self._schema.management_ui.state_readers:
            state_readers = [
                StateReaderDefinition(
                    id=r.id,
                    label=r.label,
                    apdu=r.apdu,
                    select_file=r.select_file,  # File to SELECT before reading
                    parse={
                        "type": r.parse.type.value if hasattr(r.parse.type, "value") else r.parse.type,
                        "offset": r.parse.offset,
                        "length": r.parse.length,
                        "tag": r.parse.tag,  # TLV tag to search for
                        "encoding": r.parse.encoding,  # Value encoding (e.g., "ascii")
                        "format": r.parse.format,  # Value format (e.g., "int")
                        "display": r.parse.display,
                        "display_map": r.parse.display_map,
                    },
                )
                for r in self._schema.management_ui.state_readers
            ]

        # Get the AID for SELECT
        # For dynamic AIDs, prefer using just the base prefix for selection.
        # This is more robust because it doesn't require knowing the exact
        # manufacturer/serial of the installed applet.
        if self._schema.has_dynamic_aid():
            # Use the base AID prefix for selection
            # E.g., for SmartPGP: D276000124010304 (or even shorter D27600012401)
            base_aid = self._schema.applet.metadata.aid_construction.base
            # If installed_aid is provided and starts with the base, use partial
            # This allows SELECT to find the correct applet regardless of suffix
            if installed_aid and installed_aid.upper().startswith(base_aid.upper()):
                applet_aid = base_aid  # Use base for selection
            else:
                applet_aid = base_aid  # Use base anyway for dynamic AIDs
        else:
            # For static AIDs, prefer the actual installed AID
            applet_aid = installed_aid or self.get_aid()

        # Get workflows if defined
        workflows = self._schema.workflows if self._schema.workflows else {}

        return ManagementDialog(
            title=f"Manage {self._schema.applet.metadata.name}",
            actions=actions,
            state_readers=state_readers,
            nfc_service=nfc_service,
            parent=parent,
            applet_aid=applet_aid,
            workflows=workflows,
        )


class ValidationError(Exception):
    """Exception raised when hook validation fails."""
    pass
