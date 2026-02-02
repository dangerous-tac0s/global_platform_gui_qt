"""
YAML Plugin Schema Definitions

Dataclass models representing the structure of YAML plugin definitions.
These models are used for parsing, validation, and type-safe access to plugin data.
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Optional
from enum import Enum


class SourceType(str, Enum):
    """Types of CAP file sources."""
    HTTP = "http"
    LOCAL = "local"
    GITHUB_RELEASE = "github_release"


class FieldType(str, Enum):
    """Types of UI form fields."""
    TEXT = "text"
    PASSWORD = "password"
    DROPDOWN = "dropdown"
    CHECKBOX = "checkbox"
    HEX_EDITOR = "hex_editor"
    NUMBER = "number"
    FILE = "file"
    HIDDEN = "hidden"


class EncodingType(str, Enum):
    """Parameter encoding types."""
    TEMPLATE = "template"
    TLV = "tlv"
    CUSTOM = "custom"
    NONE = "none"


class StepType(str, Enum):
    """Workflow step types."""
    SCRIPT = "script"
    COMMAND = "command"
    APDU = "apdu"
    DIALOG = "dialog"


class ParseType(str, Enum):
    """State reader parse types."""
    BYTE = "byte"
    TLV = "tlv"
    HEX = "hex"
    STRING = "string"
    ASCII = "ascii"
    OPENPGP_KEY = "openpgp_key"


# ============================================================================
# Field Definitions
# ============================================================================

@dataclass
class FieldValidation:
    """Validation rules for a form field."""
    pattern: Optional[str] = None  # Regex pattern
    message: Optional[str] = None  # Error message
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    min_value: Optional[int] = None
    max_value: Optional[int] = None
    equals_field: Optional[str] = None  # Must equal another field's value


@dataclass
class FieldOption:
    """A single option in a dropdown field."""
    label: str
    value: str


@dataclass
class ShowWhen:
    """Conditional display rules for a field."""
    field: str  # ID of the field to check
    equals: Optional[str] = None  # Show when field equals this value
    not_equals: Optional[str] = None  # Show when field doesn't equal this value
    is_set: Optional[bool] = None  # Show when field is/isn't set


@dataclass
class FieldDefinition:
    """Definition of a single form field."""
    id: str
    type: FieldType
    label: str
    placeholder: Optional[str] = None
    default: Optional[Any] = None
    required: bool = False
    options: list[FieldOption] = field(default_factory=list)  # For dropdowns
    validation: Optional[FieldValidation] = None
    show_when: Optional[ShowWhen] = None
    transform: Optional[str] = None  # e.g., "uppercase", "lowercase"
    rows: int = 4  # For hex_editor/textarea
    description: Optional[str] = None  # Help text
    width: float = 1.0  # Column width ratio (0.25, 0.33, 0.5, 1.0) for multi-column layouts
    readonly: bool = False  # If True, field is display-only


# ============================================================================
# UI Definitions
# ============================================================================

@dataclass
class TabDefinition:
    """Definition of a dialog tab."""
    name: str
    fields: list[FieldDefinition] = field(default_factory=list)


@dataclass
class DialogDefinition:
    """Definition of a dialog with tabs."""
    title: str = "Configuration"
    size: tuple[int, int] = (400, 400)
    tabs: list[TabDefinition] = field(default_factory=list)


@dataclass
class FormDefinition:
    """Definition of a simple form (no tabs)."""
    fields: list[FieldDefinition] = field(default_factory=list)


@dataclass
class InstallUIDefinition:
    """Installation UI definition - either dialog (tabs) or form (single page)."""
    dialog: Optional[DialogDefinition] = None
    form: Optional[FormDefinition] = None


# ============================================================================
# Management UI Definitions
# ============================================================================

@dataclass
class ApduCommand:
    """An APDU command to send to the card."""
    apdu: str  # APDU hex string with template variables
    command: Optional[str] = None  # Optional name for the command
    description: Optional[str] = None  # Description shown during execution


@dataclass
class StateParse:
    """How to parse an APDU response for state display."""
    type: ParseType
    offset: int = 0
    length: Optional[int] = None
    tag: Optional[str] = None  # For TLV parsing
    encoding: Optional[str] = None  # Value encoding, e.g., "ascii" to decode hex to text
    format: Optional[str] = None  # Value format: "int" to convert hex to decimal
    display: Optional[str] = None  # Display template, e.g., "{value}/3 attempts"
    display_map: Optional[dict[str, str]] = None  # Value -> display text mapping


@dataclass
class StateReader:
    """Definition for reading applet state."""
    id: str
    label: str
    apdu: str  # APDU to send
    parse: StateParse
    select_file: Optional[str] = None  # File ID to SELECT before reading (e.g., "E104")


@dataclass
class ManagementAction:
    """A management action that can be performed on an installed applet."""
    id: str
    label: str
    dialog: Optional[FormDefinition] = None  # Optional input dialog
    apdu_sequence: list[ApduCommand] = field(default_factory=list)
    workflow: Optional[str] = None  # Reference to a workflow by name
    description: Optional[str] = None


@dataclass
class ManagementUIDefinition:
    """Post-install management UI definition."""
    actions: list[ManagementAction] = field(default_factory=list)
    state_readers: list[StateReader] = field(default_factory=list)


# ============================================================================
# Applet Source Definitions
# ============================================================================

@dataclass
class SourceDefinition:
    """Definition of where to get the CAP file."""
    type: SourceType
    url: Optional[str] = None  # For HTTP/local
    path: Optional[str] = None  # For local files
    owner: Optional[str] = None  # GitHub owner
    repo: Optional[str] = None  # GitHub repo
    asset_pattern: Optional[str] = None  # Glob pattern for GitHub release assets
    extract_pattern: Optional[str] = None  # Pattern for files to extract from ZIP


@dataclass
class AIDSegment:
    """A segment of a dynamically constructed AID."""
    name: str
    length: int  # Length in bytes
    source: Optional[str] = None  # e.g., "field:manufacturer_id"
    default: Optional[str] = None  # Default hex value


@dataclass
class AIDConstruction:
    """Rules for dynamically constructing an AID."""
    base: str  # Base AID prefix
    segments: list[AIDSegment] = field(default_factory=list)


@dataclass
class StorageRequirements:
    """Applet storage requirements."""
    persistent: int = 0  # Bytes of persistent memory
    transient: int = 0  # Bytes of transient memory


@dataclass
class AppletMetadata:
    """Metadata about the applet."""
    name: str
    aid: Optional[str] = None  # Static AID
    aid_construction: Optional[AIDConstruction] = None  # Dynamic AID
    storage: StorageRequirements = field(default_factory=StorageRequirements)
    mutual_exclusion: list[str] = field(default_factory=list)  # CAP files this conflicts with
    description: Optional[str] = None  # Markdown description


@dataclass
class VariantDefinition:
    """Definition of a CAP file variant for multi-CAP plugins."""
    filename: str  # CAP filename (e.g., "SmartPGP-default.cap")
    display_name: str  # Friendly display name (e.g., "SmartPGP Default")
    description: Optional[str] = None  # Optional description
    aid: Optional[str] = None  # Applet AID for this variant
    # Per-variant overrides (optional - falls back to plugin-level definitions)
    storage: Optional[StorageRequirements] = None
    install_ui: Optional[InstallUIDefinition] = None
    management_ui: Optional[ManagementUIDefinition] = None


@dataclass
class AppletDefinition:
    """Complete applet definition."""
    source: SourceDefinition
    metadata: AppletMetadata
    variants: list[VariantDefinition] = field(default_factory=list)  # For multi-CAP plugins


# ============================================================================
# Parameter Encoding Definitions
# ============================================================================

@dataclass
class TLVEntry:
    """A single TLV entry for parameter encoding."""
    tag: str  # Hex tag
    value: str  # Template string for value
    length_bytes: int = 1  # Number of bytes for length field


@dataclass
class ParameterDefinition:
    """Definition of how to encode installation parameters."""
    encoding: EncodingType = EncodingType.NONE
    template: Optional[str] = None  # For template encoding
    tlv_structure: list[TLVEntry] = field(default_factory=list)  # For TLV encoding
    builder: Optional[str] = None  # Python snippet for custom encoding
    create_aid: Optional[str] = None  # AID to use with --create flag


# ============================================================================
# Workflow Definitions
# ============================================================================

@dataclass
class WorkflowStep:
    """A single step in a workflow."""
    id: str
    type: StepType
    name: Optional[str] = None
    description: Optional[str] = None
    depends_on: list[str] = field(default_factory=list)  # IDs of steps this depends on

    # For script steps
    script: Optional[str] = None

    # For command steps
    command: Optional[list[str]] = None  # Command and arguments

    # For APDU steps
    apdu: Optional[str] = None
    expected_sw: Optional[list[str]] = None  # Expected status words

    # For dialog steps
    fields: list[FieldDefinition] = field(default_factory=list)


@dataclass
class WorkflowDefinition:
    """Definition of a multi-step workflow."""
    steps: list[WorkflowStep] = field(default_factory=list)


# ============================================================================
# Hook Definitions
# ============================================================================

@dataclass
class HookDefinition:
    """Definition of a lifecycle hook."""
    type: Literal["script", "command"]
    script: Optional[str] = None  # Python snippet
    command: Optional[list[str]] = None  # Shell command


@dataclass
class HooksDefinition:
    """All lifecycle hooks."""
    pre_install: Optional[HookDefinition] = None
    post_install: Optional[HookDefinition] = None
    pre_uninstall: Optional[HookDefinition] = None
    post_uninstall: Optional[HookDefinition] = None


# ============================================================================
# Plugin Definition (Root)
# ============================================================================

@dataclass
class PluginInfo:
    """Basic plugin information."""
    name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""


@dataclass
class PluginSchema:
    """
    Root schema for a YAML plugin definition.

    This is the top-level dataclass that represents an entire plugin YAML file.
    """
    schema_version: str
    plugin: PluginInfo
    applet: AppletDefinition
    install_ui: Optional[InstallUIDefinition] = None
    management_ui: Optional[ManagementUIDefinition] = None
    parameters: Optional[ParameterDefinition] = None
    workflows: dict[str, WorkflowDefinition] = field(default_factory=dict)
    hooks: Optional[HooksDefinition] = None

    def get_aid(self) -> Optional[str]:
        """Get the static AID if defined."""
        return self.applet.metadata.aid

    def has_dynamic_aid(self) -> bool:
        """Check if this plugin uses dynamic AID construction."""
        return self.applet.metadata.aid_construction is not None

    def has_install_ui(self) -> bool:
        """Check if this plugin has installation UI."""
        return self.install_ui is not None and (
            self.install_ui.dialog is not None or self.install_ui.form is not None
        )

    def has_management_ui(self) -> bool:
        """Check if this plugin has management UI."""
        return (
            self.management_ui is not None and
            (len(self.management_ui.actions) > 0 or len(self.management_ui.state_readers) > 0)
        )

    def get_workflow(self, name: str) -> Optional[WorkflowDefinition]:
        """Get a workflow by name."""
        return self.workflows.get(name)


# ============================================================================
# Schema Version
# ============================================================================

CURRENT_SCHEMA_VERSION = "1.0"

SUPPORTED_SCHEMA_VERSIONS = ["1.0"]
