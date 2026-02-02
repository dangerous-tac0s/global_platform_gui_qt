"""
YAML Plugin Parser

Handles loading, validation, and conversion of YAML plugin files to schema objects.
"""

import re
from pathlib import Path
from typing import Any, Optional, Union

import yaml

from .schema import (
    AIDConstruction,
    AIDSegment,
    ApduCommand,
    AppletDefinition,
    AppletMetadata,
    CURRENT_SCHEMA_VERSION,
    DialogDefinition,
    EncodingType,
    FieldDefinition,
    FieldOption,
    FieldType,
    FieldValidation,
    FormDefinition,
    HookDefinition,
    HooksDefinition,
    InstallUIDefinition,
    ManagementAction,
    ManagementUIDefinition,
    ParameterDefinition,
    ParseType,
    PluginInfo,
    PluginSchema,
    ShowWhen,
    SourceDefinition,
    SourceType,
    StateParse,
    StateReader,
    StepType,
    StorageRequirements,
    SUPPORTED_SCHEMA_VERSIONS,
    TabDefinition,
    TLVEntry,
    WorkflowDefinition,
    WorkflowStep,
)


class YamlParseError(Exception):
    """Exception raised when parsing a YAML plugin file fails."""

    def __init__(self, message: str, path: Optional[str] = None, line: Optional[int] = None):
        self.path = path
        self.line = line
        location = ""
        if path:
            location = f" in {path}"
        if line:
            location += f" at line {line}"
        super().__init__(f"{message}{location}")


class YamlPluginParser:
    """
    Parser for YAML plugin definition files.

    Converts YAML files into validated PluginSchema objects.
    """

    @classmethod
    def load(cls, path: Union[str, Path]) -> PluginSchema:
        """
        Load and parse a YAML plugin file.

        Args:
            path: Path to the YAML file

        Returns:
            Validated PluginSchema object

        Raises:
            YamlParseError: If parsing or validation fails
        """
        path = Path(path)
        if not path.exists():
            raise YamlParseError(f"File not found: {path}")

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise YamlParseError(f"Invalid YAML syntax: {e}", str(path))

        if data is None:
            raise YamlParseError("Empty YAML file", str(path))

        return cls.parse(data, str(path))

    @classmethod
    def loads(cls, yaml_str: str, source: str = "<string>") -> PluginSchema:
        """
        Parse a YAML string.

        Args:
            yaml_str: YAML content as string
            source: Source identifier for error messages

        Returns:
            Validated PluginSchema object
        """
        try:
            data = yaml.safe_load(yaml_str)
        except yaml.YAMLError as e:
            raise YamlParseError(f"Invalid YAML syntax: {e}", source)

        if data is None:
            raise YamlParseError("Empty YAML content", source)

        return cls.parse(data, source)

    @classmethod
    def parse(cls, data: dict[str, Any], source: str = "<dict>") -> PluginSchema:
        """
        Parse a dictionary into a PluginSchema.

        Args:
            data: Dictionary from parsed YAML
            source: Source identifier for error messages

        Returns:
            Validated PluginSchema object
        """
        parser = cls(source)
        return parser._parse_root(data)

    def __init__(self, source: str = "<unknown>"):
        self.source = source

    def _error(self, message: str) -> YamlParseError:
        """Create a parse error with source context."""
        return YamlParseError(message, self.source)

    def _require(self, data: dict, key: str, context: str = "") -> Any:
        """Require a key to be present in a dictionary."""
        if key not in data:
            ctx = f" in {context}" if context else ""
            raise self._error(f"Missing required field '{key}'{ctx}")
        return data[key]

    def _get(self, data: dict, key: str, default: Any = None) -> Any:
        """Get a value with a default."""
        return data.get(key, default)

    def _parse_root(self, data: dict) -> PluginSchema:
        """Parse the root plugin schema."""
        # Validate schema version
        schema_version = self._get(data, "schema_version", CURRENT_SCHEMA_VERSION)
        if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise self._error(
                f"Unsupported schema version '{schema_version}'. "
                f"Supported versions: {SUPPORTED_SCHEMA_VERSIONS}"
            )

        # Parse required sections
        plugin_data = self._require(data, "plugin", "root")
        applet_data = self._require(data, "applet", "root")

        plugin = self._parse_plugin_info(plugin_data)
        applet = self._parse_applet(applet_data)

        # Parse optional sections
        install_ui = None
        if "install_ui" in data:
            install_ui = self._parse_install_ui(data["install_ui"])

        management_ui = None
        if "management_ui" in data:
            management_ui = self._parse_management_ui(data["management_ui"])

        parameters = None
        if "parameters" in data:
            parameters = self._parse_parameters(data["parameters"])

        workflows = {}
        if "workflows" in data:
            for name, workflow_data in data["workflows"].items():
                workflows[name] = self._parse_workflow(workflow_data, name)

        hooks = None
        if "hooks" in data:
            hooks = self._parse_hooks(data["hooks"])

        return PluginSchema(
            schema_version=schema_version,
            plugin=plugin,
            applet=applet,
            install_ui=install_ui,
            management_ui=management_ui,
            parameters=parameters,
            workflows=workflows,
            hooks=hooks,
        )

    def _parse_plugin_info(self, data: dict) -> PluginInfo:
        """Parse plugin info section."""
        return PluginInfo(
            name=self._require(data, "name", "plugin"),
            description=self._get(data, "description", ""),
            version=self._get(data, "version", "1.0.0"),
            author=self._get(data, "author", ""),
        )

    def _parse_applet(self, data: dict) -> AppletDefinition:
        """Parse applet definition section."""
        source_data = self._require(data, "source", "applet")
        metadata_data = self._require(data, "metadata", "applet")

        # Parse variants if present
        variants = []
        for variant_data in self._get(data, "variants", []):
            variants.append(self._parse_variant(variant_data))

        return AppletDefinition(
            source=self._parse_source(source_data),
            metadata=self._parse_metadata(metadata_data),
            variants=variants,
        )

    def _parse_variant(self, data: dict) -> "VariantDefinition":
        """Parse a variant definition."""
        from .schema import VariantDefinition, StorageRequirements

        filename = self._require(data, "filename", "variant")
        display_name = self._require(data, "display_name", "variant")
        description = self._get(data, "description")
        aid = self._get(data, "aid")

        # Parse optional per-variant overrides
        storage = None
        if "storage" in data:
            storage_data = data["storage"]
            storage = StorageRequirements(
                persistent=self._get(storage_data, "persistent", 0),
                transient=self._get(storage_data, "transient", 0),
            )

        install_ui = None
        if "install_ui" in data:
            install_ui = self._parse_install_ui(data["install_ui"])

        management_ui = None
        if "management_ui" in data:
            management_ui = self._parse_management_ui(data["management_ui"])

        return VariantDefinition(
            filename=filename,
            display_name=display_name,
            description=description,
            aid=aid,
            storage=storage,
            install_ui=install_ui,
            management_ui=management_ui,
        )

    def _parse_source(self, data: dict) -> SourceDefinition:
        """Parse source definition."""
        type_str = self._require(data, "type", "source")
        try:
            source_type = SourceType(type_str)
        except ValueError:
            raise self._error(
                f"Invalid source type '{type_str}'. "
                f"Valid types: {[t.value for t in SourceType]}"
            )

        return SourceDefinition(
            type=source_type,
            url=self._get(data, "url"),
            path=self._get(data, "path"),
            owner=self._get(data, "owner"),
            repo=self._get(data, "repo"),
            asset_pattern=self._get(data, "asset_pattern"),
            extract_pattern=self._get(data, "extract_pattern"),
        )

    def _parse_metadata(self, data: dict) -> AppletMetadata:
        """Parse applet metadata."""
        name = self._require(data, "name", "metadata")

        # Validate AID if provided
        aid = self._get(data, "aid")
        if aid:
            # Normalize and validate the AID
            normalized_aid = aid.upper().replace(" ", "")
            try:
                validate_aid(normalized_aid)
            except YamlParseError as e:
                raise self._error(str(e))
            aid = normalized_aid

        aid_construction = None
        if "aid_construction" in data:
            aid_construction = self._parse_aid_construction(data["aid_construction"])

        storage = StorageRequirements()
        if "storage" in data:
            storage_data = data["storage"]
            storage = StorageRequirements(
                persistent=self._get(storage_data, "persistent", 0),
                transient=self._get(storage_data, "transient", 0),
            )

        return AppletMetadata(
            name=name,
            aid=aid,
            aid_construction=aid_construction,
            storage=storage,
            mutual_exclusion=self._get(data, "mutual_exclusion", []),
            description=self._get(data, "description"),
        )

    def _parse_aid_construction(self, data: dict) -> AIDConstruction:
        """Parse dynamic AID construction rules."""
        base = self._require(data, "base", "aid_construction")

        # Validate base is valid hex
        normalized_base = base.upper().replace(" ", "")
        try:
            validate_hex_string(normalized_base, "aid_construction.base")
        except YamlParseError as e:
            raise self._error(str(e))

        segments = []
        for seg_data in self._get(data, "segments", []):
            # Validate default value if provided
            default = self._get(seg_data, "default")
            if default:
                normalized_default = default.upper().replace(" ", "")
                try:
                    validate_hex_string(normalized_default, "aid_construction.segment.default")
                except YamlParseError as e:
                    raise self._error(str(e))
                default = normalized_default

            segments.append(
                AIDSegment(
                    name=self._require(seg_data, "name", "aid_construction.segment"),
                    length=self._require(seg_data, "length", "aid_construction.segment"),
                    source=self._get(seg_data, "source"),
                    default=default,
                )
            )

        return AIDConstruction(base=normalized_base, segments=segments)

    def _parse_install_ui(self, data: dict) -> InstallUIDefinition:
        """Parse installation UI definition."""
        dialog = None
        form = None

        if "dialog" in data:
            dialog = self._parse_dialog(data["dialog"])
        if "form" in data:
            form = self._parse_form(data["form"])

        return InstallUIDefinition(dialog=dialog, form=form)

    def _parse_dialog(self, data: dict) -> DialogDefinition:
        """Parse dialog definition with tabs."""
        tabs = []
        for tab_data in self._get(data, "tabs", []):
            tabs.append(
                TabDefinition(
                    name=self._require(tab_data, "name", "dialog.tab"),
                    fields=self._parse_fields(self._get(tab_data, "fields", [])),
                )
            )

        size = self._get(data, "size", [400, 400])
        if isinstance(size, list) and len(size) == 2:
            size = tuple(size)
        else:
            size = (400, 400)

        return DialogDefinition(
            title=self._get(data, "title", "Configuration"),
            size=size,
            tabs=tabs,
        )

    def _parse_form(self, data: dict) -> FormDefinition:
        """Parse simple form definition."""
        return FormDefinition(
            fields=self._parse_fields(self._get(data, "fields", []))
        )

    def _parse_fields(self, fields_data: list) -> list[FieldDefinition]:
        """Parse a list of field definitions."""
        fields = []
        for field_data in fields_data:
            fields.append(self._parse_field(field_data))
        return fields

    def _parse_field(self, data: dict) -> FieldDefinition:
        """Parse a single field definition."""
        field_id = self._require(data, "id", "field")
        type_str = self._require(data, "type", f"field '{field_id}'")

        try:
            field_type = FieldType(type_str)
        except ValueError:
            raise self._error(
                f"Invalid field type '{type_str}' for field '{field_id}'. "
                f"Valid types: {[t.value for t in FieldType]}"
            )

        # Parse options for dropdown
        options = []
        for opt_data in self._get(data, "options", []):
            if isinstance(opt_data, dict):
                options.append(
                    FieldOption(
                        label=self._require(opt_data, "label", f"field '{field_id}' option"),
                        value=str(self._require(opt_data, "value", f"field '{field_id}' option")),
                    )
                )
            else:
                # Simple string option - use as both label and value
                options.append(FieldOption(label=str(opt_data), value=str(opt_data)))

        # Parse validation
        validation = None
        if "validation" in data:
            val_data = data["validation"]
            validation = FieldValidation(
                pattern=self._get(val_data, "pattern"),
                message=self._get(val_data, "message"),
                min_length=self._get(val_data, "min_length"),
                max_length=self._get(val_data, "max_length"),
                min_value=self._get(val_data, "min_value"),
                max_value=self._get(val_data, "max_value"),
                equals_field=self._get(val_data, "equals_field"),
            )

        # Parse show_when
        show_when = None
        if "show_when" in data:
            sw_data = data["show_when"]
            show_when = ShowWhen(
                field=self._require(sw_data, "field", f"field '{field_id}' show_when"),
                equals=self._get(sw_data, "equals"),
                not_equals=self._get(sw_data, "not_equals"),
                is_set=self._get(sw_data, "is_set"),
            )

        return FieldDefinition(
            id=field_id,
            type=field_type,
            label=self._get(data, "label", field_id),
            placeholder=self._get(data, "placeholder"),
            default=self._get(data, "default"),
            required=self._get(data, "required", False),
            options=options,
            validation=validation,
            show_when=show_when,
            transform=self._get(data, "transform"),
            rows=self._get(data, "rows", 4),
            description=self._get(data, "description"),
            width=self._get(data, "width", 1.0),
            readonly=self._get(data, "readonly", False),
        )

    def _parse_management_ui(self, data: dict) -> ManagementUIDefinition:
        """Parse management UI definition."""
        actions = []
        for action_data in self._get(data, "actions", []):
            actions.append(self._parse_management_action(action_data))

        state_readers = []
        for reader_data in self._get(data, "state_readers", []):
            state_readers.append(self._parse_state_reader(reader_data))

        return ManagementUIDefinition(
            actions=actions,
            state_readers=state_readers,
        )

    def _parse_management_action(self, data: dict) -> ManagementAction:
        """Parse a management action."""
        action_id = self._require(data, "id", "management_ui.action")

        dialog = None
        if "dialog" in data:
            dialog = self._parse_form(data["dialog"])

        apdu_sequence = []
        for apdu_data in self._get(data, "apdu_sequence", []):
            if isinstance(apdu_data, str):
                apdu_sequence.append(ApduCommand(apdu=apdu_data))
            else:
                apdu_sequence.append(
                    ApduCommand(
                        apdu=self._require(apdu_data, "apdu", f"action '{action_id}' apdu"),
                        command=self._get(apdu_data, "command"),
                        description=self._get(apdu_data, "description"),
                    )
                )

        return ManagementAction(
            id=action_id,
            label=self._get(data, "label", action_id),
            dialog=dialog,
            apdu_sequence=apdu_sequence,
            workflow=self._get(data, "workflow"),
            description=self._get(data, "description"),
        )

    def _parse_state_reader(self, data: dict) -> StateReader:
        """Parse a state reader definition."""
        reader_id = self._require(data, "id", "state_reader")
        parse_data = self._require(data, "parse", f"state_reader '{reader_id}'")

        try:
            parse_type = ParseType(parse_data.get("type", "hex"))
        except ValueError:
            raise self._error(
                f"Invalid parse type for state_reader '{reader_id}'. "
                f"Valid types: {[t.value for t in ParseType]}"
            )

        state_parse = StateParse(
            type=parse_type,
            offset=self._get(parse_data, "offset", 0),
            length=self._get(parse_data, "length"),
            tag=self._get(parse_data, "tag"),
            encoding=self._get(parse_data, "encoding"),
            format=self._get(parse_data, "format"),
            display=self._get(parse_data, "display"),
            display_map=self._get(parse_data, "display_map"),
        )

        return StateReader(
            id=reader_id,
            label=self._get(data, "label", reader_id),
            apdu=self._require(data, "apdu", f"state_reader '{reader_id}'"),
            parse=state_parse,
            select_file=self._get(data, "select_file"),
        )

    def _parse_parameters(self, data: dict) -> ParameterDefinition:
        """Parse parameter encoding definition."""
        encoding_str = self._get(data, "encoding", "none")
        try:
            encoding = EncodingType(encoding_str)
        except ValueError:
            raise self._error(
                f"Invalid encoding type '{encoding_str}'. "
                f"Valid types: {[t.value for t in EncodingType]}"
            )

        tlv_structure = []
        for tlv_data in self._get(data, "tlv_structure", []):
            tlv_structure.append(
                TLVEntry(
                    tag=self._require(tlv_data, "tag", "parameters.tlv_structure"),
                    value=self._require(tlv_data, "value", "parameters.tlv_structure"),
                    length_bytes=self._get(tlv_data, "length_bytes", 1),
                )
            )

        return ParameterDefinition(
            encoding=encoding,
            template=self._get(data, "template"),
            tlv_structure=tlv_structure,
            builder=self._get(data, "builder"),
            create_aid=self._get(data, "create_aid"),
        )

    def _parse_workflow(self, data: dict, name: str) -> WorkflowDefinition:
        """Parse a workflow definition."""
        steps = []
        for step_data in self._get(data, "steps", []):
            steps.append(self._parse_workflow_step(step_data, name))

        return WorkflowDefinition(steps=steps)

    def _parse_workflow_step(self, data: dict, workflow_name: str) -> WorkflowStep:
        """Parse a workflow step."""
        step_id = self._require(data, "id", f"workflow '{workflow_name}' step")
        type_str = self._require(data, "type", f"workflow step '{step_id}'")

        try:
            step_type = StepType(type_str)
        except ValueError:
            raise self._error(
                f"Invalid step type '{type_str}' for step '{step_id}'. "
                f"Valid types: {[t.value for t in StepType]}"
            )

        # Parse command as list if it's a string
        command = self._get(data, "command")
        if isinstance(command, str):
            command = [command]

        # Parse fields for dialog steps
        fields = self._parse_fields(self._get(data, "fields", []))

        return WorkflowStep(
            id=step_id,
            type=step_type,
            name=self._get(data, "name"),
            description=self._get(data, "description"),
            depends_on=self._get(data, "depends_on", []),
            script=self._get(data, "script"),
            command=command,
            apdu=self._get(data, "apdu"),
            fields=fields,
        )

    def _parse_hooks(self, data: dict) -> HooksDefinition:
        """Parse lifecycle hooks."""
        hooks = HooksDefinition()

        if "pre_install" in data:
            hooks.pre_install = self._parse_hook(data["pre_install"], "pre_install")
        if "post_install" in data:
            hooks.post_install = self._parse_hook(data["post_install"], "post_install")
        if "pre_uninstall" in data:
            hooks.pre_uninstall = self._parse_hook(data["pre_uninstall"], "pre_uninstall")
        if "post_uninstall" in data:
            hooks.post_uninstall = self._parse_hook(data["post_uninstall"], "post_uninstall")

        return hooks

    def _parse_hook(self, data: dict, hook_name: str) -> HookDefinition:
        """Parse a single hook definition."""
        hook_type = self._require(data, "type", f"hook '{hook_name}'")
        if hook_type not in ("script", "command"):
            raise self._error(
                f"Invalid hook type '{hook_type}' for hook '{hook_name}'. "
                "Valid types: script, command"
            )

        command = self._get(data, "command")
        if isinstance(command, str):
            command = [command]

        return HookDefinition(
            type=hook_type,
            script=self._get(data, "script"),
            command=command,
        )


def validate_hex_string(value: str, field_name: str = "value") -> bool:
    """
    Validate that a string is valid hexadecimal.

    Args:
        value: String to validate
        field_name: Name of field for error messages

    Returns:
        True if valid

    Raises:
        YamlParseError: If invalid hex
    """
    if not re.match(r"^[0-9A-Fa-f]*$", value):
        raise YamlParseError(f"Invalid hex string for {field_name}: '{value}'")
    return True


def validate_aid(aid: str) -> bool:
    """
    Validate an AID string.

    AIDs must be 5-16 bytes (10-32 hex characters).

    Args:
        aid: AID string to validate

    Returns:
        True if valid

    Raises:
        YamlParseError: If invalid AID
    """
    validate_hex_string(aid, "AID")
    if len(aid) < 10 or len(aid) > 32:
        raise YamlParseError(
            f"Invalid AID length: {len(aid)//2} bytes. AIDs must be 5-16 bytes."
        )
    return True
